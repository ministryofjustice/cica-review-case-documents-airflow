"""Integration tests for Textract document chunking."""

import json
from datetime import date
from pathlib import Path
from typing import Optional

import pytest
from pydantic import ValidationError
from textractor.entities.document import Document

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.schemas import DocumentBoundingBox, DocumentMetadata
from ingestion_pipeline.chunking.strategies.layout_text import LayoutTextChunkingStrategy
from ingestion_pipeline.chunking.strategies.table import LayoutTableChunkingStrategy
from ingestion_pipeline.chunking.textract import (
    DocumentChunk,
    DocumentChunker,
)

TEXTRACT_JSON_PATH = Path(__file__).parent / "data" / "single_text_layout_textract_response.json"


@pytest.fixture
def textract_response():
    """Loads the sample Textract JSON response from a file."""
    with open(TEXTRACT_JSON_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def document_metadata_factory():
    """Returns a factory function to create DocumentMetadata objects.

    Returns:
        DocumentMetadata: The created DocumentMetadata object.
    """

    def _factory(**overrides):
        """Inner factory function with default metadata values.

        Returns:
            DocumentMetadata: The created DocumentMetadata object.
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
    """Returns a factory function to create DocumentChunker objects.

    this fixture returns a FACTORY function that can create a
    fully-wired TextractDocumentChunker instance.

    This allows tests to create a chunker with a custom config.

    Returns:
        DocumentChunker: The created DocumentChunker object.
    """

    def _factory(config: Optional[ChunkingConfig] = None) -> DocumentChunker:
        # If no config is provided by the test, use the default one.
        if config is None:
            config = ChunkingConfig()

        layout_text_strategy = LayoutTextChunkingStrategy(config)
        layout_table_strategy = LayoutTableChunkingStrategy(config)

        strategy_handlers = {
            "LAYOUT_TEXT": layout_text_strategy,
            "LAYOUT_TABLE": layout_table_strategy,
        }

        return DocumentChunker(
            strategy_handlers=strategy_handlers,
            config=config,
        )

    return _factory


def test_extract_single_layout_chunk_from_actual_textract_response(
    document_chunker_factory, textract_response, document_metadata_factory
):
    """Tests that a single LAYOUT_TEXT block is correctly processed.

    Args:
        document_chunker_factory (DocumentChunker): DocumentChunker factory fixture.
        textract_response (MockTextractResponse): Textract response JSON data.
        document_metadata_factory (DocumentMetadata): DocumentMetadata factory fixture.
    """
    mock_doc = Document.open(textract_response)

    mock_metadata = document_metadata_factory()

    processed_document = document_chunker_factory().chunk(doc=mock_doc, metadata=mock_metadata)

    actual_chunks = processed_document.chunks

    assert len(actual_chunks) == 1
    chunk1 = actual_chunks[0]
    assert isinstance(chunk1, DocumentChunk)

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


def test_handles_missing_pdf_id_metadata_throws_error(document_metadata_factory):
    """Tests that the function throws an error when required metadata is missing."""
    with pytest.raises(ValidationError, match="String should have at least 1 character"):
        document_metadata_factory(ingested_doc_id="")


def test_handles_empty_source_file_name_metadata_throws_error(document_metadata_factory):
    with pytest.raises(ValidationError, match="String should have at least 1 character"):
        document_metadata_factory(source_file_name="")


def test_handles_zero_page_count_metadata_throws_error(document_metadata_factory):
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        document_metadata_factory(page_count=0)


def test_handles_negative_page_count_metadata_throws_error(document_metadata_factory):
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        document_metadata_factory(page_count=-7)


def test_empty_textract_document_throws_error(document_chunker_factory, document_metadata_factory):
    mock_doc = Document()
    mock_metadata = document_metadata_factory()

    with pytest.raises(Exception, match="Document cannot be None and must contain pages."):
        document_chunker_factory().chunk(doc=mock_doc, metadata=mock_metadata)
