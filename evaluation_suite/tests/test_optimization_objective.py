"""Unit tests for optimization_objective module.

Tests the OptimizationObjective class and create_objective factory function.
"""

from unittest.mock import MagicMock, patch

import pytest

from evaluation_suite.search_evaluation.optimization_objective import (
    OptimizationObjective,
    create_objective,
)


@patch("evaluation_suite.search_evaluation.optimization_objective.run_evaluation")
def test_objective_returns_score(mock_run_evaluation):
    """Test that the objective function returns the optimization score."""
    mock_summary = {"optimization_score": 42.0}
    mock_run_evaluation.return_value = (None, mock_summary)
    objective = create_objective(step=0.1)
    trial = MagicMock()
    trial.suggest_float = lambda name, low, high, step: 1.0
    trial.number = 1
    score = objective(trial)
    assert score == 42.0


@patch("evaluation_suite.search_evaluation.optimization_objective.run_evaluation")
def test_objective_handles_none_result(mock_run_evaluation):
    """Test that the objective function returns -1000.0 if run_evaluation returns None."""
    mock_run_evaluation.return_value = None
    objective = create_objective(step=0.1)
    trial = MagicMock()
    trial.suggest_float = lambda name, low, high, step: 1.0
    trial.number = 2
    score = objective(trial)
    assert score == -1000.0


@patch("evaluation_suite.search_evaluation.optimization_objective.run_evaluation")
def test_objective_handles_exception(mock_run_evaluation):
    """Test that the objective function returns -1000.0 if an exception occurs."""
    mock_run_evaluation.side_effect = Exception("Test error")
    objective = create_objective(step=0.1)
    trial = MagicMock()
    trial.suggest_float = lambda name, low, high, step: 1.0
    trial.number = 3
    score = objective(trial)
    assert score == -1000.0


@patch("evaluation_suite.search_evaluation.optimization_objective.run_evaluation")
def test_objective_reraises_connection_error(mock_run_evaluation):
    """Test that ConnectionError propagates (stops optimization)."""
    mock_run_evaluation.side_effect = ConnectionError("OpenSearch is not reachable")
    objective = create_objective(step=0.1)
    trial = MagicMock()
    trial.suggest_float = lambda name, low, high, step: 1.0
    trial.number = 5

    with pytest.raises(ConnectionError, match="OpenSearch is not reachable"):
        objective(trial)


def test_objective_all_boosts_zero():
    """Test that the objective function returns -1000.0 if all boosts are zero."""
    objective = create_objective(step=0.1)
    trial = MagicMock()
    trial.suggest_float = lambda name, low, high, step: 0.0
    trial.number = 4
    score = objective(trial)
    assert score == -1000.0


def test_create_objective_returns_callable():
    """Test that create_objective returns a callable."""
    objective = create_objective(step=0.1)
    assert callable(objective)


def test_create_objective_with_different_steps():
    """Test that create_objective respects different step sizes."""
    objective_coarse = create_objective(step=0.3)
    objective_fine = create_objective(step=0.05)

    # Both should be OptimizationObjective instances
    assert isinstance(objective_coarse, OptimizationObjective)
    assert isinstance(objective_fine, OptimizationObjective)
    assert objective_coarse.step == 0.3
    assert objective_fine.step == 0.05


@patch("evaluation_suite.search_evaluation.optimization_objective.run_evaluation")
def test_objective_extracts_score_from_dataclass(mock_run_evaluation):
    """Test that the objective extracts optimization_score from EvaluationSummary dataclass."""
    # Create a mock summary object with optimization_score attribute
    mock_summary = MagicMock()
    mock_summary.optimization_score = 75.5
    mock_run_evaluation.return_value = (None, mock_summary)

    objective = create_objective(step=0.1)
    trial = MagicMock()
    trial.suggest_float = lambda name, low, high, step: 1.0
    trial.number = 1

    score = objective(trial)
    assert score == 75.5


@patch("evaluation_suite.search_evaluation.optimization_objective.run_evaluation")
def test_objective_rounds_parameters_to_precision(mock_run_evaluation):
    """Test that parameters are rounded to OPTIMIZATION_PRECISION (4 decimal places)."""
    mock_summary = {"optimization_score": 50.0}
    mock_run_evaluation.return_value = (None, mock_summary)

    objective = create_objective(step=0.1)
    trial = MagicMock()
    # Suggest floats that would need rounding
    trial.suggest_float = MagicMock(side_effect=[1.23456789, 2.13579246, 3.97531234, 4.11111111, 5.99999999])
    trial.number = 1

    # Call the objective - it should round the values
    objective(trial)

    # The values passed to run_evaluation should be rounded to 4 decimal places
    assert mock_run_evaluation.called
    call_kwargs = mock_run_evaluation.call_args[1]
    settings_overrides = call_kwargs["settings_overrides"]

    # Check that all values are rounded to 4 decimals
    for key, value in settings_overrides.items():
        assert isinstance(value, float)
        # Check it's rounded to at most 4 decimal places
        assert len(str(value).split(".")[-1]) <= 4 or "." not in str(value)
