#!/usr/bin/env python
"""Run relevance evaluation on search results.

This is the main entry point for running the relevance scoring evaluation.
It orchestrates the search loop, evaluation, and output generation.

Usage (run from local-dev-environment directory):
    python -m testing.run_evaluation
"""

import logging

from testing.config import get_date_folder, get_search_config, get_timestamp
from testing.relevance_scoring import (
    append_to_evaluation_log,
    evaluate_relevance,
    write_results_csv,
)
from testing.search_looper import run_search_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("run_evaluation")


def main() -> tuple | None:
    """Main entry point for relevance scoring evaluation.

    Returns:
        Tuple of (evaluated DataFrame, summary dict), or None if no results.
    """
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

    # Write CSV to date-based evaluation folder
    output_folder = get_date_folder()
    output_folder.mkdir(parents=True, exist_ok=True)
    csv_file = output_folder / f"{timestamp}_relevance_results.csv"
    write_results_csv(evaluated_df, csv_file, config, summary)

    # Append to cumulative evaluation log
    append_to_evaluation_log(config, summary)

    logger.info(f"Summary: {summary}")
    return evaluated_df, summary


if __name__ == "__main__":
    main()
