"""Evaluation reporting utilities.

This module handles writing evaluation results to CSV files and
appending summaries to the cumulative evaluation log.
"""

import logging
from pathlib import Path

import pandas as pd

from evaluation_suite.search_evaluation.evaluation_config import EVALUATION_LOG_FILE
from evaluation_suite.search_evaluation.evaluation_models import EvaluationSummary

logger = logging.getLogger("evaluation_reporting")


def write_results_csv(
    df: pd.DataFrame,
    output_file: Path,
    config: dict,
    summary: EvaluationSummary | dict,
) -> None:
    """Write evaluation results DataFrame to a CSV file with config header.

    Args:
        df: DataFrame with evaluation results.
        output_file: Path to write the CSV file.
        config: Search configuration dictionary to write at top of file.
        summary: EvaluationSummary or dict with summary statistics.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Convert EvaluationSummary to dict if needed
    summary_dict = summary.to_dict() if isinstance(summary, EvaluationSummary) else summary

    with open(output_file, "w", encoding="utf-8") as f:
        # Write config section as row (keys then values)
        config_keys = ",".join(str(key) for key in config.keys())
        config_values = ",".join(str(value) for value in config.values())
        f.write("Search Configuration\n")
        f.write(f"{config_keys}\n")
        f.write(f"{config_values}\n")
        f.write("\n")

        # Write summary section as row (keys then values)
        summary_keys = ",".join(str(key) for key in summary_dict.keys())
        summary_values = ",".join(str(value) for value in summary_dict.values())
        f.write("Summary Statistics\n")
        f.write(f"{summary_keys}\n")
        f.write(f"{summary_values}\n")
        f.write("\n")

        # Write the DataFrame
        df.to_csv(f, index=False)

    logger.info(f"Results CSV written to {output_file.resolve()}")


def append_to_evaluation_log(config: dict, summary: EvaluationSummary | dict) -> None:
    """Append evaluation summary to the cumulative log file.

    Creates the log file with headers if it doesn't exist.

    Args:
        config: Search configuration dictionary.
        summary: EvaluationSummary or dict with summary statistics.
    """
    EVALUATION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Convert EvaluationSummary to dict if needed
    summary_dict = summary.to_dict() if isinstance(summary, EvaluationSummary) else summary

    # Combine config and summary into a single row
    log_entry = {**config, **summary_dict}

    # Remove columns we don't want in the log
    for key in ["fuzziness", "max_expansions", "queries_with_expected_chunk"]:
        log_entry.pop(key, None)

    # Reorder to put timestamp first, then search_type
    reordered = {}
    if "timestamp" in log_entry:
        reordered["timestamp"] = log_entry.pop("timestamp")
    if "search_type" in log_entry:
        reordered["search_type"] = log_entry.pop("search_type")
    log_entry = {**reordered, **log_entry}

    # Check if file exists to determine if we need headers
    write_header = not EVALUATION_LOG_FILE.exists()

    # Convert to DataFrame for easy CSV append
    log_df = pd.DataFrame([log_entry])

    with open(EVALUATION_LOG_FILE, "a", encoding="utf-8") as f:
        log_df.to_csv(f, header=write_header, index=False)

    logger.info(f"Appended evaluation summary to {EVALUATION_LOG_FILE.resolve()}")
