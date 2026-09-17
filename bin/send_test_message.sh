#!/bin/bash
#
# send_test_message.sh — DEV / TESTING AID (not production code)
#
# Enqueues a single well-formed document-processing message onto the LocalStack
# SQS queue, standing in for the external producer that will exist in the real
# world. Use it to exercise the SqsDocumentSource consumer locally.
#
# In production NOTHING in this repo sends messages: an upstream system produces
# them and the pipeline only consumes. This script exists purely so developers can
# put test work on the local queue without hand-writing the JSON contract each time.
#
# The message body matches the contract enforced by
# src/ingestion_pipeline/orchestration/message_parser.py:
#   Required: correspondence_type, case_ref (^\d{2}-[78]\d{5}$), and a source
#             location (a full source_file_s3_uri here).
#   Optional: received_date.
#   Ignored:  source_doc_id, page_count (derived during ingestion).
#
# Usage:
#   bin/send_test_message.sh                       # send one message using defaults
#   bin/send_test_message.sh -c 26-700099 -f merged-all.pdf
#   bin/send_test_message.sh --body '{"correspondence_type":"...","case_ref":"...","source_file_s3_uri":"..."}'
#   bin/send_test_message.sh --malformed           # send an invalid message to test rejection
#
# Options:
#   -q, --queue NAME        SQS queue name        (default: $SQS_DOCUMENT_QUEUE or cica-document-search-queue)
#   -b, --bucket NAME       Source S3 bucket       (default: $AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET or local-kta-documents-bucket)
#   -c, --case-ref REF      Case reference         (default: 26-700001)
#   -t, --type TYPE         Correspondence type    (default: "TC19 - ADDITIONAL INFO REQUEST")
#   -f, --filename NAME     Source file name       (default: Case1_TC19_50_pages_brain_injury.pdf)
#       --received-date DT  Optional received_date (ISO-8601). Omitted if unset.
#       --body JSON         Send this raw JSON body verbatim (overrides all field options).
#       --malformed         Send a deliberately invalid body ("not valid json") to test rejection.
#   -h, --help              Show this help and exit.
#
# Requires: docker (with the localstack-main container running). No AWS creds needed;
# LocalStack accepts the dummy "test" credentials configured by the local dev stack.

set -euo pipefail

CONTAINER="${LOCALSTACK_DOCKER_NAME:-localstack-main}"

QUEUE_NAME="${SQS_DOCUMENT_QUEUE:-cica-document-search-queue}"
BUCKET="${AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET:-local-kta-documents-bucket}"
CASE_REF="26-700001"
CORRESPONDENCE_TYPE="TC19 - ADDITIONAL INFO REQUEST"
FILENAME="Case1_TC19_50_pages_brain_injury.pdf"
RECEIVED_DATE=""
RAW_BODY=""
MALFORMED=0

usage() {
  sed -n '2,38p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -q|--queue)        QUEUE_NAME="$2"; shift 2 ;;
    -b|--bucket)       BUCKET="$2"; shift 2 ;;
    -c|--case-ref)     CASE_REF="$2"; shift 2 ;;
    -t|--type)         CORRESPONDENCE_TYPE="$2"; shift 2 ;;
    -f|--filename)     FILENAME="$2"; shift 2 ;;
    --received-date)   RECEIVED_DATE="$2"; shift 2 ;;
    --body)            RAW_BODY="$2"; shift 2 ;;
    --malformed)       MALFORMED=1; shift ;;
    -h|--help)         usage 0 ;;
    *) echo "Unknown option: $1" >&2; usage 1 ;;
  esac
done

# Resolve the queue URL from inside the LocalStack container.
QUEUE_URL="$(docker exec "${CONTAINER}" awslocal sqs get-queue-url \
  --queue-name "${QUEUE_NAME}" --output text 2>/dev/null)" || {
  echo "ERROR: could not resolve queue '${QUEUE_NAME}'. Is the '${CONTAINER}' container running?" >&2
  exit 1
}

# Build the message body.
if [[ "${MALFORMED}" -eq 1 ]]; then
  BODY="not valid json"
elif [[ -n "${RAW_BODY}" ]]; then
  BODY="${RAW_BODY}"
else
  S3_URI="s3://${BUCKET}/${CASE_REF}/${FILENAME}"
  if [[ -n "${RECEIVED_DATE}" ]]; then
    BODY=$(printf '{"correspondence_type":"%s","case_ref":"%s","source_file_s3_uri":"%s","received_date":"%s"}' \
      "${CORRESPONDENCE_TYPE}" "${CASE_REF}" "${S3_URI}" "${RECEIVED_DATE}")
  else
    BODY=$(printf '{"correspondence_type":"%s","case_ref":"%s","source_file_s3_uri":"%s"}' \
      "${CORRESPONDENCE_TYPE}" "${CASE_REF}" "${S3_URI}")
  fi
fi

echo "Queue:   ${QUEUE_NAME}"
echo "Body:    ${BODY}"

docker exec "${CONTAINER}" awslocal sqs send-message \
  --queue-url "${QUEUE_URL}" \
  --message-body "${BODY}"

echo "Sent. Consume it with the pipeline runner or an SqsDocumentSource().fetch_batch()."
