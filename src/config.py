from pydantic_settings import BaseSettings, SettingsConfigDict

# Order of priority
# Pydantic performs the following steps to determine the final value for each attribute:
# Arguments to the Initializer (Highest Priority): If you pass values directly when creating the object
# (e.g., Settings(OPENSEARCH_PORT=1234)), these would take precedence over everything else.

# System Environment Variables: Pydantic will then look for environment variables set in your operating system's shell.
# For example, running export OPENSEARCH_PORT=5000 in a terminal before running the script,
# would use that value.

# .env File Values: Next, because you've specified env_file=".env" in your model_config,
# Pydantic reads the .env file. If OPENSEARCH_PORT=0 is set in that file,
# it will override the default value from the class definition.

# Default Values in the Class (Lowest Priority): Finally, if a value isn't found in any of the sources above,
# Pydantic uses the default value defined directly in the class. For OPENSEARCH_PORT, this would be 9200.


class Settings(BaseSettings):  # type: ignore
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    # -- OpenSearch client --
    OPENSEARCH_HOST: str = "localhost"
    OPENSEARCH_URL_PREFIX: str = "/opensearch/eu-west-2/case-document-search-domain"
    OPENSEARCH_PORT: int = 9200
    OPENSEARCH_USERNAME: str = "admin"
    OPENSEARCH_PASSWORD: str = "really-secure-passwordAa!1"
    OPENSEARCH_CHUNK_INDEX_NAME: str = "case-documents"
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
    CHUNK_INDEX_UUID_NAMESPACE: str = "f0e1c2d3-4567-89ab-cdef-fedcba987654"
    TEXTRACT_API_POLL_INTERVAL_SECONDS: int = 5
    TEXTRACT_API_JOB_TIMEOUT_SECONDS: int = 600

    # Leaving this here for reference
    # S3_BUCKET_NAME: str = "alpha-a2j-projects"
    # S3_PREFIX: str = "textract-test"

    # And this
    # POLL_INTERVAL_SECONDS: int = 5  # for checking Textract job status
    # BEDROCK_TOKENIZER_NAME: str = "cl100k_base"
    # BEDROCK_CHUNK_SIZE: int = 300  # 100 tokens ~ 75 words (1 token ~ (3/4) words)
    # BEDROCK_EMBEDDING_MODEL_ID: str = "amazon.titan-embed-text-v2:0"


settings = Settings()
