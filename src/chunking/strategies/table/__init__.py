# src/chunking/strategies/table/__init__.py

"""
Table chunking strategies package.

This file makes the primary classes available for easier import from other modules.
For example, other modules can now use:
`from src.chunking.strategies.table import LayoutTableChunkingStrategy`
"""

# Expose the main strategy class from its submodule
from .layout_table_strategy import LayoutTableChunkingStrategy

# Also expose the relevant data types from their submodule
from .schemas import TextBlock

# It's good practice to also define __all__ to control `from ... import *`
# and to make the public API of the package explicit.
__all__ = [
    "LayoutTableChunkingStrategy",
    "TextBlock",
]
