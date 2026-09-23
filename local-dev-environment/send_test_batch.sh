#!/bin/bash
#
# send_test_batch.sh — DEV / TESTING AID (not production code)
#
# Enqueues MANY well-formed document-processing messages onto the LocalStack SQS
# queue in one run — a bulk companion to send_test_message.sh. Use it to load a
# whole evaluation set onto the queue and then drain it with the pipeline runner.
#
# In production NOTHING in this repo sends messages: an upstream system produces
# them and the pipeline only consumes. This script exists purely so developers can
# put test work on the local queue without hand-writing the JSON contract each time.
#
# You supply a comma-separated list of PARTIAL keys of the form "<case_ref>/<filename>"
# (e.g. "26-700030/case30_TC19_Redacted_White.pdf"). For each key the script derives
# case_ref from the leading folder, prepends the bucket to form the full
# source_file_s3_uri, and sends one message. A built-in default set of 30 documents
# is used when no keys are supplied.
#
# Each message body matches the contract enforced by
# src/ingestion_pipeline/orchestration/document_ingress.py:
#   Required: correspondence_type, case_ref (^\d{2}-[78]\d{5}$), a source location
#             (a full source_file_s3_uri here), and received_date (ISO-8601).
#   Ignored:  source_doc_id, page_count (derived during ingestion).
#   Cross-check: case_ref must equal the case folder in source_file_s3_uri.
#
# AWS access: prefers the host AWS CLI pointed at LocalStack
#   aws --endpoint-url=http://localhost:4566 --region <region> sqs ...
# and falls back to `docker exec <container> awslocal sqs ...` when the host `aws`
# CLI is not installed but the LocalStack container is running. No AWS creds needed;
# LocalStack accepts the dummy "test" credentials configured by the local dev stack.
#
# Usage (paths shown relative to the repository root):
#   local-dev-environment/send_test_batch.sh                         # send the built-in 30-document set
#   local-dev-environment/send_test_batch.sh --dry-run               # print bodies, send nothing (no AWS needed)
#   local-dev-environment/send_test_batch.sh -k "26-700001/a.pdf,26-700002/b.pdf"
#   local-dev-environment/send_test_batch.sh --keys-file keys.txt    # comma and/or newline separated
#
# Options:
#   -k, --keys LIST         Comma-separated "case_ref/filename" keys.
#       --keys-file FILE    Read keys from FILE (comma and/or newline separated).
#   -q, --queue NAME        SQS queue name        (default: $SQS_DOCUMENT_QUEUE or cica-document-search-queue)
#   -b, --bucket NAME       Source S3 bucket       (default: $AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET or local-kta-documents-bucket)
#   -t, --type TYPE         Correspondence type    (default: "TC19 - ADDITIONAL INFO REQUEST")
#       --received-date DT  received_date (ISO-8601). Defaults to the current UTC time, reused for every message.
#       --endpoint URL      LocalStack endpoint URL (default: http://localhost:4566)
#       --region REGION     AWS region             (default: $AWS_REGION or eu-west-2)
#   -n, --dry-run           Print the message bodies that would be sent; send nothing.
#   -h, --help              Show this help and exit.
#
# Requires: python3 (to build JSON bodies safely). For real sends: either the host
# `aws` CLI or docker with the localstack-main container running.

set -euo pipefail

CONTAINER="${LOCALSTACK_DOCKER_NAME:-localstack-main}"

QUEUE_NAME="${SQS_DOCUMENT_QUEUE:-cica-document-search-queue}"
BUCKET="${AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET:-local-kta-documents-bucket}"
CORRESPONDENCE_TYPE="TC19 - ADDITIONAL INFO REQUEST"
RECEIVED_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
ENDPOINT_URL="http://localhost:4566"
REGION="${AWS_REGION:-eu-west-2}"

KEYS=""
KEYS_FILE=""
DRY_RUN=0

# Built-in default set of 30 documents. The exact filenames and case order below are
# intentional (note the mixed casing, e.g. "case30_..." vs "Case29_...", and
# "Redacted_white.pdf" vs "Redacted_White.pdf"); preserve them verbatim.
DEFAULT_KEYS="26-700030/case30_TC19_Redacted_White.pdf
26-700029/Case29_TC19_Redacted_White.pdf
26-700028/Case28_TC19_Redacted_White.pdf
26-700027/Case27_TC19_Redacted_White.pdf
26-700026/Case26_TC19_Redacted_White.pdf
26-700025/Case25_TC19_Redacted_White.pdf
26-700024/Case24_TC19_Redacted_White.pdf
26-700023/Case23_TC19_Redacted_White.pdf
26-700022/Case22_TC19_Redacted_White.pdf
26-700021/Case21_TC19_Redacted_White.pdf
26-700020/Case20_TC19_Redacted_White.pdf
26-700019/Case19_TC19_Redacted_White.pdf
26-700018/Case18_TC19_Redacted_White.pdf
26-700017/Case17_TC19_Redacted_White.pdf
26-700016/Case16_TC19_Redacted_White.pdf
26-700015/Case15_TC19_Redacted_White.pdf
26-700014/Case14_TC19_Redacted_white.pdf
26-700013/Case13_TC19_Redacted_White.pdf
26-700012/Case12_TC19_Redacted_White.pdf
26-700011/Case11_TC19_Redacted_White.pdf
26-700010/Case10_TC19_Redacted_White.pdf
26-700009/Case9_TC19_Redacted_White.pdf
26-700008/Case8_TC19_Redacted_White.pdf
26-700007/Case7_TC19_Redacted_White.pdf
26-700006/Case6_TC19_Redacted_White.pdf
26-700005/Case5_TC19_with_injury_photos_Redacted_White.pdf
26-700004/Case4_TC19_with_handwriting_Redacted_White.pdf
26-700003/Case3_TC19_with_handwriting_Redacted_white.pdf
26-700002/Case2_TC19_with_handwriting_Redacted_white.pdf
26-700001/Case1_TC19_50_pages_brain_injury.pdf"

usage() {
  sed -n '2,63p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -k|--keys)         KEYS="$2"; shift 2 ;;
    --keys-file)       KEYS_FILE="$2"; shift 2 ;;
    -q|--queue)        QUEUE_NAME="$2"; shift 2 ;;
    -b|--bucket)       BUCKET="$2"; shift 2 ;;
    -t|--type)         CORRESPONDENCE_TYPE="$2"; shift 2 ;;
    --received-date)   RECEIVED_DATE="$2"; shift 2 ;;
    --endpoint)        ENDPOINT_URL="$2"; shift 2 ;;
    --region)          REGION="$2"; shift 2 ;;
    -n|--dry-run)      DRY_RUN=1; shift ;;
    -h|--help)         usage 0 ;;
    *) echo "Unknown option: $1" >&2; usage 1 ;;
  esac
done

# python3 is required to build the JSON bodies safely (values are escaped by
# json.dumps and passed via the environment, never interpolated into code).
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required to build the message bodies safely." >&2
  exit 1
fi

# Resolve the list of keys. Precedence: --keys, then --keys-file, then $SRC_S3_KEY,
# then the built-in DEFAULT_KEYS. --keys-file joins newlines to commas so the split
# below handles both separators uniformly.
if [[ -n "${KEYS}" ]]; then
  KEY_LIST="${KEYS}"
elif [[ -n "${KEYS_FILE}" ]]; then
  if [[ ! -f "${KEYS_FILE}" ]]; then
    echo "ERROR: keys file not found: ${KEYS_FILE}" >&2
    exit 1
  fi
  KEY_LIST="$(tr '\n' ',' < "${KEYS_FILE}")"
elif [[ -n "${SRC_S3_KEY:-}" ]]; then
  KEY_LIST="${SRC_S3_KEY}"
else
  KEY_LIST="$(printf '%s' "${DEFAULT_KEYS}" | tr '\n' ',')"
fi

# CASE_REF_PATTERN mirrors the contract enforced by document_ingress.py. Keys whose
# case folder does not match are skipped (with a warning) rather than sent, since the
# consumer would reject them as malformed.
CASE_REF_PATTERN='^[0-9]{2}-[78][0-9]{5}$'

# Selected AWS access mode: "aws" (host CLI) or "docker" (awslocal in the container).
# Resolved lazily on first real send so --dry-run needs neither AWS nor LocalStack.
AWS_MODE=""
QUEUE_URL=""

# select_aws_mode picks the host AWS CLI if available, otherwise falls back to
# awslocal inside the LocalStack container.
select_aws_mode() {
  if command -v aws >/dev/null 2>&1; then
    AWS_MODE="aws"
  elif command -v docker >/dev/null 2>&1; then
    AWS_MODE="docker"
  else
    echo "ERROR: neither the host 'aws' CLI nor 'docker' is available to reach SQS." >&2
    exit 1
  fi
}

# sqs_cli dispatches an SQS sub-command to whichever access mode was selected.
sqs_cli() {
  if [[ "${AWS_MODE}" == "aws" ]]; then
    aws --endpoint-url="${ENDPOINT_URL}" --region "${REGION}" sqs "$@"
  else
    docker exec "${CONTAINER}" awslocal sqs "$@"
  fi
}

# ensure_queue_url resolves the queue URL exactly once, on first real send.
ensure_queue_url() {
  [[ -n "${QUEUE_URL}" ]] && return 0
  select_aws_mode
  QUEUE_URL="$(sqs_cli get-queue-url --queue-name "${QUEUE_NAME}" \
    --query QueueUrl --output text 2>/dev/null)" || {
    echo "ERROR: could not resolve queue '${QUEUE_NAME}'. Is LocalStack running?" >&2
    exit 1
  }
}

# build_body assembles the JSON message body for one document using json.dumps.
# Values are passed via the environment so quotes, backslashes, spaces, or other
# JSON-special characters in any field are escaped correctly and never interpolated
# into code.
build_body() {
  local s3_uri="$1"
  CORRESPONDENCE_TYPE="${CORRESPONDENCE_TYPE}" CASE_REF="$2" \
  S3_URI="${s3_uri}" RECEIVED_DATE="${RECEIVED_DATE}" \
  python3 -c '
import json, os
body = {
    "correspondence_type": os.environ["CORRESPONDENCE_TYPE"],
    "case_ref": os.environ["CASE_REF"],
    "source_file_s3_uri": os.environ["S3_URI"],
    "received_date": os.environ["RECEIVED_DATE"],
}
print(json.dumps(body))
'
}

echo "Queue:   ${QUEUE_NAME}"
echo "Bucket:  ${BUCKET}"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Mode:    DRY RUN (no messages will be sent)"
fi
echo

SENT=0
SKIPPED=0

# Split the comma-separated list into an array and process each key.
IFS=',' read -r -a KEY_ARRAY <<< "${KEY_LIST}"
for raw_key in "${KEY_ARRAY[@]}"; do
  # Trim surrounding whitespace and any stray carriage returns.
  key="$(printf '%s' "${raw_key}" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

  # Skip empty entries (e.g. trailing commas or blank lines).
  [[ -z "${key}" ]] && continue

  # A key must be "<case_ref>/<filename>".
  if [[ "${key}" != */* ]]; then
    echo "WARN: skipping key without a '/': ${key}" >&2
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  case_ref="${key%%/*}"
  filename="${key#*/}"

  # Skip keys whose case_ref would be rejected by the consumer.
  if [[ ! "${case_ref}" =~ ${CASE_REF_PATTERN} ]]; then
    echo "WARN: skipping key with invalid case_ref '${case_ref}': ${key}" >&2
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  s3_uri="s3://${BUCKET}/${case_ref}/${filename}"
  body="$(build_body "${s3_uri}" "${case_ref}")"

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "would send: ${body}"
    SENT=$((SENT + 1))
    continue
  fi

  ensure_queue_url
  sqs_cli send-message --queue-url "${QUEUE_URL}" --message-body "${body}" >/dev/null
  echo "sent: ${s3_uri}"
  SENT=$((SENT + 1))
done

echo
if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "${SENT} message(s) would be sent, ${SKIPPED} skipped."
else
  echo "${SENT} message(s) sent, ${SKIPPED} skipped."
  if [[ "${SENT}" -gt 0 ]]; then
    echo "Drain the queue with: bash run_locally_with_dot_env.sh"
  fi
fi
