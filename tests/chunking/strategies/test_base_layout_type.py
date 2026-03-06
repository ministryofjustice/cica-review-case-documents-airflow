"""Unit Test: Tests for the base LayoutType class."""

import pytest

from ingestion_pipeline.chunking.strategies.layout.layout_chunking_config import LayoutChunkingConfig
from ingestion_pipeline.chunking.strategies.layout.types.base import LayoutType


def test_cannot_instantiate_abstract_class():
    """Verifies that the abstract LayoutType cannot be instantiated directly."""
    config = LayoutChunkingConfig(maximum_chunk_size=512)

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        LayoutType(config)  # type: ignore
