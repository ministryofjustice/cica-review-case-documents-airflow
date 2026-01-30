"""Pipeline runner responsible for creating and running the ingestion pipeline."""

import datetime
import logging
import re

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


# /\d{2}[-][78]d{5}/gm
def extract_case_ref(s3_uri: str) -> str:
    """Extract the case_ref from the S3 URI (the folder after the bucket)."""
    # Example: s3://bucket/26-711111/filename.pdf → 26-711111
    parts = s3_uri.replace("s3://", "").split("/")
    if len(parts) >= 2:
        return parts[1]
    return ""


def validate_s3_uri(s3_uri: str, expected_bucket: str) -> bool:
    """Validates whether the given S3 URI matches the expected bucket and follows the required path pattern.

    Args:
        s3_uri (str): The S3 URI to validate (e.g., 's3://bucket/26-711111/').
        expected_bucket (str): The expected S3 bucket name.

    Returns:
        bool: True if the S3 URI matches the expected bucket and path pattern, False otherwise.
    Pattern:
        The S3 URI must start with 's3://{expected_bucket}/', followed by a directory in the format 'NN-NNNNNN/',
        where 'NN' is any two digits, and 'NNNNNN' starts with either 7 or 8.
    """
    pattern = rf"^s3://{re.escape(expected_bucket)}/\d{{2}}-[78]\d{{5}}/"
    return re.match(pattern, s3_uri) is not None


def main():
    """Main entry point for the application runner."""
    logger.info("Pipeline runner started.")
    if not check_opensearch_health(settings.OPENSEARCH_PROXY_URL):
        logger.critical("OpenSearch health check failed. Exiting pipeline runner.")
        return

    S3_DOCUMENT_URI = (
        f"s3://{settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET}/26-711111/Case1_TC19_50_pages_brain_injury.pdf"
    )

    logger.info(f"Validating S3 URI: {S3_DOCUMENT_URI}")
    if not validate_s3_uri(S3_DOCUMENT_URI, settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET):
        logger.critical(f"Invalid S3 URI: {S3_DOCUMENT_URI}")
        raise ValueError(f"Invalid S3 URI: {S3_DOCUMENT_URI}")

    case_ref = extract_case_ref(S3_DOCUMENT_URI)
    correspondence_type = "TC19 - ADDITIONAL INFO REQUEST"
    logger.info(f"Processing document for case reference: {case_ref}")

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
        page_count=None,
        case_ref=case_ref,
        received_date=datetime.datetime.now(),
        correspondence_type=correspondence_type,
    )

    logger.info(
        f"Document metadata prepared: source_doc_id={source_doc_id}, "
        f"file={document_metadata.source_file_name}, case_ref={case_ref}"
    )

    pipeline = build_pipeline()
    try:
        logger.info("Starting document processing in pipeline.")
        pipeline.process_document(document_metadata=document_metadata)
        logger.info("Pipeline runner finished successfully.")
    except Exception as exc:
        logger.critical(
            f"Pipeline runner encountered a fatal error for source_doc_id={source_doc_id}, "
            f"case_ref={case_ref}, s3_uri={S3_DOCUMENT_URI}: {type(exc).__name__}: {exc}",
            exc_info=True,
        )
        # Optionally: raise or exit(1)


if __name__ == "__main__":
    main()
