"""Chunk creation and building logic."""

import logging
from typing import List, Tuple

from textractor.entities.bbox import BoundingBox

from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.strategies.line_sentence.config import LineSentenceChunkingConfig
from ingestion_pipeline.chunking.utils.bbox_utils import combine_bounding_boxes

logger = logging.getLogger(__name__)


class ChunkBuilder:
    """Builds DocumentChunk objects from accumulated lines."""

    def __init__(self, config: LineSentenceChunkingConfig):
        """Initialize the chunk builder.

        Args:
            config: Chunking configuration
        """
        self.config = config

    def create_chunk(
        self,
        lines: List[Tuple[str, BoundingBox]],
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index: int,
    ) -> DocumentChunk:
        """Create a DocumentChunk from accumulated lines.

        Args:
            lines: List of (text, bbox) tuples
            page_number: Page number
            metadata: Document metadata
            chunk_index: Index for this chunk

        Returns:
            DocumentChunk instance
        """
        # Combine text with spaces
        chunk_text = " ".join(text for text, _ in lines)

        # Extract bounding boxes and create enclosing bbox
        bboxes = [bbox for _, bbox in lines]
        combined_bbox = combine_bounding_boxes(bboxes)

        if logger.isEnabledFor(logging.DEBUG):
            word_count = len(chunk_text.split())
            logger.debug(
                f"Page {page_number}, Chunk {chunk_index}: "
                f"{len(lines)} lines, {word_count} words, text='{chunk_text[:50]}...'"
            )

        # Create chunk with layout type and confidence
        # The original confidence value represents a Textract Layout Block
        # confidence score, it has no meaning in this context.
        # It is not used anywat
        # TODO review and potentially remove
        return DocumentChunk.create_chunk(
            layout_type="LINE_SENTENCE_CHUNK",
            confidence=None,  # see the comment
            page_number=page_number,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            combined_bbox=combined_bbox,
        )
