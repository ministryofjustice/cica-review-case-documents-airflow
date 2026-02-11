"""Unit tests for document_chunker.py."""

import datetime
from unittest.mock import MagicMock, patch

import pytest
from textractor.entities.page import Page

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.schemas import DocumentBoundingBox, DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.textract_document_chunker import ChunkError, DocumentChunker


def create_mock_layout(block_type="LAYOUT_TEXT", text="some valid text", block_id="id-1"):
    """Creates a mock Textractor Layout object."""
    layout = MagicMock()
    layout.layout_type = block_type
    layout.text = text
    layout.id = block_id
    return layout


def create_mock_page(layouts, page_num=1, width=1000, height=1500):
    """Creates a mock Textractor Page object."""
    page = MagicMock()
    page.layouts = layouts
    page.page_num = page_num
    page.width = width
    page.height = height
    return page


def create_mock_document(pages, response={"some": "data"}):
    """Creates a mock Textractor Document object."""
    doc = MagicMock()
    doc.pages = pages
    doc.response = response
    return doc


@pytest.fixture
def document_metadata():
    """Provides a DocumentMetadata instance for tests."""
    return DocumentMetadata(
        source_doc_id="doc123",
        source_file_name="file.pdf",
        source_file_s3_uri="s3://bucket/25-787878/file.pdf",
        page_count=5,
        case_ref="25-787878",
        received_date=datetime.datetime.fromisoformat("2025-11-06T00:00:00"),
        correspondence_type="TC19",
    )


@pytest.fixture
def mock_strategy_handler():
    """Provides a generic mock strategy handler."""
    handler = MagicMock()
    # By default, return one mock chunk per call
    handler.chunk.return_value = [MagicMock(spec=DocumentChunk)]
    return handler


@pytest.fixture
def mock_strategy_handlers(mock_strategy_handler):
    """Provides a mapping of layout types to mock handlers."""
    return {"TEXT": mock_strategy_handler}


@pytest.fixture
def mock_document():
    """Provides a mock Document object for tests."""
    page1 = MagicMock()
    page1.layouts = [MagicMock(layout_type="TEXT", text="Text1")]
    page1.page_num = 1
    page1.width = 800
    page1.height = 600

    page2 = MagicMock()
    page2.layouts = [MagicMock(layout_type="TEXT", text="Text2")]
    page2.page_num = 2
    page2.width = 800
    page2.height = 600

    doc = MagicMock()
    doc.pages = [page1, page2]
    doc.response = {"some": "data"}
    return doc


def test_selects_correct_strategy_and_increments_index(document_metadata):
    # Arrange
    mock_text_strategy = MagicMock()
    mock_text_strategy.chunk.return_value = [MagicMock(spec=DocumentChunk), MagicMock(spec=DocumentChunk)]

    mock_table_strategy = MagicMock()
    mock_table_strategy.chunk.return_value = [MagicMock(spec=DocumentChunk)]  # Returns 1 chunk

    strategy_handlers = {
        "LAYOUT_TEXT": mock_text_strategy,
        "LAYOUT_TABLE": mock_table_strategy,
    }

    page = create_mock_page(layouts=[create_mock_layout("LAYOUT_TEXT"), create_mock_layout("LAYOUT_TABLE")])
    doc = create_mock_document(pages=[page])

    chunker = DocumentChunker(strategy_handlers)

    with patch("ingestion_pipeline.chunking.textract_document_chunker.ChunkMerger", autospec=True) as mock_merger:
        mock_merger.return_value.group_atomic_chunks.side_effect = lambda group_atomic_chunks: group_atomic_chunks
        processed_doc = chunker.chunk(doc, document_metadata)

    mock_text_strategy.chunk.assert_called_once()
    # assert chunk_index_start == 0
    assert mock_text_strategy.chunk.call_args.args[3] == 0
    # assert chunk_index_start is now 2
    assert mock_table_strategy.chunk.call_args.args[3] == 2
    assert len(processed_doc.chunks) == 3


def test_skips_blocks_without_strategy_or_text(document_metadata, mock_strategy_handler):
    """Verifies that blocks are skipped if they have no associated strategy.
    no text, or only whitespace text.
    """
    # Arrange
    strategy_handlers = {"LAYOUT_TEXT": mock_strategy_handler}
    page = create_mock_page(
        layouts=[
            create_mock_layout("LAYOUT_TEXT", text="This is valid."),  # Should be processed
            create_mock_layout("LAYOUT_FIGURE", text="No strategy for this"),  # Should be skipped
            create_mock_layout("LAYOUT_TEXT", text=""),  # Should be skipped
            create_mock_layout("LAYOUT_TEXT", text="   \n\t "),  # Should be skipped
        ]
    )
    doc = create_mock_document(pages=[page])

    chunker = DocumentChunker(strategy_handlers)

    with patch("ingestion_pipeline.chunking.textract_document_chunker.ChunkMerger", autospec=True) as mock_merger:
        mock_merger.return_value.group_atomic_chunks.side_effect = lambda group_atomic_chunks: group_atomic_chunks
        processed_doc = chunker.chunk(doc, document_metadata)

    mock_strategy_handler.chunk.assert_called_once()
    assert len(processed_doc.chunks) == 1


def test_calls_merger_once_per_page(document_metadata, mock_strategy_handler):
    """Verifies that the ChunkMerger is instantiated and called once for each page."""
    strategy_handlers = {"LAYOUT_TEXT": mock_strategy_handler}
    pages = [
        create_mock_page(layouts=[create_mock_layout()], page_num=1),
        create_mock_page(layouts=[create_mock_layout()], page_num=2),
    ]
    doc = create_mock_document(pages=pages)
    chunker = DocumentChunker(strategy_handlers)

    with patch("ingestion_pipeline.chunking.textract_document_chunker.ChunkMerger", autospec=True) as mock_merger:
        chunker.chunk(doc, document_metadata)

        assert mock_merger.return_value.group_atomic_chunks.call_count == 2


def test_creates_pagedocument_with_correct_data(document_metadata, mock_strategy_handler):
    """Verifies that PageDocument objects are created correctly from page data."""
    # Add a layout block that will be processed
    layout = MagicMock()
    layout.layout_type = "LAYOUT_TEXT"
    layout.text = "Some text"
    layout.id = "id-1"

    page = create_mock_page(layouts=[layout], page_num=5, width=800, height=600)
    doc = create_mock_document(pages=[page])

    # Create a real DocumentChunk object
    mock_chunk = DocumentChunk(
        chunk_id="chunk-id-1",
        chunk_index=0,
        chunk_text="Some text",
        chunk_type="LAYOUT_TEXT",
        confidence=99.0,
        page_number=5,
        bounding_box=DocumentBoundingBox(Top=0.1, Left=0.1, Width=0.2, Height=0.2),
        source_doc_id="doc123",
        source_file_name="file.pdf",
        source_file_s3_uri="s3://bucket/25-787878/doc123/page_images/page_5.png",
        case_ref="25-787878",
        received_date=document_metadata.received_date,
        correspondence_type="TC19",
        page_count=5,
    )
    mock_strategy_handler.chunk.return_value = [mock_chunk]

    strategy_handlers = {"LAYOUT_TEXT": mock_strategy_handler}
    chunker = DocumentChunker(strategy_handlers)

    with patch("ingestion_pipeline.chunking.textract_document_chunker.ChunkMerger", autospec=True) as mock_merger:
        mock_merger.return_value.group_atomic_chunks.side_effect = lambda chunks: chunks
        processed_doc = chunker.chunk(doc, document_metadata)

    assert len(processed_doc.chunks) == 1
    page_doc = processed_doc.chunks[0]

    assert page_doc.source_doc_id == "doc123"
    assert page_doc.page_number == 5
    assert page_doc.source_file_s3_uri == "s3://bucket/25-787878/doc123/page_images/page_5.png"


def test_wraps_strategy_exception_in_chunkexception(document_metadata, mock_strategy_handler):
    """Verifies that if a strategy raises an unexpected error,
    it is caught and re-raised as a ChunkException with the original stack trace.
    """
    error_message = "something went very wrong!"
    mock_strategy_handler.chunk.side_effect = Exception(error_message)

    strategy_handlers = {"LAYOUT_TEXT": mock_strategy_handler}
    page = create_mock_page(layouts=[create_mock_layout()])
    doc = create_mock_document(pages=[page])
    chunker = DocumentChunker(strategy_handlers)

    with pytest.raises(ChunkError, match="Error extracting chunks from document: something went very wrong!"):
        chunker.chunk(doc, document_metadata)


def test_init_with_default_config(mock_strategy_handlers):
    """Verifies the chunker initializes with a default config if none is provided."""
    chunker = DocumentChunker(strategy_handlers=mock_strategy_handlers)
    assert isinstance(chunker.config, ChunkingConfig)
    assert chunker.strategy_handlers is mock_strategy_handlers


def test_chunk_raises_error_on_invalid_document(mock_strategy_handlers, document_metadata):
    """Verifies `chunk` raises ValueError for invalid documents."""
    chunker = DocumentChunker(strategy_handlers=mock_strategy_handlers)

    with pytest.raises(ChunkError, match="Document cannot be None and must contain pages."):
        chunker.chunk(None, document_metadata)  # type: ignore[arg-type]

    doc_no_pages = MagicMock()
    doc_no_pages.pages = []
    with pytest.raises(ChunkError, match="Document cannot be None and must contain pages."):
        chunker.chunk(doc_no_pages, document_metadata)


def test_chunk_raises_error_on_missing_raw_response(mock_strategy_handlers, mock_document, document_metadata):
    """Verifies `chunk` raises ChunkException if the raw response is missing."""
    mock_document.response = None
    chunker = DocumentChunker(strategy_handlers=mock_strategy_handlers)

    with pytest.raises(ChunkError, match="missing raw response from Textract"):
        chunker.chunk(mock_document, document_metadata)


# def test_chunk_raises_error_on_missing_strategy_handler(document_metadata):
#     """Verifies `chunk` raises ChunkException if a strategy handler is not found."""
#     from ingestion_pipeline.chunking.textract_document_chunker import ChunkError, DocumentChunker

#     # No handler for "UNIMPLEMENTED" type
#     strategy_handlers = {}  # type: ignore[arg-type]
#     page = MagicMock()
#     page.layouts = [MagicMock(layout_type="UNIMPLEMENTED", text="Some text")]
#     page.page_num = 1
#     page.width = 800
#     page.height = 600

#     doc = MagicMock()
#     doc.pages = [page]
#     doc.response = {"some": "data"}

#     chunker = DocumentChunker(strategy_handlers=strategy_handlers)

#     with pytest.raises(ChunkError, match="has no associated strategy handler"):
#         chunker.chunk(doc, document_metadata)


def test_chunk_raises_error_on_strategy_handler_not_implemented(document_metadata):
    """Verifies `chunk` wraps NotImplementedError from a strategy handler."""
    from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
    from ingestion_pipeline.chunking.strategies.base import ChunkingStrategyHandler
    from ingestion_pipeline.chunking.textract_document_chunker import ChunkError, DocumentChunker

    class DummyHandler(ChunkingStrategyHandler):
        def chunk(self, *args, **kwargs):
            raise NotImplementedError("Not implemented")

    strategy_handlers = {"UNIMPLEMENTED": DummyHandler(ChunkingConfig())}
    page = MagicMock()
    page.layouts = [MagicMock(layout_type="UNIMPLEMENTED", text="Some text")]
    page.page_num = 1
    page.width = 800
    page.height = 600

    doc = MagicMock()
    doc.pages = [page]
    doc.response = {"some": "data"}

    chunker = DocumentChunker(strategy_handlers=strategy_handlers)

    with pytest.raises(ChunkError, match="Not implemented"):
        chunker.chunk(doc, document_metadata)


def test_should_process_block(mock_strategy_handlers):
    """Tests the logic for deciding whether to process a layout block."""
    chunker = DocumentChunker(strategy_handlers=mock_strategy_handlers)

    # Should process: type is in handlers and text is present
    block_good = MagicMock(layout_type="TEXT", text="Valid text")
    assert chunker._should_process_block(block_good, mock_strategy_handlers) is True

    # Should not process: type not in handlers
    block_bad_type = MagicMock(layout_type="FIGURE", text="Valid text")
    assert chunker._should_process_block(block_bad_type, mock_strategy_handlers) is False

    # Should not process: text is None
    block_no_text = MagicMock(layout_type="TEXT", text=None)
    assert chunker._should_process_block(block_no_text, mock_strategy_handlers) is False

    # Should not process: text is only whitespace
    block_whitespace = MagicMock(layout_type="TEXT", text="   \n\t ")
    assert chunker._should_process_block(block_whitespace, mock_strategy_handlers) is False


def test_process_page_handles_empty_layouts(document_metadata):
    """Verifies _process_page runs without error if a page has no layouts."""
    chunker = DocumentChunker(strategy_handlers={})
    page = MagicMock(spec=Page, layouts=[])
    raw_response = {"some": "data"}

    # Should return an empty list and not raise an error
    result = chunker._process_page(page, document_metadata, 0, raw_response)
    assert result == []


@patch("ingestion_pipeline.chunking.textract_document_chunker.logger")
def test_chunk_general_exception_handling(mock_logger, mock_strategy_handlers, document_metadata):
    """Verifies that a general exception during chunking is caught and re-raised as ChunkError."""
    chunker = DocumentChunker(strategy_handlers=mock_strategy_handlers)
    error_message = "Something went wrong"
    # Simulate an error during validation
    with patch.object(chunker, "_validate_textract_document", side_effect=Exception(error_message)):
        with pytest.raises(ChunkError, match=error_message):
            chunker.chunk(MagicMock(), document_metadata)
        mock_logger.error.assert_called_once_with(f"Error extracting chunks from document: {error_message}")
