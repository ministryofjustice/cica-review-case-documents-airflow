"""Path constants for iam_testing module.

Import these instead of using fragile parent.parent chains.
"""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent  # iam_testing/
TEXTRACT_ACCURACY_ROOT = PACKAGE_ROOT.parent  # textract_accuracy/
DATA_DIR = TEXTRACT_ACCURACY_ROOT / "data"  # textract_accuracy/data/


def get_repo_root() -> Path:
    """Find repository root by looking for .git directory."""
    for parent in PACKAGE_ROOT.parents:
        if (parent / ".git").exists():
            return parent
    raise RuntimeError("Could not find repository root (.git not found)")
