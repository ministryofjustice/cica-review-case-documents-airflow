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
    """Creates a Textractor instance backed by explicitly-credentialed boto3 clients.

    Builds a boto3 session from the credentials in settings and overwrites the
    session and Textract/S3 clients that ``Textractor`` creates for itself, so that
    subsequent API calls use those explicit credentials rather than the boto3 default
    chain (which reads ``AWS_*`` env vars).

    Known limitation: the pinned ``textractor`` release has no public API for injecting
    an explicit session or credentials. Its ``__init__`` eagerly builds a session and
    Textract/S3 clients from the default credential chain before we reassign them below,
    and that reassignment relies on undocumented internal attributes
    (``session``/``textract_client``/``s3_client``). Because the default-chain session is
    process-wide mutable state, this does not fully satisfy a thread-safe
    explicit-credential construction contract. boto3 client creation is lazy and does not
    resolve credentials until the first API call, so construction itself does not fail
    when ambient credentials are absent, but the current pipeline relies on credentials
    being present locally. A proper fix (subclassing/vendoring Textractor or an upstream
    injection API) is deferred while the project is paused.

    # TODO(paused-project): revisit once work resumes and the deployment moves off
    #   locally-supplied AWS credentials. Replace the internal-attribute reassignment with
    #   a supported explicit-credential construction path for Textractor.

    Returns:
        Textractor: Configured Textractor client instance for the specified AWS region.
    """
    session = boto3.Session(
        aws_access_key_id=settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
        aws_session_token=getattr(settings, "AWS_MOD_PLATFORM_SESSION_TOKEN", None),
        region_name=settings.AWS_REGION,
    )
    # The pinned Textractor constructor only accepts its own documented arguments and
    # does not take a botocore Config, so we instantiate it with region alone and apply
    # AWS_RETRY_CONFIG on the explicitly-credentialed clients assigned below.
    textractor = Textractor(region_name=settings.AWS_REGION)
    # Overwrite the internally-created session/clients (which rely on the default
    # credential chain) with our explicitly-credentialed ones. These attributes are
    # internal to Textractor; the tests guard against the pinned library changing them.
    textractor.session = session
    textractor.textract_client = session.client("textract", region_name=settings.AWS_REGION, config=AWS_RETRY_CONFIG)
    textractor.s3_client = session.client("s3", region_name=settings.AWS_REGION, config=AWS_RETRY_CONFIG)
    return textractor


def get_sqs_client():
    """Creates a boto3 SQS client configured for local or AWS environments.

    In LOCAL_DEVELOPMENT_MODE, connects to LocalStack at localhost:4566 with test
    credentials. Otherwise, connects to AWS SQS using the MOD Platform credentials and
    region from settings. In both cases the client uses botocore's "standard" retry mode
    for broader transient-error coverage.

    Returns:
        boto3.client: Configured SQS client instance for the appropriate environment.
    """
    local_mode = getattr(settings, "LOCAL_DEVELOPMENT_MODE", False)
    if isinstance(local_mode, str):
        local_mode = local_mode.lower() == "true"

    if local_mode:
        return boto3.client(
            "sqs",
            endpoint_url="http://localhost:4566",
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name=settings.AWS_REGION,
            config=AWS_RETRY_CONFIG,
        )
    else:
        return boto3.client(
            "sqs",
            aws_access_key_id=settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
            aws_session_token=getattr(settings, "AWS_MOD_PLATFORM_SESSION_TOKEN", None),
            region_name=settings.AWS_REGION,
            config=AWS_RETRY_CONFIG,
        )


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
