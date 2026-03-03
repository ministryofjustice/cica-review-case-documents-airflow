"""Unit tests for run_evaluation.py."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from evaluation_suite.search_evaluation import run_evaluation


@patch("evaluation_suite.search_evaluation.run_evaluation.reset_settings")
@patch("evaluation_suite.search_evaluation.run_evaluation.apply_overrides")
@patch("evaluation_suite.search_evaluation.run_evaluation.check_opensearch_health")
@patch("evaluation_suite.search_evaluation.run_evaluation.run_search_loop")
@patch("evaluation_suite.search_evaluation.run_evaluation.evaluate_relevance")
@patch("evaluation_suite.search_evaluation.run_evaluation.append_to_evaluation_log")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_search_config")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_timestamp")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_active_search_type")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_date_folder")
@patch("evaluation_suite.search_evaluation.run_evaluation.write_results_csv")
def test_main_returns_tuple_on_success(
    mock_write_results_csv,
    mock_get_date_folder,
    mock_get_active_search_type,
    mock_get_timestamp,
    mock_get_search_config,
    mock_append_to_evaluation_log,
    mock_evaluate_relevance,
    mock_run_search_loop,
    mock_check_opensearch_health,
    mock_apply_overrides,
    mock_reset_settings,
    tmp_path,
):
    """Test that main returns a tuple of (DataFrame, summary) on success."""
    mock_get_timestamp.return_value = "2026-02-27_12-00-00"
    mock_get_search_config.return_value = {"search_type": "exact"}
    mock_get_active_search_type.return_value = "exact"
    mock_get_date_folder.return_value = tmp_path
    results_df = pd.DataFrame({"search_term": ["test"], "expected_chunk_id": ["c1"]})
    mock_run_search_loop.return_value = results_df
    summary = MagicMock()
    mock_evaluate_relevance.return_value = (results_df, summary)

    result = run_evaluation.run_evaluation()

    assert result is not None
    output_df, result_summary = result
    assert isinstance(output_df, pd.DataFrame)
    assert result_summary == summary


@patch("evaluation_suite.search_evaluation.run_evaluation.reset_settings")
@patch("evaluation_suite.search_evaluation.run_evaluation.apply_overrides")
@patch("evaluation_suite.search_evaluation.run_evaluation.check_opensearch_health")
@patch("evaluation_suite.search_evaluation.run_evaluation.run_search_loop")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_search_config")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_timestamp")
def test_main_returns_none_when_no_results(
    mock_get_timestamp,
    mock_get_search_config,
    mock_run_search_loop,
    mock_check_opensearch_health,
    mock_apply_overrides,
    mock_reset_settings,
):
    """Test that main returns None when search loop returns empty DataFrame."""
    mock_get_timestamp.return_value = "2026-02-27_12-00-00"
    mock_get_search_config.return_value = {"search_type": "exact"}
    mock_run_search_loop.return_value = pd.DataFrame()

    result = run_evaluation.run_evaluation()

    assert result is None


@patch("evaluation_suite.search_evaluation.run_evaluation.check_opensearch_health")
def test_main_raises_when_opensearch_unavailable(mock_check_opensearch_health):
    """Test that main raises an exception when OpenSearch is unreachable."""
    mock_check_opensearch_health.side_effect = ConnectionError("OpenSearch unavailable")

    with pytest.raises(ConnectionError, match="OpenSearch unavailable"):
        run_evaluation.run_evaluation()


@patch("evaluation_suite.search_evaluation.run_evaluation.reset_settings")
@patch("evaluation_suite.search_evaluation.run_evaluation.apply_overrides")
@patch("evaluation_suite.search_evaluation.run_evaluation.check_opensearch_health")
@patch("evaluation_suite.search_evaluation.run_evaluation.run_search_loop")
@patch("evaluation_suite.search_evaluation.run_evaluation.evaluate_relevance")
@patch("evaluation_suite.search_evaluation.run_evaluation.append_to_evaluation_log")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_search_config")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_timestamp")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_active_search_type")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_date_folder")
@patch("evaluation_suite.search_evaluation.run_evaluation.write_results_csv")
def test_main_applies_and_resets_overrides(
    mock_write_results_csv,
    mock_get_date_folder,
    mock_get_active_search_type,
    mock_get_timestamp,
    mock_get_search_config,
    mock_append_to_evaluation_log,
    mock_evaluate_relevance,
    mock_run_search_loop,
    mock_check_opensearch_health,
    mock_apply_overrides,
    mock_reset_settings,
    tmp_path,
):
    """Test that main applies overrides at start and resets them at end."""
    mock_get_timestamp.return_value = "2026-02-27_12-00-00"
    mock_get_search_config.return_value = {"search_type": "exact"}
    mock_get_active_search_type.return_value = "exact"
    mock_get_date_folder.return_value = tmp_path
    results_df = pd.DataFrame({"search_term": ["test"], "expected_chunk_id": ["c1"]})
    mock_run_search_loop.return_value = results_df
    mock_evaluate_relevance.return_value = (results_df, MagicMock())
    overrides = {"KEYWORD_BOOST": 2.0}

    run_evaluation.run_evaluation(settings_overrides=overrides)

    mock_apply_overrides.assert_called_once_with(overrides)
    mock_reset_settings.assert_called_once()


@patch("evaluation_suite.search_evaluation.run_evaluation.reset_settings")
@patch("evaluation_suite.search_evaluation.run_evaluation.apply_overrides")
@patch("evaluation_suite.search_evaluation.run_evaluation.check_opensearch_health")
@patch("evaluation_suite.search_evaluation.run_evaluation.run_search_loop")
@patch("evaluation_suite.search_evaluation.run_evaluation.evaluate_relevance")
@patch("evaluation_suite.search_evaluation.run_evaluation.append_to_evaluation_log")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_search_config")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_timestamp")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_active_search_type")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_date_folder")
@patch("evaluation_suite.search_evaluation.run_evaluation.write_results_csv")
def test_main_skips_csv_when_log_to_file_false(
    mock_write_results_csv,
    mock_get_date_folder,
    mock_get_active_search_type,
    mock_get_timestamp,
    mock_get_search_config,
    mock_append_to_evaluation_log,
    mock_evaluate_relevance,
    mock_run_search_loop,
    mock_check_opensearch_health,
    mock_apply_overrides,
    mock_reset_settings,
    tmp_path,
):
    """Test that main skips writing CSV when log_to_file=False."""
    mock_get_timestamp.return_value = "2026-02-27_12-00-00"
    mock_get_search_config.return_value = {"search_type": "exact"}
    mock_get_active_search_type.return_value = "exact"
    mock_get_date_folder.return_value = tmp_path
    results_df = pd.DataFrame({"search_term": ["test"], "expected_chunk_id": ["c1"]})
    mock_run_search_loop.return_value = results_df
    mock_evaluate_relevance.return_value = (results_df, MagicMock())

    run_evaluation.run_evaluation(log_to_file=False)

    mock_write_results_csv.assert_not_called()


@patch("evaluation_suite.search_evaluation.run_evaluation.reset_settings")
@patch("evaluation_suite.search_evaluation.run_evaluation.apply_overrides")
@patch("evaluation_suite.search_evaluation.run_evaluation.check_opensearch_health")
@patch("evaluation_suite.search_evaluation.run_evaluation.run_search_loop")
@patch("evaluation_suite.search_evaluation.run_evaluation.evaluate_relevance")
@patch("evaluation_suite.search_evaluation.run_evaluation.append_to_evaluation_log")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_search_config")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_timestamp")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_active_search_type")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_date_folder")
@patch("evaluation_suite.search_evaluation.run_evaluation.write_results_csv")
def test_main_always_appends_to_evaluation_log(
    mock_write_results_csv,
    mock_get_date_folder,
    mock_get_active_search_type,
    mock_get_timestamp,
    mock_get_search_config,
    mock_append_to_evaluation_log,
    mock_evaluate_relevance,
    mock_run_search_loop,
    mock_check_opensearch_health,
    mock_apply_overrides,
    mock_reset_settings,
    tmp_path,
):
    """Test that main always appends to evaluation log regardless of log_to_file."""
    mock_get_timestamp.return_value = "2026-02-27_12-00-00"
    mock_get_search_config.return_value = {"search_type": "exact"}
    mock_get_active_search_type.return_value = "exact"
    mock_get_date_folder.return_value = tmp_path
    results_df = pd.DataFrame({"search_term": ["test"], "expected_chunk_id": ["c1"]})
    mock_run_search_loop.return_value = results_df
    summary = MagicMock()
    mock_evaluate_relevance.return_value = (results_df, summary)

    run_evaluation.run_evaluation(log_to_file=False)

    mock_append_to_evaluation_log.assert_called_once()


@patch("evaluation_suite.search_evaluation.run_evaluation.reset_settings")
@patch("evaluation_suite.search_evaluation.run_evaluation.apply_overrides")
@patch("evaluation_suite.search_evaluation.run_evaluation.check_opensearch_health")
@patch("evaluation_suite.search_evaluation.run_evaluation.run_search_loop")
@patch("evaluation_suite.search_evaluation.run_evaluation.evaluate_relevance")
@patch("evaluation_suite.search_evaluation.run_evaluation.append_to_evaluation_log")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_search_config")
@patch("evaluation_suite.search_evaluation.run_evaluation.get_timestamp")
def test_main_resets_settings_even_on_exception(
    mock_get_timestamp,
    mock_get_search_config,
    mock_append_to_evaluation_log,
    mock_evaluate_relevance,
    mock_run_search_loop,
    mock_check_opensearch_health,
    mock_apply_overrides,
    mock_reset_settings,
):
    """Test that settings are reset even if an exception occurs during evaluation."""
    mock_get_timestamp.return_value = "2026-02-27_12-00-00"
    mock_get_search_config.return_value = {"search_type": "exact"}
    results_df = pd.DataFrame({"search_term": ["test"], "expected_chunk_id": ["c1"]})
    mock_run_search_loop.return_value = results_df
    mock_evaluate_relevance.side_effect = RuntimeError("Evaluation failed")
    overrides = {"KEYWORD_BOOST": 2.0}

    with pytest.raises(RuntimeError, match="Evaluation failed"):
        run_evaluation.run_evaluation(settings_overrides=overrides)

    mock_reset_settings.assert_called_once()
