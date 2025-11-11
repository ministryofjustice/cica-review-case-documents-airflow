"""This module orchestrates the analysis of documents using AWS Textract.

handles chunking strategies, and indexes the processed content into OpenSearch.
"""

import datetime
import logging
import time

import boto3
from textractcaller.t_call import Textract_API, get_full_json
from textractor import Textractor
from textractor.data.constants import TextractFeatures
from textractor.entities.document import Document
from textractor.parsers.response_parser import parse

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.schemas import DocumentMetadata
from ingestion_pipeline.chunking.strategies.key_value.layout_key_value import KeyValueChunker
from ingestion_pipeline.chunking.strategies.layout_text import LayoutTextChunkingStrategy
from ingestion_pipeline.chunking.strategies.list.list_chunker import LayoutListChunkingStrategy
from ingestion_pipeline.chunking.strategies.table.layout_table import LayoutTableChunkingStrategy
from ingestion_pipeline.chunking.textract import DocumentChunker
from ingestion_pipeline.config import settings
from ingestion_pipeline.custom_logging.log_context import setup_logging, source_doc_id_context
from ingestion_pipeline.indexing.healthcheck import check_opensearch_health
from ingestion_pipeline.indexing.indexer import OpenSearchIndexer
from ingestion_pipeline.orchestration.pipeline import ChunkAndIndexPipeline
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

# TODO move this to main once we have an orchestrator
setup_logging()
log = logging.getLogger(__name__)

# OpenSearch Connection Details
CHUNK_INDEX_NAME = settings.OPENSEARCH_CHUNK_INDEX_NAME

# --- Configuration for Polling ---
POLL_INTERVAL_SECONDS = settings.TEXTRACT_API_POLL_INTERVAL_SECONDS
JOB_TIMEOUT_SECONDS = settings.TEXTRACT_API_JOB_TIMEOUT_SECONDS

# TODO this will be picked up from a queue in a real world scenario
# you can add your own S3 document URI here for testing
S3_DOCUMENT_URI = "s3://cica-textract-response-dev/Case1_TC19_50_pages_brain_injury.pdf"


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
        """Starts a Textract analysis job and returns the JobId.

        Args:
            s3_document_uri (str): The S3 URI of the document to process.

        Returns:
            str: The JobId of the started Textract job.
        """
        log.info(f"Begin Textract job for {s3_document_uri}")
        document = self.textractor.start_document_analysis(
            file_source=s3_document_uri,
            features=[TextractFeatures.LAYOUT],
            save_image=False,
        )
        log.info(f"Textract Job: {document.job_id}")
        return document.job_id

    def _poll_for_job_completion(self, job_id: str) -> str:
        """Polls Textract until the job completes, fails, or times out.

        Args:
            job_id (str): The JobId of the Textract job to poll.

        Raises:
            TimeoutError: If the job does not complete within the timeout period.

        Returns:
            str: The final status of the Textract job.
        """
        start_time = time.time()
        while time.time() - start_time < self.timeout_seconds:
            response = self.textract_client.get_document_analysis(JobId=job_id)
            status = response["JobStatus"]
            log.info(f"Textract Job {job_id} {status}")

            if status in ["SUCCEEDED", "FAILED", "PARTIAL_SUCCESS"]:
                return status

            time.sleep(self.poll_interval)

        raise TimeoutError(f"Textract job {job_id} timed out after {self.timeout_seconds} seconds.")

    def _get_job_results(self, job_id: str) -> Document:
        """Fetches the results of a completed Textract job.

        Args:
            job_id (str): The JobId of the Textract job to fetch results for.

        Returns:
            Document: The parsed document containing the Textract job results.
        """
        log.info(f"Fetching results for Textract job {job_id}")
        full_response = get_full_json(
            job_id=job_id, boto3_textract_client=self.textract_client, textract_api=Textract_API.ANALYZE
        )
        return parse(full_response)

    def process_document(self, s3_document_uri: str) -> Document | None:
        """Process and parse a document from S3 using Textract.

        Args:
            s3_document_uri (str): The S3 URI of the document to process.

        Returns:
            Document: Document, or None on failure.
        """
        log.info(f"Processing s3 file: {s3_document_uri}")

        try:
            job_id = self._start_textract_job(s3_document_uri)
            final_status = self._poll_for_job_completion(job_id)

            if final_status != "SUCCEEDED":
                log.error(f"Textract job {job_id} did not succeed. Status: {final_status}")
                raise Exception(f"Textract job {job_id} failed with status: {final_status}")

            document_to_process = self._get_job_results(job_id)

            return document_to_process

        except Exception as e:
            log.error(f"Failed to process s3 file {s3_document_uri}: {e}")
            raise


# TODO this main function is just for demo purposes
# it will be replaced by an orchestrator
def main():
    """Main function to set up and run the indexing pipeline."""
    # Health check for OpenSearch
    if not check_opensearch_health(settings.OPENSEARCH_PROXY_URL):
        raise RuntimeError("OpenSearch cluster is not healthy. Exiting.")

    config = ChunkingConfig()

    layout_text_strategy = LayoutTextChunkingStrategy(config)
    layout_table_strategy = LayoutTableChunkingStrategy(config)
    layout_key_value_strategy = KeyValueChunker(config)
    layout_list_strategy = LayoutListChunkingStrategy(config)

    strategy_handlers = {
        "LAYOUT_TEXT": layout_text_strategy,
        "LAYOUT_HEADER": layout_text_strategy,
        "LAYOUT_TITLE": layout_text_strategy,
        "LAYOUT_TABLE": layout_table_strategy,
        "LAYOUT_SECTION_HEADER": layout_text_strategy,
        "LAYOUT_FOOTER": layout_text_strategy,
        "LAYOUT_FIGURE": layout_table_strategy,
        "LAYOUT_KEY_VALUE": layout_key_value_strategy,
        "LAYOUT_LIST": layout_list_strategy,
    }

    chunker = DocumentChunker(
        strategy_handlers=strategy_handlers,
        config=config,
    )

    chunk_indexer = OpenSearchIndexer(index_name=CHUNK_INDEX_NAME, proxy_url=settings.OPENSEARCH_PROXY_URL)

    # 1. Instantiate dependencies
    textractor_instance = Textractor()
    boto3_textract_client = boto3.client("textract", settings.AWS_REGION)
    chunk_and_index_pipeline = ChunkAndIndexPipeline(chunker=chunker, chunk_indexer=chunk_indexer)

    # 2. Instantiate the processor with its dependencies
    textract_processor = TextractProcessor(
        textractor=textractor_instance,
        textract_client=boto3_textract_client,
    )

    # 3. Run the jobs, handling exceptions as needed
    try:
        identifier = DocumentIdentifier(
            source_file_name="source_document.pdf", correspondence_type="TC19", case_ref="25-111111"
        )

        source_doc_id = identifier.generate_uuid()
        log.debug(f"Generated 16-digit UUID: {source_doc_id}")
        source_doc_id_context.set(source_doc_id)

        result = textract_processor.process_document(S3_DOCUMENT_URI)

        # Step 2: If successful, pass the document to the next pipeline stage
        if result:
            document = result
            filename = S3_DOCUMENT_URI.split("/")[-1]

            metadata = DocumentMetadata(
                source_doc_id=source_doc_id,
                source_file_name=filename,
                page_count=document.num_pages,
                case_ref="25-111111",
                # TODO this should be the actual received date from metadata
                received_date=datetime.datetime.now(),
                correspondence_type="TC19",
            )
            chunk_and_index_pipeline.process_and_index(document, metadata)
        else:
            log.warning("Document processing failed, skipping chunking and indexing.")
            raise Exception(f"Document processing returned None for {S3_DOCUMENT_URI}")

    except Exception as e:
        log.critical(f"Pipeline failed: {e}")

    finally:
        log.info("Pipeline execution finished.")
        source_id_to_remove = source_doc_id_context.get()
        log.info("Cleaning up context.")
        source_doc_id_context.set(None)  # ✓ This ALWAYS runs, even after exception
        log.info(f"{source_id_to_remove} Context cleanup complete.")


if __name__ == "__main__":
    main()
