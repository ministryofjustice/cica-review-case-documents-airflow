"""Optimization results persistence and reporting.

This module handles saving Optuna study results to disk and printing
human-readable summaries. Kept separate from the core optimization
loop so I/O concerns don't mix with search logic.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import optuna

logger = logging.getLogger("optimization_results")

# Output directory for optimization results
_SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = _SCRIPT_DIR / "output" / "optimization"


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
