"""Unit tests for the LayoutListChunkingStrategy class."""

import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.chunking.strategies.list.list_chunker import LayoutListChunkingStrategy


# Helper function to create mock layout blocks for cleaner tests
def create_mock_layout_block(layout_type: str, text: str, block_id: str = "id-123", bbox=None):
    """Creates a MagicMock object that simulates a Textractor LayoutBlock."""
    block = MagicMock()
    block.layout_type = layout_type
    block.text = text
    block.id = block_id
    block.bbox = bbox or MagicMock(x=0.1, y=0.1, width=0.5, height=0.05)
    return block


# Pytest fixtures to provide reusable setup for tests
@pytest.fixture
def chunking_config() -> ChunkingConfig:
    """Provides a default ChunkingConfig instance."""
    return ChunkingConfig()


@pytest.fixture
def document_metadata() -> DocumentMetadata:
    """Provides a sample DocumentMetadata instance."""
    import datetime

    return DocumentMetadata(
        source_doc_id="doc-abc-123",
        source_file_name="key.pdf",
        page_count=1,
        case_ref="case-xyz-789",
        received_date=datetime.date(2024, 1, 1),
        correspondence_type="email",
    )


@pytest.fixture
def list_chunking_strategy(chunking_config: ChunkingConfig) -> LayoutListChunkingStrategy:
    """Provides an instance of the class under test."""
    return LayoutListChunkingStrategy(config=chunking_config)


def test_chunk_with_valid_list_items(list_chunking_strategy, document_metadata):
    """Tests the happy path: a LAYOUT_LIST with multiple valid LAYOUT_TEXT children."""
    list_item_1 = create_mock_layout_block("LAYOUT_TEXT", "First list item.")
    list_item_2 = create_mock_layout_block("LAYOUT_TEXT", "Second list item.")
    layout_list_block = create_mock_layout_block("LAYOUT_LIST", "Unused parent text")
    layout_list_block.children = [list_item_1, list_item_2]

    with patch("ingestion_pipeline.chunking.schemas.DocumentChunk.from_textractor_layout") as mock_from_layout:
        mock_from_layout.side_effect = lambda **kwargs: MagicMock(text=kwargs["chunk_text"])

        chunks = list_chunking_strategy.chunk(
            layout_block=layout_list_block,
            page_number=1,
            metadata=document_metadata,
            chunk_index_start=0,
        )

    assert len(chunks) == 2, "Should create one chunk for each valid list item"
    assert chunks[0].text == "First list item."
    assert chunks[1].text == "Second list item."

    first_call_args = mock_from_layout.call_args_list[0].kwargs
    assert first_call_args["chunk_text"] == "First list item."
    assert first_call_args["chunk_index"] == 0
    assert first_call_args["page_number"] == 1

    second_call_args = mock_from_layout.call_args_list[1].kwargs
    assert second_call_args["chunk_text"] == "Second list item."
    assert second_call_args["chunk_index"] == 1


def test_chunk_with_empty_children_list(list_chunking_strategy, document_metadata):
    """Tests that an empty list of chunks is returned if the LAYOUT_LIST has no children."""
    layout_list_block = create_mock_layout_block("LAYOUT_LIST", "Parent text")
    layout_list_block.children = []

    chunks = list_chunking_strategy.chunk(
        layout_block=layout_list_block,
        page_number=1,
        metadata=document_metadata,
        chunk_index_start=0,
    )

    assert len(chunks) == 0, "Should return an empty list for a block with no children"


def test_chunk_skips_children_with_empty_text(list_chunking_strategy, document_metadata):
    """Tests that children with empty or whitespace-only text are correctly skipped."""
    list_item_1 = create_mock_layout_block("LAYOUT_TEXT", "This is a valid item.")
    list_item_2 = create_mock_layout_block("LAYOUT_TEXT", "")  # Empty string
    list_item_3 = create_mock_layout_block("LAYOUT_TEXT", "   \n\t ")  # Whitespace only
    list_item_4 = create_mock_layout_block("LAYOUT_TEXT", "Another valid item.")

    layout_list_block = create_mock_layout_block("LAYOUT_LIST", "Parent text")
    layout_list_block.children = [list_item_1, list_item_2, list_item_3, list_item_4]

    chunks = list_chunking_strategy.chunk(
        layout_block=layout_list_block,
        page_number=3,
        metadata=document_metadata,
        chunk_index_start=10,
    )

    assert len(chunks) == 2, "Should only create chunks for items with actual text content"
    assert chunks[0].chunk_text == "This is a valid item."
    assert chunks[1].chunk_text == "Another valid item."

    assert chunks[0].chunk_index == 10
    assert chunks[1].chunk_index == 11


def test_chunk_skips_non_layout_text_children_and_logs_warning(list_chunking_strategy, document_metadata, caplog):
    """Tests that non-LAYOUT_TEXT children are skipped and a warning is logged.

    `caplog` is a pytest fixture to capture logging output.
    """
    list_item_valid = create_mock_layout_block("LAYOUT_TEXT", "Valid text.")
    # Create a child of an unexpected type (e.g., a table inside a list)
    list_item_invalid = create_mock_layout_block("LAYOUT_TABLE", "Unexpected table text", block_id="id-999")

    layout_list_block = create_mock_layout_block("LAYOUT_LIST", "Parent text", block_id="list-id-456")
    layout_list_block.children = [list_item_valid, list_item_invalid]

    with caplog.at_level(logging.WARNING):
        chunks = list_chunking_strategy.chunk(
            layout_block=layout_list_block,
            page_number=1,
            metadata=document_metadata,
            chunk_index_start=0,
        )

    assert len(chunks) == 1, "Should only create one chunk for the valid LAYOUT_TEXT child"
    assert chunks[0].chunk_text == "Valid text."

    assert "Skipping unexpected list child block" in caplog.text
    assert "MagicMock in LAYOUT_KEY_VALUE block list-id-456" in caplog.text
    assert "Text: Unexpected table text" in caplog.text
