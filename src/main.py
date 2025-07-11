import json
import logging
import sys

import urllib3  # Import urllib3
from opensearchpy import OpenSearch
from sentence_transformers import SentenceTransformer

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

# Suppress InsecureRequestWarning for unverified HTTPS requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Configuration ---
# OpenSearch connection details for LocalStack
# IMPORTANT: In a production environment, avoid hardcoding credentials.
# Use environment variables or a secure secrets management solution.
OPENSEARCH_HOST = (
    "case-document-search-domain.eu-west-2.opensearch.localhost.localstack.cloud"
)
OPENSEARCH_PORT = 4566
OPENSEARCH_USERNAME = "admin"
OPENSEARCH_PASSWORD = "really-secure-passwordAa!1"  # As provided in your curl command
OPENSEARCH_INDEX_NAME = "case-documents"

# Embedding model name
MODEL_NAME = "all-MiniLM-L6-v2"

# --- Initialize Embedding Model ---
try:
    # print(f"Loading SentenceTransformer model: {MODEL_NAME}...")
    logging.info(f"Loading SentenceTransformer model: {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    logging.info("Model loaded successfully.")
except Exception as e:
    logging.info(f"Error loading model: {e}")
    exit(1)


# --- Initialize OpenSearch Client ---
def get_opensearch_client():
    """
    Initializes and returns an OpenSearch client.
    For LocalStack, we use HTTP (not HTTPS) and basic auth.
    """
    try:
        client = OpenSearch(
            hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
            http_auth=(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),
            use_ssl=False,  # Changed to False for LocalStack HTTP connection
            verify_certs=False,  # Disable certificate verification
            ssl_show_warn=False,  # Disable SSL warnings
            timeout=30,
        )
        logging.info("OpenSearch client initialized.")
        return client
    except Exception as e:
        logging.info(f"Error initializing OpenSearch client: {e}")
        exit(1)


# --- Embedding and Indexing Function ---
def embed_and_index_paragraph(client, index_name, paragraph_text, metadata):
    """
    Embeds a paragraph of text and indexes it into OpenSearch.
    """
    try:
        logging.info(f"Embedding text: '{paragraph_text[:50]}...'")
        embedding = model.encode(
            paragraph_text
        ).tolist()  # Convert numpy array to list for JSON serialization
        logging.info("Text embedded successfully.")

        document = {
            "chunk_text": paragraph_text,
            "embedding": embedding,
            **metadata,  # Unpack additional metadata
        }

        logging.info(f"Indexing document into '{index_name}'...")
        response = client.index(
            index=index_name,
            body=document,
            id=metadata.get(
                "chunk_id"
            ),  # Use chunk_id as OpenSearch document ID for idempotency
        )
        logging.info(f"Indexing response: {json.dumps(response, indent=2)}")
        if response.get("result") in ["created", "updated"]:
            logging.info(
                f"Document indexed successfully with ID: {response.get('_id')}"
            )
        else:
            logging.info(f"Failed to index document. Result: {response.get('result')}")

    except Exception as e:
        logging.info(f"Error embedding or indexing document: {e}")
        # Add failures to a DLQ


# --- Main Execution ---
if __name__ == "__main__":
    opensearch_client = get_opensearch_client()

    sample_paragraph = (
        "This is a sample paragraph of text that we want to embed and store in "
        "OpenSearch. "
        "It contains information that could be useful for semantic search later on. "
        "The model 'all-MiniLM-L6-v2' will convert this text into a dense vector "
        "representation."
    )

    sample_metadata = {
        "s3_uri": "s3://my-bucket/documents/doc1.pdf",
        "case_ref": "25/771234",
        "correspondence_type": "TC19",
        "page_count": 10,
        "page_number": 1,
        "chunk_id": "doc1_page1_chunk1",
        "received_date": "2023-01-15 10:30:00",
    }

    embed_and_index_paragraph(
        opensearch_client, OPENSEARCH_INDEX_NAME, sample_paragraph, sample_metadata
    )

    # You can add more paragraphs with different metadata here
    # For example:
    # another_paragraph = "Another text to demonstrate indexing multiple documents."
    # another_metadata = {
    #     "s3_uri": "s3://my-bucket/documents/doc1.pdf",
    #     "case_ref": "CASE-2023-001",
    #     "correspondence_type": "Letter",
    #     "page_count": 10,
    #     "page_number": 2,
    #     "chunk_id": "doc1_page2_chunk1",
    #     "received_date": "2023-01-16 11:00:00"
    # }
    # embed_and_index_paragraph(opensearch_client,
    # OPENSEARCH_INDEX_NAME, another_paragraph, another_metadata)

    logging.info("\nScript finished.")
