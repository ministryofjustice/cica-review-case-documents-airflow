#!/bin/bash
set -euo pipefail 

echo "Starting LocalStack OpenSearch domain and index setup..."

LOCALSTACK_OPENSEARCH_DOMAIN_NAME="case-document-search-domain"

DIRECT_OPENSEARCH_ENDPOINT="opensearch:9200"
OPENSEARCH_AUTH="admin:really-secure-passwordAa!1" # Credentials for direct OpenSearch access

# --- Step 1: Create the OpenSearch domain within LocalStack ---
# This step tells LocalStack to emulate an OpenSearch domain.
# As OPENSEARCH_CUSTOM_BACKEND is set in docker-compose, this domain
# will point to your 'opensearch' container.
echo "Creating LocalStack OpenSearch domain '${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}'..."
# Check if domain already exists to make script idempotent
if awslocal opensearch describe-domain --domain-name "${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}" 2>/dev/null; then
  echo "LocalStack OpenSearch domain '${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}' already exists."
else
  awslocal opensearch create-domain --cli-input-json file:///etc/localstack/init/ready.d/opensearch_domain.json
  echo "LocalStack OpenSearch domain creation initiated."
fi


# --- Step 2: Wait for the LocalStack-managed domain to become active ---
echo "Waiting for LocalStack OpenSearch domain '${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}' to be active..."
until awslocal opensearch describe-domain --domain-name "${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}" | grep '"Processing": false' > /dev/null; do
  echo -n "."
  sleep 5
done
echo -e "\nLocalStack OpenSearch domain '${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}' is active."


# --- Step 3: Wait for the actual OpenSearch container to be ready ---
# This is crucial as LocalStack's domain being "active" doesn't mean your
# 'opensearch' container is fully initialized and ready for requests.
echo "Waiting for actual OpenSearch container at ${DIRECT_OPENSEARCH_ENDPOINT} to be ready..."
until curl --silent --fail -u "${OPENSEARCH_AUTH}" "http://${DIRECT_OPENSEARCH_ENDPOINT}/_cluster/health" > /dev/null; do
    echo -n "."
    sleep 2
done
echo -e "\nActual OpenSearch container is ready!"

# --- Step 4: Create the index in the actual OpenSearch container ---
INDEX_NAME="case-documents"

# Check if the index already exists to ensure idempotency
if curl --silent --fail -u "${OPENSEARCH_AUTH}" "http://${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" > /dev/null; then
  echo "Index '${INDEX_NAME}' already exists. Skipping creation."
else
  echo "Creating index '${INDEX_NAME}'..."
  CREATE_RESPONSE=$(curl -XPUT -u "${OPENSEARCH_AUTH}" "http://${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" -H 'Content-Type: application/json' -d'
  {
      "settings": {
          "index": {
              "knn": true,
              "knn.algo_param.ef_search": 100
          }
      },
      "mappings": {
          "properties": {
              "embedding": {
                  "type": "knn_vector",
                  "dimension": 384,
                  "method": {
                      "name": "hnsw",
                      "space_type": "l2",
                      "engine": "faiss",
                      "parameters": {
                          "ef_construction": 128,
                          "m": 24
                      }
                  }
              },
              "s3_uri": {"type": "keyword"},
              "case_ref": {"type": "keyword"},
              "correspondence_type": {"type": "keyword"},
              "page_count": {"type": "integer"},
              "page_number": {"type": "integer"},
              "chunk_id": {"type": "keyword"},
              "chunk_index": {"type": "integer"},
              "chunk_text": {"type": "text", "index": false},
              "received_date": {
                  "type": "date",
                  "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||epoch_millis"
              }
          }
      }
  }
  ')

  if echo "${CREATE_RESPONSE}" | grep -q '"acknowledged":true'; then
    echo "Index '${INDEX_NAME}' created successfully."
  else
    echo "Failed to create index '${INDEX_NAME}'. Response: ${CREATE_RESPONSE}"
    exit 1 # Fail the script if index creation wasn't acknowledged
  fi
fi

# --- Step 5: Create a marker file for the LocalStack health check ---
# This signals that all custom initialization steps are complete.
touch /tmp/opensearch_index_ready
echo "LocalStack OpenSearch Domain and Index resources completed."
