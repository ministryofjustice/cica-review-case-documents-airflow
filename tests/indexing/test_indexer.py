import logging
from unittest.mock import MagicMock

import pytest
from opensearchpy.helpers import BulkIndexError

from ingestion_pipeline.chunking.schemas import DocumentBoundingBox, DocumentChunk
from ingestion_pipeline.indexing.indexer import OpenSearchIndexer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@pytest.fixture
def mock_opensearch_client(mocker):
    """Mocks the OpenSearch client and its connection using pytest-mock."""
    return mocker.patch("ingestion_pipeline.indexing.indexer.OpenSearch", autospec=True)


@pytest.fixture
def mock_helpers_bulk(mocker):
    """Mocks the opensearchpy.helpers.bulk function using pytest-mock."""
    return mocker.patch("ingestion_pipeline.indexing.indexer.helpers.bulk", autospec=True)


@pytest.fixture
def sample_documents():
    """Provides a list of sample OpenSearchDocument objects for testing."""
    return [
        DocumentChunk(
            chunk_id="doc1-p1-c0",
            ingested_doc_id="doc1",
            source_file_name="file1.pdf",
            page_count=2,
            page_number=1,
            chunk_index=0,
            chunk_type="LAYOUT_TEXT",
            chunk_text="This is the first chunk.",
            confidence=0.95,
            bounding_box=DocumentBoundingBox(Width=0.1, Height=0.1, Left=0.1, Top=0.1),
        ),
        DocumentChunk(
            chunk_id="doc1-p1-c1",
            ingested_doc_id="doc1",
            source_file_name="file1.pdf",
            page_count=2,
            page_number=1,
            chunk_index=1,
            chunk_type="LAYOUT_TEXT",
            chunk_text="This is the second chunk.",
            confidence=0.96,
            bounding_box=DocumentBoundingBox(Width=0.2, Height=0.2, Left=0.2, Top=0.2),
        ),
    ]


def test_indexer_initialization_success(mock_opensearch_client):
    """
    Tests that the indexer initializes correctly with a valid host, port, and index name.
    """
    # The instantiation of OpenSearchIndexer will cause the mocked OpenSearch class to be called.
    indexer = OpenSearchIndexer(host="test_host", port=9200, index_name="test_index")

    # The mock object represents the class, so we assert the call on the mock itself.
    mock_opensearch_client.assert_called_once_with(
        hosts=[{"host": "test_host", "port": 9200}],
        http_auth=("admin", "really-secure-passwordAa!1"),
        use_ssl=False,
        verify_certs=False,
        ssl_assert_hostname=False,
    )

    assert indexer.index_name == "test_index"
    assert indexer.client == mock_opensearch_client.return_value


def test_indexer_initialization_with_empty_index_name_raises_error():
    """
    Tests that initializing the indexer with an empty index name raises a ValueError.
    """
    with pytest.raises(ValueError, match="Index name cannot be empty."):
        OpenSearchIndexer(host="test_host", port=9200, index_name="")


def test_index_documents_success(mock_helpers_bulk, mock_opensearch_client, sample_documents):
    """
    Tests that documents are successfully indexed using the bulk helper.
    """
    # Configure the mock to simulate a successful bulk operation
    mock_helpers_bulk.return_value = (len(sample_documents), [])

    indexer = OpenSearchIndexer(host="localhost", port=9200, index_name="test_index")
    # Set the mock client on the indexer instance
    indexer.client = mock_opensearch_client

    success_count, errors = indexer.index_documents(sample_documents)

    # Assert that the bulk helper was called correctly
    mock_helpers_bulk.assert_called_once()
    assert success_count == len(sample_documents)
    assert errors == []


def test_index_documents_with_empty_list_returns_zero(mock_helpers_bulk, mock_opensearch_client):
    """
    Tests that passing an empty list of documents returns 0 successes and no errors.
    """
    indexer = OpenSearchIndexer(host="localhost", port=9200, index_name="test_index")
    indexer.client = mock_opensearch_client

    success_count, errors = indexer.index_documents([])

    mock_helpers_bulk.assert_not_called()
    assert success_count == 0
    assert errors == []


def test_index_documents_with_partial_failures(mock_helpers_bulk, mock_opensearch_client, sample_documents):
    """
    Tests that partial failures from the bulk helper are correctly handled and returned.
    """
    mock_errors = [{"index": {"error": {"reason": "Test error"}}}, {"index": {"error": {"reason": "Another error"}}}]
    # Simulate partial success with 1 document failing
    mock_helpers_bulk.return_value = (1, mock_errors)

    indexer = OpenSearchIndexer(host="localhost", port=9200, index_name="test_index")
    indexer.client = mock_opensearch_client

    success_count, errors = indexer.index_documents(sample_documents)

    assert success_count == 1
    assert len(errors) == len(mock_errors)
    assert errors == mock_errors


def test_index_documents_raises_on_bulk_exception(mock_helpers_bulk, mock_opensearch_client, sample_documents):
    """
    Tests that a bulk operation exception is caught, logged, and re-raised.
    """
    # Simulate a critical error during the bulk operation
    mock_helpers_bulk.side_effect = BulkIndexError("Simulated bulk error", [])

    indexer = OpenSearchIndexer(host="localhost", port=9200, index_name="test_index")
    indexer.client = mock_opensearch_client

    with pytest.raises(BulkIndexError, match="Simulated bulk error"):
        indexer.index_documents(sample_documents)


def test_generate_bulk_actions_missing_id_field_raises_error(mock_opensearch_client):
    """
    Tests that a document missing the specified ID field raises an AttributeError.
    """
    # Create a mock document that is missing the 'chunk_id' attribute
    MockDocument = MagicMock()
    del MockDocument.chunk_id

    indexer = OpenSearchIndexer(host="localhost", port=9200, index_name="test_index")
    indexer.client = mock_opensearch_client

    with pytest.raises(AttributeError, match="Document model is missing the required id_field 'chunk_id'."):
        # The generator will raise the error on the first iteration
        list(indexer._generate_bulk_actions([MockDocument], id_field="chunk_id"))
