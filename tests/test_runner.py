import datetime
from unittest import mock

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.runner import main

"""Tests for the pipeline runner module."""


@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.logger")
def test_main_successful_execution(mock_logger, mock_build_pipeline):
    """Test that main executes successfully with valid input."""
    mock_pipeline = mock.Mock()
    mock_build_pipeline.return_value = mock_pipeline

    main()

    mock_build_pipeline.assert_called_once()
    mock_pipeline.process_document.assert_called_once()
    assert mock_logger.info.call_count >= 2
    mock_logger.info.assert_any_call("Pipeline runner started.")
    mock_logger.info.assert_any_call("Pipeline runner finished successfully.")


@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.logger")
def test_main_handles_pipeline_exception(mock_logger, mock_build_pipeline):
    """Test that main logs critical error when pipeline raises exception."""
    mock_pipeline = mock.Mock()
    mock_pipeline.process_document.side_effect = Exception("Pipeline error")
    mock_build_pipeline.return_value = mock_pipeline

    main()

    mock_pipeline.process_document.assert_called_once()
    mock_logger.critical.assert_called_once_with("Pipeline runner encountered a fatal error.", exc_info=True)


@mock.patch("ingestion_pipeline.runner.build_pipeline")
@mock.patch("ingestion_pipeline.runner.DocumentIdentifier")
def test_main_creates_correct_document_metadata(mock_identifier_class, mock_build_pipeline):
    """Test that main creates DocumentMetadata with correct values."""
    mock_pipeline = mock.Mock()
    mock_build_pipeline.return_value = mock_pipeline

    mock_identifier = mock.Mock()
    mock_identifier.generate_uuid.return_value = "test-uuid-123"
    mock_identifier_class.return_value = mock_identifier

    with mock.patch("ingestion_pipeline.runner.datetime") as mock_datetime:
        mock_now = datetime.datetime(2024, 1, 15, 12, 0, 0)
        mock_datetime.datetime.now.return_value = mock_now

        main()

        mock_identifier_class.assert_called_once_with(
            source_file_name="Case1_TC19_50_pages_brain_injury.pdf",
            correspondence_type="TC19",
            case_ref="25-111111",
        )

        call_args = mock_pipeline.process_document.call_args
        metadata = call_args.kwargs["document_metadata"]

        assert isinstance(metadata, DocumentMetadata)
        assert metadata.source_doc_id == "test-uuid-123"
        assert metadata.source_file_name == "Case1_TC19_50_pages_brain_injury.pdf"
        assert metadata.case_ref == "25-111111"
        assert metadata.correspondence_type == "TC19"
        assert metadata.page_count is None
