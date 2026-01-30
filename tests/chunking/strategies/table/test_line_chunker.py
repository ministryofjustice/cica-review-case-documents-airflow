import logging
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

# Application modules that we will be patching
import ingestion_pipeline.chunking.strategies.table.base as base_module
import ingestion_pipeline.chunking.strategies.table.line_chunker as line_chunker_module
from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.strategies.table.line_chunker import LineTableChunker


# --- Mock Objects ---
@dataclass
class MockSpatialObject:
    """Represents a dummy spatial context (page width/height)."""

    width: int = 1000
    height: int = 1000


@dataclass
class MockBoundingBox:
    """A simple mock for textractor.entities.bbox.BoundingBox."""

    x: float
    y: float
    width: float
    height: float
    spatial_object: Optional[MockSpatialObject] = field(default_factory=MockSpatialObject)

    @staticmethod
    def enclosing_bbox(bboxes: List["MockBoundingBox"]) -> "MockBoundingBox":
        if not bboxes:
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

    @staticmethod
    def from_normalized_dict(d, spatial_object):
        """Mocks the constructor that takes a dictionary."""
        return MockBoundingBox(
            x=d["Left"], y=d["Top"], width=d["Width"], height=d["Height"], spatial_object=spatial_object
        )


@dataclass
class MockLine:
    """A mock for textractor.entities.layout.Line."""

    id: str
    text: str
    bbox: Optional[MockBoundingBox]  # <--- CORRECT: bbox can be None
    confidence: float = 99.0
    raw_object: object = None  # Accept any type for testing malformed data

    def __post_init__(self):
        if self.raw_object is None:
            self.raw_object = {"Text": self.text}


@dataclass
class MockLayout:
    """A mock for textractor.entities.layout.Layout."""

    id: str
    bbox: MockBoundingBox
    children: List[MockLine]
    layout_type: str = "LAYOUT_TABLE"


@dataclass
class MockDocumentMetadata:
    source_doc_id: str


@dataclass
class MockTextBlock:
    """A mock for the REFACTORED ingestion_pipeline.chunking.strategies.table.schemas.TextBlock."""

    text: str
    bbox: "MockBoundingBox"
    confidence: float = 0.0

    @property
    def top(self) -> float:
        return self.bbox.y

    @property
    def left(self) -> float:
        return self.bbox.x

    @property
    def width(self) -> float:
        return self.bbox.width

    @property
    def height(self) -> float:
        return self.bbox.height

    @property
    def center_y(self) -> float:
        return self.top + (self.height / 2)


@pytest.fixture(autouse=True)
def apply_patches(monkeypatch):
    """This autouse fixture automatically applies patches for every test in this file.

    `monkeypatch` ensures that all changes are reverted after each test,
    preventing state leakage into other test files like the integration test.
    """
    monkeypatch.setattr(line_chunker_module, "BoundingBox", MockBoundingBox)
    monkeypatch.setattr(line_chunker_module, "Line", MockLine)
    monkeypatch.setattr(line_chunker_module, "TextBlock", MockTextBlock)
    monkeypatch.setattr(base_module, "BoundingBox", MockBoundingBox)


@pytest.fixture
def chunker():
    """Provides a LineTableChunker instance for tests."""
    return LineTableChunker(config=ChunkingConfig(y_tolerance_ratio=0.5, line_chunk_char_limit=0))


# --- Tests ---
def test_group_into_visual_rows(chunker):
    """Tests that text blocks are correctly grouped into rows based on vertical alignment."""
    blocks = [
        # Row 1 (both have y=0.1)
        MockTextBlock(text="R1C1", bbox=MockBoundingBox(x=0.1, y=0.1, width=0.2, height=0.02), confidence=0.99),
        MockTextBlock(text="R1C2", bbox=MockBoundingBox(x=0.4, y=0.1, width=0.2, height=0.02), confidence=0.99),
        # Row 2 (both have y=0.2)
        MockTextBlock(text="R2C1", bbox=MockBoundingBox(x=0.1, y=0.2, width=0.2, height=0.02), confidence=0.99),
        MockTextBlock(text="R2C2", bbox=MockBoundingBox(x=0.4, y=0.2, width=0.2, height=0.02), confidence=0.99),
    ]

    rows = chunker._group_into_visual_rows(blocks)

    assert len(rows) == 2
    assert len(rows[0]) == 2
    assert len(rows[1]) == 2
    assert rows[0][0].text == "R1C1"
    assert rows[1][0].text == "R2C1"


def test_recover_missed_lines(chunker):
    """Tests the workaround to find line IDs present in the raw response but missing.

    from the textractor Layout object's children.
    """
    mock_spatial_context = MockSpatialObject(width=1000, height=1000)
    layout_children = [MockLine("id1", "Actual Child", MockBoundingBox(0.1, 0.1, 0.8, 0.1))]
    layout_bbox = MockBoundingBox(0, 0, 1, 1, spatial_object=mock_spatial_context)
    layout_block = MockLayout(id="layout1", bbox=layout_bbox, children=layout_children)
    raw_response = {
        "Blocks": [
            {"Id": "layout1", "Relationships": [{"Type": "CHILD", "Ids": ["id1", "id2_missed"]}]},
            {"Id": "id1", "BlockType": "LINE", "Text": "Actual Child"},
            {
                "Id": "id2_missed",
                "BlockType": "LINE",
                "Text": "Missed Child",
                "Confidence": 95.0,
                "Geometry": {"BoundingBox": {"Top": 0.2, "Left": 0.1, "Width": 0.8, "Height": 0.1}},
            },
        ]
    }

    missed_blocks = chunker._recover_missed_lines(layout_block, raw_response)

    assert len(missed_blocks) == 1
    missed_block = missed_blocks[0]
    assert isinstance(missed_block, MockTextBlock)
    assert missed_block.text == "Missed Child"
    assert missed_block.top == pytest.approx(0.2)


def test_process_text_block_row_sorting(chunker):
    """Tests that blocks in a row are correctly sorted by their left coordinate."""
    blocks = [
        MockTextBlock(text="Second", confidence=99, bbox=MockBoundingBox(x=0.4, y=0.1, width=0.2, height=0.02)),
        MockTextBlock(text="First", confidence=99, bbox=MockBoundingBox(x=0.1, y=0.1, width=0.2, height=0.02)),
    ]

    chunk_text, bboxes = chunker._process_text_block_row(blocks)

    assert chunk_text == "First Second"
    assert len(bboxes) == 2
    assert bboxes[0].x == pytest.approx(0.1)
    assert bboxes[1].x == pytest.approx(0.4)


def test_chunk_method_integration(chunker, monkeypatch):
    """Tests the full chunking process from a Layout object to DocumentChunks."""

    class MockDocumentChunk:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        @classmethod
        def from_textractor_layout(cls, **kwargs):
            return cls(**kwargs)

    monkeypatch.setattr(base_module, "DocumentChunk", MockDocumentChunk)

    lines = [
        MockLine("l1", "Name", MockBoundingBox(x=0.1, y=0.1, width=0.2, height=0.05)),
        MockLine("l2", "Value", MockBoundingBox(x=0.4, y=0.1, width=0.2, height=0.05)),
        MockLine("l3", "Item A", MockBoundingBox(x=0.1, y=0.2, width=0.2, height=0.05)),
        MockLine("l4", "100", MockBoundingBox(x=0.4, y=0.2, width=0.2, height=0.05)),
    ]
    layout_block = MockLayout("layout1", MockBoundingBox(0, 0, 1, 1), children=lines)
    metadata = MockDocumentMetadata("doc1")

    chunks = chunker.chunk(layout_block, page_number=1, metadata=metadata, chunk_index_start=10, raw_response=None)

    assert len(chunks) == 2
    chunk1 = chunks[0]
    assert chunk1.kwargs["chunk_index"] == 10
    assert chunk1.kwargs["chunk_text"] == "Name Value"
    bbox1 = chunk1.kwargs["combined_bbox"]
    assert bbox1.x == pytest.approx(0.1)
    assert bbox1.width == pytest.approx(0.5)

    chunk2 = chunks[1]
    assert chunk2.kwargs["chunk_index"] == 11
    assert chunk2.kwargs["chunk_text"] == "Item A 100"
    bbox2 = chunk2.kwargs["combined_bbox"]
    assert bbox2.x == pytest.approx(0.1)
    assert bbox2.y == pytest.approx(0.2)


def test_convert_lines_handles_invalid_and_empty_data(chunker, caplog):
    """Tests the guard in `_convert_lines_to_text_blocks`.

    Verifies that it correctly skips:
    - Objects that are not `Line` instances.
    - Lines with no `bbox`.
    - Lines with no `text` or only whitespace `text`.
    """
    valid_line = MockLine("id1", "Valid Text", MockBoundingBox(0.1, 0.1, 0.1, 0.1))

    # Create a list of children with various invalid data points
    children = [
        valid_line,
        None,  # Not a Line instance
        "a string",  # Not a Line instance
        MockLine("id2", " ", MockBoundingBox(0.2, 0.2, 0.1, 0.1)),  # Whitespace only
        MockLine("id3", "", MockBoundingBox(0.3, 0.3, 0.1, 0.1)),  # Empty text
        MockLine("id4", "No BBox", bbox=None),  # NOW VALID: bbox is None
    ]

    with caplog.at_level(logging.WARNING):
        text_blocks = chunker._convert_lines_to_text_blocks(children)

    # It should have skipped all invalid entries and processed only the valid one
    assert len(text_blocks) == 1
    assert text_blocks[0].text == "Valid Text"
    # No warnings should be logged for this kind of skipping
    assert not caplog.records


def test_convert_lines_handles_malformed_raw_object(chunker, caplog):
    """Tests the `try...except (AttributeError, KeyError)` guard in `_convert_lines_to_text_blocks`.

    Verifies that the method continues processing even if a line's `raw_object` is
    corrupt, causing an exception.
    """
    valid_line = MockLine("id1", "First", MockBoundingBox(0.1, 0.1, 0.1, 0.1))

    # This line will cause an AttributeError because an int has no .get() method
    malformed_line = MockLine("id2", "Malformed", MockBoundingBox(0.2, 0.2, 0.1, 0.1), raw_object=123)

    another_valid_line = MockLine("id3", "Third", MockBoundingBox(0.3, 0.3, 0.1, 0.1))

    children = [valid_line, malformed_line, another_valid_line]

    with caplog.at_level(logging.WARNING):
        text_blocks = chunker._convert_lines_to_text_blocks(children)

    # It should have processed the two valid lines and skipped the malformed one
    assert len(text_blocks) == 2
    assert text_blocks[0].text == "First"
    assert text_blocks[1].text == "Third"

    # It should have logged a warning about the failure
    assert len(caplog.records) == 1
    assert "Failed to convert line to TextBlock" in caplog.text

    # --- CORRECTED ASSERTION ---
    # Check for the actual string representation of the AttributeError
    assert "'int' object has no attribute 'get'" in caplog.text


def test_recover_missed_lines_gracefully_handles_internal_error(chunker, monkeypatch, caplog):
    """Tests the broad `except Exception` guard in `_recover_missed_lines`.

    Verifies that if any unexpected error occurs during recovery, it's caught,
    logged, and the function returns `[]` without crashing the whole process.
    """
    # Force an internal function to raise an error
    monkeypatch.setattr(
        line_chunker_module.LineTableChunker,
        "_find_missed_line_ids",
        MagicMock(side_effect=ValueError("A wild error appears!")),
    )

    layout_block = MockLayout("id1", MockBoundingBox(0, 0, 1, 1), children=[])

    with caplog.at_level(logging.ERROR):
        missed_blocks = chunker._recover_missed_lines(layout_block, raw_response={})

    # The function should not crash and should return an empty list
    assert missed_blocks == []
    # An error should be logged
    assert len(caplog.records) == 1
    assert f"Error recovering missed lines for block {layout_block.id}" in caplog.text
    assert "A wild error appears!" in caplog.text


def test_recover_missed_lines_when_layout_has_no_spatial_object(chunker, caplog):
    """Tests the `if not spatial_object` guard in `_create_text_blocks_from_missed_ids`.

    This is an indirect test. We check that `_recover_missed_lines` returns empty
    if the provided layout block lacks the necessary page geometry.
    """
    # Create a layout block with bbox.spatial_object = None
    layout_bbox = MockBoundingBox(0, 0, 1, 1, spatial_object=None)
    layout_block = MockLayout(id="layout1", bbox=layout_bbox, children=[])
    raw_response = {
        "Blocks": [
            {"Id": "layout1", "Relationships": [{"Type": "CHILD", "Ids": ["id_missed"]}]},
            {
                "Id": "id_missed",
                "BlockType": "LINE",
                "Text": "Missed Text",
                "Geometry": {"BoundingBox": {"Top": 0.2, "Left": 0.1, "Width": 0.8, "Height": 0.1}},
            },
        ]
    }

    with caplog.at_level(logging.WARNING):
        missed_blocks = chunker._recover_missed_lines(layout_block, raw_response)

    # No blocks should be recovered
    assert missed_blocks == []
    # A warning should be logged about the missing context
    assert len(caplog.records) == 1
    assert f"No spatial context for layout {layout_block.id}" in caplog.text


def test_create_text_blocks_handles_bad_missed_data(chunker, caplog):
    """Tests various guards within `_create_text_blocks_from_missed_ids`.

    Verifies it correctly skips:
    - Missed IDs that aren't LINEs.
    - Missed LINEs with no text.
    - Missed LINEs with malformed geometry data (triggering the `except`).
    """
    layout_block = MockLayout(id="l1", bbox=MockBoundingBox(0, 0, 1, 1), children=[])
    missed_ids = {"id_ok", "id_word", "id_notext", "id_badgeom"}
    raw_response = {
        "Blocks": [
            {
                "Id": "id_ok",
                "BlockType": "LINE",
                "Text": "Good Line",
                "Geometry": {"BoundingBox": {"Top": 0.1, "Left": 0.1, "Width": 0.1, "Height": 0.1}},
                "Confidence": 99.0,
            },
            # This is a WORD, not a LINE, and should be skipped
            {"Id": "id_word", "BlockType": "WORD", "Text": "Not a Line"},
            # This is a LINE but has no text, and should be skipped
            {"Id": "id_notext", "BlockType": "LINE", "Text": " "},
            # This LINE has invalid geometry and should be caught by the except block
            {
                "Id": "id_badgeom",
                "BlockType": "LINE",
                "Text": "Bad Geometry",
                "Geometry": {"BoundingBox": {"Top": 0.3, "Left": 0.3}},  # Missing Width/Height
            },
        ]
    }

    with caplog.at_level(logging.ERROR):
        blocks = chunker._create_text_blocks_from_missed_ids(missed_ids, raw_response, layout_block)

    # Only the one valid block should have been created
    assert len(blocks) == 1
    assert blocks[0].text == "Good Line"

    # An error should be logged for the geometry failure
    assert len(caplog.records) == 1
    assert "Failed to create TextBlock LAYOUT_TABLE from missed line id_badgeom: 'Width'" in caplog.text


def test_group_into_visual_rows_with_no_blocks(chunker):
    """Tests the `if not blocks:` guard in `_group_into_visual_rows`."""
    assert chunker._group_into_visual_rows([]) == []


def test_group_into_visual_rows_with_zero_height_blocks(chunker):
    """Tests the `if not heights:` guard in `_group_into_visual_rows`.

    Verifies the fallback behavior that treats each zero-height block as its own row
    to avoid a `statistics.mean` error.
    """
    blocks = [
        MockTextBlock(text="B1", bbox=MockBoundingBox(x=0.1, y=0.1, width=0.2, height=0)),
        MockTextBlock(text="B2", bbox=MockBoundingBox(x=0.4, y=0.1, width=0.2, height=0)),
        MockTextBlock(text="B3", bbox=MockBoundingBox(x=0.1, y=0.2, width=0.2, height=0)),
    ]

    rows = chunker._group_into_visual_rows(blocks)

    # It should not crash and should return each block in its own row
    assert len(rows) == 3
    assert len(rows[0]) == 1
    assert rows[0][0].text == "B1"
    assert rows[1][0].text == "B2"
    assert rows[2][0].text == "B3"


def test_chunk_method_resilience_with_mixed_quality_data(chunker, monkeypatch):
    """An integration test to ensure the main `chunk` method is resilient to
    a layout block containing a mix of valid and invalid lines.
    """

    # Mock DocumentChunk as in your original test
    class MockDocumentChunk:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        @classmethod
        def from_textractor_layout(cls, **kwargs):
            return cls(**kwargs)

    monkeypatch.setattr(base_module, "DocumentChunk", MockDocumentChunk)

    lines = [
        MockLine("l1", "Name", MockBoundingBox(x=0.1, y=0.1, width=0.2, height=0.05)),
        MockLine("l2", "Value", MockBoundingBox(x=0.4, y=0.1, width=0.2, height=0.05)),
        # Invalid data to be ignored
        MockLine("l_bad1", " ", MockBoundingBox(x=0.1, y=0.15, width=0.2, height=0.05)),
        MockLine("l_bad2", "No BBox", bbox=None),
        # Next valid row
        MockLine("l3", "Item A", MockBoundingBox(x=0.1, y=0.2, width=0.2, height=0.05)),
        MockLine("l4", "100", MockBoundingBox(x=0.4, y=0.2, width=0.2, height=0.05)),
    ]
    layout_block = MockLayout("layout1", MockBoundingBox(0, 0, 1, 1), children=lines)
    metadata = MockDocumentMetadata("doc1")

    chunks = chunker.chunk(layout_block, page_number=1, metadata=metadata, chunk_index_start=0)

    # The chunker should have ignored the two bad lines and produced two valid chunks
    assert len(chunks) == 2
    assert chunks[0].kwargs["chunk_text"] == "Name Value"
    assert chunks[1].kwargs["chunk_text"] == "Item A 100"


def test_extract_text_blocks_recovers_and_sorts_missed_lines(chunker):
    """Tests the _extract_text_blocks method's logic to recover, extend, and sort.

    Verifies that when a raw_response is provided:
    1. Missed lines are recovered.
    2. The list of text blocks is extended with the missed ones.
    3. The final combined list is correctly sorted by top, then left coordinates.
    """
    # ARRANGE
    # An existing line that is part of the layout object's children.
    # We place it further down the page (y=0.3).
    existing_line = MockLine("id_existing", "Existing Line", MockBoundingBox(x=0.1, y=0.3, width=0.8, height=0.1))

    layout_block = MockLayout(id="layout1", bbox=MockBoundingBox(0, 0, 1, 1), children=[existing_line])

    # A raw response that contains a "missed" line.
    # Crucially, we place it *above* the existing line (y=0.1) to test the sort.
    raw_response = {
        "Blocks": [
            {"Id": "layout1", "Relationships": [{"Type": "CHILD", "Ids": ["id_existing", "id_missed"]}]},
            {"Id": "id_existing", "BlockType": "LINE", "Text": "Existing Line"},
            {
                "Id": "id_missed",
                "BlockType": "LINE",
                "Text": "Recovered Missed Line",
                "Confidence": 95.0,
                "Geometry": {"BoundingBox": {"Top": 0.1, "Left": 0.1, "Width": 0.8, "Height": 0.1}},
            },
        ]
    }

    final_blocks = chunker._extract_text_blocks(layout_block, raw_response)

    assert len(final_blocks) == 2, "Should contain both existing and missed blocks."

    assert final_blocks[0].text == "Recovered Missed Line"
    assert final_blocks[0].top == pytest.approx(0.1)

    assert final_blocks[1].text == "Existing Line"
    assert final_blocks[1].top == pytest.approx(0.3)


def test_chunk_with_no_text_blocks(chunker, monkeypatch):
    """Tests that chunking returns an empty list if no text blocks are extracted."""
    # ARRANGE
    # Mock _extract_text_blocks to return an empty list, simulating no text found.
    monkeypatch.setattr(chunker, "_extract_text_blocks", MagicMock(return_value=[]))

    layout_block = MockLayout("empty_layout", MockBoundingBox(0, 0, 1, 1), children=[])
    metadata = MockDocumentMetadata("doc1")

    # ACT
    chunks = chunker.chunk(layout_block, page_number=1, metadata=metadata, chunk_index_start=0)

    # ASSERT
    assert chunks == []


def test_chunk_method_single_chunk_under_limit(chunker, monkeypatch):
    """Tests that a single chunk is created when the total text is under the character limit."""

    class MockDocumentChunk:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        @classmethod
        def from_textractor_layout(cls, **kwargs):
            # In the actual implementation, this would be called on the class
            # For the mock, we just instantiate it to capture the args
            return cls(**kwargs)

    monkeypatch.setattr(base_module, "DocumentChunk", MockDocumentChunk)
    # Mock the base class method that creates the chunk
    monkeypatch.setattr(
        base_module.BaseTableChunker,
        "_create_chunk",
        lambda self, **kwargs: MockDocumentChunk(**kwargs),
    )

    # Set a high character limit to force the single-chunk path
    chunker.config.line_chunk_char_limit = 500

    lines = [
        MockLine("l1", "Row 1", MockBoundingBox(x=0.1, y=0.1, width=0.8, height=0.05)),
        MockLine("l2", "Row 2", MockBoundingBox(x=0.1, y=0.2, width=0.8, height=0.05)),
    ]
    layout_block = MockLayout("layout1", MockBoundingBox(0, 0, 1, 1), children=lines)
    metadata = MockDocumentMetadata("doc1")

    # ACT
    chunks = chunker.chunk(layout_block, page_number=1, metadata=metadata, chunk_index_start=5)

    # ASSERT
    assert len(chunks) == 1
    single_chunk = chunks[0]
    assert single_chunk.kwargs["chunk_index"] == 5
    assert single_chunk.kwargs["chunk_text"] == "Row 1\nRow 2"

    # Check that the bboxes for the single chunk are from all original text blocks
    assert len(single_chunk.kwargs["bboxes"]) == 2


def test_chunk_handles_empty_visual_rows(chunker, monkeypatch):
    """Tests that the chunker correctly skips empty lists in the visual rows."""

    class MockDocumentChunk:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(base_module, "DocumentChunk", MockDocumentChunk)
    monkeypatch.setattr(
        base_module.BaseTableChunker,
        "_create_chunk",
        lambda self, **kwargs: MockDocumentChunk(**kwargs),
    )

    # Mock _group_into_visual_rows to return a list containing an empty list
    # This simulates a scenario where row grouping might produce an empty row
    row1_block = MockTextBlock(text="Row 1", bbox=MockBoundingBox(0.1, 0.1, 0.8, 0.1))
    row3_block = MockTextBlock(text="Row 3", bbox=MockBoundingBox(0.1, 0.3, 0.8, 0.1))

    monkeypatch.setattr(chunker, "_group_into_visual_rows", MagicMock(return_value=[[row1_block], [], [row3_block]]))

    # Also mock _extract_text_blocks to return the blocks that are used in the mocked rows
    monkeypatch.setattr(chunker, "_extract_text_blocks", MagicMock(return_value=[row1_block, row3_block]))

    layout_block = MockLayout("layout1", MockBoundingBox(0, 0, 1, 1), children=[])
    metadata = MockDocumentMetadata("doc1")

    # ACT
    chunks = chunker.chunk(layout_block, page_number=1, metadata=metadata, chunk_index_start=0)

    # ASSERT
    # It should have skipped the empty row and created chunks for the valid ones
    assert len(chunks) == 2
    assert chunks[0].kwargs["chunk_text"] == "Row 1"
    assert chunks[1].kwargs["chunk_text"] == "Row 3"


def test_find_missed_line_ids_no_layout_json(chunker):
    """Tests that an empty set is returned if the layout_block ID is not in the raw_response."""
    layout_block = MockLayout(id="not_in_response", bbox=MockBoundingBox(0, 0, 1, 1), children=[])
    raw_response = {"Blocks": [{"Id": "some_other_id"}]}
    missed_ids = chunker._find_missed_line_ids(layout_block, raw_response)
    assert missed_ids == set()


def test_find_missed_line_ids_no_relationships(chunker):
    """Tests that an empty set is returned if the layout block has no CHILD relationships."""
    layout_block = MockLayout(id="layout1", bbox=MockBoundingBox(0, 0, 1, 1), children=[])
    raw_response = {
        "Blocks": [
            {"Id": "layout1", "Relationships": [{"Type": "OTHER", "Ids": ["id1"]}]},
        ]
    }
    missed_ids = chunker._find_missed_line_ids(layout_block, raw_response)
    assert missed_ids == set()


def test_extract_text_blocks_no_raw_response(chunker):
    """Tests that _extract_text_blocks works correctly when raw_response is None."""
    # ARRANGE
    # Create lines that are out of order to test the sorting that should happen
    # in _convert_lines_to_text_blocks.
    line1 = MockLine("id1", "Second Line", MockBoundingBox(x=0.1, y=0.2, width=0.8, height=0.1))
    line2 = MockLine("id2", "First Line", MockBoundingBox(x=0.1, y=0.1, width=0.8, height=0.1))
    layout_block = MockLayout(id="layout1", bbox=MockBoundingBox(0, 0, 1, 1), children=[line1, line2])

    # ACT
    # Call the method with raw_response=None, so it only processes the children
    final_blocks = chunker._extract_text_blocks(layout_block, raw_response=None)

    # ASSERT
    assert len(final_blocks) == 2
    # Verify that the blocks were sorted correctly by the `_convert_lines_to_text_blocks` method
    assert final_blocks[0].text == "First Line"
    assert final_blocks[1].text == "Second Line"


def test_recover_missed_lines_no_missed_ids(chunker, monkeypatch):
    """Tests that _recover_missed_lines returns an empty list if no IDs are missed."""
    # ARRANGE
    # Mock _find_missed_line_ids to return an empty set
    monkeypatch.setattr(chunker, "_find_missed_line_ids", MagicMock(return_value=set()))
    layout_block = MockLayout(id="layout1", bbox=MockBoundingBox(0, 0, 1, 1), children=[])

    # ACT
    recovered_blocks = chunker._recover_missed_lines(layout_block, raw_response={})

    # ASSERT
    assert recovered_blocks == []
