"""Module for processing pages from a Textract Document and constructing DocumentPage objects.

Classes:
    PageProcessor: Processes pages from a Textract Document and builds DocumentPage objects.

Methods:
    PageProcessor.__init__():
        Initializes the PageProcessor instance.

    PageProcessor.process(doc: Document, metadata: DocumentMetadata) -> List[DocumentPage]:
        Iterates over the pages in a Textract Document and constructs DocumentPage objects
        using provided document metadata. Returns a list of DocumentPage instances.
"""

import logging
from typing import List

from textractor.entities.document import Document

from ingestion_pipeline.chunking.schemas import DocumentMetadata, DocumentPage
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

logger = logging.getLogger(__name__)


class PageProcessor:
    """Processes pages from a Textract Document and builds DocumentPage objects."""

    def __init__(self):
        """Initializes the class instance. Currently, no initialization logic is implemented."""
        pass

    def process(self, doc: Document, metadata: DocumentMetadata) -> List[DocumentPage]:
        """Iterate over document pages and build DocumentPage objects."""
        logger.info(f"Processing document pages with source_doc_id: {metadata.source_doc_id}")
        pages = []
        for page in doc.pages:
            identifier = DocumentIdentifier(
                source_file_name=metadata.source_file_name,
                correspondence_type=metadata.correspondence_type,
                case_ref=metadata.case_ref,
                page_num=page.page_num,
            )
            page_id = identifier.generate_uuid()

            page_id = page_id
            page_doc = DocumentPage(
                source_doc_id=metadata.source_doc_id,
                page_num=page.page_num,
                page_id=page_id,
                page_width=page.width,
                page_height=page.height,
                text=page.text if hasattr(page, "text") else "",
                received_date=metadata.received_date,
                # Add more fields as needed
            )
            pages.append(page_doc)
        return pages
