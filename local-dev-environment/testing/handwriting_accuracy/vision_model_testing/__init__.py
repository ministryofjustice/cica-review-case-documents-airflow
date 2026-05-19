"""Vision model testing for handwriting extraction from document page images.

Supports evaluation (WER/CER against ground truth) using vision LLMs, and
provides the LiteLLMVisionClient for production pipeline integration.

Recommended model: bedrock-claude-opus-4-6 via the MoJ LiteLLM gateway.
Recommended prompt: v1.5-mm (best evaluated, avg WER 0.1522).

See vision_model_testing/README.md for full usage and integration guidance.
"""

from pathlib import Path

# Root directory for this testing module
VISION_TESTING_ROOT = Path(__file__).parent

# Data directory (shared with iam_testing for custom documents)
DATA_DIR = VISION_TESTING_ROOT.parent / "data"

__all__ = ["VISION_TESTING_ROOT", "DATA_DIR"]
