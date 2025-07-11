#!/bin/bash
set -euo pipefail # Exit immediately if a command exits with a non-zero status or pipe fails

echo "Starting LocalStack AWS resource creation..."

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

# --- Final Message ---
echo "All LocalStack AWS resources checked/created successfully."
touch /tmp/aws_resources_ready
