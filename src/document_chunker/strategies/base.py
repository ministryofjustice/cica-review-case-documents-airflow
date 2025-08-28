from abc import ABC, abstractmethod
from typing import List

from data_models.chunk_models import DocumentMetadata, OpenSearchChunk


class ChunkingStrategyHandler(ABC):
    """Abstract base class for chunking strategies."""

    def __init__(self, maximum_chunk_size: int):
        self.maximum_chunk_size = maximum_chunk_size

    @abstractmethod
    def chunk(
        self, layout_block, page_number: int, metadata: DocumentMetadata, chunk_index_start: int
    ) -> List[OpenSearchChunk]:
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
