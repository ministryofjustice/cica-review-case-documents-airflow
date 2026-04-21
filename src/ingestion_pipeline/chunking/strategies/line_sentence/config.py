"""Configuration for line-by-line sentence-aware chunking strategy."""

from dataclasses import dataclass
from typing import Any


@dataclass
class LineSentenceChunkingConfig:
    """Configuration for line-by-line sentence-aware chunking."""

    # Word count limits
    min_words: int
    max_words: int

    # Vertical spacing threshold for forcing chunk breaks
    # This is relative to page height (0.0 to 1.0)
    max_vertical_gap_ratio: float

    # Toggle for gap splitting behavior (for testing, not yet used)
    include_gap_line_in_previous_chunk: bool = False

    @classmethod
    def from_settings(cls, settings_obj: Any = None) -> "LineSentenceChunkingConfig":
        """Create config from app settings.

        Args:
            settings_obj: Optional settings-like object used for easier testing.
                          When not provided, imports global app settings.
        """
        if settings_obj is None:
            from ingestion_pipeline.config import settings as settings_obj

        return cls(
            min_words=settings_obj.SENTENCE_CHUNKER_MIN_WORDS,
            max_words=settings_obj.SENTENCE_CHUNKER_MAX_WORDS,
            max_vertical_gap_ratio=settings_obj.SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO,
        )
