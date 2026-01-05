"""Index a document into OpenSearch with a 1024-dimension embedding vector.

This script connects to a LocalStack OpenSearch instance and indexes a document
with a mock embedding vector for testing purposes. It is not intended for production use.
"""

import logging
import sys

from examples import embedding_example_1024  # Import the example embedding vector
from opensearchpy import OpenSearch

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

console_output_handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_output_handler.setFormatter(formatter)
logger.addHandler(console_output_handler)


# --- 1. CONFIGURE YOUR LOCALSTACK OPENSEARCH CONNECTION ---
HOST = "localhost"
PORT = 9200
USER = "admin"
PASSWORD = "really-secure-passwordAa!1"

# --- 2. DEFINE YOUR DOCUMENT AND INDEX DETAILS ---
INDEX_NAME = "case-documents"
source_doc_id = "document-id"

# This is the full document body, including a 1024-dimension vector
document_body = {
    "chunk_id": "doc-gla-456_p1_c0",
    "source_doc_id": "doc-111111",
    "chunk_text": "Text for an imaginary medical report for document creation and retrieval purposes.",
    "embedding": embedding_example_1024,
    "case_ref": "25-781234",
    "received_date": "2025-08-18 11:55:00",
    "source_file_name": "medical_record_18-08-2925.pdf",
    "s3_page_image_uri": "s3://case-kta-document-images-bucket/doc-111111/page_1.png",
    "correspondence_type": "TC19",
    "page_count": 12,
    "page_number": 1,
    "chunk_index": 0,
    "chunk_type": "LAYOUT_TEXT",
    "confidence": 99.81,
    "geometry": {"BoundingBox": {"Width": 0.9, "Height": 0.08, "Left": 0.05, "Top": 0.22}},
}


# --- 3. EXECUTE THE INDEXING OPERATION ---
def main():
    """Main function to index a test document into OpenSearch."""
    # Create the client instance for LocalStack
    # NOTE: use_ssl is set to False as the bash script uses http
    client = OpenSearch(
        hosts=[{"host": HOST, "port": PORT}],
        http_auth=(USER, PASSWORD),
        use_ssl=False,
        verify_certs=False,  # Not relevant when use_ssl is False
        ssl_assert_hostname=False,  # Not relevant when use_ssl is False
    )

    try:
        logger.info(f"Indexing document with ID '{source_doc_id}' into index '{INDEX_NAME}'...")
        response = client.index(index=INDEX_NAME, body=document_body, id=source_doc_id)
        logger.info("\nSUCCESS! Document indexed successfully")
        logger.info(response)

    except Exception as e:
        logger.error("\nERROR: An exception occurred while trying to index the document", e)


if __name__ == "__main__":
    main()
