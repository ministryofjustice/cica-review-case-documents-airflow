import logging

from ingestion_code.chunk_text import chunk_text_for_local_model
from ingestion_code.embed_text import embed_text_with_local_model
from ingestion_code.extract_text import extract_text_from_pdf
from ingestion_code.index_text import index_text_to_opensearch

logging.basicConfig(
    filename="ingestion.log",
    filemode="w",
    level=logging.INFO,
    force=True,
    format="%(asctime)s %(levelname)s [%(filename)s:%(funcName)s:%(lineno)d] %(name)s: "
    "%(message)s",
)
logger = logging.getLogger(__name__)


def main():
    # Extract text from pdf
    pdf_filename = "ai-04-00049.pdf"
    pages = extract_text_from_pdf(pdf_filename)

    # Split page text into chunks
    chunks = chunk_text_for_local_model(pages)

    # Create chunk embeddings
    chunks_with_embeddings = embed_text_with_local_model(chunks)

    # Index documents to OpenSearch
    index_text_to_opensearch(pdf_filename, chunks_with_embeddings)

    logger.info("Script finished.")


# --- Main Execution ---
if __name__ == "__main__":
    main()
