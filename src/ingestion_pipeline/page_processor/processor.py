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

import io
import logging
from typing import List, Tuple

from textractor.entities.document import Document

from ingestion_pipeline.chunking.schemas import DocumentMetadata, DocumentPage
from ingestion_pipeline.config import settings
from ingestion_pipeline.page_processor.image_utils import convert_pdf_to_images
from ingestion_pipeline.page_processor.s3_utils import (
    delete_files_from_s3,
    download_file_from_s3,
    upload_file_to_s3_with_retry,
)
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

logger = logging.getLogger(__name__)


class PageProcessingError(Exception):
    """Raised when page processing fails due to invalid page count."""


class PageProcessor:
    """Processes pages from a Textract Document and builds DocumentPage objects."""

    def __init__(self, s3_client, source_bucket=None, page_bucket=None):
        """Initializes the PageProcessor instance."""
        self.s3_client = s3_client
        self.source_bucket = source_bucket or settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET
        self.page_bucket = page_bucket or settings.AWS_CICA_S3_PAGE_BUCKET

    def _download_pdf_from_s3(self, s3_uri: str) -> bytes:
        """Download the PDF file from the appropriate S3 bucket, depending on environment."""
        if not s3_uri.startswith("s3://"):
            raise ValueError("source_file_s3_uri must be an S3 URI")

        key = s3_uri.split("/", 3)[-1]

        # Choose bucket based on environment
        bucket = self.source_bucket

        logger.info(f"Original S3 URI was '{s3_uri}'")
        logger.info(f"Downloading PDF: Bucket='{bucket}', Key='{key}'")

        return download_file_from_s3(self.s3_client, bucket, key)

    def _delete_uploaded_images(self, s3_keys: list):
        """Delete uploaded images from S3 if a failure occurs."""
        delete_files_from_s3(self.s3_client, self.page_bucket, s3_keys)

    def _generate_and_upload_page_images(
        self, pdf_bytes: bytes, source_doc_id: str, key_prefix: str
    ) -> List[Tuple[str, int, int]]:
        """Generate PNG images for each page and upload to the page bucket, preserving the key prefix."""
        images = convert_pdf_to_images(pdf_bytes)
        s3_uris_and_sizes = []
        uploaded_keys = []
        try:
            for i, image in enumerate(images, start=1):
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                buf.seek(0)
                s3_key = f"{key_prefix}/{source_doc_id}/pages/{i}.png"
                logger.info(f"Uploading page image to Bucket='{self.page_bucket}', Key='{s3_key}'")
                upload_file_to_s3_with_retry(self.s3_client, buf, self.page_bucket, s3_key)
                width, height = image.size
                s3_uri = f"s3://{self.page_bucket}/{s3_key}"
                s3_uris_and_sizes.append((s3_uri, width, height))
                uploaded_keys.append(s3_key)
            return s3_uris_and_sizes
        except Exception as upload_error:
            logger.critical(f"Image upload failed, cleaning up uploaded images: {upload_error}")
            self._delete_uploaded_images(uploaded_keys)
            raise PageProcessingError(f"Failed to upload all page images: {upload_error}")

    def process(self, doc: Document, metadata: DocumentMetadata) -> List[DocumentPage]:
        """Iterate over document pages, generate images, upload to S3, and build DocumentPage objects."""
        logger.info(f"Processing document pages with source_doc_id: {metadata.source_doc_id}")
        pages = []
        page_count = metadata.page_count if metadata.page_count is not None else 0
        if page_count == 0:
            logger.error(f"Page count is zero for document {metadata.source_doc_id}. Aborting page processing.")
            raise PageProcessingError(f"Page count is zero for document {metadata.source_doc_id}.")

        # Download the PDF using the URI from the metadata
        pdf_bytes = self._download_pdf_from_s3(metadata.source_file_s3_uri)

        # Pass the prefix to the upload function
        s3_page_uris_and_sizes = self._generate_and_upload_page_images(
            pdf_bytes, metadata.source_doc_id, metadata.case_ref
        )

        if len(doc.pages) != len(s3_page_uris_and_sizes):
            logger.error(
                f"Mismatch between Textract pages ({len(doc.pages)}) and generated images "
                f"({len(s3_page_uris_and_sizes)}) for document {metadata.source_doc_id}."
            )
            raise PageProcessingError(
                f"Mismatch between Textract pages and generated images for document {metadata.source_doc_id}."
            )

        for idx, page in enumerate(doc.pages):
            identifier = DocumentIdentifier(
                source_file_name=metadata.source_file_name,
                correspondence_type=metadata.correspondence_type,
                case_ref=metadata.case_ref,
                page_num=page.page_num,
            )
            page_id = identifier.generate_uuid()
            s3_page_image_s3_uri, img_width, img_height = s3_page_uris_and_sizes[idx]

            page_doc = DocumentPage(
                source_doc_id=metadata.source_doc_id,
                page_num=page.page_num,
                page_id=page_id,
                page_width=img_width,
                page_height=img_height,
                text=page.text if hasattr(page, "text") else "",
                received_date=metadata.received_date,
                page_count=page_count,
                s3_page_image_s3_uri=s3_page_image_s3_uri,
                correspondence_type=metadata.correspondence_type,
                # Add more fields as needed
            )
            pages.append(page_doc)
        return pages
