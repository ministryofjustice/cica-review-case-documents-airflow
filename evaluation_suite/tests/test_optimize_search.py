"""Unit tests for optimize_search.py."""

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


def test_update_latest_symlink(tmp_path):
    """Test that _update_latest_symlink creates a symlink to the latest run directory."""
    output_dir = tmp_path / "optimization"
    output_dir.mkdir()
    run_dir = output_dir / "2026-02-27_12-00-00"
    run_dir.mkdir()
    with patch.object(optimize_search, "OUTPUT_DIR", output_dir):
        optimize_search._update_latest_symlink(run_dir)
        latest_link = output_dir / "latest"
        assert latest_link.is_symlink()
        assert latest_link.resolve() == run_dir.resolve()


def test_save_results_creates_files(tmp_path):
    """Test that save_results creates summary and trial history files."""
    output_dir = tmp_path / "optimization"
    output_dir.mkdir()
    with patch.object(optimize_search, "OUTPUT_DIR", output_dir):
        mock_study = MagicMock()
        mock_study.study_name = "test_study"
        # Create a trial mock with state.name as a string, not a MagicMock
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
        run_dirs = list(output_dir.iterdir())
        assert any(d.is_dir() for d in run_dirs)
        run_dir = [d for d in run_dirs if d.is_dir()][0]
        summary_file = run_dir / "summary.json"
        history_file = run_dir / "trial_history.json"
        assert summary_file.exists()
        assert history_file.exists()
