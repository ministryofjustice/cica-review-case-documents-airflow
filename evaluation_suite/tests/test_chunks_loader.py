"""Unit tests for chunks_loader.py."""

from unittest.mock import MagicMock, patch

import pytest

from evaluation_suite.search_evaluation.chunks_loader import (
    get_chunk_details_from_opensearch,
    load_all_chunks_from_opensearch,
)
from evaluation_suite.search_evaluation.opensearch_client import OpenSearchConnectionError


@patch("evaluation_suite.search_evaluation.chunks_loader.get_opensearch_client")
def test_load_all_chunks_success(mock_get_client):
    """Test successful loading of all chunks from OpenSearch with mocked client."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # Simulate count response
    mock_client.count.return_value = {"count": 2}

    # Simulate search and scroll responses
    mock_client.search.return_value = {
        "_scroll_id": "scroll123",
        "hits": {
            "hits": [
                {"_id": "chunk1", "_source": {"chunk_text": "text1"}},
                {"_id": "chunk2", "_source": {"chunk_text": "text2"}},
            ]
        },
    }
    mock_client.scroll.side_effect = [{"_scroll_id": "scroll123", "hits": {"hits": []}}]
    mock_client.clear_scroll.return_value = None

    chunks = load_all_chunks_from_opensearch()
    assert chunks == {"chunk1": "text1", "chunk2": "text2"}


@patch("evaluation_suite.search_evaluation.chunks_loader.get_opensearch_client")
def test_load_all_chunks_empty_index(mock_get_client):
    """Test loading chunks from an empty OpenSearch index."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.count.return_value = {"count": 0}

    chunks = load_all_chunks_from_opensearch()
    assert chunks == {}


@patch("evaluation_suite.search_evaluation.chunks_loader.get_opensearch_client")
def test_load_all_chunks_opensearch_connection_error(mock_get_client):
    """Test handling of OpenSearch connection error when loading chunks."""
    mock_get_client.side_effect = OpenSearchConnectionError(
        "Connection failed", ConnectionError("Connection refused"), {}
    )
    with pytest.raises(OpenSearchConnectionError):
        load_all_chunks_from_opensearch()


@patch("evaluation_suite.search_evaluation.chunks_loader.get_opensearch_client")
def test_load_all_chunks_generic_exception(mock_get_client):
    """Test handling of generic exception when loading chunks."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.count.side_effect = Exception("Something went wrong")
    with pytest.raises(Exception):
        load_all_chunks_from_opensearch()


@patch("evaluation_suite.search_evaluation.chunks_loader.get_opensearch_client")
def test_get_chunk_details_success(mock_get_client):
    """Test successful retrieval of chunk details from OpenSearch with mocked client."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_client.search.return_value = {
        "_scroll_id": "scroll123",
        "hits": {
            "hits": [
                {"_id": "chunk1", "_source": {"chunk_text": "text1", "page_number": 1, "case_ref": "ref1"}},
                {"_id": "chunk2", "_source": {"chunk_text": "text2", "page_number": 2, "case_ref": "ref2"}},
            ]
        },
    }
    mock_client.scroll.side_effect = [{"_scroll_id": "scroll123", "hits": {"hits": []}}]
    mock_client.clear_scroll.return_value = None

    chunks = get_chunk_details_from_opensearch()
    assert chunks == [
        {"chunk_id": "chunk1", "chunk_text": "text1", "page_number": 1, "case_ref": "ref1"},
        {"chunk_id": "chunk2", "chunk_text": "text2", "page_number": 2, "case_ref": "ref2"},
    ]


@patch("evaluation_suite.search_evaluation.chunks_loader.get_opensearch_client")
def test_get_chunk_details_opensearch_connection_error(mock_get_client):
    """Test handling of OpenSearch connection error when retrieving chunk details."""
    mock_get_client.side_effect = OpenSearchConnectionError(
        "Connection failed", ConnectionError("Connection refused"), {}
    )
    with pytest.raises(OpenSearchConnectionError):
        get_chunk_details_from_opensearch()


@patch("evaluation_suite.search_evaluation.chunks_loader.get_opensearch_client")
def test_get_chunk_details_generic_exception(mock_get_client):
    """Test handling of generic exception when retrieving chunk details."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.search.side_effect = Exception("Something went wrong")
    with pytest.raises(Exception):
        get_chunk_details_from_opensearch()
