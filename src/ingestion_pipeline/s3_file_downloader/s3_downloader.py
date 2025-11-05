"""Module for downloading files from S3."""

import logging

import boto3

logger = logging.getLogger(__name__)


def download_pdf_from_s3(bucket_name: str, file_key: str, download_path: str):
    """Downloads a PDF file from an S3 bucket.

    Args:
        bucket_name (str): The name of the S3 bucket.
        file_key (str): The key (path) of the file in the bucket.
            example s2 uri - s3://uat-kta-documents-bucket/25-757332/3034917-20250106094458.pdf
        download_path (str): The local path to save the downloaded file.

    Raises:
        botocore.exceptions.ClientError: If the file is not found
        or another S3 error occurs.
    """
    s3 = boto3.client("s3")
    s3.download_file(bucket_name, file_key, download_path)
    logger.info(f"Successfully downloaded {file_key} from bucket {bucket_name} to {download_path}")
