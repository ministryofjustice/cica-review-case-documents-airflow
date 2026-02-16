import pytest

from ingestion_pipeline.config import Settings


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_PROXY_URL", "http://test:1234")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    settings = Settings()
    assert settings.OPENSEARCH_PROXY_URL == "http://test:1234"
    assert settings.AWS_REGION == "us-west-2"


def test_initializer_override():
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
            Settings(MAXIMUM_CHUNK_SIZE=value)
    else:
        Settings(MAXIMUM_CHUNK_SIZE=value)


@pytest.mark.parametrize("ratio", [-0.1, 0.5, 1.1])
def test_y_tolerance_ratio_validation(ratio):
    if not 0.0 <= ratio <= 1.0:
        with pytest.raises(ValueError):
            Settings(Y_TOLERANCE_RATIO=ratio)
    else:
        Settings(Y_TOLERANCE_RATIO=ratio)


@pytest.mark.parametrize("gap", [-0.5, 0.0, 0.1])
def test_max_vertical_gap_validation(gap):
    if gap <= 0.0:
        with pytest.raises(ValueError):
            Settings(MAX_VERTICAL_GAP=gap)
    else:
        Settings(MAX_VERTICAL_GAP=gap)


@pytest.mark.parametrize("poll,timeout", [(5, 4), (5, 5), (5, 10)])
def test_timeout_greater_than_poll_validation(poll, timeout):
    if timeout <= poll:
        with pytest.raises(ValueError):
            Settings(TEXTRACT_API_POLL_INTERVAL_SECONDS=poll, TEXTRACT_API_JOB_TIMEOUT_SECONDS=timeout)
    else:
        Settings(TEXTRACT_API_POLL_INTERVAL_SECONDS=poll, TEXTRACT_API_JOB_TIMEOUT_SECONDS=timeout)
