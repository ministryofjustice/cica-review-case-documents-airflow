from abc import ABC, abstractmethod
from typing import List, Optional

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig  # ← Changed import
from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata


class ChunkingStrategyHandler(ABC):
    """Abstract base class for chunking strategies."""

    def __init__(self, config: ChunkingConfig):
        self.config = config
        self.maximum_chunk_size = config.maximum_chunk_size

    @abstractmethod
    def chunk(
        self,
        layout_block,
        page_number: int,
        metadata: DocumentMetadata,
        chunk_index_start: int,
        raw_response: Optional[dict],
    ) -> List[DocumentChunk]:
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
