"""AWS Client Configuration for Ingestion Pipeline."""

import boto3
from boto3.session import Config
from textractor import Textractor

from ingestion_pipeline.config import settings

# Use botocore's "standard" retry mode instead of the default "legacy" mode. Standard
# mode retries a broader set of throttling and transient errors (e.g. SlowDown,
# InternalError, 5xx). For S3 this reduces the chance those failures surface as per-key
# errors in a DeleteObjects response and leave orphaned page images behind; for Textract
# it improves resilience to throttling during OCR calls.
AWS_RETRY_CONFIG = Config(retries={"max_attempts": 5, "mode": "standard"})
# Kept as an alias for readability at S3 call sites and backwards compatibility.
S3_RETRY_CONFIG = AWS_RETRY_CONFIG


def get_s3_client():
    """Creates a boto3 S3 client configured for local or AWS environments.

    In LOCAL_DEVELOPMENT_MODE, connects to LocalStack at localhost:4566 with test credentials.
    Otherwise, connects to AWS S3 using credentials from settings. In both cases the client
    uses botocore's "standard" retry mode for broader transient-error coverage.

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
            config=S3_RETRY_CONFIG,
        )
    else:
        return boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_CICA_AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_CICA_AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_CICA_AWS_SESSION_TOKEN,
            region_name=settings.AWS_REGION,
            config=S3_RETRY_CONFIG,
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
    textractor.textract_client = session.client("textract", region_name=settings.AWS_REGION, config=AWS_RETRY_CONFIG)
    textractor.s3_client = session.client("s3", region_name=settings.AWS_REGION, config=AWS_RETRY_CONFIG)
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
        config=AWS_RETRY_CONFIG,
    )
