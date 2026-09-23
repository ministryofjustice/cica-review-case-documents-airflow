import json
from unittest import mock

import boto3
import pytest
from botocore.exceptions import ClientError, ConnectionClosedError, EndpointConnectionError, ReadTimeoutError
from moto import mock_aws

from ingestion_pipeline.orchestration.document_source import (
    _MAX_LOGGED_BODY_CHARS,
    DocumentJob,
    FetchResult,
    QueueResolutionError,
    SqsDocumentSource,
    _truncate_body_for_log,
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


def _malformed_body() -> str:
    """A body the parser rejects: valid JSON but missing the required received_date."""
    return json.dumps(
        {
            "correspondence_type": "TC19 - ADDITIONAL INFO REQUEST",
            "case_ref": "26-711111",
            "source_file_s3_uri": VALID_URI,
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


def test_document_job_source_doc_id_is_derived_from_natural_key():
    """source_doc_id equals the DocumentIdentifier UUID for the job's natural key."""
    from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

    job = DocumentJob(
        source_file_s3_uri="s3://bucket/26-711111/some_file.pdf",
        correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
        case_ref="26-711111",
    )
    expected = DocumentIdentifier(
        source_file_name="some_file.pdf",
        correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
        case_ref="26-711111",
    ).generate_uuid()
    assert job.source_doc_id == expected


def test_document_job_source_doc_id_matches_for_equal_natural_keys():
    """Two jobs with the same natural key resolve to the same source_doc_id."""
    job_a = DocumentJob(
        source_file_s3_uri="s3://bucket-a/26-711111/file.pdf",
        correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
        case_ref="26-711111",
    )
    # Different bucket, same file name / correspondence_type / case_ref -> same id.
    job_b = DocumentJob(
        source_file_s3_uri="s3://bucket-b/26-711111/file.pdf",
        correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
        case_ref="26-711111",
    )
    assert job_a.source_doc_id == job_b.source_doc_id


def test_document_job_source_doc_id_stable_when_receipt_handle_attached():
    """Attaching a receipt handle via model_copy does not change the computed id."""
    job = DocumentJob(
        source_file_s3_uri="s3://bucket/26-711111/file.pdf",
        correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
        case_ref="26-711111",
    )
    copied = job.model_copy(update={"receipt_handle": "rh-123"})
    assert copied.receipt_handle == "rh-123"
    assert copied.source_doc_id == job.source_doc_id


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

    result = source.fetch_batch()

    assert len(result.jobs) == 1
    assert result.malformed_discarded == 0
    job = result.jobs[0]
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


def test_fetch_batch_empty_receive_returns_empty_result():
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    sqs_client.receive_message.return_value = {}
    result = source.fetch_batch()
    assert result.jobs == []
    assert result.malformed_discarded == 0


def test_fetch_batch_deletes_malformed_and_continues():
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    sqs_client.receive_message.return_value = {
        "Messages": [
            {"MessageId": "bad", "ReceiptHandle": "rh-bad", "Body": "{not json"},
            {"MessageId": "good", "ReceiptHandle": "rh-good", "Body": _valid_body()},
        ]
    }

    result = source.fetch_batch()

    # The malformed message is dropped; the valid one is returned.
    assert len(result.jobs) == 1
    assert result.jobs[0].receipt_handle == "rh-good"
    assert result.malformed_discarded == 1
    # The malformed message is deleted so it does not reappear after visibility timeout.
    sqs_client.delete_message.assert_called_once_with(QueueUrl=QUEUE_URL, ReceiptHandle="rh-bad")


def test_fetch_batch_mixed_valid_and_malformed_accounts_discards():
    """A mixed poll returns the valid jobs and counts every malformed message."""
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    sqs_client.receive_message.return_value = {
        "Messages": [
            {"MessageId": "good-1", "ReceiptHandle": "rh-good-1", "Body": _valid_body()},
            {"MessageId": "bad-json", "ReceiptHandle": "rh-bad-1", "Body": "{not json"},
            {"MessageId": "good-2", "ReceiptHandle": "rh-good-2", "Body": _valid_body()},
            {"MessageId": "bad-field", "ReceiptHandle": "rh-bad-2", "Body": _malformed_body()},
        ]
    }

    result = source.fetch_batch()

    # Two valid jobs returned; two malformed messages discarded.
    assert len(result.jobs) == 2
    assert result.malformed_discarded == 2
    assert {job.receipt_handle for job in result.jobs} == {"rh-good-1", "rh-good-2"}
    # Both malformed messages are still deleted so they do not reappear.
    assert sqs_client.delete_message.call_count == 2
    deleted_handles = {call.kwargs["ReceiptHandle"] for call in sqs_client.delete_message.call_args_list}
    assert deleted_handles == {"rh-bad-1", "rh-bad-2"}


def test_fetch_batch_all_malformed_returns_no_jobs_with_discard_count():
    """A poll of only malformed messages returns no jobs and counts them all."""
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    sqs_client.receive_message.return_value = {
        "Messages": [
            {"MessageId": "bad-1", "ReceiptHandle": "rh-bad-1", "Body": "{not json"},
            {"MessageId": "bad-2", "ReceiptHandle": "rh-bad-2", "Body": _malformed_body()},
            {"MessageId": "bad-3", "ReceiptHandle": "rh-bad-3", "Body": "not even json"},
        ]
    }

    result = source.fetch_batch()

    assert result.jobs == []
    assert result.malformed_discarded >= 1
    assert result.malformed_discarded == 3
    # Every malformed message is deleted.
    assert sqs_client.delete_message.call_count == 3


def test_fetch_batch_logs_raw_body_when_discarding(caplog):
    """The discard log includes the raw message body so upstream errors are diagnosable."""
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    bad_body = '{"correspondence_type": "WRONG TYPE", "case_ref": "26-711111"}'
    sqs_client.receive_message.return_value = {
        "Messages": [
            {"MessageId": "bad", "ReceiptHandle": "rh-bad", "Body": bad_body},
        ]
    }

    with caplog.at_level("ERROR"):
        result = source.fetch_batch()

    assert result.malformed_discarded == 1
    # The full raw body appears in the discard log record.
    assert bad_body in caplog.text
    assert "raw body:" in caplog.text


def test_fetch_batch_truncates_oversized_body_in_log(caplog):
    """An oversized body is clipped in the log so a single message cannot flood it."""
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    # Valid JSON but not an object, so it is rejected without the body being echoed by
    # the parser; the huge padding forces truncation in the discard log.
    oversized_body = '"' + ("x" * (_MAX_LOGGED_BODY_CHARS + 500)) + '"'
    sqs_client.receive_message.return_value = {
        "Messages": [
            {"MessageId": "bad", "ReceiptHandle": "rh-bad", "Body": oversized_body},
        ]
    }

    with caplog.at_level("ERROR"):
        result = source.fetch_batch()

    assert result.malformed_discarded == 1
    assert "truncated" in caplog.text
    # The untruncated body is longer than what we ever log.
    assert oversized_body not in caplog.text


# --- _truncate_body_for_log -------------------------------------------------


def test_truncate_body_for_log_returns_short_body_unchanged():
    body = "short body"
    assert _truncate_body_for_log(body) == body


def test_truncate_body_for_log_clips_and_marks_omitted_chars():
    body = "y" * (_MAX_LOGGED_BODY_CHARS + 42)
    result = _truncate_body_for_log(body)
    assert result.startswith("y" * _MAX_LOGGED_BODY_CHARS)
    assert "truncated 42 more chars" in result


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
def test_fetch_batch_transient_receive_error_returns_empty_result(error):
    """Transient receive failures are swallowed as an empty poll for retry."""
    sqs_client = mock.Mock()
    source = _make_source(sqs_client)
    sqs_client.receive_message.side_effect = error
    result = source.fetch_batch()
    assert result == FetchResult(jobs=[], malformed_discarded=0)
    assert result.jobs == []
    assert result.malformed_discarded == 0


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
    result = source.fetch_batch()
    assert len(result.jobs) == 1
    assert result.malformed_discarded == 0
    assert result.jobs[0].source_file_s3_uri == VALID_URI

    # Acknowledge removes it from the queue.
    source.acknowledge(result.jobs[0])
    remaining = sqs.receive_message(QueueUrl=queue_url, WaitTimeSeconds=0)
    assert "Messages" not in remaining or remaining["Messages"] == []
