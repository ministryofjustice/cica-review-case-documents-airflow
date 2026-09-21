import logging
from unittest import mock

import pytest

from ingestion_pipeline.orchestration.document_source import DocumentJob
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
        messages_received=5,
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
    # The extra payload is unchanged: the five fields remain LogRecord attributes.
    assert record.batches_processed == summary.batches_processed
    assert record.messages_received == summary.messages_received
    assert record.successes == summary.successes
    assert record.failures == summary.failures
    assert record.terminal_reason == summary.terminal_reason
    # The values are now rendered into the human-readable message too.
    rendered = record.getMessage()
    assert "2 batch" in rendered
    assert "5 message" in rendered
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

    fetch_batch() returns each seeded batch in order; once exhausted it returns
    []. acknowledge() records its calls so tests can assert drain_queue never
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
            return batch
        return []

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
        return list(self._batch)

    def acknowledge(self, job):
        self.acknowledge_calls.append(job)


def _make_results(jobs, successes):
    """Build DocumentResults for jobs, marking the first `successes` as success."""
    from ingestion_pipeline.orchestration.batch_processing.document_result import DocumentResult

    return [
        DocumentResult(job=job, source_doc_id=job.source_doc_id, success=index < successes)
        for index, job in enumerate(jobs)
    ]


def test_drain_queue_stops_on_first_empty_poll(patch_settings):
    """Two non-empty batches then an empty poll: run_batch runs once per batch, drained."""
    patch_settings.MAX_BATCHES_PER_RUN = 50
    batch_one = [_make_job(case_ref="26-711111")]
    batch_two = [_make_job(case_ref="26-711112"), _make_job(case_ref="26-711113")]
    source = _FakeDocumentSource([batch_one, batch_two])
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source: _make_results(jobs, len(jobs))
        from ingestion_pipeline.runner import RunSummary, drain_queue

        summary = drain_queue(source, pipeline)

    assert mock_run_batch.call_count == 2
    # Two non-empty batches plus the empty poll that signals drained.
    assert source.fetch_calls == 3
    assert isinstance(summary, RunSummary)
    assert summary.terminal_reason == "queue drained"
    assert summary.batches_processed == 2
    assert summary.messages_received == 3  # 1 + 2 jobs

    # run_batch was handed each batch in order, with the shared pipeline and source.
    first_call, second_call = mock_run_batch.call_args_list
    assert first_call.args == (batch_one, pipeline, source)
    assert second_call.args == (batch_two, pipeline, source)


def test_drain_queue_ceiling_stops_starting_new_batches(patch_settings):
    """An inexhaustible source stops after exactly MAX_BATCHES_PER_RUN batches."""
    patch_settings.MAX_BATCHES_PER_RUN = 2
    source = _InexhaustibleDocumentSource([_make_job()])
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source: _make_results(jobs, len(jobs))
        from ingestion_pipeline.runner import drain_queue

        summary = drain_queue(source, pipeline)

    # Never requests an (n+1)-th batch that would start a new batch.
    assert source.fetch_calls == 2
    assert mock_run_batch.call_count == 2
    assert summary.batches_processed == 2
    assert summary.terminal_reason == "hit max-batches ceiling"


def test_drain_queue_does_not_acknowledge_directly(patch_settings):
    """drain_queue never calls source.acknowledge; delegation leaves failed jobs queued."""
    patch_settings.MAX_BATCHES_PER_RUN = 50
    jobs = [_make_job(case_ref="26-711111"), _make_job(case_ref="26-711112")]
    source = _FakeDocumentSource([jobs])
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        # One job fails: its message must be left in the queue (never acknowledged here).
        mock_run_batch.side_effect = lambda batch, _pipeline, _source: _make_results(batch, successes=1)
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

    # batch_one: 1 success + 1 failure; batch_two: 0 success + 1 failure.
    outcomes = {id(batch_one): 1, id(batch_two): 0}

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda batch, _pipeline, _source: _make_results(batch, outcomes[id(batch)])
        from ingestion_pipeline.runner import drain_queue

        summary = drain_queue(source, pipeline)

    assert summary.successes == 1
    assert summary.failures == 2
    assert summary.messages_received == 3
    assert summary.batches_processed == 2


def test_drain_queue_emits_single_warning_on_ceiling(patch_settings, caplog):
    """The ceiling path emits exactly one WARNING from drain_queue."""
    patch_settings.MAX_BATCHES_PER_RUN = 2
    source = _InexhaustibleDocumentSource([_make_job()])
    pipeline = mock.Mock()

    with mock.patch("ingestion_pipeline.runner.run_batch") as mock_run_batch:
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source: _make_results(jobs, len(jobs))
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
        mock_run_batch.side_effect = lambda jobs, _pipeline, _source: _make_results(jobs, len(jobs))
        from ingestion_pipeline.runner import drain_queue

        with caplog.at_level(logging.WARNING, logger="ingestion_pipeline.runner"):
            drain_queue(source, pipeline)

    warnings = [r for r in caplog.records if r.name == "ingestion_pipeline.runner" and r.levelno == logging.WARNING]
    assert len(warnings) == 0
