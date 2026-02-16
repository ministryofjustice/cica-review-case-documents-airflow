"""Tests for the pipeline_builder module."""

from unittest.mock import patch

import pytest

from ingestion_pipeline.pipeline_builder import build_pipeline


@pytest.fixture(autouse=True)
def patch_external_dependencies():
    with (
        patch("ingestion_pipeline.pipeline_builder.get_s3_client") as mock_get_s3_client,
        patch("ingestion_pipeline.pipeline_builder.get_textract_client") as mock_get_textract_client,
        patch("ingestion_pipeline.pipeline_builder.get_textractor_instance") as mock_get_textractor_instance,
        patch("ingestion_pipeline.pipeline_builder.settings") as mock_settings,
        patch("ingestion_pipeline.pipeline_builder.TextractProcessor") as mock_textract_processor,
        patch("ingestion_pipeline.pipeline_builder.ChunkingConfig") as mock_chunking_config,
        patch("ingestion_pipeline.pipeline_builder.LayoutTextChunkingStrategy") as mock_text_strategy,
        patch("ingestion_pipeline.pipeline_builder.LayoutTableChunkingStrategy") as mock_table_strategy,
        patch("ingestion_pipeline.pipeline_builder.KeyValueChunker") as mock_kv_strategy,
        patch("ingestion_pipeline.pipeline_builder.LayoutListChunkingStrategy") as mock_list_strategy,
        patch("ingestion_pipeline.pipeline_builder.DocumentChunker") as mock_document_chunker,
        patch("ingestion_pipeline.pipeline_builder.EmbeddingGenerator") as mock_embedding_generator,
        patch("ingestion_pipeline.pipeline_builder.OpenSearchIndexer") as mock_indexer,
        patch("ingestion_pipeline.pipeline_builder.Pipeline") as mock_pipeline,
        patch("ingestion_pipeline.pipeline_builder.S3DocumentService") as mock_s3_document_service,
        patch("ingestion_pipeline.pipeline_builder.ImageConverter") as mock_image_converter,
        patch("ingestion_pipeline.pipeline_builder.DocumentPageFactory") as mock_page_factory,
        patch("ingestion_pipeline.pipeline_builder.PageProcessor") as mock_page_processor,
    ):
        # Set up minimal config for settings mock
        mock_settings.BEDROCK_EMBEDDING_MODEL_ID = "test-model-id"
        mock_settings.OPENSEARCH_CHUNK_INDEX_NAME = "test-chunk-index"
        mock_settings.OPENSEARCH_PAGE_METADATA_INDEX_NAME = "test-page-index"
        mock_settings.OPENSEARCH_PROXY_URL = "http://test-proxy"
        mock_settings.AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET = "test-source-bucket"
        mock_settings.AWS_LOCALSTACK_S3_SOURCE_DOCUMENT_ROOT_BUCKET = "test-localstack-bucket"
        mock_settings.AWS_CICA_S3_PAGE_BUCKET = "test-page-bucket"
        mock_settings.LOCAL_DEVELOPMENT_MODE = False
        yield {
            "get_s3_client": mock_get_s3_client,
            "get_textract_client": mock_get_textract_client,
            "get_textractor_instance": mock_get_textractor_instance,
            "settings": mock_settings,
            "TextractProcessor": mock_textract_processor,
            "ChunkingConfig": mock_chunking_config,
            "LayoutTextChunkingStrategy": mock_text_strategy,
            "LayoutTableChunkingStrategy": mock_table_strategy,
            "KeyValueChunker": mock_kv_strategy,
            "LayoutListChunkingStrategy": mock_list_strategy,
            "DocumentChunker": mock_document_chunker,
            "EmbeddingGenerator": mock_embedding_generator,
            "OpenSearchIndexer": mock_indexer,
            "Pipeline": mock_pipeline,
            "S3DocumentService": mock_s3_document_service,
            "ImageConverter": mock_image_converter,
            "DocumentPageFactory": mock_page_factory,
            "PageProcessor": mock_page_processor,
        }


def test_build_pipeline_wires_up_pipeline_correctly(patch_external_dependencies):
    """Test that build_pipeline returns a Pipeline instance and wires up dependencies."""
    result = build_pipeline()
    pipeline_mock = patch_external_dependencies["Pipeline"]
    assert result == pipeline_mock.return_value
    pipeline_mock.assert_called_once()
    # Check that PageProcessor and other key components were instantiated
    patch_external_dependencies["PageProcessor"].assert_called_once()
    patch_external_dependencies["S3DocumentService"].assert_called_once()
    patch_external_dependencies["ImageConverter"].assert_called_once()
    patch_external_dependencies["DocumentPageFactory"].assert_called_once()
    patch_external_dependencies["TextractProcessor"].assert_called_once()
    patch_external_dependencies["EmbeddingGenerator"].assert_called_once()
    patch_external_dependencies["OpenSearchIndexer"].assert_any_call(
        index_name="test-chunk-index", proxy_url="http://test-proxy"
    )
    patch_external_dependencies["OpenSearchIndexer"].assert_any_call(
        index_name="test-page-index", proxy_url="http://test-proxy"
    )


def test_build_pipeline_uses_localstack_bucket_when_in_local_mode(patch_external_dependencies):
    """Test that the localstack bucket is used when LOCAL_DEVELOPMENT_MODE is True."""
    patch_external_dependencies["settings"].LOCAL_DEVELOPMENT_MODE = True
    build_pipeline()
    patch_external_dependencies["S3DocumentService"].assert_called_once_with(
        s3_client=patch_external_dependencies["get_s3_client"].return_value,
        source_bucket="test-source-bucket",
        page_bucket="test-page-bucket",
    )


def test_build_pipeline_uses_source_bucket_when_not_in_local_mode(patch_external_dependencies):
    """Test that the source bucket is used when LOCAL_DEVELOPMENT_MODE is False."""
    patch_external_dependencies["settings"].LOCAL_DEVELOPMENT_MODE = False
    build_pipeline()
    patch_external_dependencies["S3DocumentService"].assert_called_once_with(
        s3_client=patch_external_dependencies["get_s3_client"].return_value,
        source_bucket="test-source-bucket",
        page_bucket="test-page-bucket",
    )
