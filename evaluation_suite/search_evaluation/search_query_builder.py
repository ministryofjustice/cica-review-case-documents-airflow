"""Hybrid search query builder for OpenSearch.

This module builds OpenSearch query dicts and applies score filtering.
It is used by search_client to execute searches against OpenSearch.

Responsibilities:
- Build hybrid search queries (keyword, analyser, fuzzy, wildcard, semantic)
- Apply adaptive score filtering with semantic fallback
"""

from evaluation_suite.search_evaluation import evaluation_settings as eval_settings
from evaluation_suite.search_evaluation.date_formats import extract_dates_for_search


def _build_hybrid_clauses(query_text: str, query_vector: list[float], k: int) -> list[dict]:
    """Build the standard hybrid search clauses based on evaluation settings.

    Returns a list of should clauses for keyword, analyzer, fuzzy, wildcard, and semantic search.
    Each clause is only included if its corresponding boost setting is greater than 0.

    Args:
        query_text: The text query to search for.
        query_vector: The embedding vector for semantic search.
        k: Number of nearest neighbours for knn search.

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
        clauses.append({"knn": {"embedding": {"vector": query_vector, "k": k, "boost": eval_settings.SEMANTIC_BOOST}}})

    return clauses


def create_hybrid_query(query_text: str, query_vector: list[float], k: int = 5) -> dict:
    """Create a hybrid search query combining keyword, fuzzy, and semantic vector search.

    Each search type is only included if its boost value is greater than 0.
    For queries containing dates (when DATE_FORMAT_DETECTION is enabled), uses ONLY
    match_phrase for date variants (no fuzzy/semantic).

    Restricts results to the case specified in CASE_FILTER.

    Args:
        query_text: The text query to search for.
        query_vector: The embedding vector for semantic search.
        k: Number of results to return.

    Returns:
        OpenSearch query dict.
    """
    should_clauses = []

    date_variants = extract_dates_for_search(query_text) if eval_settings.DATE_FORMAT_DETECTION else []

    if date_variants:
        for date in date_variants:
            should_clauses.append({"match_phrase": {"chunk_text": {"query": date, "boost": 2}}})

        query_body = {
            "size": k,
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

    should_clauses = _build_hybrid_clauses(query_text, query_vector, k)

    query_body = {
        "size": k,
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
