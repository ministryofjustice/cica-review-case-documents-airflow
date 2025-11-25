from unittest import mock

import pytest
from opensearchpy import ConnectionError

from ingestion_pipeline.indexing import healthcheck


@pytest.fixture
def mock_opensearch():
    with mock.patch("ingestion_pipeline.indexing.healthcheck.OpenSearch") as opensearch_cls:
        yield opensearch_cls


@pytest.fixture
def mock_time():
    with mock.patch("ingestion_pipeline.indexing.healthcheck.time") as time_mod:
        yield time_mod


def test_healthcheck_green_status(mock_opensearch, mock_time):
    client = mock.Mock()
    client.cluster.health.return_value = {"status": "green"}
    mock_opensearch.return_value = client
    mock_time.time.side_effect = [0, 0.5]
    mock_time.sleep.return_value = None

    assert healthcheck.check_opensearch_health("http://localhost:9200", timeout=1) is True
    client.cluster.health.assert_called_once()


def test_healthcheck_yellow_status(mock_opensearch, mock_time):
    client = mock.Mock()
    client.cluster.health.return_value = {"status": "yellow"}
    mock_opensearch.return_value = client
    mock_time.time.side_effect = [0, 0.5]
    mock_time.sleep.return_value = None

    assert healthcheck.check_opensearch_health("http://localhost:9200", timeout=1) is True


def test_healthcheck_red_status_then_timeout(mock_opensearch, mock_time):
    client = mock.Mock()
    client.cluster.health.return_value = {"status": "red"}
    mock_opensearch.return_value = client
    # Simulate two attempts, both "red", then timeout
    mock_time.time.side_effect = [0, 0.5, 1, 2, 3]
    mock_time.sleep.return_value = None

    assert healthcheck.check_opensearch_health("http://localhost:9200", timeout=2) is False
    assert client.cluster.health.call_count == 2


def test_healthcheck_connection_error_then_success(mock_opensearch, mock_time):
    client = mock.Mock()
    # First call raises ConnectionError, second returns "green"
    client.cluster.health.side_effect = [ConnectionError(400, "fail", {}), {"status": "green"}]
    mock_opensearch.return_value = client
    mock_time.time.side_effect = [0, 0.5, 1, 2]
    mock_time.sleep.return_value = None

    assert healthcheck.check_opensearch_health("http://localhost:9200", timeout=2) is True
    assert client.cluster.health.call_count == 2


def test_healthcheck_unexpected_exception_then_timeout(mock_opensearch, mock_time):
    client = mock.Mock()
    client.cluster.health.side_effect = [Exception("unexpected"), Exception("unexpected")]
    mock_opensearch.return_value = client
    mock_time.time.side_effect = [0, 0.5, 1, 2]
    mock_time.sleep.return_value = None

    assert healthcheck.check_opensearch_health("http://localhost:9200", timeout=1) is False
    assert client.cluster.health.call_count == 1


def test_healthcheck_https_port_default(mock_opensearch, mock_time):
    client = mock.Mock()
    client.cluster.health.return_value = {"status": "green"}
    mock_opensearch.return_value = client
    mock_time.time.side_effect = [0, 0.5]
    mock_time.sleep.return_value = None

    healthcheck.check_opensearch_health("https://example.com")
    args, kwargs = mock_opensearch.call_args
    hosts = kwargs["hosts"]
    assert hosts[0]["port"] == 443
    assert hosts[0]["scheme"] == "https"
