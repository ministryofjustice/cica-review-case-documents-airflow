#!/usr/bin/env python
"""30-case chunking strategy comparison.

The multi-case equivalent of :mod:`run_chunking_comparison`. Sweeps all three
chunking strategies over all 30 UAT cases (or a configured subset) and writes
a per-strategy aggregate CSV for each.

For each strategy the script:

1. Resets the shared OpenSearch chunk index (drops + recreates).
2. Re-ingests all cases via the production ingestion pipeline (uses real AWS
   S3 / Textract — LocalStack is not required for ingestion).
3. Regenerates expected chunk IDs for every per-case ``search_terms.csv``
   (ground truth depends on what is currently indexed).
4. Runs the relevance scoring loop across all cases.
5. Writes an aggregate CSV named
   ``output/<YYYYMMDD>/multi_case_chunking_<strategy>_<HHMMSS>.csv``.

Run via the shell wrapper (which loads credentials and starts Docker services)::

    ./run_multi_case_chunking_comparison.sh

Optional flags::

    --cases 26-700001,26-700002    restrict to a subset of cases
    --strategies layout,textractor-word-stream   restrict to specific strategies

WARNING: this script resets and rebuilds the chunk index once per strategy.
The final state of the index reflects the last strategy in the sweep (``layout``
by default).
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
logger = logging.getLogger("run_multi_case_chunking_comparison")

_EVAL_DIR = Path(__file__).resolve().parent  # evaluation_suite/
_CASES_DIR = _EVAL_DIR / "testing_docs" / "cases"
_OUTPUT_DIR = _EVAL_DIR / "output"

DEFAULT_CHUNKING_STRATEGIES: tuple[str, ...] = (
    "textractor-word-stream",
    "linear-sentence-splitter",
    "layout",
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the full 30-case evaluation for each chunking strategy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--cases",
        default="",
        metavar="REFS",
        help=("Comma-separated case refs to run, e.g. 26-700001,26-700002. Defaults to all cases discovered in S3."),
    )
    p.add_argument(
        "--strategies",
        default="",
        metavar="NAMES",
        help=(f"Comma-separated strategies to sweep. Defaults to all three: {','.join(DEFAULT_CHUNKING_STRATEGIES)}."),
    )
    return p.parse_args()


def run_multi_case_chunking_comparison(
    cases: list,
    strategies: tuple[str, ...] = DEFAULT_CHUNKING_STRATEGIES,
) -> dict[str, list]:
    """Sweep *strategies* over *cases* and write a per-strategy aggregate CSV.

    Args:
        cases: List of :class:`~evaluation_suite.search_evaluation.multi_case.case_discovery.CaseSpec`
            objects to evaluate.
        strategies: Chunking strategy names to sweep.

    Returns:
        Mapping of strategy name → ``(case_ref, result)`` list as returned by
        :func:`~evaluation_suite.search_evaluation.multi_case.multi_case_runner.run_all_cases`.
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

    original_strategy = ingestion_settings.DOCUMENT_CHUNKING_STRATEGY
    original_env_strategy = os.environ.get("DOCUMENT_CHUNKING_STRATEGY")

    all_results: dict[str, list] = {}
    try:
        for strategy in strategies:
            logger.info(
                "=== Chunking strategy: %s (%d cases) ===",
                strategy,
                len(cases),
            )

            # Update the in-process settings object (used by bootstrap state checks)
            # AND the env var (inherited by ingestion subprocesses).
            ingestion_settings.DOCUMENT_CHUNKING_STRATEGY = strategy
            os.environ["DOCUMENT_CHUNKING_STRATEGY"] = strategy

            # --- Step 1: reset index ------------------------------------------
            logger.info("[%s] Resetting chunk index…", strategy)
            reset_chunk_index()

            # --- Step 2: ingest all cases with this strategy ------------------
            logger.info("[%s] Ingesting %d case(s)…", strategy, len(cases))
            chunk_counts = bootstrap_all_cases(cases)
            zero_chunk_cases = [c for c, n in chunk_counts.items() if n == 0]
            if zero_chunk_cases:
                logger.warning(
                    "[%s] %d case(s) produced 0 chunks — results may be incomplete: %s",
                    strategy,
                    len(zero_chunk_cases),
                    zero_chunk_cases,
                )
            logger.info("[%s] Ingestion complete.", strategy)

            # --- Step 3: regenerate expected chunks ---------------------------
            # Ground truth is corpus-dependent: must be refreshed after each
            # index rebuild so it matches the chunks from this strategy.
            logger.info("[%s] Regenerating expected chunk IDs…", strategy)
            for case in cases:
                csv_path = _CASES_DIR / case.case_ref / "search_terms.csv"
                if csv_path.exists():
                    generate_expected_chunks_for_case(case.case_ref, csv_path)
                else:
                    logger.warning(
                        "[%s] Case '%s': no search_terms.csv at '%s' — skipping.",
                        strategy,
                        case.case_ref,
                        csv_path,
                    )

            # --- Step 4: evaluate all cases -----------------------------------
            logger.info("[%s] Running relevance evaluation…", strategy)
            results = run_all_cases(cases)
            all_results[strategy] = results

            # --- Step 5: write aggregate CSV ----------------------------------
            now = datetime.now()
            safe_strategy = strategy.replace("-", "_")
            output_path = _OUTPUT_DIR / f"{now:%Y%m%d}" / f"multi_case_chunking_{safe_strategy}_{now:%H%M%S}.csv"
            summary_df = aggregate_results(results, output_path=output_path)
            logger.info(
                "[%s] Results written to %s\n%s",
                strategy,
                output_path,
                summary_df.tail(1).to_string(),  # MACRO_AVG row
            )

    finally:
        # Restore original strategy so the process is not left in a mutated state.
        ingestion_settings.DOCUMENT_CHUNKING_STRATEGY = original_strategy
        if original_env_strategy is None:
            os.environ.pop("DOCUMENT_CHUNKING_STRATEGY", None)
        else:
            os.environ["DOCUMENT_CHUNKING_STRATEGY"] = original_env_strategy
        logger.info("Restored chunking strategy to '%s'.", original_strategy)

    return all_results


def main() -> None:
    """Run a multi-case chunking strategy comparison across all configured strategies."""
    args = _parse_args()

    strategies: tuple[str, ...] = (
        tuple(s.strip() for s in args.strategies.split(",")) if args.strategies else DEFAULT_CHUNKING_STRATEGIES
    )

    # Discover cases from S3 and optionally filter to the requested subset.
    logger.info("Discovering cases in S3…")
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
        "Sweeping %d strategy/strategies over %d case(s): %s",
        len(strategies),
        len(cases),
        [c.case_ref for c in cases],
    )

    run_multi_case_chunking_comparison(cases=cases, strategies=strategies)
    logger.info("All strategies complete.")


if __name__ == "__main__":
    main()
