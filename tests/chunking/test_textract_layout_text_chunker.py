"""Unit tests for the LayoutTextChunkingStrategy in the ingestion pipeline."""

from datetime import date
from typing import Sequence
from unittest.mock import MagicMock, call

import pytest
from textractor.entities.bbox import BoundingBox

import ingestion_pipeline.chunking.strategies.layout_text as layout_text_module
from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.strategies.layout_text import LayoutTextChunkingStrategy
from ingestion_pipeline.chunking.utils.bbox_utils import combine_bounding_boxes


@pytest.fixture
def document_metadata_factory():
    """Returns a factory function to create DocumentMetadata objects.

    Returns:
        DocumentMetadata: The created DocumentMetadata object.
    """

    def _factory(**overrides):
        """Creates a DocumentMetadata object with default or overridden values.

        Returns:
            DocumentMetadata: The created DocumentMetadata object.
        """
        defaults = {
            "source_doc_id": "unique_ingested_doc_UUID",
            "source_file_name": "test_ingested_document.pdf",
            "page_count": 1,
            "case_ref": "25-787878",
            "received_date": date.fromisoformat("2025-08-21"),
            "correspondence_type": "TC19",
        }
        final_args = {**defaults, **overrides}
        return DocumentMetadata(**final_args)

    return _factory


@pytest.fixture
def mock_config():
    """Provides a mock ChunkingConfig for the strategy."""
    config = MagicMock(spec=ChunkingConfig)
    config.maximum_chunk_size = 50
    return config


@pytest.fixture
def strategy(mock_config):
    """Provides an instance of the LayoutTextChunkingStrategy."""
    return LayoutTextChunkingStrategy(config=mock_config)


def create_mock_bbox(x: float, y: float, width: float, height: float) -> BoundingBox:
    """Helper to create a configured BoundingBox mock."""
    bbox = MagicMock(spec=BoundingBox)
    bbox.x = x
    bbox.y = y
    bbox.width = width
    bbox.height = height
    return bbox


def create_mock_layout_block(lines_with_bboxes: Sequence[tuple[str, BoundingBox]]):
    """Creates a mock layout block with child 'line' blocks.

    Args:
        lines_with_bboxes (Sequence[tuple[str, BoundingBox]]): A sequence of tuples, each containing
        the text and bounding box for a line.

    Returns:
        MagicMock: A mock layout block with the specified line children.
    """
    mock_block = MagicMock()
    mock_block.id = "block-123"
    children = []
    for text, bbox in lines_with_bboxes:
        child = MagicMock()
        child.text = text
        child.bbox = bbox
        children.append(child)
    mock_block.children = children
    return mock_block


def test_single_chunk_created_for_two_lines_within_size_limit(strategy, document_metadata_factory):
    metadata = document_metadata_factory()
    lines = [
        ("First line.", create_mock_bbox(0.1, 0.1, 0.2, 0.05)),
        ("Second line.", create_mock_bbox(0.1, 0.2, 0.2, 0.05)),
    ]
    layout_block = create_mock_layout_block(lines)

    with pytest.MonkeyPatch.context() as m:
        mock_creator = MagicMock()
        m.setattr(layout_text_module.DocumentChunk, DocumentChunk.from_textractor_layout.__name__, mock_creator)

        chunks = strategy.chunk(layout_block, page_number=1, metadata=metadata, chunk_index_start=0)

        assert len(chunks) == 1
        mock_creator.assert_called_once()
        call_args = mock_creator.call_args
        assert call_args.kwargs["chunk_text"] == "First line. Second line."
        assert call_args.kwargs["chunk_index"] == 0


def test_multiple_chunks_created_on_size_limit(strategy, document_metadata_factory):
    metadata = document_metadata_factory()
    lines = [
        ("This is the first chunk, it is quite long.", create_mock_bbox(0.1, 0.1, 0.8, 0.05)),
        ("This line will cause a split.", create_mock_bbox(0.1, 0.2, 0.7, 0.05)),
        ("This is the start of the final chunk.", create_mock_bbox(0.1, 0.3, 0.8, 0.05)),
    ]
    layout_block = create_mock_layout_block(lines)

    with pytest.MonkeyPatch.context() as m:
        mock_creator = MagicMock()
        m.setattr(layout_text_module.DocumentChunk, DocumentChunk.from_textractor_layout.__name__, mock_creator)

        chunks = strategy.chunk(layout_block, page_number=2, metadata=metadata, chunk_index_start=5)

        assert len(chunks) == 3
        calls = mock_creator.call_args_list
        assert calls[0].kwargs["chunk_text"] == "This is the first chunk, it is quite long."
        assert calls[0].kwargs["chunk_index"] == 5
        assert calls[1].kwargs["chunk_text"] == "This line will cause a split."
        assert calls[1].kwargs["chunk_index"] == 6
        assert calls[2].kwargs["chunk_text"] == "This is the start of the final chunk."
        assert calls[2].kwargs["chunk_index"] == 7


def test_single_line_exceeding_limit_only_creates_one_chunk(strategy, document_metadata_factory):
    metadata = document_metadata_factory()
    long_line = "This single line is deliberately much longer than the configured maximum chunk size of fifty."
    assert len(long_line) > strategy.maximum_chunk_size

    lines = [(long_line, create_mock_bbox(0.1, 0.1, 0.9, 0.05))]
    layout_block = create_mock_layout_block(lines)

    with pytest.MonkeyPatch.context() as m:
        mock_creator = MagicMock()
        m.setattr(layout_text_module.DocumentChunk, DocumentChunk.from_textractor_layout.__name__, mock_creator)

        chunks = strategy.chunk(layout_block, page_number=1, metadata=metadata, chunk_index_start=0)

        assert len(chunks) == 1
        call_args = mock_creator.call_args
        assert call_args.kwargs["chunk_text"] == long_line


def test_empty_layout_block_returns_no_chunks(strategy, document_metadata_factory):
    layout_block = create_mock_layout_block([])
    chunks = strategy.chunk(layout_block, page_number=1, metadata=document_metadata_factory(), chunk_index_start=0)
    assert chunks == []


def test_bounding_boxes_are_combined_per_chunk(strategy, document_metadata_factory, monkeypatch):
    metadata = document_metadata_factory()
    bbox1 = create_mock_bbox(0.1, 0.1, 0.3, 0.05)
    bbox2 = create_mock_bbox(0.1, 0.2, 0.4, 0.05)
    bbox3 = create_mock_bbox(0.1, 0.3, 0.5, 0.05)
    lines = [
        ("First part of chunk one.", bbox1),
        ("Second part of chunk one.", bbox2),
        ("This starts the second chunk.", bbox3),
    ]
    layout_block = create_mock_layout_block(lines)

    mock_combiner = MagicMock()

    monkeypatch.setattr(layout_text_module, combine_bounding_boxes.__name__, mock_combiner)
    monkeypatch.setattr(layout_text_module.DocumentChunk, DocumentChunk.from_textractor_layout.__name__, MagicMock())

    strategy.chunk(layout_block, page_number=1, metadata=metadata, chunk_index_start=0)

    assert mock_combiner.call_count == 2
    mock_combiner.assert_has_calls([call([bbox1, bbox2]), call([bbox3])])
