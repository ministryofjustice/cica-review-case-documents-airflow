"""Hybrid search query builder for OpenSearch.

This module builds OpenSearch query dicts and applies score filtering.
It is used by search_client to execute searches against OpenSearch.

Responsibilities:
- Build hybrid search queries (keyword, analyser, fuzzy, wildcard, semantic)
- Apply adaptive score filtering with semantic fallback
- Support simple and combined query modes for date+text and multi-term text searches
"""

import logging

from evaluation_suite.search_evaluation import evaluation_settings as eval_settings
from evaluation_suite.search_evaluation.date_formats import (
    extract_dates_from_search_string,
    generate_date_format_variants,
    generate_month_year_variants,
)

logger = logging.getLogger("search_query_builder")


def _build_hybrid_clauses(query_text: str, query_vector: list[float], result_size: int) -> list[dict]:
    """Build the standard hybrid search clauses based on evaluation settings.

    Returns a list of should clauses for keyword, analyzer, fuzzy, wildcard, and semantic search.
    Each clause is only included if its corresponding boost setting is greater than 0.

    Args:
        query_text: The text query to search for.
        query_vector: The embedding vector for semantic search.
        result_size: Number of nearest neighbours for knn search.

    Returns:
        List of OpenSearch query clause dicts.
    """
    clauses = []

    if eval_settings.KEYWORD_BOOST > 0:
        clauses.append({"match": {"chunk_text": {"query": query_text, "boost": eval_settings.KEYWORD_BOOST}}})

    if eval_settings.ANALYSER_BOOST > 0:
        clauses.append(
            {
                "match": {
                    "chunk_text.english": {
                        "query": query_text,
                        "boost": eval_settings.ANALYSER_BOOST,
                    }
                }
            }
        )

    if eval_settings.FUZZY_BOOST > 0:
        clauses.append(
            {
                "fuzzy": {
                    "chunk_text": {
                        "value": query_text,
                        "fuzziness": eval_settings.FUZZINESS,
                        "max_expansions": eval_settings.MAX_EXPANSIONS,
                        "prefix_length": eval_settings.PREFIX_LENGTH,
                        "boost": eval_settings.FUZZY_BOOST,
                    }
                }
            }
        )

    if eval_settings.WILDCARD_BOOST > 0:
        clauses.append(
            {
                "wildcard": {
                    "chunk_text": {
                        "value": f"*{query_text}*",
                        "boost": eval_settings.WILDCARD_BOOST,
                    }
                }
            }
        )

    if eval_settings.SEMANTIC_BOOST > 0:
        clauses.append(
            {"knn": {"embedding": {"vector": query_vector, "k": result_size, "boost": eval_settings.SEMANTIC_BOOST}}}
        )

    return clauses


def _build_tiered_text_query(query_text: str) -> list[dict]:
    """Build tiered text query for multi-term searches without dates.

    Creates a tiered query structure:
    - Tier 1 (highest): ALL search terms required (operator: "and")
    - Tier 2 (medium): MOST search terms required (minimum_should_match)
    - Tier 3 (fallback): ANY search term matches (operator: "or")

    Args:
        query_text: The text query to search for.

    Returns:
        List of should clauses for the tiered query.
    """
    return [
        # Tier 1: All terms required
        {
            "match": {
                "chunk_text": {
                    "query": query_text,
                    "operator": "and",
                    "boost": eval_settings.TEXT_TIER1_BOOST,
                }
            }
        },
        # Tier 2: Most terms required
        {
            "match": {
                "chunk_text": {
                    "query": query_text,
                    "minimum_should_match": eval_settings.TEXT_MINIMUM_SHOULD_MATCH,
                    "boost": eval_settings.TEXT_TIER2_BOOST,
                }
            }
        },
        # Tier 3: Any term (fallback)
        {
            "match": {
                "chunk_text": {
                    "query": query_text,
                    "operator": "or",
                    "boost": eval_settings.TEXT_TIER3_BOOST,
                }
            }
        },
    ]


def _build_combined_date_query(
    remaining_text: str,
    exact_variants: list[str],
    partial_variants: list[str],
    query_text: str,
) -> list[dict]:
    """Build tiered combined query for date+text searches.

    Creates a tiered query structure:
    - Tier 1 (highest): Text phrase AND exact date (any variant)
    - Tier 2 (medium): Exact date AND partial match of remaining text terms
    - Tier 3 (fallback): Simple bag-of-words query

    Args:
        remaining_text: The non-date portion of the search query.
        exact_variants: List of exact date format variants.
        partial_variants: List of month-year only variants.
        query_text: Original full query text for fallback.

    Returns:
        List of should clauses for the tiered query.
    """
    should_clauses: list[dict] = []

    # Tier 1: Text phrase AND exact date variants
    if remaining_text and exact_variants:
        exact_date_should = [
            {"match_phrase": {"chunk_text": {"query": v, "boost": eval_settings.COMBINED_EXACT_DATE_BOOST}}}
            for v in exact_variants
        ]

        tier1 = {
            "bool": {
                "must": [
                    {
                        "match_phrase": {
                            "chunk_text": {
                                "query": remaining_text,
                                "slop": eval_settings.COMBINED_PHRASE_SLOP,
                                "boost": eval_settings.COMBINED_PHRASE_BOOST,
                            }
                        }
                    },
                    {"bool": {"should": exact_date_should, "minimum_should_match": 1}},
                ],
                "boost": eval_settings.COMBINED_TIER1_BOOST,
            }
        }
        should_clauses.append(tier1)

    # Tier 2: Exact date AND partial match of remaining text terms
    if remaining_text and exact_variants:
        exact_date_should_t2 = [
            {"match_phrase": {"chunk_text": {"query": v, "boost": eval_settings.COMBINED_EXACT_DATE_BOOST}}}
            for v in exact_variants
        ]

        tier2 = {
            "bool": {
                "must": [
                    {
                        "match": {
                            "chunk_text": {
                                "query": remaining_text,
                                "minimum_should_match": eval_settings.TEXT_MINIMUM_SHOULD_MATCH,
                                "boost": eval_settings.COMBINED_PHRASE_BOOST - 1,
                            }
                        }
                    },
                    {"bool": {"should": exact_date_should_t2, "minimum_should_match": 1}},
                ],
                "boost": eval_settings.COMBINED_TIER2_BOOST,
            }
        }
        should_clauses.append(tier2)

    # Tier 3: Fallback - date variants OR remaining text (no thresholds)
    for v in exact_variants:
        should_clauses.append({"match_phrase": {"chunk_text": {"query": v, "boost": eval_settings.DATE_QUERY_BOOST}}})
    if remaining_text:
        should_clauses.append({"match": {"chunk_text": {"query": remaining_text, "operator": "or"}}})

    return should_clauses


def create_hybrid_query(query_text: str, query_vector: list[float], result_size: int = 5) -> dict:
    """Create a hybrid search query combining keyword, fuzzy, and semantic vector search.

    Each search type is only included if its boost value is greater than 0.
    For queries containing dates (when DATE_FORMAT_DETECTION is enabled):
    - Simple mode: Flat OR query with date variants and remaining text
    - Combined mode: Tiered AND query preferring chunks with both text and date

    For non-date queries:
    - Simple mode: Flat hybrid clauses (keyword, analyser, fuzzy, wildcard, semantic)
    - Combined mode: Tiered text query (all terms > most terms > any term) with
      supplementary fuzzy/wildcard/semantic clauses

    Restricts results to the case specified in CASE_FILTER.

    Args:
        query_text: The text query to search for.
        query_vector: The embedding vector for semantic search.
        result_size: Number of results to return.

    Returns:
        OpenSearch query dict.
    """
    should_clauses: list[dict] = []

    # Extract dates and generate variants if date detection is enabled
    if eval_settings.DATE_FORMAT_DETECTION:
        extraction = extract_dates_from_search_string(query_text)

        if extraction.dates:
            logger.debug(
                f"Date detection: found {len(extraction.dates)} date(s) in '{query_text}', "
                f"remaining_text='{extraction.remaining_text}'"
            )

            # Generate variants for each extracted date using its matched pattern
            all_exact_variants: set[str] = set()
            all_partial_variants: set[str] = set()

            for i, date in enumerate(extraction.dates):
                matched_pattern = extraction.matched_patterns[i] if i < len(extraction.matched_patterns) else {}

                # Generate exact date variants
                exact_variants = generate_date_format_variants(date, matched_pattern)
                if exact_variants:
                    all_exact_variants.update(exact_variants)
                else:
                    all_exact_variants.add(date)

                # Generate partial (month-year) variants for combined mode
                if eval_settings.QUERY_MODE == "combined":
                    partial_variants = generate_month_year_variants(date, matched_pattern)
                    all_partial_variants.update(partial_variants)

            logger.debug(
                f"Generated {len(all_exact_variants)} exact variant(s), "
                f"{len(all_partial_variants)} partial variant(s), mode='{eval_settings.QUERY_MODE}'"
            )

            # Build query based on mode
            if eval_settings.QUERY_MODE == "combined" and extraction.remaining_text:
                # Combined mode: tiered AND query
                logger.debug("Using combined query mode (tiered AND)")
                should_clauses = _build_combined_date_query(
                    remaining_text=extraction.remaining_text,
                    exact_variants=list(all_exact_variants),
                    partial_variants=list(all_partial_variants),
                    query_text=query_text,
                )
            else:
                # Simple mode (default): flat OR query
                logger.debug("Using simple query mode (flat OR)")
                for variant in all_exact_variants:
                    should_clauses.append(
                        {"match_phrase": {"chunk_text": {"query": variant, "boost": eval_settings.DATE_QUERY_BOOST}}}
                    )

                if extraction.remaining_text:
                    should_clauses.append(
                        {"match": {"chunk_text": {"query": extraction.remaining_text, "operator": "or"}}}
                    )

            query_body = {
                "size": result_size,
                "_source": ["document_id", "page_number", "chunk_text", "case_ref"],
                "query": {
                    "bool": {
                        "should": should_clauses,
                        "minimum_should_match": 1,
                        "filter": {"term": {"case_ref": eval_settings.CASE_FILTER}},
                    }
                },
            }

            return query_body

    # Standard query (no dates detected or date detection disabled)
    if eval_settings.QUERY_MODE == "combined":
        # Tiered text query: all terms > most terms > any term
        logger.debug("Using combined text query mode (tiered match)")
        should_clauses = _build_tiered_text_query(query_text)
    else:
        # Simple mode: flat hybrid clauses
        should_clauses = _build_hybrid_clauses(query_text, query_vector, result_size)

    # Add supplementary clauses (fuzzy, wildcard, semantic) if enabled
    if eval_settings.QUERY_MODE == "combined":
        for clause in _build_hybrid_clauses(query_text, query_vector, result_size):
            # Skip keyword/analyser match clauses (already covered by tiered query)
            key = list(clause.keys())[0]
            if key not in ("match",):
                should_clauses.append(clause)

    query_body = {
        "size": result_size,
        "_source": ["document_id", "page_number", "chunk_text", "case_ref"],
        "query": {
            "bool": {
                "should": should_clauses,
                "filter": {"term": {"case_ref": eval_settings.CASE_FILTER}},
            }
        },
    }

    return query_body


def apply_adaptive_score_filter(hits: list[dict], score_filter: float) -> tuple[list[dict], float, int]:
    """Apply additive semantic fallback filtering based on evaluation settings.

    Prioritizes keyword results (high score threshold). If fewer than
    MIN_RESULTS_BEFORE_FALLBACK keyword results exist, supplements with
    semantic results (lower score threshold) up to MAX_SEMANTIC_RESULTS.

    Args:
        hits: List of search hits from OpenSearch.
        score_filter: Primary score threshold for keyword results.

    Returns:
        Tuple of (filtered_hits, effective_score_filter, semantic_results_added).
    """
    keyword_hits = [hit for hit in hits if hit["_score"] >= score_filter]

    if eval_settings.ADAPTIVE_SCORE_FILTER and len(keyword_hits) < eval_settings.MIN_RESULTS_BEFORE_FALLBACK:
        keyword_ids = {hit["_id"] for hit in keyword_hits}

        semantic_hits = [
            hit
            for hit in hits
            if eval_settings.SEMANTIC_SCORE_FILTER <= hit["_score"] < score_filter and hit["_id"] not in keyword_ids
        ]

        semantic_to_add = semantic_hits[: eval_settings.MAX_SEMANTIC_RESULTS]
        combined_hits = keyword_hits + semantic_to_add

        return combined_hits, score_filter, len(semantic_to_add)

    return keyword_hits, score_filter, 0
