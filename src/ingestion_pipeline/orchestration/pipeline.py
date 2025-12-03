"""Orchestration pipeline for chunking and indexing documents."""

import logging

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.chunking.textract_document_chunker import ChunkError, DocumentChunker
from ingestion_pipeline.config import settings
from ingestion_pipeline.custom_logging.log_context import source_doc_id_context
from ingestion_pipeline.embedding.embedding_generator import EmbeddingError, EmbeddingGenerator
from ingestion_pipeline.indexing.indexer import IndexingError, OpenSearchIndexer
from ingestion_pipeline.page_processor.processor import PageProcessor
from ingestion_pipeline.textract.textract_processor import TextractProcessingError, TextractProcessor

logger = logging.getLogger(__name__)

CHUNK_INDEX_NAME = settings.OPENSEARCH_CHUNK_INDEX_NAME
AWS_REGION = settings.AWS_REGION

# --- Configuration for Polling ---
POLL_INTERVAL_SECONDS = settings.TEXTRACT_API_POLL_INTERVAL_SECONDS
JOB_TIMEOUT_SECONDS = settings.TEXTRACT_API_JOB_TIMEOUT_SECONDS


class PipelineError(Exception):
    """Base exception for pipeline failures."""


class Pipeline:
    """Orchestrates the document processing pipeline: chunking -> embedding -> indexing."""

    def __init__(
        self,
        textract_processor: TextractProcessor,
        chunker: DocumentChunker,
        embedding_generator: EmbeddingGenerator,
        chunk_indexer: OpenSearchIndexer,
        page_indexer: OpenSearchIndexer,
        page_processor: PageProcessor,
    ):
        """Initializes the orchestrator with injected dependencies.

        Args:
            textract_processor: Processor to extract data using Textract.
            chunker: Document chunker with configured strategies.
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

    def process_document(self, document_metadata: DocumentMetadata):
        """Runs the full pipeline for a single document.

        Args:
            document_metadata: Metadata of the document to process.
        """
        source_doc_id = document_metadata.source_doc_id
        source_doc_id_context.set(source_doc_id)
        logger.info("Starting document processing pipeline")

        try:
            document = self.textract_processor.process_document(document_metadata.source_file_s3_uri)
            if not document:
                logger.warning("Textract did not return a document. Skipping rest of pipeline.")
                return

            updated_metadata = document_metadata.model_copy(update={"page_count": document.num_pages})

            # Index page metadata here
            page_documents = self.page_processor.process(document, updated_metadata)
            self.page_indexer.index_documents(page_documents, id_field="page_id")

            processed_data = self.chunker.chunk(document, updated_metadata)
            if not processed_data.chunks:
                logger.warning("No chunks were generated. Skipping embedding and indexing.")
                return

            for chunk in processed_data.chunks:
                chunk.embedding = self.embedding_generator.generate_embedding(chunk.chunk_text)

            self.chunk_indexer.index_documents(processed_data.chunks)
            logger.info("Successfully finished processing document")

        except (TextractProcessingError, EmbeddingError, IndexingError, ChunkError) as e:
            logger.critical(f"Pipeline failed for document: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.critical(f"An unexpected error occurred in the pipeline for document: {e}", exc_info=True)
            raise PipelineError(f"Unexpected pipeline failure: {str(e)}") from e
        finally:
            logger.info("Cleaning up context for document")
            source_doc_id_context.set(None)
