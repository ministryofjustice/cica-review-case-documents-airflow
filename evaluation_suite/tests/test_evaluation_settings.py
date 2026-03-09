"""Unit tests for evaluation_settings.py."""

import pytest

from evaluation_suite.search_evaluation import evaluation_settings


def test_apply_overrides_and_reset_settings():
    """Test applying overrides and resetting settings."""
    # Save original settings
    original = evaluation_settings.get_current_settings().copy()

    # Apply overrides
    overrides = {
        "KEYWORD_BOOST": 9.9,
        "SEMANTIC_BOOST": 8.8,
        "RESULT_SIZE": 123,
        "DATE_FORMAT_DETECTION": False,
    }
    evaluation_settings.apply_overrides(overrides)
    current = evaluation_settings.get_current_settings()
    for key, value in overrides.items():
        assert current[key] == value

    # Reset settings
    evaluation_settings.reset_settings()
    reset = evaluation_settings.get_current_settings()
    assert reset == original


def test_apply_overrides_invalid_key():
    """Test that applying overrides with an invalid key raises ValueError."""
    with pytest.raises(ValueError):
        evaluation_settings.apply_overrides({"NOT_A_SETTING": 1})


def test_get_current_settings_returns_dict():
    """Test that get_current_settings returns a dictionary."""
    settings = evaluation_settings.get_current_settings()
    assert isinstance(settings, dict)
    # Should contain all default keys
    for key in evaluation_settings._DEFAULTS:
        assert key in settings


def test_reset_settings_restores_defaults():
    """Test that reset_settings restores default settings."""
    # Change a setting
    evaluation_settings.KEYWORD_BOOST = 99
    evaluation_settings.reset_settings()
    assert evaluation_settings.KEYWORD_BOOST == evaluation_settings._DEFAULTS["KEYWORD_BOOST"]


def test_apply_overrides_multiple_types():
    """Test that apply_overrides works with multiple types."""
    overrides = {
        "FUZZINESS": "2",
        "ADAPTIVE_SCORE_FILTER": True,
        "MAX_EXPANSIONS": 999,
    }
    evaluation_settings.apply_overrides(overrides)
    current = evaluation_settings.get_current_settings()
    for key, value in overrides.items():
        assert current[key] == value
    evaluation_settings.reset_settings()
