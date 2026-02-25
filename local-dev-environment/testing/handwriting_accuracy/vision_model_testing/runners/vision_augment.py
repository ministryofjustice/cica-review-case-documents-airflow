"""Vision + LLM augmentation runner.

Applies LLM text correction to vision results and recalculates WER/CER.
See README.md for usage examples.
"""

import argparse
import logging
from pathlib import Path

# Import LLM augmentation from sibling iam_testing module
from iam_testing.iam_filters import normalize_text
from iam_testing.llm import SUPPORTED_MODELS as SUPPORTED_LLM_MODELS, get_llm_client
from iam_testing.llm.prompt import DEFAULT_PROMPT as DEFAULT_LLM_PROMPT, PROMPTS as LLM_PROMPTS
from jiwer import cer, wer

from .. import DATA_DIR
from ..scoring import VisionAugmentedScoreResult
from .utils import (
    append_jsonl,
    get_augmented_paths,
    get_completed_ids,
    get_vision_paths,
    load_jsonl,
    save_summary,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def calculate_improvement(baseline: float, augmented: float) -> float:
    """Calculate improvement in WER/CER (positive = better).

    Args:
        baseline: Baseline error rate.
        augmented: Augmented error rate.

    Returns:
        Improvement (positive means augmented is better).
    """
    return baseline - augmented


def run_augment(
    baseline_run_id: str,
    vision_model: str,
    vision_prompt: str,
    llm_model: str,
    llm_prompt: str,
    batch_runs_dir: Path,
    resume: bool = True,
) -> list[VisionAugmentedScoreResult]:
    """Augment vision results with LLM text correction.

    Args:
        baseline_run_id: Vision run ID to augment.
        vision_model: Vision model used in baseline.
        vision_prompt: Vision prompt version used in baseline.
        llm_model: LLM model for augmentation.
        llm_prompt: LLM prompt version for augmentation.
        batch_runs_dir: Directory containing vision runs.
        resume: If True, skip already-processed pages.

    Returns:
        List of VisionAugmentedScoreResult objects.
    """
    # Get paths
    vision_paths = get_vision_paths(batch_runs_dir, baseline_run_id, vision_model, vision_prompt)
    augmented_paths = get_augmented_paths(
        batch_runs_dir, baseline_run_id, vision_model, vision_prompt, llm_model, llm_prompt
    )

    # Validate baseline exists
    if not vision_paths["scores"].exists():
        raise FileNotFoundError(
            f"Vision baseline not found: {vision_paths['scores']}\n"
            f"Run vision extraction first with: "
            f"python -m vision_model_testing.runners.vision --model {vision_model} ..."
        )

    logger.info("Loading vision baseline from: %s", vision_paths["scores"])
    baseline_scores = load_jsonl(vision_paths["scores"])
    logger.info("Loaded %d baseline results", len(baseline_scores))

    # Check for resume
    completed_ids: set[str] = set()
    if resume and augmented_paths["results"].exists():
        completed_ids = get_completed_ids(augmented_paths["results"])
        logger.info("Resuming: %d pages already augmented", len(completed_ids))

    # Create output directory
    augmented_paths["dir"].mkdir(parents=True, exist_ok=True)

    # Initialize LLM client
    llm_client = get_llm_client(model=llm_model, prompt_version=llm_prompt)
    logger.info("Using LLM: %s (prompt: %s)", llm_model, llm_prompt)

    results: list[VisionAugmentedScoreResult] = []

    for i, baseline in enumerate(baseline_scores, 1):
        page_id = baseline["page_id"]

        if page_id in completed_ids:
            logger.debug("Skipping already augmented: %s", page_id)
            continue

        try:
            logger.info("[%d/%d] Augmenting: %s", i, len(baseline_scores), page_id)

            # Get vision text from baseline
            vision_text = baseline["vision_text"]
            gt_text = baseline["gt_text"]

            # Apply LLM correction to vision output
            llm_response = llm_client.correct_ocr_text(vision_text)
            augmented_text = llm_response.corrected_text

            # Calculate scores
            gt_normalized = normalize_text(gt_text)
            vision_normalized = normalize_text(vision_text)
            augmented_normalized = normalize_text(augmented_text)

            # Baseline scores (vision only)
            if gt_normalized and vision_normalized:
                baseline_wer = wer(gt_normalized, vision_normalized)
                baseline_cer = cer(gt_normalized, vision_normalized)
            else:
                baseline_wer = 1.0 if gt_normalized or vision_normalized else 0.0
                baseline_cer = baseline_wer

            # Augmented scores (after LLM)
            if gt_normalized and augmented_normalized:
                augmented_wer = wer(gt_normalized, augmented_normalized)
                augmented_cer = cer(gt_normalized, augmented_normalized)
            else:
                augmented_wer = 1.0 if gt_normalized or augmented_normalized else 0.0
                augmented_cer = augmented_wer

            result = VisionAugmentedScoreResult(
                page_id=page_id,
                vision_model=vision_model,
                vision_prompt=baseline["vision_prompt"],
                llm_model=llm_model,
                llm_prompt=llm_client.get_prompt_hash(),
                baseline_wer=baseline_wer,
                baseline_cer=baseline_cer,
                augmented_wer=augmented_wer,
                augmented_cer=augmented_cer,
                wer_improvement=calculate_improvement(baseline_wer, augmented_wer),
                cer_improvement=calculate_improvement(baseline_cer, augmented_cer),
                gt_text=gt_text,
                vision_text=vision_text,
                augmented_text=augmented_text,
                vision_input_tokens=baseline.get("input_tokens", 0),
                vision_output_tokens=baseline.get("output_tokens", 0),
                llm_input_tokens=llm_response.input_tokens,
                llm_output_tokens=llm_response.output_tokens,
            )
            results.append(result)

            # Append to results file
            append_jsonl(augmented_paths["results"], result)

            # Log progress
            improvement_indicator = "+" if result.wer_improvement > 0 else ""
            logger.info(
                "  Vision WER: %.4f -> Augmented: %.4f (%s%.4f)",
                baseline_wer,
                augmented_wer,
                improvement_indicator,
                result.wer_improvement,
            )

        except Exception as e:
            logger.error("Failed to augment %s: %s", page_id, e)
            continue

    # Generate and save summary
    summary = generate_augmented_summary(results)
    summary["baseline_run_id"] = baseline_run_id
    summary["vision_model"] = vision_model
    summary["vision_prompt"] = vision_prompt
    summary["llm_model"] = llm_model
    summary["llm_prompt"] = llm_prompt
    save_summary(augmented_paths["summary"], summary)

    # Print summary
    print_augmented_summary(summary)

    return results


def generate_augmented_summary(results: list[VisionAugmentedScoreResult]) -> dict:
    """Generate summary statistics for augmented run.

    Args:
        results: List of VisionAugmentedScoreResult objects.

    Returns:
        Summary dict with aggregate metrics.
    """
    if not results:
        return {"total_pages": 0}

    # Aggregate metrics
    baseline_wer_sum = sum(r.baseline_wer for r in results)
    baseline_cer_sum = sum(r.baseline_cer for r in results)
    augmented_wer_sum = sum(r.augmented_wer for r in results)
    augmented_cer_sum = sum(r.augmented_cer for r in results)
    wer_improvement_sum = sum(r.wer_improvement for r in results)
    cer_improvement_sum = sum(r.cer_improvement for r in results)

    improved_pages = sum(1 for r in results if r.wer_improvement > 0)
    degraded_pages = sum(1 for r in results if r.wer_improvement < 0)
    unchanged_pages = sum(1 for r in results if r.wer_improvement == 0)

    total_vision_input = sum(r.vision_input_tokens for r in results)
    total_vision_output = sum(r.vision_output_tokens for r in results)
    total_llm_input = sum(r.llm_input_tokens for r in results)
    total_llm_output = sum(r.llm_output_tokens for r in results)

    n = len(results)
    return {
        "total_pages": n,
        # Baseline metrics
        "baseline_avg_wer": baseline_wer_sum / n,
        "baseline_avg_cer": baseline_cer_sum / n,
        # Augmented metrics
        "augmented_avg_wer": augmented_wer_sum / n,
        "augmented_avg_cer": augmented_cer_sum / n,
        # Improvement
        "avg_wer_improvement": wer_improvement_sum / n,
        "avg_cer_improvement": cer_improvement_sum / n,
        "improved_pages": improved_pages,
        "degraded_pages": degraded_pages,
        "unchanged_pages": unchanged_pages,
        "improvement_rate": improved_pages / n if n > 0 else 0,
        # Token usage
        "total_vision_input_tokens": total_vision_input,
        "total_vision_output_tokens": total_vision_output,
        "total_llm_input_tokens": total_llm_input,
        "total_llm_output_tokens": total_llm_output,
    }


def print_augmented_summary(summary: dict) -> None:
    """Log formatted augmented summary."""
    logger.info("=" * 70)
    logger.info("VISION + LLM AUGMENTATION SUMMARY")
    logger.info("=" * 70)
    logger.info(
        "Vision: %s (%s) | LLM: %s (%s)",
        summary.get("vision_model", "N/A"),
        summary.get("vision_prompt", "N/A"),
        summary.get("llm_model", "N/A"),
        summary.get("llm_prompt", "N/A"),
    )
    logger.info("Total pages: %d", summary["total_pages"])
    logger.info("-" * 70)
    logger.info(
        "BASELINE (Vision Only): WER=%.4f, CER=%.4f",
        summary.get("baseline_avg_wer", 0),
        summary.get("baseline_avg_cer", 0),
    )
    logger.info(
        "AUGMENTED (Vision+LLM): WER=%.4f, CER=%.4f",
        summary.get("augmented_avg_wer", 0),
        summary.get("augmented_avg_cer", 0),
    )
    logger.info("-" * 70)
    logger.info(
        "IMPROVEMENT: WER=%+.4f, CER=%+.4f",
        summary.get("avg_wer_improvement", 0),
        summary.get("avg_cer_improvement", 0),
    )
    logger.info(
        "Improved: %d | Degraded: %d | Unchanged: %d (%.1f%% improved)",
        summary.get("improved_pages", 0),
        summary.get("degraded_pages", 0),
        summary.get("unchanged_pages", 0),
        summary.get("improvement_rate", 0) * 100,
    )
    logger.info("-" * 70)
    logger.info(
        "Tokens - Vision: %d/%d | LLM: %d/%d",
        summary.get("total_vision_input_tokens", 0),
        summary.get("total_vision_output_tokens", 0),
        summary.get("total_llm_input_tokens", 0),
        summary.get("total_llm_output_tokens", 0),
    )
    logger.info("=" * 70)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Augment vision model results with LLM text correction.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--baseline-run",
        type=str,
        required=True,
        help="Vision run ID to augment (e.g., 20260225_120000)",
    )
    parser.add_argument(
        "--vision-model",
        type=str,
        required=True,
        help="Vision model used in baseline (e.g., nova-pro)",
    )
    parser.add_argument(
        "--vision-prompt",
        type=str,
        required=True,
        help="Vision prompt version used in baseline (e.g., v1)",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        required=True,
        choices=sorted(SUPPORTED_LLM_MODELS),
        help="LLM model for augmentation",
    )
    parser.add_argument(
        "--llm-prompt",
        type=str,
        default=DEFAULT_LLM_PROMPT,
        choices=sorted(LLM_PROMPTS.keys()),
        help=f"LLM prompt version (default: {DEFAULT_LLM_PROMPT})",
    )
    parser.add_argument(
        "--batch-runs-dir",
        type=Path,
        default=DATA_DIR / "vision_runs",
        help="Directory containing vision runs",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Don't resume from previous run, start fresh",
    )

    args = parser.parse_args()

    run_augment(
        baseline_run_id=args.baseline_run,
        vision_model=args.vision_model,
        vision_prompt=args.vision_prompt,
        llm_model=args.llm_model,
        llm_prompt=args.llm_prompt,
        batch_runs_dir=args.batch_runs_dir,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
