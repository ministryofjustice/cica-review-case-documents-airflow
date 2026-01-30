import datetime
import logging
from unittest import mock

import pytest

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.chunking.textract_document_chunker import ChunkError
from ingestion_pipeline.embedding.embedding_generator import EmbeddingError
from ingestion_pipeline.indexing.indexer import IndexingError
from ingestion_pipeline.orchestration.pipeline import Pipeline, PipelineError
from ingestion_pipeline.textract.textract_processor import TextractProcessingError


@pytest.fixture
def document_metadata():
    return DocumentMetadata(
        source_doc_id="doc-123-test",
        source_file_name="test_file.pdf",
        source_file_s3_uri="s3://bucket/test_file.pdf",
        page_count=1,
        case_ref="25-787878",
        received_date=datetime.datetime.fromisoformat("2024-01-01"),
        correspondence_type="Email",
    )


@pytest.fixture
def mock_textract_processor():
    return mock.Mock()


@pytest.fixture
def mock_chunker():
    return mock.Mock()


@pytest.fixture
def mock_embedding_generator():
    return mock.Mock()


@pytest.fixture
def mock_chunk_indexer():
    return mock.Mock()


@pytest.fixture
def mock_page_indexer():
    return mock.Mock()


@pytest.fixture
def mock_page_processor():
    return mock.Mock()


@pytest.fixture
def pipeline(
    mock_textract_processor,
    mock_chunker,
    mock_embedding_generator,
    mock_chunk_indexer,
    mock_page_indexer,
    mock_page_processor,
):
    return Pipeline(
        textract_processor=mock_textract_processor,
        chunker=mock_chunker,
        embedding_generator=mock_embedding_generator,
        chunk_indexer=mock_chunk_indexer,
        page_indexer=mock_page_indexer,
        page_processor=mock_page_processor,
    )


@pytest.fixture(autouse=True)
def suppress_pipeline_errors(caplog):
    caplog.set_level(logging.ERROR)


def test_process_document_success(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_chunker,
    mock_embedding_generator,
    mock_chunk_indexer,
    mock_page_indexer,
    mock_page_processor,
):
    mock_document = mock.Mock()
    mock_document.num_pages = 5
    mock_textract_processor.process_document.return_value = mock_document

    processed_data = mock.Mock()
    chunk = mock.Mock()
    processed_data.chunks = [chunk]
    mock_chunker.chunk.return_value = processed_data
    mock_embedding_generator.generate_embedding.return_value = [0.1, 0.2]
    mock_chunk_indexer.index_documents.return_value = None

    page_documents = [mock.Mock()]
    mock_page_processor.process.return_value = page_documents
    mock_page_indexer.index_documents.return_value = None

    pipeline.process_document(document_metadata)

    mock_textract_processor.process_document.assert_called_once_with(document_metadata.source_file_s3_uri)
    mock_page_processor.process.assert_called_once_with(mock_document, mock.ANY)
    mock_page_indexer.index_documents.assert_called_once_with(page_documents, id_field="page_id")
    mock_chunker.chunk.assert_called_once()
    mock_embedding_generator.generate_embedding.assert_called_once_with(chunk.chunk_text)
    mock_chunk_indexer.index_documents.assert_called_once_with(processed_data.chunks)


def test_process_document_no_document(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_page_processor,
    mock_page_indexer,
    mock_chunker,
    mock_chunk_indexer,
):
    mock_textract_processor.process_document.return_value = None
    pipeline.process_document(document_metadata)
    mock_textract_processor.process_document.assert_called_once_with(document_metadata.source_file_s3_uri)
    mock_page_processor.process.assert_not_called()
    mock_page_indexer.index_documents.assert_not_called()
    mock_chunker.chunk.assert_not_called()
    mock_chunk_indexer.index_documents.assert_not_called()


def test_process_document_no_chunks(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_chunker,
    mock_page_processor,
    mock_page_indexer,
    mock_chunk_indexer,
):
    mock_document = mock.Mock()
    mock_document.num_pages = 2
    mock_textract_processor.process_document.return_value = mock_document

    processed_data = mock.Mock()
    processed_data.chunks = []
    mock_chunker.chunk.return_value = processed_data

    page_documents = [mock.Mock()]
    mock_page_processor.process.return_value = page_documents
    mock_page_indexer.index_documents.return_value = None

    pipeline.process_document(document_metadata)
    mock_chunker.chunk.assert_called_once()
    mock_chunk_indexer.index_documents.assert_not_called()


@pytest.mark.parametrize(
    "exception",
    [
        TextractProcessingError("textract error"),
        EmbeddingError("embedding error"),
        IndexingError("indexing error"),
        ChunkError("chunk error"),
    ],
)
def test_process_document_known_errors(
    pipeline,
    document_metadata,
    mock_textract_processor,
    exception,
):
    mock_textract_processor.process_document.side_effect = exception
    with pytest.raises(type(exception)):
        pipeline.process_document(document_metadata)


def test_process_document_unexpected_error(
    pipeline,
    document_metadata,
    mock_textract_processor,
):
    mock_textract_processor.process_document.side_effect = RuntimeError("unexpected")
    with pytest.raises(PipelineError):
        pipeline.process_document(document_metadata)
        assert pipeline._cleanup_indexed_data.called_once_with(document_metadata.source_doc_id)
