import json
from unittest import mock

import boto3
import pytest
from botocore.exceptions import ClientError, ConnectionClosedError, EndpointConnectionError, ReadTimeoutError
from moto import mock_aws

from ingestion_pipeline.orchestration.document_source import (
    DocumentJob,
    QueueResolutionError,
    SqsDocumentSource,
)


def _client_error(code: str, operation: str = "ReceiveMessage") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


QUEUE_URL = "https://sqs.eu-west-2.amazonaws.com/123456789012/cica-document-search-queue"
# The URI bucket must match the configured source document root bucket
# (settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET, default local-kta-documents-bucket)
# for the message parser to accept it.
VALID_URI = "s3://local-kta-documents-bucket/26-711111/case1.pdf"


def _valid_body() -> str:
    return json.dumps(
        {
            "correspondence_type": "TC19 - ADDITIONAL INFO REQUEST",
            "case_ref": "26-711111",
            "source_file_s3_uri": VALID_URI,
            "received_date": "2026-01-15T09:30:00",
        }
    )


def _make_source(sqs_client) -> SqsDocumentSource:
    """Build a source with a resolvable queue URL and explicit tuning params."""
    sqs_client.get_queue_url.return_value = {"QueueUrl": QUEUE_URL}
    return SqsDocumentSource(
        sqs_client=sqs_client,
        queue_name="cica-document-search-queue",
        max_messages=10,
        wait_time_seconds=20,
        visibility_timeout_seconds=300,
    )


# --- DocumentJob ------------------------------------------------------------


def test_document_job_source_file_name_derived_from_uri():
    job = DocumentJob(
        source_file_s3_uri="s3://bucket/26-711111/some_file.pdf",
        correspondence_type="TC19",
        case_ref="26-711111",
    )
    assert job.source_file_name == "some_file.pdf"


def test_document_job_source_file_name_ignores_trailing_slash():
    job = DocumentJob(
        source_file_s3_uri="s3://bucket/26-711111/some_file.pdf/",
        correspondence_type="TC19",
        case_ref="26-711111",
    )
    assert job.source_file_name == "some_file.pdf"


# --- queue URL resolution ---------------------------------------------------


def test_resolve_queue_url_success():
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    assert source.queue_url == QUEUE_URL
    sqs_client.get_queue_url.assert_called_once_with(QueueName="cica-document-search-queue")


def test_resolve_queue_url_raises_when_get_queue_url_errors():
    sqs_client = mock.Mock()
    sqs_client.get_queue_url.side_effect = Exception("QueueDoesNotExist")
    with pytest.raises(QueueResolutionError):
        SqsDocumentSource(sqs_client=sqs_client, queue_name="missing-queue")


def test_resolve_queue_url_raises_when_no_url_returned():
    sqs_client = mock.Mock()
    sqs_client.get_queue_url.return_value = {}
    with pytest.raises(QueueResolutionError):
        SqsDocumentSource(sqs_client=sqs_client, queue_name="cica-document-search-queue")


# --- fetch_batch ------------------------------------------------------------


def test_fetch_batch_returns_jobs_for_valid_messages():
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    sqs_client.receive_message.return_value = {
        "Messages": [{"MessageId": "m-1", "ReceiptHandle": "rh-1", "Body": _valid_body()}]
    }

    jobs = source.fetch_batch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source_file_s3_uri == VALID_URI
    assert job.case_ref == "26-711111"
    assert job.receipt_handle == "rh-1"
    sqs_client.receive_message.assert_called_once_with(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20,
        VisibilityTimeout=300,
    )
    # Valid messages are not deleted at receive time (deleted on successful processing).
    sqs_client.delete_message.assert_not_called()


def test_fetch_batch_empty_receive_returns_empty_list():
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    sqs_client.receive_message.return_value = {}
    assert source.fetch_batch() == []


def test_fetch_batch_deletes_malformed_and_continues():
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    sqs_client.receive_message.return_value = {
        "Messages": [
            {"MessageId": "bad", "ReceiptHandle": "rh-bad", "Body": "{not json"},
            {"MessageId": "good", "ReceiptHandle": "rh-good", "Body": _valid_body()},
        ]
    }

    jobs = source.fetch_batch()

    # The malformed message is dropped; the valid one is returned.
    assert len(jobs) == 1
    assert jobs[0].receipt_handle == "rh-good"
    # The malformed message is deleted so it does not reappear after visibility timeout.
    sqs_client.delete_message.assert_called_once_with(QueueUrl=QUEUE_URL, ReceiptHandle="rh-bad")


@pytest.mark.parametrize(
    "error",
    [
        _client_error("RequestThrottled"),
        _client_error("ThrottlingException"),
        _client_error("ServiceUnavailable"),
        _client_error("InternalError"),
        _client_error("OverLimit"),  # short-poll temporary rate limit
        _client_error("KmsThrottled"),  # SQS KMS throttling (actual code)
        EndpointConnectionError(endpoint_url="http://localhost:4566"),
        # HTTPClientError subclasses (do NOT derive from ConnectionError) - common
        # transport failures raised after the SDK exhausts its own retries.
        ReadTimeoutError(endpoint_url="http://localhost:4566"),
        ConnectionClosedError(endpoint_url="http://localhost:4566"),
    ],
)
def test_fetch_batch_transient_receive_error_returns_empty_list(error):
    """Transient receive failures are swallowed as an empty poll for retry."""
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    sqs_client.receive_message.side_effect = error
    assert source.fetch_batch() == []


@pytest.mark.parametrize(
    "error",
    [
        _client_error("AccessDenied"),
        _client_error("QueueDoesNotExist"),
        _client_error("InvalidAddress"),
        _client_error("SomeUnknownCode"),
        Exception("unexpected non-client error"),
    ],
)
def test_fetch_batch_permanent_receive_error_propagates(error):
    """Permanent or unknown receive failures propagate so the run fails visibly."""
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    sqs_client.receive_message.side_effect = error
    with pytest.raises(type(error)):
        source.fetch_batch()


# --- acknowledge ------------------------------------------------------------


def test_acknowledge_deletes_message_by_receipt_handle():
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    job = DocumentJob(
        source_file_s3_uri=VALID_URI,
        correspondence_type="TC19",
        case_ref="26-711111",
        receipt_handle="rh-1",
    )
    source.acknowledge(job)
    sqs_client.delete_message.assert_called_once_with(QueueUrl=QUEUE_URL, ReceiptHandle="rh-1")


def test_acknowledge_without_receipt_handle_is_noop():
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    job = DocumentJob(
        source_file_s3_uri=VALID_URI,
        correspondence_type="TC19",
        case_ref="26-711111",
    )
    source.acknowledge(job)
    sqs_client.delete_message.assert_not_called()


def test_delete_error_is_logged_not_raised():
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    sqs_client.delete_message.side_effect = Exception("delete failed")
    job = DocumentJob(
        source_file_s3_uri=VALID_URI,
        correspondence_type="TC19",
        case_ref="26-711111",
        receipt_handle="rh-1",
    )
    # Should not raise despite the delete failing.
    source.acknowledge(job)


# --- end-to-end against moto ------------------------------------------------


@mock_aws
def test_fetch_batch_and_acknowledge_end_to_end_with_moto():
    sqs = boto3.client("sqs", region_name="eu-west-2")
    queue_url = sqs.create_queue(QueueName="cica-document-search-queue")["QueueUrl"]
    sqs.send_message(QueueUrl=queue_url, MessageBody=_valid_body())

    source = SqsDocumentSource(
        sqs_client=sqs,
        queue_name="cica-document-search-queue",
        wait_time_seconds=0,
    )
    jobs = source.fetch_batch()
    assert len(jobs) == 1
    assert jobs[0].source_file_s3_uri == VALID_URI

    # Acknowledge removes it from the queue.
    source.acknowledge(jobs[0])
    remaining = sqs.receive_message(QueueUrl=queue_url, WaitTimeSeconds=0)
    assert "Messages" not in remaining or remaining["Messages"] == []
