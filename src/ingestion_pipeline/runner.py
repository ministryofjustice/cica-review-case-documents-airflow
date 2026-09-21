"""Pipeline runner responsible for creating and running the ingestion pipeline.

Processes a batch of documents in parallel. Documents are supplied by a
:class:`DocumentSource` (an SQS-backed stub for now). A single :class:`Pipeline`
and its underlying AWS/OpenSearch clients are constructed once in the main thread
and shared across worker threads; each worker sets its own logging context so
per-document log lines remain correctly attributed.
"""

import logging
import sys

from pydantic import BaseModel, ConfigDict

from ingestion_pipeline.config import settings
from ingestion_pipeline.custom_logging.log_context import setup_logging
from ingestion_pipeline.indexing.healthcheck import check_opensearch_health
from ingestion_pipeline.orchestration.batch_processing.batch_runner import run_batch
from ingestion_pipeline.orchestration.document_source import (
    DocumentSource,
    QueueResolutionError,
    SqsDocumentSource,
)
from ingestion_pipeline.orchestration.pipeline import Pipeline
from ingestion_pipeline.pipeline_builder import build_pipeline

setup_logging()
logger = logging.getLogger(__name__)


class RunSummary(BaseModel):
    """Immutable summary of a single drain run.

    Carries the aggregate counts the operator alerts on plus the reason the drain loop
    stopped. Frozen so a returned summary cannot be mutated by a caller before it is
    logged.

    Attributes:
        batches_processed (int): Number of batches started this run.
        messages_received (int): Sum of ``len(jobs)`` over each non-empty ``fetch_batch``.
        successes (int): Count of ``DocumentResult.success`` being True across all results.
        failures (int): Count of ``DocumentResult.success`` being False across all results.
        terminal_reason (str): Why the loop stopped: ``"queue drained"`` or
            ``"hit max-batches ceiling"``.
    """

    model_config = ConfigDict(frozen=True)

    batches_processed: int
    messages_received: int
    successes: int
    failures: int
    terminal_reason: str


def drain_queue(source: DocumentSource, pipeline: Pipeline) -> RunSummary:
    """Repeatedly fetch and process batches until the queue drains or the ceiling trips.

    Runs the bounded drain loop: on each iteration it fetches one batch from ``source``
    and, if non-empty, processes it with ``run_batch``. The loop stops on the first empty
    poll (the queue is drained) or once ``settings.MAX_BATCHES_PER_RUN`` batches have been
    started (the ceiling). Termination is evaluated only between batches, so a batch already
    running is always allowed to finish; ``run_batch``'s ``ThreadPoolExecutor`` performs
    ``shutdown(wait=True)`` on exit, guaranteeing no jobs are in flight once it returns.

    On the ceiling path the loop's ``else`` clause records the terminal reason and emits a
    single WARNING; ``drain_queue`` returns normally rather than raising, leaving any work
    not acknowledged during the run in the queue for a subsequent run. Acknowledgement is
    delegated entirely to ``run_batch``/``source`` (delete on success, leave unacknowledged
    on failure); ``drain_queue`` never calls ``source.acknowledge`` itself.

    Args:
        source (DocumentSource): Supplies batches and acknowledges completed jobs.
        pipeline (Pipeline): The shared, thread-safe pipeline instance.

    Returns:
        RunSummary: Aggregate counts and the terminal reason for the run.
    """
    batches_processed = 0
    messages_received = 0
    successes = 0
    failures = 0
    terminal_reason = "queue drained"

    # Termination is checked only between batches. run_batch blocks until its
    # ThreadPoolExecutor joins all workers, so no job is in flight at this boundary.
    while batches_processed < settings.MAX_BATCHES_PER_RUN:
        jobs = source.fetch_batch()
        if not jobs:
            # A single empty long-poll receive means the queue is drained.
            terminal_reason = "queue drained"
            break

        # Count STARTED batches so the ceiling reflects how many batches this run began.
        batches_processed += 1
        messages_received += len(jobs)

        # Acknowledgement is delegated entirely to run_batch/source; drain_queue never
        # acknowledges itself, so failed-job messages are left in the queue for redrive.
        results = run_batch(jobs, pipeline, source)
        successes += sum(1 for r in results if r.success)
        failures += sum(1 for r in results if not r.success)
    else:
        # The while condition fell through (never hit the empty-poll break): the run
        # stopped because it reached the batch ceiling.
        terminal_reason = "hit max-batches ceiling"
        logger.warning(
            "Reached MAX_BATCHES_PER_RUN ceiling (%d batches); stopping this run. "
            "Remaining work is left in the queue for the next run.",
            settings.MAX_BATCHES_PER_RUN,
        )

    return RunSummary(
        batches_processed=batches_processed,
        messages_received=messages_received,
        successes=successes,
        failures=failures,
        terminal_reason=terminal_reason,
    )


def main():
    """Main entry point for the application runner: health check, build pipeline, drain the queue, log one summary."""
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

    # Drain the queue: fetch and process batches until the queue empties or the ceiling
    # trips, then emit exactly one structured summary record operators can alert on. The
    # counts are rendered into the message via %-args so the plain-text formatter shows
    # them, and are also attached via extra so a structured/JSON sink keeps them as fields.
    summary = drain_queue(source, pipeline)
    logger.info(
        "Pipeline run summary: %d batch(es), %d message(s), %d succeeded, %d failed; terminal_reason=%s.",
        summary.batches_processed,
        summary.messages_received,
        summary.successes,
        summary.failures,
        summary.terminal_reason,
        extra={
            "batches_processed": summary.batches_processed,
            "messages_received": summary.messages_received,
            "successes": summary.successes,
            "failures": summary.failures,
            "terminal_reason": summary.terminal_reason,
        },
    )


if __name__ == "__main__":
    main()
