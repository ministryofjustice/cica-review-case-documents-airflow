"""Unit tests for optimization_engine module.

Tests the run_optimization function and two-phase optimization strategy.
"""

from unittest.mock import MagicMock, patch

from evaluation_suite.search_evaluation.optimization_engine import run_optimization


@patch("evaluation_suite.search_evaluation.optimization_engine.optuna.create_study")
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

    study = run_optimization(n_trials=2, study_name="test_study", two_phase=False)
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

    monkeypatch.setattr("evaluation_suite.search_evaluation.optimization_engine.TPESampler", lambda seed: None)
    monkeypatch.setattr(
        "evaluation_suite.search_evaluation.optimization_engine.optuna.create_study", lambda **kwargs: DummyStudy()
    )
    run_optimization(n_trials=4, study_name="dummy", two_phase=True)
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

    monkeypatch.setattr("evaluation_suite.search_evaluation.optimization_engine.TPESampler", lambda seed: None)
    monkeypatch.setattr(
        "evaluation_suite.search_evaluation.optimization_engine.optuna.create_study", lambda **kwargs: DummyStudy()
    )
    run_optimization(n_trials=3, study_name="dummy", two_phase=False)
    assert called == [3]


def test_run_optimization_uses_default_n_trials(monkeypatch):
    """Test that run_optimization uses OPTIMIZATION_DEFAULT_N_TRIALS when n_trials is None."""
    called = []

    class DummyStudy:
        def __init__(self):
            self.trials = []
            self.best_value = 1.0
            self.best_params = {"KEYWORD_BOOST": 1.0}
            self.best_trial = MagicMock(number=0)
            self.study_name = "dummy"

        def optimize(self, *a, **kw):
            n_trials = kw.get("n_trials")
            called.append(n_trials)

    monkeypatch.setattr("evaluation_suite.search_evaluation.optimization_engine.TPESampler", lambda seed: None)
    monkeypatch.setattr(
        "evaluation_suite.search_evaluation.optimization_engine.optuna.create_study", lambda **kwargs: DummyStudy()
    )

    # Run with n_trials=None (should use default)
    run_optimization(n_trials=None, study_name="dummy", two_phase=False)

    # Should have called optimize with the default value (30 from settings)
    assert len(called) == 1
    assert called[0] == 30  # Default from OPTIMIZATION_DEFAULT_N_TRIALS


def test_run_optimization_two_phase_splits_trials():
    """Test that two-phase optimization splits trials correctly."""
    # With 10 trials total: 5 in phase 1, 5 in phase 2
    # With 9 trials total: 4 in phase 1, 5 in phase 2
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

    import sys

    old_modules = sys.modules.copy()

    try:
        # Mock the modules
        import evaluation_suite.search_evaluation.optimization_engine as engine

        engine.TPESampler = lambda seed: None
        engine.optuna.create_study = lambda **kwargs: DummyStudy()

        # Test 10 trials
        called.clear()
        run_optimization(n_trials=10, study_name="dummy", two_phase=True)
        assert called == [5, 5]

        # Test 9 trials
        called.clear()
        run_optimization(n_trials=9, study_name="dummy", two_phase=True)
        assert called == [4, 5]
    finally:
        sys.modules.update(old_modules)


def test_run_optimization_generates_study_name_if_not_provided(monkeypatch):
    """Test that run_optimization generates a study name if not provided."""
    created_studies = []

    class DummyStudy:
        def __init__(self, study_name=None, **kwargs):
            self.study_name = study_name
            self.trials = []
            self.best_value = 1.0
            self.best_params = {}
            self.best_trial = MagicMock(number=0)
            created_studies.append(self)

        def optimize(self, *a, **kw):
            pass

    def mock_create_study(**kwargs):
        return DummyStudy(**kwargs)

    monkeypatch.setattr("evaluation_suite.search_evaluation.optimization_engine.TPESampler", lambda seed: None)
    monkeypatch.setattr("evaluation_suite.search_evaluation.optimization_engine.optuna.create_study", mock_create_study)

    # Run without specifying study_name
    run_optimization(n_trials=1, study_name=None, two_phase=False)

    # The study name should have been auto-generated
    assert len(created_studies) == 1
    assert "search_optimization_" in created_studies[0].study_name


@patch("evaluation_suite.search_evaluation.optimization_engine.optuna.create_study")
def test_run_optimization_connection_error_exits(mock_create_study):
    """Test that ConnectionError during optimization causes SystemExit."""
    mock_study = MagicMock()
    mock_create_study.return_value = mock_study
    mock_study.trials = []
    mock_study.best_value = 1.0
    mock_study.best_params = {}
    mock_study.best_trial = MagicMock(number=0)
    mock_study.study_name = "test"

    # Make optimize raise ConnectionError
    mock_study.optimize = MagicMock(side_effect=ConnectionError("OpenSearch down"))

    # run_optimization should catch this and raise SystemExit
    import pytest

    with pytest.raises(SystemExit):
        run_optimization(n_trials=2, study_name="test", two_phase=False)
