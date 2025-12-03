"""Pipeline builder responsible for creating the ingestion pipeline components."""

import logging

from ingestion_pipeline.aws_client.clients import (
    get_s3_client,
    get_textract_client,
    get_textractor_instance,
)
from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.strategies.key_value.layout_key_value import KeyValueChunker
from ingestion_pipeline.chunking.strategies.layout_text import LayoutTextChunkingStrategy
from ingestion_pipeline.chunking.strategies.list.list_chunker import LayoutListChunkingStrategy
from ingestion_pipeline.chunking.strategies.table.layout_table import LayoutTableChunkingStrategy
from ingestion_pipeline.chunking.textract_document_chunker import DocumentChunker
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


def build_pipeline() -> Pipeline:
    """Constructs the pipeline with all its dependencies.

    This acts as the composition root for the application.

    Returns:
        Pipeline: A fully configured instance of the ingestion pipeline.
    """
    # --- Pipeline Components ---
    textractor_instance = get_textractor_instance()
    textract_processor = TextractProcessor(
        textractor=textractor_instance,
        textract_client=get_textract_client(),
    )

    # --- Chunking Strategies ---
    chunking_config = ChunkingConfig()
    layout_text_strategy = LayoutTextChunkingStrategy(chunking_config)
    layout_table_strategy = LayoutTableChunkingStrategy(chunking_config)
    layout_key_value_strategy = KeyValueChunker(chunking_config)
    layout_list_strategy = LayoutListChunkingStrategy(chunking_config)

    strategy_handlers = {
        "LAYOUT_TEXT": layout_text_strategy,
        "LAYOUT_HEADER": layout_text_strategy,
        "LAYOUT_TITLE": layout_text_strategy,
        "LAYOUT_TABLE": layout_table_strategy,
        "LAYOUT_SECTION_HEADER": layout_text_strategy,
        "LAYOUT_FOOTER": layout_text_strategy,
        "LAYOUT_FIGURE": layout_table_strategy,
        "LAYOUT_KEY_VALUE": layout_key_value_strategy,
        "LAYOUT_LIST": layout_list_strategy,
    }

    chunker = DocumentChunker(
        strategy_handlers=strategy_handlers,
        config=chunking_config,
    )

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

    page_processor = PageProcessor()

    # --- Construct and Return the Pipeline ---
    return Pipeline(
        textract_processor=textract_processor,
        chunker=chunker,
        embedding_generator=embedding_generator,
        chunk_indexer=chunk_indexer,
        page_indexer=page_indexer,
        page_processor=page_processor,
    )
