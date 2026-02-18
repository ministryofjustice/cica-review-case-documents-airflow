"""CLI runners for IAM testing.

Usage:
    python -m iam_testing.runners.single --form-id r06-121
    python -m iam_testing.runners.batch --limit 10
    python -m iam_testing.runners.augment --baseline-run 20260126_140000
"""

from .augment import main as augment_main
from .batch import main as batch_main
from .single import main as single_main

__all__ = ["single_main", "batch_main", "augment_main"]
