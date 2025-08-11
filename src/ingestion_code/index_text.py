import json
import logging
from typing import Any

from opensearchpy import OpenSearch, OpenSearchException

from ingestion_code.config import settings
from ingestion_code.extract_text import count_pages_in_pdf

logger = logging.getLogger(__name__)


# --- Initialize OpenSearch Client ---
def get_opensearch_client() -> OpenSearch:
    """
    Initializes and returns an OpenSearch client.
    For LocalStack, we use HTTP (not HTTPS) and basic auth.
    """
    try:
        client = OpenSearch(
            hosts=[
                {"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}
            ],
            http_auth=(settings.OPENSEARCH_USERNAME, settings.OPENSEARCH_PASSWORD),
            use_ssl=False,  # Changed to False for LocalStack HTTP connection
            verify_certs=False,  # Disable certificate verification
            ssl_show_warn=False,  # Disable SSL warnings
            timeout=30,
        )
        logger.info("OpenSearch client initialised.")
        return client
    except Exception as e:
        logger.exception("Failed to initialise OpenSearch client.")
        raise RuntimeError("Error initialising OpenSearch client.") from e


def index_text_to_opensearch(
    pdf_filename: str,
    chunks_with_embeddings: list[tuple[int, str, list[str], list[list[float]]]],
) -> None:
    """Stores text chunks with embeddings in an OpenSearch database."""
    client = get_opensearch_client()
    logger.info(
        f"Indexing chunks with embeddings into '{settings.OPENSEARCH_INDEX_NAME}'..."
    )
    for page_number, page_text, chunks, embeddings in chunks_with_embeddings:
        for chunk_index, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"{pdf_filename}_{page_number}_{chunk_index}"
            metadata = {
                "s3_uri": pdf_filename,
                "case_ref": "25/771234",
                "correspondence_type": "TC19",
                "page_count": count_pages_in_pdf(pdf_filename),
                "page_number": page_number,
                "chunk_id": chunk_id,
                "received_date": "2023-01-15 10:30:00",
                "chunk_index": chunk_index,
            }
            document = {
                "chunk_text": chunk_text,
                "embedding": embedding,
                **metadata,  # Unpack additional metadata
            }
            try:
                response = client.index(
                    index=settings.OPENSEARCH_INDEX_NAME,
                    body=document,
                    id=chunk_id,
                )
                logger.debug("Indexing response:\n%s", json.dumps(response, indent=2))
            except OpenSearchException as e:
                logger.error(
                    "OpenSearch indexing failed for chunk with ID: %s.",
                    chunk_id,
                    exc_info=True,
                )
                raise RuntimeError(f"Error indexing chunk {chunk_id}") from e
            result = response.get("result")
            if result in ("created", "updated"):
                logger.debug("Chunk indexed successfully with ID: %s", chunk_id)
            else:
                logger.error(
                    "Failed to index chunk with ID %s: %s",
                    chunk_id,
                    result,
                    exc_info=True,
                )
                raise RuntimeError(
                    f"Unexpected result with indexing chunk with ID: {chunk_id}."
                )
    logger.info(
        "Finished indexing %d chunks into '%s'",
        sum(len(c[2]) for c in chunks_with_embeddings),
        settings.OPENSEARCH_INDEX_NAME,
    )


def index_textract_text_to_opensearch(
    chunks_with_embeddings: list[dict[str, Any]],
) -> None:
    """Stores text chunks with embeddings in an OpenSearch database."""
    client = get_opensearch_client()
    logger.info(
        f"Indexing chunks with embeddings into '{settings.OPENSEARCH_INDEX_NAME}'..."
    )
    for chunk_index, chunk in enumerate(chunks_with_embeddings):
        metadata = chunk["metadata"]
        page_number = metadata["page"]
        document_key = metadata["document_key"]
        page_count = metadata["page_count"]
        chunk_id = f"{document_key}_{page_number}_{chunk_index}"
        metadata = {
            "s3_uri": f"s3://{settings.S3_BUCKET_NAME}/{document_key}",
            "case_ref": "25/771234",
            "correspondence_type": "TC19",
            "page_count": page_count,
            "page_number": page_number,
            "chunk_id": chunk_id,
            "received_date": "2023-01-15 10:30:00",
            "chunk_index": chunk_index,
        }
        document = {
            "chunk_text": chunk["text"],
            "embedding": chunk["embedding"],
            **metadata,  # Unpack additional metadata
        }
        try:
            response = client.index(
                index=settings.OPENSEARCH_INDEX_NAME,
                body=document,
                id=chunk_id,
            )
            logger.debug("Indexing response:\n%s", json.dumps(response, indent=2))
        except OpenSearchException as e:
            logger.error(
                "OpenSearch indexing failed for chunk with ID: %s.",
                chunk_id,
                exc_info=True,
            )
            raise RuntimeError(f"Error indexing chunk {chunk_id}") from e
        result = response.get("result")
        if result in ("created", "updated"):
            logger.debug("Chunk indexed successfully with ID: %s", chunk_id)
        else:
            logger.error(
                "Failed to index chunk with ID %s: %s",
                chunk_id,
                result,
                exc_info=True,
            )
            raise RuntimeError(
                f"Unexpected result with indexing chunk with ID: {chunk_id}."
            )
    logger.info(
        "Finished indexing %d chunks into '%s'",
        len(chunks_with_embeddings),
        settings.OPENSEARCH_INDEX_NAME,
    )
