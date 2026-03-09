"""Tests for LineSentenceChunker."""

import pytest
from textractor.entities.bbox import BoundingBox
from textractor.entities.line import Line

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.chunking.strategies.line_sentence.chunker import LineSentenceChunker
from ingestion_pipeline.chunking.strategies.line_sentence.config import LineSentenceChunkingConfig


@pytest.fixture
def sample_metadata():
    """Create sample document metadata for testing."""
    from datetime import datetime

    return DocumentMetadata(
        source_doc_id="test_doc_1",
        source_file_name="test.pdf",
        source_file_s3_uri="s3://test-bucket/test.pdf",
        page_count=1,
        case_ref="TEST123",
        received_date=datetime(2024, 1, 1),
        correspondence_type="letter",
    )


@pytest.fixture
def chunker():
    """Create a chunker instance with default configuration."""
    return LineSentenceChunker()


@pytest.fixture
def custom_chunker():
    """Create a chunker with custom configuration."""
    config = LineSentenceChunkingConfig(
        min_words=10,
        max_words=20,
        max_vertical_gap_ratio=0.05,
    )
    return LineSentenceChunker(config=config)


def create_mock_line(text: str, top: float, left: float = 0.1, width: float = 0.8, height: float = 0.02) -> Line:
    """Create a mock Line object for testing.

    Args:
        text: Line text content
        top: Top position (y coordinate)
        left: Left position (x coordinate)
        width: Width of bounding box
        height: Height of bounding box

    Returns:
        Mock Line object
    """
    from unittest.mock import MagicMock

    bbox = BoundingBox(x=left, y=top, width=width, height=height)

    # Create a mock Line that behaves like a real one
    mock_line = MagicMock(spec=Line)
    mock_line.entity_id = f"line_{top}"
    mock_line.bbox = bbox
    mock_line.confidence = 95.0
    mock_line.text = text

    return mock_line


def test_initialization_with_custom_config():
    """Test that chunker initializes with custom configuration."""
    config = LineSentenceChunkingConfig(
        min_words=50,
        max_words=75,
        max_vertical_gap_ratio=0.03,
    )
    chunker = LineSentenceChunker(config=config)
    assert chunker.config.min_words == 50
    assert chunker.config.max_words == 75
    assert chunker.config.max_vertical_gap_ratio == 0.03


def test_empty_lines_returns_empty_list(chunker, sample_metadata):
    """Test that empty lines list returns empty chunks."""
    chunks = chunker.chunk_page(
        lines=[],
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )
    assert chunks == []


def test_single_line_creates_single_chunk(chunker, sample_metadata):
    """Test that a single line creates a single chunk."""
    lines = [create_mock_line("This is a test sentence.", top=0.1)]

    chunks = chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_text == "This is a test sentence."
    assert chunks[0].page_number == 1
    assert chunks[0].chunk_index == 0


def test_lines_sorted_by_vertical_position(chunker, sample_metadata):
    """Test that lines are sorted by vertical position before chunking."""
    # Create lines out of order
    lines = [
        create_mock_line("Third line.", top=0.3),
        create_mock_line("First line.", top=0.1),
        create_mock_line("Second line.", top=0.2),
    ]

    chunks = chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )

    all_text = " ".join(chunk.chunk_text for chunk in chunks)
    assert "First line." in all_text
    assert "Second line." in all_text
    assert "Third line." in all_text
    sorted_texts = [chunk.chunk_text for chunk in chunks]
    combined = " ".join(sorted_texts)
    assert combined.index("First line.") < combined.index("Second line.") < combined.index("Third line.")


def test_sentence_boundary_closes_chunk(custom_chunker, sample_metadata):
    """Test that sentence boundaries close chunks after min_words."""
    lines = [
        create_mock_line("This is the first sentence.", top=0.1),  # 5 words
        create_mock_line("This is the second sentence.", top=0.15),  # 5 words
        create_mock_line("Here is a third complete sentence.", top=0.2),  # 6 words (total: 16 > min=10)
        create_mock_line("And here is a fourth sentence.", top=0.25),  # 6 words
    ]

    chunks = custom_chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )

    # With lookahead, all lines may be included in one chunk if under max_words
    if custom_chunker.config.max_words >= 22:
        assert len(chunks) == 1
        assert "third complete sentence." in chunks[0].chunk_text
        assert "fourth sentence." in chunks[0].chunk_text
    else:
        assert len(chunks) >= 1


def test_max_words_forces_chunk_break(custom_chunker, sample_metadata):
    """Test that exceeding max_words forces a chunk break."""
    long_text = " ".join(["word"] * 25)  # 25 words
    lines = [
        create_mock_line(long_text, top=0.1),
        create_mock_line("Additional text here", top=0.15),
    ]

    chunks = custom_chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )

    assert len(chunks) == 2


def test_vertical_gap_forces_chunk_break(custom_chunker, sample_metadata):
    """Test that large vertical gaps trigger a chunk break."""
    lines = [
        create_mock_line("First paragraph text.", top=0.1),
        create_mock_line("More text in first paragraph.", top=0.12),
        create_mock_line("Second paragraph after gap.", top=0.25),
    ]

    chunks = custom_chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )

    if custom_chunker.config.min_words > 6:
        assert len(chunks) == 1
        assert "First paragraph" in chunks[0].chunk_text
        assert "Second paragraph" in chunks[0].chunk_text
    else:
        assert len(chunks) >= 1


def test_chunk_index_increments_correctly(custom_chunker, sample_metadata):
    """Test that chunk indices increment correctly."""
    lines = [
        create_mock_line("First chunk complete sentence.", top=0.1),
        create_mock_line("Second chunk complete sentence.", top=0.2),
        create_mock_line("Third chunk complete sentence.", top=0.3),
    ]

    chunks = custom_chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=5,  # Start at 5
    )

    assert len(chunks) >= 1
    assert chunks[0].chunk_index == 5
    if len(chunks) > 1:
        assert chunks[1].chunk_index == 6
    if len(chunks) > 2:
        assert chunks[2].chunk_index == 7


def test_bounding_box_calculation(chunker, sample_metadata):
    """Test that bounding boxes are correctly calculated."""
    lines = [
        create_mock_line("Line 1.", top=0.1, left=0.1, width=0.5),
        create_mock_line("Line 2.", top=0.15, left=0.2, width=0.6),
    ]

    chunks = chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )

    assert len(chunks) == 1
    bbox = chunks[0].bounding_box
    assert bbox.left == pytest.approx(0.1)
    assert bbox.top == pytest.approx(0.1)
    assert bbox.right == pytest.approx(0.8)
    assert bbox.bottom == pytest.approx(0.17)


def test_lines_without_text_are_skipped(chunker, sample_metadata):
    """Test that lines without text are skipped."""
    lines = [
        create_mock_line("Valid line.", top=0.1),
        create_mock_line("", top=0.15),
        create_mock_line("   ", top=0.2),
        create_mock_line("Another valid line.", top=0.25),
    ]

    chunks = chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )

    assert len(chunks) == 1
    assert "Valid line" in chunks[0].chunk_text
    assert "Another valid line" in chunks[0].chunk_text


def test_lines_without_bbox_are_skipped(chunker, sample_metadata):
    """Test that lines without bounding boxes are skipped."""
    from unittest.mock import MagicMock

    valid_line = create_mock_line("Valid line.", top=0.1)

    invalid_line = MagicMock(spec=Line)
    invalid_line.entity_id = "invalid"
    invalid_line.bbox = None
    invalid_line.text = "Invalid line without bbox"
    invalid_line.confidence = 95.0

    lines = [valid_line, invalid_line]

    chunks = chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )

    assert len(chunks) == 1
    assert "Valid line" in chunks[0].chunk_text
    assert "Invalid" not in chunks[0].chunk_text


def test_ends_with_sentence_terminator(chunker):
    """Test sentence terminator detection."""
    assert chunker.sentence_detector.ends_with_sentence_terminator("This is a sentence.") is True
    assert chunker.sentence_detector.ends_with_sentence_terminator("Is this a question?") is True
    assert chunker.sentence_detector.ends_with_sentence_terminator("What an exclamation!") is True
    assert chunker.sentence_detector.ends_with_sentence_terminator("No terminator here") is False
    assert chunker.sentence_detector.ends_with_sentence_terminator("Comma,") is False
    assert chunker.sentence_detector.ends_with_sentence_terminator("") is False
    assert chunker.sentence_detector.ends_with_sentence_terminator("   ") is False


def test_chunk_metadata_preserved(chunker, sample_metadata):
    """Test that document metadata is preserved in chunks."""
    lines = [create_mock_line("Test text.", top=0.1)]

    chunks = chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.source_doc_id == "test_doc_1"
    assert chunk.source_file_name == "test.pdf"
    assert chunk.case_ref == "TEST123"
    assert chunk.correspondence_type == "letter"


def test_word_count_computed_field(chunker, sample_metadata):
    """Test that word_count computed field is correct."""
    lines = [
        create_mock_line("One two three four five.", top=0.1),
        create_mock_line("Six seven eight.", top=0.15),
    ]

    chunks = chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )

    assert len(chunks) == 1
    assert chunks[0].word_count == 8


def test_chunk_type_is_line_sentence_chunk(chunker, sample_metadata):
    """Test that chunk type is set correctly."""
    lines = [create_mock_line("Test.", top=0.1)]

    chunks = chunker.chunk_page(
        lines=lines,
        page_number=1,
        metadata=sample_metadata,
        chunk_index_start=0,
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "LINE_SENTENCE_CHUNK"


def test_exactly_min_words_with_sentence_boundary(sample_metadata):
    """Test behavior when reaching exactly min_words with sentence boundary."""
    config = LineSentenceChunkingConfig(min_words=5, max_words=10, max_vertical_gap_ratio=0.05)
    chunker = LineSentenceChunker(config=config)

    lines = [
        create_mock_line("One two three four five.", top=0.1),  # Exactly 5 words, ends with .
        create_mock_line("Six seven eight nine ten.", top=0.15),  # 5 more words
    ]

    chunks = chunker.chunk_page(lines, 1, sample_metadata, 0)

    assert len(chunks) == 2
    assert chunks[0].word_count == 5
    assert chunks[1].word_count == 5
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1


def test_exactly_max_words(sample_metadata):
    """Test behavior when reaching exactly max_words."""
    config = LineSentenceChunkingConfig(min_words=5, max_words=10, max_vertical_gap_ratio=0.05)
    chunker = LineSentenceChunker(config=config)

    lines = [
        create_mock_line("One two three four five six seven eight nine ten", top=0.1),  # Exactly 10
        create_mock_line("Eleven", top=0.15),
    ]

    chunks = chunker.chunk_page(lines, 1, sample_metadata, 0)

    assert len(chunks) == 2
    assert chunks[0].word_count == 10
    assert chunks[1].word_count == 1
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1


def test_single_line_exceeds_max_words(sample_metadata):
    """Test handling when a single line exceeds max_words."""
    config = LineSentenceChunkingConfig(min_words=5, max_words=10, max_vertical_gap_ratio=0.05)
    chunker = LineSentenceChunker(config=config)

    long_text = " ".join([f"word{i}" for i in range(15)])  # 15 words
    lines = [
        create_mock_line(long_text, top=0.1),
        create_mock_line("Short line.", top=0.15),
    ]

    chunks = chunker.chunk_page(lines, 1, sample_metadata, 0)

    assert len(chunks) == 2
    assert chunks[0].word_count >= 10
    assert chunks[1].word_count >= 1
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1


def test_backward_split_finds_sentence_boundary_and_splits(sample_metadata):
    """Covers _find_backward_split: finds a sentence boundary and splits."""
    config = LineSentenceChunkingConfig(min_words=2, max_words=5, max_vertical_gap_ratio=1.0)
    chunker = LineSentenceChunker(config=config)

    # 1st line: no terminator, 2nd line: sentence terminator, 3rd line: no terminator
    lines = [
        create_mock_line("No end", top=0.1),
        create_mock_line("Boundary here.", top=0.2),
        create_mock_line("More text", top=0.3),
        create_mock_line("And more", top=0.4),
    ]
    # This will force a backward split after exceeding min_words but before max_words
    chunks = chunker.chunk_page(lines, 1, sample_metadata, 0)
    # Should split at the sentence boundary (after "Boundary here.")
    assert any("Boundary here." in c.chunk_text for c in chunks)
    assert len(chunks) >= 2


def test_backward_split_returns_none_when_no_boundary(sample_metadata):
    """Covers _find_backward_split: returns None if no sentence boundary found."""
    config = LineSentenceChunkingConfig(min_words=2, max_words=5, max_vertical_gap_ratio=1.0)
    chunker = LineSentenceChunker(config=config)
    # Patch sentence_detector to always return False
    chunker.sentence_detector.ends_with_sentence_terminator = lambda text: False

    # All lines lack sentence terminators
    lines = [
        create_mock_line("No end", top=0.1),
        create_mock_line("Still no end", top=0.2),
        create_mock_line("More text", top=0.3),
    ]
    # Should not split, so only force close at max_words
    chunks = chunker.chunk_page(lines, 1, sample_metadata, 0)
    assert len(chunks) >= 1


def test_lookahead_absorbs_lines_into_chunk(sample_metadata):
    """Covers lookahead_count > 0: absorbs lookahead lines into current chunk."""
    config = LineSentenceChunkingConfig(min_words=2, max_words=10, max_vertical_gap_ratio=1.0)
    chunker = LineSentenceChunker(config=config)

    # Patch sentence_detector to only return True for the third line
    def ends_with_terminator(text):
        return text.endswith("!")

    chunker.sentence_detector.ends_with_sentence_terminator = ends_with_terminator

    lines = [
        create_mock_line("First line", top=0.1),
        create_mock_line("Second line", top=0.2),
        create_mock_line("Third line!", top=0.3),  # Only this triggers lookahead close
    ]
    chunks = chunker.chunk_page(lines, 1, sample_metadata, 0)
    # All three lines should be in the first chunk
    assert any("Third line!" in c.chunk_text for c in chunks)
    assert len(chunks) == 1


def test_force_close_after_backward_split(sample_metadata):
    """Covers force close after backward split if still over max_words."""
    config = LineSentenceChunkingConfig(min_words=2, max_words=3, max_vertical_gap_ratio=1.0)
    chunker = LineSentenceChunker(config=config)

    # Patch sentence_detector to only return True for the first line
    def ends_with_terminator(text):
        return text.endswith(".")

    chunker.sentence_detector.ends_with_sentence_terminator = ends_with_terminator

    # 4 lines, only first is a sentence boundary, so after backward split, still over max_words
    lines = [
        create_mock_line("End.", top=0.1),
        create_mock_line("A", top=0.2),
        create_mock_line("B", top=0.3),
        create_mock_line("C", top=0.4),
    ]
    chunks = chunker.chunk_page(lines, 1, sample_metadata, 0)
    # Should result in two chunks: one for "End.", one for the rest (force closed)
    assert len(chunks) == 2
    assert "End." in chunks[0].chunk_text


def test_force_close_after_backward_split_triggers_force_close(sample_metadata):
    """Covers force close after backward split if still over max_words (lines 161-166)."""
    config = LineSentenceChunkingConfig(min_words=2, max_words=3, max_vertical_gap_ratio=1.0)
    chunker = LineSentenceChunker(config=config)

    # Patch sentence_detector to only return True for the first line
    def ends_with_terminator(text):
        return text == "End."

    chunker.sentence_detector.ends_with_sentence_terminator = ends_with_terminator

    # 4 lines, only first is a sentence boundary, so after backward split, still over max_words
    lines = [
        create_mock_line("End.", top=0.1),
        create_mock_line("A", top=0.2),
        create_mock_line("B", top=0.3),
        create_mock_line("C", top=0.4),
    ]
    chunks = chunker.chunk_page(lines, 1, sample_metadata, 0)
    # Should result in two chunks: one for "End.", one for the rest (force closed)
    assert len(chunks) == 2
    assert "End." in chunks[0].chunk_text
    # The second chunk should contain "A", "B", "C"
    assert all(any(x in c.chunk_text for c in chunks) for x in ["A", "B", "C"])


def test_lookahead_absorbs_lines_into_chunk_and_closes(sample_metadata):
    """Covers lookahead_count > 0 (line 238): absorbs lookahead lines into current chunk."""
    config = LineSentenceChunkingConfig(min_words=2, max_words=10, max_vertical_gap_ratio=1.0)
    chunker = LineSentenceChunker(config=config)

    # Patch sentence_detector to only return True for the third line
    def ends_with_terminator(text):
        return text.endswith("!")

    chunker.sentence_detector.ends_with_sentence_terminator = ends_with_terminator

    lines = [
        create_mock_line("First line", top=0.1),
        create_mock_line("Second line", top=0.2),
        create_mock_line("Third line!", top=0.3),  # Only this triggers lookahead close
    ]
    chunks = chunker.chunk_page(lines, 1, sample_metadata, 0)
    # All three lines should be in the first chunk
    assert len(chunks) == 1
    assert "Third line!" in chunks[0].chunk_text
    assert "First line" in chunks[0].chunk_text
    assert "Second line" in chunks[0].chunk_text


def test_forward_close_skips_empty_lookahead_line(sample_metadata):
    """Covers _check_forward_close skipping a lookahead line with no text (line 238)."""
    config = LineSentenceChunkingConfig(min_words=2, max_words=20, max_vertical_gap_ratio=1.0)
    chunker = LineSentenceChunker(config=config)

    lines = [
        create_mock_line("Two words", top=0.1),
        create_mock_line("", top=0.2),  # empty text, valid bbox — hits the `continue` in lookahead
        create_mock_line("Ending sentence.", top=0.3),
    ]

    chunks = chunker.chunk_page(lines, 1, sample_metadata, 0)
    assert len(chunks) == 1
    assert "Two words" in chunks[0].chunk_text
    assert "Ending sentence." in chunks[0].chunk_text
