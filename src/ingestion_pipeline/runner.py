"""Pipeline runner responsible for creating and running the ingestion pipeline.

Processes a batch of documents in parallel. Documents are supplied by a
:class:`DocumentSource` (an SQS-backed stub for now). A single :class:`Pipeline`
and its underlying AWS/OpenSearch clients are constructed once in the main thread
and shared across worker threads; each worker sets its own logging context so
per-document log lines remain correctly attributed.
"""

import datetime
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.config import settings
from ingestion_pipeline.custom_logging.log_context import setup_logging, source_doc_id_context
from ingestion_pipeline.indexing.healthcheck import check_opensearch_health
from ingestion_pipeline.orchestration.document_source import DocumentJob, DocumentSource, SqsDocumentSource
from ingestion_pipeline.orchestration.pipeline import Pipeline
from ingestion_pipeline.pipeline_builder import build_pipeline
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

setup_logging()
logger = logging.getLogger(__name__)


@dataclass
class DocumentResult:
    """Outcome of processing a single document in the batch."""

    job: DocumentJob
    source_doc_id: str
    success: bool
    error: Exception | None = None


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
        where 'NN' is any two digits representing the year, and 'NNNNNN' starts with either 7 or 8.
    """
    pattern = rf"^s3://{re.escape(expected_bucket)}/\d{{2}}-[78]\d{{5}}/"
    return re.match(pattern, s3_uri) is not None


def build_document_metadata(job: DocumentJob, source_doc_id: str) -> DocumentMetadata:
    """Build the DocumentMetadata for a job.

    Args:
        job (DocumentJob): The document work item.
        source_doc_id (str): The deterministic document UUID.

    Returns:
        DocumentMetadata: Metadata ready to feed into the pipeline.
    """
    return DocumentMetadata(
        source_doc_id=source_doc_id,
        source_file_name=job.source_file_name,
        source_file_s3_uri=job.source_file_s3_uri,
        page_count=None,
        case_ref=job.case_ref,
        received_date=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
        correspondence_type=job.correspondence_type,
    )


def process_document_job(job: DocumentJob, pipeline: Pipeline) -> DocumentResult:
    """Process a single document. Runs inside a worker thread.

    Sets the per-document logging context for the duration of the call (ContextVars
    are not inherited by pool threads, so each worker must set its own), validates
    the S3 URI, runs the pipeline, and contains any error so one failing document
    does not abort the batch.

    Args:
        job (DocumentJob): The document to process.
        pipeline (Pipeline): The shared, thread-safe pipeline instance.

    Returns:
        DocumentResult: The outcome for this document.
    """
    identifier = DocumentIdentifier(
        source_file_name=job.source_file_name,
        correspondence_type=job.correspondence_type,
        case_ref=job.case_ref,
    )
    source_doc_id = identifier.generate_uuid()
    token = source_doc_id_context.set(source_doc_id)
    try:
        logger.info(f"Generated source_doc_id: {source_doc_id} for document: {job.source_file_s3_uri}")

        if not validate_s3_uri(job.source_file_s3_uri, settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET):
            raise ValueError(f"Invalid S3 URI: {job.source_file_s3_uri}")

        logger.info(f"Processing document for case reference: {job.case_ref}")
        document_metadata = build_document_metadata(job, source_doc_id)
        logger.info(f"Document metadata prepared: file={document_metadata.source_file_name}, case_ref={job.case_ref}")

        pipeline.process_document(document_metadata=document_metadata)
        logger.info(f"Finished processing document {job.source_file_s3_uri}")
        return DocumentResult(job=job, source_doc_id=source_doc_id, success=True)
    except Exception as exc:
        logger.critical(
            f"Pipeline runner encountered a fatal error for source_doc_id={source_doc_id}, "
            f"case_ref={job.case_ref}, s3_uri={job.source_file_s3_uri}: {type(exc).__name__}: {exc}",
            exc_info=True,
        )
        return DocumentResult(job=job, source_doc_id=source_doc_id, success=False, error=exc)
    finally:
        source_doc_id_context.reset(token)


def run_batch(jobs: list[DocumentJob], pipeline: Pipeline, source: DocumentSource) -> list[DocumentResult]:
    """Process a batch of documents concurrently using a thread pool.

    Args:
        jobs (list[DocumentJob]): Documents to process.
        pipeline (Pipeline): The shared pipeline instance.
        source (DocumentSource): The source used to acknowledge completed jobs.

    Returns:
        list[DocumentResult]: One result per job.
    """
    if not jobs:
        logger.info("No documents to process in this batch.")
        return []

    max_workers = min(settings.MAX_CONCURRENT_DOCUMENTS, len(jobs))
    logger.info(f"Processing {len(jobs)} document(s) with up to {max_workers} concurrent worker(s).")

    results: list[DocumentResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {executor.submit(process_document_job, job, pipeline): job for job in jobs}
        for future in as_completed(future_to_job):
            result = future.result()
            results.append(result)
            if result.success:
                source.acknowledge(result.job)

    succeeded = sum(1 for r in results if r.success)
    failed = len(results) - succeeded
    logger.info(f"Batch complete: {succeeded} succeeded, {failed} failed (of {len(results)}).")
    return results


def main():
    """Main entry point for the application runner: process a batch of documents in parallel."""
    if settings.LOCAL_DEVELOPMENT_MODE:
        logger.warning("Running in LOCAL_DEVELOPMENT_MODE. Ensure your S3 URIs are accessible in LocalStack.")

    logger.info("Pipeline runner started.")
    if not check_opensearch_health(
        settings.OPENSEARCH_PROXY_URL,
        verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
        ssl_assert_hostname=settings.OPENSEARCH_SSL_ASSERT_HOSTNAME,
    ):
        logger.critical("OpenSearch health check failed. Exiting pipeline runner.")
        return

    # Build the pipeline (and all AWS/OpenSearch clients) once and share it across
    # worker threads. All components are stateless per-document and their underlying
    # clients are safe to call concurrently.
    pipeline = build_pipeline()

    # Fetch the batch of documents to process from the (stubbed) SQS source.
    source: DocumentSource = SqsDocumentSource()
    jobs = source.fetch_batch()

    run_batch(jobs, pipeline, source)
    logger.info("Pipeline runner finished.")


if __name__ == "__main__":
    main()
