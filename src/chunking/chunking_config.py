from dataclasses import dataclass
from enum import Enum

# from src.core import settings  # Your settings import


class ChunkingStrategy(Enum):
    """Enumeration of available chunking strategies."""

    LAYOUT_TEXT = "LAYOUT_TEXT"
    LAYOUT_TABLE = "LAYOUT_TABLE"


@dataclass
class ChunkingConfig:
    """Configuration for chunking behavior."""

    maximum_chunk_size: int = 1000  # settings.MAXIMUM_CHUNK_SIZE
    strategy: ChunkingStrategy = ChunkingStrategy.LAYOUT_TEXT
    y_tolerance_ratio: float = 0.5  # Specific to table chunking strategies
    line_chunk_char_limit: int = 300  # Specific to table line chunking strategies
