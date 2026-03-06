"""Configuration for chunking behavior in the ingestion pipeline."""

from dataclasses import dataclass
from enum import Enum

from ingestion_pipeline.config import settings


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
    maximum_chunk_size: int = settings.LAYOUT_CHUNKING_MAXIMUM_CHUNK_SIZE
    strategy: ChunkingStrategy = ChunkingStrategy.LAYOUT_TEXT

    # Specific to table chunking strategies
    # is this statement true, review at a later date
    y_tolerance_ratio: float = settings.LAYOUT_CHUNKING_Y_TOLERANCE_RATIO
    max_vertical_gap: float = (
        settings.LAYOUT_CHUNKING_MAX_VERTICAL_GAP
    )  # Specific to grouping and merge chunking strategies
    line_chunk_char_limit: int = (
        settings.LAYOUT_CHUNKING_LINE_CHUNK_CHAR_LIMIT
    )  # Specific to table line chunking strategies
