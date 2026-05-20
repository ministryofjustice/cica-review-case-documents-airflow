import pytest

from ingestion_pipeline.config import Settings


def _disable_env_file_loading(monkeypatch):
    """Disable .env file loading in Settings to ensure hermetic tests.

    This prevents local .env files from interfering with tests that validate code defaults.
    """
    config = Settings.model_config.copy()
    config["env_file"] = None
    monkeypatch.setattr(Settings, "model_config", config)


@pytest.fixture
def settings_without_env_file(monkeypatch):
    """Create Settings instance with .env file loading disabled.

    This ensures hermetic tests that validate only code defaults, not local .env overrides.
    """
    _disable_env_file_loading(monkeypatch)
    return Settings()


def test_env_overrides(monkeypatch):
    """Verify that system environment variables override defaults.

    Note: This test allows .env file loading to test real-world priority order where
    system env vars take precedence over .env file values (per pydantic-settings priority).
    """
    monkeypatch.setenv("OPENSEARCH_PROXY_URL", "http://test:1234")
    monkeypatch.setenv("OPENSEARCH_VERIFY_CERTS", "true")
    monkeypatch.setenv("OPENSEARCH_SSL_ASSERT_HOSTNAME", "true")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    settings = Settings()
    assert settings.OPENSEARCH_PROXY_URL == "http://test:1234"
    assert settings.OPENSEARCH_VERIFY_CERTS is True
    assert settings.OPENSEARCH_SSL_ASSERT_HOSTNAME is True
    assert settings.AWS_REGION == "us-west-2"


def test_opensearch_tls_defaults_are_secure(settings_without_env_file):
    """Verify that TLS verification is enabled by default (secure-by-default posture)."""
    assert settings_without_env_file.OPENSEARCH_VERIFY_CERTS is True
    assert settings_without_env_file.OPENSEARCH_SSL_ASSERT_HOSTNAME is True


def test_opensearch_tls_can_be_disabled_via_env(monkeypatch):
    """Verify that operators can opt out of TLS verification for self-signed certificate environments.

    Tests system environment variable override behavior only (not .env file loading).
    """
    # Disable env_file loading to isolate this test to system environment variables only
    _disable_env_file_loading(monkeypatch)
    monkeypatch.setenv("OPENSEARCH_VERIFY_CERTS", "false")
    monkeypatch.setenv("OPENSEARCH_SSL_ASSERT_HOSTNAME", "false")
    settings = Settings()
    assert settings.OPENSEARCH_VERIFY_CERTS is False
    assert settings.OPENSEARCH_SSL_ASSERT_HOSTNAME is False


def test_initializer_override():
    """Verify that initializer arguments override defaults.

    Note: This test allows .env file loading because it validates that direct initializer
    arguments take precedence (highest priority), regardless of other config sources.
    """
    settings = Settings(OPENSEARCH_PROXY_URL="http://init:9999", AWS_REGION="ap-south-1")
    assert settings.OPENSEARCH_PROXY_URL == "http://init:9999"
    assert settings.AWS_REGION == "ap-south-1"


@pytest.mark.parametrize("pages", [{0, 1}, {-1, 2}, {1, 2, 3}])
def test_debug_page_numbers_validation(pages):
    if any(page < 1 for page in pages):
        with pytest.raises(ValueError):
            Settings(DEBUG_PAGE_NUMBERS=pages)
    else:
        Settings(DEBUG_PAGE_NUMBERS=pages)  # Should not raise


@pytest.mark.parametrize("value", [-10, 0, 10])
def test_maximum_chunk_size_validation(value):
    if value <= 0:
        with pytest.raises(ValueError):
            Settings(LAYOUT_CHUNKING_MAXIMUM_CHUNK_SIZE=value)
    else:
        Settings(LAYOUT_CHUNKING_MAXIMUM_CHUNK_SIZE=value)


@pytest.mark.parametrize("ratio", [-0.1, 0.5, 1.1])
def test_y_tolerance_ratio_validation(ratio):
    if not 0.0 <= ratio <= 1.0:
        with pytest.raises(ValueError):
            Settings(LAYOUT_CHUNKING_Y_TOLERANCE_RATIO=ratio)
    else:
        Settings(LAYOUT_CHUNKING_Y_TOLERANCE_RATIO=ratio)


@pytest.mark.parametrize("gap", [-0.5, 0.0, 0.1])
def test_max_vertical_gap_validation(gap):
    if gap <= 0.0:
        with pytest.raises(ValueError):
            Settings(LAYOUT_CHUNKING_MAX_VERTICAL_GAP=gap)
    else:
        Settings(LAYOUT_CHUNKING_MAX_VERTICAL_GAP=gap)


@pytest.mark.parametrize("poll,timeout", [(5, 4), (5, 5), (5, 10)])
def test_timeout_greater_than_poll_validation(poll, timeout):
    if timeout <= poll:
        with pytest.raises(ValueError):
            Settings(TEXTRACT_API_POLL_INTERVAL_SECONDS=poll, TEXTRACT_API_JOB_TIMEOUT_SECONDS=timeout)
    else:
        Settings(TEXTRACT_API_POLL_INTERVAL_SECONDS=poll, TEXTRACT_API_JOB_TIMEOUT_SECONDS=timeout)
