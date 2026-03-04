#!/usr/bin/env python
"""Bayesian optimization for search configuration parameters.

This script uses Optuna to find the optimal combination of search boosts
that maximizes the optimization score from the evaluation framework.

Usage:
    python -m evaluation_suite.search_evaluation.optimize_search

The script will:
1. Phase 1: Coarse search with step=0.3 to explore the parameter space
2. Phase 2: Fine-tuning with step=0.05 around the best region found
3. Log all trials to the evaluation_log.csv (full audit trail)
4. Save the best parameters found to a JSON file
5. Print a summary of the optimization results
"""

import argparse
import logging
import warnings

import optuna

from evaluation_suite.search_evaluation import evaluation_settings as eval_settings
from evaluation_suite.search_evaluation.opensearch_client import check_opensearch_health
from evaluation_suite.search_evaluation.optimization_engine import run_optimization
from evaluation_suite.search_evaluation.optimization_results import OUTPUT_DIR, print_summary, save_results

# Suppress Optuna UserWarnings about step size not dividing range evenly
warnings.filterwarnings(
    "ignore",
    message="The distribution is specified by .* and step=.*, but the range is not divisible by `step`.*",
    category=UserWarning,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("optimize_search")

logging.getLogger("opensearch").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("optuna").setLevel(logging.CRITICAL)  # Suppress all Optuna trial logging

# Reduce optuna verbosity to maximum
optuna.logging.set_verbosity(optuna.logging.CRITICAL)


def run_optimization_workflow(n_trials: int | None = None, two_phase: bool = True) -> optuna.Study:
    """Run the complete optimization workflow.

    This is the main business logic function that orchestrates the optimization process.

    Args:
        n_trials: Total number of optimization trials to run. If None, uses OPTIMIZATION_DEFAULT_N_TRIALS.
        two_phase: If True, use coarse step for first half, fine step for second.

    Returns:
        Completed Optuna study with all trial results.
    """
    # Use default n_trials if not specified
    if n_trials is None:
        n_trials = eval_settings.OPTIMIZATION_DEFAULT_N_TRIALS

    # Pre-flight check: verify OpenSearch is reachable before starting optimization
    try:
        check_opensearch_health()
    except ConnectionError as e:
        logger.error(str(e))
        raise SystemExit(1) from e

    logger.info("=" * 60)
    logger.info("SEARCH PARAMETER OPTIMIZATION")
    logger.info("=" * 60)
    if two_phase:
        logger.info("Mode: Two-phase (coarse then fine-tuning)")
    else:
        logger.info(f"Mode: Single-phase (step={eval_settings.OPTIMIZATION_SINGLE_PHASE_STEP})")

    # Run optimization
    study = run_optimization(n_trials=n_trials, two_phase=two_phase)

    # Save results
    save_results(study)

    # Print summary
    print_summary(study)

    # Suggest next steps
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Review the best parameters above")
    logger.info("2. Update evaluation_settings.py with the best values")
    logger.info("3. Run a full evaluation to confirm: python -m evaluation_suite.search_evaluation.run_evaluation")
    logger.info(f"4. Results saved in: {OUTPUT_DIR / 'latest'}")

    return study


def main(n_trials: int | None = None, two_phase: bool = True) -> optuna.Study:
    """Main entry point for optimization (legacy compatibility).

    This function exists for backward compatibility with existing code and tests.
    New code should use run_optimization_workflow() directly.

    Args:
        n_trials: Total number of optimization trials to run. If None, uses OPTIMIZATION_DEFAULT_N_TRIALS.
        two_phase: If True, use coarse step for first half, fine step for second.

    Returns:
        Completed Optuna study with all trial results.
    """
    return run_optimization_workflow(n_trials=n_trials, two_phase=two_phase)


def cli_main() -> None:
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description="Optimize search configuration parameters using Bayesian optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 30 trials with two-phase optimization (default)
  python -m evaluation_suite.search_evaluation.optimize_search

  # Run 50 trials
  python -m evaluation_suite.search_evaluation.optimize_search --n-trials 50

  # Run single-phase optimization
  python -m evaluation_suite.search_evaluation.optimize_search --single-phase
        """,
    )
    parser.add_argument(
        "--n-trials",
        type=int,
        default=eval_settings.OPTIMIZATION_DEFAULT_N_TRIALS,
        help=f"Total number of optimization trials to run (default: {eval_settings.OPTIMIZATION_DEFAULT_N_TRIALS})",
    )
    parser.add_argument(
        "--single-phase",
        action="store_true",
        help="Run single phase optimization instead of two-phase",
    )
    args = parser.parse_args()

    run_optimization_workflow(n_trials=args.n_trials, two_phase=not args.single_phase)


if __name__ == "__main__":
    cli_main()
