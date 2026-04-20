#!/bin/bash
set -euo pipefail

echo "Starting Bedrock dense-vector setup..."

OPENSEARCH_ENDPOINT="http://opensearch:9200"
INDEX_NAME="page_chunks"

BEDROCK_REGION="${AWS_REGION:-eu-west-2}"
BEDROCK_MODEL_ID="amazon.titan-embed-text-v2:0"

INGEST_PIPELINE_NAME="bedrock-dense-ingest"
SEARCH_PIPELINE_NAME="bedrock-dense-search"

# ------------------------------------------------------------
# Load AWS credentials (LocalStack pattern)
# ------------------------------------------------------------
if [ -f /etc/localstack/.env ]; then
  export $(grep -v '^#' /etc/localstack/.env | grep -v '^$' | sed 's/#.*//' | xargs)
fi

if [ -z "${AWS_MOD_PLATFORM_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY:-}" ]; then
  echo "AWS credentials not found; skipping Bedrock setup."
  exit 0
fi

# ------------------------------------------------------------
# Wait for OpenSearch and index
# ------------------------------------------------------------
echo "Waiting for OpenSearch and index ${INDEX_NAME}..."
until curl -sf "${OPENSEARCH_ENDPOINT}/${INDEX_NAME}" > /dev/null; do
  sleep 5
done
echo "Index ready."

# ------------------------------------------------------------
# ML Commons cluster settings
# ------------------------------------------------------------
echo "Configuring ML Commons settings..."
curl -s -XPUT "${OPENSEARCH_ENDPOINT}/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{
    "persistent": {
      "plugins.ml_commons.only_run_on_ml_node": false,
      "plugins.ml_commons.allow_registering_model_via_url": true,
      "plugins.ml_commons.native_memory_threshold": 99,
      "plugins.ml_commons.trusted_connector_endpoints_regex": [".*"]
    }
  }' > /dev/null

# ------------------------------------------------------------
# Create Bedrock connector
# ------------------------------------------------------------
echo "Creating Bedrock connector..."
CONNECTOR_RESPONSE=$(curl -s -XPOST \
  "${OPENSEARCH_ENDPOINT}/_plugins/_ml/connectors/_create" \
  -H 'Content-Type: application/json' \
  -d "{
    \"name\": \"bedrock-titan-v2-connector\",
    \"description\": \"Titan Embed Text v2 (1024 dims)\",
    \"version\": 1,
    \"protocol\": \"aws_sigv4\",
    \"parameters\": {
      \"region\": \"${BEDROCK_REGION}\",
      \"service_name\": \"bedrock\"
    },
    \"credential\": {
      \"access_key\": \"${AWS_MOD_PLATFORM_ACCESS_KEY_ID}\",
      \"secret_key\": \"${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY}\",
      \"session_token\": \"${AWS_MOD_PLATFORM_SESSION_TOKEN}\"
    },
    \"actions\": [
      {
        \"action_type\": \"predict\",
        \"method\": \"POST\",
        \"url\": \"https://bedrock-runtime.${BEDROCK_REGION}.amazonaws.com/model/${BEDROCK_MODEL_ID}/invoke\",
        \"headers\": {
          \"content-type\": \"application/json\"
        },
        \"request_body\": \"{ \\\"inputText\\\": \\\"\${parameters.inputText}\\\", \\\"dimensions\\\": 1024, \\\"normalize\\\": true }\",
        \"pre_process_function\": \"connector.pre_process.bedrock.embedding\",
        \"post_process_function\": \"connector.post_process.bedrock.embedding\"
      }
    ]
  }")

CONNECTOR_ID=$(echo "$CONNECTOR_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('connector_id',''))")
if [ -z "${CONNECTOR_ID}" ]; then
  echo "Error: Failed to create Bedrock connector. Response: $CONNECTOR_RESPONSE"
  exit 1
fi
echo "Connector ID: ${CONNECTOR_ID}"

# ------------------------------------------------------------
# Register model
# ------------------------------------------------------------
echo "Registering Bedrock model..."
REGISTER_RESPONSE=$(curl -s -XPOST \
  "${OPENSEARCH_ENDPOINT}/_plugins/_ml/models/_register" \
  -H 'Content-Type: application/json' \
  -d "{
    \"name\": \"bedrock-titan-embed-text-v2\",
    \"function_name\": \"remote\",
    \"description\": \"Titan v2 dense embeddings\",
    \"connector_id\": \"${CONNECTOR_ID}\"
  }")

TASK_ID=$(echo "$REGISTER_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('task_id',''))")
if [ -z "${TASK_ID}" ]; then
  echo "Error: Failed to register model. Response: $REGISTER_RESPONSE"
  exit 1
fi

echo "Waiting for model registration..."
MODEL_ID=""
until [ -n "$MODEL_ID" ]; do
  TASK_STATUS=$(curl -s "${OPENSEARCH_ENDPOINT}/_plugins/_ml/tasks/${TASK_ID}")
  STATE=$(echo "$TASK_STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',''))")
  if [ "$STATE" = "COMPLETED" ]; then
    MODEL_ID=$(echo "$TASK_STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('model_id',''))")
  elif [ "$STATE" = "FAILED" ]; then
    echo "Model registration failed"
    exit 1
  fi
  sleep 2
done

echo "Model ID: ${MODEL_ID}"

# ------------------------------------------------------------
# Deploy model
# ------------------------------------------------------------
echo "Deploying model..."
DEPLOY_TASK=$(curl -s -XPOST \
  "${OPENSEARCH_ENDPOINT}/_plugins/_ml/models/${MODEL_ID}/_deploy" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('task_id',''))")

DEPLOY_TIMEOUT=60
DEPLOY_COUNT=0
until curl -s "${OPENSEARCH_ENDPOINT}/_plugins/_ml/tasks/${DEPLOY_TASK}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('state')=='COMPLETED' else 1)"; do
  DEPLOY_COUNT=$((DEPLOY_COUNT + 1))
  if [ $DEPLOY_COUNT -ge $DEPLOY_TIMEOUT ]; then
    echo "Error: Model deployment timed out"
    exit 1
  fi
  sleep 2
done

echo "Model deployed."

# ------------------------------------------------------------
# Ingest pipeline (index-time embeddings)
# ------------------------------------------------------------
echo "Creating ingest pipeline..."
curl -s -XPUT \
  "${OPENSEARCH_ENDPOINT}/_ingest/pipeline/${INGEST_PIPELINE_NAME}" \
  -H 'Content-Type: application/json' \
  -d "{
    \"description\": \"Ingest-time dense embedding with Titan v2\",
    \"processors\": [
      {
        \"text_embedding\": {
          \"model_id\": \"${MODEL_ID}\",
          \"field_map\": {
            \"chunk_text\": \"embedding\"
          }
        }
      }
    ]
  }" > /dev/null

# ------------------------------------------------------------
# Search pipeline (query-time embeddings)
# ------------------------------------------------------------
echo "Creating search pipeline..."
curl -s -XPUT \
  "${OPENSEARCH_ENDPOINT}/_search/pipeline/${SEARCH_PIPELINE_NAME}" \
  -H 'Content-Type: application/json' \
  -d "{
    \"description\": \"Query-time embedding with Titan v2\",
    \"processors\": [
      {
        \"inference\": {
          \"model_id\": \"${MODEL_ID}\",
          \"input_map\": {
            \"inputText\": \"query_text\"
          },
          \"output_map\": {
            \"embedding\": \"query_embedding\"
          }
        }
      }
    ]
  }" > /dev/null

# ------------------------------------------------------------
# Attach pipelines to index
# ------------------------------------------------------------
echo "Attaching ingest pipeline to index..."
curl -s -XPUT \
  "${OPENSEARCH_ENDPOINT}/${INDEX_NAME}/_settings" \
  -H 'Content-Type: application/json' \
  -d "{
    \"index\": {
      \"default_pipeline\": \"${INGEST_PIPELINE_NAME}\"
    }
  }" > /dev/null

echo "✅ Bedrock dense-vector setup complete."
