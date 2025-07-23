from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ingestion_code.extract_text import PDFExtractionError, extract_text_from_pdf

# -- Test extract_text_from_pdf --


# @patch("ingestion_code.paths.get_repo_root")
# @patch("ingestion_code.config.settings")
# def test_extract_text_from_pdf_raises(mock_settings, mock_get_repo_root, tmp_path):
#     """Test raises RuntimeError if text could not be extracted from pdf."""

#     # Simulate repo root and settings
#     mock_get_repo_root.return_value = tmp_path
#     mock_settings.DATA_DIR = "data"

#     # Create test pdf file
#     data_dir = tmp_path / "data"
#     data_dir.mkdir()
#     pdf_file = data_dir / "test.pdf"
#     pdf_file.write_bytes(b"")

#     with pytest.raises(PDFExtractionError):
#         extract_text_from_pdf("test.pdf")


@patch("ingestion_code.extract_text.get_pdf_path")
@patch("ingestion_code.extract_text.PdfReader")
def test_extract_text_success(mock_pdf_reader, mock_get_pdf_path):
    """
    When PdfReader.pages all return valid text, we should get a list of
    (page_number, stripped_text) tuples.
    """
    fake_path = Path("/fake/dir/doc.pdf")
    mock_get_pdf_path.return_value = fake_path

    # Create two fake pages
    page1 = MagicMock()
    page1.extract_text.return_value = "  Hello World  "
    page2 = MagicMock()
    page2.extract_text.return_value = "\nFoo\nBar\n"
    mock_reader = MagicMock()
    mock_reader.pages = [page1, page2]
    mock_pdf_reader.return_value = mock_reader

    result = extract_text_from_pdf("doc.pdf")
    assert result == [
        (1, "Hello World"),
        (2, "Foo\nBar"),
    ]

    # ensure we called PdfReader with the stringified path
    mock_pdf_reader.assert_called_once_with(str(fake_path))


@patch("ingestion_code.extract_text.get_pdf_path")
@patch("ingestion_code.extract_text.PdfReader")
def test_extract_text_open_error(mock_pdf_reader, mock_get_pdf_path):
    """
    If PdfReader(...) itself raises, we should wrap it in PDFExtractionError.
    """
    fake_path = Path("/fake/dir/doesnotopen.pdf")
    mock_get_pdf_path.return_value = fake_path

    # simulate an error opening the PDF
    mock_pdf_reader.side_effect = ValueError("bad file format")

    with pytest.raises(PDFExtractionError) as excinfo:
        extract_text_from_pdf("doesnotopen.pdf")

    assert "Could not open PDF 'doesnotopen.pdf'" in str(excinfo.value)


@patch("ingestion_code.extract_text.get_pdf_path")
@patch("ingestion_code.extract_text.PdfReader")
def test_extract_text_page_error(mock_pdf_reader, mock_get_pdf_path):
    """
    If page.extract_text() on any page raises, we should stop and raise
    a PDFExtractionError indicating the page number.
    """
    fake_path = Path("/fake/dir/badpage.pdf")
    mock_get_pdf_path.return_value = fake_path

    # first page OK, second page blows up
    page1 = MagicMock()
    page1.extract_text.return_value = "All good"
    page2 = MagicMock()
    page2.extract_text.side_effect = RuntimeError("extraction failed")
    mock_reader = MagicMock()
    mock_reader.pages = [page1, page2]
    mock_pdf_reader.return_value = mock_reader

    with pytest.raises(PDFExtractionError) as excinfo:
        extract_text_from_pdf("badpage.pdf")

    # page numbers are 1-based, so the failure is reported on page 2
    assert "Error extracting text on page 2 from badpage.pdf" in str(excinfo.value)
