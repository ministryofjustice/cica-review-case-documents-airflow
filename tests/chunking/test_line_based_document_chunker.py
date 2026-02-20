"""Tests for LineBasedDocumentChunker."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from textractor.entities.bbox import BoundingBox
from textractor.entities.document import Document

from ingestion_pipeline.chunking.line_based_document_chunker import (
    ChunkError,
    LineBasedDocumentChunker,
)
from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.chunking.strategies.line_sentence_chunker import LineSentenceChunkingConfig


@pytest.fixture
def sample_metadata():
    """Create sample document metadata for testing."""
    return DocumentMetadata(
        source_doc_id="test_doc_1",
        source_file_name="test.pdf",
        source_file_s3_uri="s3://test-bucket/test.pdf",
        page_count=2,
        case_ref="TEST123",
        received_date=datetime(2024, 1, 1),
        correspondence_type="letter",
    )


@pytest.fixture
def chunker():
    """Create a LineBasedDocumentChunker with test configuration."""
    config = LineSentenceChunkingConfig(
        min_words=10,
        max_words=20,
        max_vertical_gap_ratio=0.05,
        debug=False,
    )
    return LineBasedDocumentChunker(config=config)


def create_mock_line(text: str, top: float, left: float = 0.1):
    """Create a mock Line object."""
    mock_line = MagicMock()
    mock_line.bbox = BoundingBox(x=left, y=top, width=0.8, height=0.02)
    mock_line.text = text
    return mock_line


def create_mock_page(page_num: int, lines: list):
    """Create a mock page with lines."""
    mock_page = MagicMock()
    mock_page.page_num = page_num
    mock_page.lines = lines
    return mock_page


def create_mock_document(pages: list, with_response: bool = True):
    """Create a mock Textractor Document."""
    mock_doc = MagicMock(spec=Document)
    mock_doc.pages = pages
    mock_doc.response = {"Blocks": [], "DocumentMetadata": {"Pages": len(pages)}} if with_response else None
    return mock_doc


class TestLineBasedDocumentChunker:
    """Test suite for LineBasedDocumentChunker."""

    def test_initialization_with_default_config(self):
        """Test that chunker initializes with default configuration."""
        with patch("ingestion_pipeline.chunking.line_based_document_chunker.settings") as mock_settings:
            mock_settings.SENTENCE_CHUNKER_MIN_WORDS = 80
            mock_settings.SENTENCE_CHUNKER_MAX_WORDS = 100
            mock_settings.SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO = 0.05

            chunker = LineBasedDocumentChunker()

            assert chunker.config.min_words == 80
            assert chunker.config.max_words == 100
            assert chunker.config.max_vertical_gap_ratio == 0.05

    def test_initialization_with_custom_config(self):
        """Test that chunker initializes with custom configuration."""
        config = LineSentenceChunkingConfig(
            min_words=50,
            max_words=75,
            max_vertical_gap_ratio=0.03,
            debug=True,
        )
        chunker = LineBasedDocumentChunker(config=config)

        assert chunker.config.min_words == 50
        assert chunker.config.max_words == 75
        assert chunker.config.max_vertical_gap_ratio == 0.03
        assert chunker.config.debug is True

    def test_chunk_empty_document_raises_error(self, chunker, sample_metadata):
        """Test that empty document raises ValueError."""
        mock_doc = create_mock_document(pages=[])

        with pytest.raises(ValueError, match="Document cannot be None and must contain pages"):
            chunker.chunk(mock_doc, sample_metadata)

    def test_chunk_document_without_response_raises_error(self, chunker, sample_metadata):
        """Test that document without response raises ChunkException."""
        lines = [create_mock_line("Test line.", 0.1)]
        pages = [create_mock_page(1, lines)]
        mock_doc = create_mock_document(pages, with_response=False)

        with pytest.raises(ChunkError, match="missing raw response"):
            chunker.chunk(mock_doc, sample_metadata)

    def test_chunk_single_page_document(self, chunker, sample_metadata):
        """Test processing a single-page document."""
        lines = [
            create_mock_line("This is the first sentence.", 0.1),
            create_mock_line("This is the second sentence.", 0.15),
        ]
        pages = [create_mock_page(1, lines)]
        mock_doc = create_mock_document(pages)

        result = chunker.chunk(mock_doc, sample_metadata)

        assert len(result.chunks) == 1
        assert result.chunks[0].page_number == 1
        assert result.chunks[0].chunk_index == 0
        assert "first sentence" in result.chunks[0].chunk_text
        assert "second sentence" in result.chunks[0].chunk_text

    def test_chunk_multi_page_document(self, chunker, sample_metadata):
        """Test processing a multi-page document."""
        # Page 1
        page1_lines = [
            create_mock_line("Page one first sentence.", 0.1),
            create_mock_line("Page one second sentence.", 0.15),
        ]
        # Page 2
        page2_lines = [
            create_mock_line("Page two first sentence.", 0.1),
            create_mock_line("Page two second sentence.", 0.15),
        ]

        pages = [
            create_mock_page(1, page1_lines),
            create_mock_page(2, page2_lines),
        ]
        mock_doc = create_mock_document(pages)

        result = chunker.chunk(mock_doc, sample_metadata)

        # Should have chunks from both pages
        assert len(result.chunks) >= 2
        page_numbers = {chunk.page_number for chunk in result.chunks}
        assert 1 in page_numbers
        assert 2 in page_numbers

    def test_chunk_indices_increment_correctly(self, chunker, sample_metadata):
        """Test that chunk indices increment correctly across pages."""
        # Page 1 - will create 2 chunks
        page1_lines = [
            create_mock_line("First chunk on page one.", 0.1),
            create_mock_line("Second chunk on page one.", 0.2),  # Large gap forces break
        ]
        # Page 2 - will create 1 chunk
        page2_lines = [
            create_mock_line("First chunk on page two.", 0.1),
        ]

        pages = [
            create_mock_page(1, page1_lines),
            create_mock_page(2, page2_lines),
        ]
        mock_doc = create_mock_document(pages)

        result = chunker.chunk(mock_doc, sample_metadata)

        # Check indices are sequential
        indices = [chunk.chunk_index for chunk in result.chunks]
        assert indices == list(range(len(indices)))

    def test_page_without_lines_skipped(self, chunker, sample_metadata):
        """Test that pages without lines are skipped."""
        page1_lines = [create_mock_line("Text on page 1.", 0.1)]
        page2_lines = []  # Empty page
        page3_lines = [create_mock_line("Text on page 3.", 0.1)]

        pages = [
            create_mock_page(1, page1_lines),
            create_mock_page(2, page2_lines),
            create_mock_page(3, page3_lines),
        ]
        mock_doc = create_mock_document(pages)

        result = chunker.chunk(mock_doc, sample_metadata)

        # Should have chunks from pages 1 and 3 only
        page_numbers = {chunk.page_number for chunk in result.chunks}
        assert 1 in page_numbers
        assert 2 not in page_numbers
        assert 3 in page_numbers

    def test_page_without_lines_attribute_handled(self, chunker, sample_metadata):
        """Test that pages without lines attribute are handled gracefully."""
        mock_page = MagicMock()
        mock_page.page_num = 1
        # Don't set lines attribute
        delattr(mock_page, "lines") if hasattr(mock_page, "lines") else None

        pages = [mock_page]
        mock_doc = create_mock_document(pages)

        result = chunker.chunk(mock_doc, sample_metadata)

        # Should return empty chunks list but not crash
        assert result.chunks == []

    def test_metadata_preserved_in_chunks(self, chunker, sample_metadata):
        """Test that document metadata is preserved in all chunks."""
        lines = [create_mock_line("Test text.", 0.1)]
        pages = [create_mock_page(1, lines)]
        mock_doc = create_mock_document(pages)

        result = chunker.chunk(mock_doc, sample_metadata)

        assert len(result.chunks) == 1
        chunk = result.chunks[0]
        assert chunk.source_doc_id == "test_doc_1"
        assert chunk.source_file_name == "test.pdf"
        assert chunk.case_ref == "TEST123"
        assert chunk.correspondence_type == "letter"

    def test_chunk_type_is_line_sentence_chunk(self, chunker, sample_metadata):
        """Test that chunks have correct type."""
        lines = [create_mock_line("Test.", 0.1)]
        pages = [create_mock_page(1, lines)]
        mock_doc = create_mock_document(pages)

        result = chunker.chunk(mock_doc, sample_metadata)

        assert len(result.chunks) == 1
        assert result.chunks[0].chunk_type == "LINE_SENTENCE_CHUNK"

    def test_returns_processed_document(self, chunker, sample_metadata):
        """Test that chunk() returns a ProcessedDocument."""
        from ingestion_pipeline.chunking.schemas import ProcessedDocument

        lines = [create_mock_line("Test.", 0.1)]
        pages = [create_mock_page(1, lines)]
        mock_doc = create_mock_document(pages)

        result = chunker.chunk(mock_doc, sample_metadata)

        assert isinstance(result, ProcessedDocument)
        assert hasattr(result, "chunks")
        assert isinstance(result.chunks, list)

    def test_integration_with_line_sentence_chunker(self, sample_metadata):
        """Test that LineBasedDocumentChunker correctly uses LineSentenceChunker."""
        config = LineSentenceChunkingConfig(
            min_words=5,
            max_words=10,
            max_vertical_gap_ratio=0.05,
        )
        chunker = LineBasedDocumentChunker(config=config)

        lines = [
            create_mock_line("One two three four five.", 0.1),  # 5 words, ends with period
            create_mock_line("Six seven eight nine ten.", 0.15),  # 5 words
        ]
        pages = [create_mock_page(1, lines)]
        mock_doc = create_mock_document(pages)

        result = chunker.chunk(mock_doc, sample_metadata)

        # Should create 2 chunks due to sentence boundary at min_words
        assert len(result.chunks) == 2
        assert "five." in result.chunks[0].chunk_text
        assert "ten." in result.chunks[1].chunk_text


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_none_document_raises_error(self, sample_metadata):
        """Test that None document raises ValueError."""
        chunker = LineBasedDocumentChunker()

        with pytest.raises(ValueError, match="Document cannot be None"):
            chunker.chunk(None, sample_metadata)

    def test_processing_error_wrapped_in_chunk_error(self, chunker, sample_metadata):
        """Test that processing errors are wrapped in ChunkError."""
        lines = [create_mock_line("Test", 0.1)]
        pages = [create_mock_page(1, lines)]
        mock_doc = create_mock_document(pages)

        # Force an error by mocking the chunker to raise an exception
        with patch.object(chunker.chunker, "chunk_page", side_effect=Exception("Test error")):
            with pytest.raises(ChunkError, match="Error processing page"):
                chunker.chunk(mock_doc, sample_metadata)


class TestCompatibilityWithDocumentChunker:
    """Test that LineBasedDocumentChunker is compatible with DocumentChunker interface."""

    def test_has_same_interface_as_document_chunker(self):
        """Test that LineBasedDocumentChunker has the same public interface."""
        from ingestion_pipeline.chunking.textract_document_chunker import TextractLayoutDocumentChunker

        line_chunker = LineBasedDocumentChunker()
        layout_chunker = TextractLayoutDocumentChunker(strategy_handlers={})

        # Both should have chunk method with same signature
        assert hasattr(line_chunker, "chunk")
        assert hasattr(layout_chunker, "chunk")

        # Check method signatures are compatible
        import inspect

        line_sig = inspect.signature(line_chunker.chunk)
        layout_sig = inspect.signature(layout_chunker.chunk)

        # Parameter names should match
        assert list(line_sig.parameters.keys()) == list(layout_sig.parameters.keys())

    def test_can_be_used_as_drop_in_replacement(self, sample_metadata):
        """Test that it can be used as a drop-in replacement in pipeline."""
        # This simulates how it would be used in pipeline_builder.py
        lines = [create_mock_line("Test text.", 0.1)]
        pages = [create_mock_page(1, lines)]
        mock_doc = create_mock_document(pages)

        # Use the line-based chunker
        chunker = LineBasedDocumentChunker()
        result = chunker.chunk(mock_doc, sample_metadata)

        # Should work exactly like DocumentChunker
        assert hasattr(result, "chunks")
        assert isinstance(result.chunks, list)
        assert all(hasattr(chunk, "chunk_text") for chunk in result.chunks)
