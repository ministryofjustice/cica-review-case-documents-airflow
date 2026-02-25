"""Configuration for IAM testing module.

This module provides a centralized way to access settings from the main
ingestion_pipeline package without fragile path manipulation.
"""

import sys
from pathlib import Path


def _find_repo_root() -> Path:
    """Find repository root by looking for .git directory."""
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / ".git").exists():
            return parent
    raise RuntimeError("Could not find repository root (.git not found)")


def _add_src_to_path() -> None:
    """Add the src directory to sys.path if not already present.

    This allows importing from ingestion_pipeline without installing it.
    """
    src_path = _find_repo_root() / "src"
    src_str = str(src_path)

    if src_str not in sys.path:
        sys.path.insert(0, src_str)


# Add src to path on module import
_add_src_to_path()

# Now we can safely import settings
from ingestion_pipeline.config import settings  # noqa: E402

# Re-export settings for use by other modules
__all__ = ["settings"]
