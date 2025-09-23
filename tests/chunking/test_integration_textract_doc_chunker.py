import json
from datetime import date
from pathlib import Path
from typing import Optional

import pytest
from pydantic import ValidationError
from textractor.entities.bbox import BoundingBox
from textractor.entities.document import Document

from src.chunking.chunking_config import ChunkingConfig, ChunkingStrategy
from src.chunking.schemas import DocumentBoundingBox, DocumentMetadata
from src.chunking.strategies.layout_text import LayoutTextChunkingStrategy
from src.chunking.strategies.table import LayoutTableChunkingStrategy
from src.chunking.textract import (
    OpenSearchDocument,
    TextractDocumentChunker,
)

from .test_utils.textract_response_builder import textractor_document_factory

TEXTRACT_JSON_PATH = Path(__file__).parent / "data" / "single_text_layout_textract_response.json"


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


@pytest.fixture
def document_chunker_factory():
    """
    This fixture returns a FACTORY function that can create a
    fully-wired TextractDocumentChunker instance.

    This allows tests to create a chunker with a custom config.
    """

    def _factory(config: Optional[ChunkingConfig] = None) -> TextractDocumentChunker:
        # If no config is provided by the test, use the default one.
        if config is None:
            config = ChunkingConfig()

        layout_text_strategy = LayoutTextChunkingStrategy(config)
        layout_table_strategy = LayoutTableChunkingStrategy(config)

        strategy_handlers = {
            "LAYOUT_TEXT": layout_text_strategy,
            "LAYOUT_TABLE": layout_table_strategy,
        }

        return TextractDocumentChunker(
            strategy_handlers=strategy_handlers,
            config=config,
        )

    return _factory


def test_extract_single_layout_chunk_from_actual_textract_response(
    document_chunker_factory, textract_response, document_metadata_factory
):
    """
    Tests that a single LAYOUT_TEXT block is correctly processed
    into an OpenSearch chunk document.
    This is test using an actutal Textract response.
    """

    mock_doc = Document.open(textract_response)

    mock_metadata = document_metadata_factory()

    actual_chunks: list[OpenSearchDocument] = document_chunker_factory().chunk(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 1
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchDocument)

    expected_text = (
        "We have discussed with our patient, who has requested we release all medical records from the "
        "date of the incident, from birth. Please find these attached."
    )

    chunk1.chunk_id = "unique_ingested_doc_UUID_p1_c0"
    chunk1.ingested_doc_id = "unique_ingested_doc_UUID"
    chunk1.source_file_name = "document_single_layout_response.pdf"
    chunk1.chunk_text = expected_text
    chunk1.embedding = None  # Metadata to be added later
    chunk1.case_ref = None
    chunk1.received_date = None
    chunk1.correspondence_type = None
    chunk1.page_count = 1
    chunk1.page_number = 1
    chunk1.chunk_index = 0
    chunk1.chunk_type = "LAYOUT_TEXT"
    chunk1.confidence = 0.60009765625
    chunk1.bounding_box = DocumentBoundingBox(
        Width=0.7254804372787476,
        Height=0.02834956906735897,
        Left=0.12123029679059982,
        Top=0.4854643642902374,
    )


def test_multiple_pages_with_layout_text(document_chunker_factory, document_metadata_factory):
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

    actual_chunks: list[OpenSearchDocument] = document_chunker_factory().chunk(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 3
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchDocument)

    assert chunk1.chunk_text == "Content on the first page."
    assert chunk1.page_number == 1
    assert chunk1.source_file_name == "test_ingested_document.pdf"
    assert chunk1.page_count == 2
    assert chunk1.chunk_index == 0

    chunk2 = actual_chunks[1]
    assert isinstance(chunk2, OpenSearchDocument)
    assert chunk2.chunk_text == "First paragraph on page two."
    assert chunk2.page_number == 2
    assert chunk2.source_file_name == "test_ingested_document.pdf"
    assert chunk2.page_count == 2
    assert chunk2.chunk_index == 1  # TODO should each page have its own chunk index?

    chunk3 = actual_chunks[2]
    assert isinstance(chunk3, OpenSearchDocument)
    assert chunk3.chunk_text == "Second paragraph on page two."
    assert chunk3.page_number == 2
    assert chunk3.source_file_name == "test_ingested_document.pdf"
    assert chunk3.page_count == 2
    assert chunk3.chunk_index == 2


def test_page_with_layout_text_with_mutliple_lines(document_chunker_factory, document_metadata_factory):
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

    actual_chunks: list[OpenSearchDocument] = document_chunker_factory().chunk(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 3
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchDocument)

    assert chunk1.chunk_text == "First line on paragraph one Second line on paragraph one Third line on paragraph one"
    assert chunk1.page_number == 1
    assert chunk1.source_file_name == "test_ingested_document.pdf"
    assert chunk1.page_count == 1
    assert chunk1.chunk_index == 0

    chunk2 = actual_chunks[1]
    assert isinstance(chunk2, OpenSearchDocument)
    assert chunk2.chunk_text == "First line on paragraph two."
    assert chunk2.page_number == 1
    assert chunk2.source_file_name == "test_ingested_document.pdf"
    assert chunk2.page_count == 1
    assert chunk2.chunk_index == 1

    chunk3 = actual_chunks[2]
    assert isinstance(chunk3, OpenSearchDocument)
    assert chunk3.chunk_text == "First line on paragraph three. Second line on paragraph three."
    assert chunk3.page_number == 1
    assert chunk3.source_file_name == "test_ingested_document.pdf"
    assert chunk3.page_count == 1
    assert chunk3.chunk_index == 2


def test_multiple_layout_text_blocks_on_single_page(document_chunker_factory, document_metadata_factory):
    """
    Tests that multiple LAYOUT_TEXT blocks on the same page are extracted as
    separate chunks with correctly incrementing chunk indices.
    """

    document_definition = [
        [  # Page 1
            {"type": "LAYOUT_TEXT", "lines": ["This is the first paragraph."]},
            {"type": "LAYOUT_TITLE", "lines": ["An Ignored Title"]},
            {"type": "LAYOUT_TEXT", "lines": ["This is the second paragraph."]},
        ]
    ]
    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory()
    actual_chunks: list[OpenSearchDocument] = document_chunker_factory().chunk(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 2, "Should create two chunks from the two LAYOUT_TEXT blocks"
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchDocument)

    # Check first chunk
    assert chunk1.chunk_text == "This is the first paragraph."
    assert chunk1.page_number == 1
    assert chunk1.chunk_index == 0
    assert chunk1.chunk_id == "unique_ingested_doc_UUID_p1_c0"

    # Check second chunk
    chunk2 = actual_chunks[1]
    assert isinstance(chunk2, OpenSearchDocument)
    assert chunk2.chunk_text == "This is the second paragraph."
    assert chunk2.page_number == 1
    assert chunk2.chunk_index == 1
    assert chunk2.chunk_id == "unique_ingested_doc_UUID_p1_c1"


def test_page_with_no_layout_text_blocks_is_skipped(document_chunker_factory, document_metadata_factory):
    """
    Tests that a page containing no LAYOUT_TEXT blocks is skipped, and processing
    continues on subsequent pages, with the chunk index incrementing correctly.
    """

    document_definition = [
        [{"type": "LAYOUT_TEXT", "lines": ["Content on page one."]}],  # Page 1
        [{"type": "LAYOUT_TITLE", "lines": ["Page 2 has no text blocks."]}],  # Page 2 (should be skipped)
        [{"type": "LAYOUT_TEXT", "lines": ["Content on page three."]}],  # Page 3
    ]
    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory(page_count=3)

    actual_chunks: list[OpenSearchDocument] = document_chunker_factory().chunk(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 2, "Should create two chunks from the two LAYOUT_TEXT blocks"

    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchDocument)

    # Check first chunk from Page 1
    assert chunk1.chunk_text == "Content on page one."
    assert chunk1.page_number == 1
    assert chunk1.chunk_index == 0

    # Check second chunk from Page 3
    chunk2 = actual_chunks[1]
    assert isinstance(chunk1, OpenSearchDocument)
    assert chunk2.chunk_text == "Content on page three."
    assert chunk2.page_number == 3
    assert chunk2.chunk_index == 1, "Chunk index should continue from the previous valid chunk"


def test_empty_or_whitespace_layout_text_block_is_ignored(document_chunker_factory, document_metadata_factory):
    """
    Tests that LAYOUT_TEXT blocks containing no text or only whitespace are ignored
    and not created as chunks.
    """

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

    actual_chunks: list[OpenSearchDocument] = document_chunker_factory().chunk(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 2, "Should ignore empty and whitespace-only blocks"
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchDocument)
    assert chunk1.chunk_text == "This is a valid chunk."
    assert chunk1.chunk_index == 0
    chunk2 = actual_chunks[1]
    assert isinstance(chunk2, OpenSearchDocument)
    assert chunk2.chunk_text == "Another valid chunk."
    assert chunk2.chunk_index == 1


def test_handles_missing_pdf_id_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function throws an error when required metadata is missing.
    """

    with pytest.raises(ValidationError, match="String should have at least 1 character"):
        document_metadata_factory(ingested_doc_id="")


def test_handles_missing_source_file_name_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """

    with pytest.raises(ValidationError, match="String should have at least 1 character"):
        document_metadata_factory(source_file_name="")


def test_handles_zero_page_count_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """

    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        document_metadata_factory(page_count=0)


def test_handles_negative_page_count_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """

    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        document_metadata_factory(page_count=-7)


def test_empty_document_throws_error(document_chunker_factory, document_metadata_factory):
    """
    Tests that an empty Textract Document raises an Exception.
    """
    mock_doc = Document()
    mock_metadata = document_metadata_factory()

    with pytest.raises(Exception, match="Document cannot be None and must contain pages."):
        document_chunker_factory().chunk(doc=mock_doc, metadata=mock_metadata)


def create_long_line_data(num_lines: int, line_length: int = 100) -> list[dict]:
    """Helper to create a layout block with many long lines."""
    line_text = "a" * (line_length - 1) + " "
    lines = [{"text": line_text, "bbox": BoundingBox(0.1, 0.1, 0.8, 0.01)} for _ in range(num_lines)]
    return [{"type": "LAYOUT_TEXT", "lines": lines}]


def test_single_layout_block_splits_into_multiple_chunks_by_line_count(
    document_chunker_factory, document_metadata_factory
):
    """
    Tests that a single LAYOUT_TEXT block with many lines exceeding the
    maximum_chunk_size is correctly split into multiple chunks, with
    correct chunk text and index.
    """
    # Create a document with one block containing lines that exceed the max size
    # maximum_chunk_size will be set to 10 for this test
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

    # Set the maximum_chunk_size to 10 for this test
    chunking_config = ChunkingConfig(maximum_chunk_size=10, strategy=ChunkingStrategy.LAYOUT_TEXT)
    chunker = document_chunker_factory(chunking_config)
    mock_doc = textractor_document_factory(document_definition)
    mock_metadata = document_metadata_factory()

    actual_chunks: list[OpenSearchDocument] = chunker.chunk(doc=mock_doc, metadata=mock_metadata)

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


def test_chunk_splitting_handles_exact_size_limit(document_chunker_factory, document_metadata_factory):
    """
    Tests the edge case where the combined text size is exactly the
    maximum_chunk_size, ensuring the next line triggers a new chunk.
    """

    # The first line's length is precisely calculated to make the first chunk
    # exactly the maximum size, causing the split on the next line.
    # maximum_chunk_size set to 10 for this test
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
    chunking_config = ChunkingConfig(maximum_chunk_size, strategy=ChunkingStrategy.LAYOUT_TEXT)
    chunker = document_chunker_factory(chunking_config)
    actual_chunks: list[OpenSearchDocument] = chunker.chunk(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 2, "Chunk should be split into two"
    assert actual_chunks[0].chunk_text.strip() == line1_text.strip()
    assert actual_chunks[1].chunk_text.strip() == line2_text.strip()
    assert actual_chunks[0].chunk_index == 0
    assert actual_chunks[1].chunk_index == 1


def test_multiple_long_layout_blocks_are_all_split(document_chunker_factory, document_metadata_factory):
    """
    Tests that multiple layout blocks, each requiring splitting, are handled correctly
    and create a sequence of new chunks.
    """
    # Set the maximum_chunk_size to 10 for this test
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

    chunking_config = ChunkingConfig(maximum_chunk_size, strategy=ChunkingStrategy.LAYOUT_TEXT)
    chunker = document_chunker_factory(chunking_config)
    actual_chunks: list[OpenSearchDocument] = chunker.chunk(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 4, "Expected a total of four chunks"
    assert actual_chunks[0].chunk_index == 0
    assert actual_chunks[1].chunk_index == 1
    assert actual_chunks[2].chunk_index == 2
    assert actual_chunks[3].chunk_index == 3


def test_bounding_box_is_correctly_combined_for_split_chunks(document_chunker_factory, document_metadata_factory):
    """
    Tests that when a chunk is split, the bounding box for each new chunk is
    correctly calculated by combining the bounding boxes of the lines it contains.
    """
    # Set the maximum_chunk_size to 1000 for this test
    maximum_chunk_size = 1000
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
    chunking_config = ChunkingConfig(maximum_chunk_size, strategy=ChunkingStrategy.LAYOUT_TEXT)
    chunker = document_chunker_factory(chunking_config)

    actual_chunks: list[OpenSearchDocument] = chunker.chunk(doc=mock_doc, metadata=mock_metadata)

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
