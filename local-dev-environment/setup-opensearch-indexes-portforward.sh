#!/usr/bin/env bash
set -euo pipefail

# Usage:
# 1) Start port-forward to the OpenSearch endpoint on localhost:9200
# 2) Optionally set OPENSEARCH_ENDPOINT, auth variables, and overwrite behavior
# 3) Run this script
#
# Example:
#   OPENSEARCH_ENDPOINT=http://127.0.0.1:9200 ./setup-opensearch-indexes-portforward.sh
#
# Optional auth:
#   OPENSEARCH_USERNAME=admin OPENSEARCH_PASSWORD=admin ./setup-opensearch-indexes-portforward.sh
#   OPENSEARCH_BEARER_TOKEN=... ./setup-opensearch-indexes-portforward.sh
#
# Optional overwrite behavior:
#   CONFIRM_OVERWRITE=true ./setup-opensearch-indexes-portforward.sh
#
# Optional index topology (applied via shared templates):
#   OPENSEARCH_NUMBER_OF_SHARDS=2 OPENSEARCH_NUMBER_OF_REPLICAS=1 ./setup-opensearch-indexes-portforward.sh
#
# Notes:
# - Default values are resolved in init-scripts/lib/opensearch_templates.inc.
# - These variables can be set here to override those defaults per run.
# - They only affect newly created indexes (recreate with CONFIRM_OVERWRITE=true to apply changes).

log() { echo "[opensearch-index-setup] $*" >&2; }
fail() { echo "[opensearch-index-setup][ERROR] $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

OPENSEARCH_ENDPOINT="${OPENSEARCH_ENDPOINT:-http://127.0.0.1:9200}"
CONFIRM_OVERWRITE="${CONFIRM_OVERWRITE:-prompt}"

# Optional OpenSearch auth
OPENSEARCH_USERNAME="${OPENSEARCH_USERNAME:-}"
OPENSEARCH_PASSWORD="${OPENSEARCH_PASSWORD:-}"
OPENSEARCH_BEARER_TOKEN="${OPENSEARCH_BEARER_TOKEN:-}"

AUTH_ARGS=()
if [[ -n "${OPENSEARCH_BEARER_TOKEN}" ]]; then
  AUTH_ARGS+=( -H "Authorization: Bearer ${OPENSEARCH_BEARER_TOKEN}" )
elif [[ -n "${OPENSEARCH_USERNAME}" && -n "${OPENSEARCH_PASSWORD}" ]]; then
  AUTH_ARGS+=( -u "${OPENSEARCH_USERNAME}:${OPENSEARCH_PASSWORD}" )
elif [[ -n "${OPENSEARCH_USERNAME}" || -n "${OPENSEARCH_PASSWORD}" ]]; then
   fail "Both OPENSEARCH_USERNAME and OPENSEARCH_PASSWORD must be set when using basic auth"
fi

wait_for_cluster() {
  log "Waiting for OpenSearch at ${OPENSEARCH_ENDPOINT}"
  local status
  for _ in $(seq 1 60); do
    status="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 10 \
       "${OPENSEARCH_ENDPOINT}/_cluster/health?wait_for_status=yellow&timeout=5s" "${AUTH_ARGS[@]}" || true)"
     case "${status}" in
       200)
         log "OpenSearch is ready"
         return 0
         ;;
       401|403)
         fail "Authentication/authorization failed (HTTP ${status}) while checking cluster health"
         ;;
     esac
    sleep 5
  done

  fail "Timed out waiting for OpenSearch cluster health"
}

# Source shared template helper (if present) and apply templates so new indices use correct defaults
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/init-scripts/lib/opensearch_templates.inc" ]; then
  # shellcheck source=./init-scripts/lib/opensearch_templates.inc
  source "${SCRIPT_DIR}/init-scripts/lib/opensearch_templates.inc"
else
  fail "Missing shared template helper: ${SCRIPT_DIR}/init-scripts/lib/opensearch_templates.inc"
fi

resource_exists() {
  local path="$1"
  local status

  status="$(curl -sS -o /dev/null -w '%{http_code}' "${OPENSEARCH_ENDPOINT}${path}" "${AUTH_ARGS[@]}" -I)"
  [[ "${status}" -ge 200 && "${status}" -lt 300 ]]
}

confirm_overwrite_if_needed() {
  local existing_resources=()
  local reply

  if resource_exists "/page_chunks"; then
    existing_resources+=("index page_chunks")
  fi

  if resource_exists "/page_metadata"; then
    existing_resources+=("index page_metadata")
  fi

  if [[ ${#existing_resources[@]} -eq 0 ]]; then
    return 0
  fi

  log "Existing resources detected: ${existing_resources[*]}"

  case "${CONFIRM_OVERWRITE}" in
    true)
      log "Proceeding because CONFIRM_OVERWRITE=true"
      return 0
      ;;
    false)
      log "Skipping recreation because CONFIRM_OVERWRITE=false"
      return 0
      ;;
    prompt)
      if [[ ! -t 0 ]]; then
        fail "Existing indexes found. Re-run with CONFIRM_OVERWRITE=true or CONFIRM_OVERWRITE=false"
      fi
      read -r -p "Existing indexes were found. Recreate page_chunks/page_metadata? [y/N]: " reply
      if [[ "${reply}" =~ ^[Yy]$ ]]; then
        CONFIRM_OVERWRITE=true
      else
        CONFIRM_OVERWRITE=false
      fi
      ;;
    *)
      fail "Unsupported CONFIRM_OVERWRITE value: ${CONFIRM_OVERWRITE}"
      ;;
  esac
}

os_request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local response status resp_body

  if [[ -n "${body}" ]]; then
    response="$(curl -sS -X "${method}" "${OPENSEARCH_ENDPOINT}${path}" "${AUTH_ARGS[@]}" -H "Content-Type: application/json" -d "${body}" -w $'\n%{http_code}')"
  else
    response="$(curl -sS -X "${method}" "${OPENSEARCH_ENDPOINT}${path}" "${AUTH_ARGS[@]}" -H "Content-Type: application/json" -w $'\n%{http_code}')"
  fi

  status="$(echo "${response}" | tail -n1)"
  resp_body="$(echo "${response}" | sed '$d')"

  if [[ "${status}" -lt 200 || "${status}" -ge 300 ]]; then
    echo "${resp_body}" >&2
    fail "HTTP ${status} for ${method} ${path}"
  fi

  echo "${resp_body}"
}

delete_index_if_requested() {
  local index_name="$1"

  if ! resource_exists "/${index_name}"; then
    return 0
  fi

  if [[ "${CONFIRM_OVERWRITE}" != "true" ]]; then
    log "Index ${index_name} already exists. Skipping creation."
    return 0
  fi

  log "Deleting existing index ${index_name}"
  os_request DELETE "/${index_name}" >/dev/null
}

create_page_chunks() {
  delete_index_if_requested "page_chunks"

  if resource_exists "/page_chunks"; then
    log "Index page_chunks already exists. Skipping creation."
    return 0
  fi

  log "Creating index page_chunks from templates"
  os_request PUT "/page_chunks" "{}" >/dev/null
}

create_page_metadata() {
  delete_index_if_requested "page_metadata"

  if resource_exists "/page_metadata"; then
    log "Index page_metadata already exists. Skipping creation."
    return 0
  fi

  log "Creating index page_metadata from templates"
  os_request PUT "/page_metadata" "{}" >/dev/null
}

main() {
  require_cmd curl
  wait_for_cluster
  log "Applying OpenSearch index templates"
  opensearch_apply_templates
  confirm_overwrite_if_needed
  create_page_chunks
  create_page_metadata
  log "OpenSearch index setup complete"
}

main "$@"
