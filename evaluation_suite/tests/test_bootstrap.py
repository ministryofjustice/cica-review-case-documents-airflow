"""Unit tests for the OpenSearch bootstrap module."""

from unittest.mock import MagicMock, patch

from evaluation_suite.search_evaluation.opensearch import bootstrap


def test_ensure_chunk_index_creates_when_missing():
    """Index is created with the kNN mapping when it does not exist."""
    client = MagicMock()
    client.indices.exists.return_value = False

    created = bootstrap.ensure_chunk_index(client)

    assert created is True
    client.indices.create.assert_called_once()
    _, kwargs = client.indices.create.call_args
    assert kwargs["index"] == bootstrap.CHUNK_INDEX_NAME
    assert kwargs["body"]["settings"]["index.knn"] is True
    assert kwargs["body"]["mappings"]["properties"]["embedding"]["type"] == "knn_vector"
    assert kwargs["body"]["mappings"]["properties"]["embedding"]["dimension"] == 1024


def test_ensure_chunk_index_skips_when_present():
    """Existing index is left untouched."""
    client = MagicMock()
    client.indices.exists.return_value = True

    created = bootstrap.ensure_chunk_index(client)

    assert created is False
    client.indices.create.assert_not_called()


def test_count_indexed_chunks_reads_count():
    """count_indexed_chunks returns the OpenSearch count value."""
    client = MagicMock()
    client.count.return_value = {"count": 42}

    assert bootstrap.count_indexed_chunks(client) == 42


def test_count_indexed_chunks_for_case_filters_by_case_ref():
    """count_indexed_chunks_for_case passes a case_ref term filter to the count API."""
    client = MagicMock()
    client.count.return_value = {"count": 17}

    result = bootstrap.count_indexed_chunks_for_case("26-700001", client)

    assert result == 17
    _, kwargs = client.count.call_args
    query = kwargs["body"]["query"]
    assert query == {"bool": {"filter": {"term": {"case_ref": "26-700001"}}}}


def test_reset_chunk_index_deletes_then_recreates():
    """reset_chunk_index deletes the existing index and recreates it."""
    client = MagicMock()
    # exists() is True for the delete check, then False for the recreate check.
    client.indices.exists.side_effect = [True, False]

    bootstrap.reset_chunk_index(client)

    client.indices.delete.assert_called_once_with(index=bootstrap.CHUNK_INDEX_NAME)
    client.indices.create.assert_called_once()


def test_reset_chunk_index_creates_when_absent():
    """reset_chunk_index creates the index without deleting when it does not exist."""
    client = MagicMock()
    client.indices.exists.return_value = False

    bootstrap.reset_chunk_index(client)

    client.indices.delete.assert_not_called()
    client.indices.create.assert_called_once()


@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.index_documents")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.count_indexed_chunks")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.ensure_chunk_index")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.get_opensearch_client")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.check_opensearch_health")
def test_bootstrap_indexes_when_empty(mock_health, mock_get_client, mock_ensure, mock_count, mock_index_documents):
    """Ingestion runs when the index is empty, and the post-index count is returned."""
    mock_count.return_value = 0

    result = bootstrap.bootstrap_opensearch()

    mock_health.assert_called_once()
    mock_ensure.assert_called_once()
    mock_index_documents.assert_called_once()
    assert result == 0


@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.index_documents")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.count_indexed_chunks")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.ensure_chunk_index")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.get_opensearch_client")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.check_opensearch_health")
def test_bootstrap_skips_ingestion_when_populated(
    mock_health, mock_get_client, mock_ensure, mock_count, mock_index_documents
):
    """Ingestion is skipped when the index already has documents, count is returned."""
    mock_count.return_value = 10

    result = bootstrap.bootstrap_opensearch()

    mock_index_documents.assert_not_called()
    assert result == 10


@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.index_documents")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.count_indexed_chunks")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.ensure_chunk_index")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.get_opensearch_client")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.check_opensearch_health")
def test_bootstrap_skips_ingestion_when_disabled(
    mock_health, mock_get_client, mock_ensure, mock_count, mock_index_documents
):
    """index_if_empty=False never triggers ingestion or a count, and returns None."""
    result = bootstrap.bootstrap_opensearch(index_if_empty=False)

    mock_count.assert_not_called()
    mock_index_documents.assert_not_called()
    assert result is None


@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.index_documents")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.count_indexed_chunks_for_case")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.ensure_chunk_index")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.get_opensearch_client")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.check_opensearch_health")
def test_bootstrap_skips_ingestion_for_case_already_indexed(
    mock_health, mock_get_client, mock_ensure, mock_count_for_case, mock_index_documents
):
    """When case_ref is provided and that case has chunks, ingestion is skipped."""
    mock_count_for_case.return_value = 25

    result = bootstrap.bootstrap_opensearch(case_ref="26-700001")

    mock_count_for_case.assert_called_once()
    call_args = mock_count_for_case.call_args[0]
    assert call_args[0] == "26-700001"
    mock_index_documents.assert_not_called()
    assert result == 25


@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.index_documents")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.count_indexed_chunks_for_case")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.ensure_chunk_index")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.get_opensearch_client")
@patch("evaluation_suite.search_evaluation.opensearch.bootstrap.check_opensearch_health")
def test_bootstrap_indexes_when_case_not_yet_indexed(
    mock_health, mock_get_client, mock_ensure, mock_count_for_case, mock_index_documents
):
    """When case_ref is provided and that case has no chunks, ingestion runs."""
    mock_count_for_case.return_value = 0

    bootstrap.bootstrap_opensearch(case_ref="26-700002")

    mock_index_documents.assert_called_once()
