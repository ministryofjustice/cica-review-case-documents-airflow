import logging

from langchain_text_splitters import SentenceTransformersTokenTextSplitter

from ingestion_code.config import settings
from ingestion_code.model import model

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
    # Splitting text to tokens using sentence model tokenizer.
    splitter = SentenceTransformersTokenTextSplitter(
        model_name=settings.MODEL_NAME,
        chunk_overlap=settings.TOKEN_OVERLAP,  # used to retain context across chunks
        tokens_per_chunk=model.max_seq_length,  # set max sequence length
    )

    try:
        logger.info("Splitting page text into chunks.")
        extracted_data = []
        for page_number, page_text in pages:
            chunks = splitter.split_text(page_text)
            extracted_data.append((page_number, page_text, chunks))
        logger.info("Text split into chunks successfully.")
        return extracted_data

    except Exception as e:
        logger.info(f"Error chunking text: {e}")
        exit(1)
