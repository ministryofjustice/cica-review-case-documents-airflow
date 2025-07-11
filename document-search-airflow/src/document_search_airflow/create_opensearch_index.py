import os

from dotenv import load_dotenv
from opensearchpy import OpenSearch
from sentence_transformers import SentenceTransformer

# --- Configuration ---
load_dotenv()
DOMAIN_NAME = os.getenv("DOMAIN_NAME")
AWS_REGION = os.getenv("AWS_REGION")
OPENSEARCH_PORT = os.getenv("OPENSEARCH_PORT")
INDEX_NAME = os.getenv("INDEX_NAME")
OPENSEARCH_HOST = f"{DOMAIN_NAME}.{AWS_REGION}.opensearch.localhost.localstack.cloud"
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME")

# --- Initialize SentenceTransformer to get embedding dimension ---
print(f"Loading SentenceTransformer model: {EMBEDDING_MODEL_NAME}...")
try:
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    EMBEDDING_DIM = model.encode(["Sample sentence"])[0].shape[0]
    print(f"Embedding dimension determined: {EMBEDDING_DIM}")
except Exception as e:
    print(f"Error loading SentenceTransformer model: {e}")
    print(
        "Please ensure you have an internet connection or the model is cached locally."
    )
    exit(1)

# --- OpenSearch Client Configuration ---
# For a local OpenSearch instance, typically you'd use HTTP and basic auth.
# If you are using AWS OpenSearch Service, you would need AWS4Auth.
# For simplicity with a local docker-compose setup, we'll use basic auth.
auth = (OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)
client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
    http_auth=auth,
    http_compress=True,  # enables gzip compression for request bodies
    use_ssl=True,  # Use SSL for local OpenSearch, usually self-signed
    verify_certs=False,  # Do not verify certs for local self-signed certs
    ssl_assert_hostname=False,
    ssl_show_warn=False,
)

# --- Create the index ---
# Set the onfiguration for the index (settings and mappings)
index_body = {
    "settings": {"index": {"knn": True, "knn.algo_param.ef_search": 100}},
    "mappings": {
        "properties": {
            "embedding": {
                "type": "knn_vector",
                "dimension": EMBEDDING_DIM,
                "method": {
                    "name": "hnsw",
                    "space_type": "l2",
                    "engine": "faiss",
                    "parameters": {"ef_construction": 128, "m": 24},
                },
            },
            "page_number": {"type": "integer"},  # Better for range filtering
            "chunk_text": {"type": "text"},
            "file_name": {"type": "keyword"},
            "chunk_index": {"type": "integer"},
        }
    },
}

print(f"Checking if index '{INDEX_NAME}' already exists...")
if client.indices.exists(index=INDEX_NAME):
    print(f"Index '{INDEX_NAME}' already exists. Deleting and recreating...")
    try:
        client.indices.delete(index=INDEX_NAME)
        print(f"Index '{INDEX_NAME}' deleted successfully.")
    except Exception as e:
        print(f"Error deleting index '{INDEX_NAME}': {e}")
        exit(1)

print(f"Creating index '{INDEX_NAME}'")
try:
    response = client.indices.create(index=INDEX_NAME, body=index_body)
    print("Index creation response:")
    print(response)
    if response.get("acknowledged"):
        print(f"Index '{INDEX_NAME}' created successfully!")
    else:
        print(f"Failed to create index '{INDEX_NAME}'. Response: {response}")
        exit(1)
except Exception as e:
    print(f"Error creating index '{INDEX_NAME}': {e}")
    print("Please ensure your OpenSearch instance is running and accessible.")
    exit(1)
