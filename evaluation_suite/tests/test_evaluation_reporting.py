"""Unit tests for evaluation_reporting.py."""

from unittest.mock import patch

import pandas as pd

from evaluation_suite.search_evaluation import evaluation_reporting
from evaluation_suite.search_evaluation.evaluation_models import EvaluationSummary


def _make_summary(**overrides) -> EvaluationSummary:
    defaults = dict(
        total_queries=1,
        queries_with_results=1,
        result_rate=1.0,
        avg_chunks_returned=1.0,
        queries_with_expected_chunk=1,
        avg_precision=1.0,
        avg_recall=1.0,
        avg_f1_score=1.0,
        avg_acceptable_term_based_precision=100.0,
        optimization_score=1.0,
    )
    return EvaluationSummary(**{**defaults, **overrides})


def _make_results_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "search_term": ["a"],
            "expected_chunk_id": ["c1"],
            "total_results": [1],
            "precision": [1.0],
            "recall": [1.0],
            "missing_chunk_ids": [""],
            "term_based_precision": [100],
            "acceptable_term_based_precision": [100],
            "manual_identifications": [1],
            "total_term_frequency": [1],
            "term_freq_difference": [0],
        }
    )


def test_write_results_csv(tmp_path):
    """Test write_results_csv writes CSV file with config and summary."""
    output_file = tmp_path / "results.csv"
    config = {"search_type": "exact"}
    summary = _make_summary()

    evaluation_reporting.write_results_csv(_make_results_df(), output_file, config, summary)

    assert output_file.exists()
    content = output_file.read_text()
    assert "Search Configuration" in content
    assert "Summary Statistics" in content
    assert "search_term" in content


def test_write_results_csv_with_dict_summary(tmp_path):
    """Test write_results_csv accepts a plain dict for summary."""
    output_file = tmp_path / "results.csv"
    config = {"search_type": "exact"}
    summary_dict = {"total_queries": 1, "optimization_score": 0.5}

    evaluation_reporting.write_results_csv(_make_results_df(), output_file, config, summary_dict)

    content = output_file.read_text()
    assert "optimization_score" in content


def test_write_results_csv_creates_parent_dirs(tmp_path):
    """Test write_results_csv creates parent directories if missing."""
    output_file = tmp_path / "nested" / "deep" / "results.csv"
    config = {"search_type": "exact"}

    evaluation_reporting.write_results_csv(_make_results_df(), output_file, config, _make_summary())

    assert output_file.exists()


@patch("evaluation_suite.search_evaluation.evaluation_reporting.EVALUATION_LOG_FILE")
def test_append_to_evaluation_log_creates_file(mock_log_file, tmp_path):
    """Test append_to_evaluation_log creates log file and writes entry."""
    log_path = tmp_path / "log.csv"
    mock_log_file.__str__.return_value = str(log_path)
    mock_log_file.parent = log_path.parent
    mock_log_file.exists.return_value = False

    with patch("evaluation_suite.search_evaluation.evaluation_reporting.EVALUATION_LOG_FILE", log_path):
        config = {"search_type": "exact", "timestamp": "2026-02-27"}
        evaluation_reporting.append_to_evaluation_log(config, _make_summary())

    assert log_path.exists()
    content = log_path.read_text()
    assert "search_type" in content
    assert "total_queries" in content


@patch("evaluation_suite.search_evaluation.evaluation_reporting.EVALUATION_LOG_FILE")
def test_append_to_evaluation_log_appends_on_second_call(mock_log_file, tmp_path):
    """Test that a second call appends without writing headers again."""
    log_path = tmp_path / "log.csv"

    with patch("evaluation_suite.search_evaluation.evaluation_reporting.EVALUATION_LOG_FILE", log_path):
        config = {"search_type": "exact", "timestamp": "2026-02-27"}
        evaluation_reporting.append_to_evaluation_log(config, _make_summary())
        evaluation_reporting.append_to_evaluation_log(config, _make_summary())

    lines = log_path.read_text().splitlines()
    # header + 2 data rows = 3 lines
    assert len(lines) == 3


@patch("evaluation_suite.search_evaluation.evaluation_reporting.EVALUATION_LOG_FILE")
def test_append_to_evaluation_log_removes_unwanted_keys(mock_log_file, tmp_path):
    """Test fuzziness, max_expansions, queries_with_expected_chunk are dropped from log."""
    log_path = tmp_path / "log.csv"

    with patch("evaluation_suite.search_evaluation.evaluation_reporting.EVALUATION_LOG_FILE", log_path):
        config = {
            "search_type": "exact",
            "timestamp": "2026-02-27",
            "fuzziness": "AUTO",
            "max_expansions": 50,
        }
        evaluation_reporting.append_to_evaluation_log(config, _make_summary())

    content = log_path.read_text()
    assert "fuzziness" not in content
    assert "max_expansions" not in content
