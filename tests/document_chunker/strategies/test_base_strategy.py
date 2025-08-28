import pytest

from src.document_chunker.strategies.base import ChunkingStrategyHandler  # Adjust import path


def test_cannot_instantiate_abstract_class():
    """
    Verifies that the abstract ChunkingStrategyHandler cannot be instantiated directly.
    """
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        # This line should fail, which is what the test is asserting.
        ChunkingStrategyHandler(maximum_chunk_size=512)  # type: ignore
