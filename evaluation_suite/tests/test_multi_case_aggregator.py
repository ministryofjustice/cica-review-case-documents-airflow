"""Unit tests for multi_case_aggregator.py."""

import math
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from evaluation_suite.search_evaluation.multi_case.multi_case_aggregator import aggregate_results
from evaluation_suite.search_evaluation.relevance.evaluation_models import EvaluationSummary

_CHUNKING_STRATEGY = "textractor-word-stream"
_PATCH_STRATEGY = patch(
    "evaluation_suite.search_evaluation.multi_case.multi_case_aggregator._resolve_chunking_strategy",
    return_value=_CHUNKING_STRATEGY,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_summary(**overrides) -> EvaluationSummary:
    """Return an EvaluationSummary with sensible defaults, optionally overridden."""
    defaults = dict(
        total_queries=10,
        queries_with_results=9,
        result_rate=0.9,
        avg_chunks_returned=5.0,
        queries_with_expected_chunk=7,
        avg_precision_at_10=0.8,
        avg_precision_at_20=0.7,
        avg_recall_at_10=0.6,
        avg_recall_at_20=0.5,
        avg_f1_at_10=0.68,
        avg_f1_at_20=0.58,
        avg_term_based_precision_at_10=0.75,
        avg_term_based_precision_at_20=0.65,
        avg_acceptable_term_based_precision_at_10=0.85,
        avg_acceptable_term_based_precision_at_20=0.80,
        optimization_score=0.8,
    )
    defaults.update(overrides)
    return EvaluationSummary(**defaults)


_SUMMARY_A = _make_summary(optimization_score=0.8, avg_precision_at_10=0.8)
_SUMMARY_B = _make_summary(optimization_score=0.6, avg_precision_at_10=0.4)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@_PATCH_STRATEGY
def test_aggregate_results_empty_input(_mock):
    """Empty results list returns an empty DataFrame."""
    df = aggregate_results([])
    assert df.empty


@_PATCH_STRATEGY
def test_aggregate_results_per_case_rows(_mock):
    """Each case gets its own row with correct case_ref and metric values."""
    results = [
        ("26-700001", (MagicMock(), _SUMMARY_A)),
        ("26-700002", (MagicMock(), _SUMMARY_B)),
    ]
    df = aggregate_results(results)

    case_refs = list(df["case_ref"])
    assert "26-700001" in case_refs
    assert "26-700002" in case_refs

    row_a = df[df["case_ref"] == "26-700001"].iloc[0]
    assert row_a["optimization_score"] == pytest.approx(0.8)
    assert row_a["chunking_strategy"] == _CHUNKING_STRATEGY

    row_b = df[df["case_ref"] == "26-700002"].iloc[0]
    assert row_b["optimization_score"] == pytest.approx(0.6)


@_PATCH_STRATEGY
def test_aggregate_results_macro_avg_row(_mock):
    """The MACRO_AVG row contains the mean of numeric columns; strategy is preserved."""
    results = [
        ("26-700001", (MagicMock(), _SUMMARY_A)),
        ("26-700002", (MagicMock(), _SUMMARY_B)),
    ]
    df = aggregate_results(results)

    agg_row = df[df["case_ref"] == "MACRO_AVG"].iloc[0]
    assert agg_row["optimization_score"] == pytest.approx(0.7)  # (0.8 + 0.6) / 2
    assert agg_row["avg_precision_at_10"] == pytest.approx(0.6)  # (0.8 + 0.4) / 2
    assert agg_row["chunking_strategy"] == _CHUNKING_STRATEGY


@_PATCH_STRATEGY
def test_aggregate_results_single_case(_mock):
    """Single case produces two rows: the case itself and MACRO_AVG equal to it."""
    results = [("26-700001", (MagicMock(), _SUMMARY_A))]
    df = aggregate_results(results)

    assert len(df) == 2
    agg_row = df[df["case_ref"] == "MACRO_AVG"].iloc[0]
    assert agg_row["optimization_score"] == pytest.approx(_SUMMARY_A.optimization_score)


@_PATCH_STRATEGY
def test_aggregate_results_none_result_gives_nan(_mock):
    """A None result gives NaN for numeric columns; MACRO_AVG excludes it."""
    results = [
        ("26-700001", (MagicMock(), _SUMMARY_A)),
        ("26-700002", None),
    ]
    df = aggregate_results(results)

    row_b = df[df["case_ref"] == "26-700002"].iloc[0]
    assert math.isnan(row_b["optimization_score"])

    # MACRO_AVG is computed only from the non-NaN case
    agg_row = df[df["case_ref"] == "MACRO_AVG"].iloc[0]
    assert agg_row["optimization_score"] == pytest.approx(_SUMMARY_A.optimization_score)


@_PATCH_STRATEGY
def test_aggregate_results_all_none_gives_no_metric_columns(_mock):
    """When all cases return None there are no numeric columns — only case_ref and chunking_strategy."""
    results = [("26-700001", None), ("26-700002", None)]
    df = aggregate_results(results)

    assert list(df.columns) == ["case_ref", "chunking_strategy"]
    assert "MACRO_AVG" in list(df["case_ref"])


@_PATCH_STRATEGY
def test_aggregate_results_writes_csv(_mock, tmp_path):
    """When output_path is provided the DataFrame is written as a CSV file."""
    csv_path = tmp_path / "summary" / "results.csv"
    results = [("26-700001", (MagicMock(), _SUMMARY_A))]

    df = aggregate_results(results, output_path=csv_path)

    assert csv_path.exists()
    loaded = pd.read_csv(csv_path)
    assert list(loaded["case_ref"]) == ["26-700001", "MACRO_AVG"]
    assert len(loaded.columns) == len(df.columns)


@_PATCH_STRATEGY
def test_aggregate_results_accepts_plain_dict_summary(_mock):
    """Summary provided as a plain dict (not EvaluationSummary) is handled correctly."""
    plain_dict = _SUMMARY_A.to_dict()
    results = [("26-700001", (MagicMock(), plain_dict))]

    df = aggregate_results(results)

    row = df[df["case_ref"] == "26-700001"].iloc[0]
    assert row["optimization_score"] == pytest.approx(_SUMMARY_A.optimization_score)
