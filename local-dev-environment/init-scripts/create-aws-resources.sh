#!/bin/bash
set -euo pipefail # Exit immediately if a command exits with a non-zero status or pipe fails

#####################################################################
# TROUBLESHOOTING STEPS
#
# 1. Ensure your AWS credentials are valid and have access to the source S3 bucket/object.
#    - Test with: aws s3 cp s3://mod-platfform-sandbox-kta-documents-bucket/26-711111/Case1_TC19_50_pages_brain_injury.pdf /tmp/test.pdf
#    - If this fails, check your AWS credentials and permissions.
#
# 2. Ensure awslocal is installed and available in the PATH.
#
# 3. If the sample document is not present in LocalStack S3, check the logs for errors in the download/upload steps.
#
# 4. To verify the file exists in LocalStack S3:
#    - awslocal s3 ls s3://local-kta-documents-bucket/26-711111/
#
# 5. If you see 404 (NoSuchKey) errors, the file was not uploaded to LocalStack S3.
#
#####################################################################

echo "Starting LocalStack AWS resource creation..."

# Load environment variables from LocalStack .env file if it exists
if [ -f /etc/localstack/.env ]; then
  export $(grep -v '^#' /etc/localstack/.env | grep -v '^$' | sed 's/#.*//' | xargs)
fi

# Map MOD_PLATFORM_SANDBOX variables to standard AWS variables
export AWS_ACCESS_KEY_ID="${AWS_MOD_PLATFORM_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY}"
export AWS_SESSION_TOKEN="${AWS_MOD_PLATFORM_SESSION_TOKEN}"

# Check required variables
: "${AWS_ACCESS_KEY_ID:?AWS_MOD_PLATFORM_ACCESS_KEY_ID not set}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_MOD_PLATFORM_SECRET_ACCESS_KEY not set}"
: "${AWS_SESSION_TOKEN:?AWS_MOD_PLATFORM_SESSION_TOKEN not set}"
: "${AWS_REGION:?AWS_REGION not set}"
: "${S3_KTA_DOCUMENTS_BUCKET:?S3_KTA_DOCUMENTS_BUCKET not set}"
: "${S3_PAGE_BUCKET:?S3_PAGE_BUCKET not set}"
: "${SQS_DOCUMENT_QUEUE:?SQS_DOCUMENT_QUEUE not set}"
: "${SRC_S3_BUCKET:?SRC_S3_BUCKET not set}"
: "${SRC_S3_KEY:?SRC_S3_KEY not set}"

export AWS_ACCESS_KEY_ID="${AWS_MOD_PLATFORM_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY}"
export AWS_SESSION_TOKEN="${AWS_MOD_PLATFORM_SESSION_TOKEN}"

# Define resource names from environment variables
S3_KTA_DOCUMENTS_BUCKET_NAME="${S3_KTA_DOCUMENTS_BUCKET}"
S3_PAGE_BUCKET_NAME="${S3_PAGE_BUCKET}"
SQS_DOCUMENT_QUEUE_NAME="${SQS_DOCUMENT_QUEUE}"

# --- Create S3 Buckets ---
echo "Checking/creating S3 buckets..."
if ! awslocal s3api head-bucket --bucket "${S3_KTA_DOCUMENTS_BUCKET_NAME}" >/dev/null 2>&1; then
  echo "Creating bucket ${S3_KTA_DOCUMENTS_BUCKET_NAME}..."
  awslocal s3 mb "s3://${S3_KTA_DOCUMENTS_BUCKET_NAME}"
else
  echo "Bucket ${S3_KTA_DOCUMENTS_BUCKET_NAME} already exists. Skipping creation."
fi

if ! awslocal s3api head-bucket --bucket "${S3_PAGE_BUCKET_NAME}" >/dev/null 2>&1; then
  echo "Creating bucket ${S3_PAGE_BUCKET_NAME}..."
  awslocal s3 mb "s3://${S3_PAGE_BUCKET_NAME}"
else
  echo "Bucket ${S3_PAGE_BUCKET_NAME} already exists. Skipping creation."
fi

# --- Create SQS Queue ---
echo "Checking/creating SQS queue..."
if ! awslocal sqs get-queue-url --queue-name "${SQS_DOCUMENT_QUEUE_NAME}" >/dev/null 2>&1; then
  echo "Creating queue ${SQS_DOCUMENT_QUEUE_NAME}..."
  awslocal sqs create-queue --queue-name "${SQS_DOCUMENT_QUEUE_NAME}"
else
  echo "Queue ${SQS_DOCUMENT_QUEUE_NAME} already exists. Skipping creation."
fi

# --- Copy sample document from AWS S3 to LocalStack S3 ---

SRC_BUCKET_NAME="${SRC_S3_BUCKET}"
SRC_KEY_PATH="${SRC_S3_KEY}"
DEST_BUCKET_NAME="${S3_KTA_DOCUMENTS_BUCKET_NAME}"
DEST_KEY_PATH="${SRC_S3_KEY}"
TMP_FILE="/tmp/$(basename "${SRC_S3_KEY}")"

echo "Downloading sample document from AWS S3..."
echo "Source S3 URI: s3://${SRC_BUCKET_NAME}/${SRC_KEY_PATH}"
if ! aws s3 cp "s3://${SRC_BUCKET_NAME}/${SRC_KEY_PATH}" "${TMP_FILE}"; then
  echo "ERROR: Failed to download sample document from AWS S3. Check your AWS credentials and network access.
  You may need to update your local-dev-environment/.env file with correct AWS credentials." >&2
  exit 1
fi

echo "Uploading sample document to LocalStack S3..."
echo "Destination S3 URI: s3://${DEST_BUCKET_NAME}/${DEST_KEY_PATH}"
if ! awslocal s3 cp "${TMP_FILE}" "s3://${DEST_BUCKET_NAME}/${DEST_KEY_PATH}"; then
  echo "ERROR: Failed to upload sample document to LocalStack S3." >&2
  exit 1
fi

echo "Listing contents of s3://${DEST_BUCKET_NAME}/$(dirname "${SRC_KEY_PATH}")/ in LocalStack S3:"
awslocal s3 ls "s3://${DEST_BUCKET_NAME}/$(dirname "${SRC_KEY_PATH}")/"

# Clean up temp file
rm -f "${TMP_FILE}"

echo "Sample document copied to LocalStack S3 at s3://${DEST_BUCKET_NAME}/${DEST_KEY_PATH}"

# --- Final Message ---
echo "All LocalStack AWS resources checked/created successfully."
touch /tmp/aws_resources_ready


