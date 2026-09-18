"""Pipeline runner responsible for creating and running the ingestion pipeline.

Processes a batch of documents in parallel. Documents are supplied by a
:class:`DocumentSource` (an SQS-backed stub for now). A single :class:`Pipeline`
and its underlying AWS/OpenSearch clients are constructed once in the main thread
and shared across worker threads; each worker sets its own logging context so
per-document log lines remain correctly attributed.
"""

import logging
import sys

from ingestion_pipeline.config import settings
from ingestion_pipeline.custom_logging.log_context import setup_logging
from ingestion_pipeline.indexing.healthcheck import check_opensearch_health
from ingestion_pipeline.orchestration.batch_processing.batch_runner import run_batch
from ingestion_pipeline.orchestration.document_source import (
    DocumentSource,
    QueueResolutionError,
    SqsDocumentSource,
)
from ingestion_pipeline.pipeline_builder import build_pipeline

setup_logging()
logger = logging.getLogger(__name__)


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

    # Connect to the SQS document queue. An unresolvable queue is fatal: log and exit
    # non-zero rather than proceeding with no source of work.
    try:
        source: DocumentSource = SqsDocumentSource()
    except QueueResolutionError as exc:
        logger.critical(f"Could not connect to the SQS document queue; exiting: {exc}")
        sys.exit(1)

    # Fetch a batch of documents from the queue and process them.
    jobs = source.fetch_batch()

    run_batch(jobs, pipeline, source)
    logger.info("Pipeline runner finished.")


if __name__ == "__main__":
    main()
