"""Factory for creating DocumentChunker implementations based on config or runtime selection."""


from ingestion_pipeline.chunking.base_document_chunker import DocumentChunker
from ingestion_pipeline.chunking.chunking_config import ChunkingConfig
from ingestion_pipeline.chunking.line_based_document_chunker import LineBasedDocumentChunker
from ingestion_pipeline.chunking.strategies.key_value.layout_key_value import KeyValueChunker
from ingestion_pipeline.chunking.strategies.layout_text import LayoutTextChunkingStrategy
from ingestion_pipeline.chunking.strategies.line_sentence_chunker import LineSentenceChunkingConfig
from ingestion_pipeline.chunking.strategies.list.list_chunker import LayoutListChunkingStrategy
from ingestion_pipeline.chunking.strategies.table.layout_table import LayoutTableChunkingStrategy
from ingestion_pipeline.chunking.textract_document_chunker import TextractLayoutDocumentChunker
from ingestion_pipeline.config import settings

ALLOWED_CHUNKER_TYPES = {"layout", "line"}

def get_document_chunker(chunker_type: str) -> DocumentChunker:
    """Factory function to return the desired DocumentChunker implementation.

    Args:
        chunker_type (str): Which chunker to use. Allowed: "layout", "line".

    Returns:
        DocumentChunker: The selected chunker implementation.

    Raises:
        ValueError: If chunker_type is not recognized.
    """
    chunker_type = str(chunker_type).strip().lower()
    if chunker_type not in ALLOWED_CHUNKER_TYPES:
        raise ValueError(f"Unknown chunker_type: '{chunker_type}'. Allowed values: {sorted(ALLOWED_CHUNKER_TYPES)}")

    if chunker_type == "layout":
        chunking_config = ChunkingConfig()
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
    elif chunker_type == "line":
        line_chunking_config = LineSentenceChunkingConfig(
            min_words=settings.SENTENCE_CHUNKER_MIN_WORDS,
            max_words=settings.SENTENCE_CHUNKER_MAX_WORDS,
            max_vertical_gap_ratio=settings.SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO,
            debug=False,
        )
        return LineBasedDocumentChunker(config=line_chunking_config)
    else:
        raise ValueError(f"Unknown chunker_type: '{chunker_type}'. Allowed values: {sorted(ALLOWED_CHUNKER_TYPES)}")
