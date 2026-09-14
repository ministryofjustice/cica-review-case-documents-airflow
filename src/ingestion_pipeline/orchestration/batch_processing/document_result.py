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
