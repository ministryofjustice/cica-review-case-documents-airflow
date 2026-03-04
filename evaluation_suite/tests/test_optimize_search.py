"""Unit tests for optimize_search orchestration and CLI.

Tests the run_optimization_workflow, main, and cli_main entry points.
"""

from unittest.mock import MagicMock

import pytest

import evaluation_suite.search_evaluation.optimize_search as optimize_search


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


def test_main_calls_check_opensearch_health(monkeypatch):
    """Test that main performs OpenSearch health check before optimization."""
    health_checked = {}

    def fake_check_opensearch_health():
        health_checked["called"] = True

    def fake_run_optimization(n_trials, two_phase):
        class DummyStudy:
            study_name = "study"
            trials = []
            best_trial = MagicMock(number=0)
            best_value = 1.0
            best_params = {"A": 1}

        return DummyStudy()

    monkeypatch.setattr(optimize_search, "check_opensearch_health", fake_check_opensearch_health)
    monkeypatch.setattr(optimize_search, "run_optimization", fake_run_optimization)
    monkeypatch.setattr(optimize_search, "save_results", lambda study: None)
    monkeypatch.setattr(optimize_search, "print_summary", lambda study: None)

    optimize_search.main(n_trials=1, two_phase=False)
    assert health_checked.get("called") is True


def test_main_exits_on_connection_error(monkeypatch):
    """Test that main exits if OpenSearch health check fails."""

    def fake_check_opensearch_health():
        raise ConnectionError("OpenSearch is down")

    monkeypatch.setattr(optimize_search, "check_opensearch_health", fake_check_opensearch_health)

    with pytest.raises(SystemExit):
        optimize_search.main(n_trials=1, two_phase=False)


def test_cli_main_default_args(monkeypatch):
    """Test cli_main with default arguments."""
    called = {}

    def fake_run_optimization_workflow(n_trials, two_phase):
        called["n_trials"] = n_trials
        called["two_phase"] = two_phase

    monkeypatch.setattr(optimize_search, "run_optimization_workflow", fake_run_optimization_workflow)
    monkeypatch.setattr("sys.argv", ["optimize_search.py"])

    optimize_search.cli_main()

    # Should use defaults: 30 trials, two_phase=True
    assert called["n_trials"] == 30
    assert called["two_phase"] is True


def test_cli_main_with_n_trials(monkeypatch):
    """Test cli_main with custom n_trials argument."""
    called = {}

    def fake_run_optimization_workflow(n_trials, two_phase):
        called["n_trials"] = n_trials
        called["two_phase"] = two_phase

    monkeypatch.setattr(optimize_search, "run_optimization_workflow", fake_run_optimization_workflow)
    monkeypatch.setattr("sys.argv", ["optimize_search.py", "--n-trials", "50"])

    optimize_search.cli_main()

    assert called["n_trials"] == 50
    assert called["two_phase"] is True


def test_cli_main_single_phase(monkeypatch):
    """Test cli_main with --single-phase flag."""
    called = {}

    def fake_run_optimization_workflow(n_trials, two_phase):
        called["n_trials"] = n_trials
        called["two_phase"] = two_phase

    monkeypatch.setattr(optimize_search, "run_optimization_workflow", fake_run_optimization_workflow)
    monkeypatch.setattr("sys.argv", ["optimize_search.py", "--single-phase"])

    optimize_search.cli_main()

    assert called["n_trials"] == 30  # Default
    assert called["two_phase"] is False


def test_cli_main_both_args(monkeypatch):
    """Test cli_main with both --n-trials and --single-phase."""
    called = {}

    def fake_run_optimization_workflow(n_trials, two_phase):
        called["n_trials"] = n_trials
        called["two_phase"] = two_phase

    monkeypatch.setattr(optimize_search, "run_optimization_workflow", fake_run_optimization_workflow)
    monkeypatch.setattr("sys.argv", ["optimize_search.py", "--n-trials", "75", "--single-phase"])

    optimize_search.cli_main()

    assert called["n_trials"] == 75
    assert called["two_phase"] is False
