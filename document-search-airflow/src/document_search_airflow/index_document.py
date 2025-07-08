import os

from dotenv import load_dotenv
from opensearchpy import OpenSearch

# --- Configuration ---
load_dotenv()
domain_name = os.getenv("DOMAIN_NAME")
aws_region = os.getenv("AWS_REGION")
port = os.getenv("OPENSEARCH_PORT")
index_name = os.getenv("INDEX_NAME")
opensearch_host = f"{domain_name}.{aws_region}.opensearch.localhost.localstack.cloud"
opensearch_username = os.getenv("OPENSEARCH_USERNAME")
opensearch_password = os.getenv("OPENSEARCH_PASSWORD")

# --- OpenSearch Client Configuration ---
# For a local OpenSearch instance, typically you'd use HTTP and basic auth.
# If you are using AWS OpenSearch Service, you would need AWS4Auth.
# For simplicity with a local docker-compose setup, we'll use basic auth.
auth = (opensearch_username, opensearch_password)
client = OpenSearch(
    hosts=[{"host": opensearch_host, "port": port}],
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
print(f"Checking if index '{index_name}' already exists...")
if client.indices.exists(index=index_name):
    print(f"Index '{index_name}' exists.")
    try:
        response = client.index(index=index_name, body=document, id="1", refresh=True)
        print("Document successfully indexed.")
        print(response)
    except Exception as e:
        print(f"Failed to index document: {e}")
        exit(1)
