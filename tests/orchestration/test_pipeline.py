import datetime
import logging
from unittest import mock

import pytest

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.chunking.strategies.layout.layout_chunk_handler import ChunkError
from ingestion_pipeline.embedding.embedding_generator import EmbeddingError
from ingestion_pipeline.errors import (
    DlqCategory,
    EmptyTextractResponseError,
    PipelineError,
    ZeroChunksError,
)
from ingestion_pipeline.indexing.indexer import IndexingError
from ingestion_pipeline.orchestration.pipeline import Pipeline
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
    chunk.page_number = 1
    chunk.page_contains_handwriting = False
    chunk.chunk_id = "chunk-1"
    chunk.source_doc_id = "doc-123-test"
    processed_data.chunks = [chunk]
    mock_chunker.chunk.return_value = processed_data
    mock_embedding_generator.generate_embedding.return_value = [0.1, 0.2]
    mock_chunk_indexer.index_documents.return_value = None

    page_doc = mock.Mock()
    page_doc.page_num = 1
    page_doc.page_contains_handwriting = False
    page_documents = [page_doc]
    mock_page_processor.process.return_value = page_documents
    mock_page_indexer.index_documents.return_value = None

    result = pipeline.process_document(document_metadata)

    # Succeed-or-raise: a successful run returns None.
    assert result is None
    mock_textract_processor.process_document.assert_called_once_with(document_metadata.source_file_s3_uri)
    mock_page_processor.process.assert_called_once_with(mock_document, mock.ANY)
    mock_chunker.chunk.assert_called_once()
    mock_embedding_generator.generate_embedding.assert_called_once_with(chunk.chunk_text)
    mock_chunk_indexer.index_documents.assert_called_once_with(processed_data.chunks)
    mock_page_indexer.index_documents.assert_called_once_with(page_documents, id_field="page_id")


def test_process_document_no_document_raises_and_skips_downstream(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_page_processor,
    mock_page_indexer,
    mock_chunker,
    mock_chunk_indexer,
):
    """Textract returning no document raises a terminal EmptyTextractResponseError."""
    mock_textract_processor.process_document.return_value = None

    with pytest.raises(EmptyTextractResponseError) as excinfo:
        pipeline.process_document(document_metadata)

    err = excinfo.value
    assert err.category is DlqCategory.EMPTY_TEXTRACT_RESPONSE
    assert err.retryable is False
    assert err.source_doc_id == document_metadata.source_doc_id
    assert err.case_ref == document_metadata.case_ref
    # Nothing downstream ran.
    mock_textract_processor.process_document.assert_called_once_with(document_metadata.source_file_s3_uri)
    mock_page_processor.process.assert_not_called()
    mock_page_indexer.index_documents.assert_not_called()
    mock_chunker.chunk.assert_not_called()
    mock_chunk_indexer.index_documents.assert_not_called()


def test_process_document_no_chunks_raises_before_indexing_page_metadata(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_chunker,
    mock_page_processor,
    mock_page_indexer,
    mock_chunk_indexer,
):
    """A whole-document zero-chunk result raises before any page metadata is indexed."""
    mock_document = mock.Mock()
    mock_document.num_pages = 2
    mock_textract_processor.process_document.return_value = mock_document

    processed_data = mock.Mock()
    processed_data.chunks = []
    mock_chunker.chunk.return_value = processed_data

    with pytest.raises(ZeroChunksError) as excinfo:
        pipeline.process_document(document_metadata)

    err = excinfo.value
    assert err.category is DlqCategory.ZERO_CHUNKS_EXTRACTED_FROM_DOCUMENT
    assert err.retryable is False
    mock_chunker.chunk.assert_called_once()
    # Zero-chunk check happens before page processing/indexing, so neither runs.
    mock_page_processor.process.assert_not_called()
    mock_chunk_indexer.index_documents.assert_not_called()
    mock_page_indexer.index_documents.assert_not_called()


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
    cleanup_spy = mock.Mock()
    pipeline._cleanup_document = cleanup_spy

    with pytest.raises(PipelineError) as excinfo:
        pipeline.process_document(document_metadata)

    # An unexpected error is wrapped as an UNEXPECTED-category PipelineError.
    assert excinfo.value.category is DlqCategory.UNEXPECTED
    cleanup_spy.assert_called_once_with(document_metadata.source_doc_id, document_metadata.case_ref)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Connection refused", True),
        ("Failed to establish a new connection", True),
        ("Name or service not known", True),
        ("some other failure", False),
    ],
)
def test_is_opensearch_connectivity_error(message, expected):
    assert Pipeline._is_opensearch_connectivity_error(Exception(message)) is expected


def test_cleanup_indexed_data_suppresses_traceback_for_connectivity_error(
    pipeline,
    mock_chunk_indexer,
    mock_page_indexer,
    caplog,
):
    caplog.set_level(logging.DEBUG)
    mock_chunk_indexer.delete_documents_by_source_doc_id.side_effect = Exception("Connection refused")

    pipeline._cleanup_indexed_data("doc-123-test")

    mock_page_indexer.delete_documents_by_source_doc_id.assert_not_called()
    assert "Skipping verbose cleanup error log for connectivity issue" in caplog.text
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


def test_cleanup_page_images_prefix_deletes(pipeline, mock_page_processor):
    """Page-image cleanup prefix-deletes all images for the document."""
    pipeline._cleanup_page_images("doc-123-test", "25-787878")

    mock_page_processor.s3_document_service.delete_page_images.assert_called_once_with("25-787878", "doc-123-test")


def test_cleanup_page_images_swallows_errors(pipeline, mock_page_processor, caplog):
    """A cleanup failure is logged but never propagated (must not mask the original error)."""
    caplog.set_level(logging.ERROR)
    mock_page_processor.s3_document_service.delete_page_images.side_effect = RuntimeError("s3 down")

    # Must not raise.
    pipeline._cleanup_page_images("doc-123-test", "25-787878")

    assert any(
        record.levelno == logging.ERROR
        and "Failed to clean up page images for document doc-123-test" in record.getMessage()
        for record in caplog.records
    )


def test_cleanup_indexed_data_logs_traceback_for_non_connectivity_error(
    pipeline,
    mock_chunk_indexer,
    caplog,
):
    caplog.set_level(logging.ERROR)
    mock_chunk_indexer.delete_documents_by_source_doc_id.side_effect = RuntimeError("boom")

    pipeline._cleanup_indexed_data("doc-123-test")

    assert any(
        record.levelno == logging.ERROR
        and record.exc_info is not None
        and "Failed to clean up indexed data for document doc-123-test: boom" in record.getMessage()
        for record in caplog.records
    )


# --- Tests for pipeline execution order ---


def test_chunk_indexer_called_before_page_indexer(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_chunker,
    mock_embedding_generator,
    mock_chunk_indexer,
    mock_page_indexer,
    mock_page_processor,
):
    """Verify chunk indexing happens before page metadata indexing."""
    mock_document = mock.Mock()
    mock_document.num_pages = 1
    mock_textract_processor.process_document.return_value = mock_document

    chunk = mock.Mock()
    chunk.page_number = 1
    chunk.page_contains_handwriting = False
    chunk.chunk_id = "chunk-1"
    chunk.source_doc_id = "doc-123-test"
    processed_data = mock.Mock()
    processed_data.chunks = [chunk]
    mock_chunker.chunk.return_value = processed_data
    mock_embedding_generator.generate_embedding.return_value = [0.1]

    page_doc = mock.Mock()
    page_doc.page_num = 1
    page_doc.page_contains_handwriting = False
    mock_page_processor.process.return_value = [page_doc]

    call_order = []
    mock_chunk_indexer.index_documents.side_effect = lambda *a, **kw: call_order.append("chunk_indexer")
    mock_page_indexer.index_documents.side_effect = lambda *a, **kw: call_order.append("page_indexer")

    pipeline.process_document(document_metadata)

    assert call_order == ["chunk_indexer", "page_indexer"]


def test_page_metadata_receives_propagated_handwriting_flag(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_chunker,
    mock_embedding_generator,
    mock_chunk_indexer,
    mock_page_indexer,
    mock_page_processor,
):
    """Verify page metadata documents have handwriting flag set when chunks indicate handwriting."""
    mock_document = mock.Mock()
    mock_document.num_pages = 1
    mock_textract_processor.process_document.return_value = mock_document

    chunk = mock.Mock()
    chunk.page_number = 1
    chunk.page_contains_handwriting = True
    chunk.chunk_id = "chunk-hw"
    chunk.source_doc_id = "doc-123-test"
    processed_data = mock.Mock()
    processed_data.chunks = [chunk]
    mock_chunker.chunk.return_value = processed_data
    mock_embedding_generator.generate_embedding.return_value = [0.1]

    page_doc = mock.Mock()
    page_doc.page_num = 1
    page_doc.page_contains_handwriting = False
    mock_page_processor.process.return_value = [page_doc]

    pipeline.process_document(document_metadata)

    # After propagation, the page_doc should have been updated
    assert page_doc.page_contains_handwriting is True
    mock_page_indexer.index_documents.assert_called_once_with([page_doc], id_field="page_id")


def test_chunk_error_triggers_cleanup_before_page_indexing(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_chunker,
    mock_page_processor,
    mock_page_indexer,
    mock_chunk_indexer,
):
    """When chunking fails, cleanup runs and page metadata is never indexed."""
    mock_document = mock.Mock()
    mock_document.num_pages = 1
    mock_textract_processor.process_document.return_value = mock_document

    mock_page_processor.process.return_value = [mock.Mock()]
    mock_chunker.chunk.side_effect = ChunkError("chunking failed")

    with pytest.raises(ChunkError):
        pipeline.process_document(document_metadata)

    mock_page_indexer.index_documents.assert_not_called()
    mock_chunk_indexer.delete_documents_by_source_doc_id.assert_called_once_with("doc-123-test")
    mock_page_indexer.delete_documents_by_source_doc_id.assert_called_once_with("doc-123-test")


def test_chunk_indexing_error_triggers_cleanup(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_chunker,
    mock_embedding_generator,
    mock_chunk_indexer,
    mock_page_indexer,
    mock_page_processor,
):
    """When chunk indexing fails, cleanup deletes from both indices."""
    mock_document = mock.Mock()
    mock_document.num_pages = 1
    mock_textract_processor.process_document.return_value = mock_document

    chunk = mock.Mock()
    chunk.page_number = 1
    chunk.page_contains_handwriting = False
    chunk.chunk_id = "chunk-1"
    chunk.source_doc_id = "doc-123-test"
    processed_data = mock.Mock()
    processed_data.chunks = [chunk]
    mock_chunker.chunk.return_value = processed_data
    mock_embedding_generator.generate_embedding.return_value = [0.1]

    page_doc = mock.Mock()
    page_doc.page_num = 1
    page_doc.page_contains_handwriting = False
    mock_page_processor.process.return_value = [page_doc]

    mock_chunk_indexer.index_documents.side_effect = IndexingError("index failed")

    with pytest.raises(IndexingError):
        pipeline.process_document(document_metadata)

    mock_chunk_indexer.delete_documents_by_source_doc_id.assert_called_once_with("doc-123-test")
    mock_page_indexer.delete_documents_by_source_doc_id.assert_called_once_with("doc-123-test")
    mock_page_indexer.index_documents.assert_not_called()


def test_bare_lower_level_error_is_enriched_with_document_context(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_chunker,
    mock_embedding_generator,
    mock_chunk_indexer,
    mock_page_indexer,
    mock_page_processor,
):
    """A lower-level error raised with only a message gets document context backfilled.

    Most errors (IndexingError, ChunkError, EmbeddingError, ...) are raised deep in
    the pipeline with no document context. The orchestrator must populate
    source_doc_id/case_ref/s3_uri before re-raising so failure_context() is complete.
    """
    mock_document = mock.Mock()
    mock_document.num_pages = 1
    mock_textract_processor.process_document.return_value = mock_document

    chunk = mock.Mock()
    chunk.page_number = 1
    chunk.page_contains_handwriting = False
    chunk.chunk_id = "chunk-1"
    chunk.source_doc_id = "doc-123-test"
    processed_data = mock.Mock()
    processed_data.chunks = [chunk]
    mock_chunker.chunk.return_value = processed_data
    mock_embedding_generator.generate_embedding.return_value = [0.1]

    page_doc = mock.Mock()
    page_doc.page_num = 1
    page_doc.page_contains_handwriting = False
    mock_page_processor.process.return_value = [page_doc]

    # Raised with only a message: context fields default to None.
    mock_chunk_indexer.index_documents.side_effect = IndexingError("index failed")

    with pytest.raises(IndexingError) as excinfo:
        pipeline.process_document(document_metadata)

    err = excinfo.value
    assert err.source_doc_id == document_metadata.source_doc_id
    assert err.case_ref == document_metadata.case_ref
    assert err.s3_uri == document_metadata.source_file_s3_uri

    context = err.failure_context()
    assert context["source_doc_id"] == document_metadata.source_doc_id
    assert context["case_ref"] == document_metadata.case_ref
    assert context["s3_uri"] == document_metadata.source_file_s3_uri


def test_existing_error_context_is_preserved_not_overwritten(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_chunker,
    mock_embedding_generator,
    mock_chunk_indexer,
    mock_page_indexer,
    mock_page_processor,
):
    """Context already supplied by a terminal error is preserved, not overwritten.

    When an error carries its own document context, the orchestrator must not clobber
    it with the current document's metadata.
    """
    mock_document = mock.Mock()
    mock_document.num_pages = 1
    mock_textract_processor.process_document.return_value = mock_document

    chunk = mock.Mock()
    chunk.page_number = 1
    chunk.page_contains_handwriting = False
    chunk.chunk_id = "chunk-1"
    chunk.source_doc_id = "doc-123-test"
    processed_data = mock.Mock()
    processed_data.chunks = [chunk]
    mock_chunker.chunk.return_value = processed_data
    mock_embedding_generator.generate_embedding.return_value = [0.1]

    page_doc = mock.Mock()
    page_doc.page_num = 1
    page_doc.page_contains_handwriting = False
    mock_page_processor.process.return_value = [page_doc]

    # Error already carries context that differs from the current document.
    mock_chunk_indexer.index_documents.side_effect = IndexingError(
        "index failed",
        source_doc_id="other-doc",
        case_ref="99-999999",
        s3_uri="s3://other/file.pdf",
    )

    with pytest.raises(IndexingError) as excinfo:
        pipeline.process_document(document_metadata)

    err = excinfo.value
    assert err.source_doc_id == "other-doc"
    assert err.case_ref == "99-999999"
    assert err.s3_uri == "s3://other/file.pdf"


def test_chunks_not_modified_by_propagation(
    pipeline,
    document_metadata,
    mock_textract_processor,
    mock_chunker,
    mock_embedding_generator,
    mock_chunk_indexer,
    mock_page_indexer,
    mock_page_processor,
):
    """Verify chunk objects passed to chunk_indexer retain their original field values."""
    mock_document = mock.Mock()
    mock_document.num_pages = 1
    mock_textract_processor.process_document.return_value = mock_document

    chunk = mock.Mock()
    chunk.page_number = 1
    chunk.page_contains_handwriting = True
    chunk.chunk_id = "chunk-1"
    chunk.source_doc_id = "doc-123-test"
    chunk.chunk_text = "original text"
    processed_data = mock.Mock()
    processed_data.chunks = [chunk]
    mock_chunker.chunk.return_value = processed_data
    mock_embedding_generator.generate_embedding.return_value = [0.1]

    page_doc = mock.Mock()
    page_doc.page_num = 1
    page_doc.page_contains_handwriting = False
    mock_page_processor.process.return_value = [page_doc]

    pipeline.process_document(document_metadata)

    # Chunk fields should remain unchanged after propagation
    assert chunk.page_contains_handwriting is True
    assert chunk.chunk_text == "original text"
    assert chunk.page_number == 1
    mock_chunk_indexer.index_documents.assert_called_once_with(processed_data.chunks)


# --- Tests for _propagate_handwriting_flags ---


class TestPropagateHandwritingFlags:
    """Unit tests for Pipeline._propagate_handwriting_flags static method."""

    @staticmethod
    def _make_page(page_num, source_doc_id="doc-123"):
        """Create a minimal DocumentPage-like mock with required attributes."""
        page = mock.Mock()
        page.page_num = page_num
        page.page_contains_handwriting = False
        page.source_doc_id = source_doc_id
        return page

    @staticmethod
    def _make_chunk(page_number, page_contains_handwriting=False, chunk_id="chunk-1", source_doc_id="doc-123"):
        """Create a minimal DocumentChunk-like mock with required attributes."""
        chunk = mock.Mock()
        chunk.page_number = page_number
        chunk.page_contains_handwriting = page_contains_handwriting
        chunk.chunk_id = chunk_id
        chunk.source_doc_id = source_doc_id
        return chunk

    def test_single_page_with_handwriting_chunk_sets_flag(self):
        page = self._make_page(1)
        chunk = self._make_chunk(1, page_contains_handwriting=True)

        Pipeline._propagate_handwriting_flags([page], [chunk])

        assert page.page_contains_handwriting is True

    def test_single_page_multiple_chunks_one_has_handwriting(self):
        page = self._make_page(1)
        chunk1 = self._make_chunk(1, page_contains_handwriting=False, chunk_id="c1")
        chunk2 = self._make_chunk(1, page_contains_handwriting=True, chunk_id="c2")

        Pipeline._propagate_handwriting_flags([page], [chunk1, chunk2])

        assert page.page_contains_handwriting is True

    def test_single_page_all_chunks_no_handwriting(self):
        page = self._make_page(1)
        chunk1 = self._make_chunk(1, page_contains_handwriting=False, chunk_id="c1")
        chunk2 = self._make_chunk(1, page_contains_handwriting=False, chunk_id="c2")

        Pipeline._propagate_handwriting_flags([page], [chunk1, chunk2])

        assert page.page_contains_handwriting is False

    def test_multiple_pages_only_correct_page_flagged(self):
        page1 = self._make_page(1)
        page2 = self._make_page(2)
        chunk_p1 = self._make_chunk(1, page_contains_handwriting=True, chunk_id="c1")
        chunk_p2 = self._make_chunk(2, page_contains_handwriting=False, chunk_id="c2")

        Pipeline._propagate_handwriting_flags([page1, page2], [chunk_p1, chunk_p2])

        assert page1.page_contains_handwriting is True
        assert page2.page_contains_handwriting is False

    def test_page_with_no_corresponding_chunks_remains_false(self):
        page1 = self._make_page(1)
        page2 = self._make_page(2)
        # Only page 1 has chunks
        chunk = self._make_chunk(1, page_contains_handwriting=False, chunk_id="c1")

        Pipeline._propagate_handwriting_flags([page1, page2], [chunk])

        assert page1.page_contains_handwriting is False
        assert page2.page_contains_handwriting is False

    def test_chunk_references_nonexistent_page_raises_pipeline_error(self):
        page = self._make_page(1)
        chunk = self._make_chunk(99, page_contains_handwriting=False, chunk_id="orphan-chunk")

        with pytest.raises(PipelineError, match="page_number=99"):
            Pipeline._propagate_handwriting_flags([page], [chunk])

    def test_empty_chunks_list_leaves_all_pages_unchanged(self):
        page1 = self._make_page(1)
        page2 = self._make_page(2)

        Pipeline._propagate_handwriting_flags([page1, page2], [])

        assert page1.page_contains_handwriting is False
        assert page2.page_contains_handwriting is False
