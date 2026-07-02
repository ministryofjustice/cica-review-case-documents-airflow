#!/usr/bin/env python
"""End-to-end multi-case evaluation pipeline.

Runs all five phases in sequence for a configurable set of evaluation cases:

1. **Extract** — parse ``search_terms_source.docx`` and write per-case
   ``search_terms.csv`` files under ``testing_docs/cases/<case_ref>/``.
2. **Bootstrap** — ingest each case's PDF via the ingestion pipeline and index
   chunks into OpenSearch (idempotent: already-indexed cases are skipped).
3. **Expected chunks** — query OpenSearch to populate ``expected_chunk_id`` and
   ``expected_page_number`` in each case's CSV.
4. **Evaluate** — run the relevance scoring loop per case.
5. **Aggregate** — build a cross-case summary DataFrame and write a CSV report.

Usage
-----
Always run via the shell wrapper so credentials are loaded::

    ./run_multi_case_evaluation.sh

Optional flags::

    --cases 26-700001,26-700003   # restrict to a subset (comma-separated refs)
    --skip-extract                # skip step 1 (CSVs already generated)
    --skip-ingest                 # skip step 2 (cases already indexed)
    --output path/to/report.csv   # override default output path
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_multi_case_evaluation")

_EVAL_DIR = Path(__file__).resolve().parent  # evaluation_suite/
_REPO_ROOT = _EVAL_DIR.parent  # repo root
_TESTING_DOCS_DIR = _EVAL_DIR / "testing_docs"
_DOCX_PATH = _TESTING_DOCS_DIR / "search_terms_source.docx"
_CASES_DIR = _TESTING_DOCS_DIR / "cases"
_OUTPUT_DIR = _EVAL_DIR / "output"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the full multi-case evaluation pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--cases",
        default="",
        metavar="REFS",
        help=("Comma-separated case refs to run, e.g. 26-700001,26-700002. Defaults to all cases discovered in S3."),
    )
    p.add_argument(
        "--skip-extract",
        action="store_true",
        help="Skip step 1 — assume search_terms.csv files are already generated.",
    )
    p.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip step 2 — assume all cases are already indexed in OpenSearch.",
    )
    p.add_argument(
        "--output",
        default="",
        metavar="PATH",
        help=("Path for the aggregate CSV report. Defaults to evaluation_suite/output/multi_case_<timestamp>.csv."),
    )
    return p.parse_args()


def main() -> None:
    """Run the full multi-case search evaluation pipeline."""
    args = _parse_args()

    # ------------------------------------------------------------------
    # Step 1 — Extract search terms from source .docx
    # ------------------------------------------------------------------
    if args.skip_extract:
        logger.info("Step 1 skipped (--skip-extract).")
    else:
        logger.info("Step 1: extracting search terms from %s …", _DOCX_PATH)
        if not _DOCX_PATH.exists():
            logger.error(
                "Source .docx not found at %s — cannot generate CSVs.\n"
                "Place the file there or re-run with --skip-extract.",
                _DOCX_PATH,
            )
            sys.exit(1)
        from evaluation_suite.search_evaluation.multi_case.search_term_extractor import (
            extract_and_write_search_terms,
        )

        counts = extract_and_write_search_terms(_DOCX_PATH, _CASES_DIR)
        logger.info("Step 1 complete — %d case CSV(s) written.", len(counts))

    # ------------------------------------------------------------------
    # Step 2 — Discover cases and (optionally) bootstrap OpenSearch
    # ------------------------------------------------------------------
    logger.info("Discovering cases in S3 …")
    from evaluation_suite.search_evaluation.multi_case.case_discovery import discover_cases

    all_cases = discover_cases()

    if args.cases:
        requested = {ref.strip() for ref in args.cases.split(",")}
        cases = [c for c in all_cases if c.case_ref in requested]
        if not cases:
            logger.error(
                "No discovered cases matched --cases=%s.\nAvailable: %s",
                args.cases,
                [c.case_ref for c in all_cases],
            )
            sys.exit(1)
    else:
        cases = all_cases

    logger.info(
        "Pipeline will run for %d case(s): %s",
        len(cases),
        [c.case_ref for c in cases],
    )

    if args.skip_ingest:
        logger.info("Step 2 skipped (--skip-ingest).")
    else:
        logger.info("Step 2: bootstrapping %d case(s) into OpenSearch …", len(cases))
        from evaluation_suite.search_evaluation.multi_case.multi_case_bootstrap import bootstrap_all_cases

        chunk_counts = bootstrap_all_cases(cases)
        logger.info("Step 2 complete — chunk counts: %s", chunk_counts)

    # ------------------------------------------------------------------
    # Step 3 — Generate expected chunk IDs
    # ------------------------------------------------------------------
    logger.info("Step 3: generating expected chunks for %d case(s) …", len(cases))
    from evaluation_suite.search_evaluation.generate_expected_chunks import (
        generate_expected_chunks_for_case,
    )

    for case in cases:
        csv_path = _CASES_DIR / case.case_ref / "search_terms.csv"
        if not csv_path.exists():
            logger.warning(
                "Case '%s': search_terms.csv not found at %s — skipping expected chunks.",
                case.case_ref,
                csv_path,
            )
            continue
        generate_expected_chunks_for_case(case.case_ref, csv_path)

    logger.info("Step 3 complete.")

    # ------------------------------------------------------------------
    # Step 4 — Run per-case relevance evaluation
    # ------------------------------------------------------------------
    logger.info("Step 4: running relevance evaluation for %d case(s) …", len(cases))
    from evaluation_suite.search_evaluation.multi_case.multi_case_runner import run_all_cases

    results = run_all_cases(cases)
    logger.info("Step 4 complete.")

    # ------------------------------------------------------------------
    # Step 5 — Aggregate and write report
    # ------------------------------------------------------------------
    logger.info("Step 5: aggregating results …")
    now = datetime.now()
    output_path = Path(args.output) if args.output else _OUTPUT_DIR / f"{now:%Y%m%d}" / f"multi_case_{now:%H%M%S}.csv"
    from evaluation_suite.search_evaluation.multi_case.multi_case_aggregator import aggregate_results

    summary_df = aggregate_results(results, output_path=output_path)
    logger.info("Step 5 complete — report written to %s", output_path)

    logger.info("\n%s", summary_df.to_string())


if __name__ == "__main__":
    main()
