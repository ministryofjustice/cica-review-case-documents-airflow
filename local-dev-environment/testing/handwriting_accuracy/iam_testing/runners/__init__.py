"""CLI runners for IAM testing.

Run from local-dev-environment:
    source .venv/bin/activate
    PYTHONPATH=testing/handwriting_accuracy python -m iam_testing.runners.single --form-id <FORM_ID>
    PYTHONPATH=testing/handwriting_accuracy python -m iam_testing.runners.batch --limit 10
    PYTHONPATH=testing/handwriting_accuracy python -m iam_testing.runners.augment --baseline-run <RUN_ID>
"""

from iam_testing.runners.augment import main as augment_main
from iam_testing.runners.batch import main as batch_main
from iam_testing.runners.single import main as single_main

__all__ = ["single_main", "batch_main", "augment_main"]
