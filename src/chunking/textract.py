import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set

from textractor.entities.document import Document

from src.config import settings

from .schemas import DocumentMetadata, OpenSearchDocument
from .strategies.base import ChunkingStrategyHandler
from .strategies.line_based import LineBasedChunkingStrategy

logger = logging.getLogger(__name__)


class ChunkingStrategy(Enum):
    """Available chunking strategies."""

    LINE_BASED = "line_based"
    # SENTENCE_BASED = "sentence_based"
    # TOKEN_BASED = "token_based"


@dataclass
class ChunkingConfig:
    """Configuration for chunking behavior."""

    maximum_chunk_size: int = settings.MAXIMUM_CHUNK_SIZE
    strategy: ChunkingStrategy = ChunkingStrategy.LINE_BASED


class TextractDocumentChunker:
    """Handles extraction of chunks from Textractor documents."""

    def __init__(self, config: Optional[ChunkingConfig] = None):
        self.config = config or ChunkingConfig()
        self.strategy_handlers = self._create_strategy_handlers()
        # A default handler for any types not explicitly mapped
        self.default_strategy = self._create_default_strategy()

    def _create_strategy_handlers(self) -> Dict[str, ChunkingStrategyHandler]:
        """Factory method for creating strategy handlers."""
        # This centralizes handler creation, making it easier to override in tests
        return {
            "LAYOUT_TEXT": LineBasedChunkingStrategy(self.config.maximum_chunk_size),
            # "LAYOUT_TABLE": TableChunkingHandler(self.config.maximum_chunk_size),
            # "LAYOUT_LIST": ListChunkingHandler(self.config.maximum_chunk_size),
        }

    def _create_default_strategy(self) -> ChunkingStrategyHandler:
        """Factory method for the default handler."""
        return LineBasedChunkingStrategy(self.config.maximum_chunk_size)

    def chunk(
        self, doc: Document, metadata: DocumentMetadata, desired_layout_types: Optional[Set[str]] = None
    ) -> List[OpenSearchDocument]:
        """
        Parses a Textractor Document and extracts specified layout blocks as structured chunks.

        Args:
            doc: Textractor Document to process
            metadata: Document metadata
            desired_layout_types: Set of layout types to extract (defaults to {"LAYOUT_TEXT"})

        Returns:
            List of OpenSearchChunk objects

        Raises:
            ValueError: If metadata validation fails
        """
        try:
            self._validate_inputs(doc, metadata)

            if desired_layout_types is None:
                desired_layout_types = {"LAYOUT_TEXT"}

            all_chunks = []
            chunk_index_counter = 0

            for page in doc.pages:
                page_chunks = self._process_page(page, metadata, desired_layout_types, chunk_index_counter)
                all_chunks.extend(page_chunks)
                chunk_index_counter += len(page_chunks)

            logger.info(f"Extracted {len(all_chunks)} chunks from document {metadata.ingested_doc_id}")
            return all_chunks

        except Exception as e:
            logger.error(f"Error extracting chunks from document {metadata.ingested_doc_id}: {str(e)}")
            raise

    def _validate_inputs(self, doc: Document, metadata: DocumentMetadata) -> None:
        """Validate inputs before processing."""
        if not doc or not doc.pages:
            raise ValueError("Document cannot be None and must contain pages.")

    def _process_page(
        self, page, metadata: DocumentMetadata, desired_layout_types: Set[str], chunk_index_start: int
    ) -> List[OpenSearchDocument]:
        """Process a single page and return its chunks."""
        page_chunks = []
        current_chunk_index = chunk_index_start

        for layout_block in page.layouts:
            if self._should_process_block(layout_block, desired_layout_types):
                block_type = layout_block.layout_type
                chunking_strategy = self.strategy_handlers.get(block_type, self.default_strategy)

                block_chunks = chunking_strategy.chunk(layout_block, page.page_num, metadata, current_chunk_index)

                page_chunks.extend(block_chunks)
                current_chunk_index += len(block_chunks)

        return page_chunks

    def _should_process_block(self, layout_block, desired_layout_types: Set[str]) -> bool:
        """Determine if a layout block should be processed."""
        return layout_block.layout_type in desired_layout_types and layout_block.text and layout_block.text.strip()
