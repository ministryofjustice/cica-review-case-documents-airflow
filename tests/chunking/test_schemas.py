"""Tests for the DocumentBoundingBox schema and its conversion to Textractor BoundingBox."""

import datetime
from unittest import mock

from textractor.entities.bbox import BoundingBox

from ingestion_pipeline.chunking.schemas import DocumentBoundingBox, DocumentChunk, DocumentMetadata


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


def make_metadata():
    return DocumentMetadata(
        ingested_doc_id="doc123",
        source_file_name="file.pdf",
        page_count=5,
        case_ref="CASE-001",
        received_date=datetime.datetime.fromisoformat("2025-11-06"),
        correspondence_type="letter",
    )


@mock.patch("ingestion_pipeline.chunking.schemas.DocumentIdentifier")
def test_generate_chunk_id_calls_document_identifier(mock_identifier_cls):
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
        ingested_doc_id="id",
        source_file_name="f.pdf",
        page_count=1,
        case_ref="REF",
        received_date=datetime.datetime.fromisoformat("2025-11-06"),
        correspondence_type="type",
    )
    mock_identifier = mock_identifier_cls.return_value
    mock_identifier.generate_uuid.return_value = "uuid-minimal"

    chunk_id = DocumentChunk._generate_chunk_id(metadata, page_num=1, chunk_index=0)
    assert chunk_id == "uuid-minimal"
