import datetime
import logging
import time
import uuid

import boto3
from textractcaller.t_call import Textract_API, get_full_json
from textractor import Textractor
from textractor.data.constants import TextractFeatures
from textractor.entities.lazy_document import LazyDocument
from textractor.parsers.response_parser import parse

from src.chunking.chunking_config import ChunkingConfig
from src.chunking.schemas import DocumentMetadata
from src.chunking.strategies.key_value.layout_key_value import KeyValueChunker
from src.chunking.strategies.layout_text import LayoutTextChunkingStrategy
from src.chunking.strategies.list.list_chunker import LayoutListChunkingStrategy
from src.chunking.strategies.table.layout_table import LayoutTableChunkingStrategy
from src.chunking.textract import TextractDocumentChunker
from src.config import settings
from src.indexing.indexer import OpenSearchIndexer
from src.orchestration.pipeline import ProcessingPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.info("Processing Textract Responses using S3 bucket location ........")

# OpenSearch Connection Details
OS_HOST = settings.OPENSEARCH_HOST
OS_PORT = settings.OPENSEARCH_PORT
CHUNK_INDEX_NAME = settings.OPENSEARCH_CHUNK_INDEX_NAME
CHUNK_INDEX_UUID_NAMESPACE = settings.CHUNK_INDEX_UUID_NAMESPACE

# --- Configuration for Polling ---
POLL_INTERVAL_SECONDS = settings.TEXTRACT_API_POLL_INTERVAL_SECONDS
JOB_TIMEOUT_SECONDS = settings.TEXTRACT_API_JOB_TIMEOUT_SECONDS

# TODO this will be picked up from a queue in a real world scenario
S3_DOCUMENT_URI = "s3://cica-textract-response-dev/Case1_TC19_50_pages_brain_injury.pdf"


def create_guid_hash(filename, correspondence_type, received_date, case_ref):
    """
    Creates a Version 5 UUID from the given parameters.

    Args:
        filename (str): The name of the source file.
        correspondence_type (str): The correspondence type code.
        received_date (datetime.date): The date the document was received.
        case_ref (str): The case reference number.

    Returns:
        str: A standard UUID string in the format "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx".
    """
    # Create a unique namespace for your application
    # This is a fixed UUID that you define once for your system.
    # TODO This should be a UUID that is generated, is stored as a secret and is kept constant
    NAMESPACE_DOC_INGESTION = uuid.UUID(CHUNK_INDEX_UUID_NAMESPACE)

    data_string = f"{filename}-{correspondence_type}-{received_date.isoformat()}-{case_ref}"

    # Generate a UUID based on the namespace and the data string
    # uuid.uuid5() uses a SHA-1 hash internally.
    return str(uuid.uuid5(NAMESPACE_DOC_INGESTION, data_string))


def get_textractor_document(s3_document_uri) -> LazyDocument:
    """
    Uses the Textractor library to get a parsed document object with layout.
    """
    extractor = Textractor()

    document = extractor.start_document_analysis(
        file_source=s3_document_uri,
        features=[TextractFeatures.LAYOUT],
        save_image=False,
    )

    logging.info(f"retrieved document with layout using Textractor: {document.job_id}")

    return document


# TODO this should be async when the system is scaled up
def process_s3_file(orchestrator, s3_document_uri):
    """
    Processes a document by starting a Textract job and polling for its completion using boto3.
    """

    filename = s3_document_uri.split("/")[-1]
    logging.info(f"Processing file: {filename}")

    lazy_doc = get_textractor_document(s3_document_uri)
    logging.info(f"Started Textract job with JobId: {lazy_doc.job_id}")

    textract_client = boto3.client("textract")
    start_time = time.time()
    job_status = "IN_PROGRESS"

    while job_status == "IN_PROGRESS":
        elapsed_time = time.time() - start_time
        if elapsed_time > JOB_TIMEOUT_SECONDS:
            raise TimeoutError(f"Textract job {lazy_doc.job_id} timed out after {JOB_TIMEOUT_SECONDS} seconds.")

        logging.info(f"Job {lazy_doc.job_id} is IN_PROGRESS. Checking status...")
        response = textract_client.get_document_analysis(JobId=lazy_doc.job_id)
        job_status = response["JobStatus"]

        if job_status == "IN_PROGRESS":
            time.sleep(POLL_INTERVAL_SECONDS)

    if job_status == "SUCCEEDED":
        logging.info(f"Job {lazy_doc.job_id} completed successfully. Fetching full results.")

        # TODO investigate if we should use pagination here
        full_response = get_full_json(
            job_id=lazy_doc.job_id, boto3_textract_client=textract_client, textract_api=Textract_API.ANALYZE
        )
        document_to_process = parse(full_response)

    else:
        logging.error(f"Textract job {lazy_doc.job_id} finished with status: {job_status}")
        return

    try:
        document_id = create_guid_hash(filename, "TC19", datetime.date(2025, 10, 6), "25-111111")
        logging.info(f"Generated 16-digit UUID: {document_id}")

        mock_metadata = DocumentMetadata(
            ingested_doc_id=document_id,
            source_file_name=filename,
            page_count=document_to_process.num_pages,
            case_ref="25-111111",
            received_date=datetime.date(2025, 10, 6),
            correspondence_type="TC19",
        )
        orchestrator.process_and_index(document_to_process, mock_metadata)
    except Exception as e:
        logging.error(f"Failed to process {filename}: {e}")


# TODO this main function is for demo purposes only
# This will be moved to a higher layer when we have a working system
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

    chunker = TextractDocumentChunker(
        strategy_handlers=strategy_handlers,
        config=config,
    )
    chunk_indexer = OpenSearchIndexer(host=OS_HOST, port=OS_PORT, index_name=CHUNK_INDEX_NAME)

    orchestrator = ProcessingPipeline(chunker=chunker, chunk_indexer=chunk_indexer)

    try:
        process_s3_file(orchestrator, S3_DOCUMENT_URI)
    except Exception as e:
        logging.critical(f"Pipeline failed: {e}")


if __name__ == "__main__":
    main()
