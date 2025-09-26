"""
Table chunking strategies package.

This file makes the primary classes available for easier import from other modules.
For example, other modules can now use:
`from src.chunking.strategies.table import LayoutTableChunkingStrategy`
"""

from .layout_key_value import KeyValueChunker

__all__ = [
    "KeyValueChunker",
]
