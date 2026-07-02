"""Bootstrap all evaluation cases into a shared OpenSearch index.

Iterates over a list of :class:`~evaluation_suite.search_evaluation.multi_case.case_discovery.CaseSpec`
objects and ensures each case's documents are indexed in OpenSearch.  Ingestion
is skipped for cases that already have indexed chunks, making the function safe
to re-run (idempotent).

Subprocess-per-case ingestion
------------------------------
``ingestion_pipeline.config.settings`` is a module-level Pydantic singleton
that reads environment variables **once at import time**.  Calling
``ingestion_pipeline.runner.main()`` in-process a second time with different
env vars would still use the settings from the first import.

To work around this each case is ingested in a **fresh subprocess** via
:func:`_ingest_case_subprocess`, which sets the case-specific env vars
(``AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX`` and
``AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME``) before launching
``ingestion_pipeline.runner``.
"""

import logging
import os
import subprocess
import sys

from evaluation_suite.search_evaluation.multi_case.case_discovery import CaseSpec
from evaluation_suite.search_evaluation.opensearch.bootstrap import (
    check_opensearch_health,
    count_indexed_chunks_for_case,
    ensure_chunk_index,
)
from evaluation_suite.search_evaluation.opensearch.opensearch_client import (
    CHUNK_INDEX_NAME,
    get_opensearch_client,
)
from ingestion_pipeline.config import settings

logger = logging.getLogger(__name__)


def _ingest_case_subprocess(case: CaseSpec) -> None:
    """Run the ingestion pipeline for *case* in a fresh subprocess.

    Launches ``ingestion_pipeline.runner`` with
    ``AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX`` and
    ``AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME`` injected into the process
    environment so the singleton settings are initialised correctly for this
    specific case.

    Args:
        case: The case to ingest.

    Raises:
        subprocess.CalledProcessError: If the ingestion process exits non-zero.
    """
    env = {
        **os.environ,
        "AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX": case.case_ref,
        "AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME": case.s3_filename,
        # The evaluation cases live in the MOD_PLATFORM bucket, not LocalStack.
        # Override the CICA S3 source settings so the PDF download uses the
        # same bucket and credentials as Textract (USE_MOD_PLATFORM_MODE).
        "AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET": settings.AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET,
        "AWS_CICA_AWS_ACCESS_KEY_ID": settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
        "AWS_CICA_AWS_SECRET_ACCESS_KEY": settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
        "AWS_CICA_AWS_SESSION_TOKEN": settings.AWS_MOD_PLATFORM_SESSION_TOKEN,
        # Route page-image uploads to the same MOD_PLATFORM bucket so they
        # succeed with MOD_PLATFORM credentials.
        "AWS_CICA_S3_PAGE_BUCKET": settings.AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET,
        # Disable LocalStack mode so get_s3_client() connects to real AWS
        # (LOCAL_DEVELOPMENT_MODE=true hardcodes endpoint_url=localhost:4566).
        "LOCAL_DEVELOPMENT_MODE": "false",
    }
    logger.info(
        "Case '%s': starting ingestion subprocess for '%s'.",
        case.case_ref,
        case.s3_filename,
    )
    subprocess.run(
        [sys.executable, "-m", "evaluation_suite.search_evaluation.multi_case.ingestion_runner"],
        env=env,
        check=True,
    )


def bootstrap_all_cases(cases: list[CaseSpec]) -> dict[str, int]:
    """Ensure every case in *cases* is indexed in OpenSearch.

    Performs a single health-check and index-creation pass, then loops over
    cases: skips any case that already has indexed chunks and runs the
    ingestion subprocess for the rest.

    Args:
        cases: Ordered list of cases to bootstrap.

    Returns:
        Mapping of ``case_ref`` → number of chunks indexed after bootstrapping.
        A value of ``0`` for a case means ingestion ran but produced no chunks
        (which would indicate a problem with the source document).
    """
    check_opensearch_health()
    client = get_opensearch_client()
    ensure_chunk_index(client)

    results: dict[str, int] = {}
    for case in cases:
        count = count_indexed_chunks_for_case(case.case_ref, client)
        if count > 0:
            logger.info(
                "Case '%s': already has %d chunks in index — skipping ingestion.",
                case.case_ref,
                count,
            )
        else:
            _ingest_case_subprocess(case)
            client.indices.refresh(index=CHUNK_INDEX_NAME)
            count = count_indexed_chunks_for_case(case.case_ref, client)
            if count == 0:
                logger.warning(
                    "Case '%s': ingestion subprocess exited cleanly but 0 chunks were "
                    "indexed. The source document may be empty, Textract returned no "
                    "usable blocks, or ingestion failed silently. "
                    "Check the subprocess output above for errors and re-run with "
                    "--cases %s to retry this case.",
                    case.case_ref,
                    case.case_ref,
                )
            logger.info(
                "Case '%s': ingestion complete — %d chunks indexed.",
                case.case_ref,
                count,
            )
        results[case.case_ref] = count

    return results


__all__ = ["bootstrap_all_cases"]
