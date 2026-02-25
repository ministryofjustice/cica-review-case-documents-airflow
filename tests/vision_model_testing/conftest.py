"""Pytest configuration for vision_model_testing tests.

This conftest.py adds the vision_model_testing module to sys.path before tests run.
"""

import sys
from pathlib import Path

# Add the handwriting_accuracy module to path for imports
# This includes both vision_model_testing and iam_testing (needed for scoring imports)
_testing_path = Path(__file__).parent.parent.parent / "local-dev-environment" / "testing" / "handwriting_accuracy"
sys.path.insert(0, str(_testing_path))

# Also add src path for ingestion_pipeline config
_src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(_src_path))
