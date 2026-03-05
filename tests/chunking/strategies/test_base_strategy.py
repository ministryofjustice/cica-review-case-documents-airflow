"""Unit Test: Tests for the base ChunkingStrategyHandler class."""

import pytest

from ingestion_pipeline.chunking.layout_handler.layout_chunking_config import LayoutChunkingConfig
from ingestion_pipeline.chunking.layout_handler.strategies.base import ChunkingStrategyHandler


def test_cannot_instantiate_abstract_class():
    """Verifies that the abstract ChunkingStrategyHandler cannot be instantiated directly."""
    config = LayoutChunkingConfig(maximum_chunk_size=512)

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        ChunkingStrategyHandler(config)  # type: ignore
