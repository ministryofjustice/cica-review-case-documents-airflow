import io
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from ingestion_pipeline.chunking.schemas import DocumentMetadata, DocumentPage
from ingestion_pipeline.page_processor.processor import (
    PageProcessingError,
    PageProcessor,
)


class DummyPage:
    def __init__(self, page_num, text="Some text"):
        self.page_num = page_num
        self.text = text


class DummyDocument:
    def __init__(self, num_pages):
        self.pages = [DummyPage(i + 1) for i in range(num_pages)]


@pytest.fixture
def metadata():
    return DocumentMetadata(
        source_doc_id="doc123",
        source_file_name="file.pdf",
        correspondence_type="typeA",
        case_ref="caseX",
        page_count=2,
        source_file_s3_uri="s3://bucket/26-111111/file.pdf",
        received_date=datetime(2024, 1, 1),
    )


@pytest.fixture
def processor():
    return PageProcessor()


@patch("ingestion_pipeline.page_processor.processor.s3_client")
@patch("ingestion_pipeline.page_processor.processor.convert_from_bytes")
def test_process_success(mock_convert, mock_s3, processor, metadata):
    # Mock S3 download
    mock_s3.get_object.return_value = {"Body": io.BytesIO(b"pdfbytes")}
    # Mock PDF to image conversion
    mock_image1 = MagicMock()
    mock_image1.size = (100, 200)
    mock_image2 = MagicMock()
    mock_image2.size = (150, 250)
    mock_convert.return_value = [mock_image1, mock_image2]
    # Mock upload
    mock_s3.upload_fileobj.return_value = None

    doc = DummyDocument(2)
    pages = processor.process(doc, metadata)

    assert len(pages) == 2
    assert all(isinstance(p, DocumentPage) for p in pages)
    assert pages[0].page_num == 1
    assert pages[1].page_num == 2
    assert pages[0].page_width == 100
    assert pages[1].page_height == 250
    assert pages[0].s3_page_image_s3_uri.endswith("/1.png")
    assert pages[1].s3_page_image_s3_uri.endswith("/2.png")


@patch("ingestion_pipeline.page_processor.processor.s3_client")
def test_process_zero_page_count(mock_s3, processor, metadata):
    zero_page_metadata = metadata.model_copy(update={"page_count": 0})
    doc = DummyDocument(0)
    with pytest.raises(PageProcessingError):
        processor.process(doc, zero_page_metadata)


@patch("ingestion_pipeline.page_processor.processor.s3_client")
@patch("ingestion_pipeline.page_processor.processor.convert_from_bytes")
def test_process_page_count_mismatch(mock_convert, mock_s3, processor, metadata):
    # 2 pages in doc, 1 image generated
    mock_s3.get_object.return_value = {"Body": io.BytesIO(b"pdfbytes")}
    mock_image1 = MagicMock()
    mock_image1.size = (100, 200)
    mock_convert.return_value = [mock_image1]
    doc = DummyDocument(2)
    with pytest.raises(PageProcessingError):
        processor.process(doc, metadata)


@patch("ingestion_pipeline.page_processor.processor.s3_client")
def test_download_pdf_from_s3_invalid_uri(mock_s3, processor):
    with pytest.raises(ValueError):
        processor._download_pdf_from_s3("not-an-s3-uri")
