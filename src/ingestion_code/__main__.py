import logging

from config import settings
from ingestion_code.chunk_text import (
    chunk_textract_responses_for_bedrock,
)
from ingestion_code.embed_text import (
    # embed_text_with_cohere_model,
    embed_text_with_titan_model,
)
from ingestion_code.index_text import index_textract_text_to_opensearch

# from ingestion_code.extract_text import extract_text_from_pdf
# from ingestion_code.chunk_text import chunk_text_for_local_model
# from ingestion_code.embed_text import embed_text_with_local_model
# from ingestion_code.ocr_text import TextractMode, run_textract_and_upload_responses
from ingestion_code.utils import load_local_jsons, load_s3_jsons

logging.basicConfig(
    filename="ingestion.log",
    filemode="w",
    level=logging.INFO,
    force=True,
    format="%(asctime)s %(levelname)s [%(filename)s:%(funcName)s:%(lineno)d] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting 'main' script")

    # # -- Ingesting PDF with text --

    # # -- Step 1: Extract text from pdf --
    # pdf_filename = "ai-04-00049.pdf"
    # pages = extract_text_from_pdf(pdf_filename)

    # # -- Step 2: Split page text into chunks --
    # chunks = chunk_text_for_local_model(pages)

    # # -- Step 3: Create chunk embeddings --
    # chunks_with_embeddings = embed_text_with_local_model(chunks)

    # # -- Step 4: Index documents to OpenSearch --
    # index_text_to_opensearch(pdf_filename, chunks_with_embeddings)

    # -- Ingesting PDF requiring OCR to extract text --

    # -- Run on AP --
    # -- Step 1: OCR PDFs with Textract and save JSON responses to S3 --
    # run_textract_and_upload_responses(
    #     settings.S3_BUCKET_NAME, settings.S3_PREFIX, TextractMode.TEXT_DETECTION
    # )

    # -- Run on AP or local machine --
    # -- Step 2: Load Textract responses and split text into chunks --
    if settings.LOCAL:
        responses = load_local_jsons("redacted-black")
    else:
        responses = load_s3_jsons(settings.S3_BUCKET_NAME, settings.S3_PREFIX + "/text-detection")
    chunks = chunk_textract_responses_for_bedrock(responses)

    # -- Run on AP or local machine --
    # -- Step 3: Create chunk embeddings --
    # -- Cohere model --
    # chunks_with_embeddings = embed_text_with_cohere_model(chunks)
    # -- Or, Titan model --
    chunks_with_embeddings = embed_text_with_titan_model(chunks)

    # -- Run on local machine --
    # -- Step 4: Index documents to LocalStack OpenSearch --
    index_textract_text_to_opensearch(chunks_with_embeddings)

    logger.info("Script finished.")


# --- Main Execution ---
if __name__ == "__main__":
    main()
