"""Strategy for chunking layout_table structures."""

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
    """Main strategy class that delegates to appropriate table chunkers.

    Args:
        ChunkingStrategyHandler (ChunkingStrategyHandler): The base class for chunking strategy handlers.

    Returns:
        LayoutTableChunkingStrategy: An instance of the layout table chunking strategy.
    """

    def __init__(self, config: ChunkingConfig):
        """Initialize the layout table chunking strategy.

        Args:
            config (ChunkingConfig): The configuration for chunking.
        """
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
        """Main chunking method that detects table structure and dispatches appropriately.

        Args:
            layout_block (Layout): The layout block to process.
            page_number (int): The page number of the layout block.
            metadata (DocumentMetadata): The metadata associated with the document.
            chunk_index_start (int): The starting index for chunk numbering.
            raw_response (Optional[dict], optional): The raw response from the layout analysis. Defaults to None.

        Raises:
            ChunkException: The layout table block has no children, indicating a parsing error.
            ChunkException: Error determining chunker type for block {layout_block.id}
            ChunkException: Unsupported layout_type structure in block {layout_block.id}.
                Children are of type 'child_type', which is not supported.
            ChunkException: Unknown chunker type: chunker_type

        Returns:
            List[DocumentChunk]: The list of document chunks created from the layout block.
        """
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
        """Determine the chunker type based on the layout block's children.

        Args:
            layout_block (Layout): The layout block to analyze.

        Raises:
            ChunkException: If the layout block's structure is unsupported.

        Returns:
            str: The determined chunker type.
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
        """Get chunker instance for the specified type.

        Args:
            chunker_type (str): The type of chunker to retrieve.

        Raises:
            ChunkException: If the chunker type is unknown.

        Returns:
            BaseTableChunker: The chunker instance for the specified type.
        """
        if chunker_type not in self._chunkers:
            raise ChunkException(f"Unknown chunker type: {chunker_type}")

        chunker_class = self._chunkers[chunker_type]
        return chunker_class(self.config)
