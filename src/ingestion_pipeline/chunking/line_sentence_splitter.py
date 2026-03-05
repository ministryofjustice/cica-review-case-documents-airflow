"""Line-based document chunker using sentence-aware chunking strategy.

This chunker processes pages using LINE blocks directly, bypassing layout detection.
It inherits from the base DocumentChunker class and uses the LineSentenceChunker
internally for deterministic, sentence-aware chunking.
"""

import logging
from typing import List, Optional

from textractor.entities.document import Document

from ingestion_pipeline.chunking.base_document_chunker import ChunkError, DocumentChunker
from ingestion_pipeline.chunking.exceptions import ChunkException
from ingestion_pipeline.chunking.layout_handler.strategies.line_sentence_chunker import (
    LineSentenceChunker,
    LineSentenceChunkingConfig,
)
from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata, ProcessedDocument
from ingestion_pipeline.config import settings

logger = logging.getLogger(__name__)


class LineBasedDocumentChunker(DocumentChunker):
    """Handles extraction of chunks from Textractor documents using line-based approach.

    This chunker processes documents page-by-page using LINE blocks directly,
    applying sentence-aware chunking logic. It inherits from DocumentChunker base
    class to ensure interface compatibility.
    """

    def __init__(self, config: Optional[LineSentenceChunkingConfig] = None):
        """Initializes the LineBasedDocumentChunker.

        Args:
            config: Configuration for line-based sentence chunking.
                    If None, uses settings from environment variables.
        """
        if config is None:
            # Load configuration from settings
            config = LineSentenceChunkingConfig(
                min_words=settings.SENTENCE_CHUNKER_MIN_WORDS,
                max_words=settings.SENTENCE_CHUNKER_MAX_WORDS,
                max_vertical_gap_ratio=settings.SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO,
                debug=False,  # Can be enabled via config parameter
            )

        self.config = config
        self.chunker = LineSentenceChunker(config=config)

    def chunk(self, doc: Document, metadata: DocumentMetadata) -> ProcessedDocument:
        """Parses a Textractor Document and extracts LINE blocks as structured chunks.

        Processes all pages in the document using line-by-line sentence-aware chunking.
        Unlike layout-based chunking, this approach works directly with LINE blocks
        to ensure sentence integrity and accurate bounding boxes.

        Args:
            doc: Textractor Document containing pages and LINE blocks to process.
            metadata: Document metadata including source file information.

        Returns:
            ProcessedDocument: Container with the list of extracted DocumentChunk objects.

        Raises:
            ValueError: If the document is None or contains no pages.
            ChunkException: If required data is missing from the document.
            ChunkError: If chunk extraction fails during processing.
        """
        try:
            # Validate the document structure
            self._validate_textract_document(doc)

            all_chunks = []
            chunk_index_counter = 0

            # Verify raw response exists (needed for compatibility checks)
            if not doc.response:
                raise ChunkException(f"Document {metadata.source_doc_id} missing raw response from Textract.")

            # Process each page
            for page in doc.pages:
                logger.debug(f"Chunking page {page.page_num} of {len(doc.pages)} using line-based approach")

                page_chunks = self._process_page(
                    page=page,
                    metadata=metadata,
                    chunk_index_start=chunk_index_counter,
                )

                all_chunks.extend(page_chunks)
                chunk_index_counter += len(page_chunks)

                logger.debug(
                    f"Extracted {len(page_chunks)} chunks from page {page.page_num} "
                    f"(total: {len(all_chunks)} chunks from {page.page_num}/{len(doc.pages)} pages)"
                )

            logger.info(f"Line-based chunking complete: {len(all_chunks)} chunks from {len(doc.pages)} pages")
            return ProcessedDocument(chunks=all_chunks)

        except Exception as e:
            logger.error(f"Error extracting chunks from document: {str(e)}")
            raise ChunkError(f"Error extracting chunks from document: {str(e)}") from e

    def _validate_textract_document(self, doc: Document) -> None:
        """Validate inputs before processing.

        Args:
            doc: The Textractor document to process.

        Raises:
            ValueError: If the document or its pages are invalid.
        """
        if not doc or not doc.pages:
            raise ValueError("Document cannot be None and must contain pages.")

        # Check if pages have lines (warn but don't fail - will handle empty pages)
        pages_without_lines = sum(1 for page in doc.pages if not hasattr(page, "lines") or not page.lines)
        if pages_without_lines > 0:
            logger.warning(
                f"{pages_without_lines} of {len(doc.pages)} pages have no lines attribute or empty lines. "
                "These pages will produce no chunks."
            )

    def _process_page(
        self,
        page,
        metadata: DocumentMetadata,
        chunk_index_start: int,
    ) -> List[DocumentChunk]:
        """Process a single page and return its chunks.

        Args:
            page: The page object from Textractor containing LINE blocks.
            metadata: The metadata associated with the document.
            chunk_index_start: The starting index for chunk numbering.

        Returns:
            List[DocumentChunk]: The list of document chunks extracted from the page.

        Raises:
            ChunkError: If chunking fails for the page.
        """
        try:
            # Extract LINE blocks from the page
            lines = self._get_lines_from_page(page)

            if not lines:
                logger.info(f"Page {page.page_num} has no lines, skipping")
                return []

            # Use LineSentenceChunker to process the lines
            page_chunks = self.chunker.chunk_page(
                lines=lines,
                page_number=page.page_num,
                metadata=metadata,
                chunk_index_start=chunk_index_start,
            )

            logger.debug(
                f"Page {page.page_num}: {len(lines)} lines -> {len(page_chunks)} chunks "
                f"(word counts: {[chunk.word_count for chunk in page_chunks]})"
            )

            return page_chunks

        except Exception as e:
            logger.error(f"Error processing page {page.page_num}: {str(e)}")
            raise ChunkError(f"Error processing page {page.page_num}: {str(e)}") from e

    def _get_lines_from_page(self, page) -> List:
        """Extract LINE blocks from a page.

        Args:
            page: The Textractor page object.

        Returns:
            List of Line objects from the page.
        """
        # First try to get lines from page.lines attribute
        if hasattr(page, "lines") and page.lines:
            return page.lines

        # Fallback: If page.lines is not available, return empty list
        # In production, you might want to extract from raw response here
        logger.warning(
            f"Page {page.page_num} does not have lines attribute or it's empty. "
            "Consider extracting from raw response if needed."
        )
        return []
