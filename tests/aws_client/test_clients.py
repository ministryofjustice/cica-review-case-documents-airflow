import os
from unittest.mock import MagicMock

import pytest

from ingestion_pipeline.aws_client import clients


@pytest.fixture
def mock_settings(monkeypatch):
    class MockSettings:
        AWS_REGION = "eu-west-2"
        AWS_CICA_AWS_ACCESS_KEY_ID = "real-key"
        AWS_CICA_AWS_SECRET_ACCESS_KEY = "real-secret"
        AWS_CICA_AWS_SESSION_TOKEN = "mock-seesion-token"
        AWS_MOD_PLATFORM_ACCESS_KEY_ID = "mod-key"
        AWS_MOD_PLATFORM_SECRET_ACCESS_KEY = "mod-secret"
        AWS_MOD_PLATFORM_SESSION_TOKEN = "mod-token"
        LOCAL_DEVELOPMENT_MODE = False

    monkeypatch.setattr("ingestion_pipeline.aws_client.clients.settings", MockSettings())
    return MockSettings()


def test_get_s3_client_production(monkeypatch, mock_settings):
    mock_boto3 = MagicMock()
    monkeypatch.setattr(clients, "boto3", mock_boto3)

    clients.get_s3_client()
    mock_boto3.client.assert_called_once_with(
        "s3",
        aws_access_key_id="real-key",
        aws_secret_access_key="real-secret",
        aws_session_token="mock-seesion-token",
        region_name="eu-west-2",
    )


def test_get_s3_client_local(monkeypatch):
    class MockSettings:
        AWS_REGION = "eu-west-2"
        AWS_CICA_AWS_ACCESS_KEY_ID = "real-key"
        AWS_CICA_AWS_SECRET_ACCESS_KEY = "real-secret"
        AWS_MOD_PLATFORM_ACCESS_KEY_ID = "mod-key"
        AWS_MOD_PLATFORM_SECRET_ACCESS_KEY = "mod-secret"
        AWS_MOD_PLATFORM_SESSION_TOKEN = "mod-token"
        LOCAL_DEVELOPMENT_MODE = True  # Set before patching

    monkeypatch.setattr("ingestion_pipeline.aws_client.clients.settings", MockSettings())
    mock_boto3 = MagicMock()
    monkeypatch.setattr(clients, "boto3", mock_boto3)

    clients.get_s3_client()
    mock_boto3.client.assert_called_once_with(
        "s3",
        endpoint_url="http://localhost:4566",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="eu-west-2",
    )


def test_get_s3_client_local_string(monkeypatch):
    class MockSettings:
        AWS_REGION = "eu-west-2"
        AWS_CICA_AWS_ACCESS_KEY_ID = "real-key"
        AWS_CICA_AWS_SECRET_ACCESS_KEY = "real-secret"
        AWS_MOD_PLATFORM_ACCESS_KEY_ID = "mod-key"
        AWS_MOD_PLATFORM_SECRET_ACCESS_KEY = "mod-secret"
        AWS_MOD_PLATFORM_SESSION_TOKEN = "mod-token"
        LOCAL_DEVELOPMENT_MODE = "true"  # Set before patching

    monkeypatch.setattr("ingestion_pipeline.aws_client.clients.settings", MockSettings())
    mock_boto3 = MagicMock()
    monkeypatch.setattr(clients, "boto3", mock_boto3)

    clients.get_s3_client()
    mock_boto3.client.assert_called_once_with(
        "s3",
        endpoint_url="http://localhost:4566",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="eu-west-2",
    )


def test_get_textract_client(monkeypatch, mock_settings):
    mock_boto3 = MagicMock()
    monkeypatch.setattr(clients, "boto3", mock_boto3)

    clients.get_textract_client()
    mock_boto3.client.assert_called_once_with(
        "textract",
        aws_access_key_id="mod-key",
        aws_secret_access_key="mod-secret",
        aws_session_token="mod-token",
        region_name="eu-west-2",
    )


def test_get_textractor_instance(monkeypatch, mock_settings):
    mock_textractor = MagicMock()
    monkeypatch.setattr(clients, "Textractor", mock_textractor)

    # Save and clear env vars to test restoration
    orig_env = os.environ.copy()
    os.environ.pop("AWS_ACCESS_KEY_ID", None)
    os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
    os.environ.pop("AWS_SESSION_TOKEN", None)

    clients.get_textractor_instance()
    mock_textractor.assert_called_once_with(region_name="eu-west-2")

    # Ensure environment variables are restored
    assert os.environ.get("AWS_ACCESS_KEY_ID") is None
    assert os.environ.get("AWS_SECRET_ACCESS_KEY") is None
    assert os.environ.get("AWS_SESSION_TOKEN") is None

    # Restore original env
    os.environ.clear()
    os.environ.update(orig_env)


def test_get_textractor_instance_restores_existing_env_vars(monkeypatch, mock_settings):
    mock_textractor = MagicMock()
    monkeypatch.setattr(clients, "Textractor", mock_textractor)

    # Set a pre-existing environment variable
    os.environ["AWS_ACCESS_KEY_ID"] = "original_key"

    try:
        clients.get_textractor_instance()
        # Check that the environment variable was correctly restored
        assert os.environ["AWS_ACCESS_KEY_ID"] == "original_key"
    finally:
        # Clean up the environment variable after the test
        os.environ.pop("AWS_ACCESS_KEY_ID", None)
