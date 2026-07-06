"""Pipeline runner responsible for creating and running the ingestion pipeline.

This module refactors the previous single-document `main()` into smaller pieces:
- `create_pipeline()` — builds a pipeline instance
- `process_message()` — takes a Message and runs it through the pipeline
- `poll_and_process()` — reads messages from a (stubbed) queue and processes them in parallel

The bottom of this file contains a small `MockSQSClient` and example `main()` that
demonstrates parallel processing from a stubbed queue.
"""

import datetime
import json
import logging
import os
import re
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.config import settings
from ingestion_pipeline.custom_logging.log_context import setup_logging, source_doc_id_context
from ingestion_pipeline.indexing.healthcheck import check_opensearch_health
from ingestion_pipeline.pipeline_builder import build_pipeline
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

setup_logging()
logger = logging.getLogger(__name__)


@dataclass
class Message:
    s3_uri: str
    correspondence_type: str
    case_ref: str


class MockSQSClient:
    """A tiny in-memory SQS-like queue for local testing."""

    def __init__(self):
        self._queue = deque()
        self._inflight = {}

    def send_message(self, QueueUrl, MessageBody):
        message_id = str(uuid.uuid4())
        receipt_handle = str(uuid.uuid4())

        message = {
            "MessageId": message_id,
            "ReceiptHandle": receipt_handle,
            "Body": MessageBody,
        }

        self._queue.append(message)

        return {"MessageId": message_id}

    def receive_message(self, QueueUrl, MaxNumberOfMessages=1):
        messages = []

        for _ in range(min(MaxNumberOfMessages, len(self._queue))):
            msg = self._queue.popleft()
            self._inflight[msg["ReceiptHandle"]] = msg

            messages.append(
                {
                    "MessageId": msg["MessageId"],
                    "ReceiptHandle": msg["ReceiptHandle"],
                    "Body": msg["Body"],
                }
            )

        return {"Messages": messages} if messages else {}

    def delete_message(self, QueueUrl, ReceiptHandle):
        if ReceiptHandle in self._inflight:
            del self._inflight[ReceiptHandle]
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

        return {"ResponseMetadata": {"HTTPStatusCode": 404}}


def to_json(message: Message) -> str:
    return json.dumps(message.__dict__)


def from_json(body: str) -> Message:
    payload = json.loads(body)
    return Message(
        s3_uri=payload.get("s3_uri"),
        correspondence_type=payload.get("correspondence_type"),
        case_ref=payload.get("case_ref"),
    )


# /\d{2}[-][78]d{5}/gm
def extract_case_ref(s3_uri: str) -> str:
    """Extract the case_ref from the S3 URI (the folder after the bucket)."""
    parts = s3_uri.replace("s3://", "").split("/")
    if len(parts) >= 2:
        return parts[1]
    return ""


def validate_s3_uri(s3_uri: str, expected_bucket: str) -> bool:
    pattern = rf"^s3://{re.escape(expected_bucket)}/\d{{2}}-[78]\d{{5}}/"
    return re.match(pattern, s3_uri) is not None


def create_pipeline():
    """Create and return a new pipeline instance.

    Separated so callers can choose to build a pipeline per worker/thread.
    """
    return build_pipeline()


def process_message(message: Message, pipeline=None) -> None:
    """Process a single Message through the pipeline.

    This function is safe to call from multiple threads as long as the pipeline
    implementation is thread-safe or each caller supplies its own pipeline.
    """
    pipeline = pipeline or create_pipeline()

    S3_DOCUMENT_URI = message.s3_uri
    case_ref = message.case_ref or extract_case_ref(S3_DOCUMENT_URI)
    correspondence_type = message.correspondence_type

    identifier = DocumentIdentifier(
        source_file_name=S3_DOCUMENT_URI.split("/")[-1],
        correspondence_type=correspondence_type,
        case_ref=case_ref,
    )
    source_doc_id = identifier.generate_uuid()
    logger.info(f"Generated source_doc_id: {source_doc_id} for document: {S3_DOCUMENT_URI}")
    source_doc_id_context.set(source_doc_id)

    try:
        logger.info(f"Validating S3 URI: {S3_DOCUMENT_URI}")
        if not validate_s3_uri(S3_DOCUMENT_URI, settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET):
            logger.critical(f"Invalid S3 URI: {S3_DOCUMENT_URI}")
            raise ValueError(f"Invalid S3 URI: {S3_DOCUMENT_URI}")

        document_metadata = DocumentMetadata(
            source_doc_id=source_doc_id,
            source_file_name=S3_DOCUMENT_URI.split("/")[-1],
            source_file_s3_uri=S3_DOCUMENT_URI,
            page_count=None,
            case_ref=case_ref,
            received_date=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
            correspondence_type=correspondence_type,
        )

        logger.info(f"Starting document processing in pipeline {S3_DOCUMENT_URI}")
        pipeline.process_document(document_metadata=document_metadata)
        logger.info(f"Finished processing document {S3_DOCUMENT_URI}")

    except Exception:
        logger.critical(
            f"Pipeline processing error for source_doc_id={source_doc_id}, case_ref={case_ref}, s3_uri={S3_DOCUMENT_URI}",
            exc_info=True,
        )
        raise
    finally:
        logger.info("Cleaning up context for document")
        source_doc_id_context.set(None)


def poll_and_process(sqs_client, max_workers: int = 4, queue_url: str = "mock-queue") -> None:
    """Poll messages from `sqs_client` and process them in parallel using a thread pool.

    This will continue until the queue is empty (mock client behaviour).
    """
    logger.info("Polling queue and processing messages")

    while True:
        response = sqs_client.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=max_workers)
        messages = response.get("Messages", [])
        if not messages:
            logger.info("No messages available in queue. Exiting poll loop.")
            break

        # Build a pipeline per worker to avoid sharing state unless callers prefer otherwise
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for m in messages:
                body = m["Body"]
                msg_obj = from_json(body)
                pipeline = create_pipeline()
                future = executor.submit(process_message, msg_obj, pipeline)
                futures[future] = m

            for fut in as_completed(futures):
                raw_msg = futures[fut]
                try:
                    fut.result()
                    # delete after successful processing
                    sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=raw_msg["ReceiptHandle"])
                    logger.info(f"Deleted message {raw_msg['MessageId']} from queue")
                except Exception:
                    logger.error(f"Failed to process message {raw_msg['MessageId']}", exc_info=True)


def main():
    local_dev_mode = settings.LOCAL_DEVELOPMENT_MODE
    if local_dev_mode:
        logger.warning("Running in LOCAL_DEVELOPMENT_MODE. Ensure your S3 URI is accessible in LocalStack.")

    logger.info("Pipeline runner started.")
    if not check_opensearch_health(
        settings.OPENSEARCH_PROXY_URL,
        verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
        ssl_assert_hostname=settings.OPENSEARCH_SSL_ASSERT_HOSTNAME,
    ):
        logger.critical("OpenSearch health check failed. Exiting pipeline runner.")
        return

    # Example: stubbed queue with multiple messages
    sqs = MockSQSClient()

    # Compose messages from a comma-separated list. Prefer an env var, fall back to a default.
    csv_override = os.environ.get("SOURCE_DOCUMENTS_CSV", "26-700001/Case1_TC19_50_pages_brain_injury.pdf")

    entries = [e.strip() for e in csv_override.split(",") if e.strip()]
    for entry in entries:
        # Each entry should already be in the form: "{case_ref}/{file_name}"
        s3_uri = f"s3://{settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET}/{entry}"
        case_ref = entry.split("/", 1)[0]
        msg = Message(s3_uri=s3_uri, correspondence_type="TC19 - ADDITIONAL INFO REQUEST", case_ref=case_ref)
        sqs.send_message(QueueUrl="mock-queue", MessageBody=to_json(msg))

    poll_and_process(sqs_client=sqs, max_workers=4, queue_url="mock-queue")


if __name__ == "__main__":
    main()
