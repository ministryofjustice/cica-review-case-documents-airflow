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
from ingestion_pipeline.indexing.indexer import OpenSearchIndexer
from ingestion_pipeline.orchestration.pipeline import ChunkAndIndexPipeline
from ingestion_pipeline.uuid_generators.document_uuid import generate_uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# OpenSearch Connection Details
OS_HOST = settings.OPENSEARCH_HOST
OS_PORT = settings.OPENSEARCH_PORT
CHUNK_INDEX_NAME = settings.OPENSEARCH_CHUNK_INDEX_NAME

# --- Configuration for Polling ---
POLL_INTERVAL_SECONDS = settings.TEXTRACT_API_POLL_INTERVAL_SECONDS
JOB_TIMEOUT_SECONDS = settings.TEXTRACT_API_JOB_TIMEOUT_SECONDS

# TODO this will be picked up from a queue in a real world scenario
# you can add your own S3 document URI here for testing
S3_DOCUMENT_URI = "s3://cica-textract-response-dev/Case1_TC19_50_pages_brain_injury.pdf"


class TextractProcessor:
    """
    Orchestrates the analysis of a document with AWS Textract, from job submission
    to final processing and indexing.
    """

    def __init__(
        self,
        textractor: Textractor,
        textract_client,
        timeout_seconds: int = JOB_TIMEOUT_SECONDS,
        poll_interval: int = POLL_INTERVAL_SECONDS,
    ):
        self.textractor = textractor
        self.textract_client = textract_client
        self.timeout_seconds = timeout_seconds
        self.poll_interval = poll_interval

    def _start_textract_job(self, s3_document_uri: str) -> str:
        """Starts a Textract analysis job and returns the JobId."""
        logging.info(f"Starting Textract job for {s3_document_uri}")
        document = self.textractor.start_document_analysis(
            file_source=s3_document_uri,
            features=[TextractFeatures.LAYOUT],
            save_image=False,
        )
        logging.info(f"Started Textract job with JobId: {document.job_id}")
        return document.job_id

    def _poll_for_job_completion(self, job_id: str) -> str:
        """Polls Textract until the job completes, fails, or times out."""
        start_time = time.time()
        while time.time() - start_time < self.timeout_seconds:
            response = self.textract_client.get_document_analysis(JobId=job_id)
            status = response["JobStatus"]
            logging.info(f"Job {job_id} status is {status}.")

            if status in ["SUCCEEDED", "FAILED", "PARTIAL_SUCCESS"]:
                return status

            time.sleep(self.poll_interval)

        raise TimeoutError(f"Textract job {job_id} timed out after {self.timeout_seconds} seconds.")

    def _get_job_results(self, job_id: str) -> Document:
        """Fetches the full JSON result for a completed Textract job."""
        logging.info(f"Fetching full results for job {job_id}.")
        full_response = get_full_json(
            job_id=job_id, boto3_textract_client=self.textract_client, textract_api=Textract_API.ANALYZE
        )
        return parse(full_response)

    def process_document(self, s3_document_uri: str) -> Document | None:
        """
        Public method to fetch and parse a document from S3 using Textract.
        Returns a tuple of (Document, DocumentMetadata) on success, or None on failure.
        """

        logging.info(f"Processing s3 file: {s3_document_uri}")

        try:
            job_id = self._start_textract_job(s3_document_uri)
            final_status = self._poll_for_job_completion(job_id)

            if final_status != "SUCCEEDED":
                logging.error(f"Textract job {job_id} did not succeed. Status: {final_status}")
                raise Exception(f"Textract job {job_id} failed with status: {final_status}")

            document_to_process = self._get_job_results(job_id)

            return document_to_process

        except Exception as e:
            logging.error(f"Failed to process s3 file {s3_document_uri}: {e}")
            raise


# TODO this main function is just for demo purposes
# it will be replaced by an orchestrator
def main():
    """Main function to set up and run the indexing pipeline."""
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
    chunk_indexer = OpenSearchIndexer(host=OS_HOST, port=OS_PORT, index_name=CHUNK_INDEX_NAME)

    # 1. Instantiate dependencies
    textractor_instance = Textractor()
    boto3_textract_client = boto3.client("textract")
    chunk_and_index_pipeline = ChunkAndIndexPipeline(chunker=chunker, chunk_indexer=chunk_indexer)

    # 2. Instantiate the processor with its dependencies
    textract_processor = TextractProcessor(
        textractor=textractor_instance,
        textract_client=boto3_textract_client,
    )

    # 3. Run the jobs, handling exceptions as needed
    try:
        logging.info("Step 1: Fetching and parsing document with Textract...")
        result = textract_processor.process_document(S3_DOCUMENT_URI)

        # Step 2: If successful, pass the document to the next pipeline stage
        if result:
            logging.info("Step 2: Chunking and indexing the document content...")
            document = result
            filename = S3_DOCUMENT_URI.split("/")[-1]
            document_id = generate_uuid(filename, "TC19", datetime.date(2025, 10, 6), "25-111111")
            logging.debug(f"Generated 16-digit UUID: {document_id}")

            metadata = DocumentMetadata(
                ingested_doc_id=document_id,
                source_file_name=filename,
                page_count=document.num_pages,
                case_ref="25-111111",
                received_date=datetime.date(2025, 10, 6),
                correspondence_type="TC19",
            )
            chunk_and_index_pipeline.process_and_index(document, metadata)
            logging.info("Pipeline completed successfully.")
        else:
            logging.warning("Document processing failed, skipping chunking and indexing.")
            raise Exception(f"Document processing returned None for {S3_DOCUMENT_URI}")

    except Exception as e:
        logging.critical(f"Pipeline failed: {e}")


if __name__ == "__main__":
    main()
logging.info(f"Processing S3 document {S3_DOCUMENT_URI}........")
