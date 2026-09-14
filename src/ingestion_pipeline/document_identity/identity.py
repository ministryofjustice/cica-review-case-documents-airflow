"""Document identity computation and metadata construction for the ingestion pipeline.

Provides the single source of truth for the natural-key -> ``source_doc_id``
computation and for building the :class:`DocumentMetadata` that feeds into the
pipeline, so that batch-level deduplication and per-document processing resolve
document identity identically.
"""

import datetime

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.orchestration.document_source import DocumentJob
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier


def compute_source_doc_id(job: DocumentJob) -> str:
    """Compute the deterministic source_doc_id for a job.

    Single source of truth for the natural-key -> source_doc_id computation, shared
    by both batch-level deduplication and per-document processing so they resolve
    the identifier identically.

    Args:
        job (DocumentJob): The document work item.

    Returns:
        str: The deterministic Version 5 UUID derived from the job's natural key
            (source_file_name, correspondence_type, case_ref).
    """
    return DocumentIdentifier(
        source_file_name=job.source_file_name,
        correspondence_type=job.correspondence_type,
        case_ref=job.case_ref,
    ).generate_uuid()


def build_document_metadata(job: DocumentJob, source_doc_id: str) -> DocumentMetadata:
    """Build the DocumentMetadata for a job.

    Args:
        job (DocumentJob): The document work item.
        source_doc_id (str): The deterministic document UUID.

    Returns:
        DocumentMetadata: Metadata ready to feed into the pipeline.
    """
    return DocumentMetadata(
        source_doc_id=source_doc_id,
        source_file_name=job.source_file_name,
        source_file_s3_uri=job.source_file_s3_uri,
        page_count=None,
        case_ref=job.case_ref,
        received_date=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
        correspondence_type=job.correspondence_type,
    )
