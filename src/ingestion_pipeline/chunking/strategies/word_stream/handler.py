"""Document chunker using Textractor get_text_and_words() output."""

import logging
import re
from typing import List, Optional

from textractor.data.constants import TextTypes
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
        words, page_text_from_source = self._get_words_from_page(page)
        if not words:
            logger.info("Page %s has no words, skipping", page.page_num)
            return []

        page_contains_handwriting = self._detect_handwriting(words)
        if page_contains_handwriting:
            logger.debug("Page %s flagged as containing handwriting", page.page_num)

        page_chunks = self.chunker.chunk_page(
            words=words,
            page_number=page.page_num,
            metadata=metadata,
            chunk_index_start=chunk_index_start,
            page_contains_handwriting=page_contains_handwriting,
        )
        self._validate_text_consistency(page_text_from_source, page_chunks, page.page_num)
        return page_chunks

    @staticmethod
    def _detect_handwriting(words: List[Word]) -> bool:
        """Determine whether any word on the page is handwritten.

        Args:
            words: The list of Word entities from a page.

        Returns:
            True if at least one word has text_type == TextTypes.HANDWRITING.
        """
        handwriting_detected = False
        for word in words:
            if getattr(word, "text_type", None) == TextTypes.HANDWRITING:
                word_text = getattr(word, "text", "")
                word_bbox = getattr(word, "bbox", None)
                logger.debug(
                    "Handwriting detected: word='%s' bbox=%s",
                    word_text,
                    f"(x={word_bbox.x:.4f}, y={word_bbox.y:.4f}, w={word_bbox.width:.4f}, h={word_bbox.height:.4f})"
                    if word_bbox
                    else "None",
                )
                handwriting_detected = True
        return handwriting_detected

    @staticmethod
    def _normalize_text_for_consistency_check(text: str) -> str:
        """Normalize text for lightweight chunk/page consistency checks."""
        if not isinstance(text, str):
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def _validate_text_consistency(
        self, page_text_from_source: str, page_chunks: List[DocumentChunk], page_num: int
    ) -> None:
        """Raise ChunkException if get_text_and_words() text diverges from concatenated chunk text.

        Uses the text returned by get_text_and_words() as the authoritative source.
        """
        page_text = self._normalize_text_for_consistency_check(page_text_from_source)
        chunks_text = self._normalize_text_for_consistency_check(" ".join(chunk.chunk_text for chunk in page_chunks))

        if not page_text or not chunks_text:
            return

        if page_text != chunks_text:
            raise ChunkException(
                "Word-stream text mismatch "
                f"on page={page_num}: page_text_chars={len(page_text)} "
                f"chunk_text_chars={len(chunks_text)}"
            )

    @staticmethod
    def _get_words_from_page(page) -> tuple[List[Word], str]:
        """Get words and text from page using get_text_and_words().

        Returns:
            Tuple of (words, text) from get_text_and_words(), or ([], "") if unavailable.
        """
        if not hasattr(page, "get_text_and_words"):
            logger.warning("Page %s has no get_text_and_words method; returning no words", page.page_num)
            return [], ""

        text, words = page.get_text_and_words()
        return (words or [], text or "")
