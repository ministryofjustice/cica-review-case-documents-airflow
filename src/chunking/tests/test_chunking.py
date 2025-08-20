import json
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest
from chunking.chunker import _create_opensearch_chunk, extract_layout_chunks

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
        doc_meta={"Key": "Value"},
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
    assert chunk["page_count"] is None
    assert chunk["chunk_type"] == "LAYOUT_TEXT"


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
    # --- Input parameters for our function ---
    document_id = "unique-UUID"
    s3_image_uri_prefix = "s3://case-kta-document-images-bucket/25-787878/unique-UUID_page/page_1.png"

    # --- Call the function we are testing (which doesn't exist yet) ---
    actual_chunks = extract_layout_chunks(textract_response, document_id, s3_image_uri_prefix)

    # --- Define the EXACT output we expect ---
    # Manually combine the text from the two LINE blocks that are children of the LAYOUT_TEXT block
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
