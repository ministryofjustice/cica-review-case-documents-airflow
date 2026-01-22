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
import os
from typing import List, Tuple

import boto3
from pdf2image import convert_from_bytes
from textractor.entities.document import Document

from ingestion_pipeline.chunking.schemas import DocumentMetadata, DocumentPage
from ingestion_pipeline.uuid_generators.document_uuid import DocumentIdentifier

logger = logging.getLogger(__name__)

# Bucket for storing generated page images
AWS_S3_PAGE_BUCKET = "document-page-bucket"
AWS_S3_PAGE_BUCKET_URI = f"s3://{AWS_S3_PAGE_BUCKET}"

# Bucket for sourcing the original PDF in the local environment
LOCAL_SOURCE_DOCUMENT_BUCKET = "local-kta-documents-bucket"

# S3 client setup for LocalStack
s3_client = boto3.client(
    "s3",
    endpoint_url=os.getenv("AWS_S3_ENDPOINT_URL", "http://localhost:4566"),
    aws_access_key_id="test",
    aws_secret_access_key="test",
    region_name="eu-west-2",
)


class PageProcessingError(Exception):
    """Raised when page processing fails due to invalid page count."""


class PageProcessor:
    """Processes pages from a Textract Document and builds DocumentPage objects."""

    def _download_pdf_from_s3(self, s3_uri: str) -> bytes:
        """Download the PDF file from the local S3 bucket, using the key from the provided URI."""
        if not s3_uri.startswith("s3://"):
            raise ValueError("source_file_s3_uri must be an S3 URI")

        # Extract the full key (everything after the bucket name)
        # e.g., "cica-textract-response-dev/26-111111/Case1.pdf" -> "26-111111/Case1.pdf"
        key = s3_uri.split("/", 3)[-1]

        logger.info(f"Original S3 URI was '{s3_uri}'")
        logger.info(f"Downloading PDF from LocalStack: Bucket='{LOCAL_SOURCE_DOCUMENT_BUCKET}', Key='{key}'")

        pdf_obj = s3_client.get_object(Bucket=LOCAL_SOURCE_DOCUMENT_BUCKET, Key=key)
        return pdf_obj["Body"].read()

    def _generate_and_upload_page_images(
        self, pdf_bytes: bytes, source_doc_id: str, key_prefix: str
    ) -> List[Tuple[str, int, int]]:
        """Generate PNG images for each page and upload to the page bucket, preserving the key prefix."""
        images = convert_from_bytes(pdf_bytes)
        s3_uris_and_sizes = []
        for i, image in enumerate(images, start=1):
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            buf.seek(0)

            # Construct the key with the original prefix (e.g., "26-111111")
            # This results in a path like: "26-111111/<source_doc_id>/pages/1.png"
            s3_key = f"{key_prefix}/{source_doc_id}/pages/{i}.png"

            logger.info(f"Uploading page image to Bucket='{AWS_S3_PAGE_BUCKET}', Key='{s3_key}'")
            s3_client.upload_fileobj(buf, AWS_S3_PAGE_BUCKET, s3_key, ExtraArgs={"ContentType": "image/png"})

            width, height = image.size
            s3_uri = f"{AWS_S3_PAGE_BUCKET_URI}/{s3_key}"
            s3_uris_and_sizes.append((s3_uri, width, height))
        return s3_uris_and_sizes

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

        # Extract the prefix from the original key to maintain structure.
        # e.g., "s3://.../26-111111/Case1.pdf" -> "26-111111"
        original_key = metadata.source_file_s3_uri.split("/", 3)[-1]
        key_prefix = os.path.dirname(original_key)

        # Pass the prefix to the upload function
        s3_page_uris_and_sizes = self._generate_and_upload_page_images(pdf_bytes, metadata.source_doc_id, key_prefix)

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
