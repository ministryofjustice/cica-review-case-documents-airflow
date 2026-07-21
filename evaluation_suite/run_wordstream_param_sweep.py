#!/usr/bin/env python
"""Word-stream chunker parameter sweep.

Tests six named parameter presets of the ``textractor-word-stream`` chunker and
measures their effect on search evaluation metrics.

Run single-case first (fast, ~5–10 min) to check the presets behave sensibly
before launching the overnight 30-case sweep::

    ./run_wordstream_param_sweep.sh            # single case — 26-711111
    ./run_wordstream_param_sweep.sh --multi    # all 30 UAT cases

Optional flags::

    --presets baseline,compact          restrict to named presets
    --cases 26-700001,26-700002         restrict to case refs (multi mode only)

Outputs
-------
Single-case mode:
  ``evaluation_suite/output/YYYYMMDD/wordstream_param_sweep_single_HHMMSS.csv``
  Six rows (one per preset) with headline metrics and the preset parameter values.

Multi-case mode:
  ``evaluation_suite/output/YYYYMMDD/wordstream_param_sweep_multi_HHMMSS.csv``
  One row per (preset × case) plus a ``MACRO_AVG`` row per preset, with preset
  parameter columns prepended.

How parameters are injected
---------------------------
Each preset overrides four env vars and four ``ingestion_pipeline.config.settings``
attributes before index reset and re-ingestion.  The env vars propagate to any
subprocesses; the direct attribute write takes effect for in-process calls.
Settings are restored to their original values in a ``finally`` block.

WARNING: this script resets and rebuilds the OpenSearch chunk index once per
preset.  The final state of the index reflects the last preset in the sweep.
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_wordstream_param_sweep")

_EVAL_DIR = Path(__file__).resolve().parent  # evaluation_suite/
_CASES_DIR = _EVAL_DIR / "testing_docs" / "cases"
_OUTPUT_DIR = _EVAL_DIR / "output"

# ---------------------------------------------------------------------------
# Parameter presets
# ---------------------------------------------------------------------------
# Only min_words, max_words, and gap_ratio are varied; forward_lookahead_words
# and backward_scan_words remain at their defaults (8 and 20 respectively).
PARAM_PRESETS: list[dict] = [
    {"name": "baseline", "min_words": 80, "max_words": 120, "gap_ratio": 0.05},
    {"name": "compact", "min_words": 50, "max_words": 80, "gap_ratio": 0.05},
    {"name": "large", "min_words": 100, "max_words": 150, "gap_ratio": 0.05},
    {"name": "gap-tight", "min_words": 80, "max_words": 120, "gap_ratio": 0.03},
    {"name": "gap-loose", "min_words": 80, "max_words": 120, "gap_ratio": 0.08},
    {"name": "compact-gap-tight", "min_words": 50, "max_words": 80, "gap_ratio": 0.03},
]

_WORDSTREAM_STRATEGY = "textractor-word-stream"

_OVERRIDE_ENV_KEYS = (
    "DOCUMENT_CHUNKING_STRATEGY",
    "WORDSTREAM_CHUNKER_MIN_WORDS",
    "WORDSTREAM_CHUNKER_MAX_WORDS",
    "WORDSTREAM_CHUNKER_MAX_VERTICAL_GAP_RATIO",
)

# Columns included in every output CSV (metrics sourced from EvaluationSummary)
_REPORT_COLUMNS = [
    "preset_name",
    "min_words",
    "max_words",
    "gap_ratio",
    "total_queries",
    "avg_chunks_returned",
    "queries_with_expected_chunk",
    "avg_precision_at_10",
    "avg_recall_at_10",
    "avg_f1_at_10",
    "optimization_score",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _save_original_settings(ingestion_settings) -> dict:
    """Snapshot the settings attributes we will override."""
    return {
        "DOCUMENT_CHUNKING_STRATEGY": ingestion_settings.DOCUMENT_CHUNKING_STRATEGY,
        "WORDSTREAM_CHUNKER_MIN_WORDS": ingestion_settings.WORDSTREAM_CHUNKER_MIN_WORDS,
        "WORDSTREAM_CHUNKER_MAX_WORDS": ingestion_settings.WORDSTREAM_CHUNKER_MAX_WORDS,
        "WORDSTREAM_CHUNKER_MAX_VERTICAL_GAP_RATIO": ingestion_settings.WORDSTREAM_CHUNKER_MAX_VERTICAL_GAP_RATIO,
    }


def _apply_preset(ingestion_settings, preset: dict) -> None:
    """Apply one preset to both the in-process settings object and env vars."""
    # In-process settings (used by calls in this Python process)
    ingestion_settings.DOCUMENT_CHUNKING_STRATEGY = _WORDSTREAM_STRATEGY
    ingestion_settings.WORDSTREAM_CHUNKER_MIN_WORDS = preset["min_words"]
    ingestion_settings.WORDSTREAM_CHUNKER_MAX_WORDS = preset["max_words"]
    ingestion_settings.WORDSTREAM_CHUNKER_MAX_VERTICAL_GAP_RATIO = preset["gap_ratio"]

    # Env vars (propagated to any subprocesses, e.g. ingestion runner)
    os.environ["DOCUMENT_CHUNKING_STRATEGY"] = _WORDSTREAM_STRATEGY
    os.environ["WORDSTREAM_CHUNKER_MIN_WORDS"] = str(preset["min_words"])
    os.environ["WORDSTREAM_CHUNKER_MAX_WORDS"] = str(preset["max_words"])
    os.environ["WORDSTREAM_CHUNKER_MAX_VERTICAL_GAP_RATIO"] = str(preset["gap_ratio"])


def _restore_settings(ingestion_settings, original_attrs: dict, original_env: dict) -> None:
    """Restore settings and env vars to the snapshot captured before the sweep."""
    for attr, value in original_attrs.items():
        setattr(ingestion_settings, attr, value)

    for key in _OVERRIDE_ENV_KEYS:
        original_value = original_env.get(key)
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value


def _summary_to_dict(summary) -> dict:
    """Coerce EvaluationSummary or plain dict to a plain dict."""
    if hasattr(summary, "to_dict"):
        return summary.to_dict()
    return dict(summary)


def _preset_header(preset: dict) -> str:
    return f"preset={preset['name']}  min={preset['min_words']}  max={preset['max_words']}  gap={preset['gap_ratio']}"


# ---------------------------------------------------------------------------
# Single-case sweep
# ---------------------------------------------------------------------------


def run_single_case_sweep(presets: list[dict]) -> list[dict]:
    """Run each preset against the standard single-case fixture (26-711111).

    Returns:
        List of result dicts, one per preset, with preset params and metrics.
    """
    # Install Textract disk cache before any ingestion pipeline imports so that
    # the first preset populates the cache and subsequent presets reuse it,
    # reducing re-ingestion from ~2 min to ~seconds for presets 2–6.
    from evaluation_suite.search_evaluation.multi_case.textract_cache import install_cache

    install_cache()

    from evaluation_suite.search_evaluation.generate_expected_chunks import (
        generate_expected_chunks,
    )
    from evaluation_suite.search_evaluation.multi_case.case_discovery import CaseSpec
    from evaluation_suite.search_evaluation.multi_case.multi_case_bootstrap import bootstrap_all_cases
    from evaluation_suite.search_evaluation.opensearch.bootstrap import reset_chunk_index
    from evaluation_suite.search_evaluation.run_single_evaluation import run_evaluation
    from ingestion_pipeline.config import settings as ingestion_settings

    # Build a CaseSpec for the single-case fixture.
    # Using bootstrap_all_cases (subprocess path) avoids the LocalStack PDF
    # download issue that affects the in-process bootstrap_opensearch() call.
    single_case = CaseSpec(
        case_ref=ingestion_settings.AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX,
        s3_filename=ingestion_settings.AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME,
    )

    original_attrs = _save_original_settings(ingestion_settings)
    original_env = {k: os.environ.get(k) for k in _OVERRIDE_ENV_KEYS}

    rows: list[dict] = []
    try:
        for preset in presets:
            logger.info("=== Single-case sweep — %s ===", _preset_header(preset))

            _apply_preset(ingestion_settings, preset)

            # Rebuild the index so it reflects only this preset's chunks.
            logger.info("[%s] Resetting chunk index…", preset["name"])
            reset_chunk_index()

            # Ingest 26-711111 via subprocess (same path as multi-case), which
            # sets LOCAL_DEVELOPMENT_MODE=false and uses the MOD-platform S3
            # bucket/credentials — avoiding the LocalStack dependency.
            logger.info("[%s] Ingesting case %s…", preset["name"], single_case.case_ref)
            chunk_counts = bootstrap_all_cases([single_case])
            if chunk_counts.get(single_case.case_ref, 0) == 0:
                logger.warning(
                    "[%s] 0 chunks indexed for %s — skipping evaluation.",
                    preset["name"],
                    single_case.case_ref,
                )
                rows.append(
                    {
                        "preset_name": preset["name"],
                        "min_words": preset["min_words"],
                        "max_words": preset["max_words"],
                        "gap_ratio": preset["gap_ratio"],
                    }
                )
                continue

            # Regenerate expected chunk IDs from the freshly indexed corpus so
            # evaluate_relevance uses fresh IDs rather than stale ones from a
            # previous preset run.
            logger.info("[%s] Regenerating expected chunk IDs…", preset["name"])
            generate_expected_chunks()

            # Evaluate — bootstrap inside run_evaluation is a no-op (non-empty index).
            logger.info("[%s] Running evaluation…", preset["name"])
            result = run_evaluation(log_to_file=False)

            if result is None:
                logger.warning("[%s] Evaluation returned no results.", preset["name"])
                rows.append(
                    {
                        "preset_name": preset["name"],
                        "min_words": preset["min_words"],
                        "max_words": preset["max_words"],
                        "gap_ratio": preset["gap_ratio"],
                    }
                )
                continue

            _, summary = result
            row = {
                "preset_name": preset["name"],
                "min_words": preset["min_words"],
                "max_words": preset["max_words"],
                "gap_ratio": preset["gap_ratio"],
                **_summary_to_dict(summary),
            }
            rows.append(row)
            logger.info(
                "[%s] P@10=%.1f%%  R@10=%.1f%%  F1@10=%.1f%%  score=%.4f",
                preset["name"],
                row.get("avg_precision_at_10", 0) * 100,
                row.get("avg_recall_at_10", 0) * 100,
                row.get("avg_f1_at_10", 0) * 100,
                row.get("optimization_score", 0),
            )

    finally:
        _restore_settings(ingestion_settings, original_attrs, original_env)
        logger.info("Restored original settings.")

    return rows


# ---------------------------------------------------------------------------
# Multi-case sweep
# ---------------------------------------------------------------------------


def run_multi_case_sweep(presets: list[dict], cases: list) -> list[dict]:
    """Run each preset across all *cases*.

    Returns:
        Flat list of result dicts: one per (preset × case) plus one MACRO_AVG
        row per preset.  Each dict includes the preset parameters.
    """
    from evaluation_suite.search_evaluation.generate_expected_chunks import (
        generate_expected_chunks_for_case,
    )
    from evaluation_suite.search_evaluation.multi_case.multi_case_aggregator import (
        aggregate_results,
    )
    from evaluation_suite.search_evaluation.multi_case.multi_case_bootstrap import (
        bootstrap_all_cases,
    )
    from evaluation_suite.search_evaluation.multi_case.multi_case_runner import run_all_cases
    from evaluation_suite.search_evaluation.opensearch.bootstrap import reset_chunk_index
    from ingestion_pipeline.config import settings as ingestion_settings

    original_attrs = _save_original_settings(ingestion_settings)
    original_env = {k: os.environ.get(k) for k in _OVERRIDE_ENV_KEYS}

    all_rows: list[dict] = []
    try:
        for preset in presets:
            logger.info(
                "=== Multi-case sweep — %s (%d cases) ===",
                _preset_header(preset),
                len(cases),
            )

            _apply_preset(ingestion_settings, preset)

            # --- Step 1: reset index ----------------------------------------
            logger.info("[%s] Resetting chunk index…", preset["name"])
            reset_chunk_index()

            # --- Step 2: ingest all cases -----------------------------------
            logger.info("[%s] Ingesting %d case(s)…", preset["name"], len(cases))
            chunk_counts = bootstrap_all_cases(cases)
            zero_chunk_cases = [c for c, n in chunk_counts.items() if n == 0]
            if zero_chunk_cases:
                logger.warning(
                    "[%s] %d case(s) produced 0 chunks — results may be incomplete: %s",
                    preset["name"],
                    len(zero_chunk_cases),
                    zero_chunk_cases,
                )

            # --- Step 3: regenerate expected chunk IDs ----------------------
            logger.info("[%s] Regenerating expected chunk IDs…", preset["name"])
            for case in cases:
                csv_path = _CASES_DIR / case.case_ref / "search_terms.csv"
                if csv_path.exists():
                    generate_expected_chunks_for_case(case.case_ref, csv_path)
                else:
                    logger.warning(
                        "[%s] Case '%s': no search_terms.csv at '%s' — skipping.",
                        preset["name"],
                        case.case_ref,
                        csv_path,
                    )

            # --- Step 4: evaluate all cases ---------------------------------
            logger.info("[%s] Running relevance evaluation…", preset["name"])
            results = run_all_cases(cases)

            # --- Step 5: aggregate results ----------------------------------
            # Write per-preset CSV as a checkpoint; also collect rows for the
            # consolidated output.
            now = datetime.now()
            checkpoint_path = (
                _OUTPUT_DIR / f"{now:%Y%m%d}" / f"wordstream_param_sweep_{preset['name']}_{now:%H%M%S}.csv"
            )
            summary_df = aggregate_results(results, output_path=checkpoint_path)
            logger.info("[%s] Checkpoint written to %s", preset["name"], checkpoint_path)

            # Prepend preset parameter columns.
            for col, val in [
                ("gap_ratio", preset["gap_ratio"]),
                ("max_words", preset["max_words"]),
                ("min_words", preset["min_words"]),
                ("preset_name", preset["name"]),
            ]:
                summary_df.insert(0, col, val)

            all_rows.extend(summary_df.to_dict(orient="records"))

            macro_row = summary_df[summary_df["case_ref"] == "MACRO_AVG"]
            if not macro_row.empty:
                r = macro_row.iloc[0]
                logger.info(
                    "[%s] MACRO_AVG — P@10=%.1f%%  R@10=%.1f%%  F1@10=%.1f%%",
                    preset["name"],
                    float(r.get("avg_precision_at_10", 0)) * 100,
                    float(r.get("avg_recall_at_10", 0)) * 100,
                    float(r.get("avg_f1_at_10", 0)) * 100,
                )

    finally:
        _restore_settings(ingestion_settings, original_attrs, original_env)
        logger.info("Restored original settings.")

    return all_rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sweep word-stream chunker parameter presets over one case (default) or 30 cases (--multi).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--multi",
        action="store_true",
        help="Run the full 30-case sweep instead of the single-case fixture.",
    )
    p.add_argument(
        "--cases",
        default="",
        metavar="REFS",
        help="(multi mode) Comma-separated case refs to include, e.g. 26-700001,26-700002.",
    )
    p.add_argument(
        "--presets",
        default="",
        metavar="NAMES",
        help=(
            "Comma-separated preset names to run, e.g. baseline,compact. "
            f"Defaults to all {len(PARAM_PRESETS)}: {','.join(p['name'] for p in PARAM_PRESETS)}."
        ),
    )
    p.add_argument(
        "--output",
        default="",
        metavar="PATH",
        help="Override the default output CSV path.",
    )
    return p.parse_args()


def main() -> None:
    """Entry point for the word-stream parameter sweep."""
    args = _parse_args()

    # Filter presets if requested.
    if args.presets:
        requested_names = {n.strip() for n in args.presets.split(",")}
        presets = [p for p in PARAM_PRESETS if p["name"] in requested_names]
        unknown = requested_names - {p["name"] for p in presets}
        if unknown:
            logger.error("Unknown preset name(s): %s. Known: %s", unknown, [p["name"] for p in PARAM_PRESETS])
            sys.exit(1)
    else:
        presets = PARAM_PRESETS

    now = datetime.now()

    if args.multi:
        # Discover cases from S3.
        logger.info("Discovering cases in S3…")
        from evaluation_suite.search_evaluation.multi_case.case_discovery import discover_cases

        all_cases = discover_cases()
        if args.cases:
            requested_refs = {ref.strip() for ref in args.cases.split(",")}
            cases = [c for c in all_cases if c.case_ref in requested_refs]
            if not cases:
                logger.error("No cases matched %s — available: %s", requested_refs, [c.case_ref for c in all_cases])
                sys.exit(1)
        else:
            cases = all_cases

        logger.info("Running multi-case param sweep: %d presets × %d cases", len(presets), len(cases))
        rows = run_multi_case_sweep(presets, cases)

        output_path = (
            Path(args.output)
            if args.output
            else _OUTPUT_DIR / f"{now:%Y%m%d}" / f"wordstream_param_sweep_multi_{now:%H%M%S}.csv"
        )
    else:
        logger.info("Running single-case param sweep: %d presets against 26-711111", len(presets))
        rows = run_single_case_sweep(presets)

        output_path = (
            Path(args.output)
            if args.output
            else _OUTPUT_DIR / f"{now:%Y%m%d}" / f"wordstream_param_sweep_single_{now:%H%M%S}.csv"
        )

    if not rows:
        logger.error("No results collected — nothing to write.")
        sys.exit(1)

    import pandas as pd

    df = pd.DataFrame(rows)
    # Keep only the report columns that exist in the data.
    report_cols = [c for c in _REPORT_COLUMNS if c in df.columns] + [c for c in df.columns if c not in _REPORT_COLUMNS]
    df = df[[c for c in report_cols if c in df.columns]]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Results written to %s", output_path)
    logger.info("\n%s", df.to_string())


if __name__ == "__main__":
    main()
