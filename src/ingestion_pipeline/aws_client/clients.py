"""AWS Client Configuration for Ingestion Pipeline."""

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

    Builds an explicitly-credentialed boto3 session and injects its Textract and S3
    clients into the Textractor instance. This avoids mutating process-wide environment
    variables (Textractor otherwise resolves credentials from the boto3 default chain,
    which reads ``AWS_*`` env vars), making this factory safe to call from any thread.

    Returns:
        Textractor: Configured Textractor client instance for the specified AWS region.
    """
    session = boto3.Session(
        aws_access_key_id=settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
        aws_session_token=getattr(settings, "AWS_MOD_PLATFORM_SESSION_TOKEN", None),
        region_name=settings.AWS_REGION,
    )
    textractor = Textractor(region_name=settings.AWS_REGION)
    # Replace the internally-created session/clients (which rely on ambient credentials)
    # with our explicitly-credentialed ones. These attributes are part of Textractor's
    # construction contract; see tests for the guard against a library change.
    textractor.session = session
    textractor.textract_client = session.client("textract", region_name=settings.AWS_REGION)
    textractor.s3_client = session.client("s3", region_name=settings.AWS_REGION)
    return textractor


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
