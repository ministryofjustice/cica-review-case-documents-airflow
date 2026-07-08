#!/bin/bash
set -euo pipefail

echo "Starting OpenSearch index setup..."
echo "[02] init-scripts/02-create-opensearch-resources.sh starting"

if [ -f /tmp/aws_resources_failed ]; then
    echo "INFO: Detected /tmp/aws_resources_failed. Skipping OpenSearch setup."
    exit 0
fi

# With OPENSEARCH_ENDPOINT_STRATEGY=path, LocalStack provides a direct proxy.
# This script now interacts directly with the OpenSearch container, bypassing
# the need to create a LocalStack-managed AWS OpenSearch domain. It is set up
# to allow searches requiring an analyzer and keyword searches from the chunks.
DIRECT_OPENSEARCH_ENDPOINT="${DIRECT_OPENSEARCH_ENDPOINT:-http://opensearch:9200}"

# --- Step 1: Wait for the OpenSearch container to be ready ---
echo "Waiting for OpenSearch container at ${DIRECT_OPENSEARCH_ENDPOINT} to be ready..."
# In the compose file, DISABLE_SECURITY_PLUGIN=true, so we don't need auth.
until curl --silent --fail "${DIRECT_OPENSEARCH_ENDPOINT}/_cluster/health?wait_for_status=yellow" > /dev/null; do
    echo -n "."
    sleep 5
done
echo -e "\nOpenSearch container is ready!"

# Export a common OPENSEARCH_ENDPOINT and source shared template helper
OPENSEARCH_ENDPOINT="${DIRECT_OPENSEARCH_ENDPOINT}"
export OPENSEARCH_ENDPOINT
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/lib/opensearch_templates.inc" ]; then
    # shellcheck source=./lib/opensearch_templates.inc
    source "${SCRIPT_DIR}/lib/opensearch_templates.inc"
else
  echo "ERROR: Missing shared template helper at ${SCRIPT_DIR}/lib/opensearch_templates.inc"
  exit 1
fi
opensearch_apply_templates

# --- Step 2: Create the index directly in the OpenSearch container ---
INDEX_NAME="page_chunks"
# No auth needed due to DISABLE_SECURITY_PLUGIN=true
if curl --silent --fail -I "${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" > /dev/null; then
  echo "Index '${INDEX_NAME}' already exists. Skipping creation."
else
  echo "Creating index '${INDEX_NAME}' from templates..."
  CREATE_RESPONSE=$(curl -s -XPUT "${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" -H 'Content-Type: application/json' --data-binary '{}')
  echo "Index creation response: ${CREATE_RESPONSE}"
  if [[ ! $(echo "${CREATE_RESPONSE}" | grep '"acknowledged":true') ]]; then
    echo "Error: Index creation not acknowledged."
    exit 1
  fi
fi

# --- Create the page index in the OpenSearch container ---
INDEX_NAME="page_metadata"
if curl --silent --fail -I "${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" > /dev/null; then
  echo "Index '${INDEX_NAME}' already exists. Skipping creation."
else
  echo "Creating index '${INDEX_NAME}' from templates..."
  CREATE_RESPONSE=$(curl -s -XPUT "${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" -H 'Content-Type: application/json' --data-binary '{}')

  if echo "${CREATE_RESPONSE}" | grep -q '"acknowledged":true'; then
    echo "Index '${INDEX_NAME}' created successfully."
  else
    echo "Failed to create index '${INDEX_NAME}'. Response: ${CREATE_RESPONSE}"
    exit 1
  fi
fi

echo "Signaling that OpenSearch index is ready."
touch /tmp/opensearch_index_ready

echo "OpenSearch setup complete."
