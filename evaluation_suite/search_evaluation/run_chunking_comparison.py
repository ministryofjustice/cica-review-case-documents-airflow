#!/usr/bin/env python
"""Compare search relevance across document chunking strategies.

This is the automated counterpart to :mod:`run_evaluation`. Rather than
evaluating a single, fixed corpus, it sweeps the chunking strategies used to
build the corpus and evaluates each one in turn. For every strategy it:

1. points the ingestion pipeline at that strategy,
2. resets the chunk index so it is re-ingested from scratch with that chunker,
3. runs a full evaluation, which re-ingests via ``bootstrap_opensearch`` and
   appends a row to the cumulative evaluation log.

Because each run is stamped with ``chunking_strategy`` and ``num_chunks_indexed``
(see :func:`evaluation_suite.search_evaluation.pipeline_config.get_search_config`),
the rows in ``output/evaluation/evaluation_log.csv`` are directly comparable —
the chunking strategy is an explicit column rather than a hidden variable.

Run:
    python -m evaluation_suite.search_evaluation.run_chunking_comparison

WARNING: this deletes and rebuilds the chunk index once per strategy, and the
final state of the index is whatever the last strategy in the sweep produced.
"""

import logging

from evaluation_suite.search_evaluation.opensearch.bootstrap import reset_chunk_index
from evaluation_suite.search_evaluation.run_single_evaluation import run_evaluation
from ingestion_pipeline.config import settings as ingestion_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("run_chunking_comparison")

# Strategies to sweep. Mirrors ALLOWED_CHUNKER_TYPES in the ingestion chunk
# strategy factory; edit this to restrict or reorder the sweep.
DEFAULT_CHUNKING_STRATEGIES: tuple[str, ...] = (
    "textractor-word-stream",
    "linear-sentence-splitter",
    "layout",
)


def run_chunking_comparison(
    strategies: tuple[str, ...] | list[str] | None = None,
) -> dict[str, tuple | None]:
    """Run a full evaluation for each chunking strategy and log every run.

    Args:
        strategies: Strategies to evaluate. Defaults to
            :data:`DEFAULT_CHUNKING_STRATEGIES`.

    Returns:
        Mapping of strategy name to the result returned by :func:`run_evaluation`
        for that strategy (an ``(evaluated_df, summary)`` tuple, or ``None`` if a
        run produced no results).
    """
    strategies = tuple(strategies) if strategies else DEFAULT_CHUNKING_STRATEGIES

    original_strategy = ingestion_settings.DOCUMENT_CHUNKING_STRATEGY
    results: dict[str, tuple | None] = {}
    try:
        for strategy in strategies:
            logger.info(f"=== Evaluating chunking strategy: {strategy} ===")
            # Point ingestion at this strategy; pipeline_builder reads this when
            # bootstrap triggers ingestion.
            ingestion_settings.DOCUMENT_CHUNKING_STRATEGY = strategy
            # Drop + recreate the index so bootstrap re-ingests with the new chunker.
            reset_chunk_index()
            # run_evaluation bootstraps (re-ingests the now-empty index), evaluates,
            # and appends a row to the cumulative log stamped with this strategy.
            results[strategy] = run_evaluation()
    finally:
        # Restore the original strategy so we don't leave the process mutated.
        ingestion_settings.DOCUMENT_CHUNKING_STRATEGY = original_strategy
        logger.info(f"Restored chunking strategy to '{original_strategy}'")

    return results


def cli_main() -> None:
    """Command-line interface entry point."""
    run_chunking_comparison()


if __name__ == "__main__":
    cli_main()
