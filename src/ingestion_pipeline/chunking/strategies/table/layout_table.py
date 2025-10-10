import logging
from typing import List, Optional

from textractor.entities.layout import Layout, Line
from textractor.entities.table import Table

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.exceptions import ChunkException
from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata
from ingestion_pipeline.chunking.strategies.base import ChunkingStrategyHandler
from ingestion_pipeline.chunking.strategies.table.base import BaseTableChunker

from .cell_chunker import CellTableChunker
from .line_chunker import LineTableChunker

logger = logging.getLogger(__name__)


class LayoutTableChunkingStrategy(ChunkingStrategyHandler):
    """
    Main strategy class that delegates to appropriate table chunkers.
    Handles both cell-based and line-based layout_table structures.
    """

    def __init__(self, config: ChunkingConfig):
        super().__init__(config)
        self._chunkers = {
            "line": LineTableChunker,
            "cell": CellTableChunker,
        }

    def chunk(
        self,
        layout_block: Layout,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int,
        raw_response: Optional[dict] = None,
    ) -> List[DocumentChunk]:
        """Main chunking method that detects table structure and dispatches appropriately."""
        if not layout_block.children:
            # This is a fatal anomaly. A table block should have content.
            raise ChunkException(
                f"Layout table block {layout_block.id} {layout_block.layout_type} has no children. "
                "This indicates a parsing error."
            )

        try:
            chunker_type = self._determine_chunker_type(layout_block)
        except Exception as e:
            logger.error(
                f"Error determining chunker type for block {layout_block.id} {layout_block.layout_type}: {str(e)}"
            )
            raise ChunkException(f"Error determining chunker type for block {layout_block.id}: {str(e)}")

        chunker = self._get_chunker(chunker_type)
        logger.debug(
            f"Selected {chunker.__class__.__name__} for block: {layout_block.id} type: {layout_block.layout_type}"
        )

        return chunker.chunk(layout_block, page_number, metadata, chunk_index_start, raw_response)

    def _determine_chunker_type(self, layout_block: Layout) -> str:
        """
        Strtagey selection logic for determining which chunker to use.
        """
        first_child = layout_block.children[0]

        if isinstance(first_child, Line):
            return "line"
        elif isinstance(first_child, Table):
            return "cell"
        else:
            child_type = type(first_child).__name__
            raise ChunkException(
                f"Unsupported {layout_block.layout_type} structure in block {layout_block.id}. "
                f"Children are of type '{child_type}', which is not supported."
            )

    def _get_chunker(self, chunker_type: str) -> BaseTableChunker:
        """Get chunker instance for the specified type."""
        if chunker_type not in self._chunkers:
            raise ChunkException(f"Unknown chunker type: {chunker_type}")

        chunker_class = self._chunkers[chunker_type]
        return chunker_class(self.config)
