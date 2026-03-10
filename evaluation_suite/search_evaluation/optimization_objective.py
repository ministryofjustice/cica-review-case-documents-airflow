"""Optimization objective function for Bayesian search parameter tuning.

This module defines the trial logic for Optuna optimization. Each trial
suggests parameter values, validates them, runs an evaluation, and returns
a score to maximize.
"""

import logging
from typing import Any, Callable

import optuna

from evaluation_suite.search_evaluation import evaluation_settings as eval_settings
from evaluation_suite.search_evaluation.run_evaluation import run_evaluation

logger = logging.getLogger("optimization_objective")

# Use optimization settings from evaluation_settings
PENALTY_SCORE = eval_settings.OPTIMIZATION_PENALTY_SCORE
BOOST_RANGE = (eval_settings.OPTIMIZATION_BOOST_RANGE_MIN, eval_settings.OPTIMIZATION_BOOST_RANGE_MAX)
PRECISION = eval_settings.OPTIMIZATION_PRECISION


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
        except ConnectionError:
            raise
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
