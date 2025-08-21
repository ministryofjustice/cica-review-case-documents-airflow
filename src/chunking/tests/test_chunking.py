import json
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest
from textractor.entities.document import Document

from chunking.chunker import _create_opensearch_chunk, extract_layout_chunks
from chunking.tests.utils.textract_response_builder import textractor_document_factory

# Define the path to our test data
TEXTRACT_JSON_PATH = Path(__file__).parent / "data" / "single_text_layout_textract_response.json"


def test_create_opensearch_chunk_formats_correctly():
    # Arrange
    mock_block = MagicMock()
    type(mock_block).text = PropertyMock(return_value="  Some text.  ")
    type(mock_block).layout_type = PropertyMock(return_value="LAYOUT_TEXT")
    type(mock_block).confidence = PropertyMock(return_value=0.95)
    # Mock the bbox object and its properties
    mock_bbox = MagicMock()
    type(mock_bbox).width = PropertyMock(return_value=0.1)
    # ... set height, x, y
    type(mock_block).bbox = PropertyMock(return_value=mock_bbox)

    mock_page = MagicMock()
    type(mock_page).page_num = PropertyMock(return_value=5)

    # Act
    chunk = _create_opensearch_chunk(
        block=mock_block,
        page=mock_page,
        ingested_doc_id="unique-UUID",  # Use a unique generated ID for the scanned pdf
        chunk_index=3,
        page_count=10,
        s3_page_image_uri="s3://test-kta-document-images/25-787878/unique-UUID/page_5.png",
        file_name="test_file.pdf",
    )

    # Assert
    assert chunk["chunk_id"] == "unique-UUID_p5_c3"
    assert chunk["chunk_text"] == "Some text."  # Test the .strip()
    assert chunk["page_number"] == 5
    assert chunk["chunk_index"] == 3
    assert chunk["ingested_doc_id"] == "unique-UUID"
    assert chunk["confidence"] == 0.95
    assert chunk["bounding_box"] == {
        "Width": 0.1,
        "Height": mock_bbox.height,
        "Left": mock_bbox.x,
        "Top": mock_bbox.y,
    }
    assert chunk["source_file_name"] == "test_file.pdf"
    assert chunk["s3_page_image_uri"] == "s3://test-kta-document-images/25-787878/unique-UUID/page_5.png"
    assert chunk["embedding"] is None
    assert chunk["case_ref"] is None
    assert chunk["received_date"] is None
    assert chunk["correspondence_type"] is None
    assert chunk["page_count"] == 10
    assert chunk["chunk_type"] == "LAYOUT_TEXT"


def test_multiple_pages_with_layout_text():
    document_definition = [
        [{"type": "LAYOUT_TEXT", "lines": ["Content on the first page."]}],  # Page 1
        [
            {"type": "LAYOUT_TEXT", "lines": ["First paragraph on page two."]},
            {"type": "LAYOUT_TITLE", "lines": ["Ignored Title."]},
            {"type": "LAYOUT_TEXT", "lines": ["Second paragraph on page two."]},
        ],  # Page 2
    ]

    mock_doc = textractor_document_factory(document_definition)

    mock_uploaded_filename = "test_document_multipage.pdf"
    mock_page_count = len(mock_doc.pages)  # Get the page count from our mock object

    actual_chunks = extract_layout_chunks(
        doc=mock_doc,
        ingested_doc_id="doc-final-test",
        s3_image_uri_prefix="s3://my-bucket/doc-final-test",
        uploaded_file_name=mock_uploaded_filename,
        page_count=mock_page_count,
    )

    assert len(actual_chunks) == 3

    assert actual_chunks[0]["page_number"] == 1
    assert actual_chunks[0]["source_file_name"] == "test_document_multipage.pdf"
    assert actual_chunks[0]["page_count"] == 2

    assert actual_chunks[1]["page_number"] == 2
    assert actual_chunks[1]["source_file_name"] == "test_document_multipage.pdf"
    assert actual_chunks[1]["page_count"] == 2


def test_page_with_layout_text_with_mutliple_lines():
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

    mock_uploaded_filename = "test_document_multipage.pdf"
    mock_page_count = len(mock_doc.pages)  # Get the page count from our mock object

    actual_chunks = extract_layout_chunks(
        doc=mock_doc,
        ingested_doc_id="doc-final-test",
        s3_image_uri_prefix="s3://my-bucket/doc-final-test",
        uploaded_file_name=mock_uploaded_filename,
        page_count=mock_page_count,
    )

    assert len(actual_chunks) == 3

    assert actual_chunks[0]["page_number"] == 1
    assert actual_chunks[0]["source_file_name"] == "test_document_multipage.pdf"
    assert actual_chunks[0]["page_count"] == 1
    assert (
        actual_chunks[0]["chunk_text"]
        == "First line on paragraph one Second line on paragraph one Third line on paragraph one"
    ), "The generated chunk does not match the expected output"

    assert actual_chunks[1]["page_number"] == 1
    assert actual_chunks[1]["source_file_name"] == "test_document_multipage.pdf"
    assert actual_chunks[1]["page_count"] == 1
    assert actual_chunks[1]["chunk_text"] == "First line on paragraph two.", (
        "The generated chunk does not match the expected output"
    )

    assert actual_chunks[2]["page_number"] == 1
    assert actual_chunks[2]["source_file_name"] == "test_document_multipage.pdf"
    assert actual_chunks[2]["page_count"] == 1
    assert actual_chunks[2]["chunk_text"] == "First line on paragraph three. Second line on paragraph three.", (
        "The generated chunk does not match the expected output"
    )


@pytest.fixture
def textract_response():
    """Loads the sample Textract JSON response from a file."""
    with open(TEXTRACT_JSON_PATH, "r") as f:
        return json.load(f)


def test_extract_single_layout_chunk(textract_response):
    """
    Tests that a single LAYOUT_TEXT block is correctly processed
    into an OpenSearch chunk document.
    """
    ingested_doc_id = "unique-UUID"
    s3_image_uri_prefix = "s3://case-kta-document-images-bucket/25-787878/unique-UUID_page/page_1.png"

    doc = Document.open(textract_response)

    actual_chunks = extract_layout_chunks(
        doc,
        ingested_doc_id,
        s3_image_uri_prefix,
        uploaded_file_name="document_single_layout_response.pdf",
        page_count=1,
    )

    expected_text = (
        "We have discussed with our patient, who has requested we release all medical records from the "
        "date of the incident, from birth. Please find these attached."
    )

    expected_chunk = {
        "chunk_id": "unique-UUID_p1_c0",
        "ingested_doc_id": "unique-UUID",
        "chunk_text": expected_text,
        "embedding": None,  # We will handle embedding later
        "case_ref": None,  # Metadata to be added later
        "received_date": None,  # Metadata to be added later
        "source_file_name": "document_single_layout_response.pdf",
        "s3_page_image_uri": "s3://case-kta-document-images-bucket/25-787878/unique-UUID_page/page_1.png",
        "correspondence_type": None,  # Metadata to be added later
        "page_count": 1,
        "page_number": 1,
        "chunk_index": 0,
        "chunk_type": "LAYOUT_TEXT",
        "confidence": 0.60009765625,  # From the LAYOUT_TEXT block as a fraction of 1 ie. ~60%
        "bounding_box": {
            "Width": 0.7254804372787476,
            "Height": 0.02834956906735897,
            "Left": 0.12123029679059982,
            "Top": 0.4854643642902374,
        },
    }

    # --- Assertions ---
    assert isinstance(actual_chunks, list), "Function should return a list"
    assert len(actual_chunks) == 1, "There should be exactly one layout chunk"
    assert actual_chunks[0] == expected_chunk, "The generated chunk does not match the expected output"


def test_multiple_layout_text_blocks_on_single_page():
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

    # Act
    actual_chunks = extract_layout_chunks(
        doc=mock_doc,
        ingested_doc_id="multi-chunk-doc",
        s3_image_uri_prefix="s3://my-bucket/multi-chunk-doc",
        uploaded_file_name="multi_chunk.pdf",
        page_count=1,
    )

    # Assert
    assert len(actual_chunks) == 2, "Should create two chunks from the two LAYOUT_TEXT blocks"

    # Check first chunk
    assert actual_chunks[0]["chunk_text"] == "This is the first paragraph."
    assert actual_chunks[0]["page_number"] == 1
    assert actual_chunks[0]["chunk_index"] == 0
    assert actual_chunks[0]["chunk_id"] == "multi-chunk-doc_p1_c0"

    # Check second chunk
    assert actual_chunks[1]["chunk_text"] == "This is the second paragraph."
    assert actual_chunks[1]["page_number"] == 1
    assert actual_chunks[1]["chunk_index"] == 1
    assert actual_chunks[1]["chunk_id"] == "multi-chunk-doc_p1_c1"


def test_page_with_no_layout_text_blocks_is_skipped():
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

    # Act
    actual_chunks = extract_layout_chunks(
        doc=mock_doc,
        ingested_doc_id="skip-page-doc",
        s3_image_uri_prefix="s3://my-bucket/skip-page-doc",
        uploaded_file_name="skip_page.pdf",
        page_count=3,
    )

    # Assert
    assert len(actual_chunks) == 2, "Should only find chunks on pages 1 and 3"

    # Check first chunk from Page 1
    assert actual_chunks[0]["chunk_text"] == "Content on page one."
    assert actual_chunks[0]["page_number"] == 1
    assert actual_chunks[0]["chunk_index"] == 0

    # Check second chunk from Page 3
    assert actual_chunks[1]["chunk_text"] == "Content on page three."
    assert actual_chunks[1]["page_number"] == 3
    assert actual_chunks[1]["chunk_index"] == 1, "Chunk index should continue from the previous valid chunk"


def test_ignores_non_text_layout_blocks():
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

    # Act
    actual_chunks = extract_layout_chunks(
        doc=mock_doc,
        ingested_doc_id="ignore-types-doc",
        s3_image_uri_prefix="s3://my-bucket/ignore-types-doc",
        uploaded_file_name="ignore_types.pdf",
        page_count=1,
    )

    # Assert
    assert len(actual_chunks) == 1
    assert actual_chunks[0]["chunk_text"] == "This is the only content to be chunked."
    assert actual_chunks[0]["chunk_type"] == "LAYOUT_TEXT"


def test_empty_or_whitespace_layout_text_block_is_ignored():
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

    # Act
    actual_chunks = extract_layout_chunks(
        doc=mock_doc,
        ingested_doc_id="empty-block-doc",
        s3_image_uri_prefix="s3://my-bucket/empty-block-doc",
        uploaded_file_name="empty_block.pdf",
        page_count=1,
    )

    # Assert
    assert len(actual_chunks) == 2, "Should ignore empty and whitespace-only blocks"
    assert actual_chunks[0]["chunk_text"] == "This is a valid chunk."
    assert actual_chunks[0]["chunk_index"] == 0
    assert actual_chunks[1]["chunk_text"] == "Another valid chunk."
    assert actual_chunks[1]["chunk_index"] == 1


def test_handles_missing_optional_metadata():
    """
    Tests that the function runs without error and sets default values
    when optional arguments like `uploaded_file_name` and `page_count` are omitted.
    """
    # Arrange
    document_definition = [[{"type": "LAYOUT_TEXT", "lines": ["Simple content."]}]]
    mock_doc = textractor_document_factory(document_definition)

    # Act: Call the function without optional arguments
    # TODO review this, there should be no optional arguments in the function signature
    # However some of the metadata may be moved to the pages index
    actual_chunks = extract_layout_chunks(
        doc=mock_doc,
        ingested_doc_id="default-meta-doc",
        s3_image_uri_prefix="s3://my-bucket/default-meta-doc",
    )

    # Assert
    assert len(actual_chunks) == 1
    chunk = actual_chunks[0]

    # Assert that the default values from the function signature are used
    assert chunk["source_file_name"] == ""
    assert chunk["page_count"] == 0
    assert chunk["chunk_text"] == "Simple content."
    assert chunk["ingested_doc_id"] == "default-meta-doc"
