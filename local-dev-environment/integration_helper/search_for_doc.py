"""Search for similar documents in a LocalStack OpenSearch index using k-NN.

It is not intended for production use.
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

# --- 1. CONFIGURE YOUR RUNNING LOCALSTACK OPENSEARCH CONNECTION ---
# These values should match your LocalStack setup
HOST = "localhost"
PORT = 9200
USER = "admin"
PASSWORD = "really-secure-passwordAa!1"
INDEX_NAME = "case-documents"


# --- 2. DEFINE YOUR K-NN SEARCH QUERY ---
def create_knn_query(query_vector, k=5):
    """Creates the body for a k-NN search query."""
    return {
        "size": k,
        "_source": ["source_doc_id", "page_number", "chunk_text", "case_ref"],
        "query": {"knn": {"embedding": {"vector": query_vector, "k": k}}},
    }


# --- 3. EXECUTE THE SEARCH AND PRINT RESULTS ---
def main():
    """Search for similar documents in the OpenSearch index."""
    logger.info("Connecting to LocalStack OpenSearch...")
    # Create the client instance for LocalStack
    client = OpenSearch(
        hosts=[{"host": HOST, "port": PORT}],
        http_auth=(USER, PASSWORD),
        use_ssl=False,
        verify_certs=False,
        ssl_assert_hostname=False,
    )

    # --- Generate a sample query vector ---
    # In a real application, you would generate this vector from your ML model
    # based on the user's search query, e.g., "geotechnical survey near the River Clyde".
    # For this example, we'll create a random 1024-dimension vector.
    logger.info("Using the same vector as the put_doc.py file for search query...")
    query_vector = embedding_example_1024

    # --- Create and execute the search query ---
    k_neighbors = 5
    search_query = create_knn_query(query_vector, k=k_neighbors)

    try:
        logger.info(f"\nPerforming k-NN search for {k_neighbors} nearest neighbors in index '{INDEX_NAME}'...")

        response = client.search(index=INDEX_NAME, body=search_query)

        # --- Process and display the results ---
        hits = response["hits"]["hits"]

        if not hits:
            logger.info("\nNo similar documents found.")
        else:
            logger.info(f"\n--- Found {len(hits)} similar documents in CICA case files ---")
            for i, hit in enumerate(hits):
                score = hit["_score"]
                source = hit["_source"]
                logger.info(f"\nResult {i + 1} (Score: {score:.4f}):")
                logger.info(f"  Case Ref:     {source.get('case_ref', 'N/A')}")
                logger.info(f"  Document ID:  {source.get('source_doc_id', 'N/A')}")
                logger.info(f"  Page:         {source.get('page_number', 'N/A')}")
                # Print a snippet of the chunk text
                text_snippet = source.get("chunk_text", "")
                logger.info(f'  Text:         "{text_snippet[:100]}..."')

    except Exception as e:
        logger.error(f"\nERROR: An exception occurred during the search: {e}")


if __name__ == "__main__":
    main()
