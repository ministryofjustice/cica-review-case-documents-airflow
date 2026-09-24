"""Per-document outcome model for batch processing.

Defines :class:`DocumentResult`, the record produced for each processed document
in a batch. Kept separate from the batch execution logic so the data model and
the execution engine have distinct, independently importable boundaries.
"""

from dataclasses import dataclass

from ingestion_pipeline.errors import DlqCategory
from ingestion_pipeline.orchestration.document_source import DocumentJob


@dataclass
class DocumentResult:
    """Outcome of processing a single document in the batch.

    The pipeline contract is "succeed or raise". ``success`` is True only when
    ``process_document`` returned without raising, in which case the job is
    acknowledged (removed from the source). On any failure ``success`` is False,
    the job is left unacknowledged so SQS can redrive it toward the DLQ, and
    ``error``/``category``/``retryable`` capture the classification for the future
    metadata-index / DLQ-enrichment seam.
    """

    job: DocumentJob
    source_doc_id: str
    success: bool
    error: Exception | None = None
    category: DlqCategory | None = None
    retryable: bool | None = None


@dataclass(frozen=True)
class BatchSummary:
    """Per-batch aggregate counts for one ``run_batch`` invocation.

    ``jobs_in_batch`` is the number of jobs received into the batch
    (``len(jobs)``), not the number of owners. ``duplicates_collapsed`` is how
    many of those jobs were folded onto an earlier owner sharing the same
    ``source_doc_id``. There is no ``messages_discarded`` field: discards are a
    source/run concern, not a batch one.

    Attributes:
        batch_number: The 1-based sequence number of this batch within the run.
        jobs_in_batch: The number of jobs received into the batch (``len(jobs)``).
        succeeded: The number of processed owners that succeeded.
        failed: The number of processed owners that failed.
        duplicates_collapsed: The number of jobs folded onto an earlier owner.
    """

    batch_number: int
    jobs_in_batch: int
    succeeded: int
    failed: int
    duplicates_collapsed: int


@dataclass(frozen=True)
class BatchResult:
    """A batch outcome: its summary plus one DocumentResult per processed owner.

    Attributes:
        summary: The aggregate counts for the batch.
        results: One :class:`DocumentResult` per processed owner.
    """

    summary: BatchSummary
    results: list[DocumentResult]
