from pathlib import Path
from typing import List, Tuple

from pypdf import PdfReader


def extract_text_from_pdf(pdf_filename: str) -> List[Tuple[int, str]]:
    """
    Extracts text from each page of a PDF file.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        List[Tuple[int, str]]: A list of (page_number, page_text) tuples.
    """
    pdf_path = Path("../data/", pdf_filename)
    if not pdf_path.exists() or not pdf_path.suffix.lower() == ".pdf":
        raise FileNotFoundError(f"Invalid PDF path: {pdf_path}")

    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
            if text:
                pages.append((i + 1, text.strip()))  # 1-based page numbering
        except Exception as e:
            print(f"Failed to extract text from page {i + 1}: {e}")
            continue

    return pages
