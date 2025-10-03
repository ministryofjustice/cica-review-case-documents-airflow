import datetime
import json
import logging
import os
from pathlib import Path

from textractor.entities.document import Document

from src.chunking.chunking_config import ChunkingConfig
from src.chunking.schemas import DocumentMetadata
from src.chunking.strategies.key_value.layout_key_value import KeyValueChunker
from src.chunking.strategies.layout_text import LayoutTextChunkingStrategy
from src.chunking.strategies.list.list_chunker import LayoutListChunkingStrategy
from src.chunking.strategies.table.layout_table import LayoutTableChunkingStrategy
from src.chunking.textract import TextractDocumentChunker
from src.indexing.indexer import OpenSearchIndexer
from src.orchestration.pipeline import IndexingOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.info("Running........")

# OpenSearch Connection Details
OS_HOST = "localhost"
OS_PORT = 9200
CHUNK_INDEX_NAME = "case-documents"  # Your index for chunks

# Update this path to your directory containing Textract JSON files
TEXTRACT_JSON_PATH = Path(__file__).parent.parent / "tests/chunking/data/redacted_retrieve_from_s3/case1/"

# This function is now commented out as it's no longer used
# def textract_response():
#     """Loads the sample Textract JSON response from a file."""
#     with open(TEXTRACT_JSON_PATH, "r") as f:
#         return json.load(f)


def process_json_files_in_directory(orchestrator, directory_path):
    """Iterates through JSON files in a directory and processes each one."""
    for filename in os.listdir(directory_path):
        if filename.endswith(".json"):
            file_path = os.path.join(directory_path, filename)
            logging.info(f"Processing file: {file_path}")
            try:
                with open(file_path, "r") as f:
                    textract_response_data = json.load(f)

                test_doc = Document.open(textract_response_data)

                # Create mock metadata (this can be customized per file if needed)
                mock_metadata = DocumentMetadata(
                    ingested_doc_id=filename,  # Using filename as a simple ID
                    source_file_name=filename,
                    page_count=test_doc.num_pages,
                    case_ref="25-111111",
                    received_date=datetime.date(2025, 9, 26),
                    correspondence_type="Letter",
                )

                orchestrator.process_and_index(test_doc, mock_metadata)
            except Exception as e:
                logging.error(f"Failed to process {filename}: {e}")


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

    # 2. Initialize the orchestrator
    orchestrator = IndexingOrchestrator(chunker=chunker, chunk_indexer=chunk_indexer)

    # 3. Call the new function to process all JSON files in the specified directory
    try:
        process_json_files_in_directory(orchestrator, TEXTRACT_JSON_PATH)
    except Exception as e:
        logging.critical(f"Pipeline failed: {e}")


if __name__ == "__main__":
    main()
