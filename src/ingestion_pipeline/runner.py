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
# This needs to be accessible in your S3 bucket and available to AWS Textract.
# When developing locally with LocalStack, a copy of this document is added to localstack.
S3_DOCUMENT_URI = "s3://cica-textract-response-dev/26-111111/Case1_TC19_50_pages_brain_injury.pdf"


def extract_case_ref(s3_uri: str) -> str:
    """Extract the case_ref from the S3 URI (the folder after the bucket)."""
    # Example: s3://bucket/26-111111/filename.pdf → 26-111111
    parts = s3_uri.replace("s3://", "").split("/")
    if len(parts) >= 2:
        return parts[1]
    return ""


def main():
    """Main entry point for the application runner."""
    logger.info("Pipeline runner started.")
    if not check_opensearch_health(settings.OPENSEARCH_PROXY_URL):
        logger.critical("OpenSearch health check failed. Exiting pipeline runner.")
        return

    # These values would typically come from an SQS message in a real-world scenario.
    case_ref = extract_case_ref(S3_DOCUMENT_URI)
    correspondence_type = "TC19 - ADDITIONAL INFO REQUEST"
    logger.info(f"Processing document for case reference: {case_ref}")

    # In a real-world scenario, this metadata would come from an SQS message.
    # TODO review the metadata fields needed here, can correspondence_type change?
    # The source_file_name must be unique for a case?
    # so source_file_name and case_ref together make a unique document?
    # and should be enough to generate a unique source_doc_id
    identifier = DocumentIdentifier(
        source_file_name=S3_DOCUMENT_URI.split("/")[-1],
        correspondence_type=correspondence_type,
        case_ref=case_ref,
    )
    source_doc_id = identifier.generate_uuid()

    document_metadata = DocumentMetadata(
        source_doc_id=source_doc_id,
        source_file_name=S3_DOCUMENT_URI.split("/")[-1],
        source_file_s3_uri=S3_DOCUMENT_URI,
        page_count=None,  # Page count is determined during processing.
        case_ref=case_ref,
        received_date=datetime.datetime.now(),
        correspondence_type=correspondence_type,
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
