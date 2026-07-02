"""Discover evaluation cases available in the source S3 bucket.

Lists case folders under the configured prefix and returns their case refs and
PDF filenames. Used by the multi-case evaluation pipeline to determine which
cases are available for indexing and evaluation.

S3 bucket structure assumed::

    s3://<bucket>/<case_ref>/<filename>.pdf

Credentials are sourced from ``ingestion_pipeline.config.settings`` (the
``AWS_MOD_PLATFORM_*`` fields), matching the same credential set used by the
ingestion pipeline for Textract and source-document access.
"""

import sys
from dataclasses import dataclass

import boto3

from ingestion_pipeline.config import settings

# Prefix for the 30 dev/UAT evaluation cases.
# Scoped to "26-700" to exclude test fixtures (the 26-711111 series).
EVALUATION_CASE_PREFIX = "26-700"


@dataclass(frozen=True)
class CaseSpec:
    """A discovered evaluation case with its S3 location.

    Attributes:
        case_ref: The case reference stored on indexed chunks (e.g. ``"26-700001"``).
        s3_filename: The PDF filename within the case folder (e.g.
            ``"Case1_TC19_50_pages_brain_injury.pdf"``).
    """

    case_ref: str
    s3_filename: str


def _get_s3_client() -> boto3.client:
    """Create a boto3 S3 client using the MOD Platform credentials from settings."""
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
        aws_session_token=settings.AWS_MOD_PLATFORM_SESSION_TOKEN,
    )


def discover_cases(
    bucket: str | None = None,
    prefix: str = EVALUATION_CASE_PREFIX,
) -> list[CaseSpec]:
    """Discover evaluation cases in the source S3 bucket.

    Lists all PDF objects under ``prefix`` and returns one :class:`CaseSpec`
    per case folder. Each case folder is expected to contain exactly one PDF;
    if a folder has multiple PDFs the first one in lexicographic key order is
    used.

    Args:
        bucket: S3 bucket name. Defaults to
            ``settings.AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET``
            (``"mod-platform-sandbox-kta-documents-bucket"`` in local dev).
        prefix: S3 key prefix to scope the listing. Defaults to
            :data:`EVALUATION_CASE_PREFIX` (``"26-700"``), which targets the
            30 dev/UAT evaluation cases and excludes test fixtures.

    Returns:
        List of :class:`CaseSpec` objects sorted by ``case_ref``.

    Raises:
        botocore.exceptions.ClientError: If the bucket is not accessible with
            the configured credentials.
    """
    if bucket is None:
        bucket = settings.AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET

    s3 = _get_s3_client()
    paginator = s3.get_paginator("list_objects_v2")

    cases: dict[str, str] = {}  # case_ref -> first pdf filename
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            parts = obj["Key"].split("/")
            if len(parts) >= 2 and parts[1].endswith(".pdf"):
                case_ref = parts[0]
                filename = parts[1]
                # setdefault keeps the first PDF found per case (S3 returns keys
                # in lexicographic order, so this is the alphabetically first PDF).
                cases.setdefault(case_ref, filename)

    return [CaseSpec(case_ref=ref, s3_filename=fn) for ref, fn in sorted(cases.items())]


if __name__ == "__main__":
    """Run standalone to list all discoverable evaluation cases."""
    import logging

    logging.basicConfig(level=logging.WARNING)
    cases = discover_cases()
    if not cases:
        sys.stdout.write("No cases found.\n")
    else:
        for case in cases:
            sys.stdout.write(f"{case.case_ref}: {case.s3_filename}\n")
        sys.stdout.write(f"\nTotal: {len(cases)} cases\n")
