#!/usr/bin/env python3
"""Copy source documents from the MOD Platform S3 bucket to the CICA S3 bucket.

This is a one-off operational utility (kept under ``runbooks/`` for now) that
transfers a fixed set of case documents between two different AWS accounts.

Because the source and destination live in separate accounts, a plain
``copy_object`` call will not work (it requires a single set of credentials
with access to both buckets). Instead this script downloads each object using
the source (MOD Platform) credentials and re-uploads it using the destination
(CICA) credentials, streaming through memory.

Configuration is read from the project root ``.env`` file:

Source (MOD Platform):
    AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET  - source bucket name
    AWS_MOD_PLATFORM_ACCESS_KEY_ID
    AWS_MOD_PLATFORM_SECRET_ACCESS_KEY
    AWS_MOD_PLATFORM_SESSION_TOKEN
    SRC_S3_KEY                             - comma-separated list of object keys

Destination (CICA):
    AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET - destination bucket name
    AWS_CICA_AWS_ACCESS_KEY_ID
    AWS_CICA_AWS_SECRET_ACCESS_KEY
    AWS_CICA_AWS_SESSION_TOKEN

Shared:
    AWS_REGION                             - AWS region (defaults to eu-west-2)

Usage:
    # Dry run - list what would be copied without transferring anything
    uv run python runbooks/copy_documents_between_accounts.py --dry-run

    # Perform the copy
    uv run python runbooks/copy_documents_between_accounts.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import dotenv_values

# Project root is one level up from this runbooks/ directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

DEFAULT_REGION = "eu-west-2"


def load_config() -> dict[str, str]:
    """Load configuration values from the project root ``.env`` file.

    Returns:
        A mapping of environment variable names to their values.

    Raises:
        SystemExit: If the ``.env`` file cannot be found.
    """
    if not ENV_PATH.exists():
        sys.exit(f"Could not find .env file at {ENV_PATH}")

    # dotenv_values parses the file without mutating os.environ, which keeps
    # the two credential sets cleanly separated.
    return {k: v for k, v in dotenv_values(ENV_PATH).items() if v is not None}


def require(config: dict[str, str], key: str) -> str:
    """Return a required config value or exit with a helpful message.

    Args:
        config: The loaded configuration mapping.
        key: The environment variable name to look up.

    Returns:
        The value associated with ``key``.

    Raises:
        SystemExit: If the key is missing or empty.
    """
    value = config.get(key)
    if not value:
        sys.exit(f"Missing required value in .env: {key}")
    return value


def parse_keys(raw_keys: str) -> list[str]:
    """Split the comma-separated SRC_S3_KEY value into individual object keys.

    Args:
        raw_keys: The raw comma-separated string from the ``.env`` file.

    Returns:
        A list of trimmed, non-empty object keys.
    """
    return [key.strip() for key in raw_keys.split(",") if key.strip()]


def build_s3_client(
    access_key_id: str,
    secret_access_key: str,
    session_token: str,
    region: str,
):
    """Create a boto3 S3 client scoped to a single account's credentials.

    Args:
        access_key_id: AWS access key ID.
        secret_access_key: AWS secret access key.
        session_token: AWS session token (for temporary credentials).
        region: AWS region name.

    Returns:
        A configured boto3 S3 client.
    """
    session = boto3.session.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        aws_session_token=session_token,
        region_name=region,
    )
    return session.client("s3")


def copy_object(
    source_client,
    destination_client,
    source_bucket: str,
    destination_bucket: str,
    key: str,
) -> None:
    """Stream a single object from the source bucket to the destination bucket.

    The object body is read from the source account and re-uploaded to the
    destination account under the same key.

    Args:
        source_client: boto3 S3 client for the source account.
        destination_client: boto3 S3 client for the destination account.
        source_bucket: Name of the source bucket.
        destination_bucket: Name of the destination bucket.
        key: The object key to copy (used for both source and destination).
    """
    response = source_client.get_object(Bucket=source_bucket, Key=key)
    body = response["Body"].read()
    content_type = response.get("ContentType", "application/octet-stream")

    destination_client.put_object(
        Bucket=destination_bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
    )


def main() -> int:
    """Run the cross-account copy.

    Returns:
        Process exit code: 0 on full success, 1 if any object failed to copy.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the objects that would be copied without transferring them.",
    )
    args = parser.parse_args()

    config = load_config()

    region = config.get("AWS_REGION", DEFAULT_REGION)

    source_bucket = require(config, "AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET")
    destination_bucket = require(config, "AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET")
    keys = parse_keys(require(config, "SRC_S3_KEY"))

    print(f"Source bucket (MOD Platform):   {source_bucket}")
    print(f"Destination bucket (CICA):      {destination_bucket}")
    print(f"Region:                         {region}")
    print(f"Objects to copy:                {len(keys)}")
    print("-" * 70)

    if args.dry_run:
        for key in keys:
            print(f"[dry-run] would copy: {key}")
        print("-" * 70)
        print("Dry run complete. No objects were transferred.")
        return 0

    source_client = build_s3_client(
        require(config, "AWS_MOD_PLATFORM_ACCESS_KEY_ID"),
        require(config, "AWS_MOD_PLATFORM_SECRET_ACCESS_KEY"),
        require(config, "AWS_MOD_PLATFORM_SESSION_TOKEN"),
        region,
    )
    destination_client = build_s3_client(
        require(config, "AWS_CICA_AWS_ACCESS_KEY_ID"),
        require(config, "AWS_CICA_AWS_SECRET_ACCESS_KEY"),
        require(config, "AWS_CICA_AWS_SESSION_TOKEN"),
        region,
    )

    succeeded = 0
    failed: list[str] = []

    for index, key in enumerate(keys, start=1):
        try:
            copy_object(
                source_client,
                destination_client,
                source_bucket,
                destination_bucket,
                key,
            )
            succeeded += 1
            print(f"[{index}/{len(keys)}] copied: {key}")
        except ClientError as error:
            failed.append(key)
            error_code = error.response.get("Error", {}).get("Code", "Unknown")
            print(f"[{index}/{len(keys)}] FAILED ({error_code}): {key}")

    print("-" * 70)
    print(f"Done. {succeeded} copied, {len(failed)} failed.")

    if failed:
        print("Failed keys:")
        for key in failed:
            print(f"  - {key}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
