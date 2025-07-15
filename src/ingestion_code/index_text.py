import json
import logging

from opensearchpy import OpenSearch

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
        logger.info("OpenSearch client initialized.")
        return client
    except Exception as e:
        logger.info(f"Error initializing OpenSearch client: {e}")
        exit(1)


def index_text_to_opensearch(
    pdf_filename: str,
    chunks_with_embeddings: list[tuple[int, str, list[str], list[list[float]]]],
) -> None:
    client = get_opensearch_client()
    try:
        logger.info(f"Indexing document into '{settings.OPENSEARCH_INDEX_NAME}'...")
        for page_number, page_text, chunks, embeddings in chunks_with_embeddings:
            for chunk_index, (chunk_text, embedding) in enumerate(
                zip(chunks, embeddings)
            ):
                metadata = {
                    "s3_uri": pdf_filename,
                    "case_ref": "25/771234",
                    "correspondence_type": "TC19",
                    "page_count": count_pages_in_pdf(pdf_filename),
                    "page_number": page_number,
                    "chunk_id": f"{pdf_filename}_{page_number}_{chunk_index}",
                    "received_date": "2023-01-15 10:30:00",
                    "chunk_index": chunk_index,
                }
                document = {
                    "chunk_text": chunk_text,
                    "embedding": embedding,
                    **metadata,  # Unpack additional metadata
                }
                response = client.index(
                    index=settings.OPENSEARCH_INDEX_NAME,
                    body=document,
                    id=metadata.get("chunk_id"),
                )
                logger.info(f"Indexing response: {json.dumps(response, indent=2)}")
                if response.get("result") in ["created", "updated"]:
                    logger.info(
                        f"Document indexed successfully with ID: {response.get('_id')}"
                    )
                else:
                    logger.info(
                        f"Failed to index document. Result: {response.get('result')}"
                    )
        logger.info(
            f"Finished indexing documents into '{settings.OPENSEARCH_INDEX_NAME}'"
        )
    except Exception as e:
        logger.info(f"Error indexing document: {e}")
