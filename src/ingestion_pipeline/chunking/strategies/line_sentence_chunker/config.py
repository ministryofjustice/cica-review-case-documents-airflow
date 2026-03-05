"""Configuration for line-by-line sentence-aware chunking strategy."""

from dataclasses import dataclass


@dataclass
class LineSentenceChunkingConfig:
    """Configuration for line-by-line sentence-aware chunking."""

    # Word count limits
    min_words: int = 60  # Lowered to allow more flexibility
    max_words: int = 120  # Increased to allow more tolerance for sentence breaks

    # Vertical spacing threshold for forcing chunk breaks
    # This is relative to page height (0.0 to 1.0)
    max_vertical_gap_ratio: float = 0.05

    # Whether to enable verbose debug logging
    debug: bool = False
