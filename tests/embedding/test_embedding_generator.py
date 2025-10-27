from unittest import mock

import pytest

from ingestion_pipeline.embedding.embedding_generator import EmbeddingGenerator


@pytest.fixture
def mock_boto_client():
    with mock.patch("boto3.client") as mock_client:
        yield mock_client


@pytest.fixture
def mock_settings():
    with mock.patch("ingestion_pipeline.config.settings") as mock_settings:
        mock_settings.AWS_REGION = "us-west-2"
        mock_settings.BEDROCK_EMBEDDING_MODEL_ID = "test-model-id"
        yield mock_settings


def test_generate_embedding_returns_embedding_list(mock_boto_client, mock_settings):
    # Arrange
    mock_response = mock.MagicMock()
    embedding = [0.1, 0.2, 0.3]
    mock_response_body = mock.Mock()
    mock_response_body.read.return_value = '{"embedding": [0.1, 0.2, 0.3]}'
    mock_response.__getitem__.side_effect = lambda k: mock_response_body if k == "body" else None
    mock_boto_client.return_value.invoke_model.return_value = mock_response

    generator = EmbeddingGenerator(model_id="test-model-id")

    # Act
    result = generator.generate_embedding("test text")

    # Assert
    assert result == embedding
    mock_boto_client.return_value.invoke_model.assert_called_once()
    args, kwargs = mock_boto_client.return_value.invoke_model.call_args
    assert kwargs["modelId"] == "test-model-id"
    assert "body" in kwargs


def test_generate_embedding_handles_empty_text(mock_boto_client, mock_settings):
    mock_response = mock.MagicMock()
    mock_response_body = mock.Mock()
    mock_response_body.read.return_value = '{"embedding": []}'
    mock_response.__getitem__.side_effect = lambda k: mock_response_body if k == "body" else None
    mock_boto_client.return_value.invoke_model.return_value = mock_response

    generator = EmbeddingGenerator(model_id="test-model-id")
    result = generator.generate_embedding("")
    assert result == []


def test_init_sets_model_id_and_client(mock_settings):
    with mock.patch("boto3.client") as mock_client:
        generator = EmbeddingGenerator(model_id="abc")
        assert generator.model_id == "abc"
        assert generator.client == mock_client.return_value
