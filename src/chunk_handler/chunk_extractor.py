import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Set

from textractor.entities.bbox import BoundingBox
from textractor.entities.document import Document

from data_models.chunk_models import DocumentMetadata, OpenSearchChunk

logger = logging.getLogger(__name__)


class ChunkingStrategy(Enum):
    """Available chunking strategies."""

    LINE_BASED = "line_based"
    # SENTENCE_BASED = "sentence_based"
    # TOKEN_BASED = "token_based"


@dataclass
class ChunkingConfig:
    """Configuration for chunking behavior."""

    maximum_chunk_size: int = 1000
    strategy: ChunkingStrategy = ChunkingStrategy.LINE_BASED


class ChunkExtractor:
    """Handles extraction of chunks from Textractor documents."""

    def __init__(self, config: Optional[ChunkingConfig] = None):
        self.config = config or ChunkingConfig()

    def extract_layout_chunks(
        self, doc: Document, metadata: DocumentMetadata, desired_layout_types: Optional[Set[str]] = None
    ) -> List[OpenSearchChunk]:
        """
        Parses a Textractor Document and extracts specified layout blocks as structured chunks.

        Args:
            doc: Textractor Document to process
            metadata: Document metadata
            desired_layout_types: Set of layout types to extract (defaults to {"LAYOUT_TEXT"})

        Returns:
            List of OpenSearchChunk objects

        Raises:
            ValueError: If metadata validation fails
        """
        try:
            self._validate_inputs(doc, metadata)

            if desired_layout_types is None:
                desired_layout_types = {"LAYOUT_TEXT"}

            chunks = []
            chunk_index_counter = 0

            for page in doc.pages:
                page_chunks = self._process_page(page, metadata, desired_layout_types, chunk_index_counter)
                chunks.extend(page_chunks)
                chunk_index_counter += len(page_chunks)

            logger.info(f"Extracted {len(chunks)} chunks from document {metadata.ingested_doc_id}")
            return chunks

        except Exception as e:
            logger.error(f"Error extracting chunks from document {metadata.ingested_doc_id}: {str(e)}")
            raise

    def _validate_inputs(self, doc: Document, metadata: DocumentMetadata) -> None:
        """Validate inputs before processing."""
        if not doc or not doc.pages:
            raise ValueError("Document cannot be None and must contain pages.")

        # Metadata validation is now handled in DocumentMetadata.__post_init__

    def _process_page(
        self, page, metadata: DocumentMetadata, desired_layout_types: Set[str], chunk_index_start: int
    ) -> List[OpenSearchChunk]:
        """Process a single page and return its chunks."""
        chunks = []
        chunk_index = chunk_index_start

        for layout_block in page.layouts:
            if self._should_process_block(layout_block, desired_layout_types):
                block_chunks = self._extract_chunks_from_block(layout_block, page, metadata, chunk_index)
                chunks.extend(block_chunks)
                chunk_index += len(block_chunks)

        return chunks

    def _should_process_block(self, layout_block, desired_layout_types: Set[str]) -> bool:
        """Determine if a layout block should be processed."""
        return layout_block.layout_type in desired_layout_types and layout_block.text and layout_block.text.strip()

    def _extract_chunks_from_block(
        self, layout_block, page, metadata: DocumentMetadata, chunk_index_start: int
    ) -> List[OpenSearchChunk]:
        """Extract chunks from a layout block using the configured strategy."""
        if self.config.strategy == ChunkingStrategy.LINE_BASED:
            return self._extract_line_based_chunks(layout_block, page, metadata, chunk_index_start)
        else:
            # Future: implement other strategies
            raise NotImplementedError(f"Strategy {self.config.strategy} not yet implemented")

    def _extract_line_based_chunks(
        self, layout_block, page, metadata: DocumentMetadata, chunk_index_start: int
    ) -> List[OpenSearchChunk]:
        """Extract chunks using line-based splitting strategy."""
        chunks = []
        chunk_index = chunk_index_start

        current_chunk_lines = []
        current_chunk_bboxes = []

        for child_block in layout_block.children:
            line_text = child_block.text.strip()
            if not line_text:  # Skip empty lines
                continue

            line_bbox = child_block.bbox

            # Check if adding the new line would exceed the maximum chunk size
            if self._would_exceed_size_limit(current_chunk_lines, line_text):
                # Finalize the current chunk if it's not empty
                if current_chunk_lines:
                    chunk = self._create_chunk_from_lines(
                        current_chunk_lines, current_chunk_bboxes, layout_block, page, metadata, chunk_index
                    )
                    chunks.append(chunk)
                    chunk_index += 1

                    current_chunk_lines = []
                    current_chunk_bboxes = []

            # Add the current line
            current_chunk_lines.append(line_text)
            current_chunk_bboxes.append(line_bbox)

        # Create final chunk if there are remaining lines
        if current_chunk_lines:
            chunk = self._create_chunk_from_lines(
                current_chunk_lines, current_chunk_bboxes, layout_block, page, metadata, chunk_index
            )
            chunks.append(chunk)

        return chunks

    def _would_exceed_size_limit(self, current_lines: List[str], new_line: str) -> bool:
        """Check if adding a new line would exceed the size limit."""
        if not current_lines:
            return False

        combined_text = " ".join(current_lines + [new_line])
        return len(combined_text) > self.config.maximum_chunk_size

    def _create_chunk_from_lines(
        self,
        lines: List[str],
        bboxes: List[BoundingBox],
        layout_block,
        page,
        metadata: DocumentMetadata,
        chunk_index: int,
    ) -> OpenSearchChunk:
        """Create a chunk from accumulated lines and bounding boxes."""
        combined_bbox = self._combine_bounding_boxes(bboxes)
        chunk_text = " ".join(lines)

        return OpenSearchChunk.from_textractor_layout_and_text(
            block=layout_block,
            page=page,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            combined_bbox=combined_bbox,
        )

    @staticmethod
    def _combine_bounding_boxes(bboxes: Sequence[BoundingBox]) -> BoundingBox:
        """Combines a list of BoundingBox objects into a single encompassing BoundingBox."""
        if not bboxes:
            raise ValueError("Bounding box combination requires at least one box.")

        min_left = min(bbox.x for bbox in bboxes)
        min_top = min(bbox.y for bbox in bboxes)
        max_right = max(bbox.x + bbox.width for bbox in bboxes)
        max_bottom = max(bbox.y + bbox.height for bbox in bboxes)

        new_width = max_right - min_left
        new_height = max_bottom - min_top

        return BoundingBox(
            width=new_width,
            height=new_height,
            x=min_left,
            y=min_top,
        )


# Convenience function for backward compatibility
def extract_layout_chunks(
    doc: Document,
    metadata: DocumentMetadata,
    desired_layout_types: Optional[Set[str]] = None,
    config: Optional[ChunkingConfig] = None,
) -> List[OpenSearchChunk]:
    """
    Legacy function wrapper for the ChunkExtractor class.

    Deprecated: Use ChunkExtractor class directly for better control.
    """
    extractor = ChunkExtractor(config)
    return extractor.extract_layout_chunks(doc, metadata, desired_layout_types)
