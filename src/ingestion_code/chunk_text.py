import logging
from typing import Any

from langchain_text_splitters import (
    SentenceTransformersTokenTextSplitter,
    TokenTextSplitter,
)
from textractor.parsers import response_parser

from ingestion_code.config import settings
from ingestion_code.model import get_sentence_transformers_model

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
        model_name=settings.LOCAL_MODEL_NAME,
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


def chunk_textract_responses_for_bedrock(
    responses: list[dict],
) -> list[dict[str, Any]]:
    """
    Chunks the text from Textract responses for Bedrock embedding models.

    Args:
        json_file_paths: Paths to JSON files, each containing at least:
                         { "page_number": int, "text": str }

    Returns:
        A list of (page_number, page_text, chunks), where `chunks`
        is a list of strings, each ≤ your model's token limit.
    """
    # 1) Prepare the splitter with the embedding model’s token settings
    splitter = TokenTextSplitter(
        encoding_name=settings.BEDROCK_TOKENIZER_NAME,
        chunk_size=settings.BEDROCK_CHUNK_SIZE,
        chunk_overlap=settings.TOKEN_OVERLAP,
    )

    # 2) Load each JSON response and chunk its text
    logger.info("Start chunking text in Textract responses")
    docs = []
    for resp in responses:
        document = response_parser.parse(resp)
        for page in document.pages:
            chunks = splitter.split_text(page.text)
            for chunk in chunks:
                docs.append(
                    {
                        "text": chunk,
                        "metadata": {
                            "page": page.page_num,
                            "document_key": resp.get("document_key", ""),
                            "page_count": resp["DocumentMetadata"]["Pages"],
                        },
                    }
                )

    logger.info("Successfully chunked text from %d documents", len(responses))
    return docs
