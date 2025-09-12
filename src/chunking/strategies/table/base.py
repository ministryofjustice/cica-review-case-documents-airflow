import logging
from abc import ABC, abstractmethod
from typing import List, Optional

from textractor.entities.bbox import BoundingBox
from textractor.entities.layout import Layout

from src.chunking.config import ChunkingConfig
from src.chunking.schemas import DocumentMetadata, OpenSearchDocument

logger = logging.getLogger(__name__)


class BaseTableChunker(ABC):
    """Base class for table chunking strategies"""

    def __init__(self, config: ChunkingConfig):
        self.config = config

    @abstractmethod
    def can_handle(self, layout_block: Layout) -> bool:
        """Check if this chunker can handle the given layout block"""
        pass

    @abstractmethod
    def chunk(
        self,
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int,
        raw_response: Optional[dict] = None,
    ) -> List[OpenSearchDocument]:
        """Process the layout block into chunks"""
        pass

    def _create_chunk(
        self,
        chunk_text: str,
        bboxes: List[BoundingBox],
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index: int,
    ) -> OpenSearchDocument:
        """Create an OpenSearch document chunk."""
        combined_bbox = BoundingBox.enclosing_bbox(bboxes) if bboxes else layout_block.bbox

        logger.debug(f"Table chunk : {chunk_text}")

        return OpenSearchDocument.from_textractor_layout(
            block=layout_block,
            page_number=page_number,
            metadata=metadata,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            combined_bbox=combined_bbox,
        )
