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
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import optuna
from optuna.samplers import TPESampler
from optuna.trial import FrozenTrial

from evaluation_suite.search_evaluation.run_evaluation import run_evaluation

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("optimize_search")

# Reduce optuna verbosity
optuna.logging.set_verbosity(optuna.logging.WARNING)

# Output directory for optimization results
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output" / "optimization"

# Constants for optimization
PENALTY_SCORE = -1000.0
BOOST_RANGE = (0.0, 5.0)
PRECISION = 4  # Decimal places for rounding


class OptimizationObjective:
    """Callable class for Optuna optimization objective.

    This class encapsulates the objective function logic, making it easier to test
    and allowing for dependency injection of the evaluation runner.
    """

    def __init__(
        self,
        step: float = 0.1,
        evaluation_runner: Callable[..., tuple | None] = run_evaluation,
    ):
        """Initialize the optimization objective.

        Args:
            step: Step size for parameter suggestions (0.1 for coarse, 0.05 for fine).
            evaluation_runner: Evaluation function to call for each trial.
                              Defaults to run_evaluation. Override in tests for dependency injection.
        """
        self.step = step
        self.evaluation_runner = evaluation_runner

    def __call__(self, trial: optuna.Trial) -> float:
        """Run a single optimization trial.

        Args:
            trial: Optuna trial object for suggesting parameters.

        Returns:
            Optimization score (higher is better).
        """
        # Suggest boost parameters
        params = self._suggest_parameters(trial)

        # Validate parameters
        if not self._validate_parameters(params):
            return PENALTY_SCORE

        # Build settings overrides
        settings_overrides = self._build_settings_overrides(params)
        logger.info(f"Trial {trial.number}: {settings_overrides}")

        # Run evaluation and extract score
        try:
            score = self._run_trial_evaluation(trial, settings_overrides)
            logger.info(f"Trial {trial.number} score: {score:.4f}")
            return score
        except Exception as e:
            logger.error(f"Trial {trial.number} failed: {e}")
            return PENALTY_SCORE

    def _suggest_parameters(self, trial: optuna.Trial) -> dict[str, float]:
        """Suggest parameter values for this trial.

        Args:
            trial: Optuna trial object.

        Returns:
            Dictionary of suggested parameter values.
        """
        return {
            "KEYWORD_BOOST": trial.suggest_float("KEYWORD_BOOST", *BOOST_RANGE, step=self.step),
            "ANALYSER_BOOST": trial.suggest_float("ANALYSER_BOOST", *BOOST_RANGE, step=self.step),
            "SEMANTIC_BOOST": trial.suggest_float("SEMANTIC_BOOST", *BOOST_RANGE, step=self.step),
            "FUZZY_BOOST": trial.suggest_float("FUZZY_BOOST", *BOOST_RANGE, step=self.step),
            "WILDCARD_BOOST": trial.suggest_float("WILDCARD_BOOST", *BOOST_RANGE, step=self.step),
        }

    def _validate_parameters(self, params: dict[str, float]) -> bool:
        """Validate that at least one boost parameter is non-zero.

        Args:
            params: Dictionary of parameter values.

        Returns:
            True if parameters are valid, False otherwise.
        """
        total_boost = sum(params.values())
        if total_boost == 0:
            logger.warning("All boosts are 0, skipping trial")
            return False
        return True

    def _build_settings_overrides(self, params: dict[str, float]) -> dict[str, float]:
        """Build settings overrides with rounded values.

        Args:
            params: Dictionary of parameter values.

        Returns:
            Dictionary of settings overrides.
        """
        return {k: round(v, PRECISION) for k, v in params.items()}

    def _run_trial_evaluation(self, trial: optuna.Trial, settings_overrides: dict[str, float]) -> float:
        """Run evaluation and extract optimization score.

        Args:
            trial: Optuna trial object.
            settings_overrides: Dictionary of settings to override.

        Returns:
            Optimization score.
        """
        result = self.evaluation_runner(
            settings_overrides=settings_overrides,
            log_to_file=False,
        )

        if result is None:
            logger.warning("Evaluation returned None (no results)")
            return PENALTY_SCORE

        _, summary = result
        return self._extract_optimization_score(summary)

    def _extract_optimization_score(self, summary: Any) -> float:
        """Extract optimization score from summary object or dict.

        Args:
            summary: Evaluation summary (dict or object with optimization_score attribute).

        Returns:
            Optimization score as a float.
        """
        # Handle both EvaluationSummary dataclass and dict
        if hasattr(summary, "optimization_score"):
            score = summary.optimization_score
        else:
            score = summary.get("optimization_score", PENALTY_SCORE)

        # Handle numpy types
        if hasattr(score, "item"):
            score = score.item()

        return float(score)


def create_objective(step: float = 0.1) -> Callable[[optuna.Trial], float]:
    """Create an objective function with the specified step size.

    This is a factory function that creates an OptimizationObjective instance,
    passing run_evaluation explicitly as the evaluation runner.

    Args:
        step: Step size for parameter suggestions (0.1 for coarse, 0.05 for fine).

    Returns:
        Callable objective function for Optuna optimization.
    """
    return OptimizationObjective(step=step, evaluation_runner=run_evaluation)


def run_optimization(
    n_trials: int = 30,
    study_name: str | None = None,
    two_phase: bool = True,
) -> optuna.Study:
    """Run Bayesian optimization to find optimal search parameters.

    Args:
        n_trials: Total number of optimization trials to run.
        study_name: Optional name for the study (for persistence).
        two_phase: If True, use coarse step (0.1) for first half, fine step (0.05) for second.

    Returns:
        Optuna study object with results.
    """
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Generate study name if not provided
    if study_name is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        study_name = f"search_optimization_{timestamp}"

    logger.info(f"Starting optimization study: {study_name}")
    logger.info(f"Running {n_trials} trials...")

    # Create study with TPE sampler (Bayesian optimization)
    sampler = TPESampler(seed=42)  # Fixed seed for reproducibility
    study = optuna.create_study(
        study_name=study_name,
        direction="maximize",  # We want to maximize optimization_score
        sampler=sampler,
    )

    # Progress callback to show fraction instead of progress bar
    def progress_callback(study: optuna.Study, trial: FrozenTrial) -> None:
        """Log progress after each trial completion."""
        current = len(study.trials)
        logger.info(f"Progress: {current}/{n_trials} trials completed")

    if two_phase:
        # Phase 1: Coarse search (first half of trials)
        phase1_trials = n_trials // 2
        phase2_trials = n_trials - phase1_trials

        logger.info(f"Phase 1: Coarse search ({phase1_trials} trials, step=0.3)")
        study.optimize(
            create_objective(step=0.3),
            n_trials=phase1_trials,
            show_progress_bar=False,
            callbacks=[progress_callback],
        )

        logger.info(f"Phase 1 complete. Best score so far: {study.best_value:.4f}")
        logger.info(f"Phase 2: Fine-tuning ({phase2_trials} trials, step=0.05)")
        study.optimize(
            create_objective(step=0.05),
            n_trials=phase2_trials,
            show_progress_bar=False,
            callbacks=[progress_callback],
        )
    else:
        # Single phase with default step
        study.optimize(
            create_objective(step=0.1),
            n_trials=n_trials,
            show_progress_bar=False,
            callbacks=[progress_callback],
        )

    return study


def _round_params(params: dict[str, Any]) -> dict[str, Any]:
    """Round all numeric parameter values to 4 decimal places.

    Args:
        params: Dictionary of parameter names to values.

    Returns:
        Dictionary with float values rounded to 4 decimal places.
    """
    return {k: round(v, 4) if isinstance(v, float) else v for k, v in params.items()}


def _update_latest_symlink(run_dir: Path) -> None:
    """Update the 'latest' symlink to point to the most recent run.

    Args:
        run_dir: Path to the current run directory.
    """
    latest_link = OUTPUT_DIR / "latest"

    # Remove existing symlink if it exists
    if latest_link.is_symlink():
        latest_link.unlink()
    elif latest_link.exists():
        # If it's a regular file/dir (shouldn't happen), skip
        logger.warning(f"'latest' exists but is not a symlink: {latest_link}")
        return

    # Create relative symlink (works better across different machines)
    latest_link.symlink_to(run_dir.name)
    logger.info(f"Updated 'latest' symlink -> {run_dir.name}")


def save_results(study: optuna.Study) -> None:
    """Save optimization results to a dedicated run directory.

    Creates a directory structure:
        output/optimization/
            2025-12-31_11-49-13/
                summary.json      (best params + metadata)
                trial_history.json
            latest -> 2025-12-31_11-49-13/  (symlink to most recent)

    Args:
        study: Completed Optuna study.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Create run-specific directory
    run_dir = OUTPUT_DIR / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save summary (best params + metadata) as JSON
    summary_file = run_dir / "summary.json"
    summary = {
        "study_name": study.study_name,
        "timestamp": timestamp,
        "n_trials": len(study.trials),
        "best_trial_number": study.best_trial.number,
        "best_score": round(study.best_value, 4),
        "best_params": _round_params(study.best_params),
    }
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Summary saved to: {summary_file}")

    # Save trial history as JSON (rounded to 4 decimal places)
    history_file = run_dir / "trial_history.json"
    trial_history = []
    for trial in study.trials:
        trial_history.append(
            {
                "number": trial.number,
                "value": round(trial.value, 4) if trial.value else None,
                "params": _round_params(trial.params),
                "state": trial.state.name,
            }
        )
    with open(history_file, "w") as f:
        json.dump(trial_history, f, indent=2)
    logger.info(f"Trial history saved to: {history_file}")

    # Update 'latest' symlink
    _update_latest_symlink(run_dir)


def print_summary(study: optuna.Study) -> None:
    """Print a summary of the optimization results.

    Args:
        study: Completed Optuna study.
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("OPTIMIZATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Study: {study.study_name}")
    logger.info(f"Total trials: {len(study.trials)}")
    logger.info(f"Best trial: #{study.best_trial.number}")
    logger.info(f"Best optimization score: {study.best_value:.4f}")
    logger.info("Best parameters:")
    for param, value in study.best_params.items():
        logger.info(f"  {param}: {round(value, 4)}")
    logger.info("=" * 60)

    # Show top 5 trials
    logger.info("Top 5 trials:")
    sorted_trials = sorted(study.trials, key=lambda t: t.value if t.value else -1000, reverse=True)
    for i, trial in enumerate(sorted_trials[:5]):
        logger.info(f"  {i + 1}. Trial #{trial.number}: score={trial.value:.4f}")
        logger.info(f"     Params: {_round_params(trial.params)}")


def run_optimization_workflow(n_trials: int = 30, two_phase: bool = True) -> optuna.Study:
    """Run the complete optimization workflow.

    This is the main business logic function that orchestrates the optimization process.

    Args:
        n_trials: Total number of optimization trials to run.
        two_phase: If True, use coarse step (0.3) for first half, fine step (0.05) for second.

    Returns:
        Completed Optuna study with all trial results.
    """
    logger.info("=" * 60)
    logger.info("SEARCH PARAMETER OPTIMIZATION")
    logger.info("=" * 60)
    if two_phase:
        logger.info("Mode: Two-phase (coarse then fine-tuning)")
    else:
        logger.info("Mode: Single-phase (step=0.1)")

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


def main(n_trials: int = 30, two_phase: bool = True) -> optuna.Study:
    """Main entry point for optimization (legacy compatibility).

    This function exists for backward compatibility with existing code and tests.
    New code should use run_optimization_workflow() directly.

    Args:
        n_trials: Total number of optimization trials to run.
        two_phase: If True, use coarse step (0.3) for first half, fine step (0.05) for second.

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
        default=3,
        help="Total number of optimization trials to run (default: 30)",
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
