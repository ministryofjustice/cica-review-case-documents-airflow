"""Vision model text extraction runner.

Processes images through vision-capable LLMs and calculates WER/CER against ground truth.
See README.md for usage examples.
"""

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .. import DATA_DIR
from ..llm import SUPPORTED_VISION_MODELS, get_vision_client
from ..llm.prompt import DEFAULT_VISION_PROMPT, VISION_PROMPTS
from ..scoring import (
    VisionScoreResult,
    generate_vision_summary,
    print_vision_summary,
    score_vision_result,
)
from .utils import (
    append_jsonl,
    generate_run_id,
    get_completed_ids,
    get_vision_paths,
    save_summary,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GroundTruth:
    """Ground truth record for custom documents."""

    page_id: str
    image_path: str
    gt_handwriting_text: str


def load_ground_truth(gt_path: Path) -> dict[str, GroundTruth]:
    """Load ground truth from JSONL file.

    Args:
        gt_path: Path to ground truth JSONL file.

    Returns:
        Dict mapping page_id to GroundTruth records.
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

                records[page_id] = GroundTruth(
                    page_id=page_id,
                    image_path=image_path,
                    gt_handwriting_text=gt_text,
                )
            except json.JSONDecodeError as e:
                logger.warning("Line %d: Invalid JSON: %s", line_num, e)
                continue

    logger.info("Loaded %d ground truth records from %s", len(records), gt_path)
    return records


def resolve_image_path(image_path_str: str, gt_path: Path) -> Path:
    """Resolve image path relative to ground truth file location.

    Args:
        image_path_str: Image path string from ground truth.
        gt_path: Path to the ground truth file.

    Returns:
        Resolved absolute Path to the image.
    """
    image_path = Path(image_path_str)

    if image_path.is_absolute():
        return image_path

    # Resolve relative to ground truth file directory
    return (gt_path.parent / image_path_str).resolve()


def run_single(
    page_id: str,
    gt_records: dict[str, GroundTruth],
    gt_path: Path,
    model: str,
    prompt: str,
) -> VisionScoreResult | None:
    """Process a single page through vision model.

    Args:
        page_id: Page identifier.
        gt_records: Ground truth records.
        gt_path: Path to ground truth file for resolving image paths.
        model: Vision model name.
        prompt: Prompt version.

    Returns:
        VisionScoreResult or None if failed.
    """
    gt = gt_records.get(page_id)
    if not gt:
        logger.error("Page ID '%s' not found in ground truth", page_id)
        logger.info("Available page IDs: %s", list(gt_records.keys())[:10])
        return None

    image_path = resolve_image_path(gt.image_path, gt_path)
    if not image_path.exists():
        logger.error("Image not found: %s", image_path)
        return None

    logger.info("Processing page: %s", page_id)
    logger.info("Image: %s", image_path)

    # Get vision client and extract text
    client = get_vision_client(model=model, prompt_version=prompt)
    response = client.extract_text_from_image(image_path)

    # Score against ground truth
    score = score_vision_result(
        page_id=page_id,
        gt_text=gt.gt_handwriting_text,
        vision_text=response.extracted_text,
        vision_model=response.model,
        vision_prompt=response.prompt_version,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )

    # Log result
    logger.info("--- %s ---", page_id)
    logger.info("Ground truth: %s...", gt.gt_handwriting_text[:100])
    logger.info("Vision text:  %s...", response.extracted_text[:100])
    logger.info(
        "WER: %.4f, CER: %.4f, Tokens: %d/%d", score.wer, score.cer, response.input_tokens, response.output_tokens
    )

    return score


def run_batch(
    gt_records: dict[str, GroundTruth],
    gt_path: Path,
    model: str,
    prompt: str,
    output_dir: Path,
    resume: bool = True,
) -> list[VisionScoreResult]:
    """Process all pages in ground truth through vision model.

    Args:
        gt_records: Ground truth records.
        gt_path: Path to ground truth file for resolving image paths.
        model: Vision model name.
        prompt: Prompt version.
        output_dir: Directory to write results.
        resume: If True, skip already-processed pages.

    Returns:
        List of VisionScoreResult objects.
    """
    run_id = generate_run_id()
    paths = get_vision_paths(output_dir, run_id, model, prompt)

    logger.info("Starting vision batch run: %s", run_id)
    logger.info("Model: %s, Prompt: %s", model, prompt)
    logger.info("Output: %s", paths["scores"])

    # Check for resume
    completed_ids: set[str] = set()
    if resume and paths["scores"].exists():
        completed_ids = get_completed_ids(paths["scores"])
        logger.info("Resuming: %d pages already completed", len(completed_ids))

    # Create output directory
    paths["dir"].mkdir(parents=True, exist_ok=True)

    # Initialize vision client
    client = get_vision_client(model=model, prompt_version=prompt)

    scores: list[VisionScoreResult] = []
    failed_count = 0

    for i, (page_id, gt) in enumerate(gt_records.items(), 1):
        if page_id in completed_ids:
            logger.debug("Skipping already processed: %s", page_id)
            continue

        image_path = resolve_image_path(gt.image_path, gt_path)
        if not image_path.exists():
            logger.warning("Image not found, skipping: %s", image_path)
            failed_count += 1
            continue

        try:
            logger.info("[%d/%d] Processing: %s", i, len(gt_records), page_id)

            # Extract text using vision model
            response = client.extract_text_from_image(image_path)

            # Score result
            score = score_vision_result(
                page_id=page_id,
                gt_text=gt.gt_handwriting_text,
                vision_text=response.extracted_text,
                vision_model=response.model,
                vision_prompt=response.prompt_version,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
            )
            scores.append(score)

            # Append to results file
            append_jsonl(paths["scores"], score)

            logger.info(
                "  WER: %.4f, CER: %.4f, Tokens: %d/%d",
                score.wer,
                score.cer,
                response.input_tokens,
                response.output_tokens,
            )

        except Exception as e:
            logger.error("Failed to process %s: %s", page_id, e)
            failed_count += 1
            continue

    # Generate and save summary
    summary = generate_vision_summary(scores)
    summary["run_id"] = run_id
    summary["failed_count"] = failed_count
    summary["ground_truth_file"] = str(gt_path)
    save_summary(paths["summary"], summary)

    # Print summary
    print_vision_summary(summary)

    return scores


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract text from images using vision models and score against ground truth.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        required=True,
        help="Path to ground truth JSONL file",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        choices=sorted(SUPPORTED_VISION_MODELS),
        help="Vision model to use",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=DEFAULT_VISION_PROMPT,
        choices=sorted(VISION_PROMPTS.keys()),
        help=f"Prompt version (default: {DEFAULT_VISION_PROMPT})",
    )
    parser.add_argument(
        "--page-id",
        type=str,
        help="Process single page (for testing)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DATA_DIR / "vision_runs",
        help="Output directory for results",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Don't resume from previous run, start fresh",
    )

    args = parser.parse_args()

    # Load ground truth
    gt_records = load_ground_truth(args.ground_truth)
    if not gt_records:
        logger.error("No ground truth records loaded")
        return

    if args.page_id:
        # Single page mode
        score = run_single(
            args.page_id,
            gt_records,
            args.ground_truth,
            args.model,
            args.prompt,
        )
        if score:
            logger.info("Final: WER=%.4f, CER=%.4f", score.wer, score.cer)
    else:
        # Batch mode
        run_batch(
            gt_records,
            args.ground_truth,
            args.model,
            args.prompt,
            args.output_dir,
            resume=not args.no_resume,
        )


if __name__ == "__main__":
    main()
