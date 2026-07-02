"""Unit tests for multi_case_runner.py."""

from unittest.mock import MagicMock, patch

from evaluation_suite.search_evaluation.multi_case import multi_case_runner
from evaluation_suite.search_evaluation.multi_case.case_discovery import CaseSpec

_CASE_A = CaseSpec(case_ref="26-700001", s3_filename="Case1_TC19_50_pages_brain_injury.pdf")
_CASE_B = CaseSpec(case_ref="26-700002", s3_filename="Case2_TC19_30_pages_whiplash.pdf")

_MOD = "evaluation_suite.search_evaluation.multi_case.multi_case_runner"


@patch(f"{_MOD}.run_evaluation")
def test_run_all_cases_calls_run_evaluation_per_case(mock_eval):
    """run_evaluation is called once per case with the correct CASE_FILTER override."""
    mock_eval.return_value = (MagicMock(), {"score": 0.8})

    multi_case_runner.run_all_cases([_CASE_A, _CASE_B])

    assert mock_eval.call_count == 2
    call_a, call_b = mock_eval.call_args_list
    assert call_a.kwargs["settings_overrides"] == {"CASE_FILTER": "26-700001"}
    assert call_b.kwargs["settings_overrides"] == {"CASE_FILTER": "26-700002"}
    assert call_a.kwargs["log_to_file"] is False
    assert call_b.kwargs["log_to_file"] is False


@patch(f"{_MOD}.run_evaluation")
def test_run_all_cases_returns_ordered_pairs(mock_eval):
    """Results are returned as (case_ref, result) pairs in input order."""
    result_a = (MagicMock(), {"score": 0.8})
    result_b = (MagicMock(), {"score": 0.6})
    mock_eval.side_effect = [result_a, result_b]

    output = multi_case_runner.run_all_cases([_CASE_A, _CASE_B])

    assert output == [("26-700001", result_a), ("26-700002", result_b)]


@patch(f"{_MOD}.run_evaluation")
def test_run_all_cases_handles_none_result(mock_eval):
    """A case that returns None (no search results) is included as (case_ref, None)."""
    mock_eval.return_value = None

    output = multi_case_runner.run_all_cases([_CASE_A])

    assert output == [("26-700001", None)]


@patch(f"{_MOD}.run_evaluation")
def test_run_all_cases_empty_input(mock_eval):
    """Empty case list returns empty output; run_evaluation is never called."""
    output = multi_case_runner.run_all_cases([])

    mock_eval.assert_not_called()
    assert output == []


@patch(f"{_MOD}.run_evaluation")
def test_run_all_cases_mixed_none_and_results(mock_eval):
    """Mix of successful and None results are collected correctly."""
    result_b = (MagicMock(), {"score": 0.5})
    mock_eval.side_effect = [None, result_b]

    output = multi_case_runner.run_all_cases([_CASE_A, _CASE_B])

    assert output[0] == ("26-700001", None)
    assert output[1] == ("26-700002", result_b)
