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

# --- Create the index ---
index_body = {"settings": {"index": {"number_of_shards": 4}}}
print(f"Checking if index '{index_name}' already exists...")
if client.indices.exists(index=index_name):
    print(f"Index '{index_name}' already exists. Deleting and recreating...")
    try:
        client.indices.delete(index=index_name)
        print(f"Index '{index_name}' deleted successfully.")
    except Exception as e:
        print(f"Error deleting index '{index_name}': {e}")
        exit(1)

print(f"Creating index '{index_name}'")
try:
    response = client.indices.create(index=index_name, body=index_body)
    print("Index creation response:")
    print(response)
    if response.get("acknowledged"):
        print(f"Index '{index_name}' created successfully!")
    else:
        print(f"Failed to create index '{index_name}'. Response: {response}")
        exit(1)
except Exception as e:
    print(f"Error creating index '{index_name}': {e}")
    print("Please ensure your OpenSearch instance is running and accessible.")
    exit(1)
