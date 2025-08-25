import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, cast
from unittest.mock import MagicMock, PropertyMock

import pytest
from textractor.entities.bbox import BoundingBox
from textractor.entities.document import Document

from chunk_handler.chunk_extractor import (
    ChunkExtractor,
    ChunkingConfig,
    ChunkingStrategy,
    DocumentMetadata,
    OpenSearchChunk,
)
from chunk_handler.tests.utils.textract_response_builder import textractor_document_factory
from data_models.chunk_models import BoundingBoxDict

# Define the path to our singular realistic test data
TEXTRACT_JSON_PATH = Path(__file__).parent / "data" / "single_text_layout_textract_response.json"


@dataclass
class MockBoundingBox:
    width: float
    height: float
    x: float
    y: float


# Textractor BoundingBox mock Patch
ChunkExtractor._combine_bounding_boxes.__globals__["BoundingBox"] = MockBoundingBox


@pytest.fixture
def textract_response():
    """Loads the sample Textract JSON response from a file."""
    with open(TEXTRACT_JSON_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def document_metadata_factory():
    """
    Returns a factory function to create DocumentMetadata objects.
    This allows tests to override default values as needed.
    """

    def _factory(**overrides):
        """
        Inner factory function with default metadata values.
        Accepts keyword arguments to override any default.
        """
        case_ref = "25-787878"
        received_date = date.fromisoformat("2025-08-21")
        correspondence_type = "TC19"

        defaults = {
            "ingested_doc_id": "unique_ingested_doc_UUID",
            "source_file_name": "test_ingested_document.pdf",
            "page_count": 1,
            "case_ref": case_ref,
            "received_date": received_date,
            "correspondence_type": correspondence_type,
        }
        # Merge the overrides into the defaults
        final_args = {**defaults, **overrides}
        return DocumentMetadata(**final_args)

    return _factory


def test_combine_bounding_boxes_multiple_boxes():
    """Test combining multiple bounding boxes."""
    # Arrange: Create mock bounding boxes
    bbox1 = MockBoundingBox(width=10, height=20, x=100, y=50)  # top-left
    bbox2 = MockBoundingBox(width=5, height=5, x=115, y=60)  # middle
    bbox3 = MockBoundingBox(width=30, height=40, x=80, y=80)  # bottom-left
    bbox4 = MockBoundingBox(width=10, height=10, x=150, y=40)  # top-right

    bboxes = [bbox1, bbox2, bbox3, bbox4]

    # Act: Call the method to be tested
    combined_bbox = ChunkExtractor._combine_bounding_boxes(cast(List[BoundingBox], bboxes))

    # Assert: Verify the combined bounding box coordinates and dimensions
    assert combined_bbox.x == 80.0, "The minimum x should be 80."
    assert combined_bbox.y == 40.0, "The minimum y should be 40."

    # Calculate expected max right and max bottom
    max_right = max(bbox.x + bbox.width for bbox in bboxes)
    max_bottom = max(bbox.y + bbox.height for bbox in bboxes)

    assert combined_bbox.x + combined_bbox.width == max_right, "The combined right edge is incorrect."
    assert combined_bbox.y + combined_bbox.height == max_bottom, "The combined bottom edge is incorrect."

    assert combined_bbox.width == (150 + 10) - 80, "Combined width is incorrect."
    assert combined_bbox.height == (80 + 40) - 40, "Combined height is incorrect."


def test_combine_bounding_boxes_single_box():
    """Test combining a single bounding box."""
    # Arrange
    single_bbox = MockBoundingBox(width=50, height=75, x=20, y=10)
    bboxes = [single_bbox]

    # Act
    combined_bbox = ChunkExtractor._combine_bounding_boxes(cast(List[BoundingBox], bboxes))

    # Assert
    assert combined_bbox == single_bbox, "Single box should return the same box."


def test_combine_bounding_boxes_empty_list():
    """Test that an empty list raises a ValueError."""
    # Arrange
    bboxes = []

    # Act & Assert
    with pytest.raises(ValueError, match="Bounding box combination requires at least one box."):
        ChunkExtractor._combine_bounding_boxes(bboxes)


def test_extract_single_layout_chunk(textract_response, document_metadata_factory):
    """
    Tests that a single LAYOUT_TEXT block is correctly processed
    into an OpenSearch chunk document.
    This is test usign an actutal Textract response.
    """

    mock_doc = Document.open(textract_response)

    # Call the factory, providing overrides for this specific test case
    mock_metadata = document_metadata_factory()
    extractor = ChunkExtractor()
    actual_chunks: list[OpenSearchChunk] = extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 1
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchChunk)

    expected_text = (
        "We have discussed with our patient, who has requested we release all medical records from the "
        "date of the incident, from birth. Please find these attached."
    )

    chunk1.chunk_id = "unique_ingested_doc_UUID_p1_c0"  # Set chunk_id to match expected value for assertion
    chunk1.ingested_doc_id = "unique_ingested_doc_UUID"  # Set ingested_doc_id to match expected value for assertion
    chunk1.source_file_name = "document_single_layout_response.pdf"  # Set source_file_name to match expected value
    chunk1.chunk_text = expected_text  # Set chunk_text to match expected value
    chunk1.embedding = None  # We will handle embedding later
    chunk1.case_ref = None  # Metadata to be added later
    chunk1.received_date = None  # Metadata to be added later
    chunk1.correspondence_type = None  # Metadata to be added later
    chunk1.page_count = 1  # Set page_count to match expected value
    chunk1.page_number = 1  # Set page_number to match expected value
    chunk1.chunk_index = 0  # Set chunk_index to match expected value
    chunk1.chunk_type = "LAYOUT_TEXT"  # Set chunk_type to match expected value
    chunk1.confidence = 0.60009765625  # Set confidence to match
    chunk1.bounding_box = BoundingBoxDict(
        width=0.7254804372787476,
        height=0.02834956906735897,
        left=0.12123029679059982,
        top=0.4854643642902374,
    )


def test_create_opensearch_chunk_formats_correctly(document_metadata_factory):
    # Arrange
    mock_block = MagicMock()
    type(mock_block).text = PropertyMock(return_value="  Some text.  ")
    type(mock_block).layout_type = PropertyMock(return_value="LAYOUT_TEXT")
    type(mock_block).confidence = PropertyMock(return_value=0.95)
    # Mock the bbox object and its properties
    mock_bbox = MagicMock()
    type(mock_bbox).width = PropertyMock(return_value=0.1)
    type(mock_block).bbox = PropertyMock(return_value=mock_bbox)
    mock_page = MagicMock()
    type(mock_page).page_num = PropertyMock(return_value=5)

    expected_bbox = BoundingBoxDict(
        width=mock_bbox.width,
        height=mock_bbox.height,
        left=mock_bbox.x,
        top=mock_bbox.y,
    )

    mock_metadata = document_metadata_factory(
        page_count=10,
    )

    chunk = OpenSearchChunk.from_textractor_layout(
        block=mock_block, page=mock_page, metadata=mock_metadata, chunk_index=3
    )

    # Assert
    assert chunk.chunk_id == "unique_ingested_doc_UUID_p5_c3"
    assert chunk.chunk_text == "Some text."  # Test the .strip()
    assert chunk.page_number == 5
    assert chunk.chunk_index == 3
    assert chunk.ingested_doc_id == "unique_ingested_doc_UUID"
    assert chunk.confidence == 0.95
    assert chunk.bounding_box == expected_bbox
    assert chunk.source_file_name == "test_ingested_document.pdf"
    assert chunk.embedding is None
    assert chunk.case_ref == "25-787878"
    assert chunk.received_date == date.fromisoformat("2025-08-21")
    assert chunk.correspondence_type == "TC19"
    assert chunk.page_count == 10
    assert chunk.chunk_type == "LAYOUT_TEXT"


def test_multiple_pages_with_layout_text(document_metadata_factory):
    document_definition = [
        [{"type": "LAYOUT_TEXT", "lines": ["Content on the first page."]}],  # Page 1
        [
            {"type": "LAYOUT_TEXT", "lines": ["First paragraph on page two."]},
            {"type": "LAYOUT_TITLE", "lines": ["Ignored Title."]},
            {"type": "LAYOUT_TEXT", "lines": ["Second paragraph on page two."]},
        ],  # Page 2
    ]

    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory(page_count=2)

    extractor = ChunkExtractor()
    actual_chunks: list[OpenSearchChunk] = extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 3
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchChunk)

    assert chunk1.chunk_text == "Content on the first page."
    assert chunk1.page_number == 1
    assert chunk1.source_file_name == "test_ingested_document.pdf"
    assert chunk1.page_count == 2
    assert chunk1.chunk_index == 0

    chunk2 = actual_chunks[1]
    assert isinstance(chunk2, OpenSearchChunk)
    assert chunk2.chunk_text == "First paragraph on page two."
    assert chunk2.page_number == 2
    assert chunk2.source_file_name == "test_ingested_document.pdf"
    assert chunk2.page_count == 2
    assert chunk2.chunk_index == 1  # TODO should each page have its own chunk index?

    chunk3 = actual_chunks[2]
    assert isinstance(chunk3, OpenSearchChunk)
    assert chunk3.chunk_text == "Second paragraph on page two."
    assert chunk3.page_number == 2
    assert chunk3.source_file_name == "test_ingested_document.pdf"
    assert chunk3.page_count == 2
    assert chunk3.chunk_index == 2


def test_page_with_layout_text_with_mutliple_lines(document_metadata_factory):
    document_definition = [
        [
            {
                "type": "LAYOUT_TEXT",
                "lines": [
                    "First line on paragraph one ",
                    "Second line on paragraph one ",
                    "Third line on paragraph one ",
                ],
            },
            {"type": "LAYOUT_TEXT", "lines": ["First line on paragraph two."]},
            {"type": "LAYOUT_TEXT", "lines": ["First line on paragraph three.", "Second line on paragraph three."]},
        ],  # Page 1
    ]

    mock_doc = textractor_document_factory(document_definition)
    mock_metadata = document_metadata_factory()
    extractor = ChunkExtractor()
    actual_chunks: list[OpenSearchChunk] = extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 3
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchChunk)

    assert chunk1.chunk_text == "First line on paragraph one Second line on paragraph one Third line on paragraph one"
    assert chunk1.page_number == 1
    assert chunk1.source_file_name == "test_ingested_document.pdf"
    assert chunk1.page_count == 1
    assert chunk1.chunk_index == 0

    chunk2 = actual_chunks[1]
    assert isinstance(chunk2, OpenSearchChunk)
    assert chunk2.chunk_text == "First line on paragraph two."
    assert chunk2.page_number == 1
    assert chunk2.source_file_name == "test_ingested_document.pdf"
    assert chunk2.page_count == 1
    assert chunk2.chunk_index == 1

    chunk3 = actual_chunks[2]
    assert isinstance(chunk3, OpenSearchChunk)
    assert chunk3.chunk_text == "First line on paragraph three. Second line on paragraph three."
    assert chunk3.page_number == 1
    assert chunk3.source_file_name == "test_ingested_document.pdf"
    assert chunk3.page_count == 1
    assert chunk3.chunk_index == 2


def test_multiple_layout_text_blocks_on_single_page(document_metadata_factory):
    """
    Tests that multiple LAYOUT_TEXT blocks on the same page are extracted as
    separate chunks with correctly incrementing chunk indices.
    """
    # Arrange
    document_definition = [
        [  # Page 1
            {"type": "LAYOUT_TEXT", "lines": ["This is the first paragraph."]},
            {"type": "LAYOUT_TITLE", "lines": ["An Ignored Title"]},
            {"type": "LAYOUT_TEXT", "lines": ["This is the second paragraph."]},
        ]
    ]
    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory()
    extractor = ChunkExtractor()
    actual_chunks: list[OpenSearchChunk] = extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 2, "Should create two chunks from the two LAYOUT_TEXT blocks"
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchChunk)

    # Check first chunk
    assert chunk1.chunk_text == "This is the first paragraph."
    assert chunk1.page_number == 1
    assert chunk1.chunk_index == 0
    assert chunk1.chunk_id == "unique_ingested_doc_UUID_p1_c0"

    # Check second chunk
    chunk2 = actual_chunks[1]
    assert isinstance(chunk2, OpenSearchChunk)
    assert chunk2.chunk_text == "This is the second paragraph."
    assert chunk2.page_number == 1
    assert chunk2.chunk_index == 1
    assert chunk2.chunk_id == "unique_ingested_doc_UUID_p1_c1"


def test_page_with_no_layout_text_blocks_is_skipped(document_metadata_factory):
    """
    Tests that a page containing no LAYOUT_TEXT blocks is skipped, and processing
    continues on subsequent pages, with the chunk index incrementing correctly.
    """
    # Arrange
    document_definition = [
        [{"type": "LAYOUT_TEXT", "lines": ["Content on page one."]}],  # Page 1
        [{"type": "LAYOUT_TITLE", "lines": ["Page 2 has no text blocks."]}],  # Page 2 (should be skipped)
        [{"type": "LAYOUT_TEXT", "lines": ["Content on page three."]}],  # Page 3
    ]
    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory(page_count=3)
    extractor = ChunkExtractor()
    actual_chunks: list[OpenSearchChunk] = extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 2, "Should create two chunks from the two LAYOUT_TEXT blocks"

    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchChunk)

    # Check first chunk from Page 1
    assert chunk1.chunk_text == "Content on page one."
    assert chunk1.page_number == 1
    assert chunk1.chunk_index == 0

    # Check second chunk from Page 3
    chunk2 = actual_chunks[1]
    assert isinstance(chunk1, OpenSearchChunk)
    assert chunk2.chunk_text == "Content on page three."
    assert chunk2.page_number == 3
    assert chunk2.chunk_index == 1, "Chunk index should continue from the previous valid chunk"


def test_ignores_non_text_layout_blocks(document_metadata_factory):
    """
    Tests that layout blocks of types other than LAYOUT_TEXT are ignored.
    """
    # Arrange
    document_definition = [
        [  # Page 1
            {"type": "LAYOUT_TITLE", "lines": ["A Document Title"]},
            {"type": "LAYOUT_HEADER", "lines": ["Page Header"]},
            {"type": "LAYOUT_TEXT", "lines": ["This is the only content to be chunked."]},
            {"type": "LAYOUT_FIGURE", "lines": ["A figure."]},
            {"type": "LAYOUT_TABLE", "lines": ["Some table data."]},
            {"type": "LAYOUT_FOOTER", "lines": ["Page Footer"]},
        ]
    ]
    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory()
    extractor = ChunkExtractor()
    actual_chunks: list[OpenSearchChunk] = extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    # Assert
    assert len(actual_chunks) == 1

    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchChunk)

    assert chunk1.chunk_text == "This is the only content to be chunked."
    assert chunk1.chunk_type == "LAYOUT_TEXT"


def test_empty_or_whitespace_layout_text_block_is_ignored(document_metadata_factory):
    """
    Tests that LAYOUT_TEXT blocks containing no text or only whitespace are ignored
    and not created as chunks.
    """
    # Arrange
    document_definition = [
        [  # Page 1
            {"type": "LAYOUT_TEXT", "lines": ["This is a valid chunk."]},
            {"type": "LAYOUT_TEXT", "lines": ["   \t\n   "]},  # Whitespace only
            {"type": "LAYOUT_TEXT", "lines": []},  # Empty lines array
            {"type": "LAYOUT_TEXT", "lines": ["Another valid chunk."]},
        ]
    ]
    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory()
    extractor = ChunkExtractor()
    actual_chunks: list[OpenSearchChunk] = extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 2, "Should ignore empty and whitespace-only blocks"
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchChunk)
    assert chunk1.chunk_text == "This is a valid chunk."
    assert chunk1.chunk_index == 0
    chunk2 = actual_chunks[1]
    assert isinstance(chunk2, OpenSearchChunk)
    assert chunk2.chunk_text == "Another valid chunk."
    assert chunk2.chunk_index == 1


def test_handles_missing_pdf_id_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function throws an error when required metadata is missing.
    """
    # Act & Assert
    with pytest.raises(ValueError, match="DocumentMetadata string fields cannot be empty"):
        document_metadata_factory(ingested_doc_id="")


def test_handles_missing_source_file_name_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """

    with pytest.raises(ValueError, match="DocumentMetadata string fields cannot be empty."):
        document_metadata_factory(source_file_name="")


def test_handles_zero_page_count_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """

    with pytest.raises(ValueError, match="DocumentMetadata.page_count must be a positive integer."):
        document_metadata_factory(page_count=0)


def test_handles_negative_page_count_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """

    with pytest.raises(ValueError, match="DocumentMetadata.page_count must be a positive integer."):
        document_metadata_factory(page_count=-7)


def test_empty_document_throws_error(document_metadata_factory):
    """
    Tests that an empty Textract Document raises an Exception.
    """
    mock_doc = Document()
    mock_metadata = document_metadata_factory()
    extractor = ChunkExtractor()
    with pytest.raises(Exception, match="Document cannot be None and must contain pages."):
        extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)


def create_long_line_data(num_lines: int, line_length: int = 100) -> list[dict]:
    """Helper to create a layout block with many long lines."""
    line_text = "a" * (line_length - 1) + " "
    lines = [{"text": line_text, "bbox": BoundingBox(0.1, 0.1, 0.8, 0.01)} for _ in range(num_lines)]
    return [{"type": "LAYOUT_TEXT", "lines": lines}]


def test_single_layout_block_splits_into_multiple_chunks_by_line_count(document_metadata_factory):
    """
    Tests that a single LAYOUT_TEXT block with many lines exceeding the
    maximum_chunk_size is correctly split into multiple chunks, with
    correct chunk text and index.
    """
    # Create a document with one block containing lines that exceed the max size
    line_length = 5  # Two lines will fit, three won't
    line_one_text = "a" * 4
    line_two_text = "b" * line_length
    line_three_text = "c" * line_length

    document_definition = [
        [
            {
                "type": "LAYOUT_TEXT",
                "lines": [
                    {"text": line_one_text, "bbox": BoundingBox(0.1, 0.1, 0.8, 0.01)},
                    {"text": line_two_text, "bbox": BoundingBox(0.1, 0.2, 0.8, 0.01)},
                    {"text": line_three_text, "bbox": BoundingBox(0.1, 0.3, 0.8, 0.01)},
                ],
            }
        ]
    ]

    mock_doc = textractor_document_factory(document_definition)
    mock_metadata = document_metadata_factory()

    # Set the maximum_chunk_size to 10 for this test
    chunking_config = ChunkingConfig(maximum_chunk_size=10, strategy=ChunkingStrategy.LINE_BASED)
    extractor = ChunkExtractor(chunking_config)
    actual_chunks: list[OpenSearchChunk] = extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    # Assert
    assert len(actual_chunks) == 2, "Expected two chunks to be created"

    # Check first chunk
    chunk1 = actual_chunks[0]
    expected_text1 = f"{line_one_text} {line_two_text}"
    assert chunk1.chunk_text == expected_text1.strip()
    assert chunk1.chunk_index == 0
    assert chunk1.bounding_box is not None
    # Verify the combined bounding box logic for the first chunk
    assert chunk1.bounding_box.left == pytest.approx(0.1)
    assert chunk1.bounding_box.top == pytest.approx(0.1)
    assert chunk1.bounding_box.width == pytest.approx(0.8)
    assert chunk1.bounding_box.height == pytest.approx(0.11)

    # Check second chunk
    chunk2 = actual_chunks[1]
    expected_text2 = line_three_text
    assert chunk2.chunk_text == expected_text2.strip()
    assert chunk2.chunk_index == 1
    assert chunk2.bounding_box is not None
    # Verify the bounding box for the second chunk (a single line)
    # It should match the line's bbox exactly
    assert chunk2.bounding_box.left == pytest.approx(0.1)
    assert chunk2.bounding_box.top == pytest.approx(0.3)
    assert chunk2.bounding_box.width == pytest.approx(0.8)
    assert chunk2.bounding_box.height == pytest.approx(0.01)


def test_chunk_splitting_handles_exact_size_limit(document_metadata_factory):
    """
    Tests the edge case where the combined text size is exactly the
    maximum_chunk_size, ensuring the next line triggers a new chunk.
    """

    # The first line's length is precisely calculated to make the first chunk
    # exactly the maximum size, causing the split on the next line.
    maximum_chunk_size = 10
    line1_text = "a" * (maximum_chunk_size)
    line2_text = "b"

    document_definition = [
        [
            {
                "type": "LAYOUT_TEXT",
                "lines": [
                    {"text": line1_text, "bbox": BoundingBox(0.1, 0.1, 0.8, 0.01)},
                    {"text": line2_text, "bbox": BoundingBox(0.1, 0.2, 0.8, 0.01)},
                ],
            }
        ]
    ]

    mock_doc = textractor_document_factory(document_definition)
    mock_metadata = document_metadata_factory()

    # Set the maximum_chunk_size to 10 for this test
    chunking_config = ChunkingConfig(maximum_chunk_size, strategy=ChunkingStrategy.LINE_BASED)
    extractor = ChunkExtractor(chunking_config)
    actual_chunks: list[OpenSearchChunk] = extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 2, "Chunk should be split into two"
    assert actual_chunks[0].chunk_text.strip() == line1_text.strip()
    assert actual_chunks[1].chunk_text.strip() == line2_text.strip()
    assert actual_chunks[0].chunk_index == 0
    assert actual_chunks[1].chunk_index == 1


def test_multiple_long_layout_blocks_are_all_split(document_metadata_factory):
    """
    Tests that multiple layout blocks, each requiring splitting, are handled correctly
    and create a sequence of new chunks.
    """
    maximum_chunk_size = 10
    long_lines_1 = create_long_line_data(3, line_length=4)  # Two chunks from this block
    long_lines_2 = create_long_line_data(3, line_length=4)  # Two more chunks from this block

    document_definition = [
        [
            {"type": "LAYOUT_TEXT", "lines": long_lines_1[0]["lines"]},
            {"type": "LAYOUT_TEXT", "lines": long_lines_2[0]["lines"]},
        ]
    ]

    mock_doc = textractor_document_factory(document_definition)
    mock_metadata = document_metadata_factory()
    # Set the maximum_chunk_size to 10 for this test
    chunking_config = ChunkingConfig(maximum_chunk_size, strategy=ChunkingStrategy.LINE_BASED)
    extractor = ChunkExtractor(chunking_config)
    actual_chunks: list[OpenSearchChunk] = extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 4, "Expected a total of four chunks"
    assert actual_chunks[0].chunk_index == 0
    assert actual_chunks[1].chunk_index == 1
    assert actual_chunks[2].chunk_index == 2
    assert actual_chunks[3].chunk_index == 3


def test_bounding_box_is_correctly_combined_for_split_chunks(document_metadata_factory):
    """
    Tests that when a chunk is split, the bounding box for each new chunk is
    correctly calculated by combining the bounding boxes of the lines it contains.
    """
    # Arrange
    line_1_bbox = BoundingBox(x=0.1, y=0.1, width=0.7, height=0.02)
    line_2_bbox = BoundingBox(x=0.2, y=0.15, width=0.6, height=0.03)
    line_3_bbox = BoundingBox(x=0.3, y=0.2, width=0.5, height=0.04)

    line1_text = "a" * 400
    line2_text = "b" * 400
    line3_text = "c" * 400

    document_definition = [
        [
            {
                "type": "LAYOUT_TEXT",
                "lines": [
                    {"text": line1_text, "bbox": line_1_bbox},
                    {"text": line2_text, "bbox": line_2_bbox},
                    {"text": line3_text, "bbox": line_3_bbox},
                ],
            }
        ]
    ]
    mock_doc = textractor_document_factory(document_definition)
    mock_metadata = document_metadata_factory()
    extractor = ChunkExtractor()
    actual_chunks: list[OpenSearchChunk] = extractor.extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    # Assert
    assert len(actual_chunks) == 2, "Expected the block to be split"

    # Verify the first chunk's bounding box
    chunk1_bbox = actual_chunks[0].bounding_box
    assert chunk1_bbox is not None
    assert chunk1_bbox.left == min(line_1_bbox.x, line_2_bbox.x)
    assert chunk1_bbox.top == min(line_1_bbox.y, line_2_bbox.y)
    assert chunk1_bbox.width == (
        max(line_1_bbox.x + line_1_bbox.width, line_2_bbox.x + line_2_bbox.width) - min(line_1_bbox.x, line_2_bbox.x)
    )
    assert chunk1_bbox.height == (
        max(line_1_bbox.y + line_1_bbox.height, line_2_bbox.y + line_2_bbox.height) - min(line_1_bbox.y, line_2_bbox.y)
    )

    # Verify the second chunk's bounding box (single line)
    chunk2_bbox = actual_chunks[1].bounding_box
    assert chunk2_bbox is not None
    assert chunk2_bbox.left == pytest.approx(line_3_bbox.x)
    assert chunk2_bbox.top == pytest.approx(line_3_bbox.y)
    assert chunk2_bbox.width == pytest.approx(line_3_bbox.width)
    assert chunk2_bbox.height == pytest.approx(line_3_bbox.height)
