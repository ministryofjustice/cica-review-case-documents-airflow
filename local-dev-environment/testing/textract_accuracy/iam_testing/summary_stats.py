"""Summary statistics and distribution analysis for OCR results.

This module provides functions to calculate percentiles, distribution buckets,
and save comprehensive summary JSON files.
"""

import json
import logging
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Distribution bucket boundaries (percentages)
DISTRIBUTION_BUCKETS = [
    (0.0, 0.05, "0-5%"),
    (0.05, 0.10, "5-10%"),
    (0.10, 0.20, "10-20%"),
    (0.20, 0.50, "20-50%"),
    (0.50, 1.0, "50%+"),
]


@dataclass
class MetricStats:
    """Statistics for a single metric (WER or CER)."""

    mean: float
    median: float
    std: float
    min: float
    max: float
    percentiles: dict[str, float]  # p25, p50, p75, p90, p95, p99
    distribution: dict[str, int]  # bucket label -> count


@dataclass
class BaselineSummary:
    """Summary statistics for a baseline batch run."""

    run_id: str
    generated_at: str
    total_forms: int
    handwriting_wer: MetricStats
    handwriting_cer: MetricStats
    print_wer: MetricStats
    print_cer: MetricStats


@dataclass
class AugmentedSummary:
    """Summary statistics for an LLM augmentation run."""

    run_id: str
    baseline_run_id: str
    generated_at: str
    model: str
    prompt_version: str
    mode: str
    total_forms: int
    augmented_count: int
    skipped_count: int
    # Baseline stats
    baseline_wer: MetricStats
    baseline_cer: MetricStats
    # Augmented stats
    augmented_wer: MetricStats
    augmented_cer: MetricStats
    # Improvement stats
    wer_improvement: MetricStats
    cer_improvement: MetricStats
    # Counts
    improved_wer_count: int
    worse_wer_count: int
    unchanged_wer_count: int
    improved_cer_count: int
    worse_cer_count: int
    unchanged_cer_count: int
    # Token usage
    total_input_tokens: int
    total_output_tokens: int


def calculate_percentiles(values: list[float]) -> dict[str, float]:
    """Calculate percentiles for a list of values.

    Args:
        values: List of numeric values.

    Returns:
        Dict with p25, p50, p75, p90, p95, p99 percentiles.
    """
    if not values:
        return {f"p{p}": 0.0 for p in [25, 50, 75, 90, 95, 99]}

    sorted_values = sorted(values)
    n = len(sorted_values)

    def percentile(p: float) -> float:
        """Calculate the p-th percentile."""
        k = (n - 1) * (p / 100)
        f = int(k)
        c = f + 1 if f + 1 < n else f
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])

    return {
        "p25": round(percentile(25), 4),
        "p50": round(percentile(50), 4),
        "p75": round(percentile(75), 4),
        "p90": round(percentile(90), 4),
        "p95": round(percentile(95), 4),
        "p99": round(percentile(99), 4),
    }


def calculate_distribution(values: list[float]) -> dict[str, int]:
    """Count values in each distribution bucket.

    Args:
        values: List of numeric values (typically 0.0 to 1.0).

    Returns:
        Dict mapping bucket label to count.
    """
    distribution = {label: 0 for _, _, label in DISTRIBUTION_BUCKETS}

    for value in values:
        for low, high, label in DISTRIBUTION_BUCKETS:
            if low <= value < high or (label == "50%+" and value >= 0.5):
                distribution[label] += 1
                break

    return distribution


def calculate_metric_stats(values: list[float]) -> MetricStats:
    """Calculate comprehensive statistics for a metric.

    Args:
        values: List of metric values.

    Returns:
        MetricStats with all statistics.
    """
    if not values:
        return MetricStats(
            mean=0.0,
            median=0.0,
            std=0.0,
            min=0.0,
            max=0.0,
            percentiles=calculate_percentiles([]),
            distribution=calculate_distribution([]),
        )

    return MetricStats(
        mean=round(statistics.mean(values), 4),
        median=round(statistics.median(values), 4),
        std=round(statistics.stdev(values) if len(values) > 1 else 0.0, 4),
        min=round(min(values), 4),
        max=round(max(values), 4),
        percentiles=calculate_percentiles(values),
        distribution=calculate_distribution(values),
    )


def generate_baseline_summary(
    score_results_path: Path,
    run_id: str,
) -> BaselineSummary | None:
    """Generate summary statistics for a baseline batch run.

    Args:
        score_results_path: Path to score_results JSONL file.
        run_id: Run identifier.

    Returns:
        BaselineSummary or None if file doesn't exist.
    """
    if not score_results_path.exists():
        logger.warning("Score results file not found: %s", score_results_path)
        return None

    wer_hw = []
    cer_hw = []
    wer_print = []
    cer_print = []

    with open(score_results_path, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            wer_hw.append(record["wer_handwriting"])
            cer_hw.append(record["cer_handwriting"])
            wer_print.append(record["wer_print"])
            cer_print.append(record["cer_print"])

    if not wer_hw:
        logger.warning("No results found in file")
        return None

    return BaselineSummary(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_forms=len(wer_hw),
        handwriting_wer=calculate_metric_stats(wer_hw),
        handwriting_cer=calculate_metric_stats(cer_hw),
        print_wer=calculate_metric_stats(wer_print),
        print_cer=calculate_metric_stats(cer_print),
    )


def generate_augmented_summary(
    augmented_results_path: Path,
    run_id: str,
    baseline_run_id: str,
) -> AugmentedSummary | None:
    """Generate summary statistics for an augmentation run.

    Args:
        augmented_results_path: Path to augmented_results JSONL file.
        run_id: Augmented run identifier.
        baseline_run_id: Baseline run identifier.

    Returns:
        AugmentedSummary or None if file doesn't exist.
    """
    if not augmented_results_path.exists():
        logger.warning("Augmented results file not found: %s", augmented_results_path)
        return None

    results = []
    with open(augmented_results_path, encoding="utf-8") as f:
        for line in f:
            results.append(json.loads(line))

    if not results:
        logger.warning("No results found in file")
        return None

    augmented = [r for r in results if r["was_augmented"]]

    # Extract values
    baseline_wer = [r["baseline_wer"] for r in results]
    baseline_cer = [r["baseline_cer"] for r in results]
    augmented_wer = [r["augmented_wer"] for r in results]
    augmented_cer = [r["augmented_cer"] for r in results]
    wer_improvement = [r["wer_improvement"] for r in results]
    cer_improvement = [r["cer_improvement"] for r in results]

    # Count improvements (only for augmented forms)
    improved_wer = len([r for r in augmented if r["wer_improvement"] > 0])
    worse_wer = len([r for r in augmented if r["wer_improvement"] < 0])
    unchanged_wer = len([r for r in augmented if r["wer_improvement"] == 0])
    improved_cer = len([r for r in augmented if r["cer_improvement"] > 0])
    worse_cer = len([r for r in augmented if r["cer_improvement"] < 0])
    unchanged_cer = len([r for r in augmented if r["cer_improvement"] == 0])

    return AugmentedSummary(
        run_id=run_id,
        baseline_run_id=baseline_run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model=results[0]["llm_model"],
        prompt_version=results[0]["prompt_version"],
        mode=results[0]["augmentation_mode"],
        total_forms=len(results),
        augmented_count=len(augmented),
        skipped_count=len(results) - len(augmented),
        baseline_wer=calculate_metric_stats(baseline_wer),
        baseline_cer=calculate_metric_stats(baseline_cer),
        augmented_wer=calculate_metric_stats(augmented_wer),
        augmented_cer=calculate_metric_stats(augmented_cer),
        wer_improvement=calculate_metric_stats(wer_improvement),
        cer_improvement=calculate_metric_stats(cer_improvement),
        improved_wer_count=improved_wer,
        worse_wer_count=worse_wer,
        unchanged_wer_count=unchanged_wer,
        improved_cer_count=improved_cer,
        worse_cer_count=worse_cer,
        unchanged_cer_count=unchanged_cer,
        total_input_tokens=sum(r["input_tokens"] for r in results),
        total_output_tokens=sum(r["output_tokens"] for r in results),
    )


def save_summary(summary: BaselineSummary | AugmentedSummary, output_path: Path) -> None:
    """Save summary to JSON file.

    Args:
        summary: BaselineSummary or AugmentedSummary dataclass.
        output_path: Path to save JSON file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asdict(summary), f, indent=2, ensure_ascii=False)

    logger.info("Saved summary to %s", output_path)


def print_baseline_summary(summary: BaselineSummary) -> None:
    """Print baseline summary to console.

    Args:
        summary: BaselineSummary to print.
    """
    logger.info("=" * 70)
    logger.info("BATCH SUMMARY: %s", summary.run_id)
    logger.info("=" * 70)
    logger.info("Total forms: %d", summary.total_forms)
    logger.info("-" * 70)
    logger.info("HANDWRITING WER:")
    _print_metric_stats(summary.handwriting_wer)
    logger.info("-" * 70)
    logger.info("HANDWRITING CER:")
    _print_metric_stats(summary.handwriting_cer)
    logger.info("-" * 70)
    logger.info("PRINT WER:")
    _print_metric_stats(summary.print_wer)
    logger.info("-" * 70)
    logger.info("PRINT CER:")
    _print_metric_stats(summary.print_cer)
    logger.info("=" * 70)


def print_augmented_summary(summary: AugmentedSummary) -> None:
    """Print augmented summary to console.

    Args:
        summary: AugmentedSummary to print.
    """
    logger.info("=" * 70)
    logger.info("LLM AUGMENTATION SUMMARY: %s", summary.run_id)
    logger.info("=" * 70)
    logger.info("Model: %s | Prompt: %s | Mode: %s", summary.model, summary.prompt_version, summary.mode)
    logger.info(
        "Total: %d | Augmented: %d | Skipped: %d",
        summary.total_forms,
        summary.augmented_count,
        summary.skipped_count,
    )
    logger.info("-" * 70)
    logger.info("BASELINE WER:")
    _print_metric_stats(summary.baseline_wer)
    logger.info("-" * 70)
    logger.info("AUGMENTED WER:")
    _print_metric_stats(summary.augmented_wer)
    logger.info("-" * 70)
    logger.info("WER IMPROVEMENT (positive = better):")
    _print_metric_stats(summary.wer_improvement)
    logger.info(
        "  Improved: %d | Worse: %d | Unchanged: %d",
        summary.improved_wer_count,
        summary.worse_wer_count,
        summary.unchanged_wer_count,
    )
    logger.info("-" * 70)
    logger.info("Token Usage: %d input, %d output", summary.total_input_tokens, summary.total_output_tokens)
    logger.info("=" * 70)


def _print_metric_stats(stats: MetricStats) -> None:
    """Print metric statistics to console."""
    logger.info("  Mean: %.2f%% | Median: %.2f%% | Std: %.2f%%", stats.mean * 100, stats.median * 100, stats.std * 100)
    logger.info("  Min: %.2f%% | Max: %.2f%%", stats.min * 100, stats.max * 100)
    logger.info(
        "  Percentiles: P50=%.2f%% P75=%.2f%% P90=%.2f%% P95=%.2f%%",
        stats.percentiles["p50"] * 100,
        stats.percentiles["p75"] * 100,
        stats.percentiles["p90"] * 100,
        stats.percentiles["p95"] * 100,
    )
    logger.info("  Distribution: %s", _format_distribution(stats.distribution))


def _format_distribution(distribution: dict[str, int]) -> str:
    """Format distribution dict as a compact string."""
    return " | ".join(f"{label}: {count}" for label, count in distribution.items())
