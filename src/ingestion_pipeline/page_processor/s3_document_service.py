"""Service class for S3 document operations."""

import io
from dataclasses import dataclass
from typing import Any, List

from ingestion_pipeline.page_processor.s3_utils import (
    delete_files_from_s3,
    download_file_from_s3,
    upload_file_to_s3_with_retry,
)


@dataclass
class PageImageUploadResult:
    """Represents the result of uploading a page image to S3.

    Attributes:
        s3_uri (str): The full S3 URI where the image is stored.
        s3_key (str): The S3 object key for the uploaded image.
        width (int): The width of the uploaded image in pixels.
        height (int): The height of the uploaded image in pixels.
    """

    s3_uri: str
    s3_key: str
    width: int
    height: int


class S3DocumentService:
    """Handles S3 operations for document processing."""

    def __init__(self, s3_client: Any, source_bucket: str, page_bucket: str):
        """Initialize the S3DocumentService.

        Args:
            s3_client (Any): The S3 client instance.
            source_bucket (str): The S3 bucket for source documents.
            page_bucket (str): The S3 bucket for page images.
        """
        self.s3_client = s3_client
        self.source_bucket = source_bucket
        self.page_bucket = page_bucket

    def download_pdf(self, s3_uri: str) -> bytes:
        """Download a PDF file from the source S3 bucket."""
        if not s3_uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI: {s3_uri!r} (expected to start with 's3://')")
        key = s3_uri.split("/", 3)[-1]
        try:
            return download_file_from_s3(self.s3_client, self.source_bucket, key)
        except Exception as e:
            raise RuntimeError(
                f"Failed to download PDF from S3. Bucket='{self.source_bucket}', Key='{key}', S3 URI='{s3_uri}'."
            ) from e

    def upload_page_images(
        self,
        images: List[Any],
        case_ref: str,
        source_doc_id: str,
    ) -> List[PageImageUploadResult]:
        """Uploads images to S3 and returns a list of PageImageUploadResult."""
        results = []
        for i, image in enumerate(images, start=1):
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            buf.seek(0)
            s3_key = f"{case_ref}/{source_doc_id}/pages/{i}.png"
            self._upload_image(buf, s3_key)
            width, height = image.size
            s3_uri = f"s3://{self.page_bucket}/{s3_key}"
            results.append(PageImageUploadResult(s3_uri, s3_key, width, height))
        return results

    def _upload_image(self, buf: Any, s3_key: str) -> None:
        """Upload an image buffer to the page S3 bucket."""
        try:
            upload_file_to_s3_with_retry(self.s3_client, buf, self.page_bucket, s3_key)
        except Exception as e:
            raise RuntimeError(f"Failed to upload image to S3. Bucket='{self.page_bucket}', Key='{s3_key}'.") from e

    def delete_images(self, s3_keys: List[str]) -> None:
        """Delete images from the page S3 bucket."""
        try:
            delete_files_from_s3(self.s3_client, self.page_bucket, s3_keys)
        except Exception as e:
            raise RuntimeError(f"Failed to delete images from S3. Bucket='{self.page_bucket}', Keys={s3_keys}.") from e
