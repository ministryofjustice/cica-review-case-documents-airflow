"""Vision model keyword recall runner.

Tests vision models on difficult/degraded documents using keyword recall scoring.
Instead of full WER/CER comparison, measures what percentage of identifiable
keywords are found in the extracted text.

Ground Truth Format (JSONL):
    {"page_id": "page1", "image_path": "data/custom/page1.png", "keywords": ["NHS", "2020"]}
    {"page_id": "page2", "image_path": "data/custom/page2.png", "keywords": ["medication"]}

Run from local-dev-environment:
    source .venv/bin/activate

    # Batch test all pages
    PYTHONPATH=testing/handwriting_accuracy python -m vision_model_testing.runners.vision_keyword \
        --ground-truth data/case_documents_keywords.jsonl \
        --model nova-pro
"""

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

from iam_testing.keyword_scoring import (
    KeywordGroundTruth,
    load_keyword_ground_truth,
    score_keyword_recall,
)

from .. import DATA_DIR
from ..llm import SUPPORTED_VISION_MODELS, get_vision_client
from ..llm.prompt import DEFAULT_VISION_PROMPT, VISION_PROMPTS
from .utils import append_jsonl, generate_run_id, save_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VisionKeywordScore:
    """Keyword recall score for a single page processed by vision model."""

    page_id: str
    vision_model: str
    vision_prompt: str

    # Keyword metrics
    keyword_recall: float  # 0.0 to 1.0
    keywords_found: int
    keywords_total: int
    found_keywords: tuple[str, ...]
    missing_keywords: tuple[str, ...]

    # Token usage
    input_tokens: int
    output_tokens: int


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


def run_batch(
    gt_records: dict[str, KeywordGroundTruth],
    gt_path: Path,
    model: str,
    prompt: str,
    output_dir: Path,
) -> list[VisionKeywordScore]:
    """Process all pages through vision model and score keyword recall.

    Args:
        gt_records: Keyword ground truth records.
        gt_path: Path to ground truth file for resolving image paths.
        model: Vision model name.
        prompt: Prompt version.
        output_dir: Directory to write results.

    Returns:
        List of VisionKeywordScore objects.
    """
    run_id = generate_run_id()
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    scores_path = run_dir / f"keyword_scores_{model}_{prompt}.jsonl"
    summary_path = run_dir / f"keyword_summary_{model}_{prompt}.json"

    logger.info("Starting vision keyword batch run: %s", run_id)
    logger.info("Model: %s, Prompt: %s", model, prompt)
    logger.info("Output: %s", scores_path)

    # Initialize vision client
    client = get_vision_client(model=model, prompt_version=prompt)

    scores: list[VisionKeywordScore] = []
    failed_count = 0

    for i, (page_id, gt) in enumerate(gt_records.items(), 1):
        image_path = resolve_image_path(gt.image_path, gt_path)
        if not image_path.exists():
            logger.warning("Image not found, skipping: %s", image_path)
            failed_count += 1
            continue

        try:
            logger.info("[%d/%d] Processing: %s", i, len(gt_records), page_id)

            # Extract text using vision model
            response = client.extract_text_from_image(image_path)

            # Score keyword recall
            recall, found, missing = score_keyword_recall(
                gt.keywords,
                response.extracted_text,
            )

            score = VisionKeywordScore(
                page_id=page_id,
                vision_model=response.model,
                vision_prompt=response.prompt_version,
                keyword_recall=recall,
                keywords_found=len(found),
                keywords_total=len(gt.keywords),
                found_keywords=tuple(found),
                missing_keywords=tuple(missing),
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
            )
            scores.append(score)

            # Append to results file
            append_jsonl(scores_path, score)

            logger.info(
                "  Recall: %.2f%% (%d/%d)",
                recall * 100,
                len(found),
                len(gt.keywords),
            )

        except Exception as e:
            logger.error("Failed to process %s: %s", page_id, e)
            failed_count += 1
            continue

    # Generate and save summary
    if scores:
        total_keywords = sum(s.keywords_total for s in scores)
        total_found = sum(s.keywords_found for s in scores)
        avg_recall = sum(s.keyword_recall for s in scores) / len(scores)
        overall_recall = total_found / total_keywords if total_keywords > 0 else 0.0
        total_input_tokens = sum(s.input_tokens for s in scores)
        total_output_tokens = sum(s.output_tokens for s in scores)

        summary = {
            "run_id": run_id,
            "model": model,
            "prompt": prompt,
            "pages_processed": len(scores),
            "failed_count": failed_count,
            "total_keywords": total_keywords,
            "total_found": total_found,
            "avg_recall": avg_recall,
            "overall_recall": overall_recall,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "ground_truth_file": str(gt_path),
        }
        save_summary(summary_path, summary)

        # Print results table
        _print_results_table(scores, summary)

    return scores


def _print_results_table(
    scores: list[VisionKeywordScore],
    summary: dict,
) -> None:
    """Print formatted results table."""
    logger.info("\n" + "=" * 60)
    logger.info("Per-Page Keyword Results")
    logger.info("=" * 60)

    header = f"{'Page ID':<20} {'Keywords':>10} {'Found':>8} {'Recall':>10}"
    logger.info(header)
    logger.info("-" * 60)

    for score in scores:
        logger.info(
            f"{score.page_id:<20} "
            f"{score.keywords_total:>10} "
            f"{score.keywords_found:>8} "
            f"{score.keyword_recall * 100:>9.2f}%"
        )

    logger.info("-" * 60)
    logger.info(
        f"{'AVERAGE':<20} "
        f"{summary['total_keywords']:>10} "
        f"{summary['total_found']:>8} "
        f"{summary['avg_recall'] * 100:>9.2f}%"
    )
    logger.info("=" * 60)

    logger.info(f"\nPages processed: {summary['pages_processed']}")
    logger.info(f"Total keywords: {summary['total_keywords']}")
    logger.info(f"Total found: {summary['total_found']}")
    logger.info(f"Average recall (per-page): {summary['avg_recall'] * 100:.2f}%")
    logger.info(f"Overall recall (keyword-weighted): {summary['overall_recall'] * 100:.2f}%")
    logger.info(f"Total tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")

    # Show most frequently missed keywords
    all_missing: dict[str, int] = {}
    for score in scores:
        for kw in score.missing_keywords:
            all_missing[kw] = all_missing.get(kw, 0) + 1

    if all_missing:
        sorted_missing = sorted(all_missing.items(), key=lambda x: -x[1])[:10]
        logger.info("\nMost frequently missed keywords:")
        for kw, count in sorted_missing:
            logger.info(f"  {kw}: {count} pages")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Test vision model keyword recall on difficult documents",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=DATA_DIR / "case_documents_keywords.jsonl",
        help="Path to keyword ground truth JSONL file",
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
        "--output-dir",
        type=Path,
        default=DATA_DIR / "vision_keyword_runs",
        help="Output directory for results",
    )

    args = parser.parse_args()

    # Load keyword ground truth
    try:
        gt_records = load_keyword_ground_truth(args.ground_truth)
    except FileNotFoundError as e:
        logger.error(str(e))
        logger.info(
            "\nCreate a keyword ground truth file with format:\n"
            '{"page_id": "page1", "image_path": "...", "keywords": ["NHS", "2020"]}'
        )
        return

    if not gt_records:
        logger.error("No valid ground truth records found")
        logger.info("Note: Pages with empty keyword lists are skipped. Add keywords to your ground truth file.")
        return

    run_batch(
        gt_records,
        args.ground_truth,
        args.model,
        args.prompt,
        args.output_dir,
    )


if __name__ == "__main__":
    main()
