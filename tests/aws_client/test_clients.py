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
        config=clients.S3_RETRY_CONFIG,
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
        config=clients.S3_RETRY_CONFIG,
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
        config=clients.S3_RETRY_CONFIG,
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
        config=clients.AWS_RETRY_CONFIG,
    )


def test_get_textractor_instance_uses_explicit_session_credentials(monkeypatch, mock_settings):
    mock_textractor_cls = MagicMock()
    mock_boto3 = MagicMock()
    monkeypatch.setattr(clients, "Textractor", mock_textractor_cls)
    monkeypatch.setattr(clients, "boto3", mock_boto3)

    result = clients.get_textractor_instance()

    # A session is built with the MOD-platform credentials, not the ambient environment.
    mock_boto3.Session.assert_called_once_with(
        aws_access_key_id="mod-key",
        aws_secret_access_key="mod-secret",
        aws_session_token="mod-token",
        region_name="eu-west-2",
    )
    # Textractor is still constructed for the correct region.
    mock_textractor_cls.assert_called_once_with(region_name="eu-west-2")

    # The returned instance has its session and clients replaced by the credentialed ones.
    session = mock_boto3.Session.return_value
    assert result.session is session
    assert result.textract_client is session.client.return_value
    assert result.s3_client is session.client.return_value
    session.client.assert_any_call("textract", region_name="eu-west-2", config=clients.AWS_RETRY_CONFIG)
    session.client.assert_any_call("s3", region_name="eu-west-2", config=clients.AWS_RETRY_CONFIG)


def test_get_textractor_instance_does_not_mutate_environment(monkeypatch, mock_settings):
    mock_textractor_cls = MagicMock()
    mock_boto3 = MagicMock()
    monkeypatch.setattr(clients, "Textractor", mock_textractor_cls)
    monkeypatch.setattr(clients, "boto3", mock_boto3)

    before = os.environ.copy()
    clients.get_textractor_instance()
    # No AWS credential env vars are set or left behind by the factory.
    assert os.environ == before
