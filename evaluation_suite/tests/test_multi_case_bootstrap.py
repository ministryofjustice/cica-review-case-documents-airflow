"""Unit tests for multi_case_bootstrap.py."""

import subprocess
from unittest.mock import patch

from evaluation_suite.search_evaluation.multi_case import multi_case_bootstrap
from evaluation_suite.search_evaluation.multi_case.case_discovery import CaseSpec

_CASE_A = CaseSpec(case_ref="26-700001", s3_filename="Case1_TC19_50_pages_brain_injury.pdf")
_CASE_B = CaseSpec(case_ref="26-700002", s3_filename="Case2_TC19_30_pages_whiplash.pdf")

_MOD = "evaluation_suite.search_evaluation.multi_case.multi_case_bootstrap"


# ---------------------------------------------------------------------------
# bootstrap_all_cases
# ---------------------------------------------------------------------------


@patch(f"{_MOD}._ingest_case_subprocess")
@patch(f"{_MOD}.count_indexed_chunks_for_case")
@patch(f"{_MOD}.ensure_chunk_index")
@patch(f"{_MOD}.get_opensearch_client")
@patch(f"{_MOD}.check_opensearch_health")
def test_bootstrap_all_cases_skips_already_indexed(mock_health, mock_get_client, mock_ensure, mock_count, mock_ingest):
    """All cases already indexed → no subprocess runs, existing counts returned."""
    mock_count.side_effect = [10, 20]

    result = multi_case_bootstrap.bootstrap_all_cases([_CASE_A, _CASE_B])

    mock_ingest.assert_not_called()
    assert result == {"26-700001": 10, "26-700002": 20}


@patch(f"{_MOD}._ingest_case_subprocess")
@patch(f"{_MOD}.count_indexed_chunks_for_case")
@patch(f"{_MOD}.ensure_chunk_index")
@patch(f"{_MOD}.get_opensearch_client")
@patch(f"{_MOD}.check_opensearch_health")
def test_bootstrap_all_cases_ingests_empty_case(mock_health, mock_get_client, mock_ensure, mock_count, mock_ingest):
    """Case with no chunks triggers ingestion subprocess; result is post-ingest count."""
    # pre-ingest count = 0; post-ingest count = 42
    mock_count.side_effect = [0, 42]

    result = multi_case_bootstrap.bootstrap_all_cases([_CASE_A])

    mock_ingest.assert_called_once_with(_CASE_A)
    mock_get_client.return_value.indices.refresh.assert_called_once()
    assert result == {"26-700001": 42}


@patch(f"{_MOD}._ingest_case_subprocess")
@patch(f"{_MOD}.count_indexed_chunks_for_case")
@patch(f"{_MOD}.ensure_chunk_index")
@patch(f"{_MOD}.get_opensearch_client")
@patch(f"{_MOD}.check_opensearch_health")
def test_bootstrap_all_cases_mixed(mock_health, mock_get_client, mock_ensure, mock_count, mock_ingest):
    """One case indexed, one not — only the empty case triggers ingestion."""
    # CASE_A: 15 chunks (skip). CASE_B: 0 pre-ingest, 30 post-ingest.
    mock_count.side_effect = [15, 0, 30]

    result = multi_case_bootstrap.bootstrap_all_cases([_CASE_A, _CASE_B])

    mock_ingest.assert_called_once_with(_CASE_B)
    assert result == {"26-700001": 15, "26-700002": 30}


@patch(f"{_MOD}._ingest_case_subprocess")
@patch(f"{_MOD}.count_indexed_chunks_for_case")
@patch(f"{_MOD}.ensure_chunk_index")
@patch(f"{_MOD}.get_opensearch_client")
@patch(f"{_MOD}.check_opensearch_health")
def test_bootstrap_all_cases_empty_list(mock_health, mock_get_client, mock_ensure, mock_count, mock_ingest):
    """Empty case list returns empty dict; health-check and index-setup still run."""
    result = multi_case_bootstrap.bootstrap_all_cases([])

    mock_health.assert_called_once()
    mock_ensure.assert_called_once()
    mock_count.assert_not_called()
    assert result == {}


# ---------------------------------------------------------------------------
# _ingest_case_subprocess
# ---------------------------------------------------------------------------


@patch(f"{_MOD}.subprocess.run")
def test_ingest_case_subprocess_command_and_env(mock_run):
    """_ingest_case_subprocess passes the correct command and case env vars."""
    multi_case_bootstrap._ingest_case_subprocess(_CASE_A)

    mock_run.assert_called_once()
    (cmd,), kwargs = mock_run.call_args
    assert cmd[1] == "-m"
    assert cmd[2] == "evaluation_suite.search_evaluation.multi_case.ingestion_runner"
    assert kwargs["check"] is True
    env = kwargs["env"]
    assert env["AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX"] == _CASE_A.case_ref
    assert env["AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME"] == _CASE_A.s3_filename


@patch(f"{_MOD}.subprocess.run")
def test_ingest_case_subprocess_inherits_env(mock_run, monkeypatch):
    """Subprocess env is a superset of os.environ — existing vars are preserved."""
    monkeypatch.setenv("SOME_EXISTING_VAR", "sentinel")

    multi_case_bootstrap._ingest_case_subprocess(_CASE_A)

    (_,), kwargs = mock_run.call_args
    assert kwargs["env"]["SOME_EXISTING_VAR"] == "sentinel"


@patch(f"{_MOD}.subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd"))
def test_ingest_case_subprocess_propagates_failure(mock_run):
    """CalledProcessError from subprocess.run propagates to the caller."""
    import pytest

    with pytest.raises(subprocess.CalledProcessError):
        multi_case_bootstrap._ingest_case_subprocess(_CASE_A)
