"""Orchestration pipeline for chunking and indexing documents."""

import logging
from typing import List

from ingestion_pipeline.chunking.chunk_strategy import ChunkStrategy
from ingestion_pipeline.chunking.schemas import DocumentChunk, DocumentMetadata, DocumentPage
from ingestion_pipeline.config import settings
from ingestion_pipeline.embedding.embedding_generator import EmbeddingGenerator
from ingestion_pipeline.errors import EmptyTextractResponseError, PipelineError, ZeroChunksError
from ingestion_pipeline.indexing.indexer import OpenSearchIndexer
from ingestion_pipeline.page_processor.processor import PageProcessor
from ingestion_pipeline.textract.textract_processor import TextractProcessor

logger = logging.getLogger(__name__)

CHUNK_INDEX_NAME = settings.OPENSEARCH_CHUNK_INDEX_NAME
AWS_REGION = settings.AWS_REGION

# --- Configuration for Polling ---
POLL_INTERVAL_SECONDS = settings.TEXTRACT_API_POLL_INTERVAL_SECONDS
JOB_TIMEOUT_SECONDS = settings.TEXTRACT_API_JOB_TIMEOUT_SECONDS


class Pipeline:
    """Orchestrates the document processing pipeline: chunking -> embedding -> indexing."""

    def __init__(
        self,
        textract_processor: TextractProcessor,
        chunker: ChunkStrategy,
        embedding_generator: EmbeddingGenerator,
        chunk_indexer: OpenSearchIndexer,
        page_indexer: OpenSearchIndexer,
        page_processor: PageProcessor,
    ):
        """Initializes the orchestrator with injected dependencies.

        Args:
            textract_processor: Processor to extract data using Textract.
            chunker: ChunkStrategy with configured strategies.
            embedding_generator: Generator for creating embeddings from text.
            chunk_indexer: Indexer to store documents in OpenSearch.
            page_indexer: Indexer to store document pages in OpenSearch.
            page_processor: Processor to handle page-level processing.
        """
        self.textract_processor = textract_processor
        self.chunker = chunker
        self.embedding_generator = embedding_generator
        self.chunk_indexer = chunk_indexer
        self.page_indexer = page_indexer
        self.page_processor = page_processor

    def process_document(self, document_metadata: DocumentMetadata) -> None:
        """Runs the full pipeline for a single document.

        Orchestrates the complete document processing workflow including Textract analysis,
        page processing, chunking, embedding generation, and indexing into OpenSearch.

        The contract is "succeed or raise": on success this returns ``None`` having
        indexed searchable chunks and page metadata. Any failure (including the
        terminal no-document and zero-chunks conditions) raises a
        :class:`~ingestion_pipeline.errors.PipelineError`, after cleaning up every
        side effect for this document (page images in S3 and any chunk/page records
        in OpenSearch). Callers therefore never observe a partially-ingested
        document.

        Args:
            document_metadata (DocumentMetadata): Metadata of the document to process including
                source file location, case reference, and correspondence type.

        Raises:
            EmptyTextractResponseError: If Textract returned no document (terminal).
            ZeroChunksError: If the whole document produced no chunks (terminal).
            TextractProcessingError: If Textract analysis fails.
            ChunkError: If document chunking fails.
            EmbeddingError: If embedding generation fails.
            IndexingError: If OpenSearch indexing fails.
            PageProcessingError: If page processing fails.
            PipelineError: If an unexpected error occurs during processing.
        """
        source_doc_id = document_metadata.source_doc_id
        case_ref = document_metadata.case_ref
        s3_uri = document_metadata.source_file_s3_uri

        try:
            document = self.textract_processor.process_document(s3_uri)
            if not document:
                # Terminal: no document means nothing can be indexed. Raise so the
                # runner does not acknowledge the job and cleanup runs (a no-op here,
                # but keeps the contract uniform).
                raise EmptyTextractResponseError(
                    "Textract returned no document; nothing to index.",
                    source_doc_id=source_doc_id,
                    case_ref=case_ref,
                    s3_uri=s3_uri,
                )

            updated_metadata = document_metadata.model_copy(update={"page_count": document.num_pages})

            # Chunk the document first (handwriting detection happens here per page) so a
            # zero-chunk document is rejected *before* any page metadata is indexed. This
            # avoids indexing page records only to immediately delete them.
            processed_data = self.chunker.chunk(document, updated_metadata)
            if not processed_data.chunks:
                raise ZeroChunksError(
                    "Chunking produced no chunks for the whole document; nothing searchable to index.",
                    source_doc_id=source_doc_id,
                    case_ref=case_ref,
                    s3_uri=s3_uri,
                )

            # Create page metadata records (images uploaded, DocumentPage objects constructed)
            page_documents = self.page_processor.process(document, updated_metadata)

            # Propagate handwriting flags from chunks to page metadata
            self._propagate_handwriting_flags(page_documents, processed_data.chunks)

            # Generate embeddings
            logger.info(f"Generating embeddings for {len(processed_data.chunks)} chunks")
            for chunk in processed_data.chunks:
                chunk.embedding = self.embedding_generator.generate_embedding(chunk.chunk_text)
            logger.info(f"Finished generating embeddings for {len(processed_data.chunks)} chunks")

            # Index chunks first, then page metadata
            self.chunk_indexer.index_documents(processed_data.chunks)
            self.page_indexer.index_documents(page_documents, id_field="page_id")
            logger.info("Successfully finished processing document")

        except PipelineError as e:
            # Single, centralised failure path: log, undo every side effect for this
            # document, then re-raise for the runner to classify (redrive / DLQ /
            # metadata index) using the exception's failure_context().
            logger.critical(f"Pipeline failed for document: {e}", exc_info=True)
            self._cleanup_document(source_doc_id, case_ref)
            raise
        except Exception as e:
            logger.critical(f"An unexpected error occurred in the pipeline for document: {e}", exc_info=True)
            self._cleanup_document(source_doc_id, case_ref)
            raise PipelineError(
                f"Unexpected pipeline failure: {str(e)}",
                source_doc_id=source_doc_id,
                case_ref=case_ref,
                s3_uri=s3_uri,
            ) from e

    def _cleanup_document(self, source_doc_id: str, case_ref: str) -> None:
        """Remove every side effect for a failed document.

        Centralised cleanup for the failure path. Removes any indexed chunk/page
        records from OpenSearch and prefix-deletes all page images for the document
        from S3. Both are keyed by the deterministic, per-document identifiers, so
        cleanup is complete regardless of how far processing progressed (and is
        invariant to sequential vs future parallel page uploads).

        Cleanup errors are logged but never mask the original failure.

        Args:
            source_doc_id (str): The unique identifier of the source document.
            case_ref (str): The CICA case reference for the document.
        """
        self._cleanup_indexed_data(source_doc_id)
        self._cleanup_page_images(source_doc_id, case_ref)

    def _cleanup_indexed_data(self, source_doc_id: str):
        """Removes any indexed data for a failed document.

        Attempts to delete all chunks and page metadata from OpenSearch indices
        associated with the given source document ID.

        Args:
            source_doc_id (str): The unique identifier of the source document.
        """
        try:
            logger.info("Cleaning up indexed data")
            self.chunk_indexer.delete_documents_by_source_doc_id(source_doc_id)
            self.page_indexer.delete_documents_by_source_doc_id(source_doc_id)
        except Exception as cleanup_error:
            if self._is_opensearch_connectivity_error(cleanup_error):
                logger.debug(
                    "Skipping verbose cleanup error log for connectivity issue on document %s: %s",
                    source_doc_id,
                    cleanup_error,
                )
                return

            logger.error(
                f"Failed to clean up indexed data for document {source_doc_id}: {cleanup_error}",
                exc_info=True,
            )

    def _cleanup_page_images(self, source_doc_id: str, case_ref: str) -> None:
        """Prefix-delete all page images for a failed document from S3.

        Removes everything under ``{case_ref}/{source_doc_id}/pages/`` so a partial
        or interrupted upload leaves no orphaned images. Cleanup errors are logged
        but never mask the original failure.

        Args:
            source_doc_id (str): The unique identifier of the source document.
            case_ref (str): The CICA case reference for the document.
        """
        try:
            logger.info("Cleaning up page images")
            self.page_processor.s3_document_service.delete_page_images(case_ref, source_doc_id)
        except Exception as cleanup_error:
            logger.error(
                f"Failed to clean up page images for document {source_doc_id} (case_ref={case_ref}): {cleanup_error}",
                exc_info=True,
            )

    @staticmethod
    def _is_opensearch_connectivity_error(error: Exception) -> bool:
        """Return True for expected OpenSearch connectivity failures."""
        message = str(error)
        return (
            "Connection refused" in message
            or "Failed to establish a new connection" in message
            or "Name or service not known" in message
        )

    @staticmethod
    def _propagate_handwriting_flags(
        page_documents: List[DocumentPage],
        chunks: List[DocumentChunk],
    ) -> None:
        """Set page_contains_handwriting on DocumentPage objects using chunk data.

        For each page, if any chunk on that page has page_contains_handwriting=True,
        the corresponding DocumentPage is updated to True.

        Raises PipelineError if any chunk references a page_number that has no
        corresponding DocumentPage, as this indicates a data integrity violation.

        Args:
            page_documents: List of DocumentPage objects to update in place.
            chunks: List of DocumentChunk objects containing handwriting flags.

        Raises:
            PipelineError: If a chunk references a page_number not in page_documents.
        """
        page_num_set = {page_doc.page_num for page_doc in page_documents}

        pages_with_handwriting: set[int] = set()
        for chunk in chunks:
            if chunk.page_number not in page_num_set:
                raise PipelineError(
                    f"Chunk '{chunk.chunk_id}' references page_number={chunk.page_number} "
                    f"which has no corresponding DocumentPage (source_doc_id={chunk.source_doc_id}). "
                    f"Available page numbers: {sorted(page_num_set)}",
                    source_doc_id=chunk.source_doc_id,
                )
            if chunk.page_contains_handwriting:
                pages_with_handwriting.add(chunk.page_number)

        for page_doc in page_documents:
            if page_doc.page_num in pages_with_handwriting:
                page_doc.page_contains_handwriting = True
