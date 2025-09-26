from unittest.mock import MagicMock

import pytest
from textractor.entities.layout import Layout, Line
from textractor.entities.table import Table

from src.chunking.chunking_config import ChunkingConfig
from src.chunking.exceptions import ChunkException
from src.chunking.strategies.table import LayoutTableChunkingStrategy
from src.chunking.strategies.table.cell_chunker import CellTableChunker
from src.chunking.strategies.table.line_chunker import LineTableChunker


@pytest.fixture
def mock_chunkers(mocker):
    """Mocks the sub-chunker classes to test dispatch logic."""

    target_module_path = LayoutTableChunkingStrategy.__module__

    cell_chunker_target = f"{target_module_path}.{CellTableChunker.__name__}"
    line_chunker_target = f"{target_module_path}.{LineTableChunker.__name__}"

    mock_cell_chunker_cls = mocker.patch(cell_chunker_target)
    mock_line_chunker_cls = mocker.patch(line_chunker_target)

    mock_cell_chunker_instance = MagicMock()
    mock_line_chunker_instance = MagicMock()
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
        "raw_response": {"raw response data"},
    }


def test_dispatches_to_cell_chunker_when_first_child_table(mock_chunkers, default_config, chunk_args):
    """
    Verifies that if the CellTableChunker can handle the block, it is used
    and the LineTableChunker is not consulted.
    """
    mock_cell_chunker, mock_line_chunker = mock_chunkers

    mock_cell_chunker.chunk.return_value = ["cell_chunk_output"]

    fake_layout_block = MagicMock(spec=Layout)
    fake_layout_block.id = "fake-layout-block-child-table"
    fake_layout_block.children = [MagicMock(spec=Table)]
    fake_layout_block.layout_type = "LAYOUT_TABLE"

    strategy = LayoutTableChunkingStrategy(config=default_config)

    result = strategy.chunk(layout_block=fake_layout_block, **chunk_args)

    mock_cell_chunker.chunk.assert_called_once_with(
        fake_layout_block,
        chunk_args["page_number"],
        chunk_args["metadata"],
        chunk_args["chunk_index_start"],
        chunk_args["raw_response"],
    )
    mock_line_chunker.chunk.assert_not_called()
    assert result == ["cell_chunk_output"]


def test_raises_exception_for_block_with_no_children(default_config, chunk_args):
    """
    Verifies that a ChunkException is raised if the layout block is empty.
    """

    mock_layout_block = MagicMock(spec=Layout, id="empty_block_id", children=[], layout_type="LAYOUT_TABLE")
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

    mock_child = MagicMock()
    mock_child.__class__.__name__ = "UnsupportedBlockType"
    # mock_child.__class__.__layout_type__ = "UnsupportedBlockType"
    mock_layout_block = MagicMock(
        spec=Layout, id="unsupported_block_id", children=[mock_child], layout_type="LAYOUT_TABLE"
    )

    strategy = LayoutTableChunkingStrategy(config=default_config)

    with pytest.raises(ChunkException) as exc_info:
        strategy.chunk(layout_block=mock_layout_block, **chunk_args)

    assert (
        "Error determining chunker type for block unsupported_block_id: Unsupported LAYOUT_TABLE structure in block "
        "unsupported_block_id. Children are of type 'UnsupportedBlockType', which is not supported."
        in str(exc_info.value)
    )


def test_dispatcher_selects_line_chunker_when_first_child_line(mock_chunkers, default_config, chunk_args):
    """
    Tests that the dispatcher correctly selects the LineTableChunker.
    """

    mock_cell_chunker, mock_line_chunker = mock_chunkers

    mock_line_chunker.chunk.return_value = ["line_chunk_output"]

    fake_layout_block = MagicMock(spec=Layout)
    fake_layout_block.id = "fake-layout-block-child-line"
    fake_layout_block.children = [MagicMock(spec=Line)]
    fake_layout_block.layout_type = "LAYOUT_TABLE"

    strategy = LayoutTableChunkingStrategy(config=default_config)

    result = strategy.chunk(layout_block=fake_layout_block, **chunk_args)
    mock_line_chunker.chunk.assert_called_once_with(
        fake_layout_block,
        chunk_args["page_number"],
        chunk_args["metadata"],
        chunk_args["chunk_index_start"],
        chunk_args["raw_response"],
    )
    mock_cell_chunker.chunk.assert_not_called()
    assert result == ["line_chunk_output"]
