"""Document identity computation and metadata construction for the ingestion pipeline.

Provides the single source of truth for the natural-key -> ``source_doc_id``
computation and for building the :class:`DocumentMetadata` that feeds into the
pipeline, so that batch-level deduplication and per-document processing resolve
document identity identically.
"""

import datetime

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.orchestration.document_source import DocumentJob


def compute_source_doc_id(job: DocumentJob) -> str:
    """Return the deterministic source_doc_id for a job.

    Thin accessor kept for backwards compatibility. The identifier now lives on the
    job itself as the computed :attr:`DocumentJob.source_doc_id`, so this simply
    surfaces that value; callers may read ``job.source_doc_id`` directly.

    Args:
        job (DocumentJob): The document work item.

    Returns:
        str: The deterministic Version 5 UUID derived from the job's natural key
            (source_file_name, correspondence_type, case_ref).
    """
    return job.source_doc_id


def build_document_metadata(job: DocumentJob, source_doc_id: str) -> DocumentMetadata:
    """Build the DocumentMetadata for a job.

    Args:
        job (DocumentJob): The document work item.
        source_doc_id (str): The deterministic document UUID (equal to
            ``job.source_doc_id``; accepted as an argument so callers that already
            hold the id do not recompute it).

    Returns:
        DocumentMetadata: Metadata ready to feed into the pipeline.
    """
    # Prefer the producer-supplied received_date when present; otherwise fall back to
    # the current time (message receipt time). Stored naive-UTC to match the schema:
    # a tz-aware value is converted to UTC and stripped of tzinfo.
    received_date = job.received_date
    if received_date is None:
        received_date = datetime.datetime.now(datetime.timezone.utc)
    if received_date.tzinfo is not None:
        received_date = received_date.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    return DocumentMetadata(
        source_doc_id=source_doc_id,
        source_file_name=job.source_file_name,
        source_file_s3_uri=job.source_file_s3_uri,
        page_count=None,
        case_ref=job.case_ref,
        received_date=received_date,
        correspondence_type=job.correspondence_type,
    )
