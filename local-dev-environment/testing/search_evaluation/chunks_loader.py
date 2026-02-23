"""Load all chunks from OpenSearch for term matching.

This module queries OpenSearch to fetch all indexed chunks and provides
them as a lookup dictionary for the relevance scoring process.
"""

import logging

from testing.search_evaluation.opensearch_client import (
    CHUNK_INDEX_NAME,
    OpenSearchConnectionError,
    get_opensearch_client,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chunks_loader")


def load_all_chunks_from_opensearch() -> dict[str, str]:
    """Fetch all chunks from OpenSearch and return as a lookup dictionary.

    Uses scroll API to handle large result sets efficiently.

    Returns:
        Dictionary mapping chunk_id to chunk_text.
    """
    try:
        client = get_opensearch_client()

        # First, get the total count
        count_response = client.count(index=CHUNK_INDEX_NAME)
        total_chunks = count_response["count"]
        logger.info(f"Found {total_chunks} chunks in index '{CHUNK_INDEX_NAME}'")

        if total_chunks == 0:
            logger.warning("No chunks found in OpenSearch index")
            return {}

        # Use scroll API for efficient retrieval of all documents
        chunk_lookup: dict[str, str] = {}
        scroll_timeout = "2m"
        batch_size = 1000

        # Initial search request
        response = client.search(
            index=CHUNK_INDEX_NAME,
            body={
                "query": {"match_all": {}},
                "size": batch_size,
                "_source": ["chunk_text", "page_number", "case_reference"],
            },
            scroll=scroll_timeout,
        )

        scroll_id = response["_scroll_id"]
        hits = response["hits"]["hits"]

        # Process first batch
        for hit in hits:
            chunk_id = hit["_id"]
            chunk_text = hit["_source"].get("chunk_text", "")
            chunk_lookup[chunk_id] = chunk_text

        # Continue scrolling until no more results
        while len(hits) > 0:
            response = client.scroll(scroll_id=scroll_id, scroll=scroll_timeout)
            scroll_id = response["_scroll_id"]
            hits = response["hits"]["hits"]

            for hit in hits:
                chunk_id = hit["_id"]
                chunk_text = hit["_source"].get("chunk_text", "")
                chunk_lookup[chunk_id] = chunk_text

        # Clean up scroll context
        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass  # Scroll may have already expired

        logger.info(f"Loaded {len(chunk_lookup)} chunks from OpenSearch")
        return chunk_lookup

    except OpenSearchConnectionError as ce:
        logger.error("Could not connect to OpenSearch. Is the OpenSearch DB running locally?")
        logger.error(f"OpenSearch ConnectionError details: {ce}")
        return {}

    except Exception as e:
        logger.error(f"Failed to load chunks from OpenSearch: {e}")
        return {}


def get_chunk_details_from_opensearch() -> list[dict]:
    """Fetch all chunks with full details from OpenSearch.

    Returns:
        List of dictionaries with chunk_id, chunk_text, page_number, case_reference.
    """
    try:
        client = get_opensearch_client()

        chunks: list[dict] = []
        scroll_timeout = "2m"
        batch_size = 1000

        response = client.search(
            index=CHUNK_INDEX_NAME,
            body={
                "query": {"match_all": {}},
                "size": batch_size,
                "_source": ["chunk_text", "page_number", "case_reference"],
            },
            scroll=scroll_timeout,
        )

        scroll_id = response["_scroll_id"]
        hits = response["hits"]["hits"]

        def process_hits(hits: list[dict]) -> None:
            for hit in hits:
                chunks.append(
                    {
                        "chunk_id": hit["_id"],
                        "chunk_text": hit["_source"].get("chunk_text", ""),
                        "page_number": hit["_source"].get("page_number", ""),
                        "case_reference": hit["_source"].get("case_reference", ""),
                    }
                )

        process_hits(hits)

        while len(hits) > 0:
            response = client.scroll(scroll_id=scroll_id, scroll=scroll_timeout)
            scroll_id = response["_scroll_id"]
            hits = response["hits"]["hits"]
            process_hits(hits)

        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass

        logger.info(f"Loaded {len(chunks)} chunk details from OpenSearch")
        return chunks

    except OpenSearchConnectionError as ce:
        logger.error("Could not connect to OpenSearch. Is the OpenSearch DB running locally?")
        logger.error(f"OpenSearch ConnectionError details: {ce}")
        return []

    except Exception as e:
        logger.error(f"Failed to load chunk details from OpenSearch: {e}")
        return []
