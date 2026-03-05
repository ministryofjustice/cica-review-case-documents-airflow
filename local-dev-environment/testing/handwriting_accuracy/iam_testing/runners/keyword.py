"""Test OCR accuracy on difficult pages using keyword recall.

This runner processes degraded/hard-to-read documents where full transcription
is not feasible. Instead of WER/CER, it measures what percentage of identifiable
keywords were detected by OCR.

Supports optional LLM augmentation to compare baseline Textract vs LLM-corrected
keyword recall.

Ground Truth Format (JSONL):
    {"page_id": "page1", "image_path": "data/custom/page1.png", "keywords": ["NHS", "2020", "assessment"]}
    {"page_id": "page2", "image_path": "data/custom/page2.png", "keywords": ["medication", "diagnosis"]}

Run from local-dev-environment:
    source .venv/bin/activate

    # Baseline keyword test (Textract only)
    PYTHONPATH=testing/handwriting_accuracy python -m iam_testing.runners.keyword

    # With LLM augmentation
    PYTHONPATH=testing/handwriting_accuracy python -m iam_testing.runners.keyword --augment

    # Specify LLM model
    PYTHONPATH=testing/handwriting_accuracy python -m iam_testing.runners.keyword \
        --augment --model nova-pro
"""

import argparse
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from iam_testing import DATA_DIR, TEXTRACT_ACCURACY_ROOT
from iam_testing.fuzzy_matching import score_keyword_recall_fuzzy
from iam_testing.keyword_scoring import (
    KeywordGroundTruth,
    load_keyword_ground_truth,
    score_keyword_recall,
)
from iam_testing.runners.utils import generate_run_id, write_jsonl
from iam_testing.stemmed_matching import score_keyword_recall_stemmed
from iam_testing.textract_client import get_textract_client
from iam_testing.textract_ocr import process_single_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KeywordScoreResult:
    """Keyword recall score for a single page."""

    page_id: str
    keywords_total: int
    # Baseline scores (exact, stemmed, fuzzy)
    baseline_exact: float
    baseline_stemmed: float
    baseline_fuzzy: float
    baseline_found: int
    # Augmented scores - None if not augmented
    augmented_exact: float | None
    augmented_stemmed: float | None
    augmented_fuzzy: float | None
    augmented_found: int | None
    # LLM info
    llm_model: str | None
    input_tokens: int
    output_tokens: int


def run_batch(
    gt_records: dict[str, KeywordGroundTruth],
    output_dir: Path,
    augment: bool = False,
    llm_model: str | None = None,
    prompt_version: str = "v2",
) -> None:
    """Process all pages in batch for keyword recall.

    Args:
        gt_records: Keyword ground truth records.
        output_dir: Directory to write results.
        augment: If True, also run LLM augmentation and compare.
        llm_model: LLM model to use for augmentation.
        prompt_version: Prompt version for LLM.
    """
    run_id = generate_run_id()
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting keyword batch processing: %d pages", len(gt_records))
    logger.info("Output directory: %s", run_dir)
    if augment:
        logger.info("LLM augmentation enabled: %s", llm_model)

    textract_client = get_textract_client()

    # Initialize LLM client if augmenting
    llm_client = None
    if augment and llm_model:
        from iam_testing.llm import get_llm_client

        llm_client = get_llm_client(model=llm_model, prompt_version=prompt_version)

    score_results: list[KeywordScoreResult] = []

    for idx, (page_id, gt) in enumerate(gt_records.items(), 1):
        logger.info("Processing %d/%d: %s", idx, len(gt_records), page_id)

        # Resolve image path
        image_path = Path(gt.image_path)
        if not image_path.is_absolute():
            if not image_path.exists():
                image_path = TEXTRACT_ACCURACY_ROOT / gt.image_path

        if not image_path.exists():
            logger.warning("Image not found, skipping: %s", image_path)
            continue

        try:
            # Process through Textract
            ocr_result = process_single_image(textract_client, image_path, page_id, filter_header=False)
            baseline_text = ocr_result.ocr_handwriting_text

            # Calculate baseline keyword recall (exact, stemmed, fuzzy)
            b_exact, b_found, _ = score_keyword_recall(gt.keywords, baseline_text)
            b_stemmed, _, _ = score_keyword_recall_stemmed(gt.keywords, baseline_text)
            b_fuzzy, _, _ = score_keyword_recall_fuzzy(gt.keywords, baseline_text)

            # Augmentation if enabled
            a_exact = a_stemmed = a_fuzzy = a_found = None
            input_tokens = output_tokens = 0

            if llm_client:
                llm_response = llm_client.correct_ocr_text(baseline_text)
                aug_text = llm_response.corrected_text
                input_tokens, output_tokens = llm_response.input_tokens, llm_response.output_tokens

                a_exact, a_found_list, _ = score_keyword_recall(gt.keywords, aug_text)
                a_stemmed, _, _ = score_keyword_recall_stemmed(gt.keywords, aug_text)
                a_fuzzy, _, _ = score_keyword_recall_fuzzy(gt.keywords, aug_text)
                a_found = len(a_found_list)

            score_results.append(
                KeywordScoreResult(
                    page_id=page_id,
                    keywords_total=len(gt.keywords),
                    baseline_exact=b_exact,
                    baseline_stemmed=b_stemmed,
                    baseline_fuzzy=b_fuzzy,
                    baseline_found=len(b_found),
                    augmented_exact=a_exact,
                    augmented_stemmed=a_stemmed,
                    augmented_fuzzy=a_fuzzy,
                    augmented_found=a_found,
                    llm_model=llm_model if augment else None,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            )

        except Exception as e:
            logger.error("Failed to process %s: %s", page_id, e)
            continue

    # Write results
    score_path = run_dir / "keyword_scores.jsonl"
    write_jsonl(score_path, [asdict(r) for r in score_results])

    logger.info("Batch processing complete!")
    logger.info("Keyword scores: %s", score_path)

    # Print results table
    _print_results_table(score_results, augment)


def _print_results_table(score_results: list[KeywordScoreResult], augment: bool) -> None:
    """Print formatted results table with exact/stemmed/fuzzy columns."""
    if not score_results:
        return

    n = len(score_results)
    has_aug = augment and score_results[0].augmented_exact is not None

    # Averages
    avg = lambda attr: sum(getattr(s, attr) for s in score_results) / n
    avg_b_exact, avg_b_stem, avg_b_fuzzy = avg("baseline_exact"), avg("baseline_stemmed"), avg("baseline_fuzzy")

    logger.info("\n" + "=" * 80)
    logger.info("Keyword Recall Results (Exact | Stemmed | Fuzzy)")
    logger.info("=" * 80)

    if has_aug:
        logger.info(f"{'Page':<16} {'KW':>4}  {'B-Ex':>6} {'B-St':>6} {'B-Fz':>6}  {'A-Ex':>6} {'A-St':>6} {'A-Fz':>6}")
    else:
        logger.info(f"{'Page':<20} {'Keywords':>8}  {'Exact':>8} {'Stemmed':>8} {'Fuzzy':>8}")
    logger.info("-" * 80)

    for s in score_results:
        if has_aug:
            logger.info(
                f"{s.page_id:<16} {s.keywords_total:>4}  "
                f"{s.baseline_exact * 100:>6.1f}% {s.baseline_stemmed * 100:>6.1f}% {s.baseline_fuzzy * 100:>6.1f}%  "
                f"{s.augmented_exact * 100:>6.1f}% {s.augmented_stemmed * 100:>6.1f}% {s.augmented_fuzzy * 100:>6.1f}%"
            )
        else:
            logger.info(
                f"{s.page_id:<20} {s.keywords_total:>8}  "
                f"{s.baseline_exact * 100:>7.1f}% {s.baseline_stemmed * 100:>7.1f}% {s.baseline_fuzzy * 100:>7.1f}%"
            )

    logger.info("-" * 80)
    total_kw = sum(s.keywords_total for s in score_results)

    if has_aug:
        avg_a_exact, avg_a_stem, avg_a_fuzzy = avg("augmented_exact"), avg("augmented_stemmed"), avg("augmented_fuzzy")
        logger.info(
            f"{'AVERAGE':<16} {total_kw:>4}  "
            f"{avg_b_exact * 100:>6.1f}% {avg_b_stem * 100:>6.1f}% {avg_b_fuzzy * 100:>6.1f}%  "
            f"{avg_a_exact * 100:>6.1f}% {avg_a_stem * 100:>6.1f}% {avg_a_fuzzy * 100:>6.1f}%"
        )
    else:
        logger.info(
            f"{'AVERAGE':<20} {total_kw:>8}  "
            f"{avg_b_exact * 100:>7.1f}% {avg_b_stem * 100:>7.1f}% {avg_b_fuzzy * 100:>7.1f}%"
        )
    logger.info("=" * 80)


def main() -> None:
    """Main entry point for keyword-based testing."""
    parser = argparse.ArgumentParser(description="Test OCR accuracy on difficult pages using keyword recall")
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("testing/handwriting_accuracy/data/case_documents_keywords.jsonl"),
        help="Path to ground truth JSONL",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory for results",
    )
    parser.add_argument(
        "--augment",
        action="store_true",
        help="Enable LLM augmentation (compare baseline vs LLM-corrected)",
    )
    parser.add_argument(
        "--model",
        default="nova-lite",
        choices=[
            "nova-micro",
            "nova-lite",
            "nova-pro",
            "claude-3-haiku",
            "claude-3-5-haiku",
            "claude-3-sonnet",
            "claude-3-5-sonnet",
        ],
        help="Bedrock model for augmentation (default: nova-lite)",
    )
    parser.add_argument(
        "--prompt",
        default="v2",
        help="Prompt version for LLM (default: v2)",
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

    output_dir = args.output or DATA_DIR / "output" / "keyword_batch_runs"
    run_batch(
        gt_records,
        output_dir,
        augment=args.augment,
        llm_model=args.model if args.augment else None,
        prompt_version=args.prompt,
    )


if __name__ == "__main__":
    main()
