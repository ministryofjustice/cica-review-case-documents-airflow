"""Unit tests for search_query_builder.py."""

from unittest.mock import patch

from evaluation_suite.search_evaluation import search_query_builder


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


# --- Tests for _build_hybrid_clauses ---


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_build_hybrid_clauses_all_boosts_active(mock_settings):
    """Test _build_hybrid_clauses returns all clauses when all boosts are active."""
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 1.0
    mock_settings.FUZZY_BOOST = 1.0
    mock_settings.WILDCARD_BOOST = 1.0
    mock_settings.SEMANTIC_BOOST = 1.0
    mock_settings.FUZZINESS = "AUTO"
    mock_settings.MAX_EXPANSIONS = 10
    mock_settings.PREFIX_LENGTH = 1

    clauses = search_query_builder._build_hybrid_clauses("test", [0.1, 0.2], k=5)
    clause_keys = [list(c.keys())[0] for c in clauses]

    assert "match" in clause_keys
    assert "fuzzy" in clause_keys
    assert "wildcard" in clause_keys
    assert "knn" in clause_keys
    assert len(clauses) == 5


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_build_hybrid_clauses_all_boosts_zero(mock_settings):
    """Test _build_hybrid_clauses returns empty list when all boosts are zero."""
    mock_settings.KEYWORD_BOOST = 0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0

    clauses = search_query_builder._build_hybrid_clauses("test", [0.1, 0.2], k=5)
    assert clauses == []


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_build_hybrid_clauses_keyword_only(mock_settings):
    """Test _build_hybrid_clauses returns only keyword clause when only KEYWORD_BOOST is set."""
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0

    clauses = search_query_builder._build_hybrid_clauses("test", [0.1, 0.2], k=5)
    assert len(clauses) == 1
    assert "match" in clauses[0]


# --- Tests for create_hybrid_query ---


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_for_search")
def test_create_hybrid_query_with_dates(mock_extract_dates, mock_settings):
    """Test create_hybrid_query uses match_phrase only when dates are detected."""
    mock_settings.DATE_FORMAT_DETECTION = True
    mock_extract_dates.return_value = ["12/05/2021", "2021-05-12"]

    query = search_query_builder.create_hybrid_query("12/05/2021", [0.1, 0.2], k=5)

    assert "bool" in query["query"]
    clauses = query["query"]["bool"]["should"]
    assert all("match_phrase" in c for c in clauses)
    assert query["query"]["bool"].get("minimum_should_match") == 1


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_for_search")
def test_create_hybrid_query_no_dates(mock_extract_dates, mock_settings):
    """Test create_hybrid_query uses hybrid clauses when no dates detected."""
    mock_settings.DATE_FORMAT_DETECTION = True
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0
    mock_extract_dates.return_value = []

    query = search_query_builder.create_hybrid_query("fracture", [0.1, 0.2], k=5)

    assert "bool" in query["query"]
    clauses = query["query"]["bool"]["should"]
    assert any("match" in c for c in clauses)
    assert "minimum_should_match" not in query["query"]["bool"]


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_for_search")
def test_create_hybrid_query_date_detection_disabled(mock_extract_dates, mock_settings):
    """Test create_hybrid_query skips date detection when DATE_FORMAT_DETECTION is False."""
    mock_settings.DATE_FORMAT_DETECTION = False
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0

    search_query_builder.create_hybrid_query("12/05/2021", [0.1, 0.2], k=5)

    mock_extract_dates.assert_not_called()


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
@patch("evaluation_suite.search_evaluation.search_query_builder.extract_dates_for_search")
def test_create_hybrid_query_contains_source_fields(mock_extract_dates, mock_settings):
    """Test create_hybrid_query always includes correct _source fields."""
    mock_settings.DATE_FORMAT_DETECTION = False
    mock_settings.KEYWORD_BOOST = 1.0
    mock_settings.ANALYSER_BOOST = 0
    mock_settings.FUZZY_BOOST = 0
    mock_settings.WILDCARD_BOOST = 0
    mock_settings.SEMANTIC_BOOST = 0

    query = search_query_builder.create_hybrid_query("fracture", [0.1, 0.2], k=5)

    assert "_source" in query
    assert "chunk_text" in query["_source"]
    assert "document_id" in query["_source"]
    assert "page_number" in query["_source"]
    assert "case_ref" in query["_source"]


# --- Tests for apply_adaptive_score_filter ---


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
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


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
def test_apply_adaptive_score_filter_no_hits_above_threshold(mock_settings):
    """Test apply_adaptive_score_filter returns empty when no hits above threshold."""
    mock_settings.ADAPTIVE_SCORE_FILTER = False
    hits = sample_hits()

    filtered, _, semantic_added = search_query_builder.apply_adaptive_score_filter(hits, score_filter=100.0)

    assert filtered == []
    assert semantic_added == 0


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
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


@patch("evaluation_suite.search_evaluation.search_query_builder.eval_settings")
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
