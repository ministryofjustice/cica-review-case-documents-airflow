import datetime
from unittest import mock

import pytest

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.runner import main

"""Tests for the pipeline runner module."""


@pytest.fixture(autouse=True)
def patch_settings():
    with mock.patch("ingestion_pipeline.runner.settings") as mock_settings:
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET = "test-kta-documents-bucket"
        yield mock_settings


@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.logger")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_successful_execution(mock_check_opensearch_health, mock_logger, mock_build_pipeline):
    """Test that main executes successfully with valid input."""
    mock_pipeline = mock.Mock()
    mock_build_pipeline.return_value = mock_pipeline
    mock_check_opensearch_health.return_value = True

    main()

    mock_build_pipeline.assert_called_once()
    mock_pipeline.process_document.assert_called_once()
    assert mock_logger.info.call_count >= 2
    mock_logger.info.assert_any_call("Pipeline runner started.")
    mock_logger.info.assert_any_call("Pipeline runner finished successfully.")


@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.logger")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_handles_pipeline_exception(mock_check_opensearch_health, mock_logger, mock_build_pipeline):
    """Test that main logs critical error when pipeline raises exception."""
    mock_pipeline = mock.Mock()
    mock_pipeline.process_document.side_effect = Exception("Pipeline error")
    mock_build_pipeline.return_value = mock_pipeline
    mock_check_opensearch_health.return_value = True

    main()

    mock_pipeline.process_document.assert_called_once()
    mock_logger.critical.assert_called_once_with(
        "Pipeline runner encountered a fatal error for source_doc_id=4bcba3af-d9ab-53f2-9fd7-bf4263f8118e, "
        "case_ref=26-711111, s3_uri=s3://test-kta-documents-bucket/26-711111/Case1_TC19_50_pages_brain_injury.pdf: "
        "Exception: Pipeline error",
        exc_info=True,
    )


@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.DocumentIdentifier")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_main_creates_correct_document_metadata(
    mock_check_opensearch_health, mock_identifier_class, mock_build_pipeline
):
    """Test that main creates DocumentMetadata with correct values."""
    mock_pipeline = mock.Mock()
    mock_build_pipeline.return_value = mock_pipeline

    mock_identifier = mock.Mock()
    mock_identifier.generate_uuid.return_value = "test-uuid-123"
    mock_identifier_class.return_value = mock_identifier
    mock_check_opensearch_health.return_value = True

    with mock.patch("ingestion_pipeline.runner.datetime") as mock_datetime:
        mock_now = datetime.datetime(2024, 1, 15, 12, 0, 0)
        mock_datetime.datetime.now.return_value = mock_now

        main()

        mock_identifier_class.assert_called_once_with(
            source_file_name="Case1_TC19_50_pages_brain_injury.pdf",
            correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
            case_ref="26-711111",
        )

        call_args = mock_pipeline.process_document.call_args
        metadata = call_args.kwargs["document_metadata"]

        assert isinstance(metadata, DocumentMetadata)
        assert metadata.source_doc_id == "test-uuid-123"
        assert metadata.source_file_name == "Case1_TC19_50_pages_brain_injury.pdf"
        assert metadata.case_ref == "26-711111"
        assert metadata.correspondence_type == "TC19 - ADDITIONAL INFO REQUEST"
        assert metadata.page_count is None


@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.logger")
@mock.patch("ingestion_pipeline.runner.check_opensearch_health")
def test_opensearch_health_check_failure_returns(mock_check_opensearch_health, mock_logger, mock_build_pipeline):
    """Test that main executes successfully with valid input."""
    mock_pipeline = mock.Mock()
    mock_build_pipeline.return_value = mock_pipeline
    mock_check_opensearch_health.return_value = False

    main()

    mock_build_pipeline.assert_not_called()
    mock_pipeline.process_document.assert_not_called()
    assert mock_logger.critical.call_count >= 1
    mock_logger.critical.assert_called_with("OpenSearch health check failed. Exiting pipeline runner.")
