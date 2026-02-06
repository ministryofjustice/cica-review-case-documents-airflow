"""Test OCR accuracy on custom documents (non-IAM dataset).

This runner processes arbitrary documents with handwritten text, using a simple
ground truth format. Unlike the IAM runner, this does not filter dataset-specific
headers, footers, or signatures.

Ground Truth Format (JSONL):
    {"page_id": "page1", "image_path": "data/custom/page1.png", "gt_handwriting_text": "..."}
    {"page_id": "page2", "image_path": "data/custom/page2.png", "gt_handwriting_text": "..."}

Usage:
    # Single page test
    python -m iam_testing.runners.custom --mode single --page-id page1

    # Batch test all pages in ground truth
    python -m iam_testing.runners.custom --mode batch

    # With custom ground truth file
    python -m iam_testing.runners.custom --mode batch --ground-truth data/my_gt.jsonl
"""

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from ..config import settings
from ..iam_filters import normalize_text
from ..schemas import OCRResult
from ..scoring import ScoreResult
from ..textract_client import get_textract_client
from ..textract_ocr import process_single_image
from .utils import generate_run_id, write_jsonl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CustomGroundTruth:
    """Simple ground truth record for custom documents."""

    page_id: str
    image_path: str
    gt_handwriting_text: str


def load_custom_ground_truth(gt_path: Path) -> dict[str, CustomGroundTruth]:
    """Load custom ground truth from JSONL file.

    Args:
        gt_path: Path to custom ground truth JSONL file.

    Returns:
        Dict mapping page_id to CustomGroundTruth records.
    """
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

    records = {}
    with open(gt_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line)
                page_id = data.get("page_id")
                image_path = data.get("image_path")
                gt_text = data.get("gt_handwriting_text")

                if not all([page_id, image_path, gt_text]):
                    logger.warning(
                        "Line %d missing required fields (page_id, image_path, gt_handwriting_text)",
                        line_num,
                    )
                    continue

                records[page_id] = CustomGroundTruth(
                    page_id=page_id,
                    image_path=image_path,
                    gt_handwriting_text=gt_text,
                )
            except json.JSONDecodeError as e:
                logger.warning("Line %d: Invalid JSON: %s", line_num, e)
                continue

    logger.info("Loaded %d custom ground truth records from %s", len(records), gt_path)
    return records


def score_custom_ocr(ocr_result: OCRResult, gt: CustomGroundTruth) -> ScoreResult:
    """Score OCR result against custom ground truth.

    Args:
        ocr_result: OCR result from Textract.
        gt: Custom ground truth record.

    Returns:
        ScoreResult with WER/CER metrics.
    """
    from jiwer import cer, wer

    # Normalize both ground truth and OCR output
    gt_normalized = normalize_text(gt.gt_handwriting_text)
    ocr_normalized = normalize_text(ocr_result.ocr_handwriting_text)

    # Calculate metrics for handwriting
    if gt_normalized and ocr_normalized:
        wer_hw = wer(gt_normalized, ocr_normalized)
        cer_hw = cer(gt_normalized, ocr_normalized)
    elif not gt_normalized and not ocr_normalized:
        wer_hw = 0.0
        cer_hw = 0.0
    else:
        wer_hw = 1.0
        cer_hw = 1.0

    return ScoreResult(
        form_id=ocr_result.form_id,
        wer_handwriting=wer_hw,
        cer_handwriting=cer_hw,
        gt_handwriting_word_count=len(gt_normalized.split()),
        ocr_handwriting_word_count=len(ocr_normalized.split()),
        gt_handwriting_text=gt.gt_handwriting_text,
        ocr_handwriting_text=ocr_result.ocr_handwriting_text,
        # No printed text comparison for custom documents
        wer_print=0.0,
        cer_print=0.0,
        gt_print_word_count=0,
        ocr_print_word_count=0,
        gt_print_text="",
        ocr_print_text="",
    )


def run_single(page_id: str, gt_records: dict[str, CustomGroundTruth], output_path: Path) -> None:
    """Process a single custom page.

    Args:
        page_id: Page identifier.
        gt_records: Ground truth records.
        output_path: Path to write results.
    """
    gt = gt_records.get(page_id)
    if not gt:
        logger.error("Page ID '%s' not found in ground truth", page_id)
        logger.info("Available page IDs: %s", list(gt_records.keys())[:10])
        return

    # Resolve image path (support both absolute and relative paths)
    image_path = Path(gt.image_path)
    if not image_path.is_absolute():
        # Try relative to current working directory first
        if not image_path.exists():
            # Try relative to textract_accuracy directory
            base_dir = Path(__file__).parent.parent.parent
            image_path = base_dir / gt.image_path

    if not image_path.exists():
        logger.error("Image not found: %s", image_path)
        return

    logger.info("Testing page: %s", page_id)
    logger.info("Image: %s", image_path)
    logger.info("Using AWS region: %s", settings.AWS_REGION)

    # Process through Textract (NO IAM filtering)
    textract_client = get_textract_client()
    ocr_result = process_single_image(
        textract_client,
        image_path,
        page_id,
        filter_header=False,  # Skip IAM-specific filtering
    )

    # Calculate scores
    score = score_custom_ocr(ocr_result, gt)

    # Write results
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asdict(score), f, indent=2, ensure_ascii=False)

    logger.info("Results written to: %s", output_path)
    logger.info("Handwriting WER: %.2f%%", score.wer_handwriting * 100)
    logger.info("Handwriting CER: %.2f%%", score.cer_handwriting * 100)


def run_batch(gt_records: dict[str, CustomGroundTruth], output_dir: Path, show_augmented: str | None = None) -> None:
    """Process all custom pages in batch.

    Args:
        gt_records: Ground truth records.
        output_dir: Directory to write results.
        show_augmented: Optional augmented results filename to display alongside baseline.
    """
    run_id = generate_run_id()
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting batch processing: %d pages", len(gt_records))
    logger.info("Output directory: %s", run_dir)

    textract_client = get_textract_client()
    ocr_results = []
    score_results = []

    for idx, (page_id, gt) in enumerate(gt_records.items(), 1):
        logger.info("Processing %d/%d: %s", idx, len(gt_records), page_id)

        # Resolve image path
        image_path = Path(gt.image_path)
        if not image_path.is_absolute():
            base_dir = Path(__file__).parent.parent.parent
            if not image_path.exists():
                image_path = base_dir / gt.image_path

        if not image_path.exists():
            logger.warning("Image not found, skipping: %s", image_path)
            continue

        try:
            # Process through Textract (NO IAM filtering)
            ocr_result = process_single_image(
                textract_client,
                image_path,
                page_id,
                filter_header=False,
            )
            ocr_results.append(ocr_result)

            # Calculate scores
            score = score_custom_ocr(ocr_result, gt)
            score_results.append(score)

            logger.info(
                "  WER: %.2f%% | CER: %.2f%%",
                score.wer_handwriting * 100,
                score.cer_handwriting * 100,
            )

        except Exception as e:
            logger.error("Failed to process %s: %s", page_id, e)
            continue

    # Write results
    ocr_path = run_dir / "ocr_results.jsonl"
    score_path = run_dir / "score_results.jsonl"

    write_jsonl(ocr_path, [asdict(r) for r in ocr_results])
    write_jsonl(score_path, [asdict(r) for r in score_results])

    logger.info("Batch processing complete!")
    logger.info("OCR results: %s", ocr_path)
    logger.info("Score results: %s", score_path)

    # Load augmented results if requested
    augmented_dict = {}
    if show_augmented:
        augmented_path = run_dir / "augmented" / show_augmented
        if augmented_path.exists():
            with open(augmented_path, encoding="utf-8") as f:
                for line in f:
                    aug = json.loads(line)
                    augmented_dict[aug["page_id"]] = aug
            logger.info("Loaded augmented results: %s", augmented_path)
        else:
            logger.warning("Augmented results not found: %s", augmented_path)

    # Print detailed per-page results table
    if score_results:
        has_augmented = len(augmented_dict) > 0

        logger.info("\n" + "=" * (130 if has_augmented else 110))
        logger.info("Per-Page Results")
        logger.info("=" * (130 if has_augmented else 110))

        # Header
        if has_augmented:
            header = f"{'Page ID':<20} {'GT Words':>10} {'OCR Words':>10} "
            header += f"{'Base WER':>9} {'Aug WER':>9} {'Δ WER':>9} {'CER':>8} {'Confidence':>12}"
            logger.info(header)
        else:
            logger.info(f"{'Page ID':<20} {'GT Words':>10} {'OCR Words':>10} {'WER':>8} {'CER':>8} {'Confidence':>12}")
        logger.info("-" * (130 if has_augmented else 110))

        # Get OCR results dict for confidence lookup
        ocr_dict = {r.form_id: r for r in ocr_results}

        # Per-page rows
        total_improvement = 0
        improved_count = 0
        for score in score_results:
            ocr = ocr_dict.get(score.form_id)
            confidence = ocr.avg_handwriting_confidence if ocr else 0.0

            if has_augmented:
                aug = augmented_dict.get(score.form_id)
                if aug:
                    aug_wer = aug["augmented_wer"]
                    delta_wer = score.wer_handwriting - aug_wer
                    total_improvement += delta_wer
                    if delta_wer > 0:
                        improved_count += 1

                    logger.info(
                        f"{score.form_id:<20} "
                        f"{score.gt_handwriting_word_count:>10} "
                        f"{score.ocr_handwriting_word_count:>10} "
                        f"{score.wer_handwriting * 100:>8.2f}% "
                        f"{aug_wer * 100:>8.2f}% "
                        f"{delta_wer * 100:>8.2f}% "
                        f"{score.cer_handwriting * 100:>7.2f}% "
                        f"{confidence:>11.1f}%"
                    )
                else:
                    logger.info(
                        f"{score.form_id:<20} "
                        f"{score.gt_handwriting_word_count:>10} "
                        f"{score.ocr_handwriting_word_count:>10} "
                        f"{score.wer_handwriting * 100:>8.2f}% "
                        f"{'N/A':>8} "
                        f"{'N/A':>9} "
                        f"{score.cer_handwriting * 100:>7.2f}% "
                        f"{confidence:>11.1f}%"
                    )
            else:
                logger.info(
                    f"{score.form_id:<20} "
                    f"{score.gt_handwriting_word_count:>10} "
                    f"{score.ocr_handwriting_word_count:>10} "
                    f"{score.wer_handwriting * 100:>7.2f}% "
                    f"{score.cer_handwriting * 100:>7.2f}% "
                    f"{confidence:>11.1f}%"
                )

        logger.info("-" * (130 if has_augmented else 110))

        # Summary statistics
        avg_wer = sum(s.wer_handwriting for s in score_results) / len(score_results)
        avg_cer = sum(s.cer_handwriting for s in score_results) / len(score_results)
        total_gt_words = sum(s.gt_handwriting_word_count for s in score_results)
        total_ocr_words = sum(s.ocr_handwriting_word_count for s in score_results)
        conf_sum = sum(ocr_dict[s.form_id].avg_handwriting_confidence for s in score_results if s.form_id in ocr_dict)
        avg_confidence = conf_sum / len(score_results)

        if has_augmented:
            aug_scores = [s for s in score_results if s.form_id in augmented_dict]
            avg_aug_wer = sum(augmented_dict[s.form_id]["augmented_wer"] for s in aug_scores) / len(aug_scores)
            avg_improvement = total_improvement / len(score_results)

            logger.info(
                f"{'AVERAGE':<20} "
                f"{total_gt_words:>10} "
                f"{total_ocr_words:>10} "
                f"{avg_wer * 100:>8.2f}% "
                f"{avg_aug_wer * 100:>8.2f}% "
                f"{avg_improvement * 100:>8.2f}% "
                f"{avg_cer * 100:>7.2f}% "
                f"{avg_confidence:>11.1f}%"
            )
        else:
            logger.info(
                f"{'AVERAGE':<20} "
                f"{total_gt_words:>10} "
                f"{total_ocr_words:>10} "
                f"{avg_wer * 100:>7.2f}% "
                f"{avg_cer * 100:>7.2f}% "
                f"{avg_confidence:>11.1f}%"
            )

        logger.info("=" * (130 if has_augmented else 110))
        logger.info(f"\nPages processed: {len(score_results)}")

        if has_augmented:
            improved_msg = f"Pages improved: {improved_count} | "
            improved_msg += f"Unchanged/Worse: {len(score_results) - improved_count}"
            logger.info(improved_msg)


def main() -> None:
    """Main entry point for custom document testing."""
    parser = argparse.ArgumentParser(description="Test OCR accuracy on custom documents (non-IAM dataset)")
    parser.add_argument(
        "--mode",
        choices=["single", "batch"],
        default="single",
        help="Processing mode: single page or batch",
    )
    parser.add_argument(
        "--page-id",
        help="Page ID to test (required for single mode)",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("data/custom_ground_truth.jsonl"),
        help="Path to custom ground truth JSONL file (default: data/custom_ground_truth.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path (single mode) or directory (batch mode)",
    )
    parser.add_argument(
        "--show-augmented",
        help="Show augmented results in table (batch mode only). Provide filename like 'nova-pro_v2_all.jsonl'",
    )
    args = parser.parse_args()

    # Load ground truth
    try:
        gt_records = load_custom_ground_truth(args.ground_truth)
    except FileNotFoundError as e:
        logger.error(str(e))
        logger.info(
            "\nCreate a custom ground truth file with format:\n"
            '{"page_id": "page1", "image_path": "data/custom/page1.png", "gt_handwriting_text": "..."}\n'
            '{"page_id": "page2", "image_path": "data/custom/page2.png", "gt_handwriting_text": "..."}'
        )
        return

    if not gt_records:
        logger.error("No valid ground truth records found")
        return

    # Run in requested mode
    if args.mode == "single":
        if not args.page_id:
            logger.error("--page-id is required for single mode")
            logger.info("Available page IDs: %s", list(gt_records.keys()))
            return

        output_path = args.output or Path("data/latest_custom_test.json")
        run_single(args.page_id, gt_records, output_path)

    else:  # batch mode
        output_dir = args.output or Path("data/custom_batch_runs")
        run_batch(gt_records, output_dir, args.show_augmented)


if __name__ == "__main__":
    main()
