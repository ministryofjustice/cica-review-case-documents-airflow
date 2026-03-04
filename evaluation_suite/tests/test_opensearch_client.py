"""Unit tests for opensearch_client.py."""

from unittest.mock import MagicMock, patch

import pytest

from evaluation_suite.search_evaluation import opensearch_client


@patch("evaluation_suite.search_evaluation.opensearch_client.evaluation_settings")
@patch("evaluation_suite.search_evaluation.opensearch_client.OpenSearch")
@patch("evaluation_suite.search_evaluation.opensearch_client.settings")
def test_get_opensearch_client_returns_client(mock_settings, mock_OpenSearch, mock_eval_settings):
    """Test that get_opensearch_client returns an OpenSearch client with retry configuration."""
    mock_settings.OPENSEARCH_PROXY_URL = "http://localhost:9200"
    mock_eval_settings.OPENSEARCH_TIMEOUT = 30
    mock_eval_settings.OPENSEARCH_MAX_RETRIES = 3
    client = MagicMock()
    mock_OpenSearch.return_value = client

    result = opensearch_client.get_opensearch_client()
    mock_OpenSearch.assert_called_once_with(
        hosts=[mock_settings.OPENSEARCH_PROXY_URL],
        http_auth=(opensearch_client.USER, opensearch_client.PASSWORD),
        use_ssl=False,
        verify_certs=False,
        ssl_assert_hostname=False,
        timeout=30,
        retry_on_timeout=True,
        max_retries=3,
    )
    assert result == client


@patch("evaluation_suite.search_evaluation.opensearch_client.get_opensearch_client")
def test_check_opensearch_health_success(mock_get_client):
    """Test that check_opensearch_health successfully checks health when OpenSearch is reachable."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.cluster.health.return_value = {"status": "green"}

    # Should not raise
    opensearch_client.check_opensearch_health()
    mock_client.cluster.health.assert_called_once()


@patch("evaluation_suite.search_evaluation.opensearch_client.get_opensearch_client")
def test_check_opensearch_health_connection_error(mock_get_client):
    """Test that check_opensearch_health raises ConnectionError with a clear message when OpenSearch is unreachable."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    # Pass two arguments to OpenSearchConnectionError to avoid IndexError
    mock_client.cluster.health.side_effect = opensearch_client.OpenSearchConnectionError("fail", {}, {})

    with pytest.raises(ConnectionError) as exc:
        opensearch_client.check_opensearch_health()
    assert "OpenSearch is not reachable" in str(exc.value)


def test_chunk_index_name_and_user_password():
    """Test that CHUNK_INDEX_NAME, USER, and PASSWORD are defined and are strings."""
    assert isinstance(opensearch_client.CHUNK_INDEX_NAME, str)
    assert isinstance(opensearch_client.USER, str)
    assert isinstance(opensearch_client.PASSWORD, str)
