"""Document chunker using Textractor get_text_and_words() output."""

import logging
from typing import List, Optional

from textractor.entities.document import Document
from textractor.entities.word import Word

from ingestion_pipeline.chunking.chunk_strategy import ChunkError, ChunkStrategy
from ingestion_pipeline.chunking.exceptions import ChunkException
from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata, ProcessedDocument
from ingestion_pipeline.chunking.strategies.word_stream.chunker import TextractorWordStreamChunker
from ingestion_pipeline.chunking.strategies.word_stream.config import WordStreamChunkingConfig
from ingestion_pipeline.config import settings

logger = logging.getLogger(__name__)


class TextractorWordStreamDocumentChunker(ChunkStrategy):
    """Chunk documents using Textractor reading-order words from get_text_and_words()."""

    def __init__(self, config: Optional[WordStreamChunkingConfig] = None):
        """Initializes the TextractorWordStreamDocumentChunker.

        Args:
            config (Optional[WordStreamChunkingConfig], optional):
                Configuration for the word stream chunker. Defaults to None.
        """
        self.config = config or WordStreamChunkingConfig.from_settings(settings)
        self.chunker = TextractorWordStreamChunker(config=self.config)

    def chunk(self, doc: Document, metadata: DocumentMetadata) -> ProcessedDocument:
        """Extract chunks page-by-page from Textractor's word stream."""
        try:
            self._validate_textract_document(doc)
            self._validate_raw_response(doc, metadata)

            all_chunks: List[DocumentChunk] = []
            for page in doc.pages:
                page_chunks = self._process_page(page=page, metadata=metadata, chunk_index_start=0)
                all_chunks.extend(page_chunks)

            logger.info(
                "Word-stream chunking complete: %s chunks from %s pages",
                len(all_chunks),
                len(doc.pages),
            )
            return ProcessedDocument(chunks=all_chunks)
        except Exception as e:
            logger.error("Error extracting chunks from document using word-stream strategy: %s", str(e))
            raise ChunkError(f"Error extracting chunks from document using word-stream strategy: {str(e)}") from e

    @staticmethod
    def _validate_raw_response(doc: Document, metadata: DocumentMetadata) -> None:
        if not doc.response:
            raise ChunkException(f"Document {metadata.source_doc_id} missing raw response from Textract.")

    @staticmethod
    def _validate_textract_document(doc: Document) -> None:
        if not doc or not doc.pages:
            raise ValueError("Document cannot be None and must contain pages.")

    def _process_page(self, page, metadata: DocumentMetadata, chunk_index_start: int) -> List[DocumentChunk]:
        words = self._get_words_from_page(page)
        if not words:
            logger.info("Page %s has no words, skipping", page.page_num)
            return []

        return self.chunker.chunk_page(
            words=words,
            page_number=page.page_num,
            metadata=metadata,
            chunk_index_start=chunk_index_start,
        )

    @staticmethod
    def _get_words_from_page(page) -> List[Word]:
        if not hasattr(page, "get_text_and_words"):
            logger.warning("Page %s has no get_text_and_words method; returning no words", page.page_num)
            return []

        _, words = page.get_text_and_words()
        return words or []
