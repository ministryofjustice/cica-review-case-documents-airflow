from unittest.mock import MagicMock, patch

import pytest

from ingestion_pipeline.chunking.exceptions import ChunkException
from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.textract import TextractDocumentChunker


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
def mock_metadata():
    """Provides a mock DocumentMetadata object for tests."""
    metadata = MagicMock(spec=DocumentMetadata)
    metadata.ingested_doc_id = "doc-123"
    metadata.case_ref = "case-abc"
    return metadata


@pytest.fixture
def mock_strategy_handler():
    """Provides a generic mock strategy handler."""
    handler = MagicMock()
    # By default, return one mock chunk per call
    handler.chunk.return_value = [MagicMock(spec=DocumentChunk)]
    return handler


def test_selects_correct_strategy_and_increments_index(mock_metadata):
    """
    Verifies the chunker calls the correct strategy for each block type
    and correctly increments the chunk index between calls.
    """
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

    chunker = TextractDocumentChunker(strategy_handlers)

    with patch("ingestion_pipeline.chunking.textract.ChunkMerger", autospec=True) as mock_merger:
        mock_merger.return_value.chunk.side_effect = lambda chunks: chunks
        processed_doc = chunker.chunk(doc, mock_metadata)

    mock_text_strategy.chunk.assert_called_once()
    # assert chunk_index_start == 0
    assert mock_text_strategy.chunk.call_args.args[3] == 0
    # assert chunk_index_start is now 2
    assert mock_table_strategy.chunk.call_args.args[3] == 2
    assert len(processed_doc.chunks) == 3


def test_skips_blocks_without_strategy_or_text(mock_metadata, mock_strategy_handler):
    """
    Verifies that blocks are skipped if they have no associated strategy,
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

    chunker = TextractDocumentChunker(strategy_handlers)

    with patch("ingestion_pipeline.chunking.textract.ChunkMerger", autospec=True) as mock_merger:
        mock_merger.return_value.chunk.side_effect = lambda chunks: chunks
        processed_doc = chunker.chunk(doc, mock_metadata)

    mock_strategy_handler.chunk.assert_called_once()
    assert len(processed_doc.chunks) == 1


def test_calls_merger_once_per_page(mock_metadata, mock_strategy_handler):
    """
    Verifies that the ChunkMerger is instantiated and called once for each page.
    """
    strategy_handlers = {"LAYOUT_TEXT": mock_strategy_handler}
    pages = [
        create_mock_page(layouts=[create_mock_layout()], page_num=1),
        create_mock_page(layouts=[create_mock_layout()], page_num=2),
    ]
    doc = create_mock_document(pages=pages)
    chunker = TextractDocumentChunker(strategy_handlers)

    with patch("ingestion_pipeline.chunking.textract.ChunkMerger", autospec=True) as mock_merger:
        chunker.chunk(doc, mock_metadata)

        assert mock_merger.return_value.chunk.call_count == 2


def test_creates_pagedocument_with_correct_data(mock_metadata, mock_strategy_handler):
    """
    Verifies that PageDocument objects are created correctly from page data.
    """
    strategy_handlers = {"LAYOUT_TEXT": mock_strategy_handler}
    page = create_mock_page(layouts=[], page_num=5, width=800, height=600)
    doc = create_mock_document(pages=[page])
    chunker = TextractDocumentChunker(strategy_handlers)

    processed_doc = chunker.chunk(doc, mock_metadata)

    assert len(processed_doc.pages) == 1
    page_doc = processed_doc.pages[0]

    assert page_doc.document_id == "doc-123"
    assert page_doc.page_num == 5
    assert page_doc.page_width == 800
    assert page_doc.page_height == 600
    assert page_doc.page_image_s3_uri == "s3://bucket/case-abc/doc-123/page_images/page_5.png"


def test_wraps_strategy_exception_in_chunkexception(mock_metadata, mock_strategy_handler):
    """
    Verifies that if a strategy raises an unexpected error, it is caught
    and re-raised as a ChunkException.
    """

    error_message = "Something went very wrong!"
    mock_strategy_handler.chunk.side_effect = Exception(error_message)

    strategy_handlers = {"LAYOUT_TEXT": mock_strategy_handler}
    page = create_mock_page(layouts=[create_mock_layout()])
    doc = create_mock_document(pages=[page])
    chunker = TextractDocumentChunker(strategy_handlers)

    with pytest.raises(ChunkException, match=error_message):
        chunker.chunk(doc, mock_metadata)
