"""AWS Textract client and API utilities.

This module handles communication with AWS Textract for document OCR.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import boto3

from .config import settings
from .schemas import WordBlock

if TYPE_CHECKING:
    from mypy_boto3_textract import TextractClient

logger = logging.getLogger(__name__)


def get_textract_client() -> "TextractClient":
    """Create a Textract client using credentials from settings.

    Returns:
        Configured boto3 Textract client.
    """
    return boto3.client(
        "textract",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        aws_session_token=settings.AWS_SESSION_TOKEN,
    )


def analyze_image_sync(
    textract_client: "TextractClient",
    image_path: Path,
) -> dict:
    """Analyze an image using Textract synchronous API.

    Args:
        textract_client: Boto3 Textract client.
        image_path: Path to the image file.

    Returns:
        Raw Textract response dict.

    Raises:
        FileNotFoundError: If image file doesn't exist.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    response = textract_client.detect_document_text(Document={"Bytes": image_bytes})

    return response


def extract_word_blocks(response: dict) -> list[WordBlock]:
    """Extract word blocks from Textract response.

    Args:
        response: Raw Textract response.

    Returns:
        List of WordBlock objects in reading order.
    """
    words = []

    for block in response.get("Blocks", []):
        if block.get("BlockType") != "WORD":
            continue

        bbox = block.get("Geometry", {}).get("BoundingBox", {})
        words.append(
            WordBlock(
                text=block.get("Text", ""),
                text_type=block.get("TextType", "PRINTED"),
                confidence=block.get("Confidence", 0.0),
                bbox_top=bbox.get("Top", 0.0),
                bbox_left=bbox.get("Left", 0.0),
            )
        )

    return words
