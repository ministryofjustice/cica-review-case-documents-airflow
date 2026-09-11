import datetime
import logging
from unittest import mock

import pytest

from ingestion_pipeline.chunking.schemas import DocumentMetadata
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
    """A valid job runs the pipeline and returns a successful result."""
    pipeline = mock.Mock()
    job = _make_job()

    result = process_document_job(job, pipeline)

    assert result.success is True
    assert result.error is None
    assert result.source_doc_id
    pipeline.process_document.assert_called_once()

    metadata = pipeline.process_document.call_args.kwargs["document_metadata"]
    assert isinstance(metadata, DocumentMetadata)
    assert metadata.source_file_name == "Case1_TC19_50_pages_brain_injury.pdf"
    assert metadata.case_ref == "26-711111"
    assert metadata.correspondence_type == "TC19 - ADDITIONAL INFO REQUEST"
    assert metadata.page_count is None


def test_process_document_job_invalid_uri_is_contained():
    """An invalid S3 URI is caught and reported as a failed result, not raised."""
    pipeline = mock.Mock()
    job = _make_job(s3_uri="s3://test-kta-documents-bucket/not-a-case-ref/file.pdf", case_ref="not-a-case-ref")

    result = process_document_job(job, pipeline)

    assert result.success is False
    assert isinstance(result.error, ValueError)
    pipeline.process_document.assert_not_called()


def test_process_document_job_contains_pipeline_exception(caplog):
    """A pipeline failure is contained and the traceback metadata is preserved."""
    pipeline = mock.Mock()
    pipeline.process_document.side_effect = RuntimeError("Pipeline error")
    job = _make_job()

    with caplog.at_level(logging.CRITICAL, logger="ingestion_pipeline.runner"):
        result = process_document_job(job, pipeline)

    assert result.success is False
    assert isinstance(result.error, RuntimeError)

    critical_records = [
        record
        for record in caplog.records
        if record.levelno == logging.CRITICAL and "Pipeline runner encountered a fatal error" in record.getMessage()
    ]
    assert critical_records
    assert critical_records[-1].exc_info is not None
    assert critical_records[-1].exc_info[0] is RuntimeError


def test_process_document_job_resets_log_context():
    """The source_doc_id context is reset after processing (no leak across threads)."""
    from ingestion_pipeline.custom_logging.log_context import source_doc_id_context

    pipeline = mock.Mock()
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


# --- main -----------------------------------------------------------------


@mock.patch("ingestion_pipeline.runner.SqsDocumentSource")
@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_successful_execution(mock_check_opensearch_health, mock_build_pipeline, mock_source_cls):
    """Main builds the pipeline once, fetches a batch, and processes it."""
    mock_pipeline = mock.Mock()
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
