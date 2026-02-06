"""Implements the line-based chunking strategy."""

import logging
from typing import List, Optional

from textractor.entities.bbox import BoundingBox

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.strategies.base import ChunkingStrategyHandler
from ingestion_pipeline.chunking.utils.bbox_utils import combine_bounding_boxes

logger = logging.getLogger(__name__)


class LayoutTextChunkingStrategy(ChunkingStrategyHandler):
    """Implements the line-based chunking strategy."""

    def __init__(self, config: ChunkingConfig):
        """Initializes the line-based chunking strategy.

        Args:
            config (ChunkingConfig): Configuration for the chunking strategy.
        """
        super().__init__(config)

    def chunk(
        self,
        layout_block,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int,
        raw_response: Optional[dict] = None,
    ) -> List[DocumentChunk]:
        """Extract chunks using line-based splitting strategy.

        Args:
            layout_block (LayoutBlock): The Textractor LayoutBlock to process.
            page_number (int): The page number of the layout_block.
            metadata (DocumentMetadata): The document metadata.
            chunk_index_start (int): The starting index for the chunks produced by this block.
            raw_response (Optional[dict], optional): The raw response from Textract. Defaults to None.

        Returns:
            List[DocumentChunk]: The list of document chunks produced from the layout_block.
        """
        chunks = []
        chunk_index = chunk_index_start

        current_chunk_lines = []
        current_chunk_bboxes = []

        if page_number == 3:
            logger.info(f"Page number {page_number} Chunk index {chunk_index} - merging")

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
        """Check if adding a new line would exceed the size limit.

        Args:
            current_lines (List[str]): The current accumulated lines.
            new_line (str): The new line to add.

        Returns:
            bool: True if adding the new line would exceed the size limit, False otherwise.
        """
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
    ) -> DocumentChunk:
        """Creates a document chunk from the given lines and metadata.

        Args:
            lines (List[str]): The lines to include in the chunk.
            bboxes (List[BoundingBox]): The bounding boxes of the lines.
            layout_block (LayoutBlock): The Textractor LayoutBlock type.
            page_number (int): The page number of the layout block.
            metadata (DocumentMetadata): The document metadata.
            chunk_index (int): The index of the chunk.

        Returns:
            DocumentChunk: The created document chunk.
        """
        # Debug: Only log bounding boxes for page 3
        if page_number == 3:
            logger.info(
                f"[layout_text] Page {page_number} Chunk index {chunk_index} - bounding boxes before combine:")
            min_left = min(bbox.x for bbox in bboxes)
            min_top = min(bbox.y for bbox in bboxes)
            max_right = max(bbox.x + bbox.width for bbox in bboxes)
            max_bottom = max(bbox.y + bbox.height for bbox in bboxes)
            for i, bbox in enumerate(bboxes):
                logger.info(
                    f"  Line {i}: x={bbox.x}, y={bbox.y}, width={bbox.width}, height={bbox.height}, "
                    f"right={bbox.x + bbox.width}, bottom={bbox.y + bbox.height}"
                )
            logger.info(
                f"  Bounding box union: min_left={min_left}, min_top={min_top}, max_right={max_right}, max_bottom={max_bottom}, "
                f"union_width={max_right - min_left}, union_height={max_bottom - min_top}"
            )

        combined_bbox = combine_bounding_boxes(bboxes)
        chunk_text = " ".join(lines)

        logger.info(f"Layout {layout_block.layout_type} chunk : {chunk_text}")
        return DocumentChunk.from_textractor_layout(
            block=layout_block,
            page_number=page_number,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            combined_bbox=combined_bbox,
        )
