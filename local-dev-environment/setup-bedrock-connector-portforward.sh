#!/usr/bin/env bash
set -euo pipefail

# Usage:
# 1) Start port-forward to the OpenSearch proxy on localhost:9200
# 2) Optionally export BEDROCK_ROLE_ARN directly, or let the script prompt for Kubernetes secret details
# 3) Optionally set CONFIRM_OVERWRITE=true to skip overwrite prompts
# 4) Run this script and answer any prompts for missing values
#
# Example:
#   export BEDROCK_ROLE_ARN="arn:aws:iam::123456789012:role/cica-bedrock-connector-role"
#   ./setup-bedrock-connector-portforward.sh
#
# Or:
#   export K8S_NAMESPACE="cica-review-case-documents-dev"
#   export K8S_SECRET_NAME="cica-review-case-documents-bedrock-connector"
#   ./setup-bedrock-connector-portforward.sh

log() { echo "[bedrock-setup] $*" >&2; }
fail() { echo "[bedrock-setup][ERROR] $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

prompt_if_empty() {
  local var_name="$1"
  local prompt_text="$2"
  local default_value="${3:-}"
  local current_value="${!var_name:-}"

  if [[ -n "${current_value}" ]]; then
    return 0
  fi

  if [[ ! -t 0 ]]; then
    if [[ -n "${default_value}" ]]; then
      printf -v "${var_name}" '%s' "${default_value}"
      export "${var_name}"
      return 0
    fi
    fail "Missing required value for ${var_name}"
  fi

  local response
  if [[ -n "${default_value}" ]]; then
    read -r -p "${prompt_text} [${default_value}]: " response
    response="${response:-${default_value}}"
  else
    read -r -p "${prompt_text}: " response
  fi

  if [[ -z "${response}" ]]; then
    fail "Missing required value for ${var_name}"
  fi

  printf -v "${var_name}" '%s' "${response}"
  export "${var_name}"
}

require_cmd curl

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./init-scripts/lib/bedrock_connector_common.inc
source "${SCRIPT_DIR}/init-scripts/lib/bedrock_connector_common.inc"

OPENSEARCH_ENDPOINT="${OPENSEARCH_ENDPOINT:-http://127.0.0.1:9200}"
BEDROCK_REGION="${BEDROCK_REGION:-eu-west-2}"
BEDROCK_EMBED_MODEL="${BEDROCK_MODEL_ID:-amazon.titan-embed-text-v2:0}"
TARGET_INDEX="${TARGET_INDEX:-page_chunks}"
BEDROCK_CONNECTOR_NAME="${CONNECTOR_NAME:-bedrock-titan-embed-connector}"
BEDROCK_MODEL_NAME="${MODEL_NAME:-bedrock-titan-embed-text-v2}"
BEDROCK_PIPELINE_NAME="${INGEST_PIPELINE_NAME:-bedrock-embedding-pipeline}"
BEDROCK_SEARCH_PIPELINE_NAME="${SEARCH_PIPELINE_NAME:-bedrock-neural-search-pipeline}"
BEDROCK_ENABLE_INGEST_PIPELINE="${BEDROCK_ENABLE_INGEST_PIPELINE:-true}"
BEDROCK_TARGET_INDEX="${TARGET_INDEX}"
BEDROCK_OPENSEARCH_ENDPOINT="${OPENSEARCH_ENDPOINT}"
CONFIRM_OVERWRITE="${CONFIRM_OVERWRITE:-prompt}"

# Optional OpenSearch auth
OPENSEARCH_USERNAME="${OPENSEARCH_USERNAME:-}"
OPENSEARCH_PASSWORD="${OPENSEARCH_PASSWORD:-}"
OPENSEARCH_BEARER_TOKEN="${OPENSEARCH_BEARER_TOKEN:-}"

# Connector role ARN can be provided directly or loaded from k8s secret.
BEDROCK_ROLE_ARN="${BEDROCK_ROLE_ARN:-}"
K8S_NAMESPACE="${K8S_NAMESPACE:-}"
K8S_SECRET_NAME="${K8S_SECRET_NAME:-}"
K8S_SECRET_KEY="${K8S_SECRET_KEY:-role_arn}"

BEDROCK_AUTH_ARGS=()
if [[ -n "${OPENSEARCH_BEARER_TOKEN}" ]]; then
  BEDROCK_AUTH_ARGS+=( -H "Authorization: Bearer ${OPENSEARCH_BEARER_TOKEN}" )
elif [[ -n "${OPENSEARCH_USERNAME}" || -n "${OPENSEARCH_PASSWORD}" ]]; then
  BEDROCK_AUTH_ARGS+=( -u "${OPENSEARCH_USERNAME}:${OPENSEARCH_PASSWORD}" )
fi

load_role_arn() {
  if [[ -n "${BEDROCK_ROLE_ARN}" ]]; then
    return 0
  fi

  if [[ -t 0 ]]; then
    local role_arn_input
    read -r -p "Enter BEDROCK_ROLE_ARN directly (leave blank to load from Kubernetes secret): " role_arn_input
    if [[ -n "${role_arn_input}" ]]; then
      BEDROCK_ROLE_ARN="${role_arn_input}"
      export BEDROCK_ROLE_ARN
      return 0
    fi
  fi

  prompt_if_empty "K8S_NAMESPACE" "Enter Kubernetes namespace"
  prompt_if_empty "K8S_SECRET_NAME" "Enter Kubernetes secret name"
  prompt_if_empty "K8S_SECRET_KEY" "Enter Kubernetes secret key" "role_arn"
  require_cmd kubectl

  log "Loading role ARN from secret ${K8S_SECRET_NAME} in namespace ${K8S_NAMESPACE}"
  BEDROCK_ROLE_ARN="$(kubectl get secret -n "${K8S_NAMESPACE}" "${K8S_SECRET_NAME}" -o "jsonpath={.data.${K8S_SECRET_KEY}}" | base64 -d)"
  [[ -n "${BEDROCK_ROLE_ARN}" ]] || fail "Failed to read BEDROCK_ROLE_ARN from secret"
}

wait_for_index() {
  bedrock_wait_for_index "${TARGET_INDEX}"
}

ensure_ml_settings() {
  local body
  body="$(cat <<JSON
{
  "persistent": {
    "plugins.ml_commons.only_run_on_ml_node": false,
    "plugins.ml_commons.native_memory_threshold": 99,
    "plugins.ml_commons.trusted_connector_endpoints_regex": [
      "^https://bedrock-runtime\\.${BEDROCK_REGION}\\.amazonaws\\.com/.*$"
    ]
  }
}
JSON
)"
  bedrock_ensure_ml_settings "${body}"
}

resource_exists() {
  local path="$1"
  local status

  status="$(curl -sS -o /dev/null -w '%{http_code}' "${BEDROCK_OPENSEARCH_ENDPOINT}${path}" "${BEDROCK_AUTH_ARGS[@]}" -H 'Content-Type: application/json')"
  [[ "${status}" -ge 200 && "${status}" -lt 300 ]]
}

confirm_overwrite_if_needed() {
  local existing_resources=()
  local prompt_message reply

  if [[ "${BEDROCK_ENABLE_INGEST_PIPELINE}" == "true" ]] && resource_exists "/_ingest/pipeline/${BEDROCK_PIPELINE_NAME}"; then
    existing_resources+=("ingest pipeline ${BEDROCK_PIPELINE_NAME}")
  fi

  if resource_exists "/_search/pipeline/${BEDROCK_SEARCH_PIPELINE_NAME}"; then
    existing_resources+=("search pipeline ${BEDROCK_SEARCH_PIPELINE_NAME}")
  fi

  if resource_exists "/${TARGET_INDEX}/_settings"; then
    existing_resources+=("index settings on ${TARGET_INDEX}")
  fi

  if [[ ${#existing_resources[@]} -eq 0 ]]; then
    return 0
  fi

  log "Existing resources will be updated: ${existing_resources[*]}"

  case "${CONFIRM_OVERWRITE}" in
    true)
      log "Proceeding because CONFIRM_OVERWRITE=true"
      return 0
      ;;
    false)
      fail "Refusing to overwrite existing resources because CONFIRM_OVERWRITE=false"
      ;;
    prompt)
      if [[ ! -t 0 ]]; then
        fail "Existing resources would be overwritten. Re-run with CONFIRM_OVERWRITE=true to proceed non-interactively"
      fi
      prompt_message="Existing Bedrock pipelines/index settings were found and will be overwritten. Continue? [y/N]: "
      read -r -p "${prompt_message}" reply
      if [[ ! "${reply}" =~ ^[Yy]$ ]]; then
        fail "Aborted by user"
      fi
      ;;
    *)
      fail "Unsupported CONFIRM_OVERWRITE value: ${CONFIRM_OVERWRITE}"
      ;;
  esac
}

main() {
  log "Starting Bedrock connector setup via port-forward (${OPENSEARCH_ENDPOINT})"
  load_role_arn
  wait_for_index
  ensure_ml_settings
  confirm_overwrite_if_needed

  BEDROCK_CONNECTOR_CREDENTIAL_BLOCK=$(cat <<JSON
  "credential": {
    "roleArn": "${BEDROCK_ROLE_ARN}"
  },
JSON
)

  local model_id
  model_id="$(bedrock_prepare_model "${BEDROCK_CONNECTOR_CREDENTIAL_BLOCK}")"

  if [[ "${BEDROCK_ENABLE_INGEST_PIPELINE}" == "true" ]]; then
    bedrock_upsert_ingest_pipeline "${model_id}"
  else
    bedrock_log "Skipping ingest pipeline setup (BEDROCK_ENABLE_INGEST_PIPELINE=${BEDROCK_ENABLE_INGEST_PIPELINE})."
  fi
  bedrock_upsert_search_pipeline "${model_id}"
  bedrock_set_index_default_pipelines "${BEDROCK_ENABLE_INGEST_PIPELINE}" "${TARGET_INDEX}"

  log "Done"
}

main "$@"
