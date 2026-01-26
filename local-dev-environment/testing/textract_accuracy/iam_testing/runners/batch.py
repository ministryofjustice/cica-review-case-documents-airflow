"""Batch runner for Textract OCR accuracy testing.

Processes all IAM forms through Textract and calculates baseline WER/CER scores.
Supports checkpointing to resume interrupted runs.

Usage:
    python -m iam_testing.runners.batch
    python -m iam_testing.runners.batch --limit 10
    python -m iam_testing.runners.batch --resume
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from ..scoring import load_all_ground_truth, score_ocr_result, write_score_result
from ..textract_client import get_textract_client
from ..textract_ocr import process_single_image, write_ocr_result

logger = logging.getLogger(__name__)


def get_all_form_ids(data_dir: Path) -> list[str]:
    """Get all available form IDs from the images directory.

    Args:
        data_dir: Path to the data directory.

    Returns:
        Sorted list of form IDs.
    """
    images_dir = data_dir / "page_images"
    if not images_dir.exists():
        logger.error("Images directory not found: %s", images_dir)
        return []

    form_ids = [p.stem for p in sorted(images_dir.glob("*.png"))]
    logger.info("Found %d form images", len(form_ids))
    return form_ids


def load_completed_form_ids(results_path: Path) -> set[str]:
    """Load form IDs that have already been processed.

    Args:
        results_path: Path to the JSONL results file.

    Returns:
        Set of completed form IDs.
    """
    if not results_path.exists():
        return set()

    completed = set()
    with open(results_path, encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
                completed.add(record.get("form_id"))
            except json.JSONDecodeError:
                continue

    logger.info("Found %d already completed forms", len(completed))
    return completed


def generate_run_id() -> str:
    """Generate a unique run ID based on timestamp.

    Returns:
        Run ID in format: YYYYMMDD_HHMMSS
    """
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_batch(
    form_ids: list[str],
    data_dir: Path,
    output_dir: Path,
    run_id: str,
    ground_truth: dict[str, dict],
    resume: bool = False,
) -> tuple[int, int]:
    """Process a batch of forms through Textract and calculate scores.

    Args:
        form_ids: List of form IDs to process.
        data_dir: Path to the data directory.
        output_dir: Path to the output directory.
        run_id: Unique identifier for this run.
        ground_truth: Dict mapping form_id to ground truth record.
        resume: If True, skip already completed forms.

    Returns:
        Tuple of (successful_count, failed_count).
    """
    # Output paths
    ocr_results_path = output_dir / f"ocr_results_{run_id}.jsonl"
    score_results_path = output_dir / f"score_results_{run_id}.jsonl"

    # Check for completed forms if resuming
    completed_forms: set[str] = set()
    if resume:
        completed_forms = load_completed_form_ids(score_results_path)

    # Filter to pending forms
    pending_forms = [fid for fid in form_ids if fid not in completed_forms]
    if len(pending_forms) < len(form_ids):
        logger.info(
            "Resuming: %d forms pending, %d already done", len(pending_forms), len(form_ids) - len(pending_forms)
        )

    # Create Textract client
    textract_client = get_textract_client()
    logger.info("Using AWS region: %s", settings.AWS_REGION)

    successful = 0
    failed = 0

    for i, form_id in enumerate(pending_forms, 1):
        image_path = data_dir / "page_images" / f"{form_id}.png"
        gt = ground_truth.get(form_id)

        if not image_path.exists():
            logger.warning("[%d/%d] Image not found: %s", i, len(pending_forms), form_id)
            failed += 1
            continue

        if not gt:
            logger.warning("[%d/%d] Ground truth not found: %s", i, len(pending_forms), form_id)
            failed += 1
            continue

        try:
            # Process through Textract
            logger.info("[%d/%d] Processing: %s", i, len(pending_forms), form_id)
            ocr_result = process_single_image(textract_client, image_path, form_id)

            # Calculate scores
            score = score_ocr_result(ocr_result, gt)

            # Write results (append)
            write_ocr_result(ocr_result, ocr_results_path)
            write_score_result(score, score_results_path)

            successful += 1
            logger.info(
                "[%d/%d] Done: %s (WER: %.2f%%, CER: %.2f%%)",
                i,
                len(pending_forms),
                form_id,
                score.wer_handwriting * 100,
                score.cer_handwriting * 100,
            )

        except Exception:
            logger.exception("[%d/%d] Failed: %s", i, len(pending_forms), form_id)
            failed += 1

    return successful, failed


def print_summary(score_results_path: Path) -> None:
    """Print summary statistics from a completed batch run.

    Args:
        score_results_path: Path to the score results JSONL file.
    """
    if not score_results_path.exists():
        logger.warning("No results file found")
        return

    wer_hw_values = []
    cer_hw_values = []
    wer_print_values = []
    cer_print_values = []

    with open(score_results_path, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            wer_hw_values.append(record["wer_handwriting"])
            cer_hw_values.append(record["cer_handwriting"])
            wer_print_values.append(record["wer_print"])
            cer_print_values.append(record["cer_print"])

    n = len(wer_hw_values)
    if n == 0:
        logger.warning("No results to summarize")
        return

    logger.info("=" * 60)
    logger.info("BATCH SUMMARY (%d forms)", n)
    logger.info("=" * 60)
    logger.info("HANDWRITING:")
    logger.info("  Mean WER: %.2f%%", sum(wer_hw_values) / n * 100)
    logger.info("  Mean CER: %.2f%%", sum(cer_hw_values) / n * 100)
    logger.info("  Min WER:  %.2f%%", min(wer_hw_values) * 100)
    logger.info("  Max WER:  %.2f%%", max(wer_hw_values) * 100)
    logger.info("PRINT:")
    logger.info("  Mean WER: %.2f%%", sum(wer_print_values) / n * 100)
    logger.info("  Mean CER: %.2f%%", sum(cer_print_values) / n * 100)
    logger.info("=" * 60)


def main() -> None:
    """Run batch Textract processing with scoring."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="Batch Textract OCR accuracy testing")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of forms to process (for testing)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from a previous run (uses latest run_id)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Specific run ID to use (for resuming)",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Only print summary of latest run, don't process",
    )
    args = parser.parse_args()

    # Paths
    data_dir = Path(__file__).parent.parent.parent / "data"
    output_dir = data_dir / "batch_runs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Handle summary-only mode
    if args.summary_only:
        # Find latest score results file
        score_files = sorted(output_dir.glob("score_results_*.jsonl"))
        if score_files:
            print_summary(score_files[-1])
        else:
            logger.warning("No batch runs found")
        return

    # Determine run ID
    if args.run_id:
        run_id = args.run_id
    elif args.resume:
        # Find latest run
        score_files = sorted(output_dir.glob("score_results_*.jsonl"))
        if score_files:
            run_id = score_files[-1].stem.replace("score_results_", "")
            logger.info("Resuming run: %s", run_id)
        else:
            run_id = generate_run_id()
            logger.info("No previous run found, starting new run: %s", run_id)
    else:
        run_id = generate_run_id()
        logger.info("Starting new run: %s", run_id)

    # Load ground truth
    gt_path = data_dir / "ground_truth.jsonl"
    if not gt_path.exists():
        logger.error("Ground truth file not found: %s", gt_path)
        logger.info("Run: python -m iam_testing.ground_truth_parser")
        return

    ground_truth = load_all_ground_truth(gt_path)

    # Get form IDs
    form_ids = get_all_form_ids(data_dir)
    if not form_ids:
        return

    # Apply limit if specified
    if args.limit:
        form_ids = form_ids[: args.limit]
        logger.info("Limited to %d forms", len(form_ids))

    # Run batch
    successful, failed = run_batch(
        form_ids=form_ids,
        data_dir=data_dir,
        output_dir=output_dir,
        run_id=run_id,
        ground_truth=ground_truth,
        resume=args.resume,
    )

    logger.info("Batch complete: %d successful, %d failed", successful, failed)

    # Print summary
    score_results_path = output_dir / f"score_results_{run_id}.jsonl"
    print_summary(score_results_path)


if __name__ == "__main__":
    main()
