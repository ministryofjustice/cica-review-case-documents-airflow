"""Example: Using the Line-by-Line Sentence Chunker.

This example demonstrates how to use the new LineSentenceChunker
to process pages directly using LINE blocks instead of LAYOUT blocks.
"""

import logging

from textractor.entities.document import Document

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.chunking.strategies.line_sentence_chunker import (
    LineSentenceChunker,
    LineSentenceChunkingConfig,
)
from ingestion_pipeline.config import settings

logger = logging.getLogger(__name__)


def example_usage_with_textractor_document(doc: Document, metadata: DocumentMetadata):
    """Example: Process a Textractor document with the new chunker.

    Args:
        doc: Textractor Document object
        metadata: Document metadata

    Returns:
        List of all chunks from all pages
    """
    # Create chunker with configuration from settings
    config = LineSentenceChunkingConfig(
        min_words=settings.SENTENCE_CHUNKER_MIN_WORDS,
        max_words=settings.SENTENCE_CHUNKER_MAX_WORDS,
        max_vertical_gap_ratio=settings.SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO,
        debug=True,  # Enable debug logging
    )
    chunker = LineSentenceChunker(config=config)

    # Process each page
    all_chunks = []
    chunk_index_counter = 0

    for page in doc.pages:
        # Access LINE blocks directly from the page
        lines = page.lines if hasattr(page, "lines") else []

        # Chunk this page
        page_chunks = chunker.chunk_page(
            lines=lines,
            page_number=page.page_num,
            metadata=metadata,
            chunk_index_start=chunk_index_counter,
        )

        all_chunks.extend(page_chunks)
        chunk_index_counter += len(page_chunks)

    logger.info(f"Processed {len(doc.pages)} pages, created {len(all_chunks)} chunks")
    return all_chunks


def example_usage_with_custom_config():
    """Example: Create a chunker with custom configuration.

    This shows how to override default settings for specific use cases.
    """
    # Custom configuration for smaller chunks with tighter sentence boundaries
    custom_config = LineSentenceChunkingConfig(
        min_words=50,  # Smaller minimum
        max_words=75,  # Smaller maximum
        max_vertical_gap_ratio=0.03,  # Tighter vertical gap threshold
        debug=True,
    )

    chunker = LineSentenceChunker(config=custom_config)
    return chunker


def example_integration_with_existing_pipeline(doc: Document, metadata: DocumentMetadata):
    """Example: Integrate with existing pipeline alongside other chunkers.

    This shows how you might use the new chunker in parallel with
    the existing layout-based approach for comparison.
    """
    # Initialize the new chunker
    line_chunker = LineSentenceChunker(
        LineSentenceChunkingConfig(
            min_words=settings.SENTENCE_CHUNKER_MIN_WORDS,
            max_words=settings.SENTENCE_CHUNKER_MAX_WORDS,
            max_vertical_gap_ratio=settings.SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO,
        )
    )

    # Process all pages with the line-based approach
    all_chunks = []
    chunk_index = 0

    for page in doc.pages:
        # Get lines from the page
        lines = page.lines if hasattr(page, "lines") else []

        # Chunk using line-by-line sentence approach
        page_chunks = line_chunker.chunk_page(
            lines=lines,
            page_number=page.page_num,
            metadata=metadata,
            chunk_index_start=chunk_index,
        )

        all_chunks.extend(page_chunks)
        chunk_index += len(page_chunks)

        logger.info(f"Page {page.page_num}: {len(lines)} lines -> {len(page_chunks)} chunks")

    return all_chunks


def example_extracting_lines_from_raw_response(raw_response: dict, page_number: int):
    """Example: Extract LINE blocks from raw Textract response if page.lines is not available.

    This is a fallback approach if the Textractor page object doesn't have
    the lines attribute populated.

    Args:
        raw_response: Raw response dictionary from Textract
        page_number: Page number to extract lines for

    Returns:
        List of mock line objects with text and bbox attributes
    """
    from unittest.mock import MagicMock

    from textractor.entities.bbox import BoundingBox

    lines = []
    blocks = raw_response.get("Blocks", [])

    for block in blocks:
        # Find LINE blocks for this page
        if block.get("BlockType") == "LINE" and block.get("Page") == page_number:
            # Extract geometry
            geometry = block.get("Geometry", {}).get("BoundingBox", {})
            bbox = BoundingBox(
                width=geometry.get("Width", 0),
                height=geometry.get("Height", 0),
                x=geometry.get("Left", 0),
                y=geometry.get("Top", 0),
            )

            # Create a mock Line object
            line = MagicMock()
            line.entity_id = block.get("Id", "")
            line.bbox = bbox
            line.confidence = block.get("Confidence", 0)
            line.text = block.get("Text", "")

            lines.append(line)

    return lines


if __name__ == "__main__":
    print("Line-by-Line Sentence Chunker Examples")
    print("=" * 60)
    print("\nThis file demonstrates how to use the new LineSentenceChunker.")
    print("\nKey features:")
    print("  - Word-based chunking (not character-based)")
    print("  - Respects sentence boundaries (. ? !)")
    print("  - Configurable min/max word counts")
    print("  - Vertical gap detection")
    print("  - Direct LINE block access (no LAYOUT blocks)")
    print("\nSee function examples above for usage patterns.")
