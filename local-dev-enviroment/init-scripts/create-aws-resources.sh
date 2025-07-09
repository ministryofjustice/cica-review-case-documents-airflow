#!/bin/bash

# Create an OpenSearch domain
S3_KTA_DOCUMENTS_BUCKET=local-kta-documents-bucket
S3_PAGE_BUCKET=document-page-bucket
SQS_DOCUMENT_QUEUE=cica-document-search-queue

awslocal s3api create-bucket --bucket ${S3_KTA_DOCUMENTS_BUCKET} --region eu-west-2 --create-bucket-configuration LocationConstraint=eu-west-2
awslocal s3api create-bucket --bucket ${S3_PAGE_BUCKET} --region eu-west-2 --create-bucket-configuration LocationConstraint=eu-west-2

awslocal sqs create-queue --queue-name ${SQS_DOCUMENT_QUEUE} --region eu-west-2 

echo "LocalStack AWS resources created."



awslocal sqs create-queue --queue-name cica-document-search-queue
