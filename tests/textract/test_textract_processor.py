"""Unit tests for the TextractProcessor class."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from textractcaller.t_call import Textract_API
from textractor.entities.document import Document

from ingestion_pipeline.orchestration.pipeline import Pipeline
from ingestion_pipeline.textract.textract_processor import TextractProcessor


@pytest.fixture
def mock_textractor():
    """Provides a mock Textractor object."""
    mock = MagicMock()
    mock.start_document_analysis.return_value = MagicMock(job_id="test-job-12345")
    return mock


@pytest.fixture
def mock_textract_client():
    """Provides a mock boto3 textract client."""
    return MagicMock()


@pytest.fixture
def mock_orchestrator():
    """Provides a mock ProcessingPipeline object."""
    return MagicMock(spec=Pipeline)


def test_init(mock_textractor, mock_textract_client):
    """Verifies the processor is initialized correctly with its dependencies."""
    processor = TextractProcessor(
        textractor=mock_textractor,
        textract_client=mock_textract_client,
        timeout_seconds=900,
    )

    assert processor.textractor is mock_textractor
    assert processor.textract_client is mock_textract_client
    assert processor.timeout_seconds == 900


def test_start_textract_job(mock_textractor, mock_textract_client):
    """Tests the internal job starting method."""
    s3_uri = "s3://my-bucket/doc.pdf"
    processor = TextractProcessor(mock_textractor, mock_textract_client)

    job_id = processor._start_textract_job(s3_uri)

    mock_textractor.start_document_analysis.assert_called_once()
    assert job_id == "test-job-12345"


@patch("ingestion_pipeline.textract.textract_processor.time.sleep", return_value=None)
@patch("ingestion_pipeline.textract.textract_processor.time.time")
def test_poll_for_job_completion_succeeds(mock_time, mock_sleep, mock_textractor, mock_textract_client, caplog):
    """Verifies the polling logic for a successful job."""
    # Tell the logger to ignore INFO messages for this test
    caplog.set_level(logging.WARNING)

    mock_textract_client.get_document_analysis.side_effect = [
        {"JobStatus": "IN_PROGRESS"},
        {"JobStatus": "SUCCEEDED"},
    ]

    mock_time.side_effect = [1000, 1001, 1002]

    processor = TextractProcessor(mock_textractor, mock_textract_client, timeout_seconds=30, poll_interval=1)
    status = processor._poll_for_job_completion("job-1")

    assert status == "SUCCEEDED"
    assert mock_textract_client.get_document_analysis.call_count == 2


@patch.object(TextractProcessor, "_start_textract_job")
@patch.object(TextractProcessor, "_poll_for_job_completion")
@patch.object(TextractProcessor, "_get_job_results")
@patch("ingestion_pipeline.uuid_generators.document_uuid.DocumentIdentifier")
def test_process_document_happy_path(
    mock_create_hash,
    mock_get_results,
    mock_poll,
    mock_start_job,
    mock_textractor,
    mock_textract_client,
):
    """Tests the end-to-end success scenario of the main `process_document` method."""
    s3_uri = "s3://cica-textract-response-dev/Case1.pdf"
    mock_start_job.return_value = "job-abc"
    mock_poll.return_value = "SUCCEEDED"

    mock_document = MagicMock(spec=Document, num_pages=10)
    mock_get_results.return_value = mock_document
    mock_create_hash.return_value = "mock-doc-id"

    processor = TextractProcessor(mock_textractor, mock_textract_client)
    processor.process_document(s3_uri)

    mock_start_job.assert_called_once_with(s3_uri)
    mock_poll.assert_called_once_with("job-abc")
    mock_get_results.assert_called_once_with("job-abc")


@patch.object(TextractProcessor, "_start_textract_job")
@patch.object(TextractProcessor, "_poll_for_job_completion")
@patch.object(TextractProcessor, "_get_job_results")
def test_process_document_stops_if_job_fails(
    mock_get_results,
    mock_poll,
    mock_start_job,
    mock_orchestrator,
    mock_textractor,
    mock_textract_client,
):
    """Verifies that processing is halted if the Textract job does not succeed."""
    s3_uri = "s3://my-bucket/failed.pdf"
    mock_start_job.return_value = "job-fail"
    mock_poll.return_value = "FAILED"

    textract_processor = TextractProcessor(mock_orchestrator, mock_textractor, mock_textract_client)

    with pytest.raises(Exception, match="Textract job job-fail failed with status: FAILED"):
        textract_processor.process_document(s3_uri)

    mock_start_job.assert_called_once_with(s3_uri)
    mock_poll.assert_called_once_with("job-fail")
    mock_get_results.assert_not_called()
    mock_orchestrator.process_document.assert_not_called()


@patch("ingestion_pipeline.textract.textract_processor.time.sleep", return_value=None)
@patch("ingestion_pipeline.textract.textract_processor.time.time")
def test_poll_for_job_completion_times_out(mock_time, mock_sleep, mock_textractor, mock_textract_client):
    """Verifies that a TimeoutError is raised if the job exceeds the timeout."""
    timeout = 30
    # Ensure the job status never changes from IN_PROGRESS
    mock_textract_client.get_document_analysis.return_value = {"JobStatus": "IN_PROGRESS"}

    # Simulate time passing to trigger the timeout
    mock_time.side_effect = [1000, 1010, 1020, 1031]

    processor = TextractProcessor(
        textractor=mock_textractor,
        textract_client=mock_textract_client,
        timeout_seconds=timeout,
    )

    with pytest.raises(TimeoutError) as exc_info:
        processor._poll_for_job_completion("job-1")

    assert f"Textract job job-1 timed out after {timeout} seconds." in str(exc_info.value)


@patch.object(TextractProcessor, "_start_textract_job")
def test_process_document_handles_general_exception(
    mock_start_job, mock_orchestrator, mock_textractor, mock_textract_client, caplog
):
    """Verifies the main exception handler logs an error if a step fails."""
    s3_uri = "s3://my-bucket/doc-that-will-fail.pdf"
    error_message = "Unexpected AWS error"
    mock_start_job.side_effect = Exception(error_message)

    textract_processor = TextractProcessor(mock_orchestrator, mock_textractor, mock_textract_client)

    with pytest.raises(Exception, match="Unexpected AWS error"):
        textract_processor.process_document(s3_uri)

    assert f"Failed to process s3 file {s3_uri}: Unexpected AWS error" in caplog.text


@patch("ingestion_pipeline.textract.textract_processor.parse")
@patch("ingestion_pipeline.textract.textract_processor.get_full_json")
def test_get_job_results_calls_dependencies_correctly(
    mock_get_full_json, mock_parse, mock_textractor, mock_textract_client
):
    """Verifies _get_job_results fetches raw JSON and parses it into a Document."""
    job_id = "test-job-id-456"

    # Create mock return values
    mock_raw_json_response = {"DocumentMetadata": {"Pages": 1}, "Blocks": []}
    mock_parsed_document = MagicMock(spec=Document)
    mock_get_full_json.return_value = mock_raw_json_response
    mock_parse.return_value = mock_parsed_document

    processor = TextractProcessor(
        textractor=mock_textractor,
        textract_client=mock_textract_client,
    )
    result_document = processor._get_job_results(job_id)

    mock_get_full_json.assert_called_once_with(
        job_id=job_id,
        boto3_textract_client=processor.textract_client,
        textract_api=Textract_API.ANALYZE,
    )
    mock_parse.assert_called_once_with(mock_raw_json_response)
    assert result_document is mock_parsed_document
