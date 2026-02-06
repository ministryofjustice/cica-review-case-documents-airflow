"""Batch runner for Textract OCR accuracy testing.

Processes all IAM forms through Textract and calculates baseline WER/CER scores.
Supports checkpointing to resume interrupted runs.

Usage:
    python -m iam_testing.runners.batch
    python -m iam_testing.runners.batch --limit 10
    python -m iam_testing.runners.batch --resume
"""

import argparse
import logging
import time
from pathlib import Path

from ..config import settings
from ..scoring import load_all_ground_truth, score_ocr_result
from ..summary_stats import (
    generate_baseline_summary,
    print_baseline_summary,
    save_summary,
)
from ..textract_client import get_textract_client
from ..textract_ocr import process_single_image
from .utils import append_jsonl, generate_run_id, get_baseline_paths, get_completed_ids, list_baseline_runs

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


def run_batch(
    form_ids: list[str],
    data_dir: Path,
    batch_runs_dir: Path,
    run_id: str,
    ground_truth: dict[str, dict],
    resume: bool = False,
    delay_seconds: float = 0.0,
) -> tuple[int, int]:
    """Process a batch of forms through Textract and calculate scores.

    Args:
        form_ids: List of form IDs to process.
        data_dir: Path to the data directory.
        batch_runs_dir: Path to the batch_runs directory.
        run_id: Unique identifier for this run.
        ground_truth: Dict mapping form_id to ground truth record.
        resume: If True, skip already completed forms.
        delay_seconds: Delay between API calls to avoid throttling.

    Returns:
        Tuple of (successful_count, failed_count).
    """
    # Output paths (hierarchical structure)
    paths = get_baseline_paths(batch_runs_dir, run_id)
    paths["dir"].mkdir(parents=True, exist_ok=True)

    ocr_results_path = paths["ocr"]
    score_results_path = paths["scores"]

    # Check for completed forms if resuming
    completed_forms: set[str] = set()
    if resume:
        completed_forms = get_completed_ids(score_results_path)

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
            append_jsonl(ocr_result, ocr_results_path)
            append_jsonl(score, score_results_path)

            successful += 1
            logger.info(
                "[%d/%d] Done: %s (WER: %.2f%%, CER: %.2f%%)",
                i,
                len(pending_forms),
                form_id,
                score.wer_handwriting * 100,
                score.cer_handwriting * 100,
            )

            # Rate limiting between API calls
            if delay_seconds > 0 and i < len(pending_forms):
                time.sleep(delay_seconds)

        except Exception:
            logger.exception("[%d/%d] Failed: %s", i, len(pending_forms), form_id)
            failed += 1

    return successful, failed


def print_summary(score_results_path: Path, run_id: str) -> None:
    """Generate, save, and print summary statistics from a completed batch run.

    Args:
        score_results_path: Path to the score results JSONL file.
        run_id: Run identifier for the summary.
    """
    summary = generate_baseline_summary(score_results_path, run_id)
    if summary is None:
        return

    # Save summary JSON (in same directory as results)
    summary_path = score_results_path.parent / "summary.json"
    save_summary(summary, summary_path)

    # Print to console
    print_baseline_summary(summary)


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
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay in seconds between API calls for rate limiting (default: 0)",
    )
    args = parser.parse_args()

    # Paths
    data_dir = Path(__file__).parent.parent.parent / "data"
    batch_runs_dir = data_dir / "batch_runs"
    batch_runs_dir.mkdir(parents=True, exist_ok=True)

    # Handle summary-only mode
    if args.summary_only:
        # Find latest run
        runs = list_baseline_runs(batch_runs_dir)
        if runs:
            latest_run = runs[-1]
            paths = get_baseline_paths(batch_runs_dir, latest_run)
            print_summary(paths["scores"], latest_run)
        else:
            logger.warning("No batch runs found")
        return

    # Determine run ID
    if args.run_id:
        run_id = args.run_id
    elif args.resume:
        # Find latest run
        runs = list_baseline_runs(batch_runs_dir)
        if runs:
            run_id = runs[-1]
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
        batch_runs_dir=batch_runs_dir,
        run_id=run_id,
        ground_truth=ground_truth,
        resume=args.resume,
        delay_seconds=args.delay,
    )

    logger.info("Batch complete: %d successful, %d failed", successful, failed)

    # Print and save summary
    paths = get_baseline_paths(batch_runs_dir, run_id)
    print_summary(paths["scores"], run_id)


if __name__ == "__main__":
    main()
