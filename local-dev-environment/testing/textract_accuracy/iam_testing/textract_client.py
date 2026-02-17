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
<<<<<<< HEAD
<<<<<<< HEAD
        aws_access_key_id=settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
        aws_session_token=settings.AWS_MOD_PLATFORM_SESSION_TOKEN,
=======
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        aws_session_token=settings.AWS_SESSION_TOKEN,
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
        aws_access_key_id=settings.AWS_MOD_PLATFORM_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_MOD_PLATFORM_SECRET_ACCESS_KEY,
        aws_session_token=settings.AWS_MOD_PLATFORM_SESSION_TOKEN,
>>>>>>> 435e12b (add/custom_doc_ocr_and_augmentation)
    )


def analyze_image_sync(
    textract_client: "TextractClient",
    image_path: Path,
<<<<<<< HEAD
<<<<<<< HEAD
    use_analyze_api: bool = False,
=======
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
    use_analyze_api: bool = False,
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
) -> dict:
    """Analyze an image using Textract synchronous API.

    Args:
        textract_client: Boto3 Textract client.
        image_path: Path to the image file.
<<<<<<< HEAD
<<<<<<< HEAD
        use_analyze_api: If True, use analyze_document with FORMS feature
            which may improve handwriting detection. Default False uses
            detect_document_text.
=======
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
        use_analyze_api: If True, use analyze_document with FORMS feature
            which may improve handwriting detection. Default False uses
            detect_document_text.
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

    Returns:
        Raw Textract response dict.

    Raises:
        FileNotFoundError: If image file doesn't exist.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    with open(image_path, "rb") as f:
        image_bytes = f.read()

<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
    if use_analyze_api:
        # analyze_document can provide better results for forms with handwriting
        # FeatureTypes: TABLES, FORMS, QUERIES, SIGNATURES, LAYOUT
        response = textract_client.analyze_document(
            Document={"Bytes": image_bytes},
            FeatureTypes=["FORMS"],  # FORMS helps with field/value detection
        )
    else:
        response = textract_client.detect_document_text(Document={"Bytes": image_bytes})
<<<<<<< HEAD
=======
    response = textract_client.detect_document_text(Document={"Bytes": image_bytes})
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

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
