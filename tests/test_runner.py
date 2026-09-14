import datetime
from unittest import mock

import pytest

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.orchestration.document_source import DocumentJob
from ingestion_pipeline.runner import main

"""Tests for the pipeline runner module."""


def _configure_mock_settings(mock_settings):
    mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET = "test-kta-documents-bucket"
    mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX = "26-711111"
    mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME = "Case1_TC19_50_pages_brain_injury.pdf"
    mock_settings.MAX_CONCURRENT_DOCUMENTS = 4
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

    with mock.patch("ingestion_pipeline.document_identity.identity.datetime") as mock_datetime:
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
