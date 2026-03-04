"""Unit tests for optimize_search.py."""

from unittest.mock import MagicMock, patch

import pytest

import evaluation_suite.search_evaluation.optimize_search as optimize_search


@patch("evaluation_suite.search_evaluation.optimize_search.run_evaluation")
def test_objective_returns_score(mock_run_evaluation):
    """Test that the objective function returns the optimization score."""
    mock_summary = {"optimization_score": 42.0}
    mock_run_evaluation.return_value = (None, mock_summary)
    objective = optimize_search.create_objective(step=0.1)
    trial = MagicMock()
    trial.suggest_float = lambda name, low, high, step: 1.0
    trial.number = 1
    score = objective(trial)
    assert score == 42.0


@patch("evaluation_suite.search_evaluation.optimize_search.run_evaluation")
def test_objective_handles_none_result(mock_run_evaluation):
    """Test that the objective function returns -1000.0 if run_evaluation returns None."""
    mock_run_evaluation.return_value = None
    objective = optimize_search.create_objective(step=0.1)
    trial = MagicMock()
    trial.suggest_float = lambda name, low, high, step: 1.0
    trial.number = 2
    score = objective(trial)
    assert score == -1000.0


@patch("evaluation_suite.search_evaluation.optimize_search.run_evaluation")
def test_objective_handles_exception(mock_run_evaluation):
    """Test that the objective function returns -1000.0 if an exception occurs."""
    mock_run_evaluation.side_effect = Exception("Test error")
    objective = optimize_search.create_objective(step=0.1)
    trial = MagicMock()
    trial.suggest_float = lambda name, low, high, step: 1.0
    trial.number = 3
    score = objective(trial)
    assert score == -1000.0


@patch("evaluation_suite.search_evaluation.optimize_search.run_evaluation")
def test_objective_reraises_connection_error(mock_run_evaluation):
    """Test that ConnectionError from check_opensearch_health propagates (stops optimization)."""
    mock_run_evaluation.side_effect = ConnectionError("OpenSearch is not reachable")
    objective = optimize_search.create_objective(step=0.1)
    trial = MagicMock()
    trial.suggest_float = lambda name, low, high, step: 1.0
    trial.number = 5

    with pytest.raises(ConnectionError, match="OpenSearch is not reachable"):
        objective(trial)


def test_objective_all_boosts_zero():
    """Test that the objective function returns -1000.0 if all boosts are zero."""
    objective = optimize_search.create_objective(step=0.1)
    trial = MagicMock()
    trial.suggest_float = lambda name, low, high, step: 0.0
    trial.number = 4
    score = objective(trial)
    assert score == -1000.0


@patch("evaluation_suite.search_evaluation.optimize_search.optuna.create_study")
def test_run_optimization_creates_study(mock_create_study):
    """Test that run_optimization creates a study and runs optimization."""
    mock_study = MagicMock()
    mock_create_study.return_value = mock_study
    mock_study.trials = []
    mock_study.best_value = 10.0
    mock_study.best_params = {"KEYWORD_BOOST": 1.0}
    mock_study.best_trial = MagicMock(number=0)
    mock_study.study_name = "test_study"
    mock_study.optimize = MagicMock()
    study = optimize_search.run_optimization(n_trials=2, study_name="test_study", two_phase=False)
    assert study == mock_study
    mock_study.optimize.assert_called()


def test_run_optimization_two_phase_calls_both_phases(monkeypatch):
    """Test run_optimization runs both phases when two_phase=True."""
    called = []

    class DummyStudy:
        def __init__(self):
            self.trials = []
            self.best_value = 1.0
            self.best_params = {"KEYWORD_BOOST": 1.0}
            self.best_trial = MagicMock(number=0)
            self.study_name = "dummy"

        def optimize(self, *a, **kw):
            called.append(kw.get("n_trials"))

    monkeypatch.setattr(optimize_search, "TPESampler", lambda seed: None)
    monkeypatch.setattr(optimize_search.optuna, "create_study", lambda **kwargs: DummyStudy())
    optimize_search.run_optimization(n_trials=4, study_name="dummy", two_phase=True)
    assert called == [2, 2]


def test_run_optimization_single_phase(monkeypatch):
    """Test run_optimization runs single phase when two_phase=False."""
    called = []

    class DummyStudy:
        def __init__(self):
            self.trials = []
            self.best_value = 1.0
            self.best_params = {"KEYWORD_BOOST": 1.0}
            self.best_trial = MagicMock(number=0)
            self.study_name = "dummy"

        def optimize(self, *a, **kw):
            called.append(kw.get("n_trials"))

    monkeypatch.setattr(optimize_search, "TPESampler", lambda seed: None)
    monkeypatch.setattr(optimize_search.optuna, "create_study", lambda **kwargs: DummyStudy())
    optimize_search.run_optimization(n_trials=3, study_name="dummy", two_phase=False)
    assert called == [3]


def test_main_two_phase(monkeypatch):
    """Test main runs two-phase and logs steps."""
    called = {}

    def fake_run_optimization(n_trials, two_phase):
        called["n_trials"] = n_trials
        called["two_phase"] = two_phase

        class DummyStudy:
            study_name = "study"
            trials = []
            best_trial = MagicMock(number=0)
            best_value = 1.0
            best_params = {"A": 1}

        return DummyStudy()

    monkeypatch.setattr(optimize_search, "run_optimization", fake_run_optimization)
    monkeypatch.setattr(optimize_search, "save_results", lambda study: called.setdefault("saved", True))
    monkeypatch.setattr(optimize_search, "print_summary", lambda study: called.setdefault("printed", True))
    optimize_search.main(n_trials=5, two_phase=True)
    assert called["n_trials"] == 5
    assert called["two_phase"] is True
    assert called["saved"]
    assert called["printed"]


def test_main_single_phase(monkeypatch):
    """Test main runs single-phase and logs steps."""
    called = {}

    def fake_run_optimization(n_trials, two_phase):
        called["n_trials"] = n_trials
        called["two_phase"] = two_phase

        class DummyStudy:
            study_name = "study"
            trials = []
            best_trial = MagicMock(number=0)
            best_value = 1.0
            best_params = {"A": 1}

        return DummyStudy()

    monkeypatch.setattr(optimize_search, "run_optimization", fake_run_optimization)
    monkeypatch.setattr(optimize_search, "save_results", lambda study: called.setdefault("saved", True))
    monkeypatch.setattr(optimize_search, "print_summary", lambda study: called.setdefault("printed", True))
    optimize_search.main(n_trials=2, two_phase=False)
    assert called["n_trials"] == 2
    assert called["two_phase"] is False
    assert called["saved"]
    assert called["printed"]
