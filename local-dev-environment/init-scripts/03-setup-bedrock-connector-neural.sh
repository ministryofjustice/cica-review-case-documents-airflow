#!/bin/bash
set -euo pipefail

echo "Starting Bedrock connector setup..."
echo "[03] init-scripts/03-setup-bedrock-connector-neural.sh starting"

if [ -f /tmp/aws_resources_failed ]; then
  echo "INFO: Detected /tmp/aws_resources_failed. Skipping Bedrock connector setup."
  exit 0
fi

# This script configures OpenSearch ML Commons to call Amazon Bedrock Titan Embed Text v2
# when documents are indexed into page_chunks, so embeddings are generated automatically
# without a separate client-side Bedrock call.
#
# It is a separate init script from 02-create-opensearch-resources.sh so that
# Bedrock-specific configuration is isolated. Init scripts are numbered to make
# execution order explicit: this file (03-*) runs after 02-create-opensearch-resources.sh,
# so the page_chunks index is guaranteed to exist before this script runs.

DIRECT_OPENSEARCH_ENDPOINT="http://opensearch:9200"
BEDROCK_READY_SENTINEL="/tmp/bedrock_connector_ready"
BEDROCK_FAILED_SENTINEL="/tmp/bedrock_connector_failed"

mark_bedrock_setup_failed() {
  touch "${BEDROCK_FAILED_SENTINEL}"
}

mark_bedrock_setup_successful() {
  touch "${BEDROCK_READY_SENTINEL}"
  rm -f "${BEDROCK_FAILED_SENTINEL}"
}

# Reset any stale sentinel files from previous runs.
rm -f "${BEDROCK_READY_SENTINEL}" "${BEDROCK_FAILED_SENTINEL}"
trap mark_bedrock_setup_failed ERR

# Load environment variables for AWS credentials (same pattern as create-aws-resources.sh)
if [ -f /etc/localstack/.env ]; then
  export $(grep -v '^#' /etc/localstack/.env | grep -v '^$' | sed 's/#.*//' | xargs)
fi

BEDROCK_REGION="${AWS_REGION:-eu-west-2}"
BEDROCK_EMBED_MODEL="amazon.titan-embed-text-v2:0"
BEDROCK_CONNECTOR_NAME="bedrock-titan-embed-connector"
BEDROCK_MODEL_NAME="bedrock-titan-embed-text-v2"
BEDROCK_PIPELINE_NAME="bedrock-embedding-pipeline"
BEDROCK_SEARCH_PIPELINE_NAME="bedrock-neural-search-pipeline"
BEDROCK_ENABLE_INGEST_PIPELINE="${BEDROCK_ENABLE_INGEST_PIPELINE:-false}"

if [ -z "${AWS_MOD_PLATFORM_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY:-}" ]; then
  echo "WARNING: AWS credentials not found. Skipping Bedrock connector setup."
  exit 0
fi

extract_json_field() {
  echo "$1" | grep -o "\"$2\":\"[^\"]*\"" | head -n1 | cut -d'"' -f4 || true
}

get_connector_id_by_name() {
  SEARCH_RESPONSE=$(curl -s -XPOST "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/connectors/_search" \
    -H 'Content-Type: application/json' \
    --data-binary @- <<EOF
{
  "size": 1,
  "query": {
    "match_phrase": {
      "name": "${BEDROCK_CONNECTOR_NAME}"
    }
  }
}
EOF
)
  extract_json_field "${SEARCH_RESPONSE}" "_id"
}

create_connector() {
  echo "Creating Bedrock ML connector..." >&2

  if [ -n "${AWS_MOD_PLATFORM_SESSION_TOKEN:-}" ]; then
    CONNECTOR_CREDENTIAL_JSON=$(cat <<EOF
  "credential": {
    "access_key": "${AWS_MOD_PLATFORM_ACCESS_KEY_ID}",
    "secret_key": "${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY}",
    "session_token": "${AWS_MOD_PLATFORM_SESSION_TOKEN}"
  },
EOF
)
  else
    CONNECTOR_CREDENTIAL_JSON=$(cat <<EOF
  "credential": {
    "access_key": "${AWS_MOD_PLATFORM_ACCESS_KEY_ID}",
    "secret_key": "${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY}"
  },
EOF
)
  fi

  CONNECTOR_RESPONSE=$(curl -s -XPOST "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/connectors/_create" \
    -H 'Content-Type: application/json' \
    --data-binary @- <<EOF
{
  "name": "${BEDROCK_CONNECTOR_NAME}",
  "description": "Remote connector to Amazon Bedrock Titan Embed Text v2 (1024 dimensions)",
  "version": 1,
  "protocol": "aws_sigv4",
  "parameters": {
    "region": "${BEDROCK_REGION}",
    "service_name": "bedrock"
  },
${CONNECTOR_CREDENTIAL_JSON}
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
  echo "Connector response: ${CONNECTOR_RESPONSE}" >&2
  CONNECTOR_ID=$(extract_json_field "${CONNECTOR_RESPONSE}" "connector_id")
  if [ -z "${CONNECTOR_ID}" ]; then
    echo "Error: Failed to create Bedrock connector." >&2
    exit 1
  fi

  echo "${CONNECTOR_ID}"
}

get_model_id_by_name() {
  SEARCH_RESPONSE=$(curl -s -XPOST "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/models/_search" \
    -H 'Content-Type: application/json' \
    --data-binary @- <<EOF
{
  "size": 1,
  "query": {
    "match_phrase": {
      "name": "${BEDROCK_MODEL_NAME}"
    }
  }
}
EOF
)
  extract_json_field "${SEARCH_RESPONSE}" "_id"
}

wait_for_task_completion() {
  TASK_ID="$1"
  ACTION_LABEL="$2"

  for attempt in $(seq 1 30); do
    TASK_RESPONSE=$(curl -s "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/tasks/${TASK_ID}")
    TASK_STATE=$(extract_json_field "${TASK_RESPONSE}" "state")

    if [ "${TASK_STATE}" = "COMPLETED" ]; then
      echo "${TASK_RESPONSE}"
      return 0
    fi

    if [ "${TASK_STATE}" = "FAILED" ]; then
      echo "Error: ${ACTION_LABEL} failed. Response: ${TASK_RESPONSE}" >&2
      exit 1
    fi

    echo -n "." >&2
    sleep 3
  done

  echo "Error: ${ACTION_LABEL} timed out." >&2
  exit 1
}

register_model() {
  CONNECTOR_ID="$1"

  echo "Registering Bedrock embedding model..." >&2
  REGISTER_RESPONSE=$(curl -s -XPOST "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/models/_register" \
    -H 'Content-Type: application/json' \
    --data-binary @- <<EOF
{
  "name": "${BEDROCK_MODEL_NAME}",
  "function_name": "remote",
  "description": "Amazon Bedrock Titan Embed Text v2 — used for page_chunks automatic embedding",
  "connector_id": "${CONNECTOR_ID}"
}
EOF
)
  echo "Register model response: ${REGISTER_RESPONSE}" >&2
  REGISTER_TASK_ID=$(extract_json_field "${REGISTER_RESPONSE}" "task_id")
  if [ -z "${REGISTER_TASK_ID}" ]; then
    echo "Error: Failed to get model registration task ID." >&2
    exit 1
  fi

  echo "Waiting for model registration task ${REGISTER_TASK_ID} to complete..." >&2
  TASK_RESPONSE=$(wait_for_task_completion "${REGISTER_TASK_ID}" "Model registration")
  MODEL_ID=$(extract_json_field "${TASK_RESPONSE}" "model_id")
  if [ -z "${MODEL_ID}" ]; then
    echo "Error: Model registration completed without a model ID." >&2
    exit 1
  fi

  echo "Model registered with ID: ${MODEL_ID}" >&2
  echo "${MODEL_ID}"
}

deploy_model_if_needed() {
  MODEL_ID="$1"
  MODEL_RESPONSE=$(curl -s "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/models/${MODEL_ID}")
  MODEL_STATE=$(extract_json_field "${MODEL_RESPONSE}" "model_state")

  if [ "${MODEL_STATE}" = "DEPLOYED" ]; then
    echo "Model ${MODEL_ID} is already deployed."
    return 0
  fi

  echo "Deploying Bedrock embedding model ${MODEL_ID}..."
  DEPLOY_RESPONSE=$(curl -s -XPOST "${DIRECT_OPENSEARCH_ENDPOINT}/_plugins/_ml/models/${MODEL_ID}/_deploy")
  DEPLOY_TASK_ID=$(extract_json_field "${DEPLOY_RESPONSE}" "task_id")
  if [ -z "${DEPLOY_TASK_ID}" ]; then
    echo "Error: Failed to start model deployment. Response: ${DEPLOY_RESPONSE}"
    exit 1
  fi

  echo "Waiting for model deployment task ${DEPLOY_TASK_ID} to complete..."
  wait_for_task_completion "${DEPLOY_TASK_ID}" "Model deployment" > /dev/null
  echo "Model deployed successfully."
}

upsert_ingest_pipeline() {
  MODEL_ID="$1"

  echo "Upserting ingest pipeline '${BEDROCK_PIPELINE_NAME}'..."
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
    echo "Ingest pipeline '${BEDROCK_PIPELINE_NAME}' is configured."
  else
    echo "Error: Failed to create ingest pipeline. Response: ${PIPELINE_RESPONSE}"
    exit 1
  fi
}

upsert_search_pipeline() {
  MODEL_ID="$1"

  echo "Upserting search pipeline '${BEDROCK_SEARCH_PIPELINE_NAME}'..."
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
  ],
  "phase_results_processors": [
    {
      "normalization-processor": {
        "normalization": {
          "technique": "min_max"
        },
        "combination": {
          "technique": "arithmetic_mean",
          "parameters": {
            "weights": [0.6, 0.2, 0.2]
          }
        }
      }
    }
  ]
}
EOF
)
  if echo "${SEARCH_PIPELINE_RESPONSE}" | grep -q '"acknowledged":true'; then
    echo "Search pipeline '${BEDROCK_SEARCH_PIPELINE_NAME}' is configured."
  else
    echo "Error: Failed to create search pipeline. Response: ${SEARCH_PIPELINE_RESPONSE}"
    exit 1
  fi
}

set_index_default_pipelines() {
  ENABLE_INGEST_PIPELINE="$1"

  echo "Setting default pipelines on page_chunks index..."
  if [ "${ENABLE_INGEST_PIPELINE}" = "true" ]; then
    UPDATE_RESPONSE=$(curl -s -XPUT "${DIRECT_OPENSEARCH_ENDPOINT}/page_chunks/_settings" \
      -H 'Content-Type: application/json' \
      -d "{
        \"index\": {
          \"default_pipeline\": \"${BEDROCK_PIPELINE_NAME}\",
          \"search.default_pipeline\": \"${BEDROCK_SEARCH_PIPELINE_NAME}\"
        }
      }")
  else
    UPDATE_RESPONSE=$(curl -s -XPUT "${DIRECT_OPENSEARCH_ENDPOINT}/page_chunks/_settings" \
      -H 'Content-Type: application/json' \
      -d "{
        \"index\": {
          \"default_pipeline\": \"_none\",
          \"search.default_pipeline\": \"${BEDROCK_SEARCH_PIPELINE_NAME}\"
        }
      }")
  fi

  if echo "${UPDATE_RESPONSE}" | grep -q '"acknowledged":true'; then
    echo "page_chunks index configured with ingest and search pipelines."
  else
    echo "Error: Failed to update page_chunks settings. Response: ${UPDATE_RESPONSE}"
    exit 1
  fi
}

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

# --- Step 3: Create or reuse the connector and model ---
CONNECTOR_ID="$(get_connector_id_by_name)"
if [ -z "${CONNECTOR_ID}" ]; then
  CONNECTOR_ID="$(create_connector)"
  echo "Bedrock connector created with ID: ${CONNECTOR_ID}"
else
  echo "Reusing Bedrock connector with ID: ${CONNECTOR_ID}"
fi

MODEL_ID="$(get_model_id_by_name)"
if [ -z "${MODEL_ID}" ]; then
  MODEL_ID="$(register_model "${CONNECTOR_ID}")"
else
  echo "Reusing Bedrock model with ID: ${MODEL_ID}"
fi

# --- Step 4: Ensure the model and pipelines are configured ---
# default_pipeline:        auto-embeds chunk_text at index time
# default_search_pipeline: injects model_id into neural queries at search time
deploy_model_if_needed "${MODEL_ID}"
# Toggle ingest-time embedding via BEDROCK_ENABLE_INGEST_PIPELINE=true|false.
if [ "${BEDROCK_ENABLE_INGEST_PIPELINE}" = "true" ]; then
  upsert_ingest_pipeline "${MODEL_ID}"
else
  echo "Skipping ingest pipeline setup (BEDROCK_ENABLE_INGEST_PIPELINE=${BEDROCK_ENABLE_INGEST_PIPELINE})."
fi
upsert_search_pipeline "${MODEL_ID}"
set_index_default_pipelines "${BEDROCK_ENABLE_INGEST_PIPELINE}"

mark_bedrock_setup_successful
trap - ERR
echo "Bedrock connector setup complete."
