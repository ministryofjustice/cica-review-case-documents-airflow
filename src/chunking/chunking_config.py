from dataclasses import dataclass
from enum import Enum

from src.config import settings


class ChunkingStrategy(Enum):
    """Enumeration of available chunking strategies."""

    LAYOUT_TEXT = "LAYOUT_TEXT"
    LAYOUT_TABLE = "LAYOUT_TABLE"


@dataclass
class ChunkingConfig:
    """Configuration for chunking behavior."""

    # TODO review perhaps create individual configs for each type
    # and a strategy to select the correct one?
    maximum_chunk_size: int = settings.MAXIMUM_CHUNK_SIZE
    strategy: ChunkingStrategy = ChunkingStrategy.LAYOUT_TEXT

    y_tolerance_ratio: float = settings.Y_TOLERANCE_RATIO  # Specific to table chunking strategies
    max_vertical_gap: float = settings.MAX_VERTICAL_GAP  # Specific to grouping and merge chunking strategies
    line_chunk_char_limit: int = settings.LINE_CHUNK_CHAR_LIMIT  # Specific to table line chunking strategies
