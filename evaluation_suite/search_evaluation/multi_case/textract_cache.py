"""Local Textract response cache for the multi-case evaluation pipeline.

Avoids redundant AWS Textract API calls by storing the raw JSON response for
each S3 document on disk. The cache is keyed on the resolved S3 URI so it
remains valid across runs with the same AWS environment.

Usage (via :func:`install_cache`)::

    from evaluation_suite.search_evaluation.multi_case.textract_cache import install_cache

    install_cache()
    # All subsequent TextractProcessor.process_document calls use the cache.
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from textractcaller.t_call import Textract_API, get_full_json
from textractor.parsers.response_parser import parse

if TYPE_CHECKING:
    from textractor.entities.document import Document

logger = logging.getLogger(__name__)

# Cache directory at the repository root — gitignored.
_CACHE_DIR = Path(__file__).resolve().parents[3] / ".textract_cache"

# Originals saved by install_cache() so patched functions can delegate.
_original_process_document = None
_original_get_job_results = None


def _cache_path(s3_uri: str) -> Path:
    digest = hashlib.sha256(s3_uri.encode()).hexdigest()[:16]
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", s3_uri)[:60]
    return _CACHE_DIR / f"{digest}_{safe}.json"


def _load(s3_uri: str) -> dict | None:
    path = _cache_path(s3_uri)
    if path.exists():
        return json.loads(path.read_text())
    return None


def _save(s3_uri: str, response: dict) -> None:
    _CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(s3_uri).write_text(json.dumps(response))


def _resolve_uri(s3_document_uri: str) -> str:
    """Apply the same MOD_PLATFORM URI remapping as TextractProcessor.process_document."""
    from ingestion_pipeline.config import settings

    if settings.USE_MOD_PLATFORM_MODE:
        parsed = urlparse(s3_document_uri)
        path = parsed.path.lstrip("/")
        return f"s3://{settings.AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET}/{path}"
    return s3_document_uri


def _cached_process_document(self, s3_document_uri: str) -> "Document | None":
    """Cache-aware replacement for TextractProcessor.process_document.

    On a cache hit, parses the stored JSON response and returns the Document
    without touching AWS.  On a miss, delegates to the original method (which
    starts and polls a real Textract job) and saves the raw response via the
    companion :func:`_cached_get_job_results` patch.
    """
    resolved_uri = _resolve_uri(s3_document_uri)

    cached = _load(resolved_uri)
    if cached is not None:
        logger.info("Textract cache hit for %s — skipping AWS job.", resolved_uri)
        return parse(cached)

    logger.info("Textract cache miss for %s — running full Textract job.", resolved_uri)
    # Store resolved URI as instance state so _cached_get_job_results can use it.
    self._textract_cache_uri = resolved_uri
    try:
        return _original_process_document(self, s3_document_uri)
    finally:
        self._textract_cache_uri = None


def _cached_get_job_results(self, job_id: str) -> "Document":
    """Drop-in for TextractProcessor._get_job_results that saves the raw response.

    Replicates the original logic (fetch full JSON → parse) while also writing
    the JSON to the cache when a pending URI is set on the processor instance.
    """
    logger.info("Fetching results for Textract job %s", job_id)
    full_response = get_full_json(
        job_id=job_id,
        boto3_textract_client=self.textract_client,
        textract_api=Textract_API.ANALYZE,
    )
    uri = getattr(self, "_textract_cache_uri", None)
    if uri:
        _save(uri, full_response)
        logger.info("Textract response cached for %s", uri)
    return parse(full_response)


def install_cache() -> None:
    """Monkey-patch TextractProcessor with Textract response caching.

    Replaces ``process_document`` and ``_get_job_results`` on the class so
    every instance created after this call benefits from the disk cache.
    Must be called before ``ingestion_pipeline.pipeline_builder`` imports
    ``TextractProcessor``.
    """
    global _original_process_document, _original_get_job_results
    import ingestion_pipeline.textract.textract_processor as _tp_module

    _original_process_document = _tp_module.TextractProcessor.process_document
    _original_get_job_results = _tp_module.TextractProcessor._get_job_results
    _tp_module.TextractProcessor.process_document = _cached_process_document
    _tp_module.TextractProcessor._get_job_results = _cached_get_job_results
    logger.info("Textract response cache installed (cache dir: %s)", _CACHE_DIR)
