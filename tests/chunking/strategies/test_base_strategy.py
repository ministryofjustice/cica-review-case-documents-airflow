import pytest

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig  # ← Changed import
from ingestion_pipeline.chunking.strategies.base import ChunkingStrategyHandler


def test_cannot_instantiate_abstract_class():
    """
    Verifies that the abstract ChunkingStrategyHandler cannot be instantiated directly.
    """
    config = ChunkingConfig(maximum_chunk_size=512)

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        ChunkingStrategyHandler(config)  # type: ignore
