"""Factory for creating ChunkStrategy implementations based on config or runtime selection."""

import logging

from ingestion_pipeline.chunking.chunk_strategy import ChunkStrategy
from ingestion_pipeline.chunking.strategies.layout.config import LayoutChunkingConfig
from ingestion_pipeline.chunking.strategies.layout.layout_chunk_handler import TextractLayoutDocumentChunker
from ingestion_pipeline.chunking.strategies.layout.types.key_value.layout_key_value import KeyValueChunker
from ingestion_pipeline.chunking.strategies.layout.types.list.list_chunker import LayoutListChunkingStrategy
from ingestion_pipeline.chunking.strategies.layout.types.table.layout_table import LayoutTableChunkingStrategy
from ingestion_pipeline.chunking.strategies.layout.types.text.layout_text import LayoutTextChunkingStrategy
from ingestion_pipeline.chunking.strategies.line_sentence.config import LineSentenceChunkingConfig
from ingestion_pipeline.chunking.strategies.line_sentence.line_sentence_handler import LineBasedDocumentChunker
from ingestion_pipeline.config import settings

ALLOWED_CHUNKER_TYPES = {"layout", "linear-sentence-splitter"}
logger = logging.getLogger(__name__)


def get_chunk_strategy(chunker_type: str) -> ChunkStrategy:
    """Factory function to return the desired ChunkStrategy implementation.

    Args:
        chunker_type (str): Which chunker to use. Allowed: "layout", "linear-sentence-splitter".

    Returns:
        ChunkStrategy: The selected chunker implementation.

    Raises:
        ValueError: If chunker_type is not recognized.
    """
    chunker_type = str(chunker_type).strip().lower()
    if chunker_type not in ALLOWED_CHUNKER_TYPES:
        raise ValueError(f"Unknown chunker_type: '{chunker_type}'. Allowed values: {sorted(ALLOWED_CHUNKER_TYPES)}")

    logger.info(f"Initialising ChunkStrategy of type: {chunker_type}")

    if chunker_type == "layout":
        chunking_config = LayoutChunkingConfig(
            maximum_chunk_size=settings.LAYOUT_CHUNKING_MAXIMUM_CHUNK_SIZE,
            y_tolerance_ratio=settings.LAYOUT_CHUNKING_Y_TOLERANCE_RATIO,
            max_vertical_gap=settings.LAYOUT_CHUNKING_MAX_VERTICAL_GAP,
            line_chunk_char_limit=settings.LAYOUT_CHUNKING_LINE_CHUNK_CHAR_LIMIT,
        )

        layout_text_strategy = LayoutTextChunkingStrategy(chunking_config)
        layout_table_strategy = LayoutTableChunkingStrategy(chunking_config)
        layout_key_value_strategy = KeyValueChunker(chunking_config)
        layout_list_strategy = LayoutListChunkingStrategy(chunking_config)
        strategy_handlers = {
            "LAYOUT_TEXT": layout_text_strategy,
            "LAYOUT_HEADER": layout_text_strategy,
            "LAYOUT_TITLE": layout_text_strategy,
            "LAYOUT_TABLE": layout_table_strategy,
            "LAYOUT_SECTION_HEADER": layout_text_strategy,
            "LAYOUT_FOOTER": layout_text_strategy,
            "LAYOUT_FIGURE": layout_table_strategy,
            "LAYOUT_KEY_VALUE": layout_key_value_strategy,
            "LAYOUT_LIST": layout_list_strategy,
        }
        return TextractLayoutDocumentChunker(strategy_handlers=strategy_handlers, config=chunking_config)
    elif chunker_type == "linear-sentence-splitter":
        line_chunking_config = LineSentenceChunkingConfig(
            min_words=settings.SENTENCE_CHUNKER_MIN_WORDS,
            max_words=settings.SENTENCE_CHUNKER_MAX_WORDS,
            max_vertical_gap_ratio=settings.SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO,
        )
        return LineBasedDocumentChunker(config=line_chunking_config)
    else:
        raise ValueError(f"Unknown chunker_type: '{chunker_type}'. Allowed values: {sorted(ALLOWED_CHUNKER_TYPES)}")
