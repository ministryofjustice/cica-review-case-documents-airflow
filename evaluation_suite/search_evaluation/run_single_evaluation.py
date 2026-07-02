#!/usr/bin/env python
"""Run relevance evaluation on search results.

This is the main entry point for running the relevance scoring evaluation.
It orchestrates the search loop, evaluation, and output generation.

Usage:
    python -m evaluation_suite.search_evaluation.run_single_evaluation

For programmatic use with settings overrides:
    from evaluation_suite.search_evaluation.run_single_evaluation import run_evaluation
    result = run_evaluation(settings_overrides={"KEYWORD_BOOST": 2.0, "RESULT_SIZE": 100})
"""

import logging
from pathlib import Path
from typing import Any

from evaluation_suite.search_evaluation import evaluation_settings as eval_settings
from evaluation_suite.search_evaluation.evaluation_settings import apply_overrides, reset_settings
from evaluation_suite.search_evaluation.opensearch.bootstrap import bootstrap_opensearch
from evaluation_suite.search_evaluation.pipeline_config import (
    get_active_search_type,
    get_date_folder,
    get_search_config,
    get_timestamp,
)
from evaluation_suite.search_evaluation.query.search_looper import run_search_loop
from evaluation_suite.search_evaluation.relevance.evaluation_reporting import (
    append_to_evaluation_log,
    write_results_csv,
)
from evaluation_suite.search_evaluation.relevance.relevance_scoring import evaluate_relevance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("run_evaluation")

logging.getLogger("opensearch").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("optuna").setLevel(logging.ERROR)


def run_evaluation(
    settings_overrides: dict[str, Any] | None = None,
    log_to_file: bool = True,
    input_file: Path | None = None,
) -> tuple | None:
    """Run the relevance scoring evaluation.

    Args:
        settings_overrides: Optional dict of evaluation_settings to override.
            Keys should match setting names in evaluation_settings.py
            (e.g., KEYWORD_BOOST, RESULT_SIZE, SCORE_FILTER).
        log_to_file: Whether to write per-run CSV results file.
            Set to False for optimization runs. The evaluation log is always
            updated regardless of this setting.
        input_file: Path to the search terms CSV. When None, the default
            global CSV (testing_docs/search_terms.csv) is used.

    Returns:
        Tuple of (evaluated DataFrame, summary dict), or None if no results.
    """
    # Pre-flight: ensure OpenSearch is reachable, the chunk index exists with the
    # correct kNN mapping, and documents have been indexed. This makes the run
    # self-bootstrapping rather than assuming the local env init scripts ran.
    # The returned count is the corpus size recorded in the run config.
    num_chunks_indexed = bootstrap_opensearch()

    # Apply any settings overrides
    if settings_overrides:
        apply_overrides(settings_overrides)
        logger.info(f"Applied settings overrides: {settings_overrides}")

    try:
        # Generate timestamp for this run
        timestamp = get_timestamp()

        # Log which case is being evaluated
        logger.info(f"Evaluating case: {eval_settings.CASE_FILTER}")

        # Run search loop
        logger.info("Running search loop...")
        results_df, _ = run_search_loop(input_file=input_file)

        if results_df.empty:
            logger.error("No search results to evaluate.")
            return None

        # Capture search configuration (includes corpus size and chunking strategy)
        config = get_search_config(timestamp, num_chunks_indexed=num_chunks_indexed)
        logger.info(f"Search config: {config}")

        # Evaluate relevance
        logger.info(f"Evaluating {len(results_df)} search results...")
        evaluated_df, summary = evaluate_relevance(results_df)

        # Always append to cumulative evaluation log
        append_to_evaluation_log(config, summary)

        if log_to_file:
            # Write CSV to date-based evaluation folder, organised by search_type
            search_type = get_active_search_type()
            output_folder = get_date_folder() / search_type
            output_folder.mkdir(parents=True, exist_ok=True)
            csv_file = output_folder / f"{timestamp}_relevance_results.csv"
            write_results_csv(evaluated_df, csv_file, config, summary)

        logger.info(f"Summary: {summary}")
        return evaluated_df, summary

    finally:
        # Reset settings to defaults if overrides were applied
        if settings_overrides:
            reset_settings()
            logger.info("Reset settings to defaults")


def cli_main() -> None:
    """Command-line interface entry point."""
    result = run_evaluation()

    # Suggest the next step after a successful single-strategy run.
    if result is not None:
        _, summary = result
        strategy = get_search_config().get("chunking_strategy", "unknown")
        score = getattr(summary, "optimization_score", None) or (
            summary.get("optimization_score") if isinstance(summary, dict) else None
        )
        score_str = f"  Current optimization_score: {score:.4f}\n" if score is not None else ""
        print(  # noqa: T201
            f"\n{'─' * 60}\n"
            f"  Run completed for chunking strategy: {strategy}\n"
            f"{score_str}"
            f"\n  To compare all chunking strategies:\n"
            f"    python -m evaluation_suite.search_evaluation.run_chunking_comparison\n"
            f"\n  To fine-tune boost parameters (KEYWORD / SEMANTIC / DATE) on\n"
            f"  the current corpus using Bayesian optimisation:\n"
            f"    python -m evaluation_suite.search_evaluation.optimization.optimize_search\n"
            f"{'─' * 60}\n"
        )


if __name__ == "__main__":
    cli_main()
