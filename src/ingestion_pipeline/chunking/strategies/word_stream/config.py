"""Configuration for Textractor word-stream sentence-aware chunking."""

from dataclasses import dataclass
from typing import Any


@dataclass
class WordStreamChunkingConfig:
    """Configuration for chunking words returned by get_text_and_words()."""

    min_words: int
    max_words: int
    max_vertical_gap_ratio: float
    forward_lookahead_words: int = 8
    backward_scan_words: int = 20
    normalize_spacing: bool = True

    @classmethod
    def from_settings(cls, settings_obj: Any = None) -> "WordStreamChunkingConfig":
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
            forward_lookahead_words=getattr(settings_obj, "SENTENCE_CHUNKER_FORWARD_LOOKAHEAD_WORDS", 8),
            backward_scan_words=getattr(settings_obj, "SENTENCE_CHUNKER_BACKWARD_SCAN_WORDS", 20),
            normalize_spacing=True,
        )
