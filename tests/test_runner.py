import datetime
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.errors import DlqCategory, EmptyTextractResponseError, PipelineError, ZeroChunksError
from ingestion_pipeline.orchestration.document_source import DocumentJob
from ingestion_pipeline.runner import main, process_document_job, run_batch

"""Tests for the pipeline runner module."""


@pytest.fixture(autouse=True)
def patch_settings():
    with mock.patch("ingestion_pipeline.runner.settings") as mock_settings:
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET = "test-kta-documents-bucket"
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX = "26-711111"
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME = "Case1_TC19_50_pages_brain_injury.pdf"
        mock_settings.MAX_CONCURRENT_DOCUMENTS = 4
        mock_settings.OPENSEARCH_PROXY_URL = "http://localhost:9200"
        mock_settings.OPENSEARCH_VERIFY_CERTS = True
        mock_settings.OPENSEARCH_SSL_ASSERT_HOSTNAME = True
        mock_settings.LOCAL_DEVELOPMENT_MODE = False
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


# --- process_document_job -------------------------------------------------


def test_process_document_job_success_builds_metadata_and_runs_pipeline():
    """A valid job runs the pipeline and, on a clean return, reports success."""
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    job = _make_job()

    result = process_document_job(job, pipeline)

    assert result.success is True
    assert result.error is None
    assert result.category is None
    assert result.retryable is None
    assert result.source_doc_id
    pipeline.process_document.assert_called_once()

    metadata = pipeline.process_document.call_args.kwargs["document_metadata"]
    assert isinstance(metadata, DocumentMetadata)
    assert metadata.source_file_name == "Case1_TC19_50_pages_brain_injury.pdf"
    assert metadata.case_ref == "26-711111"
    assert metadata.correspondence_type == "TC19 - ADDITIONAL INFO REQUEST"
    assert metadata.page_count is None


def test_process_document_job_invalid_uri_is_contained():
    """An invalid S3 URI is caught and reported as an unexpected, non-retryable failure."""
    pipeline = mock.Mock()
    job = _make_job(s3_uri="s3://test-kta-documents-bucket/not-a-case-ref/file.pdf", case_ref="not-a-case-ref")

    result = process_document_job(job, pipeline)

    assert result.success is False
    assert isinstance(result.error, ValueError)
    assert result.category is DlqCategory.UNEXPECTED
    assert result.retryable is False
    pipeline.process_document.assert_not_called()


def test_process_document_job_contains_unexpected_exception(caplog):
    """An unexpected (non-PipelineError) failure is contained and classified UNEXPECTED."""
    pipeline = mock.Mock()
    pipeline.process_document.side_effect = RuntimeError("boom")
    job = _make_job()

    with caplog.at_level(logging.CRITICAL, logger="ingestion_pipeline.runner"):
        result = process_document_job(job, pipeline)

    assert result.success is False
    assert isinstance(result.error, RuntimeError)
    assert result.category is DlqCategory.UNEXPECTED
    assert result.retryable is False

    critical_records = [
        record
        for record in caplog.records
        if record.levelno == logging.CRITICAL
        and "Pipeline runner encountered an unexpected error" in record.getMessage()
    ]
    assert critical_records
    assert critical_records[-1].exc_info is not None
    assert critical_records[-1].exc_info[0] is RuntimeError


@pytest.mark.parametrize(
    ("exception", "expected_category"),
    [
        (
            EmptyTextractResponseError("no document", source_doc_id="d", case_ref="c", s3_uri="s"),
            DlqCategory.EMPTY_TEXTRACT_RESPONSE,
        ),
        (
            ZeroChunksError("no chunks", source_doc_id="d", case_ref="c", s3_uri="s"),
            DlqCategory.ZERO_CHUNKS_EXTRACTED_FROM_DOCUMENT,
        ),
    ],
)
def test_process_document_job_pipeline_error_is_not_success(caplog, exception, expected_category):
    """A classified PipelineError is contained, recorded with its category, and not a success."""
    pipeline = mock.Mock()
    pipeline.process_document.side_effect = exception
    job = _make_job()

    with caplog.at_level(logging.ERROR, logger="ingestion_pipeline.runner"):
        result = process_document_job(job, pipeline)

    assert result.success is False
    assert result.error is exception
    assert result.category is expected_category
    assert result.retryable is False
    pipeline.process_document.assert_called_once()
    assert any("not acknowledging" in record.getMessage() for record in caplog.records)


def test_process_document_job_resets_log_context():
    """The source_doc_id context is reset after processing (no leak across threads)."""
    from ingestion_pipeline.custom_logging.log_context import source_doc_id_context

    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    process_document_job(_make_job(), pipeline)

    assert source_doc_id_context.get() is None


# --- run_batch ------------------------------------------------------------


def test_run_batch_empty_returns_no_results():
    pipeline = mock.Mock()
    source = mock.Mock()

    results = run_batch([], pipeline, source)

    assert results == []
    pipeline.process_document.assert_not_called()
    source.acknowledge.assert_not_called()


def test_run_batch_processes_all_and_acknowledges_only_successes():
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = mock.Mock()

    good = _make_job()
    bad = _make_job(s3_uri="s3://test-kta-documents-bucket/bad/file.pdf", case_ref="bad")

    results = run_batch([good, bad], pipeline, source)

    assert len(results) == 2
    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    assert len(successes) == 1
    assert len(failures) == 1

    # Only the successful job is acknowledged.
    source.acknowledge.assert_called_once()
    assert source.acknowledge.call_args.args[0] is good


def test_run_batch_caps_workers_at_max_concurrent_documents(patch_settings):
    """The pool is sized at min(MAX_CONCURRENT_DOCUMENTS, len(jobs)).

    With more jobs than the configured limit, the pool must be capped at the
    limit (not at the job count). Guards against a wrong worker-count regression
    that the small-batch tests would not catch.
    """
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 3
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = mock.Mock()

    jobs = [_make_job(s3_uri=f"s3://test-kta-documents-bucket/26-711111/doc{i}.pdf") for i in range(10)]

    captured_max_workers: list[int] = []
    real_executor = ThreadPoolExecutor

    def _recording_executor(max_workers, *args, **kwargs):
        captured_max_workers.append(max_workers)
        return real_executor(max_workers=max_workers, *args, **kwargs)

    with mock.patch("ingestion_pipeline.runner.ThreadPoolExecutor", side_effect=_recording_executor):
        results = run_batch(jobs, pipeline, source)

    assert len(results) == 10
    # min(3, 10) == 3: capped at the limit, not the job count.
    assert captured_max_workers == [3]


def test_run_batch_caps_workers_at_job_count_when_fewer_jobs(patch_settings):
    """When jobs are fewer than the limit, the pool is sized to the job count."""
    patch_settings.MAX_CONCURRENT_DOCUMENTS = 8
    pipeline = mock.Mock()
    pipeline.process_document.return_value = None
    source = mock.Mock()

    jobs = [_make_job(s3_uri=f"s3://test-kta-documents-bucket/26-711111/doc{i}.pdf") for i in range(2)]

    captured_max_workers: list[int] = []
    real_executor = ThreadPoolExecutor

    def _recording_executor(max_workers, *args, **kwargs):
        captured_max_workers.append(max_workers)
        return real_executor(max_workers=max_workers, *args, **kwargs)

    with mock.patch("ingestion_pipeline.runner.ThreadPoolExecutor", side_effect=_recording_executor):
        run_batch(jobs, pipeline, source)

    # min(8, 2) == 2: capped at the job count.
    assert captured_max_workers == [2]


def test_run_batch_executes_documents_concurrently(patch_settings):
    """Workers run in parallel: MAX_CONCURRENT_DOCUMENTS documents overlap in time.

    Each ``process_document`` call blocks on a barrier sized to the limit. If the
    runner processed documents serially the barrier would never be satisfied and
    the calls would time out, so this asserts genuine concurrency rather than a
    serial loop that happens to return the right results.
    """
    limit = 4
    patch_settings.MAX_CONCURRENT_DOCUMENTS = limit

    # A barrier that only releases once `limit` threads have arrived. A serial
    # implementation would deadlock here and trip the timeout below.
    barrier = threading.Barrier(limit, timeout=5)
    max_observed_concurrency = 0
    concurrency_lock = threading.Lock()
    current_concurrency = 0

    def _blocking_process(*_args, **_kwargs):
        nonlocal max_observed_concurrency, current_concurrency
        with concurrency_lock:
            current_concurrency += 1
            max_observed_concurrency = max(max_observed_concurrency, current_concurrency)
        # Wait until `limit` workers are running at once; raises BrokenBarrierError
        # (failing the test) if they never all arrive within the timeout.
        barrier.wait()
        with concurrency_lock:
            current_concurrency -= 1

    pipeline = mock.Mock()
    pipeline.process_document.side_effect = _blocking_process
    source = mock.Mock()

    jobs = [_make_job(s3_uri=f"s3://test-kta-documents-bucket/26-711111/doc{i}.pdf") for i in range(limit)]

    results = run_batch(jobs, pipeline, source)

    assert len(results) == limit
    assert all(r.success for r in results)
    assert max_observed_concurrency == limit


@pytest.mark.parametrize(
    "exception",
    [
        EmptyTextractResponseError("no document", source_doc_id="d", case_ref="c", s3_uri="s"),
        ZeroChunksError("no chunks", source_doc_id="d", case_ref="c", s3_uri="s"),
    ],
)
def test_run_batch_does_not_acknowledge_pipeline_failure(exception):
    """A terminal PipelineError leaves the job unacknowledged so SQS can redrive it."""
    pipeline = mock.Mock()
    pipeline.process_document.side_effect = exception
    source = mock.Mock()

    job = _make_job()

    results = run_batch([job], pipeline, source)

    assert len(results) == 1
    assert results[0].success is False
    assert isinstance(results[0].error, PipelineError)
    source.acknowledge.assert_not_called()


# --- main -----------------------------------------------------------------


@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_successful_execution(mock_check_opensearch_health, mock_build_pipeline, mock_source_cls):
    """Main builds the pipeline once, fetches a batch, and processes it."""
    mock_pipeline = mock.Mock()
    mock_pipeline.process_document.return_value = None
    mock_build_pipeline.return_value = mock_pipeline
    mock_check_opensearch_health.return_value = True

    mock_source = mock.Mock()
    mock_source.fetch_batch.return_value = [_make_job()]
    mock_source_cls.return_value = mock_source

    main()

    mock_build_pipeline.assert_called_once()
    mock_source.fetch_batch.assert_called_once()
    mock_pipeline.process_document.assert_called_once()
    mock_source.acknowledge.assert_called_once()


@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.logger")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_opensearch_health_check_failure_returns(
    mock_check_opensearch_health, mock_logger, mock_build_pipeline, mock_source_cls
):
    """Main exits early and builds nothing when the health check fails."""
    mock_check_opensearch_health.return_value = False

    main()

    mock_build_pipeline.assert_not_called()
    mock_source_cls.assert_not_called()
    mock_logger.critical.assert_called_with("OpenSearch health check failed. Exiting pipeline runner.")


@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_creates_correct_document_metadata(mock_check_opensearch_health, mock_build_pipeline, mock_source_cls):
    """Main feeds correctly-populated DocumentMetadata into the pipeline."""
    mock_pipeline = mock.Mock()
    mock_pipeline.process_document.return_value = None
    mock_build_pipeline.return_value = mock_pipeline
    mock_check_opensearch_health.return_value = True

    mock_source = mock.Mock()
    mock_source.fetch_batch.return_value = [_make_job()]
    mock_source_cls.return_value = mock_source

    with mock.patch("ingestion_pipeline.runner.datetime") as mock_datetime:
        mock_now = datetime.datetime(2024, 1, 15, 12, 0, 0)
        mock_datetime.datetime.now.return_value = mock_now
        mock_datetime.timezone = datetime.timezone

        main()

    metadata = mock_pipeline.process_document.call_args.kwargs["document_metadata"]
    assert isinstance(metadata, DocumentMetadata)
    assert metadata.source_file_name == "Case1_TC19_50_pages_brain_injury.pdf"
    assert metadata.case_ref == "26-711111"
    assert metadata.correspondence_type == "TC19 - ADDITIONAL INFO REQUEST"
    assert metadata.page_count is None
