"""AWS Client Configuration for Ingestion Pipeline."""

import os

import boto3
from textractor import Textractor

from ingestion_pipeline.config import settings


def get_s3_client():
    """Creates a boto3 S3 client configured for local or AWS environments.

    In LOCAL_DEVELOPMENT_MODE, connects to LocalStack at localhost:4566 with test credentials.
    Otherwise, connects to AWS S3 using credentials from settings.

    Returns:
        boto3.client: Configured S3 client instance for the appropriate environment.
    """
    local_mode = getattr(settings, "LOCAL_DEVELOPMENT_MODE", False)
    if isinstance(local_mode, str):
        local_mode = local_mode.lower() == "true"

    if local_mode:
        return boto3.client(
            "s3",
            endpoint_url="http://localhost:4566",
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name=settings.AWS_REGION,
        )
    else:
        return boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_CICA_AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_CICA_AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_CICA_AWS_SESSION_TOKEN,
            region_name=settings.AWS_REGION,
        )


def get_textractor_instance():
    """Creates a Textractor instance with AWS credentials from settings.

    Temporarily sets AWS credential environment variables from settings to instantiate
    the Textractor client, then restores original environment variables. This is required
    because Textractor reads credentials from environment variables.

    Returns:
        Textractor: Configured Textractor client instance for the specified AWS region.

    Warning:
        Modifies process-wide environment variables. Use with caution in multi-threaded
        or multi-process environments.
    """
    # Store original values
    original_env = {
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY"),
        "AWS_SESSION_TOKEN": os.environ.get("AWS_SESSION_TOKEN"),
    }
    try:
        os.environ["AWS_ACCESS_KEY_ID"] = settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID
        os.environ["AWS_SECRET_ACCESS_KEY"] = settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY
        os.environ["AWS_SESSION_TOKEN"] = settings.AWS_MOD_PLATFORM_SESSION_TOKEN
        return Textractor(region_name=settings.AWS_REGION)
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def get_textract_client():
    """Creates a boto3 Textract client configured with credentials from settings.

    Returns:
        boto3.client: Configured Textract client instance for document analysis API calls.
    """
    return boto3.client(
        "textract",
        aws_access_key_id=settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
        aws_session_token=getattr(settings, "AWS_MOD_PLATFORM_SESSION_TOKEN", None),
        region_name=settings.AWS_REGION,
    )
