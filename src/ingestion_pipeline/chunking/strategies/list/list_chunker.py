"""Chunking strategy for LAYOUT_LIST blocks."""

import logging
from typing import List, Optional

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.strategies.base import ChunkingStrategyHandler
from ingestion_pipeline.chunking.utils.bbox_utils import combine_bounding_boxes

logger = logging.getLogger(__name__)


class LayoutListChunkingStrategy(ChunkingStrategyHandler):
    """Chunking strategy for LAYOUT_LIST blocks.

    Args:
        ChunkingStrategyHandler (ChunkingStrategyHandler): The base chunking strategy handler.

    Returns:
        LayoutListChunkingStrategy: An instance of the list chunking strategy.

    """

    def __init__(self, config: ChunkingConfig):
        """Chunking strategy for LAYOUT_LIST blocks.

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
        """Chunking strategy for LAYOUT_LIST blocks.

        Args:
            layout_block (LayoutBlock): The LAYOUT_LIST block to be chunked.
            page_number (int): The page number of the document.
            metadata (DocumentMetadata): Metadata associated with the document.
            chunk_index_start (int): The starting index for the chunk.
            raw_response (Optional[dict], optional): The raw response from the layout analysis. Defaults to None.

        Returns:
            List[DocumentChunk]: A list of DocumentChunks representing the list items.
        """
        chunks = []
        chunk_index = chunk_index_start

        for child_block in layout_block.children:
            if child_block.layout_type != "LAYOUT_TEXT":
                text_content = getattr(child_block, "text", "[text attribute not found]")
                logger.warning(
                    f"Skipping unexpected list child block of type "
                    f"{type(child_block).__name__} in LAYOUT_KEY_VALUE block {layout_block.id}. "
                    f"Text: {text_content}"
                )
                continue

            line_text = child_block.text.strip()
            line_bbox = child_block.bbox

            if not line_text:
                continue

            combined_bbox = combine_bounding_boxes([line_bbox])
            chunk = DocumentChunk.from_textractor_layout(
                block=layout_block,
                page_number=page_number,
                metadata=metadata,
                chunk_index=chunk_index,
                chunk_text=line_text,
                combined_bbox=combined_bbox,
            )
            chunks.append(chunk)
            chunk_index += 1

        return chunks
