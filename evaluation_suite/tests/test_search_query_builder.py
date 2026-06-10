"""Unit tests for search_query_builder.py.

The query DSL mirrors frontend PR #209: a keyword ``match`` clause (lexicalBoost),
a vector ANN clause (neuralBoost) pre-scoped to the case, optional date
``match_phrase`` clauses (dateBoost) for the ``*-dates`` types, all combined in
``bool.should`` with ``minimum_should_match: 1`` and a ``bool.filter`` ``term`` on
``case_ref``.
"""

from unittest.mock import patch

import pytest

from evaluation_suite.search_evaluation import evaluation_settings as eval_settings
from evaluation_suite.search_evaluation.query import search_query_builder
from evaluation_suite.search_evaluation.query.search_type_config import QueryDslConfig, SearchType


def sample_hits():
    """Helper to provide sample OpenSearch hits for testing."""
    return [
        {
            "_id": "c1",
            "_score": 10.0,
            "_source": {
                "chunk_text": "fractured arm",
                "page_number": 1,
                "case_ref": "REF001",
                "document_id": "doc1",
            },
        },
        {
            "_id": "c2",
            "_score": 5.0,
            "_source": {"chunk_text": "injury report", "page_number": 2, "case_ref": "REF002", "document_id": "doc2"},
        },
        {
            "_id": "c3",
            "_score": 2.0,
            "_source": {
                "chunk_text": "no relevant info",
                "page_number": 3,
                "case_ref": "REF003",
                "document_id": "doc3",
            },
        },
    ]


def default_config():
    """A QueryDslConfig with the frontend-aligned defaults."""
    return QueryDslConfig(lexical_boost=20.0, neural_boost=4.0, date_boost=1.0, min_score=0.0)


def _clause_keys(clauses):
    return [next(iter(c.keys())) for c in clauses]


# --- Tests for create_hybrid_query: hybrid (keyword + vector, no dates) ---


def test_create_hybrid_query_has_keyword_and_neural_clauses():
    """Hybrid query combines a keyword match clause and a vector ANN clause."""
    query = search_query_builder.create_hybrid_query(
        "fracture", [0.1, 0.2], result_size=5, search_type=SearchType.HYBRID, config=default_config()
    )

    should = query["query"]["bool"]["should"]
    keys = _clause_keys(should)
    assert "match" in keys
    assert "knn" in keys
    assert all(key != "match_phrase" for key in keys)  # no date clauses for plain hybrid


def test_create_hybrid_query_keyword_clause_uses_lexical_boost():
    """The keyword match clause is boosted by the configured lexical boost."""
    query = search_query_builder.create_hybrid_query(
        "fracture", [0.1, 0.2], result_size=5, search_type=SearchType.HYBRID, config=default_config()
    )

    match_clause = next(c for c in query["query"]["bool"]["should"] if "match" in c)
    assert match_clause["match"]["chunk_text"]["query"] == "fracture"
    assert match_clause["match"]["chunk_text"]["boost"] == 20.0


def test_create_hybrid_query_neural_clause_uses_neural_boost_and_filter():
    """The ANN clause carries the vector, k, neural boost, and a case filter."""
    query = search_query_builder.create_hybrid_query(
        "fracture", [0.1, 0.2], result_size=7, search_type=SearchType.HYBRID, config=default_config()
    )

    knn_clause = next(c for c in query["query"]["bool"]["should"] if "knn" in c)["knn"]["embedding"]
    assert knn_clause["vector"] == [0.1, 0.2]
    assert knn_clause["k"] == 7
    assert knn_clause["boost"] == 4.0
    assert knn_clause["filter"] == {"term": {"case_ref": eval_settings.CASE_FILTER}}


def test_create_hybrid_query_uses_bool_filter_list_for_case_ref():
    """Case scoping uses bool.filter (a list of term clauses), not bool.must."""
    query = search_query_builder.create_hybrid_query(
        "fracture", [0.1, 0.2], result_size=5, search_type=SearchType.HYBRID, config=default_config()
    )

    bool_query = query["query"]["bool"]
    assert "must" not in bool_query
    assert bool_query["filter"] == [{"term": {"case_ref": eval_settings.CASE_FILTER}}]
    assert bool_query["minimum_should_match"] == 1


def test_create_hybrid_query_contains_source_fields_and_size():
    """The query always includes the expected _source fields and size."""
    query = search_query_builder.create_hybrid_query(
        "fracture", [0.1, 0.2], result_size=5, search_type=SearchType.HYBRID, config=default_config()
    )

    assert query["size"] == 5
    for field in ("document_id", "page_number", "chunk_text", "case_ref"):
        assert field in query["_source"]


def test_create_hybrid_query_omits_keyword_clause_when_lexical_boost_zero():
    """A zero lexical boost disables the keyword clause (ablation support)."""
    config = QueryDslConfig(lexical_boost=0.0, neural_boost=4.0, date_boost=1.0, min_score=0.0)
    query = search_query_builder.create_hybrid_query(
        "fracture", [0.1, 0.2], result_size=5, search_type=SearchType.HYBRID, config=config
    )

    keys = _clause_keys(query["query"]["bool"]["should"])
    assert "match" not in keys
    assert "knn" in keys


def test_create_hybrid_query_omits_neural_clause_when_neural_boost_zero():
    """A zero neural boost disables the ANN clause (ablation support)."""
    config = QueryDslConfig(lexical_boost=20.0, neural_boost=0.0, date_boost=1.0, min_score=0.0)
    query = search_query_builder.create_hybrid_query(
        "fracture", [0.1, 0.2], result_size=5, search_type=SearchType.HYBRID, config=config
    )

    keys = _clause_keys(query["query"]["bool"]["should"])
    assert "knn" not in keys
    assert "match" in keys


def test_create_hybrid_query_adds_min_score_when_configured():
    """min_score is added to the query body only when configured > 0."""
    with_min = search_query_builder.create_hybrid_query(
        "fracture",
        [0.1, 0.2],
        result_size=5,
        search_type=SearchType.HYBRID,
        config=QueryDslConfig(lexical_boost=20.0, neural_boost=4.0, date_boost=1.0, min_score=0.3),
    )
    without_min = search_query_builder.create_hybrid_query(
        "fracture", [0.1, 0.2], result_size=5, search_type=SearchType.HYBRID, config=default_config()
    )

    assert with_min["min_score"] == 0.3
    assert "min_score" not in without_min


# --- Tests for create_hybrid_query: hybrid-dates (adds date match_phrase) ---


@patch("evaluation_suite.search_evaluation.query.search_query_builder.extract_dates_for_search")
def test_create_hybrid_dates_query_adds_date_clauses(mock_extract_dates):
    """hybrid-dates adds a match_phrase clause per detected date variant."""
    mock_extract_dates.return_value = ["12/05/2021", "2021-05-12"]

    query = search_query_builder.create_hybrid_query(
        "12/05/2021", [0.1, 0.2], result_size=5, search_type=SearchType.HYBRID_DATES, config=default_config()
    )

    should = query["query"]["bool"]["should"]
    date_clauses = [c for c in should if "match_phrase" in c]
    assert len(date_clauses) == 2
    assert all(c["match_phrase"]["chunk_text"]["boost"] == 1.0 for c in date_clauses)
    assert query["query"]["bool"]["minimum_should_match"] == 1


@patch("evaluation_suite.search_evaluation.query.search_query_builder.extract_dates_for_search")
def test_create_hybrid_dates_query_without_dates_has_no_date_clauses(mock_extract_dates):
    """hybrid-dates with no detected dates produces no match_phrase clauses."""
    mock_extract_dates.return_value = []

    query = search_query_builder.create_hybrid_query(
        "fracture", [0.1, 0.2], result_size=5, search_type=SearchType.HYBRID_DATES, config=default_config()
    )

    keys = _clause_keys(query["query"]["bool"]["should"])
    assert "match_phrase" not in keys
    assert "match" in keys
    assert "knn" in keys


@patch("evaluation_suite.search_evaluation.query.search_query_builder.extract_dates_for_search")
def test_create_hybrid_query_plain_hybrid_does_not_extract_dates(mock_extract_dates):
    """Plain hybrid never runs date extraction (dates are a *-dates feature)."""
    search_query_builder.create_hybrid_query(
        "12/05/2021", [0.1, 0.2], result_size=5, search_type=SearchType.HYBRID, config=default_config()
    )

    mock_extract_dates.assert_not_called()


# --- Tests for create_hybrid_query: unimplemented search types ---


@pytest.mark.parametrize(
    "search_type",
    [SearchType.KEYWORD, SearchType.KEYWORD_DATES, SearchType.SEMANTIC],
)
def test_create_hybrid_query_raises_for_unimplemented_types(search_type):
    """Defined-but-unimplemented search types raise NotImplementedError."""
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        search_query_builder.create_hybrid_query(
            "fracture", [0.1, 0.2], result_size=5, search_type=search_type, config=default_config()
        )


def test_create_hybrid_query_invalid_type_falls_back_to_default():
    """An invalid search type resolves to the default (hybrid-dates) and builds."""
    query = search_query_builder.create_hybrid_query(
        "fracture", [0.1, 0.2], result_size=5, search_type="not-a-real-type", config=default_config()
    )

    assert "bool" in query["query"]


def test_create_hybrid_query_defaults_to_settings_config():
    """When no config is passed, defaults are sourced from evaluation_settings."""
    query = search_query_builder.create_hybrid_query(
        "fracture", [0.1, 0.2], result_size=5, search_type=SearchType.HYBRID
    )

    match_clause = next(c for c in query["query"]["bool"]["should"] if "match" in c)
    assert match_clause["match"]["chunk_text"]["boost"] == eval_settings.KEYWORD_BOOST


# --- Tests for apply_adaptive_score_filter ---


@patch("evaluation_suite.search_evaluation.query.search_query_builder.eval_settings")
def test_apply_adaptive_score_filter_above_threshold(mock_settings):
    """Test apply_adaptive_score_filter returns only hits above threshold."""
    mock_settings.ADAPTIVE_SCORE_FILTER = False
    hits = sample_hits()

    filtered, effective_filter, semantic_added = search_query_builder.apply_adaptive_score_filter(
        hits, score_filter=6.0
    )

    assert len(filtered) == 1
    assert filtered[0]["_id"] == "c1"
    assert effective_filter == 6.0
    assert semantic_added == 0


@patch("evaluation_suite.search_evaluation.query.search_query_builder.eval_settings")
def test_apply_adaptive_score_filter_no_hits_above_threshold(mock_settings):
    """Test apply_adaptive_score_filter returns empty when no hits above threshold."""
    mock_settings.ADAPTIVE_SCORE_FILTER = False
    hits = sample_hits()

    filtered, _, semantic_added = search_query_builder.apply_adaptive_score_filter(hits, score_filter=100.0)

    assert filtered == []
    assert semantic_added == 0


@patch("evaluation_suite.search_evaluation.query.search_query_builder.eval_settings")
def test_apply_adaptive_score_filter_fallback_adds_semantic(mock_settings):
    """Test apply_adaptive_score_filter supplements with semantic hits when below MIN_RESULTS."""
    mock_settings.ADAPTIVE_SCORE_FILTER = True
    mock_settings.MIN_RESULTS_BEFORE_FALLBACK = 2
    mock_settings.SEMANTIC_SCORE_FILTER = 1.0
    mock_settings.MAX_SEMANTIC_RESULTS = 5
    hits = sample_hits()

    filtered, _, semantic_added = search_query_builder.apply_adaptive_score_filter(hits, score_filter=6.0)

    assert semantic_added > 0
    assert any(h["_id"] == "c1" for h in filtered)


@patch("evaluation_suite.search_evaluation.query.search_query_builder.eval_settings")
def test_apply_adaptive_score_filter_no_duplicates_in_fallback(mock_settings):
    """Test apply_adaptive_score_filter does not add duplicate hits in fallback."""
    mock_settings.ADAPTIVE_SCORE_FILTER = True
    mock_settings.MIN_RESULTS_BEFORE_FALLBACK = 5
    mock_settings.SEMANTIC_SCORE_FILTER = 1.0
    mock_settings.MAX_SEMANTIC_RESULTS = 10
    hits = sample_hits()

    filtered, _, _ = search_query_builder.apply_adaptive_score_filter(hits, score_filter=6.0)
    ids = [h["_id"] for h in filtered]

    assert len(ids) == len(set(ids))
