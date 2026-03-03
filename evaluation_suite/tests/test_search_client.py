"""Unit tests for search_client.py."""

from unittest.mock import MagicMock, patch

import pytest

from evaluation_suite.search_evaluation import search_client


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


# --- Tests for count_term_occurrences ---


def test_count_term_occurrences_single_match():
    """Test count_term_occurrences returns 1 for a single match."""
    assert search_client.count_term_occurrences("fractured arm", "fracture") == 1


def test_count_term_occurrences_multiple_matches():
    """Test count_term_occurrences returns correct count for multiple matches."""
    assert search_client.count_term_occurrences("bruise bruise bruise", "bruise") == 3


def test_count_term_occurrences_case_insensitive():
    """Test count_term_occurrences is case insensitive."""
    assert search_client.count_term_occurrences("Bruise BRUISE bruise", "bruise") == 3


def test_count_term_occurrences_no_match():
    """Test count_term_occurrences returns 0 when term not found."""
    assert search_client.count_term_occurrences("injury report", "fracture") == 0


def test_count_term_occurrences_empty_text():
    """Test count_term_occurrences returns 0 for empty text."""
    assert search_client.count_term_occurrences("", "bruise") == 0


def test_count_term_occurrences_empty_term():
    """Test count_term_occurrences returns 0 for empty search term."""
    assert search_client.count_term_occurrences("fractured arm", "") == 0


def test_count_term_occurrences_both_empty():
    """Test count_term_occurrences returns 0 when both text and term are empty."""
    assert search_client.count_term_occurrences("", "") == 0


@patch("evaluation_suite.search_evaluation.search_client.get_opensearch_client")
@patch("evaluation_suite.search_evaluation.search_client.EmbeddingGenerator")
@patch("evaluation_suite.search_evaluation.search_client.eval_settings")
def test_local_search_client_raises_on_general_exception(mock_settings, mock_embedding_gen, mock_get_client):
    """Test local_search_client raises on unexpected exceptions."""
    mock_settings.K_QUERIES = 5
    mock_embedding_gen.return_value.generate_embedding.side_effect = RuntimeError("Unexpected error")

    with pytest.raises(RuntimeError, match="Unexpected error"):
        search_client.local_search_client("fracture")


@patch("evaluation_suite.search_evaluation.search_client.get_opensearch_client")
@patch("evaluation_suite.search_evaluation.search_client.EmbeddingGenerator")
def test_local_search_client_returns_hits(mock_embedding_gen, mock_get_client):
    """Test local_search_client returns hits from OpenSearch."""
    from evaluation_suite.search_evaluation import evaluation_settings as eval_settings

    mock_embedding_gen.return_value.generate_embedding.return_value = [0.1, 0.2]
    mock_client = MagicMock()
    mock_client.search.return_value = {"hits": {"hits": sample_hits()}}
    mock_get_client.return_value = mock_client

    with (
        patch.object(eval_settings, "K_QUERIES", 5),
        patch.object(eval_settings, "KEYWORD_BOOST", 1.0),
        patch.object(eval_settings, "ANALYSER_BOOST", 0),
        patch.object(eval_settings, "FUZZY_BOOST", 0),
        patch.object(eval_settings, "WILDCARD_BOOST", 0),
        patch.object(eval_settings, "SEMANTIC_BOOST", 0),
        patch.object(eval_settings, "DATE_FORMAT_DETECTION", False),
        patch.object(eval_settings, "SCORE_FILTER", 0),
        patch.object(eval_settings, "ADAPTIVE_SCORE_FILTER", False),
    ):
        hits = search_client.local_search_client("fracture")

    assert len(hits) == 3
    assert hits[0]["_id"] == "c1"


@patch("evaluation_suite.search_evaluation.search_client.get_opensearch_client")
@patch("evaluation_suite.search_evaluation.search_client.EmbeddingGenerator")
def test_local_search_client_raises_on_connection_error(mock_embedding_gen, mock_get_client):
    """Test local_search_client raises when OpenSearch connection fails."""
    from evaluation_suite.search_evaluation.opensearch_client import OpenSearchConnectionError

    mock_embedding_gen.return_value.generate_embedding.return_value = [0.1, 0.2]
    # opensearchpy ConnectionError requires (message, error, info) args
    mock_get_client.side_effect = OpenSearchConnectionError(
        "Connection failed", ConnectionError("Connection refused"), {}
    )

    with pytest.raises(OpenSearchConnectionError):
        search_client.local_search_client("fracture")
