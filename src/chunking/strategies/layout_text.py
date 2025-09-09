import logging
from typing import List, Optional

from textractor.entities.bbox import BoundingBox

from src.chunking.config import ChunkingConfig
from src.chunking.schemas import DocumentMetadata, OpenSearchDocument
from src.chunking.strategies.base import ChunkingStrategyHandler
from src.chunking.utils.bbox_utils import combine_bounding_boxes

logger = logging.getLogger(__name__)


class LayoutTextChunkingStrategy(ChunkingStrategyHandler):
    """Implements the line-based chunking strategy."""

    def __init__(self, config: ChunkingConfig):
        super().__init__(config)

    def chunk(
        self,
        layout_block,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int,
        raw_response: Optional[dict] = None,
    ) -> List[OpenSearchDocument]:
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
                        current_chunk_lines, current_chunk_bboxes, layout_block, page_number, metadata, chunk_index
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    current_chunk_lines = []
                    current_chunk_bboxes = []

            current_chunk_lines.append(line_text)
            current_chunk_bboxes.append(line_bbox)

        if current_chunk_lines:
            chunk = self._create_chunk_from_lines(
                current_chunk_lines, current_chunk_bboxes, layout_block, page_number, metadata, chunk_index
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
        page_number,
        metadata: DocumentMetadata,
        chunk_index: int,
    ) -> OpenSearchDocument:
        """Create a chunk from accumulated lines and bounding boxes."""
        combined_bbox = combine_bounding_boxes(bboxes)
        chunk_text = " ".join(lines)

        logger.debug(f"{chunk_text}")

        return OpenSearchDocument.from_textractor_layout(
            block=layout_block,
            page_number=page_number,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            combined_bbox=combined_bbox,
        )
