from abc import ABC, abstractmethod
from typing import List

from textractor.entities.bbox import BoundingBox

from data_models.chunk_models import DocumentMetadata, OpenSearchChunk
from document_chunker.utils.bbox_utils import combine_bounding_boxes


class ChunkingStrategyHandler(ABC):
    """Abstract base class for chunking strategies."""

    def __init__(self, maximum_chunk_size: int):
        self.maximum_chunk_size = maximum_chunk_size

    @abstractmethod
    def chunk(self, layout_block, page, metadata: DocumentMetadata, chunk_index_start: int) -> List[OpenSearchChunk]:
        """
        Extracts chunks from a single layout block based on the specific strategy.

        Args:
            layout_block: The Textractor LayoutBlock to process.
            page: The parent Page of the layout_block.
            metadata: Document metadata.
            chunk_index_start: The starting index for the chunks produced by this block.

        Returns:
            A list of OpenSearchChunk objects.
        """
        pass


class LineBasedChunkingHandler(ChunkingStrategyHandler):
    """Implements the line-based chunking strategy."""

    def chunk(self, layout_block, page, metadata: DocumentMetadata, chunk_index_start: int) -> List[OpenSearchChunk]:
        """Extract chunks using line-based splitting strategy."""
        chunks = []
        chunk_index = chunk_index_start

        current_chunk_lines = []
        current_chunk_bboxes = []

        for child_block in layout_block.children:
            line_text = child_block.text.strip()
            line_bbox = child_block.bbox

            if self._would_exceed_size_limit(current_chunk_lines, line_text):
                if current_chunk_lines:
                    chunk = self._create_chunk_from_lines(
                        current_chunk_lines, current_chunk_bboxes, layout_block, page, metadata, chunk_index
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    current_chunk_lines = []
                    current_chunk_bboxes = []

            current_chunk_lines.append(line_text)
            current_chunk_bboxes.append(line_bbox)

        if current_chunk_lines:
            chunk = self._create_chunk_from_lines(
                current_chunk_lines, current_chunk_bboxes, layout_block, page, metadata, chunk_index
            )
            chunks.append(chunk)

        return chunks

    def _would_exceed_size_limit(self, current_lines: List[str], new_line: str) -> bool:
        """Check if adding a new line would exceed the size limit."""
        if not current_lines:
            return len(new_line) > self.maximum_chunk_size
        combined_text = " ".join(current_lines + [new_line])
        return len(combined_text) > self.maximum_chunk_size

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
        combined_bbox = combine_bounding_boxes(bboxes)
        chunk_text = " ".join(lines)

        return OpenSearchChunk.from_textractor_layout_and_text(
            block=layout_block,
            page=page,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            combined_bbox=combined_bbox,
        )
