"""AWS Client Configuration for Ingestion Pipeline."""

import os

import boto3
from textractor import Textractor

from ingestion_pipeline.config import settings


def get_s3_client():
    """Creates and returns a boto3 S3 client configured for either local or external development environments.

    If the LOCAL_DEVELOPMENT_MODE setting is set to "true" (case-insensitive), the client is configured
    to connect to a local S3-compatible endpoint (e.g., LocalStack) with test credentials.
    Otherwise, the client is configured to connect to AWS S3 using credentials and region specified in settings.

    Returns:
        boto3.client: A configured boto3 S3 client instance.
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
            region_name=settings.AWS_REGION,
        )


def get_textractor_instance():
    """Creates and returns a Textractor instance configured with temporary AWS credentials.

    This function temporarily overrides the AWS credential environment variables with values
    from the application settings to instantiate a Textractor client for the specified AWS region.
    After the client is created, the original environment variables if present are restored to their previous values.

    Returns:
        Textractor: An instance of the Textractor client configured with the specified AWS credentials and region.

    Raises:
        Any exception raised by the Textractor constructor or environment variable manipulation.

    Note:
        This function modifies process-wide environment variables and should be used with caution
        in multi-threaded or multi-process environments.
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
    """Creates and returns a boto3 Textract client configured with credentials from settings."""
    return boto3.client(
        "textract",
        aws_access_key_id=settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
        aws_session_token=getattr(settings, "AWS_MOD_PLATFORM_SESSION_TOKEN", None),
        region_name=settings.AWS_REGION,
    )
