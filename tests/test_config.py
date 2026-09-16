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


# --- SQS settings -----------------------------------------------------------


def test_sqs_settings_defaults(settings_without_env_file):
    """SQS settings expose the documented defaults."""
    settings = settings_without_env_file
    assert settings.SQS_DOCUMENT_QUEUE == "cica-document-search-queue"
    assert settings.SQS_POLL_WAIT_TIME_SECONDS == 20
    assert settings.SQS_MAX_MESSAGES_PER_POLL == 4
    assert settings.SQS_VISIBILITY_TIMEOUT_SECONDS == 1800
    # The default visibility timeout must cover the worst-case single-document
    # processing ceiling (the Textract job timeout).
    assert settings.SQS_VISIBILITY_TIMEOUT_SECONDS >= settings.TEXTRACT_API_JOB_TIMEOUT_SECONDS


@pytest.mark.parametrize("wait_time", [-1, 0, 10, 20, 21])
def test_sqs_poll_wait_time_validation(wait_time):
    if not 0 <= wait_time <= 20:
        with pytest.raises(ValueError):
            Settings(SQS_POLL_WAIT_TIME_SECONDS=wait_time)
    else:
        Settings(SQS_POLL_WAIT_TIME_SECONDS=wait_time)


@pytest.mark.parametrize("max_messages", [0, 1, 5, 10, 11])
def test_sqs_max_messages_per_poll_validation(max_messages):
    if not 1 <= max_messages <= 10:
        with pytest.raises(ValueError):
            Settings(SQS_MAX_MESSAGES_PER_POLL=max_messages)
    else:
        Settings(SQS_MAX_MESSAGES_PER_POLL=max_messages)


@pytest.mark.parametrize(
    "visibility,valid",
    [
        (-1, False),  # below range
        (0, False),  # zero: message would be immediately visible again
        (2, True),  # minimum that also satisfies the cross-field lower bound below
        (43200, True),  # SQS service maximum (12 hours)
        (43201, False),  # above the SQS service maximum
    ],
)
def test_sqs_visibility_timeout_range(visibility, valid):
    """Visibility timeout must be within the SQS-permitted 1..43200 range.

    Low Textract timeouts (poll=1, job=2) are supplied so the cross-field lower-bound
    validator (visibility >= job timeout) and the poll<timeout validator are both
    satisfied for the valid cases, isolating the SQS range check.
    """
    textract_kwargs = {"TEXTRACT_API_POLL_INTERVAL_SECONDS": 1, "TEXTRACT_API_JOB_TIMEOUT_SECONDS": 2}
    if valid:
        Settings(SQS_VISIBILITY_TIMEOUT_SECONDS=visibility, **textract_kwargs)
    else:
        with pytest.raises(ValueError, match="SQS_VISIBILITY_TIMEOUT_SECONDS"):
            Settings(SQS_VISIBILITY_TIMEOUT_SECONDS=visibility, **textract_kwargs)


@pytest.mark.parametrize(
    "visibility,textract_timeout,valid",
    [
        (600, 600, True),  # equal: allowed (>=)
        (1800, 600, True),  # comfortably above
        (599, 600, False),  # just below the job timeout
        (300, 600, False),  # the old default, now rejected
    ],
)
def test_sqs_visibility_must_cover_textract_timeout(visibility, textract_timeout, valid):
    """The visibility timeout must be >= the worst-case single-document processing time."""
    if valid:
        Settings(
            SQS_VISIBILITY_TIMEOUT_SECONDS=visibility,
            TEXTRACT_API_JOB_TIMEOUT_SECONDS=textract_timeout,
        )
    else:
        with pytest.raises(ValueError, match="SQS_VISIBILITY_TIMEOUT_SECONDS"):
            Settings(
                SQS_VISIBILITY_TIMEOUT_SECONDS=visibility,
                TEXTRACT_API_JOB_TIMEOUT_SECONDS=textract_timeout,
            )
