"""Unit Test: Tests for the base LayoutType class."""

import pytest

from ingestion_pipeline.chunking.strategies.layout.config import LayoutChunkingConfig
from ingestion_pipeline.chunking.strategies.layout.types.base import LayoutType


def test_cannot_instantiate_abstract_class():
    """Verifies that the abstract LayoutType cannot be instantiated directly."""
    config = LayoutChunkingConfig(
        maximum_chunk_size=500,
        y_tolerance_ratio=0.1,
        max_vertical_gap=10,
        line_chunk_char_limit=100,
    )

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        LayoutType(config)  # type: ignore
