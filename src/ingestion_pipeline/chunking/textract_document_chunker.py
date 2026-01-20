"""Module for chunking Textractor documents into structured chunks."""

import logging
from typing import List, Mapping, Optional

from textractor.entities.document import Document

from ingestion_pipeline.chunking.exceptions import ChunkException
from ingestion_pipeline.chunking.strategies.merge.chunk_merger import ChunkMerger

from .chunking_config import ChunkingConfig
from .schemas import DocumentChunk, DocumentMetadata, ProcessedDocument
from .strategies.base import ChunkingStrategyHandler

logger = logging.getLogger(__name__)


class ChunkError(Exception):
    """Custom exception for chunking failures."""


class DocumentChunker:
    """Handles extraction of chunks from Textractor documents."""

    def __init__(
        self,
        strategy_handlers: Mapping[str, ChunkingStrategyHandler],
        config: Optional[ChunkingConfig] = None,
    ):
        """Initializes the DocumentChunker.

        Args:
            strategy_handlers (Mapping[str, ChunkingStrategyHandler]):
                Mapping of layout block types to their corresponding chunking strategy handlers.
            config (Optional[ChunkingConfig], optional): Configuration settings for chunking. Defaults to None.
        """
        self.config = config or ChunkingConfig()
        self.strategy_handlers = strategy_handlers

    def chunk(self, doc: Document, metadata: DocumentMetadata) -> ProcessedDocument:
        """Parses a Textractor Document and extracts specified layout blocks as structured chunks.

        Args:
            doc: Textractor Document to process
            metadata: Document metadata
        Returns:
            List of OpenSearchChunk objects

        Raises:
            ValueError: If metadata validation fails
            ChunkException: If chunk extraction fails
        """
        try:
            # Metadata is a Pydantic model, so its fields are validated on instantiation.
            # However, it's still useful to check that the document and its pages exist.
            self._validate_textract_document(doc)

            all_chunks = []
            chunk_index_counter = 0

            raw_response = doc.response

            if not raw_response:
                raise ChunkException(f"Response docment {metadata} missing raw response from Textract.")

            for page in doc.pages:
                logger.debug(f"Processing page {page.page_num} of {len(doc.pages)}")
                page_chunks = self._process_page(page, metadata, chunk_index_counter, raw_response)
                all_chunks.extend(page_chunks)
                chunk_index_counter += len(page_chunks)

            logger.info(f"Extracted {len(all_chunks)} chunks from {len(doc.pages)} pages")
            return ProcessedDocument(chunks=all_chunks)

        except Exception as e:
            logger.error(f"Error extracting chunks from document: {str(e)}")
            raise ChunkError(f"Error extracting chunks from document: {str(e)}") from e

    def _validate_textract_document(self, doc: Document) -> None:
        """Validate inputs before processing.

        Args:
            doc (Document): The Textractor document to process.

        Raises:
            ValueError: If the document or its pages are invalid.
        """
        if not doc or not doc.pages:
            raise ValueError("Document cannot be None and must contain pages.")

    def _process_page(
        self,
        page,
        metadata: DocumentMetadata,
        chunk_index_start: int,
        raw_response: Optional[dict],
    ) -> List[DocumentChunk]:
        """Process a single page and return its chunks.

        Args:
            page (DocumentPage): The page to process.
            metadata (DocumentMetadata): The metadata associated with the document.
            chunk_index_start (int): The starting index for chunking.
            raw_response (Optional[dict]): The raw response from Textract.

        Raises:
            ChunkException: If chunking fails.

        Returns:
            List[DocumentChunk]: The list of document chunks extracted from the page.
        """
        page_chunks = []
        current_chunk_index = chunk_index_start

        for layout_block in page.layouts:
            if self._should_process_block(layout_block, self.strategy_handlers):
                block_type = layout_block.layout_type
                chunking_strategy = self.strategy_handlers.get(block_type)

                if chunking_strategy is None:
                    logger.warning(f"No chunking strategy found for block type: {block_type}")
                    raise ChunkError(f"Block type {block_type} has no associated strategy handler")

                block_chunks = chunking_strategy.chunk(
                    layout_block, page.page_num, metadata, current_chunk_index, raw_response
                )

                page_chunks.extend(block_chunks)
                current_chunk_index += len(block_chunks)

        chunk_merger = ChunkMerger()
        grouped_chunks = chunk_merger.merge_chunks(page_chunks)

        return grouped_chunks

    def _should_process_block(self, layout_block, layout_types: Mapping[str, ChunkingStrategyHandler]) -> bool:
        """Determine if a layout block should be processed.

        Args:
            layout_block (layout_block): The layout block to check.
            layout_types (Mapping[str, ChunkingStrategyHandler]): The mapping of layout types to their handlers.

        Returns:
            bool: True if the block should be processed, False otherwise.
        """
        if not (
            layout_block.layout_type in layout_types
            and layout_block.text is not None
            and bool(layout_block.text.strip())
        ):
            block_text = layout_block.text if layout_block.text else "<No Text>"
            # Heavy logging for initial analysis of skipped blocks, will be removed later
            logger.info(f"Skipping layout block of type {layout_block.layout_type} {block_text.strip()}")
            return False

        return (
            layout_block.layout_type in layout_types
            and layout_block.text is not None
            and bool(layout_block.text.strip())
        )
