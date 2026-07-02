"""Aggregate per-case evaluation results into a consolidated summary.

Takes the ``list[(case_ref, result)]`` output from
:func:`~evaluation_suite.search_evaluation.multi_case.multi_case_runner.run_all_cases`
and produces a :class:`pandas.DataFrame` with one row per case plus a
``MACRO_AVG`` row that macro-averages all numeric metrics across cases.

Macro-averaging treats each case equally regardless of how many queries it
contains, which is the standard choice when cases may have different query
counts.  Cases whose evaluation produced no results (``None``) contribute
``NaN`` to the DataFrame and are excluded from the macro-average denominator.

Typical usage::

    from evaluation_suite.search_evaluation.multi_case.multi_case_runner import run_all_cases
    from evaluation_suite.search_evaluation.multi_case.multi_case_aggregator import aggregate_results

    results = run_all_cases(cases)
    summary_df = aggregate_results(results, output_path=Path("output/multi_case_summary.csv"))
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _resolve_chunking_strategy() -> str:
    """Return the ingestion pipeline's configured chunking strategy."""
    try:
        from ingestion_pipeline.config import settings as ingestion_settings

        return ingestion_settings.DOCUMENT_CHUNKING_STRATEGY
    except Exception:
        return "unknown"


def _summary_to_dict(summary: Any) -> dict:
    """Coerce *summary* to a plain dict regardless of its concrete type."""
    if hasattr(summary, "to_dict"):
        return summary.to_dict()
    return dict(summary)


def aggregate_results(
    results: list[tuple[str, tuple[Any, Any] | None]],
    output_path: Path | None = None,
) -> pd.DataFrame:
    """Aggregate per-case evaluation results into a summary DataFrame.

    Args:
        results: Output from :func:`run_all_cases` — an ordered list of
            ``(case_ref, result)`` pairs where *result* is
            ``(evaluated_df, summary)`` or ``None``.
        output_path: Optional path to write the CSV.  Parent directories are
            created if they do not exist.

    Returns:
        A :class:`pandas.DataFrame` with one row per case followed by a
        ``MACRO_AVG`` aggregate row.  The DataFrame is empty when *results*
        is empty.  Numeric columns for cases with no results contain ``NaN``.
    """
    chunking_strategy = _resolve_chunking_strategy()

    rows: list[dict] = []
    for case_ref, result in results:
        if result is None:
            rows.append({"case_ref": case_ref, "chunking_strategy": chunking_strategy})
        else:
            _, summary = result
            rows.append({"case_ref": case_ref, "chunking_strategy": chunking_strategy, **_summary_to_dict(summary)})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Macro-average: column-wise mean over numeric columns only.
    # Non-numeric label columns (case_ref, chunking_strategy) are excluded.
    # pandas.DataFrame.mean() ignores NaN by default (skipna=True).
    _label_cols = {"case_ref", "chunking_strategy"}
    numeric_cols = [c for c in df.columns if c not in _label_cols]
    agg_values: dict[str, Any] = {"case_ref": "MACRO_AVG", "chunking_strategy": chunking_strategy}
    for col in numeric_cols:
        agg_values[col] = df[col].mean()

    df = pd.concat([df, pd.DataFrame([agg_values])], ignore_index=True)

    # Keep only the headline columns — drop @20 variants and redundant counters.
    _REPORT_COLUMNS = [
        "case_ref",
        "chunking_strategy",
        "total_queries",
        "avg_chunks_returned",
        "queries_with_expected_chunk",
        "avg_precision_at_10",
        "avg_recall_at_10",
        "avg_f1_at_10",
        "optimization_score",
    ]
    report_cols = [c for c in _REPORT_COLUMNS if c in df.columns]
    df = df[report_cols]

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info("Aggregated results written to %s", output_path)

    return df


__all__ = ["aggregate_results"]
