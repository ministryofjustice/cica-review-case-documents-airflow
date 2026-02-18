#!/usr/bin/env python
"""Run relevance evaluation on search results.

This is the main entry point for running the relevance scoring evaluation.
It orchestrates the search loop, evaluation, and output generation.

Usage (run from local-dev-environment directory):
    python -m testing.run_evaluation

For programmatic use with settings overrides:
    from testing.run_evaluation import main
    result = main(settings_overrides={"KEYWORD_BOOST": 2.0, "K_QUERIES": 100})
"""

import logging
from typing import Any

from testing.evaluation_config import (
    get_active_search_type,
    get_date_folder,
    get_search_config,
    get_timestamp,
)
from testing.evaluation_settings import apply_overrides, reset_settings
from testing.relevance_scoring import (
    append_to_evaluation_log,
    evaluate_relevance,
    write_results_csv,
)
from testing.search_looper import run_search_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("run_evaluation")


def main(
    settings_overrides: dict[str, Any] | None = None,
    log_to_file: bool = True,
) -> tuple | None:
    """Main entry point for relevance scoring evaluation.

    Args:
        settings_overrides: Optional dict of evaluation_settings to override.
            Keys should match setting names in evaluation_settings.py
            (e.g., KEYWORD_BOOST, K_QUERIES, SCORE_FILTER).
        log_to_file: Whether to write per-run CSV results file.
            Set to False for optimization runs. The evaluation log is always
            updated regardless of this setting.

    Returns:
        Tuple of (evaluated DataFrame, summary dict), or None if no results.
    """
    # Apply any settings overrides
    if settings_overrides:
        apply_overrides(settings_overrides)
        logger.info(f"Applied settings overrides: {settings_overrides}")

    try:
        # Generate timestamp for this run
        timestamp = get_timestamp()

        # Capture search configuration
        config = get_search_config(timestamp)
        logger.info(f"Search config: {config}")

        # Run search loop
        logger.info("Running search loop...")
        results_df = run_search_loop()

        if results_df.empty:
            logger.error("No search results to evaluate.")
            return None

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


if __name__ == "__main__":
    main()
