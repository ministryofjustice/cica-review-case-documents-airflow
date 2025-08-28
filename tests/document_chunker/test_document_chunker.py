from datetime import date
from unittest.mock import MagicMock

import pytest
from textractor.entities.document import Document

from src.data_models.chunk_models import DocumentMetadata
from src.document_chunker.document_chunker import DocumentChunker


@pytest.fixture
def document_metadata_factory():
    """
    Returns a factory function to create DocumentMetadata objects.
    This allows tests to override default values as needed.
    """

    def _factory(**overrides):
        """
        Inner factory function with default metadata values.
        Accepts keyword arguments to override any default.
        """
        case_ref = "25-787878"
        received_date = date.fromisoformat("2025-08-21")
        correspondence_type = "TC19"

        defaults = {
            "ingested_doc_id": "unique_ingested_doc_UUID",
            "source_file_name": "test_ingested_document.pdf",
            "page_count": 1,
            "case_ref": case_ref,
            "received_date": received_date,
            "correspondence_type": correspondence_type,
        }
        # Merge the overrides into the defaults
        final_args = {**defaults, **overrides}
        return DocumentMetadata(**final_args)

    return _factory


@pytest.fixture
def mock_chunking_handler():
    """Provides a mock chunking handler that we can inspect."""
    handler = MagicMock()
    # Configure the mock to return a single chunk by default
    handler.chunk.return_value = [MagicMock()]
    return handler


@pytest.fixture
def chunker(monkeypatch, mock_chunking_handler):
    """Provides a DocumentChunker instance with mocked-out strategy handlers."""
    # Use monkeypatch to replace the factory methods with ones that return our mock
    monkeypatch.setattr(
        DocumentChunker, "_create_strategy_handlers", lambda self: {"LAYOUT_TEXT": mock_chunking_handler}
    )
    monkeypatch.setattr(DocumentChunker, "_create_default_handler", lambda self: mock_chunking_handler)
    return DocumentChunker()


def create_mock_doc(page_definitions):
    """Helper to create a mock Document object from a simpler definition."""
    mock_doc = MagicMock(spec=Document)
    pages = []
    for i, layout_blocks_def in enumerate(page_definitions, 1):
        page = MagicMock()
        page.page_num = i
        layouts = []
        for block_def in layout_blocks_def:
            block = MagicMock()
            block.layout_type = block_def.get("type")
            block.text = block_def.get("text")
            layouts.append(block)
        page.layouts = layouts
        pages.append(page)
    mock_doc.pages = pages
    return mock_doc


def test_selects_correct_handler_for_mapped_type(chunker, document_metadata_factory, mock_chunking_handler):
    """
    Unit Test: Verifies that the chunker calls the specific handler
    mapped to LAYOUT_TEXT.
    """
    mock_doc = create_mock_doc([[{"type": "LAYOUT_TEXT", "text": "Some content."}]])
    metadata = document_metadata_factory()

    chunker.chunk(mock_doc, metadata)

    mock_chunking_handler.chunk.assert_called_once()
    args, kwargs = mock_chunking_handler.chunk.call_args
    assert args[0] == mock_doc.pages[0].layouts[0]  # The layout block
    assert args[1] == 1  # The page number
    assert args[2] == metadata
    assert args[3] == 0  # The starting chunk index


def test_uses_default_handler_for_unmapped_type(chunker, document_metadata_factory, monkeypatch):
    """
    Unit Test: Verifies that the chunker falls back to the default handler
    for an unmapped layout type.
    """
    mock_text_handler = MagicMock()
    mock_default_handler = MagicMock()
    mock_default_handler.chunk.return_value = [MagicMock()]

    monkeypatch.setattr(DocumentChunker, "_create_strategy_handlers", lambda self: {"LAYOUT_TEXT": mock_text_handler})
    monkeypatch.setattr(DocumentChunker, "_create_default_handler", lambda self: mock_default_handler)

    specific_chunker = DocumentChunker()

    mock_doc = create_mock_doc([[{"type": "LAYOUT_TABLE", "text": "Table content."}]])

    specific_chunker.chunk(mock_doc, metadata=document_metadata_factory(), desired_layout_types={"LAYOUT_TABLE"})

    mock_text_handler.chunk.assert_not_called()
    mock_default_handler.chunk.assert_called_once()


def test_filters_blocks_by_type_and_content(chunker, document_metadata_factory, mock_chunking_handler):
    """
    Unit Test: Verifies the logic of _should_process_block is applied correctly.
    """
    mock_doc = create_mock_doc(
        [
            [
                {"type": "LAYOUT_TEXT", "text": "Valid content."},  # Should be processed
                {"type": "LAYOUT_TITLE", "text": "A title."},  # Should be processed
                {"type": "LAYOUT_TEXT", "text": "    \n\t "},  # Should be ignored (whitespace only)
                {"type": "LAYOUT_TEXT", "text": ""},  # Should be ignored (empty text)
                {"type": "LAYOUT_TEXT", "text": None},  # Should be ignored (None text)
            ]
        ]
    )
    metadata = document_metadata_factory()

    # Passing in both "LAYOUT_TEXT" AND "LAYOUT_TITLE"
    chunker.chunk(mock_doc, metadata, desired_layout_types={"LAYOUT_TEXT", "LAYOUT_TITLE"})

    # Assert that the handler was called exactly twice
    assert mock_chunking_handler.chunk.call_count == 2

    calls = mock_chunking_handler.chunk.call_args_list

    first_call_args = calls[0].args
    assert first_call_args[0].text == "Valid content."
    assert first_call_args[3] == 0

    second_call_args = calls[1].args
    assert second_call_args[0].text == "A title."
    assert second_call_args[3] == 1


def test_aggregates_chunks_and_maintains_index(chunker, document_metadata_factory, mock_chunking_handler):
    """
    Unit Test: Verifies that chunks from multiple pages/blocks are aggregated
    and the chunk_index is passed correctly to the handler.
    """
    mock_chunking_handler.chunk.side_effect = [
        [MagicMock(), MagicMock()],  # First call returns 2 chunks
        [MagicMock()],  # Second call returns 1 chunk
        [MagicMock(), MagicMock(), MagicMock()],  # Third call returns 3 chunks
    ]

    mock_doc = create_mock_doc(
        [
            [{"type": "LAYOUT_TEXT", "text": "Block 1"}],  # Page 1
            [{"type": "LAYOUT_TEXT", "text": "Block 2"}, {"type": "LAYOUT_TEXT", "text": "Block 3"}],  # Page 2
        ]
    )
    metadata = document_metadata_factory()

    result = chunker.chunk(mock_doc, metadata)

    # Check total chunks
    assert len(result) == 2 + 1 + 3

    # Check that the handler was called with the correct, incrementing chunk_index
    assert mock_chunking_handler.chunk.call_count == 3
    calls = mock_chunking_handler.chunk.call_args_list
    # Call 1 (Block 1): started at index 0
    assert calls[0].args[3] == 0
    # Call 2 (Block 2): started at index 2 (because call 1 returned 2 chunks)
    assert calls[1].args[3] == 2
    # Call 3 (Block 3): started at index 3 (because call 2 returned 1 chunk)
    assert calls[2].args[3] == 3


def test_empty_document_raises_value_error(chunker, document_metadata_factory):
    """Unit Test: Verifies input validation for empty documents."""
    empty_doc = MagicMock(spec=Document)
    empty_doc.pages = []

    with pytest.raises(ValueError, match="Document cannot be None and must contain pages."):
        chunker.chunk(empty_doc, document_metadata_factory())
