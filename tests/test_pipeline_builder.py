"""Tests for the pipeline_builder module."""

from unittest.mock import patch

import pytest

from ingestion_pipeline.pipeline_builder import build_pipeline

"""Tests for the pipeline_builder module."""


@pytest.fixture
def mock_textractor():
    """Mock Textractor instance."""
    with patch("ingestion_pipeline.pipeline_builder.Textractor") as mock:
        yield mock


@pytest.fixture
def mock_boto3_client():
    """Mock boto3 client."""
    with patch("ingestion_pipeline.pipeline_builder.boto3.client") as mock:
        yield mock


@pytest.fixture
def mock_settings():
    """Mock settings."""
    with patch("ingestion_pipeline.pipeline_builder.settings") as mock:
        mock.AWS_REGION = "us-east-1"
        mock.BEDROCK_EMBEDDING_MODEL_ID = "test-model-id"
        mock.OPENSEARCH_CHUNK_INDEX_NAME = "test-index"
        mock.OPENSEARCH_PROXY_URL = "http://test-proxy.com"
        yield mock


@pytest.fixture
def mock_components():
    """Mock all pipeline components."""
    with (
        patch("ingestion_pipeline.pipeline_builder.TextractProcessor") as mock_processor,
        patch("ingestion_pipeline.pipeline_builder.ChunkingConfig") as mock_config,
        patch("ingestion_pipeline.pipeline_builder.LayoutTextChunkingStrategy") as mock_text,
        patch("ingestion_pipeline.pipeline_builder.LayoutTableChunkingStrategy") as mock_table,
        patch("ingestion_pipeline.pipeline_builder.KeyValueChunker") as mock_kv,
        patch("ingestion_pipeline.pipeline_builder.LayoutListChunkingStrategy") as mock_list,
        patch("ingestion_pipeline.pipeline_builder.DocumentChunker") as mock_chunker,
        patch("ingestion_pipeline.pipeline_builder.EmbeddingGenerator") as mock_embedding,
        patch("ingestion_pipeline.pipeline_builder.OpenSearchIndexer") as mock_indexer,
        patch("ingestion_pipeline.pipeline_builder.Pipeline") as mock_pipeline,
    ):
        yield {
            "processor": mock_processor,
            "config": mock_config,
            "text": mock_text,
            "table": mock_table,
            "kv": mock_kv,
            "list": mock_list,
            "chunker": mock_chunker,
            "embedding": mock_embedding,
            "indexer": mock_indexer,
            "pipeline": mock_pipeline,
        }


def test_build_pipeline_creates_textractor_with_region(
    mock_textractor, mock_boto3_client, mock_settings, mock_components
):
    """Test that Textractor is instantiated with correct AWS region."""
    build_pipeline()

    mock_textractor.assert_called_once_with(region_name="us-east-1")


def test_build_pipeline_creates_boto3_textract_client(
    mock_textractor, mock_boto3_client, mock_settings, mock_components
):
    """Test that boto3 Textract client is created with correct region."""
    build_pipeline()

    mock_boto3_client.assert_called_once_with("textract", region_name="us-east-1")


def test_build_pipeline_creates_textract_processor(mock_textractor, mock_boto3_client, mock_settings, mock_components):
    """Test that TextractProcessor is created with correct dependencies."""
    build_pipeline()

    mock_components["processor"].assert_called_once_with(
        textractor=mock_textractor.return_value,
        textract_client=mock_boto3_client.return_value,
    )


def test_build_pipeline_creates_chunking_strategies(mock_textractor, mock_boto3_client, mock_settings, mock_components):
    """Test that all chunking strategies are instantiated."""
    build_pipeline()

    config_instance = mock_components["config"].return_value
    mock_components["text"].assert_called_once_with(config_instance)
    mock_components["table"].assert_called_once_with(config_instance)
    mock_components["kv"].assert_called_once_with(config_instance)
    mock_components["list"].assert_called_once_with(config_instance)


def test_build_pipeline_creates_document_chunker_with_strategies(
    mock_textractor, mock_boto3_client, mock_settings, mock_components
):
    """Test that DocumentChunker is created with all strategy handlers."""
    build_pipeline()

    call_args = mock_components["chunker"].call_args
    strategy_handlers = call_args.kwargs["strategy_handlers"]

    assert "LAYOUT_TEXT" in strategy_handlers
    assert "LAYOUT_HEADER" in strategy_handlers
    assert "LAYOUT_TITLE" in strategy_handlers
    assert "LAYOUT_TABLE" in strategy_handlers
    assert "LAYOUT_SECTION_HEADER" in strategy_handlers
    assert "LAYOUT_FOOTER" in strategy_handlers
    assert "LAYOUT_FIGURE" in strategy_handlers
    assert "LAYOUT_KEY_VALUE" in strategy_handlers
    assert "LAYOUT_LIST" in strategy_handlers


def test_build_pipeline_creates_embedding_generator(mock_textractor, mock_boto3_client, mock_settings, mock_components):
    """Test that EmbeddingGenerator is created with correct model ID."""
    build_pipeline()

    mock_components["embedding"].assert_called_once_with(model_id="test-model-id")


def test_build_pipeline_creates_opensearch_indexer(mock_textractor, mock_boto3_client, mock_settings, mock_components):
    """Test that OpenSearchIndexer is created with correct settings."""
    build_pipeline()

    mock_components["indexer"].assert_called_once_with(index_name="test-index", proxy_url="http://test-proxy.com")


def test_build_pipeline_returns_pipeline_instance(mock_textractor, mock_boto3_client, mock_settings, mock_components):
    """Test that build_pipeline returns a Pipeline instance."""
    result = build_pipeline()

    assert result == mock_components["pipeline"].return_value


def test_build_pipeline_creates_pipeline_with_all_components(
    mock_textractor, mock_boto3_client, mock_settings, mock_components
):
    """Test that Pipeline is instantiated with all required components."""
    build_pipeline()

    mock_components["pipeline"].assert_called_once_with(
        textract_processor=mock_components["processor"].return_value,
        chunker=mock_components["chunker"].return_value,
        embedding_generator=mock_components["embedding"].return_value,
        chunk_indexer=mock_components["indexer"].return_value,
    )
