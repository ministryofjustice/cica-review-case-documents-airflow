import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest
from textractor.entities.document import Document

from chunk_handler.chunk_extractor import (
    DocumentMetadata,
    OpenSearchChunk,
    extract_layout_chunks,
)
from chunk_handler.tests.utils.textract_response_builder import textractor_document_factory
from data_models.chunk_models import BoundingBoxDict

# Define the path to our test data
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
            "s3_page_image_uri": f"s3://kta-document-images-bucket/{case_ref}/unique_ingested_doc_UUID",
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


def test_extract_single_layout_chunk(textract_response, document_metadata_factory):
    """
    Tests that a single LAYOUT_TEXT block is correctly processed
    into an OpenSearch chunk document.
    This is test usign an actutal Textract response.
    """

    doc = Document.open(textract_response)

    # Call the factory, providing overrides for this specific test case
    mock_metadata = document_metadata_factory()

    actual_chunks: list[OpenSearchChunk] = extract_layout_chunks(doc=doc, metadata=mock_metadata)

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
        Width=0.7254804372787476,
        Height=0.02834956906735897,
        Left=0.12123029679059982,
        Top=0.4854643642902374,
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
        Width=mock_bbox.width,
        Height=mock_bbox.height,
        Left=mock_bbox.x,
        Top=mock_bbox.y,
    )

    mock_metadata = document_metadata_factory(
        s3_page_image_uri="s3://kta-document-images-bucket/25-787878/unique_ingested_doc_UUID/page_5.png",
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
    assert chunk.s3_page_image_uri == "s3://kta-document-images-bucket/25-787878/unique_ingested_doc_UUID/page_5.png"
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

    actual_chunks: list[OpenSearchChunk] = extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 3
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchChunk)

    assert chunk1.chunk_text == "Content on the first page."
    assert chunk1.page_number == 1
    assert chunk1.source_file_name == "test_ingested_document.pdf"
    assert chunk1.page_count == 2
    assert chunk1.chunk_index == 0
    assert chunk1.s3_page_image_uri == "s3://kta-document-images-bucket/25-787878/unique_ingested_doc_UUID/page_1.png"

    chunk2 = actual_chunks[1]
    assert isinstance(chunk2, OpenSearchChunk)
    assert chunk2.chunk_text == "First paragraph on page two."
    assert chunk2.page_number == 2
    assert chunk2.source_file_name == "test_ingested_document.pdf"
    assert chunk2.page_count == 2
    assert chunk2.chunk_index == 1  # TODO should each page have its own chunk index?
    assert chunk2.s3_page_image_uri == "s3://kta-document-images-bucket/25-787878/unique_ingested_doc_UUID/page_2.png"

    chunk3 = actual_chunks[2]
    assert isinstance(chunk3, OpenSearchChunk)
    assert chunk3.chunk_text == "Second paragraph on page two."
    assert chunk3.page_number == 2
    assert chunk3.source_file_name == "test_ingested_document.pdf"
    assert chunk3.page_count == 2
    assert chunk3.chunk_index == 2
    assert chunk3.s3_page_image_uri == "s3://kta-document-images-bucket/25-787878/unique_ingested_doc_UUID/page_2.png"


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

    actual_chunks: list[OpenSearchChunk] = extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

    assert len(actual_chunks) == 3
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, OpenSearchChunk)

    assert chunk1.chunk_text == "First line on paragraph one Second line on paragraph one Third line on paragraph one"
    assert chunk1.page_number == 1
    assert chunk1.source_file_name == "test_ingested_document.pdf"
    assert chunk1.page_count == 1
    assert chunk1.chunk_index == 0
    assert chunk1.s3_page_image_uri == "s3://kta-document-images-bucket/25-787878/unique_ingested_doc_UUID/page_1.png"

    chunk2 = actual_chunks[1]
    assert isinstance(chunk2, OpenSearchChunk)
    assert chunk2.chunk_text == "First line on paragraph two."
    assert chunk2.page_number == 1
    assert chunk2.source_file_name == "test_ingested_document.pdf"
    assert chunk2.page_count == 1
    assert chunk2.chunk_index == 1
    assert chunk2.s3_page_image_uri == "s3://kta-document-images-bucket/25-787878/unique_ingested_doc_UUID/page_1.png"

    chunk3 = actual_chunks[2]
    assert isinstance(chunk3, OpenSearchChunk)
    assert chunk3.chunk_text == "First line on paragraph three. Second line on paragraph three."
    assert chunk3.page_number == 1
    assert chunk3.source_file_name == "test_ingested_document.pdf"
    assert chunk3.page_count == 1
    assert chunk3.chunk_index == 2
    assert chunk3.s3_page_image_uri == "s3://kta-document-images-bucket/25-787878/unique_ingested_doc_UUID/page_1.png"


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

    actual_chunks: list[OpenSearchChunk] = extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

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

    actual_chunks: list[OpenSearchChunk] = extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

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

    actual_chunks: list[OpenSearchChunk] = extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

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

    actual_chunks: list[OpenSearchChunk] = extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)

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
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """
    # Arrange
    document_definition = [[{"type": "LAYOUT_TEXT", "lines": ["Simple content."]}]]
    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory(ingested_doc_id="")

    with pytest.raises(ValueError) as chunkingError:
        extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)
    assert str(chunkingError.value) == "DocumentMetadata cannot be None and its string fields cannot be empty."


def test_handles_missing_s3_page_image_uri_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """
    # Arrange
    document_definition = [[{"type": "LAYOUT_TEXT", "lines": ["Simple content."]}]]
    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory(s3_page_image_uri="")

    with pytest.raises(ValueError) as chunkingError:
        extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)
    assert str(chunkingError.value) == "DocumentMetadata cannot be None and its string fields cannot be empty."


def test_handles_missing_source_file_name_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """
    # Arrange
    document_definition = [[{"type": "LAYOUT_TEXT", "lines": ["Simple content."]}]]
    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory(source_file_name="")

    with pytest.raises(ValueError) as chunkingError:
        extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)
    assert str(chunkingError.value) == "DocumentMetadata cannot be None and its string fields cannot be empty."


def test_handles_zero_page_count_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """
    # Arrange
    document_definition = [[{"type": "LAYOUT_TEXT", "lines": ["Simple content."]}]]
    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory(page_count=0)

    with pytest.raises(ValueError) as chunkingError:
        extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)
    assert str(chunkingError.value) == "DocumentMetadata.page_count must be a positive integer."


def test_handles_negative_page_count_metadata_throws_error(document_metadata_factory):
    """
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """
    # Arrange
    document_definition = [[{"type": "LAYOUT_TEXT", "lines": ["Simple content."]}]]
    mock_doc = textractor_document_factory(document_definition)

    mock_metadata = document_metadata_factory(page_count=-7)

    with pytest.raises(ValueError) as chunkingError:
        extract_layout_chunks(doc=mock_doc, metadata=mock_metadata)
    assert str(chunkingError.value) == "DocumentMetadata.page_count must be a positive integer."


# Given layout text is greater than max chunk size
# the layout text should be split into multiple chunks.
# The split should be at complete lines
