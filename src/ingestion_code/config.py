from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):  # type: ignore
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    LOCAL: bool = True
    # Data directory (relative to root)
    DATA_DIR: str = "data"
    # Embedding model
    LOCAL_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
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
    AWS_ACCESS_KEY_ID: str = "aws_access_key_id"
    AWS_SECRET_ACCESS_KEY: str = "aws_secret_access_key"
    AWS_SESSION_TOKEN: str = "aws_session_token"
    AWS_REGION: str = "aws_region"
    S3_BUCKET_NAME: str = "alpha-a2j-projects"
    S3_PREFIX: str = "textract-test"
    POLL_INTERVAL_SECONDS: int = 5  # for checking Textract job status
    BEDROCK_TOKENIZER_NAME: str = "cl100k_base"
    BEDROCK_CHUNK_SIZE: int = 300  # 100 tokens ~ 75 words (1 token ~ (3/4) words)
    # Cohere model
    # BEDROCK_EMBEDDING_MODEL_ID: str = "cohere.embed-english-v3"
    # or Titan model
    BEDROCK_EMBEDDING_MODEL_ID: str = "amazon.titan-embed-text-v2:0"


settings = Settings()
