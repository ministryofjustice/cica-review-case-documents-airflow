"""Optimization engine for Bayesian parameter search.

This module handles the low-level Optuna study management and trial execution,
including two-phase optimization strategy.
"""

import logging
from datetime import datetime

import optuna
from optuna.samplers import TPESampler
from optuna.trial import FrozenTrial

from evaluation_suite.search_evaluation import evaluation_settings as eval_settings
from evaluation_suite.search_evaluation.optimization_objective import create_objective
from evaluation_suite.search_evaluation.optimization_results import OUTPUT_DIR

logger = logging.getLogger("optimization_engine")


def run_optimization(
    n_trials: int | None = None,
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

    # Use default n_trials if not specified
    if n_trials is None:
        n_trials = eval_settings.OPTIMIZATION_DEFAULT_N_TRIALS

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

        logger.info(f"Phase 1: Coarse search ({phase1_trials} trials, step={eval_settings.OPTIMIZATION_PHASE1_STEP})")
        try:
            study.optimize(
                create_objective(step=eval_settings.OPTIMIZATION_PHASE1_STEP),
                n_trials=phase1_trials,
                show_progress_bar=False,
                callbacks=[progress_callback],
            )
        except ConnectionError:
            raise SystemExit(1)

        logger.info(f"Phase 1 complete. Best score so far: {study.best_value:.4f}")
        logger.info(f"Phase 2: Fine-tuning ({phase2_trials} trials, step={eval_settings.OPTIMIZATION_PHASE2_STEP})")
        try:
            study.optimize(
                create_objective(step=eval_settings.OPTIMIZATION_PHASE2_STEP),
                n_trials=phase2_trials,
                show_progress_bar=False,
                callbacks=[progress_callback],
            )
        except ConnectionError:
            raise SystemExit(1)
    else:
        # Single phase with default step
        try:
            study.optimize(
                create_objective(step=eval_settings.OPTIMIZATION_SINGLE_PHASE_STEP),
                n_trials=n_trials,
                show_progress_bar=False,
                callbacks=[progress_callback],
            )
        except ConnectionError:
            raise SystemExit(1)

    return study
