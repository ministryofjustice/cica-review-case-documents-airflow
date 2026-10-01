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
:class:`DocumentJob`, leaves malformed messages on the queue so SQS redrives them to
the DLQ, and deletes messages once their document has been processed successfully.
Both failure classes therefore reach the DLQ via the same mechanism: any message left
undeleted (whether it failed to parse or failed processing) is redelivered and, after
``SQS_MAX_RECEIVE_COUNT`` receives, redriven to the DLQ for inspection and redrive.
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

# Upper bound on the raw message body included in the malformed-message log. The body
# is logged to reveal what the upstream system sent so the failure is diagnosable
# immediately (without waiting for the message to reach the DLQ). It is truncated to
# keep a single oversized or malicious payload from flooding the logs.
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
    The two are otherwise identical (no jobs) but call for different
    pacing: a ``RECEIVED`` or ``EMPTY`` poll already blocked for the long-poll wait,
    whereas a ``TRANSIENT_ERROR`` poll returns immediately (botocore fails fast once its
    own retries are exhausted) and so the caller should back off before retrying.

    Attributes:
        RECEIVED: The poll returned at least one valid job.
        EMPTY: A genuine empty long-poll receive (no valid jobs; a poll that saw only
            malformed messages is also EMPTY because it produced no work).
        TRANSIENT_ERROR: A transient receive error was swallowed and reported as an
            empty poll; the caller should back off and retry.
    """

    RECEIVED = "received"
    EMPTY = "empty"
    TRANSIENT_ERROR = "transient_error"


class FetchResult(BaseModel):
    """The outcome of a single ``fetch_batch`` poll: valid jobs plus malformed count.

    Carries the jobs parsed from one long-poll receive alongside the number of
    malformed messages seen during that same poll, so callers can account for every
    message received (valid or not). ``malformed_received`` equals the number of
    messages received minus the number of valid jobs produced. Note that malformed
    messages are left on the queue (not deleted) to be redriven to the DLQ, so the same
    malformed message is counted again on each poll until SQS redrives it; this counter
    therefore reflects malformed *receives*, not distinct messages. An empty poll or a
    transient-error poll carries no jobs and a ``malformed_received`` of 0; the
    ``outcome`` field distinguishes those two no-job cases from one another and from a
    populated poll. The model is frozen so a fetch result cannot be mutated after
    construction.
    """

    model_config = ConfigDict(frozen=True)

    jobs: list[DocumentJob] = Field(default_factory=list)
    malformed_received: int = Field(default=0, ge=0)
    outcome: FetchOutcome = FetchOutcome.EMPTY


class DocumentSource(Protocol):
    """Supplies batches of documents to ingest and acknowledges completed work.

    Implementations abstract the transport (SQS, an in-memory list for tests,
    etc.). The runner calls :meth:`fetch_batch` to obtain work and
    :meth:`acknowledge` after a job has been processed successfully.
    """

    def fetch_batch(self) -> FetchResult:
        """Return the next batch of documents plus the malformed-message count."""
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
    * Malformed messages are logged and left on the queue (not deleted) so SQS
      redelivers them and, after the configured max receive count, redrives them to the
      DLQ for inspection and possible redrive. They are not deleted because a
      "malformed" classification can be a consumer-side problem (a producer schema
      change this consumer version has not caught up to, or a consumer bug) rather than
      a permanently bad payload; deleting would silently discard a document request.
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
        """Receive one batch of messages and return the valid jobs and malformed count.

        Performs a single long-poll receive, parses each message into a
        :class:`DocumentJob`, and leaves malformed messages on the queue so SQS
        redelivers them and ultimately redrives them to the DLQ. A
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
                with the number of malformed messages seen during this poll and an
                ``outcome`` tag. A populated poll is ``RECEIVED``; a genuine empty
                receive (including a poll that saw only malformed messages) is
                ``EMPTY``; a swallowed transient receive error is ``TRANSIENT_ERROR``.
                Both no-job outcomes carry no jobs and a ``malformed_received`` of 0.
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
                return FetchResult(jobs=[], malformed_received=0, outcome=FetchOutcome.TRANSIENT_ERROR)
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
                # The malformed message is left on the queue (not deleted) so SQS
                # redelivers it and, after SQS_MAX_RECEIVE_COUNT receives, redrives it
                # to the DLQ for inspection. We do NOT delete here: deletion would
                # permanently discard the message, whereas a "malformed" classification
                # can be transient at the consumer level (a producer schema change this
                # consumer version has not caught up to, or a consumer bug), in which
                # case the DLQ message can be redriven once the consumer is fixed. The
                # raw body is still logged (truncated) so the failure is diagnosable
                # immediately without waiting for the DLQ.
                logger.error(
                    "Malformed message left for DLQ redrive (message_id=%s, field=%s): %s | raw body: %s",
                    message_id,
                    exc.field,
                    exc,
                    _truncate_body_for_log(body),
                )
                continue

            jobs.append(job.model_copy(update={"receipt_handle": receipt_handle}))

        logger.info(
            "SqsDocumentSource received %d message(s); %d valid job(s) after filtering malformed.",
            len(messages),
            len(jobs),
        )
        malformed_received = len(messages) - len(jobs)
        # RECEIVED when this poll produced work, otherwise a genuine EMPTY receive (a
        # poll that saw only malformed messages still had no valid jobs to hand back, so
        # it is EMPTY, not TRANSIENT_ERROR).
        outcome = FetchOutcome.RECEIVED if jobs else FetchOutcome.EMPTY
        return FetchResult(jobs=jobs, malformed_received=malformed_received, outcome=outcome)

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
            # The failure is logged and swallowed so one failed delete cannot abort the
            # batch. The tradeoff: the message is NOT removed, so after its visibility
            # timeout SQS redelivers it and the document is processed AGAIN. Processing
            # is idempotent on final state (deterministic source_doc_id -> same
            # OpenSearch doc ids and the same {case_ref}/{source_doc_id}/pages/ S3
            # prefix), so no duplicate/corrupt data results. But a full reprocess is NOT
            # free: it re-runs a billed Textract OCR job and billed Bedrock embedding
            # calls, re-uploads page images (new object versions on a versioned bucket),
            # and re-emits any OpenSearch/S3 "object created" events that downstream
            # systems may react to. A *persistently* failing delete is worse: each
            # redelivery increments the receive count, so a successfully-processed
            # document can eventually be redriven to the DLQ after SQS_MAX_RECEIVE_COUNT.
            # The robust fix is to avoid the reprocess when only the delete failed:
            # retry delete_message here, and/or add a per-message visibility heartbeat
            # (ChangeMessageVisibility) so a slow-but-healthy message is not redelivered.
            # That belongs with the concurrency/dispatch work (SQS stories 5/7).
            logger.error(
                "Failed to delete message (message_id=%s, doc=%s): %s",
                message_id,
                source_doc_id_hint,
                exc,
                exc_info=True,
            )
