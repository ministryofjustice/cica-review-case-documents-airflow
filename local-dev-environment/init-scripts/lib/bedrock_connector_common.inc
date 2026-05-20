bedrock_log() {
  echo "[bedrock-setup] $*" >&2
}

bedrock_fail() {
  echo "[bedrock-setup][ERROR] $*" >&2
  exit 1
}

bedrock_extract_json_field() {
  local json="$1"
  local key="$2"
  echo "$json" | grep -o "\"${key}\":\"[^\"]*\"" | head -n1 | cut -d'"' -f4 || true
}

bedrock_os_request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"

  local response status resp_body
  if [[ -n "${body}" ]]; then
    response="$(curl -sS -X "${method}" "${BEDROCK_OPENSEARCH_ENDPOINT}${path}" "${BEDROCK_AUTH_ARGS[@]}" -H "Content-Type: application/json" -d "${body}" -w $'\n%{http_code}')"
  else
    response="$(curl -sS -X "${method}" "${BEDROCK_OPENSEARCH_ENDPOINT}${path}" "${BEDROCK_AUTH_ARGS[@]}" -H "Content-Type: application/json" -w $'\n%{http_code}')"
  fi

  status="$(echo "${response}" | tail -n1)"
  resp_body="$(echo "${response}" | sed '$d')"

  if [[ "${status}" -lt 200 || "${status}" -ge 300 ]]; then
    echo "${resp_body}" >&2
    bedrock_fail "HTTP ${status} for ${method} ${path}"
  fi

  echo "${resp_body}"
}

bedrock_wait_for_index() {
  local index_name="${1:-${BEDROCK_TARGET_INDEX:-page_chunks}}"

  bedrock_log "Waiting for OpenSearch and index ${index_name}"
  for _ in $(seq 1 60); do
    if curl --silent --fail "${BEDROCK_AUTH_ARGS[@]}" "${BEDROCK_OPENSEARCH_ENDPOINT}/${index_name}" >/dev/null 2>&1; then
      bedrock_log "Index ${index_name} is ready"
      return 0
    fi
    sleep 5
  done

  bedrock_fail "Timed out waiting for index ${index_name}"
}

bedrock_ensure_ml_settings() {
  local settings_json="$1"
  local response status resp_body

  bedrock_log "Configuring ML Commons cluster settings"
  response="$(curl -sS -X PUT "${BEDROCK_OPENSEARCH_ENDPOINT}/_cluster/settings" "${BEDROCK_AUTH_ARGS[@]}" -H "Content-Type: application/json" -d "${settings_json}" -w $'\n%{http_code}')"
  status="$(echo "${response}" | tail -n1)"
  resp_body="$(echo "${response}" | sed '$d')"

  if [[ "${status}" -ge 200 && "${status}" -lt 300 ]]; then
    bedrock_log "ML Commons cluster settings updated"
    return 0
  fi

  bedrock_log "WARNING: Could not update /_cluster/settings (HTTP ${status}). Continuing."
  if [[ -n "${resp_body}" ]]; then
    echo "${resp_body}" >&2
  fi
}

bedrock_get_connector_id_by_name() {
  local search_response
  search_response="$(bedrock_os_request POST "/_plugins/_ml/connectors/_search" "$(cat <<JSON
{
  "size": 1,
  "query": {
    "match_phrase": {
      "name": "${BEDROCK_CONNECTOR_NAME}"
    }
  }
}
JSON
)")"

  bedrock_extract_json_field "${search_response}" "_id"
}

bedrock_create_connector() {
  local connector_credential_block="$1"
  local connector_response connector_id

  bedrock_log "Creating connector ${BEDROCK_CONNECTOR_NAME}"
  connector_response="$(bedrock_os_request POST "/_plugins/_ml/connectors/_create" "$(cat <<JSON
{
  "name": "${BEDROCK_CONNECTOR_NAME}",
  "description": "Remote connector to Amazon Bedrock Titan Embed Text v2 (1024 dimensions)",
  "version": 1,
  "protocol": "aws_sigv4",
  "parameters": {
    "region": "${BEDROCK_REGION}",
    "service_name": "bedrock"
  },
${connector_credential_block}
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
JSON
)")"

  connector_id="$(bedrock_extract_json_field "${connector_response}" "connector_id")"
  [[ -n "${connector_id}" ]] || bedrock_fail "Failed to create connector"
  echo "${connector_id}"
}

bedrock_get_model_id_by_name() {
  local search_response
  search_response="$(bedrock_os_request POST "/_plugins/_ml/models/_search" "$(cat <<JSON
{
  "size": 1,
  "query": {
    "match_phrase": {
      "name": "${BEDROCK_MODEL_NAME}"
    }
  }
}
JSON
)")"

  bedrock_extract_json_field "${search_response}" "_id"
}

bedrock_wait_for_task_completion() {
  local task_id="$1"
  local action_label="$2"

  for _ in $(seq 1 60); do
    local task_response task_state
    task_response="$(bedrock_os_request GET "/_plugins/_ml/tasks/${task_id}")"
    task_state="$(bedrock_extract_json_field "${task_response}" "state")"

    if [[ "${task_state}" == "COMPLETED" ]]; then
      echo "${task_response}"
      return 0
    fi

    if [[ "${task_state}" == "FAILED" ]]; then
      echo "${task_response}" >&2
      bedrock_fail "${action_label} failed"
    fi

    sleep 3
  done

  bedrock_fail "${action_label} timed out"
}

bedrock_register_model() {
  local connector_id="$1"
  local register_response register_task_id task_response model_id

  bedrock_log "Registering model ${BEDROCK_MODEL_NAME}"
  register_response="$(bedrock_os_request POST "/_plugins/_ml/models/_register" "$(cat <<JSON
{
  "name": "${BEDROCK_MODEL_NAME}",
  "function_name": "remote",
  "description": "Amazon Bedrock Titan Embed Text v2",
  "connector_id": "${connector_id}"
}
JSON
)")"

  register_task_id="$(bedrock_extract_json_field "${register_response}" "task_id")"
  [[ -n "${register_task_id}" ]] || bedrock_fail "Failed to get model registration task ID"

  task_response="$(bedrock_wait_for_task_completion "${register_task_id}" "Model registration")"
  model_id="$(bedrock_extract_json_field "${task_response}" "model_id")"
  [[ -n "${model_id}" ]] || bedrock_fail "Model registration completed without model ID"

  echo "${model_id}"
}

bedrock_deploy_model_if_needed() {
  local model_id="$1"
  local model_response model_state deploy_response deploy_task_id

  model_response="$(bedrock_os_request GET "/_plugins/_ml/models/${model_id}")"
  model_state="$(bedrock_extract_json_field "${model_response}" "model_state")"

  if [[ "${model_state}" == "DEPLOYED" ]]; then
    bedrock_log "Model ${model_id} is already deployed"
    return 0
  fi

  bedrock_log "Deploying model ${model_id}"
  deploy_response="$(bedrock_os_request POST "/_plugins/_ml/models/${model_id}/_deploy")"
  deploy_task_id="$(bedrock_extract_json_field "${deploy_response}" "task_id")"
  [[ -n "${deploy_task_id}" ]] || bedrock_fail "Failed to start model deployment"

  bedrock_wait_for_task_completion "${deploy_task_id}" "Model deployment" >/dev/null
}

bedrock_upsert_ingest_pipeline() {
  local model_id="$1"
  local response

  bedrock_log "Upserting ingest pipeline ${BEDROCK_PIPELINE_NAME}"
  response="$(bedrock_os_request PUT "/_ingest/pipeline/${BEDROCK_PIPELINE_NAME}" "$(cat <<JSON
{
  "description": "Automatically generate embeddings for chunk_text",
  "processors": [
    {
      "text_embedding": {
        "model_id": "${model_id}",
        "field_map": {
          "chunk_text": "embedding"
        }
      }
    }
  ]
}
JSON
)")"

  echo "${response}" | grep -q '"acknowledged":true' || bedrock_fail "Failed to upsert ingest pipeline"
}

bedrock_upsert_search_pipeline() {
  local model_id="$1"
  local response

  bedrock_log "Upserting search pipeline ${BEDROCK_SEARCH_PIPELINE_NAME}"
  response="$(bedrock_os_request PUT "/_search/pipeline/${BEDROCK_SEARCH_PIPELINE_NAME}" "$(cat <<JSON
{
  "request_processors": [
    {
      "neural_query_enricher": {
        "default_model_id": "${model_id}",
        "neural_field_default_id": {
          "embedding": "${model_id}"
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
JSON
)")"

  echo "${response}" | grep -q '"acknowledged":true' || bedrock_fail "Failed to upsert search pipeline"
}

bedrock_set_index_default_pipelines() {
  local enable_ingest_pipeline="$1"
  local index_name="${2:-${BEDROCK_TARGET_INDEX:-page_chunks}}"
  local response

  bedrock_log "Setting default pipelines on ${index_name}"
  if [[ "${enable_ingest_pipeline}" == "true" ]]; then
    response="$(bedrock_os_request PUT "/${index_name}/_settings" "$(cat <<JSON
{
  "index": {
    "default_pipeline": "${BEDROCK_PIPELINE_NAME}",
    "search.default_pipeline": "${BEDROCK_SEARCH_PIPELINE_NAME}"
  }
}
JSON
)")"
  else
    response="$(bedrock_os_request PUT "/${index_name}/_settings" "$(cat <<JSON
{
  "index": {
    "default_pipeline": "_none",
    "search.default_pipeline": "${BEDROCK_SEARCH_PIPELINE_NAME}"
  }
}
JSON
)")"
  fi

  echo "${response}" | grep -q '"acknowledged":true' || bedrock_fail "Failed to update index default pipelines"
}

bedrock_prepare_model() {
  local connector_credential_block="$1"
  local connector_id model_id

  connector_id="$(bedrock_get_connector_id_by_name)"
  if [[ -z "${connector_id}" ]]; then
    connector_id="$(bedrock_create_connector "${connector_credential_block}")"
    bedrock_log "Created connector: ${connector_id}"
  else
    bedrock_log "Reusing connector: ${connector_id}"
  fi

  model_id="$(bedrock_get_model_id_by_name)"
  if [[ -z "${model_id}" ]]; then
    model_id="$(bedrock_register_model "${connector_id}")"
    bedrock_log "Registered model: ${model_id}"
  else
    bedrock_log "Reusing model: ${model_id}"
  fi

  bedrock_deploy_model_if_needed "${model_id}"
  echo "${model_id}"
}
