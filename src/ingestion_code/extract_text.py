import logging
from typing import List, Tuple

from pypdf import PdfReader

from ingestion_code.paths import get_pdf_path

logger = logging.getLogger(__name__)


class PDFExtractionError(RuntimeError):
    """Raised when text extraction from PDF pages fails."""


def extract_text_from_pdf(pdf_filename: str) -> List[Tuple[int, str]]:
    """
    Extracts text from each page of a PDF file with text.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        List[Tuple[int, str]]: A list of (page_number, page_text) tuples.
    """
    pdf_path = get_pdf_path(pdf_filename)
    logger.info("Starting text extraction from pdf.")
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as e:
        logger.exception("Failed to open PDF %s", pdf_filename)
        raise PDFExtractionError(f"Could not open PDF '{pdf_filename}'") from e
    pages = []
    for page_num, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text()
            pages.append((page_num, text.strip()))
        except Exception as e:
            logger.exception("Failed to extract text from page %s.", page_num)
            raise PDFExtractionError(
                f"Error extracting text on page {page_num} from {pdf_filename}."
            ) from e
    logger.info("Successfully extracted text from pdf pages.")

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
