import logging
from typing import List, Tuple

from pypdf import PdfReader

from ingestion_code.utils.paths import get_pdf_path

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_filename: str) -> List[Tuple[int, str]]:
    """
    Extracts text from each page of a PDF file with text.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        List[Tuple[int, str]]: A list of (page_number, page_text) tuples.
    """
    logger.info("Extracting text from pdf pages.")
    pdf_path = get_pdf_path(pdf_filename)
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
            if text:
                pages.append((i + 1, text.strip()))  # 1-based page numbering
        except Exception as e:
            logger.info(f"Failed to extract text from page {i + 1}: {e}")
            continue
    logger.info("Finished extracting text from pdf pages.")

    return pages


def count_pages_in_pdf(pdf_filename: str) -> int:
    """
    Counts the number of pages in a pdf.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        int: The number of pages in the pdf
    """
    pdf_path = get_pdf_path(pdf_filename)
    reader = PdfReader(str(pdf_path))
    return reader.get_num_pages()
