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
