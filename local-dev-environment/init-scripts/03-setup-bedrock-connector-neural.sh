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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./lib/bedrock_connector_common.inc
source "${SCRIPT_DIR}/lib/bedrock_connector_common.inc"

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
BEDROCK_TARGET_INDEX="page_chunks"
BEDROCK_OPENSEARCH_ENDPOINT="${DIRECT_OPENSEARCH_ENDPOINT}"
BEDROCK_AUTH_ARGS=()

if [ -z "${AWS_MOD_PLATFORM_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY:-}" ]; then
  echo "WARNING: AWS credentials not found. Skipping Bedrock connector setup."
  exit 0
fi

if [ -n "${AWS_MOD_PLATFORM_SESSION_TOKEN:-}" ]; then
  BEDROCK_CONNECTOR_CREDENTIAL_BLOCK=$(cat <<EOF
  "credential": {
    "access_key": "${AWS_MOD_PLATFORM_ACCESS_KEY_ID}",
    "secret_key": "${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY}",
    "session_token": "${AWS_MOD_PLATFORM_SESSION_TOKEN}"
  },
EOF
)
else
  BEDROCK_CONNECTOR_CREDENTIAL_BLOCK=$(cat <<EOF
  "credential": {
    "access_key": "${AWS_MOD_PLATFORM_ACCESS_KEY_ID}",
    "secret_key": "${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY}"
  },
EOF
)
fi

BEDROCK_ML_SETTINGS_JSON='{
  "persistent": {
    "plugins.ml_commons.only_run_on_ml_node": false,
    "plugins.ml_commons.allow_registering_model_via_url": true,
    "plugins.ml_commons.native_memory_threshold": 99,
    "plugins.ml_commons.trusted_connector_endpoints_regex": [".*"]
  }
}'

bedrock_wait_for_index "${BEDROCK_TARGET_INDEX}"
bedrock_ensure_ml_settings "${BEDROCK_ML_SETTINGS_JSON}"
MODEL_ID="$(bedrock_prepare_model "${BEDROCK_CONNECTOR_CREDENTIAL_BLOCK}")"

if [ "${BEDROCK_ENABLE_INGEST_PIPELINE}" = "true" ]; then
  bedrock_upsert_ingest_pipeline "${MODEL_ID}"
else
  bedrock_log "Skipping ingest pipeline setup (BEDROCK_ENABLE_INGEST_PIPELINE=${BEDROCK_ENABLE_INGEST_PIPELINE})."
fi
bedrock_upsert_search_pipeline "${MODEL_ID}"
bedrock_set_index_default_pipelines "${BEDROCK_ENABLE_INGEST_PIPELINE}" "${BEDROCK_TARGET_INDEX}"

mark_bedrock_setup_successful
trap - ERR
echo "Bedrock connector setup complete."
