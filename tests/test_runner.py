import logging
from unittest import mock

import pytest

from ingestion_pipeline.orchestration.batch_processing.document_result import (
    BatchResult,
    BatchSummary,
    DocumentResult,
)
from ingestion_pipeline.orchestration.document_source import DocumentJob, FetchResult
from ingestion_pipeline.runner import RunSummary, main

"""Tests for the pipeline runner module."""


def _configure_mock_settings(mock_settings):
    mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET = "test-kta-documents-bucket"
    mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX = "26-711111"
    mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME = "Case1_TC19_50_pages_brain_injury.pdf"
    mock_settings.MAX_CONCURRENT_DOCUMENTS = 4
    mock_settings.MAX_BATCHES_PER_RUN = 50
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
# SqsDocumentSource -> drain_queue -> one structured summary log. These tests
# mock drain_queue so the wiring is verified in isolation; the drain loop
# itself is covered by the test_drain_queue_* tests below.


@mock.patch("ingestion_pipeline.runner.drain_queue")
@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_wires_source_and_pipeline_into_drain_queue(
    mock_check_opensearch_health, mock_build_pipeline, mock_source_cls, mock_drain_queue
):
    """Main builds the pipeline and source once and hands both to drain_queue."""
    mock_check_opensearch_health.return_value = True
    mock_pipeline = mock.Mock()
    mock_build_pipeline.return_value = mock_pipeline
    mock_source = mock.Mock()
    mock_source_cls.return_value = mock_source
    mock_drain_queue.return_value = RunSummary(
        batches_processed=0,
        messages_received=0,
        messages_discarded=0,
        jobs_processed=0,
        successes=0,
        failures=0,
        terminal_reason="queue drained",
    )

    main()

    mock_build_pipeline.assert_called_once()
    mock_source_cls.assert_called_once()
    mock_drain_queue.assert_called_once_with(mock_source, mock_pipeline)


@mock.patch("ingestion_pipeline.runner.drain_queue")
@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_emits_single_structured_summary_log(
    mock_check_opensearch_health, mock_build_pipeline, mock_source_cls, mock_drain_queue, caplog
):
    """Main emits exactly one INFO summary record carrying the RunSummary fields."""
    mock_check_opensearch_health.return_value = True
    summary = RunSummary(
        batches_processed=2,
        messages_received=6,
        messages_discarded=1,
        jobs_processed=5,
        successes=4,
        failures=1,
        terminal_reason="queue drained",
    )
    mock_drain_queue.return_value = summary

    with caplog.at_level(logging.INFO, logger="ingestion_pipeline.runner"):
        main()

    summary_records = [r for r in caplog.records if r.getMessage().startswith("Pipeline run summary")]
    assert len(summary_records) == 1
    record = summary_records[0]
    # The extra payload carries all seven fields as LogRecord attributes.
    assert record.batches_processed == summary.batches_processed
    assert record.messages_received == summary.messages_received
    assert record.messages_discarded == summary.messages_discarded
    assert record.jobs_processed == summary.jobs_processed
    assert record.successes == summary.successes
    assert record.failures == summary.failures
    assert record.terminal_reason == summary.terminal_reason
    # The values are now rendered into the human-readable message too.
    rendered = record.getMessage()
    assert "2 batch" in rendered
    assert "6 message" in rendered
    assert "1 discarded" in rendered
    assert "5 job" in rendered
    assert "4 succeeded" in rendered
    assert "1 failed" in rendered
    assert "terminal_reason=queue drained" in rendered


@mock.patch("ingestion_pipeline.runner.drain_queue")
@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_exits_when_queue_unresolvable(
    mock_check_opensearch_health, mock_build_pipeline, mock_source_cls, mock_drain_queue
):
    """An unresolvable queue is fatal: main exits code 1 and never drains."""
    from ingestion_pipeline.orchestration.document_source import QueueResolutionError

    mock_check_opensearch_health.return_value = True
    mock_build_pipeline.return_value = mock.Mock()
    mock_source_cls.side_effect = QueueResolutionError("no queue")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    mock_drain_queue.assert_not_called()


@mock.patch("ingestion_pipeline.runner.drain_queue")
@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.logger")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_opensearch_health_check_failure_returns(
    mock_check_opensearch_health, mock_logger, mock_build_pipeline, mock_source_cls, mock_drain_queue
):
    """Main exits early and builds nothing when the health check fails."""
    mock_check_opensearch_health.return_value = False

    main()

    mock_build_pipeline.assert_not_called()
    mock_source_cls.assert_not_called()
    mock_drain_queue.assert_not_called()
    mock_logger.critical.assert_called_with("OpenSearch health check failed. Exiting pipeline runner.")


# --- drain_queue ----------------------------------------------------------


class _FakeDocumentSource:
    """Fake DocumentSource that yields seeded batches then empty polls.

    Each seeded batch may be either a plain list of jobs (in which case the poll
    reports ``malformed_discarded=0``) or a ``(jobs, malformed_discarded)`` pair so a
    test can model malformed messages on a given poll. fetch_batch() returns each
    seeded batch in order as a FetchResult; once exhausted it returns an empty
    FetchResult. acknowledge() records its calls so tests can assert drain_queue never
    acknowledges directly.
    """

    def __init__(self, batches):
        self._batches = list(batches)
        self._index = 0
        self.fetch_calls = 0
        self.acknowledge_calls = []

    def fetch_batch(self):
        self.fetch_calls += 1
        if self._index < len(self._batches):
            batch = self._batches[self._index]
            self._index += 1
            jobs, malformed_discarded = _split_seeded_batch(batch)
            return FetchResult(jobs=jobs, malformed_discarded=malformed_discarded)
        return FetchResult(jobs=[], malformed_discarded=0)

    def acknowledge(self, job):
        self.acknowledge_calls.append(job)


class _InexhaustibleDocumentSource:
    """Fake DocumentSource that always returns a non-empty batch (never drains)."""

    def __init__(self, batch):
        self._batch = batch
        self.fetch_calls = 0
        self.acknowledge_calls = []

    def fetch_batch(self):
        self.fetch_calls += 1
        jobs, malformed_discarded = _split_seeded_batch(self._batch)
        return FetchResult(jobs=list(jobs), malformed_discarded=malformed_discarded)

    def acknowledge(self, job):
        self.acknowledge_calls.append(job)


def _split_seeded_batch(batch):
    """Normalise a seeded batch into a ``(jobs, malformed_discarded)`` pair.

    Accepts either a plain list of jobs (discards default to 0) or an explicit
    ``(jobs, malformed_discarded)`` tuple, so tests that don't care about discards
    keep passing lists while later tests can seed malformed counts per poll.
    """
    if isinstance(batch, tuple):
        jobs, malformed_discarded = batch
        return list(jobs), malformed_discarded
    return list(batch), 0


def _make_results(jobs, successes):
    """Build DocumentResults for jobs, marking the first `successes` as success."""
    return [
        DocumentResult(job=job, source_doc_id=job.source_doc_id, success=index < successes)
        for index, job in enumerate(jobs)
    ]


def _make_batch_result(jobs, successes, batch_number):
    """Wrap `_make_results` in a BatchResult with a matching BatchSummary.

    Models one processed owner per job (no duplicate collapsing), so
    ``jobs_in_batch`` equals ``len(jobs)`` and ``succeeded``/``failed`` derive from the
    per-result success flags. This mirrors what the real ``run_batch`` returns for a
    batch with no duplicate source_doc_ids.
    """
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


def test_drain_queue_stops_on_first_empty_poll(patch_settings):
    """Two non-empty batches then an empty poll: run_batch runs once per batch, drained."""
    patch_settings.MAX_BATCHES_PER_RUN = 50
    batch_one = [_make_job(case_ref="26-711111")]
    batch_two = [_make_job(case_ref="26-711112"), _make_job(case_ref="26-711113")]
    source = _FakeDocumentSource([batch_one, batch_two])
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source, batch_number: _make_batch_result(
            jobs, len(jobs), batch_number
        )
        from ingestion_pipeline.runner import RunSummary, drain_queue

        summary = drain_queue(source, pipeline)

    assert mock_run_batch.call_count == 2
    # Two non-empty batches plus the empty poll that signals drained.
    assert source.fetch_calls == 3
    assert isinstance(summary, RunSummary)
    assert summary.terminal_reason == "queue drained"
    assert summary.batches_processed == 2
    # No malformed discards, so messages_received == jobs_processed == total jobs.
    assert summary.messages_received == 3  # 1 + 2 jobs
    assert summary.messages_discarded == 0
    assert summary.jobs_processed == 3

    # run_batch was handed each batch in order, with the shared pipeline and source, and
    # a 1-based batch_number.
    first_call, second_call = mock_run_batch.call_args_list
    assert first_call.args == (batch_one, pipeline, source)
    assert first_call.kwargs == {"batch_number": 1}
    assert second_call.args == (batch_two, pipeline, source)
    assert second_call.kwargs == {"batch_number": 2}


def test_drain_queue_ceiling_stops_starting_new_batches(patch_settings):
    """An inexhaustible source stops after exactly MAX_BATCHES_PER_RUN batches."""
    patch_settings.MAX_BATCHES_PER_RUN = 2
    source = _InexhaustibleDocumentSource([_make_job()])
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source, batch_number: _make_batch_result(
            jobs, len(jobs), batch_number
        )
        from ingestion_pipeline.runner import drain_queue

        summary = drain_queue(source, pipeline)

    # Never requests an (n+1)-th batch that would start a new batch.
    assert source.fetch_calls == 2
    assert mock_run_batch.call_count == 2
    assert summary.batches_processed == 2
    assert summary.terminal_reason == "hit max-batches ceiling"
    # Two single-job batches, no discards: received == jobs_processed == 2.
    assert summary.messages_received == 2
    assert summary.jobs_processed == 2
    assert summary.messages_discarded == 0


def test_drain_queue_does_not_acknowledge_directly(patch_settings):
    """drain_queue never calls source.acknowledge; delegation leaves failed jobs queued."""
    patch_settings.MAX_BATCHES_PER_RUN = 50
    jobs = [_make_job(case_ref="26-711111"), _make_job(case_ref="26-711112")]
    source = _FakeDocumentSource([jobs])
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        # One job fails: its message must be left in the queue (never acknowledged here).
        mock_run_batch.side_effect = lambda batch, _pipeline, _source, batch_number: _make_batch_result(
            batch, 1, batch_number
        )
        from ingestion_pipeline.runner import drain_queue

        summary = drain_queue(source, pipeline)

    assert source.acknowledge_calls == []
    assert summary.successes == 1
    assert summary.failures == 1


def test_drain_queue_aggregates_successes_and_failures(patch_settings):
    """successes/failures aggregate exactly from DocumentResult.success across batches."""
    patch_settings.MAX_BATCHES_PER_RUN = 50
    batch_one = [_make_job(case_ref="26-711111"), _make_job(case_ref="26-711112")]
    batch_two = [_make_job(case_ref="26-711113")]
    source = _FakeDocumentSource([batch_one, batch_two])
    pipeline = mock.Mock()

    # batch 1 (batch_one): 1 success + 1 failure; batch 2 (batch_two): 0 success + 1 failure.
    # Keyed by the 1-based batch_number, which is stable across the fetch/FetchResult
    # boundary (the jobs list drain_queue passes is a fresh list, not the seeded object).
    successes_by_batch_number = {1: 1, 2: 0}

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda batch, _pipeline, _source, batch_number: _make_batch_result(
            batch, successes_by_batch_number[batch_number], batch_number
        )
        from ingestion_pipeline.runner import drain_queue

        summary = drain_queue(source, pipeline)

    assert summary.successes == 1
    assert summary.failures == 2
    assert summary.messages_received == 3
    assert summary.jobs_processed == 3
    assert summary.messages_discarded == 0
    assert summary.batches_processed == 2


def test_drain_queue_emits_single_warning_on_ceiling(patch_settings, caplog):
    """The ceiling path emits exactly one WARNING from drain_queue."""
    patch_settings.MAX_BATCHES_PER_RUN = 2
    source = _InexhaustibleDocumentSource([_make_job()])
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source, batch_number: _make_batch_result(
            jobs, len(jobs), batch_number
        )
        from ingestion_pipeline.runner import drain_queue

        with caplog.at_level(logging.WARNING, logger="ingestion_pipeline.runner"):
            drain_queue(source, pipeline)

    warnings = [r for r in caplog.records if r.name == "ingestion_pipeline.runner" and r.levelno == logging.WARNING]
    assert len(warnings) == 1


def test_drain_queue_emits_no_warning_on_drained(patch_settings, caplog):
    """The drained path emits zero WARNINGs from drain_queue."""
    patch_settings.MAX_BATCHES_PER_RUN = 50
    source = _FakeDocumentSource([[_make_job()]])
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source, batch_number: _make_batch_result(
            jobs, len(jobs), batch_number
        )
        from ingestion_pipeline.runner import drain_queue

        with caplog.at_level(logging.WARNING, logger="ingestion_pipeline.runner"):
            drain_queue(source, pipeline)

    warnings = [r for r in caplog.records if r.name == "ingestion_pipeline.runner" and r.levelno == logging.WARNING]
    assert len(warnings) == 0


def test_drain_queue_malformed_only_run_is_visible(patch_settings):
    """Motivating-bug regression: a malformed-only run reports non-zero received/discarded.

    A single poll that returns zero valid jobs but discarded a malformed message IS the
    terminating poll (drain_queue accounts the discard, then breaks on the empty jobs list),
    so the run is no longer summarised as all-zeros.
    """
    patch_settings.MAX_BATCHES_PER_RUN = 50
    # One poll: no valid jobs, one malformed message discarded. Because jobs is empty,
    # drain_queue accounts the discard then breaks on this same poll (queue drained).
    source = _FakeDocumentSource([([], 1)])
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        # run_batch is never called (no jobs), but patch it so a regression that started
        # a batch on an empty poll would surface here rather than hitting the real function.
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source, batch_number: _make_batch_result(
            jobs, len(jobs), batch_number
        )
        from ingestion_pipeline.runner import drain_queue

        summary = drain_queue(source, pipeline)

    mock_run_batch.assert_not_called()
    assert summary.messages_received >= 1
    assert summary.messages_discarded >= 1
    assert summary.jobs_processed == 0
    assert summary.batches_processed == 0
    assert summary.terminal_reason == "queue drained"


def test_drain_queue_assigns_batch_numbers_in_start_order(patch_settings):
    """Each started batch gets a 1-based batch_number in start order (1, 2, 3...)."""
    patch_settings.MAX_BATCHES_PER_RUN = 50
    batch_one = [_make_job(case_ref="26-711111")]
    batch_two = [_make_job(case_ref="26-711112")]
    batch_three = [_make_job(case_ref="26-711113")]
    source = _FakeDocumentSource([batch_one, batch_two, batch_three])
    pipeline = mock.Mock()

    seen_batch_numbers = []

    def _record_batch_number(jobs, _pipeline, _source, batch_number):
        seen_batch_numbers.append(batch_number)
        return _make_batch_result(jobs, len(jobs), batch_number)

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = _record_batch_number
        from ingestion_pipeline.runner import drain_queue

        summary = drain_queue(source, pipeline)

    assert seen_batch_numbers == [1, 2, 3]
    assert summary.batches_processed == 3


def test_drain_queue_preserves_discards_without_acknowledging(patch_settings):
    """Malformed discards flow through as counts; drain_queue never acks or redrives them.

    A poll carrying valid jobs alongside malformed discards contributes both to the run
    counts (received == jobs + discards, discarded == the malformed count) while drain_queue
    itself never calls source.acknowledge. SQS-level malformed deletion (delete, not DLQ) is
    covered in tests/orchestration/test_document_source.py.
    """
    patch_settings.MAX_BATCHES_PER_RUN = 50
    jobs = [_make_job(case_ref="26-711111"), _make_job(case_ref="26-711112")]
    # One poll: the valid jobs plus two malformed messages discarded, then a terminating poll.
    source = _FakeDocumentSource([(jobs, 2)])
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda batch, _pipeline, _source, batch_number: _make_batch_result(
            batch, len(batch), batch_number
        )
        from ingestion_pipeline.runner import drain_queue

        summary = drain_queue(source, pipeline)

    assert summary.messages_discarded == 2
    assert summary.jobs_processed == len(jobs)
    assert summary.messages_received == len(jobs) + 2
    # drain_queue delegates all acknowledgement; the malformed messages were already deleted
    # by the source, never acked or redriven by the runner.
    assert source.acknowledge_calls == []
