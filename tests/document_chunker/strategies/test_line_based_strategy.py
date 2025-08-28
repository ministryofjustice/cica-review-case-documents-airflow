from unittest.mock import MagicMock, call

import pytest

from src.document_chunker.strategies.line_based import LineBasedChunkingHandler


@pytest.fixture
def mock_dependencies(mocker):
    """
    This fixture mocks the external dependencies of the Handler class.
    'mocker' is provided by the pytest-mock plugin.
    """

    mock_opensearch_chunk = mocker.patch("src.document_chunker.strategies.line_based.OpenSearchChunk")
    mock_combine_bboxes = mocker.patch("src.document_chunker.strategies.line_based.combine_bounding_boxes")

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


def test_chunk_creates_a_single_chunk_for_short_text(mock_dependencies):
    """
    Tests that text smaller than the maximum size results in a single chunk.
    """

    mock_opensearch_chunk, _ = mock_dependencies

    handler = LineBasedChunkingHandler(maximum_chunk_size=500)
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

    mock_opensearch_chunk.from_textractor_layout_and_text.assert_called_once()

    call_args = mock_opensearch_chunk.from_textractor_layout_and_text.call_args
    assert call_args.kwargs["chunk_text"] == "This is the first line. This is the second line."
    assert call_args.kwargs["page_num"] == 1
    assert call_args.kwargs["chunk_index"] == 0


def test_chunk_splits_text_into_multiple_chunks(mock_dependencies):
    """
    Tests that text larger than the maximum size is split into multiple chunks.
    """
    mock_opensearch_chunk, mock_combine_bboxes = mock_dependencies

    handler = LineBasedChunkingHandler(maximum_chunk_size=30)

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
            page_num=3,
            metadata=fake_metadata,
            chunk_index=5,
            chunk_text="This is the first chunk.",
            combined_bbox=mock_combine_bboxes.return_value,
        ),
        call(
            block=fake_layout_block,
            page_num=3,
            metadata=fake_metadata,
            chunk_index=6,
            chunk_text="This line starts a new one.",
            combined_bbox=mock_combine_bboxes.return_value,
        ),
        call(
            block=fake_layout_block,
            page_num=3,
            metadata=fake_metadata,
            chunk_index=7,
            chunk_text="And so does this.",
            combined_bbox=mock_combine_bboxes.return_value,
        ),
    ]
    mock_opensearch_chunk.from_textractor_layout_and_text.assert_has_calls(expected_calls)


def test_simple_strategy_handles_empty_block():
    """
    Verifies that the strategy returns an empty list for an empty block.
    """

    strategy = LineBasedChunkingHandler(maximum_chunk_size=30)

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
        # Corrected Logic: 5 + 1 + 5 + 1 + 7 = 19, which is NOT > 20. So this should be False.
        (["hello", "world"], "and you", False),
        # 5 + 1 + 5 + 1 + 11 = 23, which IS > 20. So this should be True.
        (["hello", "world"], "and you too", True),
    ],
)
def test_would_exceed_size_limit(current_text, new_line, expected):
    """Tests the helper method directly with various inputs."""

    handler = LineBasedChunkingHandler(maximum_chunk_size=20)
    assert handler._would_exceed_size_limit(current_text, new_line) is expected
