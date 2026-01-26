"""Configuration for IAM testing module.

This module provides a centralized way to access settings from the main
ingestion_pipeline package without fragile path manipulation.
"""

import sys
from pathlib import Path


def _add_src_to_path() -> None:
    """Add the src directory to sys.path if not already present.

    This allows importing from ingestion_pipeline without installing it.
    """
    # Navigate from iam_testing/ -> textract_accuracy/ -> testing/ -> local-dev-environment/ -> repo root -> src/
    src_path = Path(__file__).parent.parent.parent.parent.parent / "src"
    src_str = str(src_path.resolve())

    if src_str not in sys.path:
        sys.path.insert(0, src_str)


# Add src to path on module import
_add_src_to_path()

# Now we can safely import settings
from ingestion_pipeline.config import settings  # noqa: E402

# Re-export settings for use by other modules
__all__ = ["settings"]
