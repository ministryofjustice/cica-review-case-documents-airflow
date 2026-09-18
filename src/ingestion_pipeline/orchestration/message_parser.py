"""Parsing and validation of SQS document-processing messages.

An external producer places one message per document on the document queue. This
module turns a raw SQS message body into a validated :class:`DocumentRequest` and
then into a :class:`DocumentJob` the runner can process.

The message contract is deliberately flat and fully specified (no optional fields):
    * ``correspondence_type`` - must be the single accepted type
      (``TC19 - ADDITIONAL INFO REQUEST``); any other value is rejected.
    * ``case_ref`` - must match the CICA case-reference pattern AND match the case
      folder embedded in ``source_file_s3_uri``.
    * ``source_file_s3_uri`` - must live in the configured source document root
      bucket and place the document under its case-reference folder.
    * ``received_date`` - the producer-supplied receipt/ingestion date.

Derived fields (``source_doc_id``, ``page_count``) are never taken from the message;
they are computed during ingestion and any values supplied for them are ignored.

Anything that cannot be parsed or fails validation raises
:class:`MalformedMessageError`. The source layer logs and then **permanently
discards** such messages by deleting them from the queue. Deleting does not route a
message to the DLQ (SQS redrive only happens after repeated receives, which cannot
occur once a message is deleted), so the log entry is the only record of a malformed
message.
"""

import datetime
import json
import logging
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ingestion_pipeline.config import settings
from ingestion_pipeline.orchestration.document_source import DocumentJob

logger = logging.getLogger(__name__)

# The only correspondence type currently accepted. Messages carrying any other type
# are rejected as malformed rather than ingested.
ACCEPTED_CORRESPONDENCE_TYPE = "TC19 - ADDITIONAL INFO REQUEST"

# Case reference pattern: two digits, a hyphen, then 7 or 8 followed by five digits
# (e.g. ``26-711111``). Shared by the case_ref field and the S3 URI path check.
CASE_REF_PATTERN = r"^\d{2}-[78]\d{5}$"
# The S3 URI must name a bucket, then a case-reference folder, then a non-empty object
# key, e.g. ``s3://some-bucket/26-711111/file.pdf``. The bucket and the case segment are
# captured so they can be checked against the configured root bucket and the message's
# case_ref respectively. The ``[^/].*`` tail requires a real object key: a folder-only
# URI such as ``s3://bucket/26-711111/`` is rejected as malformed rather than accepted
# with the case folder mistaken for the file name.
S3_URI_PATTERN = r"^s3://([^/]+)/(\d{2}-[78]\d{5})/[^/].*$"


class MalformedMessageError(Exception):
    """Raised when a message cannot be parsed or fails validation.

    Carries the failed field name (when known) so the caller can log precisely
    which part of the contract was violated before discarding the message.

    Attributes:
        field (Optional[str]): The offending field name, if a specific field caused
            the failure. ``None`` for whole-body failures such as invalid JSON.
    """

    def __init__(self, message: str, *, field: Optional[str] = None):
        """Initialise the error.

        Args:
            message (str): Human-readable description of why the message is malformed.
            field (Optional[str]): The offending field name, if applicable.
        """
        super().__init__(message)
        self.field = field


class DocumentRequest(BaseModel):
    """Validated in-memory representation of a single SQS message body.

    Holds only producer-supplied fields, all of which are required. The source
    document location is always the full ``source_file_s3_uri``.

    Derived fields (``source_doc_id``, ``page_count``) are deliberately absent: they
    are computed during ingestion and any values in the message body are ignored.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    correspondence_type: str = Field(min_length=1)
    case_ref: str = Field(pattern=CASE_REF_PATTERN)
    source_file_s3_uri: str = Field(min_length=1)
    received_date: datetime.datetime

    @field_validator("correspondence_type")
    @classmethod
    def _validate_correspondence_type(cls, v: str) -> str:
        """Accept only the single supported correspondence type.

        The value is stripped of surrounding whitespace and then checked for equality
        against :data:`ACCEPTED_CORRESPONDENCE_TYPE`. Any other value (including empty
        or whitespace-only) is rejected so unsupported document types are never
        ingested.

        Args:
            v (str): The supplied correspondence type.

        Returns:
            str: The accepted correspondence type.

        Raises:
            ValueError: If the value is not the accepted correspondence type.
        """
        stripped = v.strip()
        if stripped != ACCEPTED_CORRESPONDENCE_TYPE:
            raise ValueError(f"correspondence_type must be '{ACCEPTED_CORRESPONDENCE_TYPE}'")
        return stripped


def parse_message(body: str, *, message_id: Optional[str] = None) -> DocumentJob:
    """Parse and validate an SQS message body into a :class:`DocumentJob`.

    Parses the body as JSON, validates the producer-supplied fields against the
    message contract, and checks that ``source_file_s3_uri`` lives in the configured
    source document root bucket and places the document under a case-reference folder
    that matches ``case_ref``. Derived fields are not read from the message.

    Args:
        body (str): The raw SQS message body.
        message_id (Optional[str]): The SQS message identifier, used only to enrich
            error messages.

    Returns:
        DocumentJob: The validated work item (without a receipt handle, which the
            caller attaches from the SQS message).

    Raises:
        MalformedMessageError: If the body is not valid JSON, a required field is
            missing or invalid, the S3 URI is malformed, its bucket does not match the
            configured root bucket, or its case folder does not match ``case_ref``.
    """
    id_suffix = f" (message_id={message_id})" if message_id else ""

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError) as exc:
        raise MalformedMessageError(f"message body is not valid JSON{id_suffix}: {exc}") from exc

    if not isinstance(payload, dict):
        raise MalformedMessageError(f"message body must be a JSON object{id_suffix}")

    try:
        request = DocumentRequest.model_validate(payload)
    except ValidationError as exc:
        field = _first_error_field(exc)
        raise MalformedMessageError(
            f"message failed validation{id_suffix} (field={field}): {exc}",
            field=field,
        ) from exc

    s3_uri = request.source_file_s3_uri
    match = re.match(S3_URI_PATTERN, s3_uri)
    if not match:
        raise MalformedMessageError(
            f"source_file_s3_uri does not match the required case path{id_suffix}: {s3_uri}",
            field="source_file_s3_uri",
        )

    uri_bucket = match.group(1)
    uri_case_ref = match.group(2)

    # The URI's bucket must be the configured source document root bucket. Otherwise the
    # runner would attempt to fetch the object from a bucket the pipeline is not
    # configured for (and is not permitted to read).
    expected_bucket = settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET
    if uri_bucket != expected_bucket:
        raise MalformedMessageError(
            f"source_file_s3_uri bucket '{uri_bucket}' does not match the configured "
            f"source document root bucket '{expected_bucket}'{id_suffix}: {s3_uri}",
            field="source_file_s3_uri",
        )

    # The URI's case-folder segment must match the message's case_ref. Otherwise the
    # runner would download the object from one case's folder while deriving the
    # source_doc_id and indexed metadata from a different case reference, silently
    # associating the document with the wrong case.
    if uri_case_ref != request.case_ref:
        raise MalformedMessageError(
            f"case_ref '{request.case_ref}' does not match the case folder '{uri_case_ref}' "
            f"in source_file_s3_uri{id_suffix}: {s3_uri}",
            field="case_ref",
        )

    return DocumentJob(
        source_file_s3_uri=s3_uri,
        correspondence_type=request.correspondence_type,
        case_ref=request.case_ref,
        received_date=request.received_date,
    )


def _first_error_field(exc: ValidationError) -> str:
    """Return the name of the first field that failed validation.

    Args:
        exc (ValidationError): The pydantic validation error.

    Returns:
        str: The offending field name. Field-level errors return the field; a
            whole-model error (which pydantic reports with an empty ``loc``) returns
            ``"body"`` so the malformed-message log names a concrete area rather than
            ``None``.
    """
    for error in exc.errors():
        location = error.get("loc") or ()
        if location:
            return str(location[0])
    return "body"
