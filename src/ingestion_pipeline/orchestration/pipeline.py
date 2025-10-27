import logging

from textractor.entities.document import Document

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.chunking.textract import DocumentChunker
from ingestion_pipeline.config import settings
from ingestion_pipeline.embedding.embedding_generator import EmbeddingGenerator
from ingestion_pipeline.indexing.indexer import OpenSearchIndexer

logger = logging.getLogger(__name__)


class ChunkAndIndexPipeline:
    """
    Orchestrates the document processing pipeline: chunking -> embedding -> indexing.
    """

    def __init__(self, chunker: DocumentChunker, chunk_indexer: OpenSearchIndexer):
        """
        Initializes the orchestrator with the necessary components.

        Args:
            chunker: An instance of TextractDocumentChunker.
            chunk_indexer: An instance of OpenSearchIndexer for chunk data.
        """
        self.chunker = chunker
        self.chunk_indexer = chunk_indexer

    def process_and_index(self, doc: Document, metadata: DocumentMetadata):
        """
        Runs the full pipeline for a single document.

        Args:
            doc: The Textractor Document object to process.
            metadata: The associated metadata for the document.
        """
        logger.info(f"Starting processing for document: {metadata.ingested_doc_id}")

        processed_data = self.chunker.chunk(doc, metadata)
        logger.info(
            f"Document chunked. Found {len(processed_data.chunks)} chunks and {len(processed_data.pages)} pages."
        )

        if processed_data.chunks:
            for chunk in processed_data.chunks:
                logger.debug(f"Chunk ID: {chunk.chunk_id}, Text: {chunk.chunk_text[:50]}...")
                embedding_generator = EmbeddingGenerator(settings.BEDROCK_EMBEDDING_MODEL_ID)
                embedding = embedding_generator.generate_embedding(chunk.chunk_text)
                chunk.embedding = embedding

        if processed_data.chunks:
            logger.info(f"Indexing {len(processed_data.chunks)} chunks...")
            self.chunk_indexer.index_documents(processed_data.chunks)
        else:
            logger.warning("No chunks were generated, skipping indexing.")

        logger.info(f"Successfully finished processing document: {metadata.ingested_doc_id}")
