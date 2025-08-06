import json
import logging
from pathlib import Path

from botocore.exceptions import ClientError

from ingestion_code.aws_clients import s3
from ingestion_code.config import settings

logger = logging.getLogger(__name__)


def get_repo_root() -> Path:
    """Get the path of the root of the repository."""
    # 1. Walk up from this module’s file
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists():
            logger.debug("Found repo root at %s", parent)
            return parent

    # 2. If we get here, no .git folder was found
    message = f"Could not find .git in {current} or any of its parents."
    logger.error(message)
    raise RuntimeError(message)


def get_local_pdf_path(pdf_filename: str) -> Path:
    """Get the path of the pdf stored in the data directory given it's filename.

    Args:
        pdf_filename (str): pdf filename.

    Returns:
        Path: The path to the pdf file.
    """

    repo_root = get_repo_root()
    pdf_path = repo_root / settings.DATA_DIR / pdf_filename

    if not pdf_path.is_file() or not pdf_path.suffix.lower() == ".pdf":
        raise FileNotFoundError(f"Invalid PDF path: {pdf_path}")

    return pdf_path


def load_local_jsons(folder_name: str) -> list[dict]:
    """
    Return a list of all .json file paths in data/{folder_name}/extracted/
    """
    repo_root = get_repo_root()
    base_dir = repo_root / settings.DATA_DIR / folder_name

    # If you only want the top‐level files, otherwise use rglob
    json_file_paths = [str(p) for p in base_dir.glob("*.json") if p.is_file()]

    if not json_file_paths:
        msg = "No JSON files found under %r"
        logger.error(msg, base_dir)
        raise FileNotFoundError(msg, base_dir)

    data = []
    for path in json_file_paths:
        with open(path, "r", encoding="utf-8") as f:
            data.append(json.load(f))

    return data


def get_s3_keys(bucket: str, prefix: str, extension: str) -> list[str]:
    """Return all keys under the given bucket/prefix with the given extension."""
    keys = []
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.lower().endswith(extension):
                    keys.append(key)
    except ClientError as e:
        msg = f"Failed to fetch from s3://{bucket}/{prefix}"
        logger.exception(msg)
        raise ClientError(msg) from e

    if not keys:
        raise FileNotFoundError(
            f"No '{extension}' files found at s3://{bucket}/{prefix}"
        )

    return keys


def load_s3_jsons(bucket: str, prefix: str) -> list[dict]:
    """
    Load JSON files from S3 and return them as a Python dictionary.
    """
    responses = []
    json_keys = get_s3_keys(bucket, prefix, ".json")
    for key in json_keys:
        try:
            resp = s3.get_object(Bucket=bucket, Key=key)
            # Load directly from the streaming body
            responses.append(json.load(resp["Body"]))

        except ClientError as e:
            msg = f"Failed to fetch s3://{bucket}/{key}"
            logger.exception(msg)
            raise ClientError(msg) from e
        except json.JSONDecodeError as e:
            msg = f"Failed to parse JSON from s3://{bucket}/{key}: {e}"
            logger.exception(msg)
            raise ClientError(msg) from e

    return responses
