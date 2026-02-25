"""Tests for vision model prompts."""

import pytest
from vision_model_testing.llm.prompt import (
    DEFAULT_VISION_PROMPT,
    VISION_PROMPTS,
    get_vision_prompt,
    get_vision_prompt_hash,
    validate_vision_prompt_version,
)


class TestPromptVersioning:
    """Test prompt versioning functions."""

    def test_default_prompt_exists(self):
        """Default prompt version should exist in VISION_PROMPTS."""
        assert DEFAULT_VISION_PROMPT in VISION_PROMPTS

    def test_all_prompts_are_non_empty(self):
        """All prompt versions should have non-empty text."""
        for version, prompt in VISION_PROMPTS.items():
            assert prompt, f"Prompt {version} is empty"
            assert len(prompt) > 10, f"Prompt {version} is too short"

    def test_validate_valid_version(self):
        """validate_vision_prompt_version should accept valid versions."""
        for version in VISION_PROMPTS.keys():
            assert validate_vision_prompt_version(version) == version

    def test_validate_invalid_version(self):
        """validate_vision_prompt_version should reject invalid versions."""
        with pytest.raises(ValueError, match="Unknown vision prompt version"):
            validate_vision_prompt_version("invalid_version")

    def test_get_vision_prompt_returns_correct_text(self):
        """get_vision_prompt should return the correct prompt text."""
        for version, expected in VISION_PROMPTS.items():
            assert get_vision_prompt(version) == expected

    def test_get_vision_prompt_default(self):
        """get_vision_prompt with no args should return default prompt."""
        assert get_vision_prompt() == VISION_PROMPTS[DEFAULT_VISION_PROMPT]

    def test_prompt_hash_format(self):
        """Prompt hash should have version prefix and hash suffix."""
        hash_str = get_vision_prompt_hash("v1")
        assert hash_str.startswith("v1_")
        # Hash suffix should be 8 hex characters
        hash_suffix = hash_str.split("_", 1)[1]
        assert len(hash_suffix) == 8
        assert all(c in "0123456789abcdef" for c in hash_suffix)

    def test_prompt_hash_deterministic(self):
        """Same prompt version should always produce same hash."""
        hash1 = get_vision_prompt_hash("v1")
        hash2 = get_vision_prompt_hash("v1")
        assert hash1 == hash2

    def test_different_prompts_different_hashes(self):
        """Different prompt versions should have different hashes."""
        hashes = [get_vision_prompt_hash(v) for v in VISION_PROMPTS.keys()]
        assert len(hashes) == len(set(hashes)), "Duplicate hashes found"


class TestPromptContent:
    """Test prompt content requirements."""

    def test_prompts_request_text_extraction(self):
        """All prompts should mention text extraction."""
        extraction_keywords = ["extract", "transcribe"]
        for version, prompt in VISION_PROMPTS.items():
            prompt_lower = prompt.lower()
            has_keyword = any(kw in prompt_lower for kw in extraction_keywords)
            assert has_keyword, f"Prompt {version} should mention extraction"

    def test_prompts_specify_output_format(self):
        """Prompts should specify to return only the text."""
        for version, prompt in VISION_PROMPTS.items():
            prompt_lower = prompt.lower()
            # Should mention returning only text
            assert "return only" in prompt_lower or "only the" in prompt_lower, (
                f"Prompt {version} should specify output format"
            )
