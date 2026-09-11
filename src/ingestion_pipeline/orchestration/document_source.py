"""Document source interfaces for supplying documents to the ingestion pipeline.

This module defines the boundary between "where do documents to ingest come from"
and "how a document is processed". The pipeline runner pulls a batch of
:class:`DocumentJob` items from a :class:`DocumentSource` and processes them in
parallel.

The production intent is an SQS-backed source: an upstream system enqueues a
message per document (containing its S3 location and CICA metadata), the runner
receives a batch, processes each message, and deletes successfully handled
messages from the queue. :class:`SqsDocumentSource` is currently a STUB that
synthesises a batch from configuration so the parallel runner can be developed
and tested ahead of the real queue integration.
"""

import logging
from typing import List, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ingestion_pipeline.config import settings

logger = logging.getLogger(__name__)


class DocumentJob(BaseModel):
    """A single unit of work: one document to ingest.

    Carries the natural-key metadata needed to build a ``DocumentMetadata`` and
    generate the deterministic ``source_doc_id``. When backed by a real queue,
    ``receipt_handle`` identifies the originating message so it can be deleted
    after successful processing.
    """

    model_config = ConfigDict(frozen=True)

    source_file_s3_uri: str = Field(min_length=1)
    correspondence_type: str = Field(min_length=1)
    case_ref: str = Field(min_length=1)
    # Opaque handle used to acknowledge/delete the source message (SQS receipt handle).
    receipt_handle: Optional[str] = None

    @property
    def source_file_name(self) -> str:
        """Return the file name portion of the S3 URI."""
        return self.source_file_s3_uri.rstrip("/").split("/")[-1]


class DocumentSource(Protocol):
    """Supplies batches of documents to ingest and acknowledges completed work.

    Implementations abstract the transport (SQS, an in-memory list for tests,
    etc.). The runner calls :meth:`fetch_batch` to obtain work and
    :meth:`acknowledge` after a job has been processed successfully.
    """

    def fetch_batch(self) -> List[DocumentJob]:
        """Return the next batch of documents to process (possibly empty)."""
        ...

    def acknowledge(self, job: DocumentJob) -> None:
        """Mark a job as successfully processed so it is not redelivered."""
        ...


class SqsDocumentSource:
    """STUB SQS-backed document source.

    Intended shape of the real implementation:
        * ``fetch_batch`` -> ``sqs.receive_message(QueueUrl=..., MaxNumberOfMessages=N)``
          and parse each message body into a ``DocumentJob`` (capturing the
          ``ReceiptHandle``).
        * ``acknowledge`` -> ``sqs.delete_message(QueueUrl=..., ReceiptHandle=...)``.

    For now it synthesises a single-item batch from ``settings`` so the parallel
    runner is exercisable end-to-end without a live queue. Replace the body of
    ``fetch_batch``/``acknowledge`` with real SQS calls when the queue exists.
    """

    def __init__(self, queue_url: Optional[str] = None, max_messages: int = 10):
        """Initialise the stub source.

        Args:
            queue_url: The SQS queue URL to receive from. Unused by the stub.
            max_messages: Maximum messages to request per batch. Unused by the stub.
        """
        self.queue_url = queue_url
        self.max_messages = max_messages

    def fetch_batch(self) -> List[DocumentJob]:
        """Return a batch of documents to process.

        STUB: builds the batch from configuration. When ``SRC_S3_KEY`` is set it
        is parsed as a comma-separated list of S3 keys (relative to the root
        bucket) and one job is built per key; otherwise a single job is built
        from the ``CASE_PREFIX``/``FILENAME`` settings. The real implementation
        will receive messages from SQS and deserialise them.
        """
        # TODO: replace with sqs.receive_message + message body parsing.
        keys = [key.strip() for key in settings.SRC_S3_KEY.split(",") if key.strip()]
        if not keys:
            keys = [
                f"{settings.AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX}/{settings.AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME}"
            ]

        jobs = [self._build_job_from_key(key) for key in keys]
        logger.info("SqsDocumentSource stub produced a batch of %d document(s).", len(jobs))
        return jobs

    @staticmethod
    def _build_job_from_key(s3_key: str) -> DocumentJob:
        """Build a DocumentJob from an S3 key relative to the source root bucket.

        The ``case_ref`` is derived from the leading folder of the key
        (e.g. ``26-700030/case30.pdf`` -> ``26-700030``).

        Args:
            s3_key: S3 object key relative to the source document root bucket.

        Returns:
            DocumentJob: The work item for the document.
        """
        s3_key = s3_key.lstrip("/")
        case_ref = s3_key.split("/")[0]
        s3_uri = f"s3://{settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET}/{s3_key}"
        return DocumentJob(
            source_file_s3_uri=s3_uri,
            correspondence_type="TC19 - ADDITIONAL INFO REQUEST",
            case_ref=case_ref,
        )

    def acknowledge(self, job: DocumentJob) -> None:
        """Acknowledge a successfully processed job.

        STUB: no-op. The real implementation will call
        ``sqs.delete_message(QueueUrl=self.queue_url, ReceiptHandle=job.receipt_handle)``.
        """
        # TODO: replace with sqs.delete_message using job.receipt_handle.
        logger.debug("SqsDocumentSource stub acknowledge (no-op) for %s", job.source_file_s3_uri)
