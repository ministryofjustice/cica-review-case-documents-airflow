# create_opensearch_index.py

from sentence_transformers import SentenceTransformer
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
import os

# --- Configuration ---
MODEL_NAME = "all-MiniLM-L6-v2"
INDEX_NAME = "documents"
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", 9200))
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin") # Default for local OpenSearch
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin") # Default for local OpenSearch

# --- Initialize SentenceTransformer to get embedding dimension ---
print(f"Loading SentenceTransformer model: {MODEL_NAME}...")
try:
    model = SentenceTransformer(MODEL_NAME)
    EMBEDDING_DIM = model.encode(["Sample sentence"])[0].shape[0]
    print(f"Embedding dimension determined: {EMBEDDING_DIM}")
except Exception as e:
    print(f"Error loading SentenceTransformer model: {e}")
    print("Please ensure you have an internet connection or the model is cached locally.")
    exit(1)

# --- OpenSearch Client Configuration ---
# For a local OpenSearch instance, typically you'd use HTTP and basic auth.
# If you are using AWS OpenSearch Service, you would need AWS4Auth.
# For simplicity with a local docker-compose setup, we'll use basic auth.
auth = (OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)
client = OpenSearch(
    hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
    http_auth=auth,
    use_ssl=True, # Use SSL for local OpenSearch, usually self-signed
    verify_certs=False, # Do not verify certs for local self-signed certs
    ssl_assert_hostname=False,
    ssl_show_warn=False,
    connection_class=RequestsHttpConnection
)

# --- Define the index body ---
index_body = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 100
        }
    },
    "mappings": {
        "properties": {
            "embedding": {
                "type": "knn_vector",
                "dimension": EMBEDDING_DIM,
                "method": {
                    "name": "hnsw",
                    "space_type": "l2",
                    "engine": "nmslib",
                    "parameters": {
                        "ef_construction": 128,
                        "m": 24
                    }
                }
            },
            # You can add other fields here if needed, e.g., for movie metadata
            "title": {"type": "text"},
            "genre": {"type": "keyword"}
        }
    }
}

# --- Create the index ---
print(f"Checking if index '{INDEX_NAME}' already exists...")
if client.indices.exists(index=INDEX_NAME):
    print(f"Index '{INDEX_NAME}' already exists. Deleting and recreating...")
    try:
        client.indices.delete(index=INDEX_NAME)
        print(f"Index '{INDEX_NAME}' deleted successfully.")
    except Exception as e:
        print(f"Error deleting index '{INDEX_NAME}': {e}")
        exit(1)

print(f"Creating index '{INDEX_NAME}' with embedding dimension {EMBEDDING_DIM}...")
try:
    response = client.indices.create(index=INDEX_NAME, body=index_body)
    print("Index creation response:")
    print(response)
    if response.get('acknowledged'):
        print(f"Index '{INDEX_NAME}' created successfully!")
    else:
        print(f"Failed to create index '{INDEX_NAME}'. Response: {response}")
        exit(1)
except Exception as e:
    print(f"Error creating index '{INDEX_NAME}': {e}")
    print("Please ensure your OpenSearch instance is running and accessible.")
    exit(1)

