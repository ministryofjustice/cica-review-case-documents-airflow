"""Parsing and validation of SQS document-processing messages.

An external producer places one message per document on the document queue. This
module turns a raw SQS message body into a validated :class:`DocumentRequest` and
then into a :class:`DocumentJob` the runner can process.

The message contract distinguishes:
    * Producer-supplied fields: ``correspondence_type``, ``case_ref`` and the source
      document location (either a full ``source_file_s3_uri`` or the
      ``bucket``/``case_prefix``/``filename`` components used to build it), plus an
      optional ``received_date``.
    * Derived fields: ``source_doc_id`` and ``page_count`` are computed during
      ingestion, never taken from the message. Any values supplied for them are
      ignored.

Anything that cannot be parsed or fails validation raises
:class:`MalformedMessageError`, which the source layer uses to route the message
for dead-letter handling.
"""

import datetime
import json
import logging
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ingestion_pipeline.orchestration.document_source import DocumentJob

logger = logging.getLogger(__name__)

# Case reference pattern: two digits, a hyphen, then 7 or 8 followed by five digits
# (e.g. ``26-711111``). Shared by the case_ref field and the S3 URI path check.
CASE_REF_PATTERN = r"^\d{2}-[78]\d{5}$"
# Resolved S3 URI must place the document under a case-reference folder, e.g.
# ``s3://some-bucket/26-711111/file.pdf``. The case segment is captured so it can be
# checked for equality against the message's case_ref (they must match, otherwise a
# document would be fetched from one case but identified/indexed under another).
S3_URI_CASE_PATH_PATTERN = r"^s3://[^/]+/(\d{2}-[78]\d{5})/"


class MalformedMessageError(Exception):
    """Raised when a message cannot be parsed or fails validation.

    Carries the failed field name (when known) so the caller can log precisely
    which part of the contract was violated before routing the message to
    dead-letter handling.

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

    Holds only producer-supplied fields. The source document location may be given
    either as a full ``source_file_s3_uri`` or as its component parts; after
    validation :meth:`resolved_s3_uri` returns the effective URI.

    Derived fields (``source_doc_id``, ``page_count``) are deliberately absent: they
    are computed during ingestion and any values in the message body are ignored.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    correspondence_type: str = Field(min_length=1)
    case_ref: str = Field(pattern=CASE_REF_PATTERN)

    # Source location: either the full URI, or the components to build it.
    source_file_s3_uri: Optional[str] = Field(default=None, min_length=1)
    bucket: Optional[str] = Field(default=None, min_length=1)
    case_prefix: Optional[str] = Field(default=None, min_length=1)
    filename: Optional[str] = Field(default=None, min_length=1)

    received_date: Optional[datetime.datetime] = None

    @model_validator(mode="after")
    def validate_source_location(self) -> "DocumentRequest":
        """Ensure the source document location is fully specified one way or the other.

        Returns:
            DocumentRequest: The validated request.

        Raises:
            ValueError: If neither a full ``source_file_s3_uri`` nor a complete set of
                ``bucket``/``case_prefix``/``filename`` components was supplied.
        """
        if self.source_file_s3_uri:
            return self
        if self.bucket and self.case_prefix and self.filename:
            return self
        raise ValueError(
            "source location must be provided as 'source_file_s3_uri' or as "
            "'bucket', 'case_prefix' and 'filename' components"
        )

    def resolved_s3_uri(self) -> str:
        """Return the effective S3 URI for the document.

        Uses ``source_file_s3_uri`` when supplied, otherwise builds it from the
        component parts.

        Returns:
            str: The resolved S3 URI.
        """
        if self.source_file_s3_uri:
            return self.source_file_s3_uri
        prefix = self.case_prefix.strip("/")
        filename = self.filename.lstrip("/")
        return f"s3://{self.bucket}/{prefix}/{filename}"


def parse_message(body: str, *, message_id: Optional[str] = None) -> DocumentJob:
    """Parse and validate an SQS message body into a :class:`DocumentJob`.

    Parses the body as JSON, validates the producer-supplied fields against the
    message contract, resolves the source S3 URI, and checks it places the document
    under a valid case-reference path. Derived fields are not read from the message.

    Args:
        body (str): The raw SQS message body.
        message_id (Optional[str]): The SQS message identifier, used only to enrich
            error messages.

    Returns:
        DocumentJob: The validated work item (without a receipt handle, which the
            caller attaches from the SQS message).

    Raises:
        MalformedMessageError: If the body is not valid JSON, a required field is
            missing or invalid, or the resolved S3 URI fails the case-path check.
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

    s3_uri = request.resolved_s3_uri()
    match = re.match(S3_URI_CASE_PATH_PATTERN, s3_uri)
    if not match:
        raise MalformedMessageError(
            f"resolved source_file_s3_uri does not match the required case path{id_suffix}: {s3_uri}",
            field="source_file_s3_uri",
        )

    # The URI's case-folder segment must match the message's case_ref. Otherwise the
    # runner would download the object from one case's folder while deriving the
    # source_doc_id and indexed metadata from a different case reference, silently
    # associating the document with the wrong case.
    uri_case_ref = match.group(1)
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


def _first_error_field(exc: ValidationError) -> Optional[str]:
    """Return the name of the first field that failed validation, if identifiable.

    Args:
        exc (ValidationError): The pydantic validation error.

    Returns:
        Optional[str]: The offending field name, or ``None`` for model-level errors
            with no single field.
    """
    for error in exc.errors():
        location = error.get("loc") or ()
        if location:
            return str(location[0])
    return None
