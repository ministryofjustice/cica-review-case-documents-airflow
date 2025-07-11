import logging
import sys

import boto3

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

s3 = boto3.client(
    service_name="s3",
    aws_access_key_id="test",
    aws_secret_access_key="test",
    endpoint_url="http://localhost:4566",
)

response = s3.list_buckets()
# print(response)


# sqs = boto3.resource("sqs")
# queue = sqs.get_queue_by_name(QueueName="case-document-search-queue")
queue_url = (
    "http://sqs.eu-west-2.localhost.localstack.cloud:4566"
    "/000000000000/cica-document-search-queue"
)

# Create SQS client
sqs = boto3.client(
    "sqs",
    endpoint_url="http://sqs.eu-west-2.localhost.localstack.cloud:4566/"
    "000000000000/cica-document-search-queue",
    region_name="us-west-2",
    aws_access_key_id="dummy",
    aws_secret_access_key="dummy",
)


# Receive message from SQS queue
response = sqs.receive_message(
    QueueUrl=queue_url,
    AttributeNames=["SentTimestamp"],
    MaxNumberOfMessages=1,
    MessageAttributeNames=["All"],
    VisibilityTimeout=0,
    WaitTimeSeconds=0,
)

message = response["Messages"][0]
receipt_handle = message["ReceiptHandle"]

# Delete received message from queue
# sqs.delete_message(
#     QueueUrl=queue_url,
#     ReceiptHandle=receipt_handle
# )


logging.info("Received and deleted message: %s", message)
