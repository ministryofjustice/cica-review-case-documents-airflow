#!/bin/bash
set -euo pipefail # Exit immediately if a command exits with a non-zero status or pipe fails

#####################################################################
# TROUBLESHOOTING STEPS
#
# 1. Ensure your AWS credentials are valid and have access to the source S3 bucket/object.
#    - Test with: aws s3 cp s3://cica-textract-response-dev/26-111111/Case1_TC19_50_pages_brain_injury.pdf /tmp/test.pdf
#    - If this fails, check your AWS credentials and permissions.
#
# 2. Ensure awslocal is installed and available in the PATH.
#
# 3. If the sample document is not present in LocalStack S3, check the logs for errors in the download/upload steps.
#
# 4. To verify the file exists in LocalStack S3:
#    - awslocal s3 ls s3://local-kta-documents-bucket/26-111111/
#
# 5. If you see 404 (NoSuchKey) errors, the file was not uploaded to LocalStack S3.
#
#####################################################################

echo "Starting LocalStack AWS resource creation..."

# Load environment variables from LocalStack .env file if it exists
if [ -f /etc/localstack/.env ]; then
  export $(grep -v '^#' /etc/localstack/.env | xargs)
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

export AWS_ACCESS_KEY_ID="${AWS_MOD_PLATFORM_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${AWS_MOD_PLATFORM_SECRET_ACCESS_KEY}"
export AWS_SESSION_TOKEN="${AWS_MOD_PLATFORM_SESSION_TOKEN}"

# Define resource names
S3_KTA_DOCUMENTS_BUCKET="local-kta-documents-bucket"
S3_PAGE_BUCKET="document-page-bucket"
SQS_DOCUMENT_QUEUE="cica-document-search-queue"
AWS_REGION="eu-west-2" # Consistent region

# --- S3 Bucket Creation ---

echo "Checking and creating S3 bucket: ${S3_KTA_DOCUMENTS_BUCKET}..."
# Check if bucket exists. `head-bucket` returns 0 if exists, non-zero if not.
# Redirecting stderr to /dev/null to suppress "Not Found" errors from awslocal.
if ! awslocal s3api head-bucket --bucket "${S3_KTA_DOCUMENTS_BUCKET}" 2>/dev/null; then
  echo "Bucket ${S3_KTA_DOCUMENTS_BUCKET} does not exist. Creating..."
  awslocal s3api create-bucket \
    --bucket "${S3_KTA_DOCUMENTS_BUCKET}" \
    --region "${AWS_REGION}" \
    --create-bucket-configuration LocationConstraint="${AWS_REGION}"
  echo "Bucket ${S3_KTA_DOCUMENTS_BUCKET} created."
else
  echo "Bucket ${S3_KTA_DOCUMENTS_BUCKET} already exists. Skipping creation."
fi

echo "Checking and creating S3 bucket: ${S3_PAGE_BUCKET}..."
if ! awslocal s3api head-bucket --bucket "${S3_PAGE_BUCKET}" 2>/dev/null; then
  echo "Bucket ${S3_PAGE_BUCKET} does not exist. Creating..."
  awslocal s3api create-bucket \
    --bucket "${S3_PAGE_BUCKET}" \
    --region "${AWS_REGION}" \
    --create-bucket-configuration LocationConstraint="${AWS_REGION}"
  echo "Bucket ${S3_PAGE_BUCKET} created."
else
  echo "Bucket ${S3_PAGE_BUCKET} already exists. Skipping creation."
fi

# --- SQS Queue Creation ---

echo "Checking and creating SQS queue: ${SQS_DOCUMENT_QUEUE}..."
# Check if queue exists. `get-queue-url` returns 0 if exists, non-zero if not.
if ! awslocal sqs get-queue-url --queue-name "${SQS_DOCUMENT_QUEUE}" --region "${AWS_REGION}" 2>/dev/null; then
  echo "Queue ${SQS_DOCUMENT_QUEUE} does not exist. Creating..."
  awslocal sqs create-queue \
    --queue-name "${SQS_DOCUMENT_QUEUE}" \
    --region "${AWS_REGION}"
  echo "Queue ${SQS_DOCUMENT_QUEUE} created."
else
  echo "Queue ${SQS_DOCUMENT_QUEUE} already exists. Skipping creation."
fi

# --- Copy sample document from AWS S3 to LocalStack S3 ---

SRC_BUCKET="cica-textract-response-dev"
SRC_KEY="26-111111/Case1_TC19_50_pages_brain_injury.pdf"
DEST_BUCKET="${S3_KTA_DOCUMENTS_BUCKET}"
DEST_KEY="26-111111/Case1_TC19_50_pages_brain_injury.pdf"
TMP_FILE="/tmp/Case1_TC19_50_pages_brain_injury.pdf"

echo "Downloading sample document from AWS S3..."
echo "Source S3 URI: s3://${SRC_BUCKET}/${SRC_KEY}"
if ! aws s3 cp "s3://${SRC_BUCKET}/${SRC_KEY}" "${TMP_FILE}"; then
  echo "ERROR: Failed to download sample document from AWS S3. Check your AWS credentials and network access.
  You may need to update your local-dev-environment/.env file with correct AWS credentials." >&2
  exit 1
fi

echo "Uploading sample document to LocalStack S3..."
echo "Destination S3 URI: s3://${DEST_BUCKET}/${DEST_KEY}"
if ! awslocal s3 cp "${TMP_FILE}" "s3://${DEST_BUCKET}/${DEST_KEY}"; then
  echo "ERROR: Failed to upload sample document to LocalStack S3." >&2
  exit 1
fi

echo "Listing contents of s3://${DEST_BUCKET}/26-111111/ in LocalStack S3:"
awslocal s3 ls "s3://${DEST_BUCKET}/26-111111/"

# Clean up temp file
rm -f "${TMP_FILE}"

echo "Sample document copied to LocalStack S3 at s3://${DEST_BUCKET}/${DEST_KEY}"

# --- Final Message ---
echo "All LocalStack AWS resources checked/created successfully."
touch /tmp/aws_resources_ready


