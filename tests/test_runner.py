import logging
import threading
from unittest import mock

import pytest

from ingestion_pipeline.orchestration.batch_processing.document_result import (
    BatchResult,
    BatchSummary,
    DocumentResult,
)
from ingestion_pipeline.orchestration.document_source import (
    DocumentJob,
    FetchOutcome,
    FetchResult,
)
from ingestion_pipeline.runner import RunTotals, main, run_forever

"""Tests for the pipeline runner module."""


def _configure_mock_settings(mock_settings):
    mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET = "test-kta-documents-bucket"
    mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX = "26-711111"
    mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME = "Case1_TC19_50_pages_brain_injury.pdf"
    mock_settings.MAX_CONCURRENT_DOCUMENTS = 4
    mock_settings.SQS_TRANSIENT_ERROR_BACKOFF_SECONDS = 5.0
    mock_settings.OPENSEARCH_PROXY_URL = "http://localhost:9200"
    mock_settings.OPENSEARCH_VERIFY_CERTS = True
    mock_settings.OPENSEARCH_SSL_ASSERT_HOSTNAME = True
    mock_settings.LOCAL_DEVELOPMENT_MODE = False


@pytest.fixture(autouse=True)
def patch_settings():
    # `main` reads settings in `runner`, but it drives the batch through
    # `batch_runner`, whose worker reads settings looked up in its own module.
    # Patch both so the full `main` -> run_batch -> process_document_job flow sees
    # the same fully-mocked settings (the pre-refactor behaviour, when the worker
    # lived in `runner`).
    with (
        mock.patch("ingestion_pipeline.runner.settings") as mock_settings,
        mock.patch(
            "ingestion_pipeline.orchestration.batch_processing.batch_runner.settings",
            new=mock_settings,
        ),
    ):
        _configure_mock_settings(mock_settings)
        yield mock_settings


def _make_job(
    s3_uri: str = "s3://test-kta-documents-bucket/26-711111/Case1_TC19_50_pages_brain_injury.pdf",
    case_ref: str = "26-711111",
) -> DocumentJob:
    return DocumentJob(
        source_file_s3_uri=s3_uri,
        correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
        case_ref=case_ref,
    )


# --- main (thin wiring) ---------------------------------------------------
#
# main()'s job is wiring, not looping: health check -> build_pipeline ->
# SqsDocumentSource -> install signal handlers -> run_forever -> final summary
# log. These tests mock run_forever so the wiring is verified in isolation; the
# poll loop itself is covered by the test_run_forever_* tests below.


@mock.patch("ingestion_pipeline.runner.run_forever")
@mock.patch("ingestion_pipeline.runner._install_signal_handlers")
@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_wires_source_and_pipeline_into_run_forever(
    mock_check_opensearch_health,
    mock_build_pipeline,
    mock_source_cls,
    mock_install_handlers,
    mock_run_forever,
):
    """Main builds the pipeline and source once, installs handlers, and drives run_forever."""
    mock_check_opensearch_health.return_value = True
    mock_pipeline = mock.Mock()
    mock_build_pipeline.return_value = mock_pipeline
    mock_source = mock.Mock()
    mock_source_cls.return_value = mock_source
    mock_run_forever.return_value = RunTotals()

    main()

    mock_build_pipeline.assert_called_once()
    mock_source_cls.assert_called_once()
    mock_install_handlers.assert_called_once()
    # run_forever is handed the source, the pipeline, and a stop Event.
    assert mock_run_forever.call_count == 1
    args, _kwargs = mock_run_forever.call_args
    assert args[0] is mock_source
    assert args[1] is mock_pipeline
    assert isinstance(args[2], threading.Event)
    # The same event object is the one passed to the signal-handler installer.
    assert mock_install_handlers.call_args.args[0] is args[2]


@mock.patch("ingestion_pipeline.runner.run_forever")
@mock.patch("ingestion_pipeline.runner._install_signal_handlers")
@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_emits_final_summary_log(
    mock_check_opensearch_health,
    mock_build_pipeline,
    mock_source_cls,
    mock_install_handlers,
    mock_run_forever,
    caplog,
):
    """Main emits exactly one final INFO summary record carrying the totals."""
    mock_check_opensearch_health.return_value = True
    totals = RunTotals()
    totals.batches_processed = 2
    totals.messages_received = 6
    totals.messages_discarded = 1
    totals.jobs_processed = 5
    totals.successes = 4
    totals.failures = 1
    totals.empty_polls = 3
    totals.transient_errors = 2
    mock_run_forever.return_value = totals

    with caplog.at_level(logging.INFO, logger="ingestion_pipeline.runner"):
        main()

    final_records = [r for r in caplog.records if r.getMessage().startswith("Pipeline final summary")]
    assert len(final_records) == 1
    record = final_records[0]
    assert record.batches_processed == 2
    assert record.messages_received == 6
    assert record.messages_discarded == 1
    assert record.jobs_processed == 5
    assert record.successes == 4
    assert record.failures == 1
    assert record.empty_polls == 3
    assert record.transient_errors == 2
    assert record.final is True
    rendered = record.getMessage()
    assert "2 batch" in rendered
    assert "6 message" in rendered
    assert "1 discarded" in rendered
    assert "5 job" in rendered
    assert "4 succeeded" in rendered
    assert "1 failed" in rendered


@mock.patch("ingestion_pipeline.runner.run_forever")
@mock.patch("ingestion_pipeline.runner._install_signal_handlers")
@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_exits_when_queue_unresolvable(
    mock_check_opensearch_health,
    mock_build_pipeline,
    mock_source_cls,
    mock_install_handlers,
    mock_run_forever,
):
    """An unresolvable queue is fatal: main exits code 1 and never enters the loop."""
    from ingestion_pipeline.orchestration.document_source import QueueResolutionError

    mock_check_opensearch_health.return_value = True
    mock_build_pipeline.return_value = mock.Mock()
    mock_source_cls.side_effect = QueueResolutionError("no queue")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    mock_run_forever.assert_not_called()


@mock.patch("ingestion_pipeline.runner.run_forever")
@mock.patch("ingestion_pipeline.runner._install_signal_handlers")
@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.logger")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_opensearch_health_check_failure_returns(
    mock_check_opensearch_health,
    mock_logger,
    mock_build_pipeline,
    mock_source_cls,
    mock_install_handlers,
    mock_run_forever,
):
    """Main exits early and builds nothing when the health check fails."""
    mock_check_opensearch_health.return_value = False

    main()

    mock_build_pipeline.assert_not_called()
    mock_source_cls.assert_not_called()
    mock_run_forever.assert_not_called()
    mock_logger.critical.assert_called_with("OpenSearch health check failed. Exiting pipeline runner.")


@mock.patch("ingestion_pipeline.runner.run_forever")
@mock.patch("ingestion_pipeline.runner._install_signal_handlers")
@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_warns_in_local_development_mode(
    mock_check_opensearch_health,
    mock_build_pipeline,
    mock_source_cls,
    mock_install_handlers,
    mock_run_forever,
    caplog,
    patch_settings,
):
    """LOCAL_DEVELOPMENT_MODE emits the LocalStack warning before entering the loop."""
    patch_settings.LOCAL_DEVELOPMENT_MODE = True
    mock_check_opensearch_health.return_value = True
    mock_run_forever.return_value = RunTotals()

    with caplog.at_level(logging.WARNING, logger="ingestion_pipeline.runner"):
        main()

    assert any("LOCAL_DEVELOPMENT_MODE" in r.getMessage() for r in caplog.records)


# --- _install_signal_handlers ---------------------------------------------


def test_install_signal_handlers_registers_and_sets_event():
    """Registered SIGTERM/SIGINT handlers set the stop event when invoked."""
    from ingestion_pipeline.runner import _install_signal_handlers

    stop_event = threading.Event()
    registered = {}

    def _fake_signal(signum, handler):
        registered[signum] = handler

    with mock.patch("ingestion_pipeline.runner.signal.signal", side_effect=_fake_signal):
        _install_signal_handlers(stop_event)

    import signal as _signal

    assert _signal.SIGTERM in registered
    assert _signal.SIGINT in registered
    # Invoking the registered handler requests a graceful stop.
    assert not stop_event.is_set()
    registered[_signal.SIGTERM](_signal.SIGTERM, None)
    assert stop_event.is_set()


def test_install_signal_handlers_tolerates_non_main_thread():
    """A ValueError (not on the main thread) is caught and logged, not raised."""
    from ingestion_pipeline.runner import _install_signal_handlers

    stop_event = threading.Event()
    with (
        mock.patch("ingestion_pipeline.runner.signal.signal", side_effect=ValueError("not main thread")),
        mock.patch("ingestion_pipeline.runner.logger") as mock_logger,
    ):
        _install_signal_handlers(stop_event)  # must not raise

    assert mock_logger.warning.called


# --- run_forever ----------------------------------------------------------


class _StoppingDocumentSource:
    """Fake DocumentSource that yields seeded polls then stops the loop.

    Each seeded poll is a ``FetchResult``. fetch_batch() returns each in order; once the
    seeded polls are exhausted it sets ``stop_event`` (so the forever-loop terminates)
    and returns a final empty poll. acknowledge() records its calls so tests can assert
    run_forever never acknowledges directly.
    """

    def __init__(self, polls, stop_event):
        self._polls = list(polls)
        self._index = 0
        self._stop_event = stop_event
        self.fetch_calls = 0
        self.acknowledge_calls = []

    def fetch_batch(self):
        self.fetch_calls += 1
        if self._index < len(self._polls):
            poll = self._polls[self._index]
            self._index += 1
            return poll
        # Seeded polls exhausted: ask the loop to stop and return a benign empty poll.
        self._stop_event.set()
        return FetchResult(jobs=[], malformed_discarded=0, outcome=FetchOutcome.EMPTY)

    def acknowledge(self, job):
        self.acknowledge_calls.append(job)


def _received(jobs, malformed_discarded=0):
    """Build a RECEIVED FetchResult from a list of jobs."""
    return FetchResult(jobs=list(jobs), malformed_discarded=malformed_discarded, outcome=FetchOutcome.RECEIVED)


def _empty(malformed_discarded=0):
    """Build an EMPTY FetchResult (a genuine empty long-poll receive)."""
    return FetchResult(jobs=[], malformed_discarded=malformed_discarded, outcome=FetchOutcome.EMPTY)


def _transient():
    """Build a TRANSIENT_ERROR FetchResult (a swallowed transient receive error)."""
    return FetchResult(jobs=[], malformed_discarded=0, outcome=FetchOutcome.TRANSIENT_ERROR)


def _make_results(jobs, successes):
    """Build DocumentResults for jobs, marking the first `successes` as success."""
    return [
        DocumentResult(job=job, source_doc_id=job.source_doc_id, success=index < successes)
        for index, job in enumerate(jobs)
    ]


def _make_batch_result(jobs, successes, batch_number):
    """Wrap `_make_results` in a BatchResult with a matching BatchSummary."""
    results = _make_results(jobs, successes)
    succeeded = sum(1 for r in results if r.success)
    failed = len(results) - succeeded
    summary = BatchSummary(
        batch_number=batch_number,
        jobs_in_batch=len(jobs),
        succeeded=succeeded,
        failed=failed,
        duplicates_collapsed=0,
    )
    return BatchResult(summary=summary, results=results)


def test_run_forever_processes_batches_until_stopped(patch_settings):
    """Two non-empty polls then stop: run_batch runs once per batch, totals aggregate."""
    stop_event = threading.Event()
    batch_one = [_make_job(case_ref="26-711111")]
    batch_two = [_make_job(case_ref="26-711112"), _make_job(case_ref="26-711113")]
    source = _StoppingDocumentSource([_received(batch_one), _received(batch_two)], stop_event)
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source, batch_number: _make_batch_result(
            jobs, len(jobs), batch_number
        )
        totals = run_forever(source, pipeline, stop_event)

    assert mock_run_batch.call_count == 2
    assert isinstance(totals, RunTotals)
    assert totals.batches_processed == 2
    assert totals.messages_received == 3  # 1 + 2 jobs
    assert totals.messages_discarded == 0
    assert totals.jobs_processed == 3

    # run_batch was handed each batch in order, with the shared pipeline and source, and
    # a 1-based batch_number.
    first_call, second_call = mock_run_batch.call_args_list
    assert first_call.args == (batch_one, pipeline, source)
    assert first_call.kwargs == {"batch_number": 1}
    assert second_call.args == (batch_two, pipeline, source)
    assert second_call.kwargs == {"batch_number": 2}


def test_run_forever_keeps_polling_on_empty(patch_settings):
    """A genuine empty poll does not stop the loop; it is counted and polling continues."""
    stop_event = threading.Event()
    # An empty poll, then a real batch, then the source stops the loop.
    batch = [_make_job()]
    source = _StoppingDocumentSource([_empty(), _received(batch)], stop_event)
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source, batch_number: _make_batch_result(
            jobs, len(jobs), batch_number
        )
        totals = run_forever(source, pipeline, stop_event)

    # The empty poll did NOT terminate the loop; the later batch was still processed.
    assert mock_run_batch.call_count == 1
    assert totals.batches_processed == 1
    # At least one empty poll counted (the seeded one plus the terminating empty poll).
    assert totals.empty_polls >= 1


def test_run_forever_backs_off_on_transient_error(patch_settings):
    """A transient poll is counted and triggers an interruptible backoff, not termination."""
    patch_settings.SQS_TRANSIENT_ERROR_BACKOFF_SECONDS = 7.0
    stop_event = threading.Event()
    batch = [_make_job()]
    # Transient error first (must not stop the loop), then a real batch, then stop.
    source = _StoppingDocumentSource([_transient(), _received(batch)], stop_event)
    pipeline = mock.Mock()

    with (
        mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch,
        mock.patch.object(stop_event, "wait", wraps=stop_event.wait) as mock_wait,
    ):
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source, batch_number: _make_batch_result(
            jobs, len(jobs), batch_number
        )
        totals = run_forever(source, pipeline, stop_event)

    # The transient poll did NOT terminate the loop; the later batch was still processed.
    assert mock_run_batch.call_count == 1
    assert totals.transient_errors == 1
    # Backoff used the interruptible wait with the configured timeout.
    mock_wait.assert_any_call(timeout=7.0)


def test_run_forever_transient_backoff_interrupted_by_stop(patch_settings):
    """If stop is signalled during the transient backoff, the loop exits promptly."""
    patch_settings.SQS_TRANSIENT_ERROR_BACKOFF_SECONDS = 30.0
    stop_event = threading.Event()
    source = _StoppingDocumentSource([_transient()], stop_event)
    pipeline = mock.Mock()

    # Simulate the stop signal arriving mid-backoff: wait() returns True (event set)
    # without actually sleeping, so the test does not block on the 30s timeout.
    def _fake_wait(timeout=None):
        stop_event.set()
        return True

    with (
        mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch,
        mock.patch.object(stop_event, "wait", side_effect=_fake_wait),
    ):
        totals = run_forever(source, pipeline, stop_event)

    mock_run_batch.assert_not_called()
    assert totals.transient_errors == 1
    assert totals.batches_processed == 0


def test_run_forever_propagates_permanent_error(patch_settings):
    """A permanent receive error from fetch_batch propagates out and crashes the worker."""
    stop_event = threading.Event()
    source = mock.Mock()
    source.fetch_batch.side_effect = RuntimeError("AccessDenied")
    pipeline = mock.Mock()

    with pytest.raises(RuntimeError, match="AccessDenied"):
        run_forever(source, pipeline, stop_event)


def test_run_forever_does_not_acknowledge_directly(patch_settings):
    """run_forever never calls source.acknowledge; delegation leaves failed jobs queued."""
    stop_event = threading.Event()
    jobs = [_make_job(case_ref="26-711111"), _make_job(case_ref="26-711112")]
    source = _StoppingDocumentSource([_received(jobs)], stop_event)
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        # One job fails: its message must be left in the queue (never acknowledged here).
        mock_run_batch.side_effect = lambda batch, _pipeline, _source, batch_number: _make_batch_result(
            batch, 1, batch_number
        )
        totals = run_forever(source, pipeline, stop_event)

    assert source.acknowledge_calls == []
    assert totals.successes == 1
    assert totals.failures == 1


def test_run_forever_aggregates_successes_and_failures(patch_settings):
    """successes/failures aggregate exactly from DocumentResult.success across batches."""
    stop_event = threading.Event()
    batch_one = [_make_job(case_ref="26-711111"), _make_job(case_ref="26-711112")]
    batch_two = [_make_job(case_ref="26-711113")]
    source = _StoppingDocumentSource([_received(batch_one), _received(batch_two)], stop_event)
    pipeline = mock.Mock()

    # batch 1: 1 success + 1 failure; batch 2: 0 success + 1 failure.
    successes_by_batch_number = {1: 1, 2: 0}

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda batch, _pipeline, _source, batch_number: _make_batch_result(
            batch, successes_by_batch_number[batch_number], batch_number
        )
        totals = run_forever(source, pipeline, stop_event)

    assert totals.successes == 1
    assert totals.failures == 2
    assert totals.messages_received == 3
    assert totals.jobs_processed == 3
    assert totals.messages_discarded == 0
    assert totals.batches_processed == 2


def test_run_forever_logs_progress_summary_per_batch(patch_settings, caplog):
    """Each processed batch emits one progress summary INFO record."""
    stop_event = threading.Event()
    source = _StoppingDocumentSource([_received([_make_job()]), _received([_make_job()])], stop_event)
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source, batch_number: _make_batch_result(
            jobs, len(jobs), batch_number
        )
        with caplog.at_level(logging.INFO, logger="ingestion_pipeline.runner"):
            run_forever(source, pipeline, stop_event)

    progress_records = [r for r in caplog.records if r.getMessage().startswith("Pipeline progress summary")]
    assert len(progress_records) == 2


def test_run_forever_preserves_discards_without_acknowledging(patch_settings):
    """Malformed discards flow through as counts; run_forever never acks or redrives them."""
    stop_event = threading.Event()
    jobs = [_make_job(case_ref="26-711111"), _make_job(case_ref="26-711112")]
    # One poll: valid jobs plus two malformed messages discarded, then the source stops.
    source = _StoppingDocumentSource([_received(jobs, malformed_discarded=2)], stop_event)
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda batch, _pipeline, _source, batch_number: _make_batch_result(
            batch, len(batch), batch_number
        )
        totals = run_forever(source, pipeline, stop_event)

    assert totals.messages_discarded == 2
    assert totals.jobs_processed == len(jobs)
    assert totals.messages_received == len(jobs) + 2
    assert source.acknowledge_calls == []


def test_run_forever_stops_immediately_if_already_stopped(patch_settings):
    """If the stop event is already set, the loop performs no polls and no batches."""
    stop_event = threading.Event()
    stop_event.set()
    source = _StoppingDocumentSource([_received([_make_job()])], stop_event)
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        totals = run_forever(source, pipeline, stop_event)

    assert source.fetch_calls == 0
    mock_run_batch.assert_not_called()
    assert totals.batches_processed == 0
