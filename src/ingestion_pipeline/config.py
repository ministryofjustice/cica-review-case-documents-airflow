"""Configuration settings for the airflow pipeline."""

from pathlib import Path

from pydantic import field_validator, model_validator
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
    """Configuration settings for the ingestion pipeline.

    Loads settings from environment variables and .env file (if present in local development).
    Priority order: CLI args > Environment variables > .env file > Default values.

    Attributes:
        OPENSEARCH_PROXY_URL: OpenSearch endpoint URL for document indexing.
        AWS_REGION: AWS region for all AWS service clients.
        DEBUG_PAGE_NUMBERS: Set of page numbers to enable detailed debug logging for.
        LOCAL_DEVELOPMENT_MODE: Flag to enable local development features (LocalStack, URI remapping).
    """

    model_config = SettingsConfigDict(
        # Only load .env if it exists (local dev)
        env_file=str(ENV_FILE_PATH) if ENV_FILE_PATH.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    # -- OpenSearch client --
    # Example (k8s):
    #   OPENSEARCH_PROXY_URL="http://opensearch-proxy-service.namespace.svc.cluster.local:8080"
    # Example (localstack):
    #   OPENSEARCH_PROXY_URL="http://localhost:9200"
    OPENSEARCH_PROXY_URL: str = "http://localhost:9200"
    OPENSEARCH_CHUNK_INDEX_NAME: str = "page_chunks"
    OPENSEARCH_PAGE_METADATA_INDEX_NAME: str = "page_metadata"

    # -- GLOBAL AWS CONFIGURATION --
    AWS_REGION: str = "eu-west-2"

    # -- AWS TEXTRACT --
    AWS_MOD_PLATFORM_ACCESS_KEY_ID: str = "test"
    AWS_MOD_PLATFORM_SECRET_ACCESS_KEY: str = "test"
    AWS_MOD_PLATFORM_SESSION_TOKEN: str = "test"

    # -- AWS S3 PAGE BUCKET --
    AWS_CICA_S3_PAGE_BUCKET_URI: str = "s3://document-page-bucket"
    AWS_CICA_S3_PAGE_BUCKET: str = "document-page-bucket"
    AWS_CICA_AWS_ACCESS_KEY_ID: str = "test"
    AWS_CICA_AWS_SECRET_ACCESS_KEY: str = "test"
    AWS_CICA_AWS_SESSION_TOKEN: str = "test"

    # -- SOURCE DOCUMENT BUCKET --
    AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET: str = "local-kta-documents-bucket"

    AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET: str = "mod-platfform-sandbox-kta-documents-bucket"

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
    # In case we want to use these buckets
    # TODO we should probably delete this textract-test bucket later
    # S3_BUCKET_NAME: str = "alpha-a2j-projects"
    # S3_PREFIX: str = "textract-test"

    BEDROCK_EMBEDDING_MODEL_ID: str = "amazon.titan-embed-text-v2:0"

    # -- Local Development Mode --
    # Confgure via .env or environment variable
    LOCAL_DEVELOPMENT_MODE: bool = False

    LOG_LEVEL: str = "INFO"

    DEBUG_PAGE_NUMBERS: set[int] = {1}

    @field_validator("DEBUG_PAGE_NUMBERS")
    @classmethod
    def validate_debug_page_numbers(cls, v: set[int]) -> set[int]:
        """Ensure all debug page numbers are positive integers (>= 1).

        Args:
            v (set[int]): The set of page numbers to validate.

        Returns:
            set[int]: The validated set of page numbers.

        Raises:
            ValueError: If any page number is less than 1.
        """
        if any(page < 1 for page in v):
            raise ValueError("All page numbers in DEBUG_PAGE_NUMBERS must be >= 1")
        return v

    @field_validator("MAXIMUM_CHUNK_SIZE", "LINE_CHUNK_CHAR_LIMIT")
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        """Ensure chunk size values are positive integers.

        Args:
            v (int): The value to validate.

        Returns:
            int: The validated value.

        Raises:
            ValueError: If the value is not positive.
        """
        if v <= 0:
            raise ValueError("Chunk size must be a positive integer")
        return v

    @field_validator("Y_TOLERANCE_RATIO")
    @classmethod
    def validate_ratio(cls, v: float) -> float:
        """Ensure ratio is between 0.0 and 1.0.

        Args:
            v (float): The ratio value to validate.

        Returns:
            float: The validated ratio.

        Raises:
            ValueError: If the ratio is not between 0.0 and 1.0.
        """
        if not 0.0 <= v <= 1.0:
            raise ValueError("Y_TOLERANCE_RATIO must be between 0.0 and 1.0")
        return v

    @field_validator("MAX_VERTICAL_GAP")
    @classmethod
    def validate_positive_float(cls, v: float) -> float:
        """Ensure gap value is positive.

        Args:
            v (float): The gap value to validate.

        Returns:
            float: The validated gap value.

        Raises:
            ValueError: If the value is not positive.
        """
        if v <= 0.0:
            raise ValueError("MAX_VERTICAL_GAP must be a positive number")
        return v

    @field_validator("TEXTRACT_API_POLL_INTERVAL_SECONDS")
    @classmethod
    def validate_poll_interval(cls, v: int) -> int:
        """Ensure poll interval is positive.

        Args:
            v (int): The poll interval to validate.

        Returns:
            int: The validated poll interval.

        Raises:
            ValueError: If the value is not positive.
        """
        if v <= 0:
            raise ValueError("TEXTRACT_API_POLL_INTERVAL_SECONDS must be a positive integer")
        return v

    @model_validator(mode="after")
    def validate_timeout_greater_than_poll(self) -> "Settings":
        """Ensure timeout is greater than poll interval.

        Returns:
            Settings: The validated settings object.

        Raises:
            ValueError: If timeout is not greater than poll interval.
        """
        if self.TEXTRACT_API_JOB_TIMEOUT_SECONDS <= self.TEXTRACT_API_POLL_INTERVAL_SECONDS:
            raise ValueError("TEXTRACT_API_JOB_TIMEOUT_SECONDS must be greater than TEXTRACT_API_POLL_INTERVAL_SECONDS")
        return self


settings = Settings()
