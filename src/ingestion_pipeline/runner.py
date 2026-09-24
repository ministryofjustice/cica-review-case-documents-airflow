"""Pipeline runner: a long-lived worker that drains the SQS document queue forever.

The runner is designed to run as a long-lived Kubernetes Deployment pod. It builds a
single :class:`Pipeline` and its underlying AWS/OpenSearch clients once in the main
thread and then loops: fetch a batch from a :class:`DocumentSource` (SQS-backed) and,
when non-empty, process it in parallel via ``run_batch``. Worker threads set their own
logging context so per-document log lines stay correctly attributed.

Loop semantics (see :func:`run_forever`):

* **Work available** - process the batch and continue.
* **Empty poll** - the queue had nothing right now; keep polling. The SQS long-poll
  already blocked for ``SQS_POLL_WAIT_TIME_SECONDS``, so this does not busy-spin.
* **Transient receive error** - the source reports it as an empty poll tagged
  ``TRANSIENT_ERROR``; back off for ``SQS_TRANSIENT_ERROR_BACKOFF_SECONDS`` and retry.
  A transient blip therefore never masquerades as "queue drained" - there is no
  terminal "drained" state for a long-lived worker.
* **Permanent/unknown receive error** - propagates out of ``fetch_batch`` and crashes
  the process so Kubernetes restarts the pod and the fault is visible.
* **Signalled to stop** (``SIGTERM``/``SIGINT``) - the loop finishes the in-flight
  batch (``run_batch`` joins its thread pool before returning), logs a final summary,
  and returns so the process exits 0 cleanly.
"""

import logging
import signal
import sys
import threading

from ingestion_pipeline.config import settings
from ingestion_pipeline.custom_logging.log_context import setup_logging
from ingestion_pipeline.indexing.healthcheck import check_opensearch_health
from ingestion_pipeline.orchestration.batch_processing.batch_runner import run_batch
from ingestion_pipeline.orchestration.document_source import (
    DocumentSource,
    FetchOutcome,
    QueueResolutionError,
    SqsDocumentSource,
)
from ingestion_pipeline.orchestration.pipeline import Pipeline
from ingestion_pipeline.pipeline_builder import build_pipeline

setup_logging()
logger = logging.getLogger(__name__)


class RunTotals:
    """Mutable cumulative counters for the lifetime of a :func:`run_forever` worker.

    A long-lived worker has no "end of run" at which to emit a single summary, so it
    keeps running totals and logs a snapshot after each processed batch (and a final
    snapshot on shutdown). The counters satisfy the accounting invariant
    ``messages_received == jobs_processed + messages_discarded`` by construction: every
    poll moves the three message counters together.

    Attributes:
        batches_processed (int): Number of non-empty batches processed.
        messages_received (int): Total messages pulled off SQS, counting both valid jobs
            and malformed messages discarded, summed over every poll.
        messages_discarded (int): Total malformed messages discarded.
        jobs_processed (int): Total valid jobs handed to batches.
        successes (int): Count of ``DocumentResult.success`` being True across all results.
        failures (int): Count of ``DocumentResult.success`` being False across all results.
        empty_polls (int): Number of genuine empty long-poll receives.
        transient_errors (int): Number of transient receive errors backed off and retried.
    """

    def __init__(self) -> None:
        """Initialise all counters to zero."""
        self.batches_processed = 0
        self.messages_received = 0
        self.messages_discarded = 0
        self.jobs_processed = 0
        self.successes = 0
        self.failures = 0
        self.empty_polls = 0
        self.transient_errors = 0

    def log_summary(self, *, final: bool = False) -> None:
        """Emit one structured INFO summary carrying the current cumulative totals.

        Args:
            final (bool): When True, mark the record as the shutdown summary so operators
                can distinguish the last line before the worker exits from the per-batch
                progress lines.
        """
        prefix = "Pipeline final summary" if final else "Pipeline progress summary"
        logger.info(
            "%s: %d batch(es), %d message(s) received, %d discarded, %d job(s) processed, "
            "%d succeeded, %d failed, %d empty poll(s), %d transient error(s).",
            prefix,
            self.batches_processed,
            self.messages_received,
            self.messages_discarded,
            self.jobs_processed,
            self.successes,
            self.failures,
            self.empty_polls,
            self.transient_errors,
            extra={
                "batches_processed": self.batches_processed,
                "messages_received": self.messages_received,
                "messages_discarded": self.messages_discarded,
                "jobs_processed": self.jobs_processed,
                "successes": self.successes,
                "failures": self.failures,
                "empty_polls": self.empty_polls,
                "transient_errors": self.transient_errors,
                "final": final,
            },
        )


def _install_signal_handlers(stop_event: threading.Event) -> None:
    """Install SIGTERM/SIGINT handlers that request a graceful stop.

    Kubernetes sends SIGTERM on pod shutdown (rollout, scale-down). The handler only
    sets ``stop_event`` so the loop can finish the in-flight batch and exit cleanly
    rather than being interrupted mid-batch. SIGINT (Ctrl-C) is handled the same way for
    local runs.

    Signal handlers can only be installed from the main thread; when the runner is
    driven from a non-main thread (e.g. some test harnesses) this logs a warning and
    continues without handlers.

    Args:
        stop_event (threading.Event): The event set to request loop termination.
    """

    def _handle(signum, _frame):
        logger.info("Received signal %s; finishing in-flight work then shutting down.", signal.Signals(signum).name)
        stop_event.set()

    try:
        signal.signal(signal.SIGTERM, _handle)
        signal.signal(signal.SIGINT, _handle)
    except ValueError:
        # Raised when not on the main thread; the worker still runs, just without
        # cooperative signal handling (the platform's default handlers apply).
        logger.warning("Could not install signal handlers (not on main thread); running without graceful shutdown.")


def run_forever(
    source: DocumentSource,
    pipeline: Pipeline,
    stop_event: threading.Event,
) -> RunTotals:
    """Poll the queue and process batches until asked to stop.

    Loops until ``stop_event`` is set (by a signal handler). On each iteration it fetches
    one batch and dispatches on the fetch outcome:

    * ``RECEIVED`` - process the batch with ``run_batch``, fold its results into the
      running totals, and log a progress summary.
    * ``EMPTY`` - a genuine empty long-poll receive; count it and keep polling. No sleep
      is needed because the receive already blocked for the long-poll wait.
    * ``TRANSIENT_ERROR`` - the source swallowed a transient receive error; count it and
      sleep ``settings.SQS_TRANSIENT_ERROR_BACKOFF_SECONDS`` before the next poll so the
      loop does not spin against a degraded queue. The sleep is interruptible by
      ``stop_event`` so shutdown stays responsive.

    Permanent or unknown receive errors are not handled here: ``fetch_batch`` re-raises
    them, so they propagate out of this function and crash the worker (Kubernetes then
    restarts the pod). ``stop_event`` is re-checked between batches, so a batch already
    running always finishes; ``run_batch``'s ``ThreadPoolExecutor`` performs
    ``shutdown(wait=True)`` on exit, guaranteeing no jobs are in flight at that boundary.

    Acknowledgement is delegated entirely to ``run_batch``/``source`` (delete on success,
    leave unacknowledged on failure so SQS redrives to the DLQ); this loop never calls
    ``source.acknowledge`` itself.

    Args:
        source (DocumentSource): Supplies batches and acknowledges completed jobs.
        pipeline (Pipeline): The shared, thread-safe pipeline instance.
        stop_event (threading.Event): Set by a signal handler to request a graceful stop.

    Returns:
        RunTotals: The cumulative counters accrued before the worker was stopped.
    """
    totals = RunTotals()

    # stop_event is checked only between batches. run_batch blocks until its
    # ThreadPoolExecutor joins all workers, so no job is in flight at this boundary.
    while not stop_event.is_set():
        fetch_result = source.fetch_batch()
        jobs = fetch_result.jobs
        malformed_discarded = fetch_result.malformed_discarded

        # Account EVERY poll's messages before branching so a poll that only discarded
        # malformed messages still lifts the counters and the conservation invariant
        # (received == jobs_processed + discarded) holds by construction.
        totals.messages_received += len(jobs) + malformed_discarded
        totals.messages_discarded += malformed_discarded
        totals.jobs_processed += len(jobs)

        if fetch_result.outcome is FetchOutcome.TRANSIENT_ERROR:
            # Transient blip: never mistaken for "drained". Back off (interruptibly) and
            # retry rather than spinning against a throttled/unreachable queue.
            totals.transient_errors += 1
            if stop_event.wait(timeout=settings.SQS_TRANSIENT_ERROR_BACKOFF_SECONDS):
                break
            continue

        if not jobs:
            # Genuine empty long-poll receive: nothing to do right now, keep polling. The
            # long-poll already blocked, so no extra sleep. A quiet debug line avoids
            # spamming INFO while the queue idles.
            totals.empty_polls += 1
            logger.debug("Empty poll; queue idle, continuing to poll.")
            continue

        # Increment before run_batch so batch_number is 1-based in start order.
        totals.batches_processed += 1
        batch_result = run_batch(jobs, pipeline, source, batch_number=totals.batches_processed)
        results = batch_result.results
        totals.successes += sum(1 for r in results if r.success)
        totals.failures += sum(1 for r in results if not r.success)
        totals.log_summary()

    return totals


def main():
    """Entry point: health check, build pipeline, then poll the queue forever until stopped."""
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

    # Build the pipeline (and all AWS/OpenSearch clients) once and share it across worker
    # threads. All components are stateless per-document and their clients are safe to
    # call concurrently.
    pipeline = build_pipeline()

    # Connect to the SQS document queue. An unresolvable queue is fatal: log and exit
    # non-zero rather than looping forever with no source of work.
    try:
        source: DocumentSource = SqsDocumentSource()
    except QueueResolutionError as exc:
        logger.critical(f"Could not connect to the SQS document queue; exiting: {exc}")
        sys.exit(1)

    # Cooperative shutdown: the signal handlers set this event; run_forever finishes the
    # in-flight batch and returns so the process exits 0 cleanly.
    stop_event = threading.Event()
    _install_signal_handlers(stop_event)

    logger.info("Entering poll loop; will run until signalled to stop.")
    totals = run_forever(source, pipeline, stop_event)
    totals.log_summary(final=True)
    logger.info("Pipeline runner stopped cleanly.")


if __name__ == "__main__":
    main()
