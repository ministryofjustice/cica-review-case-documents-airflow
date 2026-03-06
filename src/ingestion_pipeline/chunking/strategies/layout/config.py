"""Configuration for chunking behavior in the ingestion pipeline."""

from dataclasses import dataclass
from enum import Enum


# TODO review is this Enum used?
class ChunkingStrategy(Enum):
    """Enumeration of available chunking strategies."""

    LAYOUT_TEXT = "LAYOUT_TEXT"
    LAYOUT_TABLE = "LAYOUT_TABLE"


@dataclass
class LayoutChunkingConfig:
    """Configuration for chunking behavior."""

    # TODO review perhaps create individual configs for each type
    # and a strategy to select the correct one?
    maximum_chunk_size: int

    # Specific to table chunking strategies
    # is this statement true, review at a later date
    y_tolerance_ratio: float
    max_vertical_gap: float
    line_chunk_char_limit: int

    # TODO is this necessary?
    strategy: ChunkingStrategy = ChunkingStrategy.LAYOUT_TEXT
