import os

from dotenv import load_dotenv
from opensearchpy import OpenSearch

# --- Configuration ---
load_dotenv()
DOMAIN_NAME = os.getenv("DOMAIN_NAME")
AWS_REGION = os.getenv("AWS_REGION")
OPENSEARCH_PORT = os.getenv("OPENSEARCH_PORT")
INDEX_NAME = os.getenv("INDEX_NAME")
OPENSEARCH_HOST = f"{DOMAIN_NAME}.{AWS_REGION}.opensearch.localhost.localstack.cloud"
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD")

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

# -- Create a document
document = {"title": "Moneyball", "director": "Bennett Miller", "year": "2011"}

# -- Index a document
print(f"Checking if index '{INDEX_NAME}' already exists...")
if client.indices.exists(index=INDEX_NAME):
    print(f"Index '{INDEX_NAME}' exists.")
    try:
        response = client.index(index=INDEX_NAME, body=document, id="1", refresh=True)
        print("Document successfully indexed.")
        print(response)
    except Exception as e:
        print(f"Failed to index document: {e}")
        exit(1)
