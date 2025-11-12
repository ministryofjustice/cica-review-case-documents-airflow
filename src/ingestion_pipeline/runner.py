"""Pipeline runner to be moved to main once Textract and Opensearch connectivity have been added."""

import datetime
import logging

import boto3
from textractor import Textractor

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.schemas import DocumentMetadata
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
from ingestion_pipeline.textract_processor import CHUNK_INDEX_NAME, TextractProcessor
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

setup_logging()
logger = logging.getLogger(__name__)


# TODO this will be picked up from a queue in a real world scenario
# you can add your own S3 document URI here for testing
S3_DOCUMENT_URI = "s3://cica-textract-response-dev/Case1_TC19_50_pages_brain_injury.pdf"


def main():
    """Main entry point for the application runner."""
    logger.info("Running........")
    # get the messages from the SQS queue

    # Generate a unique source document ID
    identifier = DocumentIdentifier(
        source_file_name=S3_DOCUMENT_URI.split("/")[-1], correspondence_type="TC19", case_ref="25-111111"
    )

    source_doc_id = identifier.generate_uuid()
    logger.debug(f"Generated 16-digit UUID: {source_doc_id}")

    document_metadata = DocumentMetadata(
        source_doc_id=source_doc_id,
        source_file_name=S3_DOCUMENT_URI.split("/")[-1],
        source_file_s3_uri=S3_DOCUMENT_URI,
        page_count=None,  # TODO is there a way to get the page count before processing?
        case_ref="25-111111",
        received_date=datetime.datetime.now(),
        correspondence_type="TC19",
    )

    config = ChunkingConfig()

    layout_text_strategy = LayoutTextChunkingStrategy(config)
    layout_table_strategy = LayoutTableChunkingStrategy(config)
    layout_key_value_strategy = KeyValueChunker(config)
    layout_list_strategy = LayoutListChunkingStrategy(config)

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
        config=config,
    )

    textractor_instance = Textractor()
    boto3_textract_client = boto3.client("textract", settings.AWS_REGION)

    textract_processor = TextractProcessor(
        textractor=textractor_instance,
        textract_client=boto3_textract_client,
    )

    embedding_generator = EmbeddingGenerator(settings.BEDROCK_EMBEDDING_MODEL_ID)
    chunk_indexer = OpenSearchIndexer(index_name=CHUNK_INDEX_NAME, proxy_url=settings.OPENSEARCH_PROXY_URL)

    pipeline = Pipeline(
        textract_processor=textract_processor,
        chunker=chunker,
        embedding_generator=embedding_generator,
        chunk_indexer=chunk_indexer,
    )
    pipeline.process_document(document_metadata=document_metadata)


if __name__ == "__main__":
    main()
