import logging
from typing import List, Optional

from textractor.entities.layout import Layout

from src.chunking.config import ChunkingConfig
from src.chunking.schemas import DocumentMetadata, OpenSearchDocument
from src.chunking.strategies.base import ChunkingStrategyHandler

from .cell_chunker import CellTableChunker
from .line_chunker import LineTableChunker

logger = logging.getLogger(__name__)


class LayoutTableChunkingStrategy(ChunkingStrategyHandler):
    """
    Main strategy class that delegates to appropriate table chunkers.
    Handles both cell-based and line-based table structures.
    """

    def __init__(self, config: ChunkingConfig):
        super().__init__(config)
        self._chunkers = [
            CellTableChunker(self.config),
            LineTableChunker(self.config),
        ]

    def chunk(
        self,
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int,
        raw_response: Optional[dict] = None,
    ) -> List[OpenSearchDocument]:
        """Main chunking method that detects table structure and dispatches appropriately."""
        if not layout_block.children:
            logger.warning(f"Layout table block {layout_block.id} has no children")
            return []

        # Find appropriate chunker
        for chunker in self._chunkers:
            if chunker.can_handle(layout_block):
                return chunker.chunk(layout_block, page_number, metadata, chunk_index_start, raw_response)

        logger.warning(f"No suitable chunker found for block {layout_block.id}")
        return []
