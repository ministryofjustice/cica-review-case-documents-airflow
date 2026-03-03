"""Unit tests for optimize_search.py."""

import json
import logging
from unittest.mock import MagicMock, patch

import evaluation_suite.search_evaluation.optimize_search as optimize_search


def test_round_params_rounds_floats():
    """Test that _round_params rounds floats to 4 decimal places."""
    params = {
        "KEYWORD_BOOST": 1.123456,
        "ANALYSER_BOOST": 2.987654,
        "SEMANTIC_BOOST": 3.0,
        "FUZZY_BOOST": 0.333333,
        "WILDCARD_BOOST": 0,
        "NON_FLOAT": "test",
    }
    rounded = optimize_search._round_params(params)
    assert rounded["KEYWORD_BOOST"] == 1.1235
    assert rounded["ANALYSER_BOOST"] == 2.9877
    assert rounded["SEMANTIC_BOOST"] == 3.0
    assert rounded["FUZZY_BOOST"] == 0.3333
    assert rounded["WILDCARD_BOOST"] == 0
    assert rounded["NON_FLOAT"] == "test"


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


def test_update_latest_symlink_existing_file(tmp_path):
    """Test _update_latest_symlink skips if 'latest' exists as a file."""
    output_dir = tmp_path / "optimization"
    output_dir.mkdir()
    run_dir = output_dir / "2026-02-27_12-00-00"
    run_dir.mkdir()
    latest = output_dir / "latest"
    latest.write_text("not a symlink")
    with patch.object(optimize_search, "OUTPUT_DIR", output_dir):
        optimize_search._update_latest_symlink(run_dir)
        # Should not overwrite the file
        assert latest.exists()
        assert not latest.is_symlink()


def test_update_latest_symlink_overwrites_symlink(tmp_path):
    """Test _update_latest_symlink replaces existing symlink."""
    output_dir = tmp_path / "optimization"
    output_dir.mkdir()
    run_dir = output_dir / "2026-02-27_12-00-00"
    run_dir.mkdir()
    latest = output_dir / "latest"
    latest.symlink_to(run_dir.name)
    # Now update to a new run_dir
    new_run_dir = output_dir / "2026-02-27_13-00-00"
    new_run_dir.mkdir()
    with patch.object(optimize_search, "OUTPUT_DIR", output_dir):
        optimize_search._update_latest_symlink(new_run_dir)
        assert latest.is_symlink()
        assert latest.resolve() == new_run_dir.resolve()


def test_save_results_creates_and_logs(monkeypatch, tmp_path):
    """Test save_results creates files and calls _update_latest_symlink."""
    output_dir = tmp_path / "optimization"
    output_dir.mkdir()
    called = {}

    def fake_update_latest_symlink(run_dir):
        called["called"] = run_dir

    monkeypatch.setattr(optimize_search, "_update_latest_symlink", fake_update_latest_symlink)
    with patch.object(optimize_search, "OUTPUT_DIR", output_dir):
        mock_study = MagicMock()
        mock_study.study_name = "test_study"
        trial_mock = MagicMock()
        trial_mock.number = 0
        trial_mock.value = 1.23456
        trial_mock.params = {"KEYWORD_BOOST": 1.23456}
        trial_mock.state = MagicMock()
        trial_mock.state.name = "COMPLETE"
        mock_study.trials = [trial_mock]
        mock_study.best_value = 1.23456
        mock_study.best_params = {"KEYWORD_BOOST": 1.23456}
        mock_study.best_trial = MagicMock(number=0)
        optimize_search.save_results(mock_study)
        # Should call _update_latest_symlink
        assert "called" in called
        run_dir = called["called"]
        summary_file = run_dir / "summary.json"
        history_file = run_dir / "trial_history.json"
        assert summary_file.exists()
        assert history_file.exists()
        # Check JSON content
        with open(summary_file) as f:
            data = json.load(f)
            assert data["best_score"] == 1.2346
        with open(history_file) as f:
            data = json.load(f)
            assert data[0]["value"] == 1.2346


def test_print_summary_logs_top_trials(caplog):
    """Test print_summary logs best trial and top 5 trials."""

    class DummyTrial:
        def __init__(self, number, value, params):
            self.number = number
            self.value = value
            self.params = params

    class DummyStudy:
        study_name = "study"
        trials = [
            DummyTrial(1, 10.0, {"A": 1}),
            DummyTrial(2, 20.0, {"A": 2}),
            DummyTrial(3, 15.0, {"A": 3}),
            DummyTrial(4, 5.0, {"A": 4}),
            DummyTrial(5, 25.0, {"A": 5}),
            DummyTrial(6, 2.0, {"A": 6}),
        ]
        best_trial = DummyTrial(5, 25.0, {"A": 5})
        best_value = 25.0
        best_params = {"A": 5}

    with caplog.at_level(logging.INFO):
        optimize_search.print_summary(DummyStudy())  # type: ignore
    assert "Top 5 trials" in caplog.text
    assert "Trial #5" in caplog.text
    assert "score=25.0000" in caplog.text


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
