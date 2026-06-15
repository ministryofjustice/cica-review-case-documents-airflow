"""Search query builder for OpenSearch, mirroring the frontend hybrid search DSL.

This module builds OpenSearch query dicts and applies score filtering. It is
used by search_client to execute searches against OpenSearch.

The query DSL mirrors the frontend (``api/DAL/utils/buildQueryJson/``) so
evaluation searches reproduce what users experience:
- A keyword ``match`` clause on ``chunk_text`` (boosted by ``lexical_boost``).
- A vector ANN clause pre-scoped to the case (boosted by ``neural_boost``).
- For ``*-dates`` types, date format variants are grouped in a nested
  ``bool.should`` with a single ``date_boost`` applied to the group — matching
  the frontend's ``{ bool: { should: matchPhraseClauses, minimum_should_match: 1,
  boost: dateBoost } }`` pattern so variant matches don't compound the boost.
- Clauses combined in ``bool.should`` with ``minimum_should_match: 1`` and a
  ``bool.filter`` ``term`` on ``case_ref``.

NOTE ON THE ANN CLAUSE — divergence from the frontend, by design:
The frontend uses a ``neural`` clause (``{neural: {embedding: {query_text, ...}}}``)
which relies on an embedding model registered server-side in its OpenSearch.
The evaluation suite instead generates embeddings client-side (Titan, via
``EmbeddingGenerator``) and passes a precomputed ``vector``, so it uses a
``knn`` clause (``{knn: {embedding: {vector, ...}}}``). The structure (k, boost,
and a pre-scoping ``filter``) mirrors the frontend DSL; only the transport differs. If a
given local OpenSearch knn engine rejects a filtered knn clause, the
``bool.filter`` term still scopes results to the case, so correctness is
preserved.

NOTE ON ``min_score`` — intentional divergence from the frontend, by design:
The frontend sets ``min_score: 2.25`` (``semanticMinScore``) on hybrid queries to
filter low-relevance results before they reach the UI. The evaluation suite sets
``min_score: 0.0`` (via ``MIN_SCORE`` in ``evaluation_settings``) to retrieve all
candidate results, then applies its own downstream score filtering via
``apply_adaptive_score_filter``. This is intentional: suppressing low-scoring
results inside OpenSearch would prevent the evaluation from measuring where the
relevance boundary actually falls.

NOTE ON ANN ``k`` — intentional divergence from the frontend, by design:
The frontend fixes ``semanticK: 250`` so the neural candidate pool is stable
across pagination depths. The evaluation suite passes ``result_size`` as ``k``
(typically ``RESULT_SIZE = 40``). A smaller ``k`` is sufficient here because
evaluation runs fetch a single page of results and do not compare across pages.

Responsibilities:
- Build hybrid / hybrid-dates search queries matching the frontend DSL.
- Apply adaptive score filtering with semantic fallback.

Only ``hybrid`` and ``hybrid-dates`` are implemented; other search types raise
``NotImplementedError``.
"""

from evaluation_suite.search_evaluation import evaluation_settings as eval_settings
from evaluation_suite.search_evaluation.query.date_formats import extract_dates_for_search
from evaluation_suite.search_evaluation.query.search_type_config import (
    DEFAULT_SEARCH_TYPE,
    QueryDslConfig,
    SearchType,
    resolve_search_type,
)

_SOURCE_FIELDS = ["document_id", "page_number", "chunk_text", "case_ref"]


def _build_hybrid_query(
    query_text: str,
    query_vector: list[float],
    result_size: int,
    config: QueryDslConfig,
    include_dates: bool,
) -> dict:
    """Build a hybrid (keyword + vector [+ dates]) query mirroring the frontend DSL.

    Args:
        query_text: The text query to search for.
        query_vector: The precomputed embedding vector for the ANN clause.
        result_size: Number of results to return (also used as the ANN ``k``).
        config: Query DSL configuration (boosts, min_score).
        include_dates: When True (``hybrid-dates``), add ``match_phrase`` clauses
            for each detected date format variant.

    Returns:
        OpenSearch query dict.
    """
    should: list[dict] = []

    # Keyword clause (frontend lexicalBoost).
    if config.lexical_boost > 0:
        should.append({"match": {"chunk_text": {"query": query_text, "boost": config.lexical_boost}}})

    # Date clauses (frontend dateBoost) — only for the *-dates search types.
    # Grouped in a nested bool.should so all variants share a single dateBoost,
    # matching the frontend: { bool: { should: matchPhraseClauses,
    #                                  minimum_should_match: 1, boost: dateBoost } }
    if include_dates:
        date_variants = [
            {"match_phrase": {"chunk_text": date}}
            for date in extract_dates_for_search(query_text)
        ]
        if date_variants:
            should.append(
                {
                    "bool": {
                        "should": date_variants,
                        "minimum_should_match": 1,
                        "boost": config.date_boost,
                    }
                }
            )

    # Vector ANN clause (frontend neuralBoost), pre-scoped to the case.
    # See module docstring for why this uses knn+vector rather than neural.
    if config.neural_boost > 0 and query_vector:
        should.append(
            {
                "knn": {
                    "embedding": {
                        "vector": query_vector,
                        "k": result_size,
                        "boost": config.neural_boost,
                        "filter": {"term": {"case_ref": eval_settings.CASE_FILTER}},
                    }
                }
            }
        )

    bool_query: dict = {
        "should": should,
        "filter": [{"term": {"case_ref": eval_settings.CASE_FILTER}}],
    }
    if should:
        bool_query["minimum_should_match"] = 1

    query_body: dict = {
        "size": result_size,
        "_source": _SOURCE_FIELDS,
        "query": {"bool": bool_query},
    }
    if config.min_score and config.min_score > 0:
        query_body["min_score"] = config.min_score

    return query_body


def create_hybrid_query(
    query_text: str,
    query_vector: list[float],
    result_size: int = 5,
    search_type: str = DEFAULT_SEARCH_TYPE,
    config: QueryDslConfig | None = None,
) -> dict:
    """Create a search query for the given search type, mirroring the frontend DSL.

    Dispatches on ``search_type``. ``hybrid`` combines a keyword clause and a
    vector ANN clause; ``hybrid-dates`` additionally adds date ``match_phrase``
    clauses. Other search types are defined in the enum but not yet implemented
    and raise ``NotImplementedError``.

    Restricts results to the case specified in ``CASE_FILTER``.

    Args:
        query_text: The text query to search for.
        query_vector: The precomputed embedding vector for the ANN clause.
        result_size: Number of results to return (also used as the ANN ``k``).
        search_type: One of the values in ``SearchType``. Defaults to the
            frontend default (``hybrid-dates``).
        config: Optional query DSL config. Defaults to values sourced from
            ``evaluation_settings`` so boost optimization keeps working.

    Returns:
        OpenSearch query dict.

    Raises:
        NotImplementedError: If ``search_type`` is valid but not yet implemented.
    """
    resolved_type = resolve_search_type(search_type)
    config = config or QueryDslConfig.from_settings()

    if resolved_type == SearchType.HYBRID:
        return _build_hybrid_query(query_text, query_vector, result_size, config, include_dates=False)
    if resolved_type == SearchType.HYBRID_DATES:
        return _build_hybrid_query(query_text, query_vector, result_size, config, include_dates=True)

    raise NotImplementedError(f"Search type '{resolved_type}' is not yet implemented — use 'hybrid' or 'hybrid-dates'")


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
