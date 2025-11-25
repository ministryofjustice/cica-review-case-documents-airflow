"""Unit Test: Tests for the LayoutTextChunkingStrategy class."""

from unittest.mock import MagicMock, call

import pytest

import ingestion_pipeline.chunking.strategies.layout_text as layout_text_module
from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.strategies.layout_text import LayoutTextChunkingStrategy


@pytest.fixture
def default_config():
    """Provides a default ChunkingConfig for tests."""
    return ChunkingConfig(maximum_chunk_size=600)


@pytest.fixture
def mock_dependencies(mocker):
    """Mocks the external dependencies of the LayoutTextChunkingStrategy class.

    Args:
        mocker (pytest_mock.MockerFixture): Fixture for mocking objects and functions.

    Returns:
        Tuple[MagicMock, MagicMock]: Mocks for DocumentChunk and combine_bounding_boxes.
    """
    mock_opensearch_chunk = mocker.patch.object(layout_text_module, "DocumentChunk", autospec=True)
    mock_combine_bboxes = mocker.patch.object(layout_text_module, "combine_bounding_boxes", autospec=True)

    return mock_opensearch_chunk, mock_combine_bboxes


def create_fake_bbox(x_min=0, y_min=0, x_max=0.1, y_max=0.1, width=0.1, height=0.1):
    """Creates a mock BoundingBox object."""
    bbox = MagicMock()
    bbox.x_min = x_min
    bbox.y_min = y_min
    bbox.x_max = x_max
    bbox.y_max = y_max
    bbox.width = width
    bbox.height = height
    return bbox


def create_fake_line(text: str):
    """Creates a mock line block (a child of the layout_block)."""
    line = MagicMock()
    line.text = text
    line.bbox = create_fake_bbox()
    return line


def test_chunk_creates_a_single_chunk_for_short_text(mock_dependencies, default_config):
    """Tests that text smaller than the maximum size results in a single chunk."""
    mock_opensearch_chunk, _ = mock_dependencies

    handler = LayoutTextChunkingStrategy(default_config)
    fake_lines = [
        create_fake_line("This is the first line."),
        create_fake_line("This is the second line."),
    ]
    fake_layout_block = MagicMock()
    fake_layout_block.children = fake_lines
    fake_metadata = MagicMock()
    page_number = 1
    chunk_index_start = 0
    result_chunks = handler.chunk(fake_layout_block, page_number, fake_metadata, chunk_index_start)
    assert len(result_chunks) == 1

    mock_opensearch_chunk.from_textractor_layout.assert_called_once()

    call_args = mock_opensearch_chunk.from_textractor_layout.call_args
    assert call_args.kwargs["chunk_text"] == "This is the first line. This is the second line."
    assert call_args.kwargs["page_number"] == 1
    assert call_args.kwargs["chunk_index"] == 0


def test_chunk_splits_text_into_multiple_chunks(mock_dependencies, default_config):
    """Tests that text larger than the maximum size is split into multiple chunks."""
    mock_opensearch_chunk, mock_combine_bboxes = mock_dependencies
    chunking_config = ChunkingConfig(maximum_chunk_size=30)
    handler = LayoutTextChunkingStrategy(chunking_config)

    fake_lines = [
        create_fake_line("This is the first chunk."),  # len = 25
        create_fake_line("This line starts a new one."),  # len = 27. (25 + 1 + 27 > 30)
        create_fake_line("And so does this."),  # len = 16
    ]
    fake_layout_block = MagicMock()
    fake_layout_block.children = fake_lines
    fake_metadata = MagicMock()
    page_number = 3
    chunk_index_start = 5

    result_chunks = handler.chunk(fake_layout_block, page_number, fake_metadata, chunk_index_start)

    assert len(result_chunks) == 3  # Should be split into 3 chunks

    expected_calls = [
        call(
            block=fake_layout_block,
            page_number=3,
            metadata=fake_metadata,
            chunk_index=5,
            chunk_text="This is the first chunk.",
            combined_bbox=mock_combine_bboxes.return_value,
        ),
        call(
            block=fake_layout_block,
            page_number=3,
            metadata=fake_metadata,
            chunk_index=6,
            chunk_text="This line starts a new one.",
            combined_bbox=mock_combine_bboxes.return_value,
        ),
        call(
            block=fake_layout_block,
            page_number=3,
            metadata=fake_metadata,
            chunk_index=7,
            chunk_text="And so does this.",
            combined_bbox=mock_combine_bboxes.return_value,
        ),
    ]
    mock_opensearch_chunk.from_textractor_layout.assert_has_calls(expected_calls)


def test_simple_strategy_handles_empty_block(default_config):
    """Verifies that the strategy returns an empty list for an empty block."""
    strategy = LayoutTextChunkingStrategy(default_config)

    fake_lines = []
    fake_layout_block = MagicMock()
    fake_layout_block.children = fake_lines
    fake_metadata = MagicMock()
    page_number = 3
    chunk_index_start = 5

    result_empty = strategy.chunk(fake_layout_block, page_number, fake_metadata, chunk_index_start)
    result_whitespace = strategy.chunk(fake_layout_block, page_number, fake_metadata, chunk_index_start)

    assert result_empty == []

    fake_whitespace = [create_fake_line("")]

    fake_whitespace = []
    fake_layout_block = MagicMock()
    fake_layout_block.children = fake_whitespace
    fake_metadata = MagicMock()
    page_number = 3
    chunk_index_start = 5
    assert result_whitespace == []


@pytest.mark.parametrize(
    "current_text, new_line, expected",
    [
        ([], "This line is too long", True),
        ([], "Short line", False),
        (["hello", "world"], "and you", False),
        (["hello", "world"], "and you too", True),
    ],
)
def test_would_exceed_size_limit(current_text, new_line, expected):
    """Tests the helper method directly with various inputs."""
    chunking_config = ChunkingConfig(maximum_chunk_size=20)
    handler = LayoutTextChunkingStrategy(chunking_config)
    assert handler._would_exceed_size_limit(current_text, new_line) is expected


def test_chunk_handles_single_line_exceeding_max_size(mock_dependencies, default_config):
    """Tests that a single line longer than the maximum chunk size becomes its own chunk."""
    mock_opensearch_chunk, mock_combine_bboxes = mock_dependencies
    chunking_config = ChunkingConfig(maximum_chunk_size=20)
    handler = LayoutTextChunkingStrategy(chunking_config)

    long_line = "This single line is far too long for the chunk size."  # len > 20
    short_line = "This is a new line."

    fake_lines = [
        create_fake_line(long_line),
        create_fake_line(short_line),
    ]
    fake_layout_block = MagicMock()
    fake_layout_block.children = fake_lines
    fake_metadata = MagicMock()
    page_number = 1
    chunk_index_start = 0

    result_chunks = handler.chunk(fake_layout_block, page_number, fake_metadata, chunk_index_start)

    # We expect two chunks: one for the oversized line, and one for the next line.
    assert len(result_chunks) == 2

    expected_calls = [
        call(
            block=fake_layout_block,
            page_number=1,
            metadata=fake_metadata,
            chunk_index=0,
            chunk_text=long_line,
            combined_bbox=mock_combine_bboxes.return_value,
        ),
        call(
            block=fake_layout_block,
            page_number=1,
            metadata=fake_metadata,
            chunk_index=1,
            chunk_text=short_line,
            combined_bbox=mock_combine_bboxes.return_value,
        ),
    ]
    mock_opensearch_chunk.from_textractor_layout.assert_has_calls(expected_calls)
