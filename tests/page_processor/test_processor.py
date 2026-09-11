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


def test_process_image_upload_failure_raises_page_processing_error(
    processor, mock_s3_document_service, mock_image_converter, metadata
):
    """An upload failure is wrapped in PageProcessingError with document context."""
    mock_image1 = MagicMock()
    mock_image1.size = (100, 200)
    mock_image2 = MagicMock()
    mock_image2.size = (150, 250)
    mock_image_converter.pdf_to_images.return_value = [mock_image1, mock_image2]
    mock_s3_document_service.upload_page_images.side_effect = Exception("upload failed")

    doc = DummyDocument(2)
    with pytest.raises(PageProcessingError) as excinfo:
        processor.process(doc, metadata)
    assert (
        "Failed to process document pages for source_doc_id=doc123, case_ref=caseX, "
        "s3_uri=s3://bucket/26-711111/file.pdf" in str(excinfo.value)
    )


def test_process_does_not_clean_up_on_upload_failure(
    processor, mock_s3_document_service, mock_image_converter, metadata
):
    """The processor no longer cleans up images itself.

    Cleanup is centralised in the pipeline's top-level failure handler (prefix-delete),
    so the processor must not call delete_images or delete_page_images on failure.
    """
    mock_image_converter.pdf_to_images.return_value = [MagicMock(), MagicMock()]
    mock_s3_document_service.upload_page_images.side_effect = Exception("upload failed")

    doc = DummyDocument(2)
    with pytest.raises(PageProcessingError, match="Failed to process document pages"):
        processor.process(doc, metadata)

    assert not mock_s3_document_service.delete_images.called
    assert not mock_s3_document_service.delete_page_images.called


def test_process_download_failure_raises_page_processing_error(
    processor, mock_s3_document_service, mock_image_converter, metadata
):
    """A download failure is wrapped in PageProcessingError and no cleanup is attempted."""
    mock_s3_document_service.download_pdf.side_effect = RuntimeError("download failed")

    doc = DummyDocument(2)
    with pytest.raises(PageProcessingError, match="Failed to process document pages"):
        processor.process(doc, metadata)

    mock_image_converter.pdf_to_images.assert_not_called()
    assert not mock_s3_document_service.delete_page_images.called
