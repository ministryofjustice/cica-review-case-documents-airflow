"""Testing utilities for search relevance evaluation."""

import os.path
import sys

# Add the project 'src' directory to sys.path so testing modules can import from ingestion_pipeline
# This runs once when the testing package is first imported
# Path: local-dev-environment/testing/__init__.py → need to go up 2 levels to project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROJECT_SRC = os.path.join(_PROJECT_ROOT, "src")
if _PROJECT_SRC not in sys.path:
    sys.path.insert(0, _PROJECT_SRC)
