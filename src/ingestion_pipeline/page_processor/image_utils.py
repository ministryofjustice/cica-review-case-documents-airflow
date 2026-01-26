"""Utility functions for image processing within the ingestion pipeline."""

from pdf2image import convert_from_bytes


def convert_pdf_to_images(pdf_bytes):
    """Converts a PDF file (provided as bytes) into a list of image objects, one per page.

    Args:
        pdf_bytes (bytes): The PDF file data in bytes.

    Returns:
        list: A list of image objects representing each page of the PDF.

    Raises:
        PDFPageCountError: If the PDF cannot be read or is invalid.
        PDFSyntaxError: If the PDF is malformed.
    """
    return convert_from_bytes(pdf_bytes)
