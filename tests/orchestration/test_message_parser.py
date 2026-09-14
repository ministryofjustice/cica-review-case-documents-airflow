import datetime

import pytest

from ingestion_pipeline.orchestration.message_parser import (
    DocumentRequest,
    MalformedMessageError,
    parse_message,
)

VALID_URI = "s3://cica-bucket/26-711111/case1.pdf"


def _valid_body_full_uri() -> str:
    return (
        '{"correspondence_type": "TC19 - ADDITIONAL INFO REQUEST", '
        '"case_ref": "26-711111", '
        f'"source_file_s3_uri": "{VALID_URI}"}}'
    )


# --- happy path -------------------------------------------------------------


def test_parse_message_full_uri_builds_job():
    job = parse_message(_valid_body_full_uri())
    assert job.source_file_s3_uri == VALID_URI
    assert job.case_ref == "26-711111"
    assert job.correspondence_type == "TC19 - ADDITIONAL INFO REQUEST"
    assert job.source_file_name == "case1.pdf"
    assert job.received_date is None
    assert job.receipt_handle is None


def test_parse_message_builds_uri_from_components():
    body = (
        '{"correspondence_type": "TC19", "case_ref": "26-800040", '
        '"bucket": "cica-bucket", "case_prefix": "26-800040", "filename": "case40.pdf"}'
    )
    job = parse_message(body)
    assert job.source_file_s3_uri == "s3://cica-bucket/26-800040/case40.pdf"
    assert job.case_ref == "26-800040"


def test_parse_message_uses_supplied_received_date():
    body = (
        '{"correspondence_type": "TC19", "case_ref": "26-711111", '
        f'"source_file_s3_uri": "{VALID_URI}", "received_date": "2026-01-15T09:30:00"}}'
    )
    job = parse_message(body)
    assert job.received_date == datetime.datetime(2026, 1, 15, 9, 30, 0)


def test_parse_message_ignores_derived_fields():
    body = (
        '{"correspondence_type": "TC19", "case_ref": "26-711111", '
        f'"source_file_s3_uri": "{VALID_URI}", '
        '"source_doc_id": "should-be-ignored", "page_count": 999}'
    )
    job = parse_message(body)
    # Derived fields are not carried on the job; source_doc_id is derived later.
    assert not hasattr(job, "source_doc_id")
    assert not hasattr(job, "page_count")


# --- malformed --------------------------------------------------------------


def test_parse_message_invalid_json_raises_malformed():
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message("{not valid json", message_id="m-1")
    # Whole-body failure: no single field.
    assert exc_info.value.field is None
    assert "m-1" in str(exc_info.value)


def test_parse_message_non_object_json_raises_malformed():
    with pytest.raises(MalformedMessageError):
        parse_message("[1, 2, 3]")


def test_parse_message_missing_case_ref_raises_malformed_with_field():
    body = f'{{"correspondence_type": "TC19", "source_file_s3_uri": "{VALID_URI}"}}'
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "case_ref"


def test_parse_message_bad_case_ref_pattern_raises_malformed():
    body = f'{{"correspondence_type": "TC19", "case_ref": "26-611111", "source_file_s3_uri": "{VALID_URI}"}}'
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "case_ref"


def test_parse_message_empty_correspondence_type_raises_malformed():
    body = f'{{"correspondence_type": "", "case_ref": "26-711111", "source_file_s3_uri": "{VALID_URI}"}}'
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "correspondence_type"


def test_parse_message_missing_source_location_raises_malformed():
    body = '{"correspondence_type": "TC19", "case_ref": "26-711111"}'
    with pytest.raises(MalformedMessageError):
        parse_message(body)


def test_parse_message_uri_failing_case_path_raises_malformed():
    # Valid case_ref field, but the URI path segment is not a valid case folder.
    body = (
        '{"correspondence_type": "TC19", "case_ref": "26-711111", '
        '"source_file_s3_uri": "s3://cica-bucket/not-a-case/case1.pdf"}'
    )
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "source_file_s3_uri"


# --- DocumentRequest direct -------------------------------------------------


def test_document_request_resolved_uri_prefers_full_uri():
    request = DocumentRequest(
        correspondence_type="TC19",
        case_ref="26-711111",
        source_file_s3_uri=VALID_URI,
        bucket="other-bucket",
        case_prefix="26-800040",
        filename="other.pdf",
    )
    assert request.resolved_s3_uri() == VALID_URI
