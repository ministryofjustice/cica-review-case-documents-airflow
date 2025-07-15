import logging

from ingestion_code.model import model

logger = logging.getLogger(__name__)


def embed_text_with_local_model(
    page_chunks: list[tuple[int, str, list[str]]],
) -> list[tuple[int, str, list[str], list[list[float]]]]:
    """
    Chunk extracted text for local embedding models.

    Args:
        pages (list[tuple[int, str]]): Page numbers and page text from a pdf.

    Returns:
        list[tuple[int, str, list[str]]]: A list of (page_number, page_text, chunks).
    """
    try:
        logger.info("Embedding text chunks.")
        extracted_data = []
        for page_number, page_text, chunks in page_chunks:
            embeddings = model.encode(
                chunks, batch_size=32, show_progress_bar=True
            ).tolist()
            extracted_data.append((page_number, page_text, chunks, embeddings))
        logger.info("Text embedded successfully.")

        return extracted_data

    except Exception as e:
        logger.info(f"Error embedding text: {e}")
        exit(1)
