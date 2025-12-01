import datetime
from unittest import mock

import pytest

from ingestion_pipeline.chunking.schemas import DocumentMetadata, DocumentPage
from ingestion_pipeline.page_processer.processor import PageProcessor


@pytest.fixture
def mock_page():
    page = mock.Mock()
    page.page_num = 1
    page.width = 800
    page.height = 600
    page.text = "Sample page text"
    return page


@pytest.fixture
def mock_document(mock_page):
    doc = mock.Mock()
    doc.pages = [mock_page]
    return doc


@pytest.fixture
def metadata():
    return DocumentMetadata(
        case_ref="CASE123",
        source_doc_id="DOC456",
        source_file_name="sample.pdf",
        source_file_s3_uri="s3://bucket/sample.pdf",
        received_date=datetime.datetime(2025, 1, 15, 12, 0, 0),
        correspondence_type="letter",
    )


def test_process_single_page(mock_document, metadata):
    processor = PageProcessor()
    result = processor.process(mock_document, metadata)
    assert isinstance(result, list)
    assert len(result) == 1
    page = result[0]
    assert isinstance(page, DocumentPage)
    assert page.source_doc_id == "DOC456"
    assert page.page_num == 1
    assert page.page_id == "s3://bucket/CASE123/DOC456/page_images/page_1.png"
    assert page.page_width == 800
    assert page.page_height == 600
    assert page.text == "Sample page text"


def test_process_multiple_pages(metadata):
    page1 = mock.Mock(page_num=1, width=800, height=600, text="Text 1")
    page2 = mock.Mock(page_num=2, width=1024, height=768, text="Text 2")
    doc = mock.Mock()
    doc.pages = [page1, page2]
    processor = PageProcessor()
    result = processor.process(doc, metadata)
    assert len(result) == 2
    assert result[0].page_num == 1
    assert result[1].page_num == 2
    assert result[0].text == "Text 1"
    assert result[1].text == "Text 2"


def test_process_page_without_text(metadata):
    page = mock.Mock(page_num=3, width=500, height=400)
    delattr(page, "text")
    doc = mock.Mock()
    doc.pages = [page]
    processor = PageProcessor()
    result = processor.process(doc, metadata)
    assert result[0].text == ""
