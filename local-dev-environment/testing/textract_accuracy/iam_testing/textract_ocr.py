"""Run Textract OCR on IAM handwriting dataset images.

This module processes images through AWS Textract and separates the output
by TextType (PRINTED vs HANDWRITING) for comparison with ground truth.

Post-processing Steps:
    1. Separate words by TextType (PRINTED vs HANDWRITING)
    2. Filter IAM dataset header from printed text ("Sentence Database", form ID)
    3. Filter IAM dataset footer ("Name:") and signatures
    4. Normalize text for comparison

Usage:
    python -m iam_testing.textract_ocr
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from .config import settings
from .iam_filters import (
    filter_iam_header_footer,
    filter_iam_signature,
<<<<<<< HEAD
<<<<<<< HEAD
=======
    normalize_text,
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)
)
from .schemas import OCRResult
from .textract_client import (
    analyze_image_sync,
    extract_word_blocks,
    get_textract_client,
)

logger = logging.getLogger(__name__)


def _lowest_quartile_mean(values: list[float]) -> float:
    """Calculate the mean of the lowest quartile of values.

    This helps identify problem areas by focusing on low-confidence words.

    Args:
        values: List of confidence values.

    Returns:
        Mean of the lowest 25% of values, or 0.0 if empty.
    """
    if not values:
        return 0.0
    sorted_values = sorted(values)
    quartile_size = max(1, len(sorted_values) // 4)
    lowest_quartile = sorted_values[:quartile_size]
    return mean(lowest_quartile)


def process_single_image(
    textract_client,
    image_path: Path,
    form_id: str,
    filter_header: bool = True,
) -> OCRResult:
    """Process a single image and return OCR result.

    Args:
        textract_client: Boto3 Textract client.
        image_path: Path to the image file.
        form_id: Form identifier.
        filter_header: Whether to filter IAM header/footer from printed text.

    Returns:
        OCRResult with separated printed and handwriting text.
    """
    logger.info("Processing image: %s", form_id)

    response = analyze_image_sync(textract_client, image_path)
    words = extract_word_blocks(response)

    # Separate by text type
    printed_words = [w for w in words if w.text_type == "PRINTED"]
    handwriting_words = [w for w in words if w.text_type == "HANDWRITING"]

    # Store raw printed text before filtering
    raw_printed_text = " ".join(w.text for w in printed_words)

    # Apply header/footer filtering if requested
    name_label_top: float | None = None
    if filter_header:
        printed_words, name_label_top = filter_iam_header_footer(printed_words)
        handwriting_words = filter_iam_signature(handwriting_words, name_label_top)

<<<<<<< HEAD
<<<<<<< HEAD
    # Build text strings (raw, normalization happens at comparison time)
    printed_text = " ".join(w.text for w in printed_words)
    handwriting_text = " ".join(w.text for w in handwriting_words)
=======
    # Build text strings
    printed_text = normalize_text(" ".join(w.text for w in printed_words))
    handwriting_text = normalize_text(" ".join(w.text for w in handwriting_words))
>>>>>>> 919a38c (feat(CICADS-579): add IAM handwriting OCR accuracy testing module)
=======
    # Build text strings (raw, normalization happens at comparison time)
    printed_text = " ".join(w.text for w in printed_words)
    handwriting_text = " ".join(w.text for w in handwriting_words)
>>>>>>> 57f41ff (feat: add clinical OCR prompts v2.4/v2.5 for CICA documents)

    # Calculate lowest quartile confidence (identifies problem areas)
    print_confidences = [w.confidence for w in printed_words]
    hw_confidences = [w.confidence for w in handwriting_words]
    avg_print_conf = _lowest_quartile_mean(print_confidences)
    avg_hw_conf = _lowest_quartile_mean(hw_confidences)

    return OCRResult(
        form_id=form_id,
        ocr_print_text=printed_text,
        ocr_print_text_raw=raw_printed_text,
        ocr_handwriting_text=handwriting_text,
        ocr_print_word_count=len(printed_words),
        ocr_handwriting_word_count=len(handwriting_words),
        avg_print_confidence=round(avg_print_conf, 2),
        avg_handwriting_confidence=round(avg_hw_conf, 2),
        textract_job_id=None,
        processed_at=datetime.now(timezone.utc).isoformat(),
    )


def write_ocr_result(result: OCRResult, output_path: Path) -> None:
    """Append OCR result to a JSONL file.

    Args:
        result: OCRResult object.
        output_path: Path to the JSONL output file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "a", encoding="utf-8") as f:
        json.dump(asdict(result), f, ensure_ascii=False)
        f.write("\n")

    logger.info("Appended OCR result for %s to %s", result.form_id, output_path)


def _display_results(result: OCRResult) -> None:
    """Display OCR results to console (for CLI testing).

    Args:
        result: OCRResult object to display.
    """
    separator = "=" * 60
    logger.info("\n%s", separator)
    logger.info("Form ID: %s", result.form_id)
    logger.info("Processed: %s", result.processed_at)
    logger.info("%s", separator)

    max_preview = 150

    logger.info("\n--- PRINTED TEXT (filtered: %d words) ---", result.ocr_print_word_count)
    logger.info("Avg Confidence: %s%%", result.avg_print_confidence)
    preview = result.ocr_print_text[:max_preview] if result.ocr_print_text else "(empty)"
    logger.info("Text: %s%s", preview, "..." if len(result.ocr_print_text) > max_preview else "")

    logger.info("\n--- PRINTED TEXT (raw: before filtering) ---")
    preview = result.ocr_print_text_raw[:max_preview] if result.ocr_print_text_raw else "(empty)"
    logger.info("Raw: %s%s", preview, "..." if len(result.ocr_print_text_raw) > max_preview else "")

    logger.info("\n--- HANDWRITING TEXT (%d words) ---", result.ocr_handwriting_word_count)
    logger.info("Avg Confidence: %s%%", result.avg_handwriting_confidence)
    preview = result.ocr_handwriting_text[:max_preview] if result.ocr_handwriting_text else "(empty)"
    logger.info("Text: %s%s", preview, "..." if len(result.ocr_handwriting_text) > max_preview else "")


def main(form_id: str | None = None) -> None:
    """Test OCR on a single image with post-processing.

    Args:
        form_id: Optional form ID. If None, uses default 'a01-000u'.

    For WER/CER scoring, use: python -m iam_testing.test_single_case
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Paths
    data_dir = Path(__file__).parent.parent / "data"
    test_form_id = form_id or "a01-000u"
    image_path = data_dir / "page_images" / f"{test_form_id}.png"

    if not image_path.exists():
        logger.error("Image not found: %s", image_path)
        return

    # Create Textract client
    textract_client = get_textract_client()
    logger.info("Using AWS region: %s", settings.AWS_REGION)

    # Process single image
    result = process_single_image(textract_client, image_path, test_form_id)

    # Display results to console
    _display_results(result)

    # Append to results file
    output_file = data_dir / "ocr_results.jsonl"
    write_ocr_result(result, output_file)


if __name__ == "__main__":
    main()
