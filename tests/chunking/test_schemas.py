"""Tests for the DocumentBoundingBox schema and its conversion to Textractor BoundingBox."""

import datetime
from unittest import mock

from textractor.entities.bbox import BoundingBox

from ingestion_pipeline.chunking.schemas import DocumentBoundingBox, DocumentChunk, DocumentMetadata, DocumentPage


def test_to_textractor_bbox_returns_correct_bbox():
    bbox_data = {
        "Width": 100.0,
        "Height": 200.0,
        "Left": 10.0,
        "Top": 20.0,
    }
    doc_bbox = DocumentBoundingBox(**bbox_data)
    tex_bbox = doc_bbox.to_textractor_bbox()

    assert isinstance(tex_bbox, BoundingBox)
    assert tex_bbox.width == bbox_data["Width"]
    assert tex_bbox.height == bbox_data["Height"]
    assert tex_bbox.x == bbox_data["Left"]
    assert tex_bbox.y == bbox_data["Top"]


def test_to_textractor_bbox_with_negative_values():
    bbox_data = {
        "Width": -50.0,
        "Height": -60.0,
        "Left": -5.0,
        "Top": -10.0,
    }
    doc_bbox = DocumentBoundingBox(**bbox_data)
    tex_bbox = doc_bbox.to_textractor_bbox()

    assert tex_bbox.width == bbox_data["Width"]
    assert tex_bbox.height == bbox_data["Height"]
    assert tex_bbox.x == bbox_data["Left"]
    assert tex_bbox.y == bbox_data["Top"]


def test_document_bounding_box_right_and_bottom():
    bbox = DocumentBoundingBox(Width=10.0, Height=20.0, Left=5.0, Top=7.0)
    assert bbox.right == 15.0  # 5.0 + 10.0
    assert bbox.bottom == 27.0  # 7.0 + 20.0


def test_document_bounding_box_right_and_bottom_negative():
    bbox = DocumentBoundingBox(Width=-3.0, Height=-4.0, Left=-2.0, Top=-1.0)
    assert bbox.right == -5.0  # -2.0 + -3.0
    assert bbox.bottom == -5.0  # -1.0 + -4.0


def make_metadata():
    return DocumentMetadata(
        source_doc_id="doc123",
        source_file_name="file.pdf",
        source_file_s3_uri="s3://bucket/file.pdf",
        page_count=5,
        case_ref="CASE-001",
        received_date=datetime.datetime.fromisoformat("2025-11-06"),
        correspondence_type="letter",
    )


@mock.patch("ingestion_pipeline.chunking.schemas.DocumentIdentifier")
def test_generate_chunk_id_calls_source_doc_identifier(mock_identifier_cls):
    metadata = make_metadata()
    mock_identifier = mock_identifier_cls.return_value
    mock_identifier.generate_uuid.return_value = "mocked-uuid"

    chunk_id = DocumentChunk._generate_chunk_id(metadata, page_num=2, chunk_index=1)

    mock_identifier_cls.assert_called_once_with(
        source_file_name=metadata.source_file_name,
        correspondence_type=metadata.correspondence_type,
        case_ref=metadata.case_ref,
        page_num=2,
        chunk_index=1,
    )
    mock_identifier.generate_uuid.assert_called_once()
    assert chunk_id == "mocked-uuid"


@mock.patch("ingestion_pipeline.chunking.schemas.DocumentIdentifier")
def test_generate_chunk_id_returns_unique_for_different_inputs(mock_identifier_cls):
    metadata = make_metadata()
    mock_identifier = mock_identifier_cls.return_value
    # Simulate different UUIDs for different calls
    mock_identifier.generate_uuid.side_effect = ["uuid1", "uuid2"]

    id1 = DocumentChunk._generate_chunk_id(metadata, page_num=1, chunk_index=1)
    id2 = DocumentChunk._generate_chunk_id(metadata, page_num=2, chunk_index=1)

    assert id1 == "uuid1"
    assert id2 == "uuid2"
    assert id1 != id2


@mock.patch("ingestion_pipeline.chunking.schemas.DocumentIdentifier")
def test_generate_chunk_id_with_minimal_metadata(mock_identifier_cls):
    metadata = DocumentMetadata(
        source_doc_id="id",
        source_file_name="f.pdf",
        source_file_s3_uri="s3://bucket/file.pdf",
        page_count=1,
        case_ref="REF",
        received_date=datetime.datetime.fromisoformat("2025-11-06"),
        correspondence_type="type",
    )
    mock_identifier = mock_identifier_cls.return_value
    mock_identifier.generate_uuid.return_value = "uuid-minimal"

    chunk_id = DocumentChunk._generate_chunk_id(metadata, page_num=1, chunk_index=0)
    assert chunk_id == "uuid-minimal"


@mock.patch("ingestion_pipeline.chunking.schemas.DocumentIdentifier")
def test_page_contains_handwriting_defaults_to_false(mock_identifier_cls):
    mock_identifier = mock_identifier_cls.return_value
    mock_identifier.generate_uuid.return_value = "uuid-hw-test"

    metadata = make_metadata()
    bbox = BoundingBox(x=0.1, y=0.2, width=0.5, height=0.3)

    chunk = DocumentChunk.create_chunk(
        page_number=1,
        metadata=metadata,
        chunk_index=0,
        chunk_text="Some text.",
        combined_bbox=bbox,
        layout_type="TEXTRACT_WORD_STREAM_CHUNK",
        confidence=None,
    )

    assert chunk.page_contains_handwriting is False
    assert "page_contains_handwriting" in chunk.model_dump()
    assert chunk.model_dump()["page_contains_handwriting"] is False


@mock.patch("ingestion_pipeline.chunking.schemas.DocumentIdentifier")
def test_page_contains_handwriting_set_to_true(mock_identifier_cls):
    mock_identifier = mock_identifier_cls.return_value
    mock_identifier.generate_uuid.return_value = "uuid-hw-true"

    metadata = make_metadata()
    bbox = BoundingBox(x=0.1, y=0.2, width=0.5, height=0.3)

    chunk = DocumentChunk.create_chunk(
        page_number=1,
        metadata=metadata,
        chunk_index=0,
        chunk_text="Handwritten text.",
        combined_bbox=bbox,
        layout_type="TEXTRACT_WORD_STREAM_CHUNK",
        confidence=None,
        page_contains_handwriting=True,
    )

    assert chunk.page_contains_handwriting is True
    assert chunk.model_dump()["page_contains_handwriting"] is True


# --- Tests for DocumentPage.page_contains_handwriting ---


def test_document_page_handwriting_defaults_to_false():
    page = DocumentPage(
        source_doc_id="doc-123",
        source_file_name="test-doc.pdf",
        case_ref="26-711111",
        page_num=1,
        page_count=3,
        page_id="page-uuid-1",
        s3_page_image_s3_uri="s3://bucket/page1.png",
        text="Some OCR text",
        page_width=612.0,
        page_height=792.0,
        received_date=datetime.datetime.fromisoformat("2024-01-01"),
        correspondence_type="Letter",
    )

    assert page.page_contains_handwriting is False


def test_document_page_handwriting_set_to_true():
    page = DocumentPage(
        source_doc_id="doc-123",
        source_file_name="test-doc.pdf",
        case_ref="26-711111",
        page_num=1,
        page_count=3,
        page_id="page-uuid-1",
        s3_page_image_s3_uri="s3://bucket/page1.png",
        text="Some OCR text",
        page_width=612.0,
        page_height=792.0,
        received_date=datetime.datetime.fromisoformat("2024-01-01"),
        correspondence_type="Letter",
        page_contains_handwriting=True,
    )

    assert page.page_contains_handwriting is True


def test_document_page_handwriting_in_model_dump():
    page = DocumentPage(
        source_doc_id="doc-123",
        source_file_name="test-doc.pdf",
        case_ref="26-711111",
        page_num=1,
        page_count=3,
        page_id="page-uuid-1",
        s3_page_image_s3_uri="s3://bucket/page1.png",
        text="Some OCR text",
        page_width=612.0,
        page_height=792.0,
        received_date=datetime.datetime.fromisoformat("2024-01-01"),
        correspondence_type="Letter",
    )

    dump = page.model_dump()
    assert "page_contains_handwriting" in dump
    assert dump["page_contains_handwriting"] is False


def test_document_page_handwriting_can_be_updated_after_construction():
    page = DocumentPage(
        source_doc_id="doc-123",
        source_file_name="test-doc.pdf",
        case_ref="26-711111",
        page_num=1,
        page_count=3,
        page_id="page-uuid-1",
        s3_page_image_s3_uri="s3://bucket/page1.png",
        text="Some OCR text",
        page_width=612.0,
        page_height=792.0,
        received_date=datetime.datetime.fromisoformat("2024-01-01"),
        correspondence_type="Letter",
    )

    assert page.page_contains_handwriting is False
    page.page_contains_handwriting = True
    assert page.page_contains_handwriting is True
    assert page.model_dump()["page_contains_handwriting"] is True
