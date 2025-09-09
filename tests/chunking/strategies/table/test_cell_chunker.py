from dataclasses import dataclass
from typing import List
from unittest.mock import MagicMock, call

import pytest
from textractor.entities.bbox import BoundingBox, SpatialObject
from textractor.entities.layout import Layout
from textractor.entities.table import Table
from textractor.entities.table_cell import TableCell

import src.chunking.strategies.table.base as base_module
import src.chunking.strategies.table.cell_chunker as cell_chunker_module
from src.chunking.config import ChunkingConfig
from src.chunking.schemas import DocumentMetadata
from src.chunking.strategies.table.cell_chunker import CellTableChunker


@pytest.fixture
def default_config():
    return ChunkingConfig(y_tolerance_ratio=0.5)


def create_fake_cell(text: str, row: int, col: int, y: float):
    """Creates a mock TableCell object with a spec."""
    page_dimensions = SpatialObject(width=1, height=1)
    mock_cell = MagicMock(spec=TableCell)
    mock_cell.id = f"cell-{row}-{col}"
    mock_cell.text = text
    mock_cell.row_index = row
    mock_cell.col_index = col
    mock_cell.bbox = BoundingBox(x=col * 0.2, y=y, width=0.18, height=0.05, spatial_object=page_dimensions)
    return mock_cell


def test_chunk_handles_cell_structure_correctly(default_config, mocker):
    """
    Tests that a LAYOUT_TABLE with a Cell structure is chunked correctly per row
    and that merged cells are handled properly.
    """
    handler = CellTableChunker(default_config)
    mock_create_chunk = mocker.patch.object(
        handler, "_create_chunk", side_effect=lambda chunk_text, **kwargs: f"CHUNK:{chunk_text}"
    )

    cell_1_1 = create_fake_cell("Date", row=1, col=1, y=0.1)
    cell_1_2 = create_fake_cell("Description", row=1, col=2, y=0.1)
    cell_2_1 = create_fake_cell("2025-09-03", row=2, col=1, y=0.2)
    cell_2_2 = create_fake_cell("Meeting", row=2, col=2, y=0.2)
    # Merged cell simulation
    cell_3_1 = create_fake_cell("Notes for all", row=3, col=1, y=0.3)
    cell_3_2 = create_fake_cell("Notes for all", row=3, col=2, y=0.3)

    fake_cells = [cell_1_1, cell_1_2, cell_2_1, cell_2_2, cell_3_1, cell_3_2]
    fake_table = MagicMock(spec=Table)
    fake_table.table_cells = fake_cells

    fake_layout_block = MagicMock(spec=Layout)
    fake_layout_block.id = "fake-layout-block-cells"
    fake_layout_block.children = [fake_table]

    fake_metadata = MagicMock(spec=DocumentMetadata)
    page_number = 1
    chunk_index_start = 0

    result_chunks = handler.chunk(fake_layout_block, page_number, fake_metadata, chunk_index_start)

    assert len(result_chunks) == 3
    assert result_chunks == ["CHUNK:Date Description", "CHUNK:2025-09-03 Meeting", "CHUNK:Notes for all"]

    mock_create_chunk.assert_has_calls(
        [
            call(
                chunk_text="Date Description",
                bboxes=[cell_1_1.bbox, cell_1_2.bbox],
                layout_block=fake_layout_block,
                page_number=1,
                metadata=fake_metadata,
                chunk_index=0,
            ),
            call(
                chunk_text="2025-09-03 Meeting",
                bboxes=[cell_2_1.bbox, cell_2_2.bbox],
                layout_block=fake_layout_block,
                page_number=1,
                metadata=fake_metadata,
                chunk_index=1,
            ),
            call(
                chunk_text="Notes for all",
                bboxes=[cell_3_1.bbox, cell_3_2.bbox],
                layout_block=fake_layout_block,
                page_number=1,
                metadata=fake_metadata,
                chunk_index=2,
            ),
        ]
    )


def test_chunk_skips_rows_with_no_text_content(default_config, mocker):
    """
    Tests that the chunker skips creating chunks for rows that only contain
    empty or whitespace cells (L39).
    """
    handler = CellTableChunker(default_config)
    mock_create_chunk = mocker.patch.object(handler, "_create_chunk")

    # Row 1 is empty, Row 2 has content
    cell_1_1 = create_fake_cell("", row=1, col=1, y=0.1)
    cell_1_2 = create_fake_cell("   ", row=1, col=2, y=0.1)
    cell_2_1 = create_fake_cell("Real", row=2, col=1, y=0.2)
    cell_2_2 = create_fake_cell("Content", row=2, col=2, y=0.2)

    fake_table = MagicMock(spec=Table)
    fake_table.table_cells = [cell_1_1, cell_1_2, cell_2_1, cell_2_2]

    fake_layout_block = MagicMock(spec=Layout)
    fake_layout_block.id = "fake-layout-block-cells"
    fake_layout_block.children = [fake_table]
    fake_metadata = MagicMock(spec=DocumentMetadata)

    handler.chunk(fake_layout_block, 1, fake_metadata, 0)

    # Assert that a chunk was created ONLY for the row with content
    mock_create_chunk.assert_called_once()
    assert mock_create_chunk.call_args.kwargs["chunk_text"] == "Real Content"


def test_chunk_ignores_non_table_objects_in_layout(default_config, mocker):
    """
    Tests that the chunker correctly ignores objects in layout_block.children
    that are not instances of Table.
    """
    handler = CellTableChunker(default_config)
    mock_create_chunk = mocker.patch.object(handler, "_create_chunk")

    cell = create_fake_cell("Some Data", row=1, col=1, y=0.1)
    fake_table = MagicMock(spec=Table)
    fake_table.table_cells = [cell]

    # A mock object that is NOT a table
    not_a_table = MagicMock()

    fake_layout_block = MagicMock(spec=Layout)
    fake_layout_block.id = "fake-layout-block-cells"
    # The layout contains a valid table and an invalid object
    fake_layout_block.children = [fake_table, not_a_table]
    fake_metadata = MagicMock(spec=DocumentMetadata)

    handler.chunk(fake_layout_block, 1, fake_metadata, 0)

    # Should only be called once, for the content of the real table
    mock_create_chunk.assert_called_once()


# BoundingBox and other dependencies mocks
@dataclass
class MockBoundingBox:
    """A simple mock for textractor.entities.bbox.BoundingBox."""

    x: float
    y: float
    width: float
    height: float

    @staticmethod
    def enclosing_bbox(bboxes: List["MockBoundingBox"]) -> "MockBoundingBox":
        """Mimics the real textractor method."""
        if not bboxes:
            # This case should be handled by the caller, but we can return an empty box.
            return MockBoundingBox(0, 0, 0, 0)

        min_x = min(b.x for b in bboxes)
        min_y = min(b.y for b in bboxes)
        max_x_plus_width = max(b.x + b.width for b in bboxes)
        max_y_plus_height = max(b.y + b.height for b in bboxes)

        return MockBoundingBox(
            x=min_x,
            y=min_y,
            width=max_x_plus_width - min_x,
            height=max_y_plus_height - min_y,
        )


@dataclass
class MockTableCell:
    """A mock for textractor.entities.table_cell.TableCell."""

    id: str
    row_index: int
    col_index: int
    text: str
    bbox: MockBoundingBox


@dataclass
class MockLayout:
    """A mock for textractor.entities.layout.Layout."""

    id: str
    bbox: MockBoundingBox


@dataclass
class MockDocumentMetadata:
    """A mock for src.chunking.schemas.DocumentMetadata."""

    document_id: str


cell_chunker_module.BoundingBox = MockBoundingBox
base_module.BoundingBox = MockBoundingBox


@pytest.fixture
def chunker(default_config):
    """Provides a CellTableChunker instance for tests."""

    return CellTableChunker(config=default_config)


def test_process_table_row_generates_correct_bboxes(chunker):
    """
    Tests the _process_table_row method to ensure it correctly extracts
    all bounding boxes from a list of cells.
    """
    # Arrange: Create mock cells for a single row
    cells = [
        MockTableCell(
            id="c1", row_index=1, col_index=1, text="Cell 1", bbox=MockBoundingBox(x=0.1, y=0.1, width=0.2, height=0.05)
        ),
        MockTableCell(
            id="c2", row_index=1, col_index=2, text="Cell 2", bbox=MockBoundingBox(x=0.3, y=0.1, width=0.2, height=0.05)
        ),
    ]

    # Act
    _text, bboxes = chunker._process_table_row(cells)

    # Assert
    assert len(bboxes) == 2
    assert bboxes[0] == cells[0].bbox
    assert bboxes[1] == cells[1].bbox


def test_create_chunk_with_multiple_bboxes(chunker, monkeypatch):
    """
    Tests the _create_chunk method to verify it calculates the
    enclosing bounding box correctly for a typical row.
    """

    class MockOpenSearchDocument:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        @classmethod
        def from_textractor_layout(cls, **kwargs):
            return cls(**kwargs)

    monkeypatch.setattr(base_module, "OpenSearchDocument", MockOpenSearchDocument)

    bboxes = [
        MockBoundingBox(x=0.1, y=0.2, width=0.3, height=0.1),  # right=0.4, bottom=0.3
        MockBoundingBox(x=0.5, y=0.2, width=0.4, height=0.1),  # right=0.9, bottom=0.3
    ]

    expected_bbox = MockBoundingBox(x=0.1, y=0.2, width=0.8, height=0.1)

    mock_layout = MockLayout(id="layout1", bbox=MockBoundingBox(0, 0, 1, 1))
    mock_metadata = MockDocumentMetadata(document_id="doc1")

    # Act
    chunk = chunker._create_chunk(
        chunk_text="Some text",
        bboxes=bboxes,
        layout_block=mock_layout,
        page_number=1,
        metadata=mock_metadata,
        chunk_index=0,
    )

    # Assert
    # We check the `combined_bbox` passed to the OpenSearchDocument constructor
    result_bbox = chunk.kwargs["combined_bbox"]
    assert result_bbox.x == pytest.approx(expected_bbox.x)
    assert result_bbox.y == pytest.approx(expected_bbox.y)
    assert result_bbox.width == pytest.approx(expected_bbox.width)
    assert result_bbox.height == pytest.approx(expected_bbox.height)


def test_create_chunk_with_no_bboxes(chunker, monkeypatch):
    """
    Tests the edge case where the bboxes list is empty.
    The chunk should fall back to using the layout_block's bbox.
    """

    # Arrange
    class MockOpenSearchDocument:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        @classmethod
        def from_textractor_layout(cls, **kwargs):
            return cls(**kwargs)

    monkeypatch.setattr(base_module, "OpenSearchDocument", MockOpenSearchDocument)

    # This is the bbox we expect to be used as the fallback
    layout_bbox = MockBoundingBox(x=0.05, y=0.05, width=0.9, height=0.9)
    mock_layout = MockLayout(id="layout1", bbox=layout_bbox)
    mock_metadata = MockDocumentMetadata(document_id="doc1")

    # Act
    chunk = chunker._create_chunk(
        chunk_text="Some text",
        bboxes=[],  # Empty list!
        layout_block=mock_layout,
        page_number=1,
        metadata=mock_metadata,
        chunk_index=0,
    )

    # Assert
    result_bbox = chunk.kwargs["combined_bbox"]
    assert result_bbox == layout_bbox
