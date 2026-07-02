"""Run relevance evaluation over all evaluation cases.

Loops over a list of :class:`~evaluation_suite.search_evaluation.multi_case.case_discovery.CaseSpec`
objects and calls :func:`~evaluation_suite.search_evaluation.run_single_evaluation.run_evaluation`
for each one, overriding ``CASE_FILTER`` so that each run is scoped to its
specific case.

Expected usage (after bootstrapping all cases)::

    from evaluation_suite.search_evaluation.multi_case.case_discovery import discover_cases
    from evaluation_suite.search_evaluation.multi_case.multi_case_runner import run_all_cases

    cases = discover_cases()

    # All 30 cases:
    results = run_all_cases(cases)

    # A subset — filter the list before passing:
    results = run_all_cases(cases[:5])
    results = run_all_cases([c for c in cases if c.case_ref in {"26-700001", "26-700003"}])

    # Single case — use run_evaluation directly (no overhead):
    from evaluation_suite.search_evaluation.run_single_evaluation import run_evaluation

    run_evaluation(settings_overrides={"CASE_FILTER": "26-700001"})

Individual CSV result files are suppressed (``log_to_file=False``) to keep the
output folder clean; the cumulative evaluation log is still updated after each
case.  Use the Phase 7 aggregator to produce a consolidated cross-case report.
"""

import logging
from pathlib import Path
from typing import Any

from evaluation_suite.search_evaluation.multi_case.case_discovery import CaseSpec
from evaluation_suite.search_evaluation.run_single_evaluation import run_evaluation

logger = logging.getLogger(__name__)

# Per-case search-term CSVs live at: evaluation_suite/testing_docs/cases/{case_ref}/search_terms.csv
_CASES_DIR = Path(__file__).resolve().parents[2] / "testing_docs" / "cases"


def run_all_cases(cases: list[CaseSpec]) -> list[tuple[str, tuple[Any, Any] | None]]:
    """Run relevance evaluation for every case in *cases*.

    For each case, ``CASE_FILTER`` is overridden to the case's reference so the
    evaluation is scoped to that case's indexed chunks.  Settings are reset to
    defaults after each case run (handled inside :func:`run_evaluation`).

    Args:
        cases: Ordered list of cases to evaluate.

    Returns:
        A list of ``(case_ref, result)`` tuples in the same order as *cases*.
        *result* is the ``(evaluated_df, summary)`` tuple returned by
        :func:`run_evaluation`, or ``None`` if evaluation produced no results
        for that case.
    """
    results: list[tuple[str, tuple[Any, Any] | None]] = []
    for case in cases:
        logger.info("Running evaluation for case '%s'...", case.case_ref)
        csv_path = _CASES_DIR / case.case_ref / "search_terms.csv"
        if not csv_path.exists():
            logger.warning(
                "Case '%s': per-case CSV not found at '%s', falling back to global CSV.",
                case.case_ref,
                csv_path,
            )
            csv_path = None
        result = run_evaluation(
            settings_overrides={"CASE_FILTER": case.case_ref},
            log_to_file=False,
            input_file=csv_path,
        )
        if result is None:
            logger.warning("Case '%s': evaluation returned no results.", case.case_ref)
        else:
            _, summary = result
            logger.info("Case '%s': evaluation complete — %s", case.case_ref, summary)
        results.append((case.case_ref, result))

    return results


__all__ = ["run_all_cases"]
