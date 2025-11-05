"""Table chunking strategies package.

This file makes the primary classes available for easier import from other modules.
For example, other modules can now use:
`from ingestion_pipeline.chunking.strategies.table import LayoutTableChunkingStrategy`
"""

from .layout_table import LayoutTableChunkingStrategy
from .schemas import TextBlock

__all__ = [
    "LayoutTableChunkingStrategy",
    "TextBlock",
]
