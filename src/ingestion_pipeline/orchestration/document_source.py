"""Document source interfaces for supplying documents to the ingestion pipeline.

This module defines the boundary between "where do documents to ingest come from"
and "how a document is processed". The pipeline runner pulls a batch of
:class:`DocumentJob` items from a :class:`DocumentSource` and processes them in
parallel.

The source is SQS-backed: an upstream system enqueues a message per document
(containing its S3 location and CICA metadata), the runner receives a batch,
processes each message, and deletes successfully handled messages from the queue.
:class:`SqsDocumentSource` implements this against a real boto3 SQS client: it
resolves the queue URL, long-polls for messages, parses each body into a
:class:`DocumentJob`, permanently discards malformed messages (by deleting them),
and deletes messages once their document has been processed successfully. Note that
deleting a malformed message does not send it to the DLQ; only processing failures
(valid messages left undeleted) are redriven to the DLQ by SQS.
"""

import datetime
import enum
import logging
from typing import List, Optional, Protocol

from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError, HTTPClientError
from pydantic import BaseModel, ConfigDict, Field, computed_field

from ingestion_pipeline.config import settings
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

logger = logging.getLogger(__name__)

# SQS/botocore error codes that represent transient conditions worth retrying on the
# next poll. Anything not listed here (auth, validation, bad endpoint, unknown) is
# treated as permanent and propagated so the run fails visibly rather than silently
# reporting "no work".
_TRANSIENT_SQS_ERROR_CODES = frozenset(
    {
        "RequestThrottled",
        "ThrottlingException",
        "Throttling",
        # Temporary per-request rate limit SQS can return (notably on short polling).
        "OverLimit",
        "RequestTimeout",
        "RequestTimeoutException",
        "ServiceUnavailable",
        "InternalError",
        "InternalFailure",
        "ServiceError",
        # KMS throttling: SQS returns "KmsThrottled"; the dotted spelling is kept too in
        # case a different surface reports it that way.
        "KmsThrottled",
        "KMS.ThrottlingException",
    }
)

# Upper bound on the raw message body included in the malformed-message discard log.
# The body is the only diagnostic record of a discarded message (deletion does not
# route it to the DLQ), so it is logged to reveal what the upstream system sent. It is
# truncated to keep a single oversized or malicious payload from flooding the logs.
_MAX_LOGGED_BODY_CHARS = 2000


def _truncate_body_for_log(body: str) -> str:
    """Return the message body clipped and escaped for safe logging.

    The body is producer-controlled, so control characters (e.g. newlines) are
    escaped with a ``repr``-style encoding before logging. This prevents a
    malicious or malformed payload from forging additional log lines or
    corrupting downstream log parsing.

    Args:
        body (str): The raw SQS message body.

    Returns:
        str: The escaped body if it is within :data:`_MAX_LOGGED_BODY_CHARS`,
            otherwise the escaped leading slice followed by a marker noting how many
            raw characters were omitted.
    """
    if len(body) <= _MAX_LOGGED_BODY_CHARS:
        return _escape_control_chars(body)
    omitted = len(body) - _MAX_LOGGED_BODY_CHARS
    escaped = _escape_control_chars(body[:_MAX_LOGGED_BODY_CHARS])
    return f"{escaped}... [truncated {omitted} more chars]"


def _escape_control_chars(text: str) -> str:
    """Escape control characters so they cannot forge or corrupt log lines.

    Uses a ``repr``-style encoding (via ``unicode_escape``) so newlines, carriage
    returns, tabs and other control characters are rendered as visible escape
    sequences rather than affecting the structure of the log output.

    Args:
        text (str): The text to escape.

    Returns:
        str: The text with control characters replaced by escape sequences.
    """
    return text.encode("unicode_escape").decode("ascii")


def _is_transient_receive_error(exc: Exception) -> bool:
    """Return True if a receive_message failure is transient and safe to skip.

    Transient failures (throttling, temporary service errors, connection blips) are
    treated as an empty poll so the caller can retry. Permanent or unknown failures
    (e.g. AccessDenied, invalid endpoint, malformed request) return False so they
    propagate and fail the run rather than masquerading as a drained queue.

    Args:
        exc (Exception): The exception raised by ``receive_message``.

    Returns:
        bool: True if the error is a known transient condition.
    """
    # Transport-level botocore failures raised after the SDK's own retries are
    # exhausted. ConnectionError covers connection-establishment failures (e.g.
    # EndpointConnectionError); HTTPClientError covers in-flight transport failures
    # (e.g. ReadTimeoutError, ConnectionClosedError) which do NOT derive from
    # ConnectionError and would otherwise be misclassified as permanent.
    if isinstance(exc, (ConnectionError, EndpointConnectionError, HTTPClientError)):
        return True
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        return code in _TRANSIENT_SQS_ERROR_CODES
    return False


class DocumentJob(BaseModel):
    """A single, self-describing unit of work: one document to ingest.

    A job is complete on construction: it carries the producer-supplied natural-key
    metadata (``source_file_s3_uri``, ``correspondence_type``, ``case_ref``) and
    exposes every value derived from it. ``source_file_name`` and the deterministic
    ``source_doc_id`` are computed fields, not constructor inputs, so they can never
    disagree with the natural key they are derived from and are resolved identically
    everywhere the job travels (batch-level deduplication and per-document
    processing). When backed by a real queue, ``receipt_handle`` identifies the
    originating message so it can be deleted after successful processing.
    """

    model_config = ConfigDict(frozen=True)

    source_file_s3_uri: str = Field(min_length=1)
    correspondence_type: str = Field(min_length=1)
    case_ref: str = Field(min_length=1)
    # Producer-supplied receipt/ingestion date. When None the runner falls back to the
    # message receipt time (set by the source) or, ultimately, the current time.
    received_date: Optional[datetime.datetime] = None
    # Opaque handle used to acknowledge/delete the source message (SQS receipt handle).
    receipt_handle: Optional[str] = None

    @computed_field
    @property
    def source_file_name(self) -> str:
        """Return the file name portion of the S3 URI."""
        return self.source_file_s3_uri.rstrip("/").split("/")[-1]

    @computed_field
    @property
    def source_doc_id(self) -> str:
        """Return the deterministic document identifier derived from the natural key.

        Computed from ``(source_file_name, correspondence_type, case_ref)`` via
        :class:`DocumentIdentifier`, so the same batch and per-document code paths
        always resolve the same id for the same document. Because it is derived, a
        ``model_copy`` that attaches a ``receipt_handle`` leaves it unchanged.

        Returns:
            str: The deterministic Version 5 UUID for this document.
        """
        return DocumentIdentifier(
            source_file_name=self.source_file_name,
            correspondence_type=self.correspondence_type,
            case_ref=self.case_ref,
        ).generate_uuid()


class FetchOutcome(str, enum.Enum):
    """Why a ``fetch_batch`` poll produced the jobs (if any) it did.

    Distinguishes the two ways a poll can carry no jobs so a long-lived caller can
    react differently: a genuine empty receive (the queue had nothing right now) versus
    a swallowed transient receive error (SQS was momentarily throttling/unreachable).
    The two are otherwise identical (no jobs, no discards) but call for different
    pacing: a ``RECEIVED`` or ``EMPTY`` poll already blocked for the long-poll wait,
    whereas a ``TRANSIENT_ERROR`` poll returns immediately (botocore fails fast once its
    own retries are exhausted) and so the caller should back off before retrying.

    Attributes:
        RECEIVED: The poll returned at least one valid job.
        EMPTY: A genuine empty long-poll receive (no messages, no discards).
        TRANSIENT_ERROR: A transient receive error was swallowed and reported as an
            empty poll; the caller should back off and retry.
    """

    RECEIVED = "received"
    EMPTY = "empty"
    TRANSIENT_ERROR = "transient_error"


class FetchResult(BaseModel):
    """The outcome of a single ``fetch_batch`` poll: valid jobs plus discard count.

    Carries the jobs parsed from one long-poll receive alongside the number of
    malformed messages discarded during that same poll, so callers can account for
    every message received (valid or not). ``malformed_discarded`` equals the number
    of messages received minus the number of valid jobs produced. An empty poll or a
    transient-error poll carries no jobs and a ``malformed_discarded`` of 0; the
    ``outcome`` field distinguishes those two no-job cases from one another and from a
    populated poll. The model is frozen so a fetch result cannot be mutated after
    construction.
    """

    model_config = ConfigDict(frozen=True)

    jobs: list[DocumentJob] = Field(default_factory=list)
    malformed_discarded: int = Field(default=0, ge=0)
    outcome: FetchOutcome = FetchOutcome.EMPTY


class DocumentSource(Protocol):
    """Supplies batches of documents to ingest and acknowledges completed work.

    Implementations abstract the transport (SQS, an in-memory list for tests,
    etc.). The runner calls :meth:`fetch_batch` to obtain work and
    :meth:`acknowledge` after a job has been processed successfully.
    """

    def fetch_batch(self) -> FetchResult:
        """Return the next batch of documents plus the malformed discard count."""
        ...

    def acknowledge(self, job: DocumentJob) -> None:
        """Mark a job as successfully processed so it is not redelivered."""
        ...


class QueueResolutionError(RuntimeError):
    """Raised when the configured SQS queue URL cannot be resolved by name."""


class SqsDocumentSource:
    """SQS-backed document source.

    Receives document-processing requests from the configured SQS queue using long
    polling, parses each message body into a :class:`DocumentJob` (capturing the
    message ``ReceiptHandle``), and manages the message lifecycle:

    * Messages that parse and validate become jobs for the runner to process.
    * Malformed messages are logged and deleted immediately so they neither block the
      queue nor return after their visibility timeout. Deleting removes them for good:
      it does NOT route them to the DLQ (SQS redrive only fires after repeated receives,
      which cannot happen once a message is deleted), so a malformed message is
      permanently discarded and the log line is its only record.
    * :meth:`acknowledge` deletes a message after its document was processed
      successfully. Jobs that fail processing are left undeleted so SQS can redrive
      them to the DLQ after the configured max receive count.

    The queue URL is resolved from the ``SQS_DOCUMENT_QUEUE`` name at construction;
    an unresolvable name raises :class:`QueueResolutionError`.
    """

    def __init__(
        self,
        sqs_client=None,
        queue_name: Optional[str] = None,
        max_messages: Optional[int] = None,
        wait_time_seconds: Optional[int] = None,
        visibility_timeout_seconds: Optional[int] = None,
    ):
        """Initialise the source and resolve the queue URL.

        Args:
            sqs_client: A boto3 SQS client. When None, one is created via the
                ``aws_client`` factory.
            queue_name: The SQS queue name. Defaults to ``settings.SQS_DOCUMENT_QUEUE``.
            max_messages: Max messages per receive. Defaults to
                ``settings.SQS_MAX_MESSAGES_PER_POLL``.
            wait_time_seconds: Long-poll wait time. Defaults to
                ``settings.SQS_POLL_WAIT_TIME_SECONDS``.
            visibility_timeout_seconds: Per-message visibility timeout. Defaults to
                ``settings.SQS_VISIBILITY_TIMEOUT_SECONDS``.

        Raises:
            QueueResolutionError: If the queue URL cannot be resolved from the name.
        """
        # Imported lazily so importing this module (and DocumentJob) does not require
        # boto3/AWS configuration, keeping the parser and job model cheap to import.
        from ingestion_pipeline.aws_client.clients import get_sqs_client

        self.sqs_client = sqs_client if sqs_client is not None else get_sqs_client()
        self.queue_name = queue_name or settings.SQS_DOCUMENT_QUEUE
        self.max_messages = max_messages if max_messages is not None else settings.SQS_MAX_MESSAGES_PER_POLL
        self.wait_time_seconds = (
            wait_time_seconds if wait_time_seconds is not None else settings.SQS_POLL_WAIT_TIME_SECONDS
        )
        self.visibility_timeout_seconds = (
            visibility_timeout_seconds
            if visibility_timeout_seconds is not None
            else settings.SQS_VISIBILITY_TIMEOUT_SECONDS
        )
        self.queue_url = self._resolve_queue_url()

    def _resolve_queue_url(self) -> str:
        """Resolve the queue URL from the configured queue name.

        Returns:
            str: The resolved SQS queue URL.

        Raises:
            QueueResolutionError: If the queue URL cannot be resolved.
        """
        try:
            response = self.sqs_client.get_queue_url(QueueName=self.queue_name)
        except Exception as exc:
            logger.critical("Could not resolve SQS queue URL for queue '%s': %s", self.queue_name, exc)
            raise QueueResolutionError(f"Could not resolve SQS queue URL for queue '{self.queue_name}'") from exc

        queue_url = response.get("QueueUrl")
        if not queue_url:
            logger.critical("SQS get_queue_url returned no QueueUrl for queue '%s'.", self.queue_name)
            raise QueueResolutionError(f"No QueueUrl returned for queue '{self.queue_name}'")
        return queue_url

    def fetch_batch(self) -> FetchResult:
        """Receive one batch of messages and return the valid jobs and discard count.

        Performs a single long-poll receive, parses each message into a
        :class:`DocumentJob`, and deletes malformed messages (permanently discarding
        them; deletion does not route them to the DLQ) without blocking the queue. A
        *transient* receive error
        (throttling, temporary service error, connection blip) is logged and treated
        as an empty batch so the caller can retry; a permanent or unknown receive
        error is logged and re-raised so the run fails rather than silently reporting
        no work.

        Raises:
            Exception: Re-raises any non-transient error from ``receive_message``
                (e.g. AccessDenied, invalid endpoint, malformed request).

        Returns:
            FetchResult: The valid jobs from this receive (possibly empty) together
                with the number of malformed messages discarded during this poll and an
                ``outcome`` tag. A populated poll is ``RECEIVED``; a genuine empty
                receive (including a poll that only discarded malformed messages) is
                ``EMPTY``; a swallowed transient receive error is ``TRANSIENT_ERROR``.
                Both no-job outcomes carry no jobs and a discard count of 0.
        """
        # Imported here to avoid a module-level import cycle (document_ingress imports
        # DocumentJob from this module).
        from ingestion_pipeline.orchestration.document_ingress import MalformedMessageError, parse_message

        try:
            response = self.sqs_client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=self.max_messages,
                WaitTimeSeconds=self.wait_time_seconds,
                VisibilityTimeout=self.visibility_timeout_seconds,
            )
        except Exception as exc:
            # Only known transient failures (throttling, temporary service errors,
            # connection blips) are swallowed as an empty poll for the caller to retry.
            # Permanent or unknown failures (AccessDenied, invalid endpoint, malformed
            # request, etc.) must propagate: otherwise an empty batch would look like a
            # drained queue and the run would report success while unable to read work.
            if _is_transient_receive_error(exc):
                logger.warning(
                    "Transient error receiving messages from queue '%s'; treating as empty poll: %s",
                    self.queue_name,
                    exc,
                )
                # Tagged TRANSIENT_ERROR (not EMPTY) so a long-lived caller can back off
                # before retrying: this path returns immediately, whereas a genuine empty
                # receive already spent the long-poll wait.
                return FetchResult(jobs=[], malformed_discarded=0, outcome=FetchOutcome.TRANSIENT_ERROR)
            logger.critical(
                "Permanent/unknown error receiving messages from queue '%s'; failing the run: %s",
                self.queue_name,
                exc,
                exc_info=True,
            )
            raise

        messages = response.get("Messages", [])
        jobs: List[DocumentJob] = []
        for message in messages:
            message_id = message.get("MessageId")
            receipt_handle = message.get("ReceiptHandle")
            body = message.get("Body", "")
            try:
                job = parse_message(body, message_id=message_id)
            except MalformedMessageError as exc:
                # The raw body is logged (truncated) because a discarded message is
                # deleted rather than sent to the DLQ, so this log entry is the only
                # record of what the upstream system sent.
                logger.error(
                    "Discarding malformed message (message_id=%s, field=%s): %s | raw body: %s",
                    message_id,
                    exc.field,
                    exc,
                    _truncate_body_for_log(body),
                )
                self._delete_message(receipt_handle, message_id=message_id)
                continue

            jobs.append(job.model_copy(update={"receipt_handle": receipt_handle}))

        logger.info(
            "SqsDocumentSource received %d message(s); %d valid job(s) after filtering malformed.",
            len(messages),
            len(jobs),
        )
        malformed_discarded = len(messages) - len(jobs)
        # RECEIVED when this poll produced work, otherwise a genuine EMPTY receive (a
        # poll that only discarded malformed messages still had no valid jobs to hand
        # back, so it is EMPTY, not TRANSIENT_ERROR).
        outcome = FetchOutcome.RECEIVED if jobs else FetchOutcome.EMPTY
        return FetchResult(jobs=jobs, malformed_discarded=malformed_discarded, outcome=outcome)

    def acknowledge(self, job: DocumentJob) -> None:
        """Delete a successfully processed job's message from the queue.

        Args:
            job (DocumentJob): The processed job carrying the message receipt handle.
        """
        if not job.receipt_handle:
            logger.warning("Cannot acknowledge job for %s: no receipt handle present.", job.source_file_s3_uri)
            return
        self._delete_message(job.receipt_handle, source_doc_id_hint=job.source_file_s3_uri)

    def _delete_message(
        self,
        receipt_handle: Optional[str],
        *,
        message_id: Optional[str] = None,
        source_doc_id_hint: Optional[str] = None,
    ) -> None:
        """Delete a message from the queue, logging (but not raising) on failure.

        Args:
            receipt_handle (Optional[str]): The receipt handle of the message to delete.
            message_id (Optional[str]): The SQS message id, for log context.
            source_doc_id_hint (Optional[str]): A document hint (e.g. S3 URI), for log context.
        """
        if not receipt_handle:
            logger.warning("Cannot delete message (message_id=%s): no receipt handle.", message_id)
            return
        try:
            self.sqs_client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)
        except Exception as exc:
            logger.error(
                "Failed to delete message (message_id=%s, doc=%s): %s",
                message_id,
                source_doc_id_hint,
                exc,
                exc_info=True,
            )
