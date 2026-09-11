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
from typing import List, Optional

from textractor.entities.document import Document

from ingestion_pipeline.chunking.schemas import DocumentMetadata, DocumentPage
from ingestion_pipeline.errors import DlqCategory, PipelineError
from ingestion_pipeline.page_processor.image_converter import ImageConverter
from ingestion_pipeline.page_processor.page_factory import DocumentPageFactory
from ingestion_pipeline.page_processor.s3_document_service import S3DocumentService

logger = logging.getLogger(__name__)


class PageProcessingError(PipelineError):
    """Raised when page processing fails (invalid page count, upload failure, or page/image mismatch).

    Page processing failures may be transient (S3/upload issues) or structural
    (page count mismatch); treated as retryable so a redrive can be attempted.
    """

    category = DlqCategory.PAGE_PROCESSING_FAILED
    retryable = True


class PageProcessor:
    """Processes pages from a Textract Document and builds DocumentPage objects."""

    def __init__(
        self,
        s3_document_service: S3DocumentService,
        image_converter: ImageConverter,
        page_factory: Optional[DocumentPageFactory] = None,
    ):
        """Initializes the PageProcessor instance.

        Args:
            s3_document_service (S3DocumentService): Service for S3 operations.
            image_converter (ImageConverter): Service for PDF-to-image conversion.
            page_factory (Optional[DocumentPageFactory]): Factory for DocumentPage creation.
        """
        self.s3_document_service = s3_document_service
        self.image_converter = image_converter
        self.page_factory = page_factory or DocumentPageFactory()

    def process(self, doc: Document, metadata: DocumentMetadata) -> List[DocumentPage]:
        """Iterate over document pages, generate images, upload to S3, and build DocumentPage objects.

        Args:
            doc (Document): The Textract Document to process.
            metadata (DocumentMetadata): Metadata associated with the document.

        Raises:
            PageProcessingError: If the page count is zero, if image upload fails, or if
                there is a mismatch between Textract pages and generated images.

        Note:
            This method does not clean up any page images it may have partially uploaded
            before failing. Cleanup is centralised in the pipeline's top-level failure
            handler, which prefix-deletes all page images for the document
            (``{case_ref}/{source_doc_id}/pages/``). This keeps cleanup correct
            regardless of how far the (sequential or future parallel) upload progressed.

        Returns:
            List[DocumentPage]: A list of DocumentPage instances.
        """
        logger.info("Processing document pages")
        source_doc_id = metadata.source_doc_id
        case_ref = metadata.case_ref
        s3_uri = metadata.source_file_s3_uri
        page_count = metadata.page_count if metadata.page_count is not None else 0
        if page_count == 0:
            raise PageProcessingError.from_metadata(
                f"Page count is zero for document {source_doc_id} (case_ref={case_ref}).",
                metadata,
            )

        try:
            pdf_bytes = self.s3_document_service.download_pdf(s3_uri)
            images = self.image_converter.pdf_to_images(pdf_bytes)
            uploaded_results = self.s3_document_service.upload_page_images(images, case_ref, source_doc_id)
        except Exception as e:
            raise PageProcessingError.from_metadata(
                f"Failed to process document pages for source_doc_id={source_doc_id}, "
                f"case_ref={case_ref}, s3_uri={s3_uri}",
                metadata,
            ) from e

        if len(doc.pages) != len(uploaded_results):
            raise PageProcessingError.from_metadata(
                f"Mismatch between Textract pages ({len(doc.pages)}) and generated images "
                f"({len(uploaded_results)}) for document {source_doc_id} (case_ref={case_ref}).",
                metadata,
            )
        pages = []
        for idx, page in enumerate(doc.pages):
            result = uploaded_results[idx]
            page_doc = self.page_factory.create(metadata, page, result.s3_uri, result.width, result.height)
            pages.append(page_doc)
        return pages
