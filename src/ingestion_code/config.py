from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):  # type: ignore
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    # Data directory (relative to root)
    DATA_DIR: str = "data"
    # Embedding model
    MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    # Chunking setting
    TOKEN_OVERLAP: int = 0
    # OpenSearch client
    OPENSEARCH_PORT: int = 4566
    OPENSEARCH_HOST: str = (
        "case-document-search-domain.eu-west-2.opensearch.localhost.localstack.cloud"
    )
    OPENSEARCH_USERNAME: str = "username"
    OPENSEARCH_PASSWORD: str = "password"
    OPENSEARCH_INDEX_NAME: str = "case-documents"


settings = Settings()
