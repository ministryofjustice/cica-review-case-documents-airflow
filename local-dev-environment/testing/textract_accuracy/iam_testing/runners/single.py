"""Test WER/CER scoring on a single IAM form.

This script processes one form through Textract and calculates accuracy metrics.
Use this to validate the pipeline before batch processing.

Usage:
    python -m iam_testing.runners.single
    python -m iam_testing.runners.single --form-id r06-121
"""

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from ..config import settings
from ..scoring import load_all_ground_truth, score_ocr_result
from ..textract_client import get_textract_client
from ..textract_ocr import process_single_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run single-case WER/CER test."""
    parser = argparse.ArgumentParser(description="Test OCR accuracy on a single form")
    parser.add_argument(
        "--form-id",
        default="r06-121",
        help="Form ID to test (default: r06-121)",
    )
    parser.add_argument(
        "--show-full-text",
        action="store_true",
        help="Show full ground truth and OCR text",
    )
    args = parser.parse_args()

    # Paths
    data_dir = Path(__file__).parent.parent.parent / "data"
    image_path = data_dir / "page_images" / f"{args.form_id}.png"
    gt_path = data_dir / "ground_truth.jsonl"

    # Validate paths
    if not image_path.exists():
        logger.error("Image not found: %s", image_path)
        logger.info("Available images: %s", list(data_dir.glob("page_images/*.png"))[:5])
        return

    if not gt_path.exists():
        logger.error("Ground truth file not found: %s", gt_path)
        return

    # Load ground truth (no API cost)
    all_gt = load_all_ground_truth(gt_path)
    gt = all_gt.get(args.form_id)
    if not gt:
        logger.error("Form ID '%s' not found in ground truth", args.form_id)
        return

    logger.info("Testing form: %s", args.form_id)
    logger.info("Image: %s", image_path)
    logger.info("Using AWS region: %s", settings.AWS_REGION)

    # Process through Textract
    textract_client = get_textract_client()
    result = process_single_image(textract_client, image_path, args.form_id)

    # Calculate scores
    score = score_ocr_result(result, gt)

    # Write to single-test result file (overwrites)
    results_path = data_dir / "latest_single_test.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(asdict(score), f, indent=2, ensure_ascii=False)
    logger.info("Wrote result to %s", results_path)

    # Console summary for interactive testing
    logger.info("--- HANDWRITING SCORES ---")
    logger.info("WER: %.2f%% | CER: %.2f%%", score.wer_handwriting * 100, score.cer_handwriting * 100)
    logger.info("GT words: %d | OCR words: %d", score.gt_handwriting_word_count, score.ocr_handwriting_word_count)
    logger.info("--- PRINT SCORES ---")
    logger.info("WER: %.2f%% | CER: %.2f%%", score.wer_print * 100, score.cer_print * 100)

    # Optionally show full text
    if args.show_full_text:
        logger.info("--- FULL GROUND TRUTH (HANDWRITING) ---")
        logger.info(score.gt_handwriting_text)
        logger.info("--- FULL OCR OUTPUT (HANDWRITING) ---")
        logger.info(score.ocr_handwriting_text)

    # Show raw Textract output for debugging
    logger.info("--- OCR DETAILS ---")
    logger.info("Printed words (filtered): %d", result.ocr_print_word_count)
    logger.info("Handwriting words: %d", result.ocr_handwriting_word_count)
    logger.info("Lowest quartile confidence (handwriting): %.1f%%", result.avg_handwriting_confidence)


if __name__ == "__main__":
    main()
