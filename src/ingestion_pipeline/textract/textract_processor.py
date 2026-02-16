"""This module orchestrates the analysis of documents using AWS Textract.

handles chunking strategies, and indexes the processed content into OpenSearch.
"""

import logging
import time
from urllib.parse import urlparse

from textractcaller.t_call import Textract_API, get_full_json
from textractor import Textractor
from textractor.data.constants import TextractFeatures
from textractor.entities.document import Document
from textractor.parsers.response_parser import parse

from ingestion_pipeline.config import settings

logger = logging.getLogger(__name__)
# OpenSearch Connection Details
CHUNK_INDEX_NAME = settings.OPENSEARCH_CHUNK_INDEX_NAME

# --- Configuration for Polling ---
POLL_INTERVAL_SECONDS = settings.TEXTRACT_API_POLL_INTERVAL_SECONDS
JOB_TIMEOUT_SECONDS = settings.TEXTRACT_API_JOB_TIMEOUT_SECONDS

# Local development mode flag (can be set via environment variable)
LOCAL_DEVELOPMENT_MODE = settings.LOCAL_DEVELOPMENT_MODE


class TextractProcessingError(Exception):
    """Custom exception for Textract processing errors."""


class TextractProcessor:
    """Orchestrates the analysis of a document with AWS Textract."""

    def __init__(
        self,
        textractor: Textractor,
        textract_client,
        timeout_seconds: int = JOB_TIMEOUT_SECONDS,
        poll_interval: int = POLL_INTERVAL_SECONDS,
    ):
        """Initializes the TextractProcessor with required dependencies and configuration.

        Args:
            textractor (Textractor): Instance of Textractor for document analysis.
            textract_client: Boto3 Textract client for API calls.
            timeout_seconds (int, optional): Maximum time to wait for Textract job completion.
                Defaults to JOB_TIMEOUT_SECONDS.
            poll_interval (int, optional): Interval (in seconds) between polling Textract job status.
                Defaults to POLL_INTERVAL_SECONDS.
        """
        self.textractor = textractor
        self.textract_client = textract_client
        self.timeout_seconds = timeout_seconds
        self.poll_interval = poll_interval

    def _start_textract_job(self, s3_document_uri: str) -> str:
        """Starts a Textract document analysis job.

        Args:
            s3_document_uri (str): The S3 URI of the document to analyze.

        Returns:
            str: The unique JobId assigned to the Textract analysis job.
        """
        logger.info(f"Begin Textract job for {s3_document_uri}")
        document = self.textractor.start_document_analysis(
            file_source=s3_document_uri,
            features=[TextractFeatures.LAYOUT],
            save_image=False,
        )
        logger.info(f"Textract Job: {document.job_id}")
        return document.job_id

    def _poll_for_job_completion(self, job_id: str) -> str:
        """Polls Textract until the job completes, fails, or times out.

        Args:
            job_id (str): The unique JobId of the Textract job to monitor.

        Returns:
            str: The final status of the Textract job (e.g., 'SUCCEEDED', 'FAILED', 'PARTIAL_SUCCESS').

        Raises:
            TimeoutError: If the job does not complete within the configured timeout period.
        """
        start_time = time.time()
        while time.time() - start_time < self.timeout_seconds:
            response = self.textract_client.get_document_analysis(JobId=job_id)
            status = response["JobStatus"]
            logger.info(f"Textract Job {job_id} {status}")

            if status in ["SUCCEEDED", "FAILED", "PARTIAL_SUCCESS"]:
                return status

            time.sleep(self.poll_interval)

        raise TimeoutError(f"Textract job {job_id} timed out after {self.timeout_seconds} seconds.")

    def _get_job_results(self, job_id: str) -> Document:
        """Fetches and parses the results of a completed Textract job.

        Args:
            job_id (str): The unique JobId of the completed Textract job.

        Returns:
            Document: The parsed Textractor document containing all detected blocks,
                layout information, and text elements.
        """
        logger.info(f"Fetching results for Textract job {job_id}")
        full_response = get_full_json(
            job_id=job_id, boto3_textract_client=self.textract_client, textract_api=Textract_API.ANALYZE
        )
        return parse(full_response)

    def process_document(self, s3_document_uri: str) -> Document | None:
        """Process and parse a document from S3 using AWS Textract.

        Starts a Textract analysis job, polls until completion, and retrieves the parsed results.
        In LOCAL_DEVELOPMENT_MODE, remaps the S3 URI to use the local development bucket.

        Args:
            s3_document_uri (str): The S3 URI of the document to process
                (e.g., 's3://bucket/path/to/document.pdf').

        Returns:
            Document | None: The parsed Textract document with layout analysis, or None on failure.

        Raises:
            TextractProcessingError: If the Textract job fails or if document processing encounters an error.
        """
        logger.info(f"Processing s3 file: {s3_document_uri}")
        if LOCAL_DEVELOPMENT_MODE:
            parsed = urlparse(s3_document_uri)
            s3_case_bucket_and_file = parsed.path.lstrip("/")
            s3_document_uri = f"s3://{settings.AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET}/{s3_case_bucket_and_file}"
            logger.info(f"Switched s3 file location for local development testing to: {s3_document_uri}")

        try:
            job_id = self._start_textract_job(s3_document_uri)
            final_status = self._poll_for_job_completion(job_id)

            if final_status != "SUCCEEDED":
                logger.error(f"Textract job {job_id} did not succeed. Status: {final_status}")
                raise Exception(f"Textract job {job_id} failed with status: {final_status}")

            document_to_process = self._get_job_results(job_id)

            return document_to_process

        except Exception as e:
            logger.error(f"Failed to process s3 file {s3_document_uri}: {e}")
            raise TextractProcessingError(f"Failed to process document with Textract: {str(e)}") from e
