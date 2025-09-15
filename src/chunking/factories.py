from src.chunking.config import ChunkingConfig
from src.chunking.strategies.layout_text import LayoutTextChunkingStrategy
from src.chunking.strategies.table import LayoutTableChunkingStrategy
from src.chunking.textract import TextractDocumentChunker


def create_default_chunker() -> TextractDocumentChunker:
    """Builds the TextractDocumentChunker with its default dependencies."""
    config = ChunkingConfig()

    default_strategy = LayoutTextChunkingStrategy(config)
    strategy_handlers = {
        "LAYOUT_TEXT": LayoutTextChunkingStrategy(config),
        "LAYOUT_TABLE": LayoutTableChunkingStrategy(config),
        # "LAYOUT_FIGURE": FigureChunkingStrategy(config),
    }

    return TextractDocumentChunker(
        strategy_handlers=strategy_handlers, default_strategy=default_strategy, config=config
    )
