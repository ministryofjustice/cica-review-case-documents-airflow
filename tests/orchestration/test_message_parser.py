import datetime
import json

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
    # received_date is stamped with the receipt-time fallback (naive UTC) when omitted.
    assert job.received_date is not None
    assert job.received_date.tzinfo is None
    assert job.receipt_handle is None


def test_parse_message_stamps_receipt_time_when_received_date_omitted():
    before = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    job = parse_message(_valid_body_full_uri())
    after = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    # The fallback is stamped at parse time, so it falls within the call window and is
    # naive UTC to match the DocumentMetadata schema.
    assert job.received_date is not None
    assert job.received_date.tzinfo is None
    assert before <= job.received_date <= after


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


@pytest.mark.parametrize("value", ["", "   ", "\t", "\n  "])
def test_parse_message_blank_correspondence_type_raises_malformed(value):
    # Empty and whitespace-only correspondence types must be rejected, not used to
    # derive a document UUID or indexed as a real correspondence type.
    body = json.dumps({"correspondence_type": value, "case_ref": "26-711111", "source_file_s3_uri": VALID_URI})
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "correspondence_type"


def test_parse_message_strips_correspondence_type_whitespace():
    # Surrounding whitespace is stripped so the derived UUID is stable regardless of padding.
    body = (
        '{"correspondence_type": "  TC19 - ADDITIONAL INFO REQUEST  ", "case_ref": "26-711111", '
        f'"source_file_s3_uri": "{VALID_URI}"}}'
    )
    job = parse_message(body)
    assert job.correspondence_type == "TC19 - ADDITIONAL INFO REQUEST"


def test_parse_message_missing_source_location_raises_malformed():
    body = '{"correspondence_type": "TC19", "case_ref": "26-711111"}'
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    # Model-level validation failure attributed to a concrete area, not field=None.
    assert exc_info.value.field == "source_location"


def test_parse_message_incomplete_source_components_raises_malformed():
    # bucket + case_prefix present but filename missing: still a model-level failure.
    body = (
        '{"correspondence_type": "TC19", "case_ref": "26-711111", "bucket": "cica-bucket", "case_prefix": "26-711111"}'
    )
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "source_location"


def test_parse_message_uri_failing_case_path_raises_malformed():
    # Valid case_ref field, but the URI path segment is not a valid case folder.
    body = (
        '{"correspondence_type": "TC19", "case_ref": "26-711111", '
        '"source_file_s3_uri": "s3://cica-bucket/not-a-case/case1.pdf"}'
    )
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "source_file_s3_uri"


@pytest.mark.parametrize(
    "uri",
    [
        "s3://cica-bucket/26-711111/",  # folder only, no object key (trailing slash)
        "s3://cica-bucket/26-711111",  # folder only, no trailing slash / key
        "s3://cica-bucket/26-711111//case1.pdf",  # empty first key segment
    ],
)
def test_parse_message_uri_without_object_key_raises_malformed(uri):
    # A case folder with no real object key must be rejected; otherwise the case folder
    # would be mistaken for the file name and the later S3 lookup would fail instead.
    body = f'{{"correspondence_type": "TC19", "case_ref": "26-711111", "source_file_s3_uri": "{uri}"}}'
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "source_file_s3_uri"


def test_parse_message_case_ref_not_matching_uri_case_folder_raises_malformed():
    # case_ref and the URI's case folder are each individually valid but disagree.
    # This must be rejected: otherwise the document would be downloaded from one case
    # but identified/indexed under another.
    body = (
        '{"correspondence_type": "TC19", "case_ref": "26-700001", '
        '"source_file_s3_uri": "s3://cica-bucket/26-800040/case1.pdf"}'
    )
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "case_ref"
    assert "26-700001" in str(exc_info.value)
    assert "26-800040" in str(exc_info.value)


def test_parse_message_case_ref_not_matching_component_case_prefix_raises_malformed():
    # Same mismatch via the component-built URI: case_ref disagrees with case_prefix.
    body = (
        '{"correspondence_type": "TC19", "case_ref": "26-700001", '
        '"bucket": "cica-bucket", "case_prefix": "26-800040", "filename": "case1.pdf"}'
    )
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "case_ref"


def test_parse_message_case_ref_matching_uri_case_folder_is_accepted():
    # Sanity check the happy path still passes with matching case references.
    body = (
        '{"correspondence_type": "TC19", "case_ref": "26-700001", '
        '"source_file_s3_uri": "s3://cica-bucket/26-700001/case1.pdf"}'
    )
    job = parse_message(body)
    assert job.case_ref == "26-700001"


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
