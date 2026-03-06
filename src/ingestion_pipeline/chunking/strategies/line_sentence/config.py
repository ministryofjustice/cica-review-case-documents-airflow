"""Configuration for line-by-line sentence-aware chunking strategy."""

from dataclasses import dataclass


@dataclass
class LineSentenceChunkingConfig:
    """Configuration for line-by-line sentence-aware chunking."""

    # Word count limits
    min_words: int
    max_words: int

    # Vertical spacing threshold for forcing chunk breaks
    # This is relative to page height (0.0 to 1.0)
    max_vertical_gap_ratio: float

    # Whether to enable verbose debug logging
    # TODO change this to use when Loger.DEBUG is on
    debug: bool = False
