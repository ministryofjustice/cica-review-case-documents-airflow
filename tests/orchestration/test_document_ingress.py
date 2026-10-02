import datetime
import json

import pytest
from pydantic import ValidationError

from ingestion_pipeline.orchestration.document_ingress import (
    ACCEPTED_CORRESPONDENCE_TYPE,
    DocumentRequest,
    MalformedMessageError,
    _all_error_fields,
    _first_error_field,
    parse_message,
)
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

# The default configured source document root bucket (see config.py). The parser
# validates the URI bucket against settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET.
ROOT_BUCKET = "local-kta-documents-bucket"
CASE_REF = "26-700001"
VALID_URI = f"s3://{ROOT_BUCKET}/{CASE_REF}/Case1_TC19_50_pages_brain_injury.pdf"
RECEIVED_DATE = "2026-01-15T09:30:00"


def _valid_body(**overrides) -> str:
    payload = {
        "correspondence_type": ACCEPTED_CORRESPONDENCE_TYPE,
        "case_ref": CASE_REF,
        "source_file_s3_uri": VALID_URI,
        "received_date": RECEIVED_DATE,
    }
    payload.update(overrides)
    return json.dumps(payload)


# --- happy path -------------------------------------------------------------


def test_parse_message_builds_job():
    job = parse_message(_valid_body())
    assert job.source_file_s3_uri == VALID_URI
    assert job.case_ref == CASE_REF
    assert job.correspondence_type == ACCEPTED_CORRESPONDENCE_TYPE
    assert job.source_file_name == "Case1_TC19_50_pages_brain_injury.pdf"
    assert job.received_date == datetime.datetime(2026, 1, 15, 9, 30, 0)
    assert job.receipt_handle is None


def test_parse_message_uses_supplied_received_date():
    job = parse_message(_valid_body(received_date="2026-02-20T12:00:00"))
    assert job.received_date == datetime.datetime(2026, 2, 20, 12, 0, 0)


def test_parse_message_strips_correspondence_type_whitespace():
    # Surrounding whitespace is stripped before the accepted-type equality check.
    job = parse_message(_valid_body(correspondence_type=f"  {ACCEPTED_CORRESPONDENCE_TYPE}  "))
    assert job.correspondence_type == ACCEPTED_CORRESPONDENCE_TYPE


def test_parse_message_ignores_derived_fields():
    job = parse_message(_valid_body(source_doc_id="should-be-ignored", page_count=999))
    # A message-supplied source_doc_id is never trusted: the job's source_doc_id is
    # computed from the natural key, so the "should-be-ignored" value cannot leak in.
    assert job.source_doc_id != "should-be-ignored"
    assert (
        job.source_doc_id
        == DocumentIdentifier(
            source_file_name=job.source_file_name,
            correspondence_type=job.correspondence_type,
            case_ref=job.case_ref,
        ).generate_uuid()
    )
    # page_count is not part of a DocumentJob at all; it is derived during ingestion.
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
    body = json.dumps(
        {
            "correspondence_type": ACCEPTED_CORRESPONDENCE_TYPE,
            "source_file_s3_uri": VALID_URI,
            "received_date": RECEIVED_DATE,
        }
    )
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "case_ref"


def test_parse_message_missing_received_date_raises_malformed_with_field():
    body = json.dumps(
        {
            "correspondence_type": ACCEPTED_CORRESPONDENCE_TYPE,
            "case_ref": CASE_REF,
            "source_file_s3_uri": VALID_URI,
        }
    )
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "received_date"


def test_parse_message_missing_source_uri_raises_malformed_with_field():
    body = json.dumps(
        {
            "correspondence_type": ACCEPTED_CORRESPONDENCE_TYPE,
            "case_ref": CASE_REF,
            "received_date": RECEIVED_DATE,
        }
    )
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body)
    assert exc_info.value.field == "source_file_s3_uri"


def test_parse_message_bad_received_date_raises_malformed_with_field():
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(_valid_body(received_date="not-a-date"))
    assert exc_info.value.field == "received_date"


def test_parse_message_bad_case_ref_pattern_raises_malformed():
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(_valid_body(case_ref="26-611111"))
    assert exc_info.value.field == "case_ref"


@pytest.mark.parametrize(
    "value",
    ["", "   ", "TC19", "TC20 - SOMETHING ELSE", "tc19 - additional info request"],
)
def test_parse_message_unsupported_correspondence_type_raises_malformed(value):
    # Only the single accepted correspondence type is allowed; anything else (empty,
    # whitespace-only, wrong type, wrong case) is rejected.
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(_valid_body(correspondence_type=value))
    assert exc_info.value.field == "correspondence_type"


def test_parse_message_uri_failing_case_path_raises_malformed():
    # Valid case_ref field, but the URI path segment is not a valid case folder.
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(_valid_body(source_file_s3_uri=f"s3://{ROOT_BUCKET}/not-a-case/case1.pdf"))
    assert exc_info.value.field == "source_file_s3_uri"


@pytest.mark.parametrize(
    "uri",
    [
        f"s3://{ROOT_BUCKET}/{CASE_REF}/",  # folder only, no object key (trailing slash)
        f"s3://{ROOT_BUCKET}/{CASE_REF}",  # folder only, no trailing slash / key
        f"s3://{ROOT_BUCKET}/{CASE_REF}//case1.pdf",  # empty first key segment
    ],
)
def test_parse_message_uri_without_object_key_raises_malformed(uri):
    # A case folder with no real object key must be rejected; otherwise the case folder
    # would be mistaken for the file name and the later S3 lookup would fail instead.
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(_valid_body(source_file_s3_uri=uri))
    assert exc_info.value.field == "source_file_s3_uri"


def test_parse_message_bucket_not_matching_root_bucket_raises_malformed():
    # The URI is well-formed and its case folder matches case_ref, but the bucket is
    # not the configured source document root bucket.
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(_valid_body(source_file_s3_uri=f"s3://some-other-bucket/{CASE_REF}/case1.pdf"))
    assert exc_info.value.field == "source_file_s3_uri"
    assert "some-other-bucket" in str(exc_info.value)
    assert ROOT_BUCKET in str(exc_info.value)


def test_parse_message_respects_configured_root_bucket(monkeypatch):
    # Point the parser at a different configured root bucket and confirm a URI in that
    # bucket is accepted while the previous default bucket is rejected.
    monkeypatch.setattr(
        "ingestion_pipeline.orchestration.document_ingress.settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET",
        "dev-documentsearch-kta-bucket",
    )
    job = parse_message(_valid_body(source_file_s3_uri=f"s3://dev-documentsearch-kta-bucket/{CASE_REF}/case1.pdf"))
    assert job.source_file_s3_uri == f"s3://dev-documentsearch-kta-bucket/{CASE_REF}/case1.pdf"

    with pytest.raises(MalformedMessageError):
        parse_message(_valid_body())


def test_parse_message_case_ref_not_matching_uri_case_folder_raises_malformed():
    # case_ref and the URI's case folder are each individually valid but disagree.
    # This must be rejected: otherwise the document would be downloaded from one case
    # but identified/indexed under another.
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(_valid_body(case_ref="26-700001", source_file_s3_uri=f"s3://{ROOT_BUCKET}/26-800040/case1.pdf"))
    assert exc_info.value.field == "case_ref"
    assert "26-700001" in str(exc_info.value)
    assert "26-800040" in str(exc_info.value)


def test_parse_message_case_ref_matching_uri_case_folder_is_accepted():
    # Sanity check the happy path still passes with matching case references.
    job = parse_message(_valid_body(case_ref="26-800040", source_file_s3_uri=f"s3://{ROOT_BUCKET}/26-800040/case1.pdf"))
    assert job.case_ref == "26-800040"


# --- DocumentRequest direct -------------------------------------------------


def test_document_request_holds_supplied_fields():
    request = DocumentRequest(
        correspondence_type=ACCEPTED_CORRESPONDENCE_TYPE,
        case_ref=CASE_REF,
        source_file_s3_uri=VALID_URI,
        received_date=datetime.datetime(2026, 1, 15, 9, 30, 0),
    )
    assert request.source_file_s3_uri == VALID_URI
    assert request.case_ref == CASE_REF
    assert request.correspondence_type == ACCEPTED_CORRESPONDENCE_TYPE


def test_document_request_rejects_unsupported_correspondence_type():
    with pytest.raises(ValidationError):
        DocumentRequest(
            correspondence_type="TC20",
            case_ref=CASE_REF,
            source_file_s3_uri=VALID_URI,
            received_date=datetime.datetime(2026, 1, 15, 9, 30, 0),
        )


# --- _first_error_field -----------------------------------------------------


def test_first_error_field_returns_field_for_field_level_error():
    try:
        DocumentRequest(
            correspondence_type=ACCEPTED_CORRESPONDENCE_TYPE,
            case_ref="bad",
            source_file_s3_uri=VALID_URI,
            received_date=datetime.datetime(2026, 1, 15, 9, 30, 0),
        )
    except ValidationError as exc:
        assert _first_error_field(exc) == "case_ref"
    else:  # pragma: no cover - guard against silent regression
        pytest.fail("expected ValidationError")


def test_first_error_field_falls_back_to_body_when_no_location():
    # A whole-model error is reported by pydantic with an empty ``loc``; the helper
    # then names a concrete area ("body") rather than returning None.
    error = ValidationError.from_exception_data(
        "DocumentRequest",
        [{"type": "value_error", "loc": (), "input": {}, "ctx": {"error": "bad"}}],
    )
    assert _first_error_field(error) == "body"


# --- _all_error_fields ------------------------------------------------------


def test_all_error_fields_lists_every_failing_field():
    try:
        DocumentRequest(
            correspondence_type="WRONG",
            case_ref="bad",
            source_file_s3_uri=VALID_URI,
            received_date="not-a-date",
        )
    except ValidationError as exc:
        result = _all_error_fields(exc)
    else:  # pragma: no cover - guard against silent regression
        pytest.fail("expected ValidationError")

    fields = {f.strip() for f in result.split(",")}
    assert fields == {"correspondence_type", "case_ref", "received_date"}


def test_all_error_fields_deduplicates_repeated_fields():
    error = ValidationError.from_exception_data(
        "DocumentRequest",
        [
            {"type": "string_type", "loc": ("case_ref",), "input": 1},
            {"type": "value_error", "loc": ("case_ref",), "input": 1, "ctx": {"error": "bad"}},
        ],
    )
    assert _all_error_fields(error) == "case_ref"


def test_all_error_fields_falls_back_to_body_when_no_location():
    error = ValidationError.from_exception_data(
        "DocumentRequest",
        [{"type": "value_error", "loc": (), "input": {}, "ctx": {"error": "bad"}}],
    )
    assert _all_error_fields(error) == "body"


def test_parse_message_reports_all_invalid_fields():
    """A body wrong in several ways names every offending field in the error."""
    body = json.dumps(
        {
            "correspondence_type": "WRONG TYPE",
            "case_ref": "not-a-ref",
            "source_file_s3_uri": VALID_URI,
            "received_date": "not-a-date",
        }
    )
    with pytest.raises(MalformedMessageError) as exc_info:
        parse_message(body, message_id="m-1")

    message = str(exc_info.value)
    assert "correspondence_type" in message
    assert "case_ref" in message
    assert "received_date" in message
    # exc.field still carries the first offending field for coarse-grained logging.
    assert exc_info.value.field == "correspondence_type"
