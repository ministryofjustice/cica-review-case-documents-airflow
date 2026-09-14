"""Worker and batch orchestration for parallel document processing.

Processes a batch of documents in parallel. Documents are supplied by a
:class:`DocumentSource` (an SQS-backed stub for now). A single :class:`Pipeline`
and its underlying AWS/OpenSearch clients are constructed once in the main thread
and shared across worker threads; each worker sets its own logging context so
per-document log lines remain correctly attributed.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from ingestion_pipeline.config import settings
from ingestion_pipeline.custom_logging.log_context import source_doc_id_context
from ingestion_pipeline.document_identity.identity import build_document_metadata, compute_source_doc_id
from ingestion_pipeline.errors import DlqCategory, PipelineError
from ingestion_pipeline.orchestration.batch_processing.document_result import DocumentResult
from ingestion_pipeline.orchestration.document_source import DocumentJob, DocumentSource
from ingestion_pipeline.orchestration.pipeline import Pipeline
from ingestion_pipeline.s3_utils.s3_uri import validate_s3_uri

logger = logging.getLogger(__name__)


def process_document_job(job: DocumentJob, pipeline: Pipeline) -> DocumentResult:
    """Process a single document. Runs inside a worker thread.

    Sets the per-document logging context for the duration of the call (ContextVars
    are not inherited by pool threads, so each worker must set its own), validates
    the S3 URI, runs the pipeline, and contains any error so one failing document
    does not abort the batch.

    Args:
        job (DocumentJob): The document to process.
        pipeline (Pipeline): The shared, thread-safe pipeline instance.

    Returns:
        DocumentResult: The outcome for this document.
    """
    source_doc_id = compute_source_doc_id(job)
    token = source_doc_id_context.set(source_doc_id)
    try:
        logger.info(f"Generated source_doc_id: {source_doc_id} for document: {job.source_file_s3_uri}")

        if not validate_s3_uri(job.source_file_s3_uri, settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET):
            raise ValueError(f"Invalid S3 URI: {job.source_file_s3_uri}")

        logger.info(f"Processing document for case reference: {job.case_ref}")
        document_metadata = build_document_metadata(job, source_doc_id)
        logger.info(f"Document metadata prepared: file={document_metadata.source_file_name}, case_ref={job.case_ref}")

        # Succeed-or-raise: a normal return means the document was fully indexed.
        pipeline.process_document(document_metadata=document_metadata)

        logger.info(f"Finished processing document {job.source_file_s3_uri}")
        return DocumentResult(job=job, source_doc_id=source_doc_id, success=True)
    except PipelineError as exc:
        # Classified pipeline failure. The pipeline has already cleaned up its side
        # effects; here we only record the outcome. The job is NOT acknowledged, so
        # SQS will redrive it toward the DLQ.
        # TODO: write an enriched failure record to the OpenSearch metadata/status
        #   index using exc.failure_context() (additional to SQS redrive + DLQ).
        logger.error(
            f"Document {job.source_file_s3_uri} failed with {type(exc).__name__} "
            f"(category={exc.category.value}, retryable={exc.retryable}); not acknowledging. Details: {exc}",
            exc_info=True,
        )
        return DocumentResult(
            job=job,
            source_doc_id=source_doc_id,
            success=False,
            error=exc,
            category=exc.category,
            retryable=exc.retryable,
        )
    except Exception as exc:
        # Unclassified/unexpected failure (e.g. invalid S3 URI before the pipeline
        # runs). Treated as a non-retryable, unexpected failure; not acknowledged.
        logger.critical(
            f"Pipeline runner encountered an unexpected error for source_doc_id={source_doc_id}, "
            f"case_ref={job.case_ref}, s3_uri={job.source_file_s3_uri}: {type(exc).__name__}: {exc}",
            exc_info=True,
        )
        return DocumentResult(
            job=job,
            source_doc_id=source_doc_id,
            success=False,
            error=exc,
            category=DlqCategory.UNEXPECTED,
            retryable=False,
        )
    finally:
        source_doc_id_context.reset(token)


def run_batch(jobs: list[DocumentJob], pipeline: Pipeline, source: DocumentSource) -> list[DocumentResult]:
    """Process a batch of documents concurrently, collapsing duplicate source_doc_ids.

    Jobs are grouped by their deterministic ``source_doc_id`` while preserving input
    order. The first job seen for an id is the *owner* and is the only job submitted
    to the thread pool; any later jobs sharing that id are *duplicates* and are not
    processed. This guarantees at most one in-flight unit per ``source_doc_id``, so
    two jobs that resolve to the same id (a repeated config key or an SQS
    redelivery) can never race on the shared OpenSearch document IDs or the shared
    ``{case_ref}/{source_doc_id}/pages/`` S3 prefix.

    Acknowledgement follows the owner's outcome: on success the owner and all of its
    duplicates are acknowledged (so SQS drops the redundant messages); on failure the
    owner and its duplicates are all left unacknowledged for redrive. A batch with no
    duplicate ids behaves exactly as before — every job is its own owner with an
    empty duplicate list, ``max_workers`` is unchanged, and one ``DocumentResult`` is
    returned per job.

    Args:
        jobs (list[DocumentJob]): Documents to process.
        pipeline (Pipeline): The shared pipeline instance.
        source (DocumentSource): The source used to acknowledge completed jobs.

    Returns:
        list[DocumentResult]: One result per processed owner (at most one per
            distinct ``source_doc_id``). Duplicate jobs produce no result.
    """
    if not jobs:
        logger.info("No documents to process in this batch.")
        return []

    # Preserve input order while grouping by deterministic source_doc_id. The first
    # job seen for an id is the owner; the rest are duplicates collapsed onto it.
    owners: list[DocumentJob] = []
    duplicates_by_id: dict[str, list[DocumentJob]] = {}
    owner_by_id: dict[str, DocumentJob] = {}
    for job in jobs:
        source_doc_id = compute_source_doc_id(job)
        if source_doc_id not in owner_by_id:
            owner_by_id[source_doc_id] = job
            owners.append(job)
            duplicates_by_id[source_doc_id] = []
        else:
            duplicates_by_id[source_doc_id].append(job)

    # Observability: surface every collapsed duplicate so operators can see that
    # redelivered/repeated documents were deduplicated rather than silently dropped.
    for source_doc_id, duplicates in duplicates_by_id.items():
        if duplicates:
            duplicate_details = [{"s3_uri": dup.source_file_s3_uri, "case_ref": dup.case_ref} for dup in duplicates]
            logger.warning(
                "Collapsed %d duplicate job(s) for source_doc_id=%s "
                "(owner s3_uri=%s, case_ref=%s); duplicates=%s. "
                "Duplicates will follow the owner's acknowledgement outcome.",
                len(duplicates),
                source_doc_id,
                owner_by_id[source_doc_id].source_file_s3_uri,
                owner_by_id[source_doc_id].case_ref,
                duplicate_details,
            )

    max_workers = min(settings.MAX_CONCURRENT_DOCUMENTS, len(owners))
    logger.info(
        f"Processing {len(owners)} owner document(s) "
        f"({len(jobs)} job(s) in batch) with up to {max_workers} concurrent worker(s)."
    )

    results: list[DocumentResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {executor.submit(process_document_job, job, pipeline): job for job in owners}
        for future in as_completed(future_to_job):
            result = future.result()
            results.append(result)
            if result.success:
                # Acknowledge the owner, then drop its collapsed duplicates so SQS
                # does not redeliver them. On failure everything is left for redrive.
                source.acknowledge(result.job)
                for duplicate in duplicates_by_id[result.source_doc_id]:
                    source.acknowledge(duplicate)

    succeeded = sum(1 for r in results if r.success)
    failed = len(results) - succeeded
    logger.info(f"Batch complete: {succeeded} succeeded, {failed} failed (of {len(results)}).")
    return results
