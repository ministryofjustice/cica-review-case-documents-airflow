from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from textractor.entities.bbox import BoundingBox, SpatialObject

import src.chunking.strategies.layout_table as layout_table_module
from src.chunking.strategies.layout_table import LayoutTableChunkingStrategy


@pytest.fixture
def mock_dependencies(mocker):
    """Mocks the external dependencies of the Handler class."""
    mock_opensearch_document = mocker.patch.object(layout_table_module, "OpenSearchDocument", autospec=True)
    mock_enclosing_bbox = mocker.patch.object(
        layout_table_module.BoundingBox, "enclosing_bbox", return_value=MagicMock(spec=layout_table_module.BoundingBox)
    )
    return mock_opensearch_document, mock_enclosing_bbox


def create_fake_line(text: str, y: float, x: float, width: float, height: float):
    """Creates a mock line object with a real BoundingBox."""
    line = MagicMock(spec=layout_table_module.Line)
    line.id = f"line-{y}-{x}"
    line.text = text
    line.confidence = 99.0
    page_dimensions = SpatialObject(width=1, height=1)
    line.bbox = BoundingBox(x=x, y=y, width=width, height=height, spatial_object=page_dimensions)
    return line


def create_fake_cell(text: str, row: int, col: int, y: float):
    """
    Creates a simple data object to simulate a TableCell, avoiding MagicMock complexity.
    """
    # Using SimpleNamespace for data-holding objects in tests.
    page_dimensions = SpatialObject(width=1, height=1)
    return SimpleNamespace(
        id=f"cell-{row}-{col}",
        text=text,
        row_index=row,
        col_index=col,
        bbox=BoundingBox(x=col * 0.2, y=y, width=0.18, height=0.05, spatial_object=page_dimensions),
    )


def test_chunk_creates_a_single_chunk_for_each_row(mock_dependencies):
    """
    Tests that a LAYOUT_TABLE with two distinct visual rows results in two chunks.
    """
    mock_opensearch_document, mock_enclosing_bbox = mock_dependencies

    handler = LayoutTableChunkingStrategy(maximum_chunk_size=500)

    fake_lines = [
        create_fake_line("This is the first row.", y=0.1, x=0.1, width=0.2, height=0.02),
        create_fake_line("This is the second row.", y=0.2, x=0.2, width=0.2, height=0.02),
    ]

    fake_layout_block = MagicMock(spec=layout_table_module.Layout)
    # FIX: The 'id' attribute was missing on the mock object.
    fake_layout_block.id = "fake-layout-block-1"
    fake_layout_block.children = fake_lines
    fake_metadata = MagicMock(spec=layout_table_module.DocumentMetadata)
    page_number = 1
    chunk_index_start = 0

    result_chunks = handler.chunk(fake_layout_block, page_number, fake_metadata, chunk_index_start)

    assert len(result_chunks) == 2
    mock_opensearch_document.from_textractor_layout.assert_has_calls(
        [
            call(
                block=fake_layout_block,
                page_number=page_number,
                metadata=fake_metadata,
                chunk_index=0,
                chunk_text="This is the first row.",
                combined_bbox=mock_enclosing_bbox.return_value,
            ),
            call(
                block=fake_layout_block,
                page_number=page_number,
                metadata=fake_metadata,
                chunk_index=1,
                chunk_text="This is the second row.",
                combined_bbox=mock_enclosing_bbox.return_value,
            ),
        ],
        any_order=False,
    )


def test_chunk_creates_a_single_chunk_for_two_spatially_aligned_lines(mock_dependencies):
    """
    Tests that two Line objects on the same visual row are grouped into one chunk.
    """
    mock_opensearch_document, mock_enclosing_bbox = mock_dependencies

    handler = LayoutTableChunkingStrategy(maximum_chunk_size=500)

    fake_lines = [
        create_fake_line("This is the first part.", y=0.1, x=0.1, width=0.2, height=0.02),
        create_fake_line("This is the second part.", y=0.101, x=0.5, width=0.2, height=0.02),
    ]

    fake_layout_block = MagicMock(spec=layout_table_module.Layout)

    fake_layout_block.id = "fake-layout-block-2"
    fake_layout_block.children = fake_lines
    fake_metadata = MagicMock(spec=layout_table_module.DocumentMetadata)
    page_number = 1
    chunk_index_start = 0

    result_chunks = handler.chunk(fake_layout_block, page_number, fake_metadata, chunk_index_start)

    assert len(result_chunks) == 1
    mock_enclosing_bbox.assert_called_once_with([fake_lines[0].bbox, fake_lines[1].bbox])
    mock_opensearch_document.from_textractor_layout.assert_called_once_with(
        block=fake_layout_block,
        page_number=page_number,
        metadata=fake_metadata,
        chunk_index=0,
        chunk_text="This is the first part. This is the second part.",
        combined_bbox=mock_enclosing_bbox.return_value,
    )


def test_chunk_handles_cell_structure_correctly(mocker, mock_dependencies):
    """
    Tests that a LAYOUT_TABLE with a Cell structure is chunked correctly per row
    and that merged cells are handled properly.
    """
    mock_opensearch_document, mock_enclosing_bbox = mock_dependencies

    handler = LayoutTableChunkingStrategy(maximum_chunk_size=500)

    # Row 1
    cell_1_1 = create_fake_cell("Date", row=1, col=1, y=0.1)
    cell_1_2 = create_fake_cell("Description", row=1, col=2, y=0.1)
    # Row 2
    cell_2_1 = create_fake_cell("2025-09-03", row=2, col=1, y=0.2)
    cell_2_2 = create_fake_cell("Meeting", row=2, col=2, y=0.2)
    # Row 3 (Simulating a merged cell)
    cell_3_1 = create_fake_cell("Notes for all", row=3, col=1, y=0.3)
    cell_3_2 = create_fake_cell("Notes for all", row=3, col=2, y=0.3)

    fake_cells = [cell_1_1, cell_1_2, cell_2_1, cell_2_2, cell_3_1, cell_3_2]

    fake_table = MagicMock(spec=layout_table_module.Table)
    fake_table.table_cells = fake_cells

    fake_layout_block = MagicMock(spec=layout_table_module.Layout)
    fake_layout_block.id = "fake-layout-block-cells"
    fake_layout_block.children = [fake_table]
    mocker.patch.object(layout_table_module, "TableCell", new=SimpleNamespace)

    fake_metadata = MagicMock(spec=layout_table_module.DocumentMetadata)
    page_number = 1
    chunk_index_start = 0

    result_chunks = handler.chunk(fake_layout_block, page_number, fake_metadata, chunk_index_start)

    assert len(result_chunks) == 3

    mock_opensearch_document.from_textractor_layout.assert_has_calls(
        [
            call(
                chunk_text="Date Description",
                chunk_index=0,
                block=fake_layout_block,
                page_number=page_number,
                metadata=fake_metadata,
                combined_bbox=mock_enclosing_bbox.return_value,
            ),
            call(
                chunk_text="2025-09-03 Meeting",
                chunk_index=1,
                block=fake_layout_block,
                page_number=page_number,
                metadata=fake_metadata,
                combined_bbox=mock_enclosing_bbox.return_value,
            ),
            call(
                chunk_text="Notes for all",
                chunk_index=2,
                block=fake_layout_block,
                page_number=page_number,
                metadata=fake_metadata,
                combined_bbox=mock_enclosing_bbox.return_value,
            ),
        ]
    )
