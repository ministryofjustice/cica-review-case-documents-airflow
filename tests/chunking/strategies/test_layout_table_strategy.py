from unittest.mock import MagicMock

import pytest
from textractor.entities.layout import Layout
from textractor.entities.line import Line
from textractor.entities.table import Table
from textractor.entities.table_cell import TableCell

from src.chunking.config import ChunkingConfig
from src.chunking.exceptions import ChunkException
from src.chunking.strategies.table import LayoutTableChunkingStrategy


@pytest.fixture
def mock_chunkers(mocker):
    """Mocks the sub-chunker classes to test dispatch logic."""
    # We patch the classes where they are looked up (in the layout_table_strategy module)
    mock_cell_chunker_cls = mocker.patch("src.chunking.strategies.table.layout_table_strategy.CellTableChunker")
    mock_line_chunker_cls = mocker.patch("src.chunking.strategies.table.layout_table_strategy.LineTableChunker")

    # Create mock instances that the constructor will use
    mock_cell_chunker_instance = MagicMock()
    mock_line_chunker_instance = MagicMock()

    # When the classes are instantiated, return our mock instances
    mock_cell_chunker_cls.return_value = mock_cell_chunker_instance
    mock_line_chunker_cls.return_value = mock_line_chunker_instance

    return mock_cell_chunker_instance, mock_line_chunker_instance


@pytest.fixture
def default_config():
    """Fixture providing a default chunking configuration for tests."""
    return ChunkingConfig(maximum_chunk_size=500)


# Dummy arguments to pass into the chunk method for all tests
@pytest.fixture
def chunk_args():
    return {
        "page_number": 1,
        "metadata": MagicMock(),
        "chunk_index_start": 0,
        "raw_response": {},
    }


def test_dispatches_to_cell_chunker_when_it_can_handle(mock_chunkers, default_config, chunk_args):
    """
    Verifies that if the CellTableChunker can handle the block, it is used
    and the LineTableChunker is not consulted.
    """
    mock_cell_chunker, mock_line_chunker = mock_chunkers

    mock_cell_chunker.can_handle.return_value = True
    mock_cell_chunker.chunk.return_value = ["cell_chunk_output"]

    mock_layout_block = MagicMock(spec=Table, children=[MagicMock(spec=TableCell)])

    strategy = LayoutTableChunkingStrategy(config=default_config)

    result = strategy.chunk(layout_block=mock_layout_block, **chunk_args)

    mock_cell_chunker.can_handle.assert_called_once_with(mock_layout_block)
    mock_cell_chunker.chunk.assert_called_once()
    mock_line_chunker.can_handle.assert_not_called()  # the second chunker is skipped
    assert result == ["cell_chunk_output"]


def test_dispatches_to_line_chunker_as_fallback(mock_chunkers, default_config, chunk_args):
    """
    Verifies that if CellTableChunker cannot handle the block, the strategy
    correctly falls back to the LineTableChunker.
    """
    mock_cell_chunker, mock_line_chunker = mock_chunkers

    mock_cell_chunker.can_handle.return_value = False
    mock_line_chunker.can_handle.return_value = True
    mock_line_chunker.chunk.return_value = ["line_chunk_output"]

    mock_layout_block = MagicMock(spec=Layout, children=[MagicMock(spec=Line)])

    strategy = LayoutTableChunkingStrategy(config=default_config)

    result = strategy.chunk(layout_block=mock_layout_block, **chunk_args)

    mock_cell_chunker.can_handle.assert_called_once_with(mock_layout_block)
    mock_line_chunker.can_handle.assert_called_once_with(mock_layout_block)
    mock_cell_chunker.chunk.assert_not_called()
    mock_line_chunker.chunk.assert_called_once()
    assert result == ["line_chunk_output"]


def test_raises_exception_for_block_with_no_children(default_config, chunk_args):
    """
    Verifies that a ChunkException is raised if the layout block is empty.
    """

    mock_layout_block = MagicMock(spec=Layout, id="empty_block_id", children=[])
    strategy = LayoutTableChunkingStrategy(config=default_config)

    with pytest.raises(ChunkException) as exc_info:
        strategy.chunk(layout_block=mock_layout_block, **chunk_args)

    assert "has no children" in str(exc_info.value)
    assert "empty_block_id" in str(exc_info.value)


def test_raises_exception_when_no_suitable_chunker_found(mock_chunkers, default_config, chunk_args):
    """
    Verifies that a ChunkException is raised if no registered chunker can
    handle the block.
    """
    mock_cell_chunker, mock_line_chunker = mock_chunkers

    mock_cell_chunker.can_handle.return_value = False
    mock_line_chunker.can_handle.return_value = False

    mock_child = MagicMock()
    mock_child.__class__.__name__ = "UnsupportedBlockType"
    mock_layout_block = MagicMock(spec=Layout, id="unsupported_block_id", children=[mock_child])

    strategy = LayoutTableChunkingStrategy(config=default_config)

    with pytest.raises(ChunkException) as exc_info:
        strategy.chunk(layout_block=mock_layout_block, **chunk_args)

    assert "No suitable chunker found" in str(exc_info.value)
    assert "unsupported_block_id" in str(exc_info.value)
    assert "'UnsupportedBlockType'" in str(exc_info.value)


def test_dispatcher_selects_cell_chunker(mock_chunkers, default_config):
    """
    Tests that the dispatcher correctly selects the CellTableChunker.
    """
    mock_cell_chunker, mock_line_chunker = mock_chunkers
    handler = LayoutTableChunkingStrategy(default_config)

    # Make the cell chunker report that it can handle the block
    mock_cell_chunker.can_handle.return_value = True
    mock_line_chunker.can_handle.return_value = False

    # Mock the return value of its chunk method
    expected_result = [MagicMock()]
    mock_cell_chunker.chunk.return_value = expected_result

    # Create a fake layout block and call the handler
    fake_layout_block = MagicMock(spec=Layout)
    fake_layout_block.children = [MagicMock(spec=Table)]
    result = handler.chunk(fake_layout_block, 1, MagicMock(), 0)

    # Assertions
    mock_cell_chunker.can_handle.assert_called_once_with(fake_layout_block)
    mock_line_chunker.can_handle.assert_not_called()  # Because the first one was chosen
    mock_cell_chunker.chunk.assert_called_once()
    assert result == expected_result


def test_dispatcher_selects_line_chunker(mock_chunkers, default_config):
    """
    Tests that the dispatcher correctly selects the LineTableChunker.
    """
    mock_cell_chunker, mock_line_chunker = mock_chunkers
    handler = LayoutTableChunkingStrategy(default_config)

    # This time, the line chunker should be selected
    mock_cell_chunker.can_handle.return_value = False
    mock_line_chunker.can_handle.return_value = True

    expected_result = [MagicMock()]
    mock_line_chunker.chunk.return_value = expected_result

    fake_layout_block = MagicMock(spec=Layout)
    fake_layout_block.children = [MagicMock()]  # Some generic child
    result = handler.chunk(fake_layout_block, 1, MagicMock(), 0)

    # Assertions
    mock_cell_chunker.can_handle.assert_called_once_with(fake_layout_block)
    mock_line_chunker.can_handle.assert_called_once_with(fake_layout_block)
    mock_line_chunker.chunk.assert_called_once()
    assert result == expected_result
