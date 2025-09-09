# tests/chunking/strategies/table/test_layout_table_strategy.py

from unittest.mock import MagicMock

import pytest
from textractor.entities.layout import Layout
from textractor.entities.table import Table

from src.chunking.config import ChunkingConfig
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
