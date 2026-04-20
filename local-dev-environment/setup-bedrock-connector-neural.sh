#!/bin/bash
set -euo pipefail

echo "Starting Bedrock connector setup..."

# This script configures OpenSearch ML Commons to call Amazon Bedrock Titan Embed Text v2
# when documents are indexed into page_chunks, so embeddings are generated automatically
# without a separate client-side Bedrock call.
#
# It is a separate init script from create-opensearch-resources.sh so that
# Bedrock-specific configuration is isolated. LocalStack executes init scripts
# alphabetically, so this file (setup-*) runs after create-* scripts, meaning
# the page_chunks index is guaranteed to exist before this script runs.

DIRECT_OPENSEARCH_ENDPOINT="http://opensearch:9200"

# Load environment variables for AWS credentials (same pattern as create-aws-resources.sh)
if [ -f /etc/localstack/.env ]; then
  export $(grep -v '^#' /etc/localstack/.env | grep -v '^$' | sed 's/#.*//' | xargs)
fi

BEDROCK_REGION="${AWS_REGION:-eu-west-2}"
BEDROCK_EMBED_MODEL="amazon.titan-embed-text-v2:0"
BEDROCK_PIPELINE_NAME="bedrock-embedding-pipeline"
BEDROCK_SEARCH_PIPELINE_NAME="bedrock-neural-search-pipeline"

if [ -z "${AWS_MOD_PLATFORM_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY:-}" ]; then
  echo "WARNING: AWS credentials not found. Skipping Bedrock connector setup."
  exit 0
fi

# --- Step 1: Wait for OpenSearch and the page_chunks index to be ready ---
echo "Waiting for OpenSearch and the page_chunks index to be ready..."
until curl --silent --fail "${DIRECT_OPENSEARCH_ENDPOINT}/page_chunks" > /dev/null; do
  echo -n "."
  sleep 5
done
echo -e "\npage_chunks index is ready."

# --- Step 2: Configure ML Commons cluster settings ---
# Allow a remote connector on the single data node and trust the Bedrock runtime endpoint.
echo "Configuring ML Commons cluster settings..."
curl -s -XPUT "${DIRECT_OPENSEARCH_ENDPOINT}/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{
    "persistent": {
      "plugins.ml_commons.only_run_on_ml_node": false,
      "plugins.ml_commons.allow_registering_model_via_url": true,
      "plugins.ml_commons.native_memory_threshold": 99,
      "plugins.ml_commons.trusted_connector_endpoints_regex": [".*"]
    }
  }' > /dev/null

# --- Step 3: Create connector, model, and ingest pipeline (idempotent) ---
# Check whether the ingest pipeline already exists from a previous run.
if curl --silent --fail "${DIRECT_OPENSEARCH_ENDPOINT}/_ingest/pipeline/${BEDROCK_PIPELINE_NAME}" > /dev/null 2>&1; then
  echo "Bedrock embedding pipeline '${BEDROCK_PIPELINE_NAME}' already exists. Skipping connector setup."
else
  # Create the Bedrock remote connector using AWS SigV4 auth.
  echo "Creating Bedrock ML connector..."
  CONNECTOR_RESPONSE=$(curl -s -XPOST "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/connectors/_create" \
    -H 'Content-Type: application/json' \
    --data-binary @- <<EOF
{
  "name": "bedrock-titan-embed-connector",
  "description": "Remote connector to Amazon Bedrock Titan Embed Text v2 (1024 dimensions)",
  "version": 1,
  "protocol": "aws_sigv4",
  "parameters": {
    "region": "${BEDROCK_REGION}",
    "service_name": "bedrock"
  },
  "credential": {
    "access_key": "${AWS_MOD_PLATFORM_ACCESS_KEY_ID}",
    "secret_key": "${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY}",
    "session_token": "${AWS_MOD_PLATFORM_SESSION_TOKEN}"
  },
  "actions": [
    {
      "action_type": "predict",
      "method": "POST",
      "url": "https://bedrock-runtime.${BEDROCK_REGION}.amazonaws.com/model/${BEDROCK_EMBED_MODEL}/invoke",
      "headers": {
        "content-type": "application/json",
        "x-amz-content-sha256": "required"
      },
      "request_body": "{ \"inputText\": \"\${parameters.inputText}\", \"dimensions\": 1024, \"normalize\": true }",
      "pre_process_function": "connector.pre_process.bedrock.embedding",
      "post_process_function": "connector.post_process.bedrock.embedding"
    }
  ]
}
EOF
)
  echo "Connector response: ${CONNECTOR_RESPONSE}"
  CONNECTOR_ID=$(echo "${CONNECTOR_RESPONSE}" | grep -o '"connector_id":"[^"]*"' | cut -d'"' -f4)
  if [ -z "${CONNECTOR_ID}" ]; then
    echo "Error: Failed to create Bedrock connector."
    exit 1
  fi
  echo "Bedrock connector created with ID: ${CONNECTOR_ID}"

  # Register a remote model backed by the connector.
  echo "Registering Bedrock embedding model..."
  REGISTER_RESPONSE=$(curl -s -XPOST "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/models/_register" \
    -H 'Content-Type: application/json' \
    --data-binary @- <<EOF
{
  "name": "bedrock-titan-embed-text-v2",
  "function_name": "remote",
  "description": "Amazon Bedrock Titan Embed Text v2 — used for page_chunks automatic embedding",
  "connector_id": "${CONNECTOR_ID}"
}
EOF
)
  echo "Register model response: ${REGISTER_RESPONSE}"
  REGISTER_TASK_ID=$(echo "${REGISTER_RESPONSE}" | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4)
  if [ -z "${REGISTER_TASK_ID}" ]; then
    echo "Error: Failed to get model registration task ID."
    exit 1
  fi

  # Poll until model registration completes.
  echo "Waiting for model registration task ${REGISTER_TASK_ID} to complete..."
  MODEL_ID=""
  for attempt in $(seq 1 30); do
    TASK_RESPONSE=$(curl -s "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/tasks/${REGISTER_TASK_ID}")
    TASK_STATE=$(echo "${TASK_RESPONSE}" | grep -o '"state":"[^"]*"' | cut -d'"' -f4)
    if [ "${TASK_STATE}" = "COMPLETED" ]; then
      MODEL_ID=$(echo "${TASK_RESPONSE}" | grep -o '"model_id":"[^"]*"' | cut -d'"' -f4)
      echo "Model registered with ID: ${MODEL_ID}"
      break
    elif [ "${TASK_STATE}" = "FAILED" ]; then
      echo "Error: Model registration failed. Response: ${TASK_RESPONSE}"
      exit 1
    fi
    echo -n "."
    sleep 3
  done
  if [ -z "${MODEL_ID}" ]; then
    echo "Error: Model registration timed out."
    exit 1
  fi

  # Deploy the model so it can serve prediction requests.
  echo "Deploying Bedrock embedding model ${MODEL_ID}..."
  DEPLOY_RESPONSE=$(curl -s -XPOST "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/models/${MODEL_ID}/_deploy")
  DEPLOY_TASK_ID=$(echo "${DEPLOY_RESPONSE}" | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4)
  if [ -z "${DEPLOY_TASK_ID}" ]; then
    echo "Error: Failed to start model deployment. Response: ${DEPLOY_RESPONSE}"
    exit 1
  fi

  # Poll until deployment completes.
  echo "Waiting for model deployment task ${DEPLOY_TASK_ID} to complete..."
  for attempt in $(seq 1 30); do
    DEPLOY_TASK_RESPONSE=$(curl -s "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/tasks/${DEPLOY_TASK_ID}")
    DEPLOY_STATE=$(echo "${DEPLOY_TASK_RESPONSE}" | grep -o '"state":"[^"]*"' | cut -d'"' -f4)
    if [ "${DEPLOY_STATE}" = "COMPLETED" ]; then
      echo "Model deployed successfully."
      break
    elif [ "${DEPLOY_STATE}" = "FAILED" ]; then
      echo "Error: Model deployment failed. Response: ${DEPLOY_TASK_RESPONSE}"
      exit 1
    fi
    echo -n "."
    sleep 3
  done

  # Create an ingest pipeline that maps chunk_text → embedding automatically.
  echo "Creating ingest pipeline '${BEDROCK_PIPELINE_NAME}'..."
  PIPELINE_RESPONSE=$(curl -s -XPUT "${DIRECT_OPENSEARCH_ENDPOINT}/_ingest/pipeline/${BEDROCK_PIPELINE_NAME}" \
    -H 'Content-Type: application/json' \
    --data-binary @- <<EOF
{
  "description": "Automatically generates a 1024-dimension embedding for chunk_text using Amazon Bedrock Titan Embed Text v2",
  "processors": [
    {
      "text_embedding": {
        "model_id": "${MODEL_ID}",
        "field_map": {
          "chunk_text": "embedding"
        }
      }
    }
  ]
}
EOF
)
  if echo "${PIPELINE_RESPONSE}" | grep -q '"acknowledged":true'; then
    echo "Ingest pipeline '${BEDROCK_PIPELINE_NAME}' created successfully."
  else
    echo "Error: Failed to create ingest pipeline. Response: ${PIPELINE_RESPONSE}"
    exit 1
  fi
fi

# --- Step 4: Create the search pipeline so clients don't need to know the model_id ---
# neural_query_enricher injects the model_id into any neural query at search time,
# so the client just sends query_text and OpenSearch handles the embedding call.
SEARCH_PIPELINE_NEEDS_CREATE=true
if curl --silent --fail "${DIRECT_OPENSEARCH_ENDPOINT}/_search/pipeline/${BEDROCK_SEARCH_PIPELINE_NAME}" > /dev/null 2>&1; then
  echo "Search pipeline '${BEDROCK_SEARCH_PIPELINE_NAME}' already exists. Skipping creation."
  SEARCH_PIPELINE_NEEDS_CREATE=false
fi

if [ "${SEARCH_PIPELINE_NEEDS_CREATE}" = "true" ]; then
  echo "Creating search pipeline '${BEDROCK_SEARCH_PIPELINE_NAME}'..."
  SEARCH_PIPELINE_RESPONSE=$(curl -s -XPUT "${DIRECT_OPENSEARCH_ENDPOINT}/_search/pipeline/${BEDROCK_SEARCH_PIPELINE_NAME}" \
    -H 'Content-Type: application/json' \
    --data-binary @- <<EOF
{
  "request_processors": [
    {
      "neural_query_enricher": {
        "default_model_id": "${MODEL_ID}",
        "neural_field_default_id": {
          "embedding": "${MODEL_ID}"
        }
      }
    }
  ]
}
EOF
)
  if echo "${SEARCH_PIPELINE_RESPONSE}" | grep -q '"acknowledged":true'; then
    echo "Search pipeline '${BEDROCK_SEARCH_PIPELINE_NAME}' created successfully."
  else
    echo "Error: Failed to create search pipeline. Response: ${SEARCH_PIPELINE_RESPONSE}"
    exit 1
  fi
fi

# --- Step 5: Set both pipelines as defaults on page_chunks ---
# default_pipeline:        auto-embeds chunk_text at index time
# default_search_pipeline: injects model_id into neural queries at search time
echo "Setting default pipelines on page_chunks index..."
UPDATE_RESPONSE=$(curl -s -XPUT "${DIRECT_OPENSEARCH_ENDPOINT}/page_chunks/_settings" \
  -H 'Content-Type: application/json' \
  -d "{
    \"index\": {
      \"default_pipeline\": \"${BEDROCK_PIPELINE_NAME}\",
      \"search.default_pipeline\": \"${BEDROCK_SEARCH_PIPELINE_NAME}\"
    }
  }")
if echo "${UPDATE_RESPONSE}" | grep -q '"acknowledged":true'; then
  echo "page_chunks index configured with ingest and search pipelines."
else
  echo "Error: Failed to update page_chunks settings. Response: ${UPDATE_RESPONSE}"
  exit 1
fi

echo "Bedrock connector setup complete."
