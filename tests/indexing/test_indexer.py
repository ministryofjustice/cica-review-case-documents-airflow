import datetime
import logging
from unittest.mock import MagicMock

import pytest
from opensearchpy.helpers import BulkIndexError

from ingestion_pipeline.chunking.schemas import DocumentBoundingBox, DocumentChunk, DocumentPage
from ingestion_pipeline.indexing.indexer import IndexingError, OpenSearchIndexer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@pytest.fixture
def mock_opensearch_client(mocker):
    """Mocks the OpenSearch client and its connection using pytest-mock."""
    mock_client = mocker.patch("ingestion_pipeline.indexing.indexer.OpenSearch", autospec=True)
    # Configure delete_by_query to return a proper dict
    mock_client.return_value.delete_by_query.return_value = {"deleted": 0}
    return mock_client


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
            source_doc_id="doc1",
            source_file_name="file1.pdf",
            source_file_s3_uri="s3://bucket/file1.pdf",
            case_ref="25-781234",
            correspondence_type="TYPE_A",
            page_count=2,
            page_number=1,
            chunk_index=0,
            chunk_type="LAYOUT_TEXT",
            chunk_text="This is the first chunk.",
            confidence=0.95,
            received_date=datetime.datetime.fromisoformat("2025-11-06"),
            bounding_box=DocumentBoundingBox(Width=0.1, Height=0.1, Left=0.1, Top=0.1),
        ),
        DocumentChunk(
            chunk_id="doc1-p1-c1",
            source_doc_id="doc1",
            source_file_name="file1.pdf",
            source_file_s3_uri="s3://bucket/file1.pdf",
            case_ref="25-781234",
            correspondence_type="TYPE_A",
            page_count=2,
            page_number=1,
            chunk_index=1,
            chunk_type="LAYOUT_TEXT",
            chunk_text="This is the second chunk.",
            confidence=0.96,
            received_date=datetime.datetime.fromisoformat("2025-11-06"),
            bounding_box=DocumentBoundingBox(Width=0.2, Height=0.2, Left=0.2, Top=0.2),
        ),
    ]


def test_indexer_initialization_success(mock_opensearch_client):
    indexer = OpenSearchIndexer(index_name="test_index", proxy_url="http://test_host:9200")

    mock_opensearch_client.assert_called_once_with(
        hosts=[{"host": "test_host", "port": 9200, "scheme": "http"}],
        http_auth=(),
        use_ssl=False,
        verify_certs=False,
        ssl_assert_hostname=False,
        timeout=30,
    )

    assert indexer.index_name == "test_index"
    assert indexer.client == mock_opensearch_client.return_value


def test_indexer_initialization_with_empty_index_name_raises_error():
    """Tests that initializing the indexer with an empty index name raises a ValueError."""
    with pytest.raises(ValueError, match="Index name cannot be empty."):
        OpenSearchIndexer(index_name="", proxy_url="http://test_host:9200")


def test_index_documents_with_bulk_indexer_success(mock_helpers_bulk, mock_opensearch_client, sample_documents):
    """Tests that documents are successfully indexed using the bulk helper."""
    mock_helpers_bulk.return_value = (len(sample_documents), [])

    indexer = OpenSearchIndexer(index_name="test_index", proxy_url="http://test_host:9200")
    # Set the mock client on the indexer instance
    indexer.client = mock_opensearch_client
    # Set the return value for delete_by_query on the instance, not the class
    indexer.client.delete_by_query.return_value = {"deleted": 0}

    success_count, errors = indexer.index_documents(sample_documents)

    mock_helpers_bulk.assert_called_once()
    assert success_count == len(sample_documents)
    assert errors == []


def test_index_documents_with_empty_list_returns_zero(mock_helpers_bulk, mock_opensearch_client):
    """Tests that passing an empty list of documents returns 0 successes and no errors."""
    indexer = OpenSearchIndexer(index_name="test_index", proxy_url="http://test_host:9200")
    indexer.client = mock_opensearch_client

    success_count, errors = indexer.index_documents([])

    mock_helpers_bulk.assert_not_called()
    assert success_count == 0
    assert errors == []


def test_index_documents_with_partial_failures(mock_helpers_bulk, mock_opensearch_client, sample_documents):
    """Tests that partial failures from the bulk helper are treated as critical errors and raise IndexingError."""
    mock_errors = [{"index": {"error": {"reason": "Test error"}}}, {"index": {"error": {"reason": "Another error"}}}]
    # Simulate partial success with errors returned
    mock_helpers_bulk.return_value = (1, mock_errors)

    indexer = OpenSearchIndexer(index_name="test_index", proxy_url="http://test_host:9200")
    indexer.client = mock_opensearch_client
    indexer.client.delete_by_query.return_value = {"deleted": 0}

    import re

    expected_message = (
        "Failed to index: Failed to index all chunks: "
        "[{'index': {'error': {'reason': 'Test error'}}}, "
        "{'index': {'error': {'reason': 'Another error'}}}]"
    )

    with pytest.raises(
        IndexingError,
        match=re.escape(expected_message),
    ):
        indexer.index_documents(sample_documents)


def test_index_documents_raises_on_bulk_exception(mock_helpers_bulk, mock_opensearch_client, sample_documents):
    """Tests that a bulk operation exception is caught, logged, and re-raised."""
    # Simulate a critical error during the bulk operation
    mock_helpers_bulk.side_effect = BulkIndexError("Simulated bulk error", ["error1"])

    indexer = OpenSearchIndexer(index_name="test_index", proxy_url="http://test_host:9200")
    indexer.client = mock_opensearch_client
    indexer.client.delete_by_query.return_value = {"deleted": 0}

    with pytest.raises(IndexingError, match="Failed to index documents due to bulk errors:"):
        indexer.index_documents(sample_documents)


def test_generate_bulk_actions_missing_id_field_raises_error(mock_opensearch_client):
    """Tests that a document missing the specified ID field raises an AttributeError."""
    # Create a mock document that is missing the 'chunk_id' attribute
    MockDocument = MagicMock()
    del MockDocument.chunk_id

    indexer = OpenSearchIndexer(index_name="test_index", proxy_url="http://test_host:9200")
    indexer.client = mock_opensearch_client

    with pytest.raises(AttributeError, match="Document model is missing the required id_field 'chunk_id'."):
        # The generator will raise the error on the first iteration
        list(indexer._generate_bulk_actions([MockDocument], id_field="chunk_id"))


def test_delete_documents_by_source_doc_id_success(mock_opensearch_client, mocker):
    mock_delete_by_query = mock_opensearch_client.delete_by_query
    mock_delete_by_query.return_value = {"deleted": 5}

    indexer = OpenSearchIndexer(index_name="test_index", proxy_url="http://test_host:9200")
    indexer.client = mock_opensearch_client

    source_doc_id = "doc1"

    mock_logger_info = mocker.patch("ingestion_pipeline.indexing.indexer.logger.info")
    indexer.delete_documents_by_source_doc_id(source_doc_id)

    mock_delete_by_query.assert_called_once_with(
        index="test_index",
        body={"query": {"match": {"source_doc_id": source_doc_id}}},
    )

    mock_logger_info.assert_called_with("Deleted 5 documents from index test_index")


def test_delete_documents_by_source_doc_id_exception(mock_opensearch_client):
    """Tests that exceptions from delete_by_query are propagated."""
    mock_opensearch_client.delete_by_query.side_effect = Exception("Delete error")

    indexer = OpenSearchIndexer(index_name="test_index", proxy_url="http://test_host:9200")
    indexer.client = mock_opensearch_client

    with pytest.raises(Exception, match="Delete error"):
        indexer.delete_documents_by_source_doc_id("doc3")


def test_indexer_initialization_with_invalid_proxy_url():
    """Tests that initializing with an invalid proxy URL raises a ValueError."""
    with pytest.raises(ValueError, match="Invalid OpenSearch proxy URL: not_a_url"):
        OpenSearchIndexer(index_name="test_index", proxy_url="not_a_url")


def test_indexer_initialization_with_https_scheme(mock_opensearch_client):
    """Tests that HTTPS proxy URL sets use_ssl=True and port=443 by default."""
    indexer = OpenSearchIndexer(index_name="secure_index", proxy_url="https://secure_host")
    mock_opensearch_client.assert_called_once_with(
        hosts=[{"host": "secure_host", "port": 443, "scheme": "https"}],
        http_auth=(),
        use_ssl=True,
        verify_certs=False,
        ssl_assert_hostname=False,
        timeout=30,
    )
    assert indexer.index_name == "secure_index"


def test_generate_bulk_actions_yields_correct_dict(sample_documents, mock_opensearch_client):
    """Tests that _generate_bulk_actions yields correct bulk action dicts."""
    indexer = OpenSearchIndexer(index_name="test_index", proxy_url="http://host:9200")
    indexer.client = mock_opensearch_client
    actions = list(indexer._generate_bulk_actions(sample_documents, id_field="chunk_id"))
    assert len(actions) == len(sample_documents)
    for doc, action in zip(sample_documents, actions):
        assert action["_op_type"] == "index"
        assert action["_index"] == "test_index"
        assert action["_id"] == doc.chunk_id
        assert action["_source"] == doc.model_dump()


def test_indexer_initialization_with_empty_proxy_url_raises_error():
    """Tests that initializing the indexer with an empty proxy URL raises a ValueError."""
    with pytest.raises(ValueError, match="The OpenSearch proxy URL cannot be empty."):
        OpenSearchIndexer(index_name="test_index", proxy_url="")


def test_indexer_initialization_with_http_scheme_no_port(mock_opensearch_client):
    """Tests that HTTP proxy URL without a port defaults to port 80."""
    indexer = OpenSearchIndexer(index_name="http_index", proxy_url="http://http_host")
    mock_opensearch_client.assert_called_once_with(
        hosts=[{"host": "http_host", "port": 80, "scheme": "http"}],
        http_auth=(),
        use_ssl=False,
        verify_certs=False,
        ssl_assert_hostname=False,
        timeout=30,
    )
    assert indexer.index_name == "http_index"


def test_indexer_initialization_with_https_scheme_and_port(mock_opensearch_client):
    """Tests that HTTPS proxy URL with a specified port uses that port."""
    indexer = OpenSearchIndexer(index_name="secure_index", proxy_url="https://secure_host:9201")
    mock_opensearch_client.assert_called_once_with(
        hosts=[{"host": "secure_host", "port": 9201, "scheme": "https"}],
        http_auth=(),
        use_ssl=True,
        verify_certs=False,
        ssl_assert_hostname=False,
        timeout=30,
    )
    assert indexer.index_name == "secure_index"


def test_index_documents_with_document_page(mock_helpers_bulk, mock_opensearch_client):
    """Tests indexing DocumentPage objects."""
    sample_pages = [
        DocumentPage(
            source_doc_id="doc1",
            page_num=1,
            page_id="page1",
            text="Page 1 text",
            page_width=8.5,
            page_height=11.0,
            received_date=datetime.datetime.fromisoformat("2025-11-06"),
        ),
        DocumentPage(
            source_doc_id="doc1",
            page_num=2,
            page_id="page2",
            text="Page 2 text",
            page_width=8.5,
            page_height=11.0,
            received_date=datetime.datetime.fromisoformat("2025-11-06"),
        ),
    ]
    mock_helpers_bulk.return_value = (len(sample_pages), [])
    indexer = OpenSearchIndexer(index_name="page_metadata", proxy_url="http://test_host:9200")
    indexer.client = mock_opensearch_client
    indexer.client.delete_by_query.return_value = {"deleted": 0}
    success_count, errors = indexer.index_documents(sample_pages, id_field="page_id")
    assert success_count == len(sample_pages)
    assert errors == []
