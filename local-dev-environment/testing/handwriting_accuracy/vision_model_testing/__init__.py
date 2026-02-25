"""Vision model testing for direct image-to-text OCR.

This package tests vision-capable LLMs (Nova Pro, Nova Lite, Claude 3.5 Sonnet)
for extracting handwritten text directly from images, bypassing Textract.

Enables comparison:
- Vision-only vs Textract
- Vision + LLM augmentation vs Textract + LLM augmentation
"""

from pathlib import Path

# Root directory for this testing module
VISION_TESTING_ROOT = Path(__file__).parent

# Data directory (shared with iam_testing for custom documents)
DATA_DIR = VISION_TESTING_ROOT.parent / "data"

__all__ = ["VISION_TESTING_ROOT", "DATA_DIR"]
