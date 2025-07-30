import json
import logging

from langchain_text_splitters import (
    SentenceTransformersTokenTextSplitter,
    TokenTextSplitter,
)

from ingestion_code.config import settings
from ingestion_code.model import get_sentence_transformers_model
from ingestion_code.paths import get_json_paths

logger = logging.getLogger(__name__)


def chunk_text_for_local_model(
    pages: list[tuple[int, str]],
) -> list[tuple[int, str, list[str]]]:
    """
    Chunk extracted text for local embedding models.

    Args:
        pages (list[tuple[int, str]]): Page numbers and page text from a pdf.

    Returns:
        list[tuple[int, str, list[str]]]: A list of (page_number, page_text, chunks).
    """
    model = get_sentence_transformers_model()
    # Splitting text to tokens using sentence model tokenizer.
    splitter = SentenceTransformersTokenTextSplitter(
        model_name=settings.MODEL_NAME,
        chunk_overlap=settings.TOKEN_OVERLAP,  # used to retain context across chunks
        tokens_per_chunk=model.max_seq_length,  # set max sequence length
    )
    extracted_data = []
    for page_number, page_text in pages:
        try:
            logger.debug("Chunking page %s", page_number)
            chunks = splitter.split_text(page_text)
            extracted_data.append((page_number, page_text, chunks))
        except Exception as e:
            logger.exception("Failed to chunk page: %s", page_number)
            raise RuntimeError("Error with chunking pages") from e

    logger.info("Pages chunked successfully.")
    return extracted_data


def chunk_text_for_bedrock(
    folder_name: str,
) -> list[tuple[int, str, list[str]]]:
    """
    Reads local JSON page files and splits each page’s text into
    token chunks sized for your Bedrock embedding model.

    Args:
        json_file_paths: Paths to JSON files, each containing at least:
                         { "page_number": int, "text": str }

    Returns:
        A list of (page_number, page_text, chunks), where `chunks`
        is a list of strings, each ≤ your model’s token limit.
    """
    json_file_paths = get_json_paths(folder_name)

    # 1) Prepare the splitter with your model’s token settings
    splitter = TokenTextSplitter(
        encoding_name=settings.BEDROCK_TOKENIZER_NAME,
        chunk_size=settings.BEDROCK_CHUNK_SIZE,
        chunk_overlap=settings.TOKEN_OVERLAP,
    )

    extracted_data = []

    # 2) Load each JSON page and chunk its text
    for path in json_file_paths:
        with open(path, "r", encoding="utf-8") as f:
            page = json.load(f)

        page_number = page["page_number"]
        text = page.get("text", "")

        try:
            logger.debug("Chunking page %d from %r", page_number, path)
            chunks = splitter.split_text(text)
            extracted_data.append((page_number, text, chunks))
        except Exception as e:
            logger.exception("Failed to chunk page %d", page_number)
            raise RuntimeError(f"Error chunking page {page_number}") from e

    logger.info("Successfully chunked %d pages", len(extracted_data))
    return extracted_data
