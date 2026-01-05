#!/usr/bin/env python
"""Bayesian optimization for search configuration parameters.

This script uses Optuna to find the optimal combination of search boosts
that maximizes the optimization score from the evaluation framework.

Usage (from local-dev-environment directory):
    source .venv/bin/activate
    python -m testing.optimize_search

Requirements:
    pip install optuna

The script will:
1. Phase 1: Coarse search with step=0.2 to explore the parameter space
2. Phase 2: Fine-tuning with step=0.05 around the best region found
3. Log all trials to the evaluation_log.csv (full audit trail)
4. Save the best parameters found to a JSON file
5. Print a summary of the optimization results
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import optuna
from optuna.samplers import TPESampler

from testing.run_evaluation import main as run_evaluation

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


def create_objective(step: float = 0.1) -> callable:
    """Create an objective function with the specified step size.

    Args:
        step: Step size for parameter suggestions (0.1 for coarse, 0.05 for fine).

    Returns:
        Objective function for Optuna optimization.
    """

    def objective(trial: optuna.Trial) -> float:
        """Objective function for Optuna optimization.

        Suggests parameter values, runs evaluation, and returns optimization score.
        SCORE_FILTER is held constant (uses default from evaluation_settings).

        Args:
            trial: Optuna trial object for suggesting parameters.

        Returns:
            Optimization score (higher is better).
        """
        # Suggest boost parameters (0.0 to 3.0 range)
        keyword_boost = trial.suggest_float("KEYWORD_BOOST", 0.0, 3.0, step=step)
        analyser_boost = trial.suggest_float("ANALYSER_BOOST", 0.0, 3.0, step=step)
        semantic_boost = trial.suggest_float("SEMANTIC_BOOST", 0.0, 3.0, step=step)
        fuzzy_boost = trial.suggest_float("FUZZY_BOOST", 0.0, 3.0, step=step)
        wildcard_boost = trial.suggest_float("WILDCARD_BOOST", 0.0, 3.0, step=step)

        # Ensure at least one search type is active
        total_boost = keyword_boost + analyser_boost + semantic_boost + fuzzy_boost + wildcard_boost
        if total_boost == 0:
            # If all boosts are 0, return a very low score
            logger.warning("All boosts are 0, skipping trial")
            return -1000.0

        # Build settings overrides (round to 4 decimal places to avoid floating point noise)
        # Note: SCORE_FILTER is not optimized - it uses the default from evaluation_settings
        settings_overrides = {
            "KEYWORD_BOOST": round(keyword_boost, 4),
            "ANALYSER_BOOST": round(analyser_boost, 4),
            "SEMANTIC_BOOST": round(semantic_boost, 4),
            "FUZZY_BOOST": round(fuzzy_boost, 4),
            "WILDCARD_BOOST": round(wildcard_boost, 4),
        }

        logger.info(f"Trial {trial.number}: {settings_overrides}")

        try:
            # Run evaluation with overrides
            # log_to_file=False skips per-run CSV, but evaluation_log.csv is always updated
            result = run_evaluation(settings_overrides=settings_overrides, log_to_file=False)

            if result is None:
                logger.warning("Evaluation returned None (no results)")
                return -1000.0

            _, summary = result
            # Handle both EvaluationSummary dataclass and dict
            if hasattr(summary, "optimization_score"):
                optimization_score = summary.optimization_score
            else:
                optimization_score = summary.get("optimization_score", -1000.0)

            # Handle numpy types
            if hasattr(optimization_score, "item"):
                optimization_score = optimization_score.item()

            logger.info(f"Trial {trial.number} score: {optimization_score:.4f}")
            return optimization_score

        except Exception as e:
            logger.error(f"Trial {trial.number} failed: {e}")
            return -1000.0

    return objective


def run_optimization(
    n_trials: int = 100,
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

    if two_phase:
        # Phase 1: Coarse search (first half of trials)
        phase1_trials = n_trials // 2
        phase2_trials = n_trials - phase1_trials

        logger.info(f"Phase 1: Coarse search ({phase1_trials} trials, step=0.2)")
        study.optimize(
            create_objective(step=0.2),
            n_trials=phase1_trials,
            show_progress_bar=True,
        )

        logger.info(f"Phase 1 complete. Best score so far: {study.best_value:.4f}")
        logger.info(f"Phase 2: Fine-tuning ({phase2_trials} trials, step=0.05)")
        study.optimize(
            create_objective(step=0.05),
            n_trials=phase2_trials,
            show_progress_bar=True,
        )
    else:
        # Single phase with default step
        study.optimize(
            create_objective(step=0.1),
            n_trials=n_trials,
            show_progress_bar=True,
        )

    return study


def _round_params(params: dict) -> dict:
    """Round all numeric parameter values to 4 decimal places."""
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


def main(n_trials: int = 100, two_phase: bool = True) -> None:
    """Main entry point for optimization.

    Args:
        n_trials: Total number of optimization trials to run.
        two_phase: If True, use coarse step (0.1) for first half, fine step (0.05) for second.
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
    logger.info("2. Update testing/evaluation_settings.py with the best values")
    logger.info("3. Run a full evaluation to confirm: python -m testing.run_evaluation")
    logger.info(f"4. Results saved in: {OUTPUT_DIR / 'latest'}")


if __name__ == "__main__":
    # Default to 100 trials, can be modified here
    main(n_trials=100)
