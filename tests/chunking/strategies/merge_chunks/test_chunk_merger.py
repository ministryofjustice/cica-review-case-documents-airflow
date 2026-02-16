"""Unit tests for the ChunkMerger class in the chunking strategies module."""

import datetime

import pytest

from ingestion_pipeline.chunking.schemas import DocumentBoundingBox, DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.strategies.merge.chunk_merger import ChunkMerger


# Helper function to create mock atomic chunks for tests
def create_atomic_chunk(
    text: str,
    page_number: int,
    top: float,
    height: float,
    metadata: DocumentMetadata,
    chunk_index: int,
    left: float = 0.1,
    width: float = 0.8,
) -> DocumentChunk:
    """Helper to create a mock OpenSearchDocument for testing."""
    bbox = DocumentBoundingBox(
        Width=width,
        Height=height,
        Left=left,
        Top=top,
    )
    # The class constructor validates the data
    return DocumentChunk(
        chunk_id=f"{metadata.source_doc_id}_p{page_number}_c{chunk_index}",
        source_doc_id=metadata.source_doc_id,
        chunk_text=text,
        source_file_name=metadata.source_file_name,
        source_file_s3_uri=metadata.source_file_s3_uri,
        page_count=metadata.page_count,
        page_number=page_number,
        chunk_index=chunk_index,
        chunk_type="TEST_CHUNK",
        confidence=0.99,
        bounding_box=bbox,
        case_ref=metadata.case_ref,
        received_date=metadata.received_date,
        correspondence_type=metadata.correspondence_type,
    )


@pytest.fixture
def doc_metadata() -> DocumentMetadata:
    """Provides a standard DocumentMetadata object for tests."""
    return DocumentMetadata(
        source_doc_id="doc123",
        source_file_name="test.pdf",
        source_file_s3_uri="s3://bucket/test.pdf",
        page_count=5,
        case_ref="CASE-001",
        received_date=datetime.datetime(2025, 9, 26),
        correspondence_type="Letter",
    )


def test_handles_empty_input_list(doc_metadata):
    """Given: An empty list of atomic chunks. When: The chunk method is called.

    Then: It should return an empty list.
    """
    merger = ChunkMerger()
    atomic_chunks = []
    result = merger.group_and_merge_atomic_chunks(atomic_chunks)
    assert result == []


def test_handles_single_atomic_chunk(doc_metadata):
    """Given: A single atomic chunk. When: The chunk method is called.

    Then: It should return a list containing a single merged chunk.
    """
    merger = ChunkMerger()
    chunk1 = create_atomic_chunk(
        "Hello world.",
        page_number=1,
        top=0.1,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=0,
    )
    atomic_chunks = [chunk1]

    result = merger.group_and_merge_atomic_chunks(atomic_chunks)

    assert len(result) == 1
    merged_chunk = result[0]
    assert merged_chunk.chunk_text == "Hello world."
    assert merged_chunk.page_number == 1

    assert merged_chunk.bounding_box.top == pytest.approx(chunk1.bounding_box.top)
    assert merged_chunk.bounding_box.left == pytest.approx(chunk1.bounding_box.left)
    assert merged_chunk.bounding_box.width == pytest.approx(chunk1.bounding_box.width)
    assert merged_chunk.bounding_box.height == pytest.approx(chunk1.bounding_box.height)

    assert merged_chunk.chunk_index == 0
    assert merged_chunk.chunk_index == 0


def test_basic_merging_within_limits(doc_metadata):
    """Given: Chunks that are close together and within the word limit.

    When: The chunk method is called.
    Then: The chunks should be merged into a single chunk.
    """
    merger = ChunkMerger(word_limit=20, max_vertical_gap=0.05)
    # Vertical gap = 0.16 - (0.1 + 0.05) = 0.01, which is < 0.05
    # Word count = 5 + 5 = 10, which is < 20
    chunk1 = create_atomic_chunk(
        "This is the first line.",
        page_number=1,
        top=0.1,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=0,
    )
    chunk2 = create_atomic_chunk(
        "This is a second line.",
        page_number=1,
        top=0.16,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=1,
    )
    atomic_chunks = [chunk1, chunk2]

    result = merger.group_and_merge_atomic_chunks(atomic_chunks)

    assert len(result) == 1
    merged_chunk = result[0]
    assert merged_chunk.chunk_text == "This is the first line. This is a second line."
    assert merged_chunk.page_number == 1
    # Check that the bounding box was correctly combined
    assert merged_chunk.bounding_box.top == 0.1
    assert merged_chunk.bounding_box.height == pytest.approx(0.11)  # 0.16 + 0.05 - 0.1


def test_flushes_on_word_limit_exceeded(doc_metadata):
    """Given: A chunk that would cause the buffer to exceed the word limit.

    When: The chunk method is called.
    Then: A new chunk should be created, splitting the content.
    """
    merger = ChunkMerger(word_limit=8, max_vertical_gap=0.05)
    # Chunk 1 has 5 words, buffer is at 5
    chunk1 = create_atomic_chunk(
        "This is the first line.",
        page_number=1,
        top=0.1,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=0,
    )
    # Chunk 2 has 5 words. 5 + 5 > 8, so it should flush.
    chunk2 = create_atomic_chunk(
        "This is a second line.",
        page_number=1,
        top=0.16,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=1,
    )
    atomic_chunks = [chunk1, chunk2]

    result = merger.group_and_merge_atomic_chunks(atomic_chunks)

    assert len(result) == 2
    assert result[0].chunk_text == "This is the first line."
    assert result[0].chunk_index == 0
    assert result[1].chunk_text == "This is a second line."
    assert result[1].chunk_index == 1


def test_flushes_on_large_positive_vertical_gap(doc_metadata):
    """Given: A chunk with a large vertical gap below the previous one.

    When: The chunk method is called.
    Then: A new chunk should be created.
    """
    merger = ChunkMerger(word_limit=20, max_vertical_gap=0.1)
    chunk1 = create_atomic_chunk(
        "This is a paragraph.",
        page_number=1,
        top=0.1,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=0,
    )
    # Large gap: top(0.3) - bottom(0.1 + 0.05) = 0.15, which is > 0.1
    chunk2 = create_atomic_chunk(
        "This is another paragraph.",
        page_number=1,
        top=0.3,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=1,
    )
    atomic_chunks = [chunk1, chunk2]

    result = merger.group_and_merge_atomic_chunks(atomic_chunks)

    assert len(result) == 2
    assert result[0].chunk_text == "This is a paragraph."
    assert result[1].chunk_text == "This is another paragraph."


def test_flushes_on_large_negative_vertical_gap_for_columns(doc_metadata):
    """Given: Chunks representing a jump from the bottom of one column to the top of another.

    When: The chunk method is called.
    Then: A new chunk should be created due to the large negative vertical gap.
    """
    merger = ChunkMerger(word_limit=50, max_vertical_gap=0.5)
    # Bottom of left column
    chunk1 = create_atomic_chunk(
        "End of column one.",
        page_number=1,
        top=0.8,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=0,
    )
    # Top of right column. Vertical gap = 0.1 - (0.8 + 0.05) = -0.75. abs(-0.75) > 0.5.
    chunk2 = create_atomic_chunk(
        "Start of column two.",
        page_number=1,
        top=0.1,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=1,
    )
    atomic_chunks = [chunk1, chunk2]

    result = merger.group_and_merge_atomic_chunks(atomic_chunks)

    assert len(result) == 2
    assert result[0].chunk_text == "End of column one."
    assert result[1].chunk_text == "Start of column two."


def test_flushes_on_page_change(doc_metadata):
    """Given: A sequence of chunks where one is on a different page.

    When: The chunk method is called.
    Then: A new chunk should be created when the page number changes.
    """
    merger = ChunkMerger(word_limit=50, max_vertical_gap=0.1)
    chunk1_p1 = create_atomic_chunk(
        "Text on page one.",
        page_number=1,
        top=0.1,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=0,
    )
    chunk2_p1 = create_atomic_chunk(
        "More text on page one.",
        page_number=1,
        top=0.2,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=1,
    )
    chunk3_p2 = create_atomic_chunk(
        "Text on page two.",
        page_number=2,
        top=0.1,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=2,
    )
    atomic_chunks = [chunk1_p1, chunk2_p1, chunk3_p2]

    result = merger.group_and_merge_atomic_chunks(atomic_chunks)

    assert len(result) == 2
    # First merged chunk contains both chunks from page 1
    assert result[0].chunk_text == "Text on page one. More text on page one."
    assert result[0].page_number == 1
    assert result[0].chunk_index == 0
    # Second merged chunk contains the chunk from page 2
    assert result[1].chunk_text == "Text on page two."
    assert result[1].page_number == 2
    assert result[1].chunk_index == 1


def test_final_buffer_is_flushed_correctly(doc_metadata):
    """Given: A sequence of chunks where the last items in the list should be grouped.

    When: The chunk method is called.
    Then: The final buffer contents should be processed into a final merged chunk.
    """
    merger = ChunkMerger(word_limit=20, max_vertical_gap=0.1)
    # These two will be grouped and flushed due to the third chunk's gap
    chunk1 = create_atomic_chunk(
        "First part.", page_number=1, top=0.1, height=0.05, metadata=doc_metadata, chunk_index=0
    )
    chunk2 = create_atomic_chunk(
        "Second part.", page_number=1, top=0.16, height=0.05, metadata=doc_metadata, chunk_index=1
    )
    # This will cause a flush and start a new buffer
    chunk3 = create_atomic_chunk(
        "A new section.", page_number=1, top=0.5, height=0.05, metadata=doc_metadata, chunk_index=2
    )
    # These two will be in the buffer at the end of the loop and should be flushed
    chunk4 = create_atomic_chunk(
        "Final words.", page_number=1, top=0.56, height=0.05, metadata=doc_metadata, chunk_index=3
    )
    atomic_chunks = [chunk1, chunk2, chunk3, chunk4]

    result = merger.group_and_merge_atomic_chunks(atomic_chunks)

    assert len(result) == 2
    assert result[0].chunk_text == "First part. Second part."
    assert result[1].chunk_text == "A new section. Final words."
    assert result[1].chunk_index == 1


def test_multiple_flush_conditions_in_sequence(doc_metadata):
    """Given: A complex sequence of chunks triggering all flush conditions.

    When: The chunk method is called.
    Then: The chunks should be grouped correctly according to the priority of flush rules.
    """
    merger = ChunkMerger(word_limit=10, max_vertical_gap=0.1)

    # Starts buffer (4 words)
    chunk1 = create_atomic_chunk("Line one is short.", 1, 0.1, 0.05, doc_metadata, 0)
    # Merges (4+5=9 words)
    chunk2 = create_atomic_chunk("Line two is also short.", 1, 0.16, 0.05, doc_metadata, 1)
    # FLUSHES (9+6 > 10 words). Creates chunk A. Starts buffer with chunk3.
    chunk3 = create_atomic_chunk("Line three breaks the limit.", 1, 0.22, 0.05, doc_metadata, 2)
    # FLUSHES (gap is 0.5 - 0.27 = 0.23 > 0.1). Creates chunk B. Starts buffer with chunk4.
    chunk4 = create_atomic_chunk("A new section after gap.", 1, 0.5, 0.05, doc_metadata, 3)
    # FLUSHES (page change). Creates chunk C. Starts buffer with chunk5.
    chunk5 = create_atomic_chunk("Text on the next page.", 2, 0.1, 0.05, doc_metadata, 4)
    # End of loop, FLUSHES final buffer. Creates chunk D.
    atomic_chunks = [chunk1, chunk2, chunk3, chunk4, chunk5]

    result = merger.group_and_merge_atomic_chunks(atomic_chunks)

    assert len(result) == 4
    assert result[0].chunk_text == "Line one is short. Line two is also short."
    assert result[0].chunk_index == 0

    assert result[1].chunk_text == "Line three breaks the limit."
    assert result[1].chunk_index == 1

    assert result[2].chunk_text == "A new section after gap."
    assert result[2].chunk_index == 2

    assert result[3].chunk_text == "Text on the next page."
    assert result[3].chunk_index == 3


def test_handles_atomic_chunk_already_over_limit(doc_metadata):
    """Given: An atomic chunk that is by itself larger than the word limit.

    When: The chunk method is called.
    Then: That chunk should be processed into its own single merged chunk.
    """
    merger = ChunkMerger(word_limit=10, max_vertical_gap=0.1)

    # This chunk has 12 words, which is over the limit of 10.
    oversized_chunk = create_atomic_chunk(
        "This is a single atomic chunk that is already over the word limit.",
        page_number=1,
        top=0.1,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=0,
    )
    # A subsequent chunk to ensure the oversized one is flushed correctly.
    next_chunk = create_atomic_chunk(
        "This is a normal chunk.",
        page_number=1,
        top=0.2,
        height=0.05,
        metadata=doc_metadata,
        chunk_index=1,
    )

    atomic_chunks = [oversized_chunk, next_chunk]
    result = merger.group_and_merge_atomic_chunks(atomic_chunks)

    # Expect two separate chunks
    assert len(result) == 2

    # The first chunk should be the oversized one, by itself.
    assert result[0].chunk_text == oversized_chunk.chunk_text
    assert result[0].chunk_index == 0
    assert result[0].word_count == 13

    # The second chunk should be the next one, by itself.
    assert result[1].chunk_text == next_chunk.chunk_text
    assert result[1].chunk_index == 1
