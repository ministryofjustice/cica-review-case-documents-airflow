"""Pipeline builder responsible for creating the ingestion pipeline components."""

import logging
import os

import boto3
from textractor import Textractor

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
from ingestion_pipeline.page_processor.processor import PageProcessor
from ingestion_pipeline.textract.textract_processor import TextractProcessor

setup_logging()
logger = logging.getLogger(__name__)


def build_pipeline() -> Pipeline:
    """Constructs the pipeline with all its dependencies.

    This acts as the composition root for the application.

    Returns:
        Pipeline: A fully configured instance of the ingestion pipeline.
    """
    # Textractor (the library) requires AWS credentials to be set in environment variables
    # at instantiation time, as it does not accept credentials via constructor or config.
    # We temporarily override the environment variables with the Textract account credentials
    # to ensure Textractor uses the correct AWS account, then restore the originals after.

    # Store original values
    original_env = {
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY"),
        "AWS_SESSION_TOKEN": os.environ.get("AWS_SESSION_TOKEN"),
    }

    try:
        # Set credentials for Textract account
        os.environ["AWS_ACCESS_KEY_ID"] = settings.AWS_TEXTRACT_ACCESS_KEY_ID
        os.environ["AWS_SECRET_ACCESS_KEY"] = settings.AWS_TEXTRACT_SECRET_ACCESS_KEY
        os.environ["AWS_SESSION_TOKEN"] = settings.AWS_TEXTRACT_SESSION_TOKEN

        textractor_instance = Textractor(region_name=settings.AWS_REGION)
    finally:
        # Restore original values
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # boto3 client with explicit credentials (no env vars needed)
    boto3_textract_client = boto3.client(
        "textract",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_TEXTRACT_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_TEXTRACT_SECRET_ACCESS_KEY,
        aws_session_token=settings.AWS_TEXTRACT_SESSION_TOKEN,
    )

    # --- Pipeline Components ---
    textract_processor = TextractProcessor(
        textractor=textractor_instance,
        textract_client=boto3_textract_client,
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
