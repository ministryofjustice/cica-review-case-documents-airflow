from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Order of priority for pydantic-settings:
#
# 1. Arguments to the Initializer (Highest Priority - rarely used):
#    If you pass values directly when creating the object (e.g., Settings(OPENSEARCH_PORT=1234)),
#    these take precedence. However, this defeats the purpose of pydantic-settings and is uncommon.
#
# 2. System Environment Variables:
#    Pydantic looks for environment variables set in your operating system.
#    Example: export OPENSEARCH_PORT=5000 before running the script.
#
# 3. .env File Values:
#    If env_file=".env" is specified in model_config, Pydantic reads from the .env file.
#    Example: OPENSEARCH_PORT=9201 in .env will be used.
#
# 4. Default Values in the Class (Lowest Priority):
#    If no value is found elsewhere, use the default from the class definition.
#    Example: OPENSEARCH_PORT: int = 9200

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):  # type: ignore
    model_config = SettingsConfigDict(
        # Only load .env if it exists (local dev)
        env_file=str(ENV_FILE_PATH) if ENV_FILE_PATH.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    # -- OpenSearch client --
    # Default credentials for LOCAL DEVELOPMENT ONLY
    # In production, these MUST be overridden
    OPENSEARCH_HOST: str = "localhost"
    OPENSEARCH_URL_PREFIX: str = "/opensearch/eu-west-2/case-document-search-domain"
    OPENSEARCH_PORT: int = 9200
    OPENSEARCH_USERNAME: str = "admin"
    OPENSEARCH_PASSWORD: str = "really-secure-passwordAa!1"
    OPENSEARCH_CHUNK_INDEX_NAME: str = "page_chunks"
    # -- AWS --
    AWS_ACCESS_KEY_ID: str = "aws_access_key_id"
    AWS_SECRET_ACCESS_KEY: str = "aws_secret_access_key"
    AWS_SESSION_TOKEN: str = "aws_session_token"
    AWS_REGION: str = "aws_region"

    # review these values when we have a working system
    MAXIMUM_CHUNK_SIZE: int = 80  # maximum chunk size
    Y_TOLERANCE_RATIO: float = 0.5
    MAX_VERTICAL_GAP: float = 0.5
    LINE_CHUNK_CHAR_LIMIT: int = 300

    # Create a unique namespace for your application
    # This is a fixed UUID defined once for the system.
    # TODO This should be a UUID that is generated, is stored as a secret? and is kept constant
    SYSTEM_UUID_NAMESPACE: str = "f0e1c2d3-4567-89ab-cdef-fedcba987654"
    TEXTRACT_API_POLL_INTERVAL_SECONDS: int = 5
    TEXTRACT_API_JOB_TIMEOUT_SECONDS: int = 600

    # Leaving this here for reference
    # S3_BUCKET_NAME: str = "alpha-a2j-projects"
    # S3_PREFIX: str = "textract-test"

    # And this
    BEDROCK_EMBEDDING_MODEL_ID: str = "amazon.titan-embed-text-v2:0"


settings = Settings()
