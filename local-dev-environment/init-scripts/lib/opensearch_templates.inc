#!/usr/bin/env bash
# Shared helper: create OpenSearch index templates for local/dev use

opensearch_log() { echo "[opensearch-templates] $*" >&2; }
opensearch_fail() { echo "[opensearch-templates][ERROR] $*" >&2; exit 1; }

opensearch_prepare_auth_args() {
  AUTH_ARGS=()
  if [[ -n "${OPENSEARCH_BEARER_TOKEN:-}" ]]; then
    AUTH_ARGS+=( -H "Authorization: Bearer ${OPENSEARCH_BEARER_TOKEN}" )
  elif [[ -n "${OPENSEARCH_USERNAME:-}" && -n "${OPENSEARCH_PASSWORD:-}" ]]; then
    AUTH_ARGS+=( -u "${OPENSEARCH_USERNAME}:${OPENSEARCH_PASSWORD}" )
  elif [[ -n "${OPENSEARCH_USERNAME:-}" || -n "${OPENSEARCH_PASSWORD:-}" ]]; then
     opensearch_fail "Both OPENSEARCH_USERNAME and OPENSEARCH_PASSWORD must be set when using basic auth"
  fi
}

opensearch_put_template() {
  local name="$1"
  local body="$2"

  opensearch_log "Putting template ${name} to ${OPENSEARCH_ENDPOINT}"
  local response
  response=$(curl -sS -X PUT "${OPENSEARCH_ENDPOINT}/_index_template/${name}" "${AUTH_ARGS[@]}" -H "Content-Type: application/json" -d "${body}" -w $'\n%{http_code}')
  local status
  status=$(echo "${response}" | tail -n1)
  local resp_body
  resp_body=$(echo "${response}" | sed '$d')
  if [[ "${status}" -lt 200 || "${status}" -ge 300 ]]; then
    echo "${resp_body}" >&2
    opensearch_fail "HTTP ${status} putting template ${name}"
  fi
  echo "${resp_body}"
}

opensearch_resolve_index_topology() {
  OPENSEARCH_RESOLVED_NUMBER_OF_SHARDS="${OPENSEARCH_NUMBER_OF_SHARDS:-2}"
  OPENSEARCH_RESOLVED_NUMBER_OF_REPLICAS="${OPENSEARCH_NUMBER_OF_REPLICAS:-1}"

  [[ "${OPENSEARCH_RESOLVED_NUMBER_OF_SHARDS}" =~ ^[0-9]+$ ]] || opensearch_fail "OPENSEARCH_NUMBER_OF_SHARDS must be an integer (got: ${OPENSEARCH_RESOLVED_NUMBER_OF_SHARDS})"
  [[ "${OPENSEARCH_RESOLVED_NUMBER_OF_REPLICAS}" =~ ^[0-9]+$ ]] || opensearch_fail "OPENSEARCH_NUMBER_OF_REPLICAS must be an integer (got: ${OPENSEARCH_RESOLVED_NUMBER_OF_REPLICAS})"
}

opensearch_create_page_chunks_template() {
  local pipeline_field=''
  if [[ -n "${OPENSEARCH_DEFAULT_PIPELINE:-}" ]]; then
    pipeline_field=",\n        \"index.default_pipeline\": \"${OPENSEARCH_DEFAULT_PIPELINE}\""
  fi

  read -r -d '' body <<JSON || true
{
  "index_patterns": ["page_chunks*"],
  "template": {
    "settings": {
      "number_of_shards": ${OPENSEARCH_RESOLVED_NUMBER_OF_SHARDS},
      "number_of_replicas": ${OPENSEARCH_RESOLVED_NUMBER_OF_REPLICAS},
      "index.knn": true${pipeline_field}
    },
    "mappings": {
      "properties": {
        "chunk_id": { "type": "keyword" },
        "source_doc_id": { "type": "keyword" },
        "chunk_text": { "type": "text", "fields": { "english": { "type": "text", "analyzer": "english" } } },
        "embedding": {
          "type": "knn_vector",
          "dimension": 1024,
          "method": {
            "name": "hnsw",
            "space_type": "cosinesimil",
            "engine": "faiss",
            "parameters": { "ef_construction": 128, "m": 24 }
          }
        },
        "source_file_name": { "type": "keyword" },
        "page_id": { "type": "keyword", "index": false },
        "case_ref": { "type": "keyword" },
        "correspondence_type": { "type": "keyword" },
        "received_date": { "type": "date", "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||epoch_millis||yyyy-MM-dd'T'HH:mm:ss.SSSSSS" },
        "page_count": { "type": "integer" },
        "page_number": { "type": "integer" },
        "chunk_index": { "type": "integer" },
        "chunk_type": { "type": "keyword" },
        "confidence": { "type": "float" },
        "geometry": {
          "properties": {
            "bounding_box": {
              "properties": {
                "top": { "type": "float" },
                "left": { "type": "float" },
                "width": { "type": "float" },
                "height": { "type": "float" }
              }
            }
          }
        }
      }
    }
  }
}
JSON

  opensearch_put_template "page_chunks_template" "${body}" >/dev/null
  opensearch_log "page_chunks_template created"
}

opensearch_create_page_metadata_template() {
  read -r -d '' body <<JSON || true
{
  "index_patterns": ["page_metadata*"],
  "template": {
    "settings": {
      "number_of_shards": ${OPENSEARCH_RESOLVED_NUMBER_OF_SHARDS},
      "number_of_replicas": ${OPENSEARCH_RESOLVED_NUMBER_OF_REPLICAS}
    },
    "mappings": {
      "properties": {
        "page_id": { "type": "keyword" },
        "source_doc_id": { "type": "keyword" },
        "page_text": { "type": "keyword", "index": false },
        "source_file_name": { "type": "keyword", "index": false },
        "s3_page_image_uri": { "type": "keyword", "index": false },
        "case_ref": { "type": "keyword", "index": false },
        "correspondence_type": { "type": "keyword", "index": false },
        "received_date": { "type": "date", "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||epoch_millis||yyyy-MM-dd'T'HH:mm:ss.SSSSSS" },
        "page_count": { "type": "integer", "index": false },
        "page_number": { "type": "integer", "index": false },
        "geometry": { "type": "object", "enabled": false }
      }
    }
  }
}
JSON

  opensearch_put_template "page_metadata_template" "${body}" >/dev/null
  opensearch_log "page_metadata_template created"
}

opensearch_apply_templates() {
  : "Ensure OPENSEARCH_ENDPOINT is set"
  [[ -n "${OPENSEARCH_ENDPOINT:-}" ]] || opensearch_fail "OPENSEARCH_ENDPOINT is not set"
  opensearch_prepare_auth_args
  opensearch_resolve_index_topology
  opensearch_create_page_chunks_template
  opensearch_create_page_metadata_template
}

