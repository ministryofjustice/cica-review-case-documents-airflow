from datetime import date
from unittest.mock import MagicMock

import pytest
from textractor.entities.document import Document

from ingestion_pipeline.chunking.schemas import (
    DocumentBoundingBox,
    DocumentChunk,
    DocumentMetadata,
    ProcessedDocument,
)
from ingestion_pipeline.chunking.textract import DocumentChunker  # Assuming this is the correct path
from ingestion_pipeline.indexing.indexer import OpenSearchIndexer
from ingestion_pipeline.orchestration.pipeline import ChunkAndIndexPipeline


@pytest.fixture
def mock_chunker(mocker):
    """Mocks the TextractDocumentChunker dependency."""
    return mocker.create_autospec(DocumentChunker, instance=True)


@pytest.fixture
def mock_indexer(mocker):
    """Mocks the OpenSearchIndexer dependency."""
    return mocker.create_autospec(OpenSearchIndexer, instance=True)


@pytest.fixture
def mock_document_metadata():
    """Provides a sample DocumentMetadata object."""
    return DocumentMetadata(
        ingested_doc_id="doc-123-test",
        source_file_name="test_file.pdf",
        page_count=1,
        case_ref="A-101",
        received_date=date.fromisoformat("2024-01-01"),
        correspondence_type="Email",
    )


@pytest.fixture
def mock_textractor_doc(mocker):
    """Provides a mock Textractor Document object."""
    return mocker.create_autospec(Document, instance=True)


@pytest.fixture
def mock_processed_data_with_chunks():
    """Provides a mock ProcessedDocument with chunks."""

    chunks = [
        DocumentChunk(
            chunk_id="c1",
            ingested_doc_id="doc-123-test",
            source_file_name="test_file.pdf",
            page_count=1,
            page_number=1,
            chunk_index=0,
            chunk_type="TEXT",
            confidence=1.0,
            chunk_text="Chunk 1",
            bounding_box=DocumentBoundingBox(Width=0.1, Height=0.1, Left=0.1, Top=0.1),
        ),
        DocumentChunk(
            chunk_id="c2",
            ingested_doc_id="doc-123-test",
            source_file_name="test_file.pdf",
            page_count=1,
            page_number=1,
            chunk_index=1,
            chunk_type="TEXT",
            confidence=1.0,
            chunk_text="Chunk 2",
            bounding_box=DocumentBoundingBox(Width=0.2, Height=0.2, Left=0.2, Top=0.2),
        ),
    ]

    mock_data = MagicMock(spec=ProcessedDocument)
    mock_data.chunks = chunks
    mock_data.pages = []
    mock_data.metadata = MagicMock(spec=DocumentMetadata)
    return mock_data


@pytest.fixture
def mock_processed_data_no_chunks():
    """Provides a mock ProcessedDocument with an empty chunk list."""
    mock_data = MagicMock(spec=ProcessedDocument)
    mock_data.chunks = []
    mock_data.pages = []
    mock_data.metadata = MagicMock(spec=DocumentMetadata)
    return mock_data


def test_orchestrator_initialization(mock_chunker, mock_indexer):
    """Tests that the orchestrator initializes correctly with its dependencies."""
    orchestrator = ChunkAndIndexPipeline(chunker=mock_chunker, chunk_indexer=mock_indexer)
    assert orchestrator.chunker == mock_chunker
    assert orchestrator.chunk_indexer == mock_indexer


def test_process_and_index_success(
    mock_chunker, mock_indexer, mock_textractor_doc, mock_document_metadata, mock_processed_data_with_chunks
):
    """
    Tests the full pipeline when chunking is successful and indexing proceeds.
    Verifies that both the chunker and indexer are called exactly once.
    """
    mock_chunker.chunk.return_value = mock_processed_data_with_chunks

    orchestrator = ChunkAndIndexPipeline(chunker=mock_chunker, chunk_indexer=mock_indexer)

    orchestrator.process_and_index(mock_textractor_doc, mock_document_metadata)

    mock_chunker.chunk.assert_called_once_with(mock_textractor_doc, mock_document_metadata)
    mock_indexer.index_documents.assert_called_once_with(mock_processed_data_with_chunks.chunks)


def test_process_and_index_no_chunks_skips_indexing(
    mock_chunker, mock_indexer, mock_textractor_doc, mock_document_metadata, mock_processed_data_no_chunks
):
    """
    Tests that if chunking returns no chunks, the indexing step is skipped.
    """
    mock_chunker.chunk.return_value = mock_processed_data_no_chunks

    orchestrator = ChunkAndIndexPipeline(chunker=mock_chunker, chunk_indexer=mock_indexer)

    orchestrator.process_and_index(mock_textractor_doc, mock_document_metadata)

    mock_chunker.chunk.assert_called_once()

    mock_indexer.index_documents.assert_not_called()


def test_process_and_index_chunker_raises_exception(
    mock_chunker, mock_indexer, mock_textractor_doc, mock_document_metadata
):
    """
    Tests that if the chunker fails, the pipeline raises the exception and indexer is never called.
    """

    mock_chunker.chunk.side_effect = Exception("Simulated chunking failure")

    orchestrator = ChunkAndIndexPipeline(chunker=mock_chunker, chunk_indexer=mock_indexer)

    with pytest.raises(Exception, match="Simulated chunking failure"):
        orchestrator.process_and_index(mock_textractor_doc, mock_document_metadata)

    mock_indexer.index_documents.assert_not_called()


def test_process_and_index_indexer_raises_exception(
    mock_chunker, mock_indexer, mock_textractor_doc, mock_document_metadata, mock_processed_data_with_chunks
):
    """
    Tests that if the indexer fails, the pipeline raises the exception.
    """

    mock_chunker.chunk.return_value = mock_processed_data_with_chunks
    mock_indexer.index_documents.side_effect = Exception("Simulated indexing failure")

    orchestrator = ChunkAndIndexPipeline(chunker=mock_chunker, chunk_indexer=mock_indexer)

    with pytest.raises(Exception, match="Simulated indexing failure"):
        orchestrator.process_and_index(mock_textractor_doc, mock_document_metadata)

    mock_chunker.chunk.assert_called_once()
