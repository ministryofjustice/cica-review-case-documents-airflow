"""Pytest configuration for textract_accuracy tests.

This conftest.py adds the iam_testing module to sys.path before tests run,
allowing clean imports without E402 violations in test files.
"""

import sys
from pathlib import Path

# Add the testing module to path for imports
_testing_path = Path(__file__).parent.parent.parent / "local-dev-environment" / "testing" / "textract_accuracy"
sys.path.insert(0, str(_testing_path))
