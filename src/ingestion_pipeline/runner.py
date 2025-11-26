"""Pipeline runner responsible for creating and running the ingestion pipeline."""

import datetime
import logging

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.config import settings
from ingestion_pipeline.custom_logging.log_context import setup_logging
from ingestion_pipeline.indexing.healthcheck import check_opensearch_health
from ingestion_pipeline.pipeline_builder import build_pipeline
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

setup_logging()
logger = logging.getLogger(__name__)

# This is a placeholder for a real message from an SQS queue.
# You can add your own S3 document URI here for testing.
S3_DOCUMENT_URI = "s3://cica-textract-response-dev/Case1_TC19_50_pages_brain_injury.pdf"


def main():
    """Main entry point for the application runner."""
    logger.info("Pipeline runner started.")
    check_opensearch_health(settings.OPENSEARCH_PROXY_URL)

    # In a real-world scenario, this metadata would come from an SQS message.
    identifier = DocumentIdentifier(
        source_file_name=S3_DOCUMENT_URI.split("/")[-1],
        correspondence_type="TC19",
        case_ref="25-111111",
    )
    source_doc_id = identifier.generate_uuid()

    document_metadata = DocumentMetadata(
        source_doc_id=source_doc_id,
        source_file_name=S3_DOCUMENT_URI.split("/")[-1],
        source_file_s3_uri=S3_DOCUMENT_URI,
        page_count=None,  # Page count is determined during processing.
        case_ref="25-111111",
        received_date=datetime.datetime.now(),
        correspondence_type="TC19",
    )

    # Build the pipeline and process the document.
    pipeline = build_pipeline()
    try:
        pipeline.process_document(document_metadata=document_metadata)
        logger.info("Pipeline runner finished successfully.")
    except Exception:
        logger.critical("Pipeline runner encountered a fatal error.", exc_info=True)


if __name__ == "__main__":
    main()
