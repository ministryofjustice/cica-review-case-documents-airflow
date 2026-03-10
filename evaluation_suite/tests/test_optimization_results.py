"""Unit tests for optimization_results.py."""

import json
import logging
from unittest.mock import MagicMock, patch

import evaluation_suite.search_evaluation.optimization_results as optimization_results


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
    rounded = optimization_results._round_params(params)
    assert rounded["KEYWORD_BOOST"] == 1.1235
    assert rounded["ANALYSER_BOOST"] == 2.9877
    assert rounded["SEMANTIC_BOOST"] == 3.0
    assert rounded["FUZZY_BOOST"] == 0.3333
    assert rounded["WILDCARD_BOOST"] == 0
    assert rounded["NON_FLOAT"] == "test"


def test_update_latest_symlink_existing_file(tmp_path):
    """Test _update_latest_symlink skips if 'latest' exists as a file."""
    output_dir = tmp_path / "optimization"
    output_dir.mkdir()
    run_dir = output_dir / "2026-02-27_12-00-00"
    run_dir.mkdir()
    latest = output_dir / "latest"
    latest.write_text("not a symlink")
    with patch.object(optimization_results, "OUTPUT_DIR", output_dir):
        optimization_results._update_latest_symlink(run_dir)
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
    new_run_dir = output_dir / "2026-02-27_13-00-00"
    new_run_dir.mkdir()
    with patch.object(optimization_results, "OUTPUT_DIR", output_dir):
        optimization_results._update_latest_symlink(new_run_dir)
        assert latest.is_symlink()
        assert latest.resolve() == new_run_dir.resolve()


def test_save_results_creates_files_and_calls_symlink(monkeypatch, tmp_path):
    """Test save_results creates JSON files and calls _update_latest_symlink."""
    output_dir = tmp_path / "optimization"
    output_dir.mkdir()
    called = {}

    def fake_update_latest_symlink(run_dir):
        called["called"] = run_dir

    monkeypatch.setattr(optimization_results, "_update_latest_symlink", fake_update_latest_symlink)
    with patch.object(optimization_results, "OUTPUT_DIR", output_dir):
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

        optimization_results.save_results(mock_study)

        assert "called" in called
        run_dir = called["called"]
        summary_file = run_dir / "summary.json"
        history_file = run_dir / "trial_history.json"
        assert summary_file.exists()
        assert history_file.exists()
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
        optimization_results.print_summary(DummyStudy())  # type: ignore
    assert "Top 5 trials" in caplog.text
    assert "Trial #5" in caplog.text
    assert "score=25.0000" in caplog.text
