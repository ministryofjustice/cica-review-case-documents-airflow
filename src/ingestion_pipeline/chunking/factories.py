"""This module is NOT used in the current implementation."""

from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.strategies.layout_text import LayoutTextChunkingStrategy
from ingestion_pipeline.chunking.strategies.table import LayoutTableChunkingStrategy
from ingestion_pipeline.chunking.textract import DocumentChunker


def create_default_chunker() -> DocumentChunker:
    """Builds the TextractDocumentChunker with its default dependencies."""
    config = ChunkingConfig()

    strategy_handlers = {
        "LAYOUT_TEXT": LayoutTextChunkingStrategy(config),
        "LAYOUT_TABLE": LayoutTableChunkingStrategy(config),
        # "LAYOUT_FIGURE": FigureChunkingStrategy(config),
    }

    return DocumentChunker(strategy_handlers=strategy_handlers, config=config)
