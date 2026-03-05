"""Pipeline builder responsible for creating the ingestion pipeline components."""

import logging

from ingestion_pipeline.aws_client.clients import (
    get_s3_client,
    get_textract_client,
    get_textractor_instance,
)
from ingestion_pipeline.chunking.document_chunker_factory import get_document_chunker
from ingestion_pipeline.config import settings
from ingestion_pipeline.custom_logging.log_context import setup_logging
from ingestion_pipeline.embedding.embedding_generator import EmbeddingGenerator
from ingestion_pipeline.indexing.indexer import OpenSearchIndexer
from ingestion_pipeline.orchestration.pipeline import Pipeline
from ingestion_pipeline.page_processor.image_converter import ImageConverter
from ingestion_pipeline.page_processor.page_factory import DocumentPageFactory
from ingestion_pipeline.page_processor.processor import PageProcessor
from ingestion_pipeline.page_processor.s3_document_service import S3DocumentService
from ingestion_pipeline.textract.textract_processor import TextractProcessor

setup_logging()
logger = logging.getLogger(__name__)

# Define the chunker type to use in the pipeline (e.g., "line" or "layout")
# Leaving both implemented chunkers available, but defaulting to "line" for now.
# Can be made configurable via settings or environment variable in the future.
# We are still experimenting with both approaches and want to keep the option open
# to easily switch between them for testing and iteration.
# ALLOWED_CHUNKER_TYPES = {"layout", "line"}
# e.g., "layout" or "linear-sentence-splitter"
DOCUMENT_CHUNKING_STRATEGY = settings.DOCUMENT_CHUNKING_STRATEGY.strip().lower()


def build_pipeline() -> Pipeline:
    """Constructs the pipeline with all its dependencies.

    This acts as the composition root for the ingestion pipeline.

    Returns:
        Pipeline: A fully configured instance of the ingestion pipeline.
    """
    # --- Pipeline Components ---
    textractor_instance = get_textractor_instance()
    textract_processor = TextractProcessor(
        textractor=textractor_instance,
        textract_client=get_textract_client(),
    )

    chunker = get_document_chunker(DOCUMENT_CHUNKING_STRATEGY)

    embedding_generator = EmbeddingGenerator(model_id=settings.BEDROCK_EMBEDDING_MODEL_ID)
    chunk_indexer = OpenSearchIndexer(
        index_name=settings.OPENSEARCH_CHUNK_INDEX_NAME,
        proxy_url=settings.OPENSEARCH_PROXY_URL,
    )
    page_indexer = OpenSearchIndexer(
        index_name=settings.OPENSEARCH_PAGE_METADATA_INDEX_NAME,
        proxy_url=settings.OPENSEARCH_PROXY_URL,
    )

    image_converter = ImageConverter()
    s3_document_service = S3DocumentService(
        s3_client=get_s3_client(),
        source_bucket=settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET,
        page_bucket=settings.AWS_CICA_S3_PAGE_BUCKET,
    )

    page_factory = DocumentPageFactory()
    page_processor = PageProcessor(
        s3_document_service=s3_document_service,
        image_converter=image_converter,
        page_factory=page_factory,
    )

    # --- Construct and Return the Pipeline ---
    return Pipeline(
        textract_processor=textract_processor,
        chunker=chunker,
        embedding_generator=embedding_generator,
        chunk_indexer=chunk_indexer,
        page_indexer=page_indexer,
        page_processor=page_processor,
    )
