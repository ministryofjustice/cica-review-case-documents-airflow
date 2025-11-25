"""Base class for table chunking strategies."""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional

from textractor.entities.bbox import BoundingBox
from textractor.entities.layout import Layout

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata

logger = logging.getLogger(__name__)


class BaseTableChunker(ABC):
    """Base class for table chunking strategies.

    Args:
        ABC (ABC): Abstract base class for table chunkers.

    Returns:
        ABC: An instance of a table chunker.
    """

    def __init__(self, config: ChunkingConfig):
        """Initializes the base table chunker.

        Args:
            config (ChunkingConfig): Configuration for the chunking strategy.
        """
        self.config = config

    @abstractmethod
    def chunk(
        self,
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        # TODO review the chunk index start usage and chunk id generation
        chunk_index_start: int,
        raw_response: Optional[dict] = None,
    ) -> List[DocumentChunk]:
        """Processes the layout block into chunks.

        Args:
            layout_block (Layout): The table layout block to be chunked.
            page_number (int): The page number of the layout block.
            metadata (DocumentMetadata): The metadata associated with the document.
            chunk_index_start (int): The starting index for chunk numbering.
            raw_response (Optional[dict], optional): Raw response from the source. Defaults to None.

        Returns:
            List[DocumentChunk]: A list of document chunks created from the layout block.
        """
        pass

    def _create_chunk(
        self,
        chunk_text: str,
        bboxes: List[BoundingBox],
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index: int,
    ) -> DocumentChunk:
        """Creates a document chunk from the provided parameters.

        Args:
            chunk_text (str): The text content of the chunk.
            bboxes (List[BoundingBox]): The bounding boxes associated with the chunk.
            layout_block (Layout): The original layout block.
            page_number (int): The page number of the layout block.
            metadata (DocumentMetadata): The metadata associated with the document.
            chunk_index (int): The index of the chunk within the layout block.

        Returns:
            DocumentChunk: A document chunk created from the provided parameters.
        """
        combined_bbox = BoundingBox.enclosing_bbox(bboxes) if bboxes else layout_block.bbox

        logger.debug(f"Table chunk : {chunk_text}")

        return DocumentChunk.from_textractor_layout(
            block=layout_block,
            page_number=page_number,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            combined_bbox=combined_bbox,
        )
