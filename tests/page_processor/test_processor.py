from datetime import datetime
from unittest.mock import MagicMock, Mock

import pytest

from ingestion_pipeline.chunking.schemas import DocumentMetadata, DocumentPage
from ingestion_pipeline.page_processor.page_factory import DocumentPageFactory
from ingestion_pipeline.page_processor.processor import (
    PageProcessingError,
    PageProcessor,
)
from ingestion_pipeline.page_processor.s3_document_service import PageImageUploadResult


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
        source_file_s3_uri="s3://bucket/26-711111/file.pdf",
        received_date=datetime(2024, 1, 1),
    )


@pytest.fixture
def mock_s3_document_service():
    service = Mock()
    service.download_pdf.return_value = b"pdfbytes"
    service.upload_page_images.return_value = []
    service.delete_images.return_value = None
    service.page_bucket = "page-bucket"
    return service


@pytest.fixture
def mock_image_converter():
    return Mock()


@pytest.fixture
def mock_page_factory():
    return DocumentPageFactory()


@pytest.fixture
def processor(mock_s3_document_service, mock_image_converter, mock_page_factory):
    return PageProcessor(
        s3_document_service=mock_s3_document_service,
        image_converter=mock_image_converter,
        page_factory=mock_page_factory,
    )


def test_process_success(processor, mock_s3_document_service, mock_image_converter, metadata):
    # Arrange
    mock_image1 = MagicMock()
    mock_image1.size = (100, 200)
    mock_image2 = MagicMock()
    mock_image2.size = (150, 250)
    mock_image_converter.pdf_to_images.return_value = [mock_image1, mock_image2]

    # Mock upload_page_images to return PageImageUploadResult objects
    mock_s3_document_service.upload_page_images.return_value = [
        PageImageUploadResult(
            s3_uri="s3://page-bucket/caseX/doc123/pages/1.png",
            s3_key="caseX/doc123/pages/1.png",
            width=100,
            height=200,
        ),
        PageImageUploadResult(
            s3_uri="s3://page-bucket/caseX/doc123/pages/2.png",
            s3_key="caseX/doc123/pages/2.png",
            width=150,
            height=250,
        ),
    ]

    doc = DummyDocument(2)
    # Act
    pages = processor.process(doc, metadata)

    # Assert
    assert len(pages) == 2
    assert all(isinstance(p, DocumentPage) for p in pages)
    assert pages[0].page_num == 1
    assert pages[1].page_num == 2
    assert pages[0].page_width == 100
    assert pages[1].page_height == 250
    assert pages[0].s3_page_image_s3_uri.endswith("/1.png")
    assert pages[1].s3_page_image_s3_uri.endswith("/2.png")
    assert mock_s3_document_service.upload_page_images.call_count == 1


def test_process_zero_page_count(processor, metadata):
    zero_page_metadata = metadata.model_copy(update={"page_count": 0})
    doc = DummyDocument(0)
    with pytest.raises(PageProcessingError):
        processor.process(doc, zero_page_metadata)


def test_process_page_count_mismatch(processor, mock_image_converter, metadata):
    # 2 pages in doc, 1 image generated
    mock_image1 = MagicMock()
    mock_image1.size = (100, 200)
    mock_image_converter.pdf_to_images.return_value = [mock_image1]
    doc = DummyDocument(2)
    with pytest.raises(PageProcessingError):
        processor.process(doc, metadata)


def test_process_image_upload_failure_triggers_cleanup(
    processor, mock_s3_document_service, mock_image_converter, metadata
):
    mock_image1 = MagicMock()
    mock_image1.size = (100, 200)
    mock_image2 = MagicMock()
    mock_image2.size = (150, 250)
    mock_image_converter.pdf_to_images.return_value = [mock_image1, mock_image2]
    # Simulate upload_page_images raising an exception
    mock_s3_document_service.upload_page_images.side_effect = Exception("upload failed")

    doc = DummyDocument(2)
    with pytest.raises(PageProcessingError) as excinfo:
        processor.process(doc, metadata)
    assert "Image upload failed" in str(excinfo.value) or "Failed to process document pages" in str(excinfo.value)
    assert not mock_s3_document_service.delete_images.called


def test_process_cleanup_failure_raises_enriched_error(
    processor, mock_s3_document_service, mock_image_converter, metadata
):
    mock_image1 = MagicMock()
    mock_image1.size = (100, 200)
    mock_image2 = MagicMock()
    mock_image2.size = (150, 250)
    mock_image_converter.pdf_to_images.return_value = [mock_image1, mock_image2]
    # Simulate upload_page_images raises, and delete_images also raises
    mock_s3_document_service.upload_page_images.side_effect = Exception("upload failed")
    mock_s3_document_service.delete_images.side_effect = Exception("cleanup failed")

    doc = DummyDocument(2)
    with pytest.raises(PageProcessingError) as excinfo:
        processor.process(doc, metadata)
    assert (
        "Failed to process document pages for source_doc_id=doc123, case_ref=caseX, s3_uri=s3://bucket/26-711111/file.pdf"
        in str(excinfo.value)
    )


def test_process_image_upload_failure_triggers_cleanup_on_second_upload(
    processor, mock_s3_document_service, mock_image_converter, metadata
):
    mock_image1 = MagicMock()
    mock_image1.size = (100, 200)
    mock_image2 = MagicMock()
    mock_image2.size = (150, 250)
    mock_image_converter.pdf_to_images.return_value = [mock_image1, mock_image2]

    # Simulate upload_page_images raises after uploading one image
    # We'll simulate this by having upload_page_images return a partial list, then raise
    def upload_page_images_side_effect(images, case_ref, source_doc_id):
        # Simulate uploading the first image, then fail
        raise Exception("upload failed")

    mock_s3_document_service.upload_page_images.side_effect = upload_page_images_side_effect

    doc = DummyDocument(2)
    with pytest.raises(PageProcessingError) as excinfo:
        processor.process(doc, metadata)
    assert "Image upload failed" in str(excinfo.value) or "Failed to process document pages" in str(excinfo.value)
    # Since upload failed immediately, no images were uploaded, so cleanup should not be called
    assert not mock_s3_document_service.delete_images.called
