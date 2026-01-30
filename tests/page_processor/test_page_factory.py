import datetime

from ingestion_pipeline.chunking.schemas import DocumentMetadata, DocumentPage
from ingestion_pipeline.page_processor.page_factory import DocumentPageFactory


class DummyPage:
    def __init__(self, page_num, text="Some text"):
        self.page_num = page_num
        self.text = text


def test_create_document_page_all_fields():
    factory = DocumentPageFactory()
    metadata = DocumentMetadata(
        source_doc_id="doc123",
        source_file_name="file.pdf",
        correspondence_type="typeA",
        case_ref="caseX",
        page_count=2,
        source_file_s3_uri="s3://bucket/26-711111/file.pdf",
        received_date=datetime.datetime(2024, 1, 1),
    )
    page = DummyPage(page_num=1, text="Hello world")
    s3_uri = "s3://bucket/caseX/doc123/pages/1.png"
    img_width = 100
    img_height = 200

    doc_page = factory.create(metadata, page, s3_uri, img_width, img_height)

    assert isinstance(doc_page, DocumentPage)
    assert doc_page.source_doc_id == "doc123"
    assert doc_page.page_num == 1
    assert doc_page.page_width == 100
    assert doc_page.page_height == 200
    assert doc_page.text == "Hello world"
    assert doc_page.s3_page_image_s3_uri == s3_uri
    assert doc_page.correspondence_type == "typeA"
    assert doc_page.page_count == 2
    assert doc_page.received_date == datetime.datetime(2024, 1, 1)


def test_create_document_page_missing_text():
    factory = DocumentPageFactory()
    metadata = DocumentMetadata(
        source_doc_id="doc456",
        source_file_name="file2.pdf",
        correspondence_type="typeB",
        case_ref="caseY",
        page_count=1,
        source_file_s3_uri="s3://bucket/26-711111/file2.pdf",
        received_date=datetime.datetime(2024, 2, 2),
    )

    class PageNoText:
        def __init__(self, page_num):
            self.page_num = page_num

    page = PageNoText(page_num=2)
    s3_uri = "s3://bucket/caseY/doc456/pages/2.png"
    img_width = 150
    img_height = 250

    doc_page = factory.create(metadata, page, s3_uri, img_width, img_height)

    assert isinstance(doc_page, DocumentPage)
    assert doc_page.text == ""  # Should default to empty string if no text attribute


def test_create_document_page_unique_page_id():
    factory = DocumentPageFactory()
    metadata = DocumentMetadata(
        source_doc_id="doc789",
        source_file_name="file3.pdf",
        correspondence_type="typeC",
        case_ref="caseZ",
        page_count=3,
        source_file_s3_uri="s3://bucket/26-711111/file3.pdf",
        received_date=datetime.datetime(2024, 3, 3),
    )
    page = DummyPage(page_num=3, text="Page 3 text")
    s3_uri = "s3://bucket/caseZ/doc789/pages/3.png"
    img_width = 200
    img_height = 300

    doc_page1 = factory.create(metadata, page, s3_uri, img_width, img_height)
    doc_page2 = factory.create(metadata, page, s3_uri, img_width, img_height)
    # The page_id should be deterministic for the same input
    assert doc_page1.page_id == doc_page2.page_id
    assert isinstance(doc_page1.page_id, str)
