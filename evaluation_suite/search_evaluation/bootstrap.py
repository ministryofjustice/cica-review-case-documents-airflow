"""OpenSearch bootstrap for the search evaluation pipeline.

Makes an evaluation run self-sufficient: rather than assuming the local
environment's init scripts have already created the ``page_chunks`` index and
that documents have been indexed, the runnable pipeline calls
:func:`bootstrap_opensearch` to:

1. verify OpenSearch is reachable,
2. create the ``page_chunks`` index (with the kNN vector mapping) if missing,
3. trigger document ingestion if the index is empty.

The index mapping mirrors
``local-dev-environment/init-scripts/02-create-opensearch-resources.sh`` so the
evaluation suite no longer depends on that script having run.

Index state tracking
--------------------
After every successful ingestion ``bootstrap_opensearch`` writes a small JSON
file (.index_state.json) recording which chunking strategy built the corpus and
how many chunks it produced. On subsequent calls, when the index is non-empty
and ingestion is skipped, the file is read back and compared against the
currently configured ``DOCUMENT_CHUNKING_STRATEGY``. A mismatch is surfaced as a
WARNING so the user knows the corpus is stale before results are reported.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from opensearchpy import OpenSearch

from evaluation_suite.search_evaluation import evaluation_settings as eval_settings
from evaluation_suite.search_evaluation.opensearch_client import (
    CHUNK_INDEX_NAME,
    check_opensearch_health,
    get_opensearch_client,
)

logger = logging.getLogger("bootstrap")

# Persisted record of the strategy and size of the currently indexed corpus.
# Written after every ingestion run; read on every eval to detect mismatches.
_INDEX_STATE_DIR = Path(__file__).resolve().parent / "output"
_INDEX_STATE_FILE = _INDEX_STATE_DIR / ".index_state.json"


def _index_state_file_for_case(case_ref: str) -> Path:
    """Return the index-state file path for a specific case."""
    return _INDEX_STATE_DIR / f".index_state_{case_ref}.json"


def _write_index_state(strategy: str, chunk_count: int, case_ref: str | None = None) -> None:
    """Record the strategy used to build the current corpus.

    Args:
        strategy: Chunking strategy name.
        chunk_count: Number of chunks indexed.
        case_ref: When provided, writes a per-case state file instead of the
            global one.
    """
    path = _index_state_file_for_case(case_ref) if case_ref else _INDEX_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "chunking_strategy": strategy,
                "num_chunks": chunk_count,
                "indexed_at": datetime.now().isoformat(timespec="seconds"),
                **(({"case_ref": case_ref}) if case_ref else {}),
            },
            indent=2,
        )
    )


def _check_index_state(configured_strategy: str, case_ref: str | None = None) -> None:
    """Warn if the configured chunking strategy doesn't match the indexed corpus.

    Args:
        configured_strategy: The strategy currently configured in settings.
        case_ref: When provided, checks the per-case state file instead of the
            global one.
    """
    state_file = _index_state_file_for_case(case_ref) if case_ref else _INDEX_STATE_FILE
    if not state_file.exists():
        logger.warning(
            "No index state file found. Cannot verify that the indexed corpus matches "
            "the configured chunking strategy '%s'. Run "
            "run_chunking_comparison to rebuild with a known strategy.",
            configured_strategy,
        )
        return
    try:
        state = json.loads(state_file.read_text())
        indexed_strategy = state.get("chunking_strategy", "unknown")
        if indexed_strategy != configured_strategy:
            logger.warning(
                "Index mismatch: corpus was built with '%s' chunks "
                "but DOCUMENT_CHUNKING_STRATEGY is set to '%s'. "
                "Results may not reflect the configured strategy. "
                "Run run_chunking_comparison to rebuild the corpus.",
                indexed_strategy,
                configured_strategy,
            )
        else:
            logger.info(
                "Index state verified: corpus matches strategy '%s' (%s chunks, indexed %s).",
                indexed_strategy,
                state.get("num_chunks", "?"),
                state.get("indexed_at", "?"),
            )
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read index state file: %s", exc)


# (Titan = 1024) and the kNN method configured on the index.
_EMBEDDING_DIMENSION = 1024

# Index definition mirrors init-scripts/02-create-opensearch-resources.sh.
CHUNK_INDEX_BODY: dict = {
    "settings": {"index.knn": True},
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "source_doc_id": {"type": "keyword"},
            "chunk_text": {
                "type": "text",
                "fields": {"english": {"type": "text", "analyzer": "english"}},
            },
            "embedding": {
                "type": "knn_vector",
                "dimension": _EMBEDDING_DIMENSION,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "faiss",
                    "parameters": {"ef_construction": 128, "m": 24},
                },
            },
            "source_file_name": {"type": "keyword"},
            "page_id": {"type": "keyword", "index": False},
            "case_ref": {"type": "keyword"},
            "correspondence_type": {"type": "keyword"},
            "received_date": {
                "type": "date",
                "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||epoch_millis||yyyy-MM-dd'T'HH:mm:ss.SSSSSS",
            },
            "page_count": {"type": "integer"},
            "page_number": {"type": "integer"},
            "chunk_index": {"type": "integer"},
            "chunk_type": {"type": "keyword"},
            "confidence": {"type": "float"},
            "geometry": {
                "properties": {
                    "bounding_box": {
                        "properties": {
                            "top": {"type": "float"},
                            "left": {"type": "float"},
                            "width": {"type": "float"},
                            "height": {"type": "float"},
                        }
                    }
                }
            },
        }
    },
}


def ensure_chunk_index(client: OpenSearch | None = None) -> bool:
    """Create the chunk index with the kNN mapping if it does not exist.

    Args:
        client: Optional OpenSearch client; one is created if not provided.

    Returns:
        True if the index was created by this call, False if it already existed.
    """
    client = client or get_opensearch_client()
    if client.indices.exists(index=CHUNK_INDEX_NAME):
        logger.info(f"Index '{CHUNK_INDEX_NAME}' already exists.")
        return False

    logger.info(f"Index '{CHUNK_INDEX_NAME}' not found. Creating with kNN mapping...")
    client.indices.create(index=CHUNK_INDEX_NAME, body=CHUNK_INDEX_BODY)
    logger.info(f"Index '{CHUNK_INDEX_NAME}' created.")
    return True


def count_indexed_chunks(client: OpenSearch | None = None) -> int:
    """Return the total number of documents currently in the chunk index."""
    client = client or get_opensearch_client()
    return int(client.count(index=CHUNK_INDEX_NAME).get("count", 0))


def count_indexed_chunks_for_case(case_ref: str, client: OpenSearch | None = None) -> int:
    """Return the number of indexed chunks belonging to a specific case.

    Uses a ``term`` filter on ``case_ref`` so only chunks for that case are
    counted, even when the index contains multiple cases.

    Args:
        case_ref: The case reference to count chunks for (e.g. ``"26-700001"``).
        client: Optional OpenSearch client; one is created if not provided.

    Returns:
        Number of chunks indexed for the given case.
    """
    client = client or get_opensearch_client()
    response = client.count(
        index=CHUNK_INDEX_NAME,
        body={"query": {"bool": {"filter": {"term": {"case_ref": case_ref}}}}},
    )
    return int(response.get("count", 0))


def reset_chunk_index(client: OpenSearch | None = None) -> None:
    """Drop and recreate the chunk index so it can be re-ingested from scratch.

    Used when re-indexing the corpus with a different chunking strategy: deleting
    the index (rather than just the documents) guarantees a clean mapping and an
    empty index, so the next :func:`bootstrap_opensearch` call re-ingests.

    Args:
        client: Optional OpenSearch client; one is created if not provided.
    """
    client = client or get_opensearch_client()
    if client.indices.exists(index=CHUNK_INDEX_NAME):
        logger.info(f"Deleting index '{CHUNK_INDEX_NAME}' to re-index from scratch...")
        client.indices.delete(index=CHUNK_INDEX_NAME)
    ensure_chunk_index(client)
    # Clear the state file so the next bootstrap records the new strategy.
    if _INDEX_STATE_FILE.exists():
        _INDEX_STATE_FILE.unlink()


def index_documents() -> None:
    """Run the ingestion pipeline to index the configured source document(s).

    Delegates to the production ingestion runner, which performs the full
    Textract -> chunk -> embed -> index flow for the document configured via
    ``ingestion_pipeline`` settings. Imported lazily to avoid the runner's
    import-time logging setup unless indexing is actually required.
    """
    from ingestion_pipeline.runner import main as run_ingestion

    logger.info("Index is empty - running ingestion pipeline to index documents...")
    run_ingestion()


def bootstrap_opensearch(index_if_empty: bool = True, case_ref: str | None = None) -> int | None:
    """Prepare OpenSearch for an evaluation run.

    Ensures OpenSearch is reachable, the chunk index exists with the correct
    mapping, and (optionally) that documents have been indexed.

    When ``case_ref`` is provided the indexed-chunk check and index-state file
    are scoped to that case, allowing multiple cases to be bootstrapped into the
    same shared index without re-indexing already-present cases.

    Args:
        index_if_empty: When True (default), run document ingestion if the
            relevant chunk count is zero.
        case_ref: Optional case reference. When provided, only chunks for this
            case are counted to decide whether to re-index. Defaults to the
            global count (single-case backward-compat behaviour).

    Returns:
        The number of chunks for the case (or in the whole index if
        ``case_ref`` is None) after bootstrapping, or ``None`` when
        ``index_if_empty`` is False.
    """
    check_opensearch_health()

    client = get_opensearch_client()
    ensure_chunk_index(client)

    if not index_if_empty:
        return None

    try:
        from ingestion_pipeline.config import settings as ingestion_settings

        configured_strategy = ingestion_settings.DOCUMENT_CHUNKING_STRATEGY
    except Exception:  # pragma: no cover
        configured_strategy = "unknown"

    if case_ref:
        chunk_count = count_indexed_chunks_for_case(case_ref, client)
    else:
        chunk_count = count_indexed_chunks(client)

    if chunk_count == 0:
        index_documents()
        # Force a refresh so freshly indexed documents are searchable/countable
        # immediately, rather than waiting for the periodic refresh interval.
        client.indices.refresh(index=CHUNK_INDEX_NAME)
        chunk_count = count_indexed_chunks_for_case(case_ref, client) if case_ref else count_indexed_chunks(client)
        _write_index_state(configured_strategy, chunk_count, case_ref)
    else:
        ref_label = case_ref or eval_settings.CASE_FILTER
        logger.info(
            f"Case '{ref_label}' already has {chunk_count} chunks in '{CHUNK_INDEX_NAME}' - skipping ingestion."
        )
        _check_index_state(configured_strategy, case_ref)

    return chunk_count


__all__ = [
    "CHUNK_INDEX_BODY",
    "ensure_chunk_index",
    "count_indexed_chunks",
    "count_indexed_chunks_for_case",
    "reset_chunk_index",
    "index_documents",
    "bootstrap_opensearch",
]
