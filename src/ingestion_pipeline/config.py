"""Configuration settings for the airflow pipeline."""

import math
import re
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
    OPENSEARCH_VERIFY_CERTS: bool = True
    OPENSEARCH_SSL_ASSERT_HOSTNAME: bool = True
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
    AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX: str = "26-711111"
    AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME: str = "Case1_TC19_50_pages_brain_injury.pdf"
    # Optional: comma-separated list of S3 keys (relative to the root bucket) to process as a batch,
    # e.g. "26-700030/case30.pdf,26-700029/case29.pdf". The case_ref is derived from each key's
    # leading folder. When set, this takes precedence over the single CASE_PREFIX/FILENAME above.
    SRC_S3_KEY: str = ""

    AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET: str = "mod-platform-sandbox-kta-documents-bucket"

    # -- Chunking Configuration --
    # The original strategy was "layout" based chunking, which uses Textract layout analysis to group text into chunks.
    # The "linear-sentence-splitter" strategy ignores layout
    # and simply splits text into chunks based on sentence boundaries and word counts.
    # The "textractor-word-stream" strategy chunks from Page.get_text_and_words()
    # so chunk text ordering aligns with Textractor's own linearized reading order.
    # This is still a work in progress and we are experimenting with these approaches,
    # but defaulting to "textractor-word-stream" for now as it looks to be the most promising.
    DOCUMENT_CHUNKING_STRATEGY: str = "textractor-word-stream"  # or "layout" or "linear-sentence-splitter"

    # review these values when we have a working system
    LAYOUT_CHUNKING_MAXIMUM_CHUNK_SIZE: int = 80  # maximum chunk size
    LAYOUT_CHUNKING_Y_TOLERANCE_RATIO: float = 0.5
    LAYOUT_CHUNKING_MAX_VERTICAL_GAP: float = 0.5
    LAYOUT_CHUNKING_LINE_CHUNK_CHAR_LIMIT: int = 300

    # -- Line-by-Line Sentence Chunker Configuration --
    # Word-based limits (not character-based)
    SENTENCE_CHUNKER_MIN_WORDS: int = 80
    SENTENCE_CHUNKER_MAX_WORDS: int = 120
    # Vertical gap threshold (relative to page height, 0.0-1.0)
    SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO: float = 0.05

    # -- Word Stream Chunker Configuration --
    # Dedicated settings for textractor-word-stream strategy.
    WORDSTREAM_CHUNKER_MIN_WORDS: int = 80
    WORDSTREAM_CHUNKER_MAX_WORDS: int = 120
    WORDSTREAM_CHUNKER_MAX_VERTICAL_GAP_RATIO: float = 0.05
    WORDSTREAM_CHUNKER_FORWARD_LOOKAHEAD_WORDS: int = 8
    WORDSTREAM_CHUNKER_BACKWARD_SCAN_WORDS: int = 20

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
    # Confgure via .env
    LOCAL_DEVELOPMENT_MODE: bool = False

    # -- Temp Development setting until MOD_PLATFORM is fully integrated --
    # That is MOD PLAT Textract can talk to CICA AWS resources
    # and we can point the Textract S3 output to the same bucket as the source documents
    # Confgure via .env
    USE_MOD_PLATFORM_MODE: bool = False

    LOG_LEVEL: str = "INFO"

    # -- Parallel Processing --
    # Maximum number of documents processed concurrently by the runner's thread pool.
    # The pipeline is IO/wait-bound (Textract polling, S3, Bedrock, OpenSearch), so
    # thread-based concurrency is effective here.
    #
    # NOTE: This is the single concurrency knob for the runner's thread pool. The SQS
    # spec referred to a separate ``SQS_MAX_CONCURRENCY``; we intentionally reuse this
    # existing setting instead of introducing a duplicate. Revisit when the SQS
    # concurrency story (parallel batch dispatch) is picked up.
    MAX_CONCURRENT_DOCUMENTS: int = 4

    # -- Drain loop --
    # Maximum number of batches a single run may START. A safety ceiling so a large backlog
    # cannot produce an unbounded run; remaining work is left for the next scheduled run.
    MAX_BATCHES_PER_RUN: int = 50

    # -- SQS Document Queue --
    # The SQS queue from which document-processing requests are consumed. Messages are
    # produced by an external system; the consumer reads them, processes each document,
    # and manages the message lifecycle (delete on success, redrive/DLQ on failure).
    SQS_DOCUMENT_QUEUE: str = "cica-document-search-queue"
    # Long-poll wait time for a receive request (seconds). SQS allows 0-20; a positive
    # value avoids busy-waiting by letting the receive block until a message arrives.
    SQS_POLL_WAIT_TIME_SECONDS: int = 20
    # Maximum messages requested per receive call. SQS allows 1-10.
    #
    # Kept in line with MAX_CONCURRENT_DOCUMENTS on purpose. The SQS visibility clock
    # starts for every received message at once, but only MAX_CONCURRENT_DOCUMENTS are
    # processed at a time; fetching many more than that leaves the surplus queued in the
    # thread pool with their visibility timers already running, inflating worst-case
    # message residence time and the risk of premature redelivery. Raise this only if
    # the visibility timeout is raised to match (and ideally once per-message visibility
    # heartbeats exist - see SQS_VISIBILITY_TIMEOUT_SECONDS).
    SQS_MAX_MESSAGES_PER_POLL: int = 4
    # Per-message visibility timeout (seconds): how long a received message is hidden
    # from other receives while it is being processed.
    #
    # This MUST cover the worst-case time a message spends received-but-not-yet-deleted:
    # the time it waits queued in the thread pool PLUS its own processing time. If it
    # expires first, SQS makes the message visible again and the document can be ingested
    # a second time. A single document's Textract step alone can run up to
    # TEXTRACT_API_JOB_TIMEOUT_SECONDS, so the default is set comfortably above that to
    # absorb pool queueing (batch size / worker count "waves") plus page processing,
    # embedding and indexing. A model validator enforces the lower bound.
    #
    # NOTE: a static timeout is a stop-gap. The robust fix is a per-message visibility
    # heartbeat (periodic ChangeMessageVisibility while a job is in flight), which
    # belongs with the concurrency/dispatch work (SQS stories 5/7) and is not in this
    # change.
    SQS_VISIBILITY_TIMEOUT_SECONDS: int = 1800
    # Multiplier applied to TEXTRACT_API_JOB_TIMEOUT_SECONDS when computing the minimum
    # acceptable visibility timeout, to account for a document's non-Textract processing
    # (chunking, page-image upload, embedding, two indexing calls) that also runs before
    # the message is deleted. Textract dominates wall-clock time, but it is not the whole
    # story, so the enforced per-wave cost is TEXTRACT_API_JOB_TIMEOUT_SECONDS * this
    # factor. This is a coarse, configurable estimate; the exact non-Textract time is not
    # modelled anywhere, which is why a visibility heartbeat (stories 5/7) is the real
    # fix. Must be >= 1.0 (1.0 = no headroom, Textract-only).
    SQS_PROCESSING_OVERHEAD_FACTOR: float = 1.5

    # -- SQS DLQ / redrive --
    # Number of times a message may be received without being deleted before SQS redrives it
    # to the DLQ. Mirrors the RedrivePolicy maxReceiveCount used by the init script / IaC.
    SQS_MAX_RECEIVE_COUNT: int = 3

    # The DLQ queue name. Empty by default; the derived value "<SQS_DOCUMENT_QUEUE>-dlq" is
    # filled in by a model validator so it always tracks the main queue name unless overridden.
    SQS_DOCUMENT_DLQ: str = ""

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

    @field_validator(
        "LAYOUT_CHUNKING_MAXIMUM_CHUNK_SIZE",
        "LAYOUT_CHUNKING_LINE_CHUNK_CHAR_LIMIT",
        "SENTENCE_CHUNKER_MIN_WORDS",
        "SENTENCE_CHUNKER_MAX_WORDS",
        "WORDSTREAM_CHUNKER_MIN_WORDS",
        "WORDSTREAM_CHUNKER_MAX_WORDS",
        "WORDSTREAM_CHUNKER_FORWARD_LOOKAHEAD_WORDS",
        "WORDSTREAM_CHUNKER_BACKWARD_SCAN_WORDS",
        "MAX_CONCURRENT_DOCUMENTS",
    )
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
            raise ValueError("Value must be a positive integer")
        return v

    @field_validator(
        "LAYOUT_CHUNKING_Y_TOLERANCE_RATIO",
        "SENTENCE_CHUNKER_MAX_VERTICAL_GAP_RATIO",
        "WORDSTREAM_CHUNKER_MAX_VERTICAL_GAP_RATIO",
    )
    @classmethod
    def validate_ratio(cls, v: float, info) -> float:
        """Ensure ratio is between 0.0 and 1.0.

        Args:
            v (float): The ratio value to validate.
            info: Pydantic validation info containing field name.

        Returns:
            float: The validated ratio.

        Raises:
            ValueError: If the ratio is not between 0.0 and 1.0.
        """
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"{info.field_name} must be between 0.0 and 1.0")
        return v

    @field_validator("LAYOUT_CHUNKING_MAX_VERTICAL_GAP")
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
            raise ValueError("LAYOUT_CHUNKING_MAX_VERTICAL_GAP must be a positive number")
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

    @field_validator("SQS_PROCESSING_OVERHEAD_FACTOR")
    @classmethod
    def validate_sqs_processing_overhead_factor(cls, v: float) -> float:
        """Ensure the processing-overhead factor adds headroom rather than removing it.

        A factor below 1.0 would make the enforced visibility bound smaller than the
        Textract time alone, which is never correct. 1.0 means no non-Textract headroom.

        Args:
            v (float): The configured overhead factor.

        Returns:
            float: The validated factor.

        Raises:
            ValueError: If the factor is less than 1.0.
        """
        if v < 1.0:
            raise ValueError("SQS_PROCESSING_OVERHEAD_FACTOR must be >= 1.0")
        return v

    @field_validator("SQS_DOCUMENT_QUEUE")
    @classmethod
    def validate_sqs_document_queue(cls, v: str) -> str:
        """Ensure the SQS queue name is valid so bad config fails at startup.

        AWS standard SQS queue names are 1-80 characters of alphanumerics, hyphens and
        underscores. Validating here means an empty, whitespace-only, overlong, or
        otherwise invalid name fails during settings construction rather than only when
        the first AWS call is made. Surrounding whitespace is stripped first.

        Args:
            v (str): The configured queue name.

        Returns:
            str: The validated (stripped) queue name.

        Raises:
            ValueError: If the name is empty or does not match the SQS naming rules.
        """
        stripped = v.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", stripped):
            raise ValueError("SQS_DOCUMENT_QUEUE must be 1-80 characters of letters, digits, hyphens or underscores")
        return stripped

    @field_validator("SQS_POLL_WAIT_TIME_SECONDS")
    @classmethod
    def validate_sqs_poll_wait_time(cls, v: int) -> int:
        """Ensure the SQS long-poll wait time is within the SQS-permitted range.

        Args:
            v (int): The long-poll wait time in seconds.

        Returns:
            int: The validated wait time.

        Raises:
            ValueError: If the value is outside the inclusive range 0 to 20.
        """
        if not 0 <= v <= 20:
            raise ValueError("SQS_POLL_WAIT_TIME_SECONDS must be between 0 and 20 inclusive")
        return v

    @field_validator("SQS_MAX_MESSAGES_PER_POLL")
    @classmethod
    def validate_sqs_max_messages_per_poll(cls, v: int) -> int:
        """Ensure the SQS max-messages-per-poll is within the SQS-permitted range.

        Args:
            v (int): The maximum number of messages requested per receive call.

        Returns:
            int: The validated maximum.

        Raises:
            ValueError: If the value is outside the inclusive range 1 to 10.
        """
        if not 1 <= v <= 10:
            raise ValueError("SQS_MAX_MESSAGES_PER_POLL must be between 1 and 10 inclusive")
        return v

    @field_validator("SQS_VISIBILITY_TIMEOUT_SECONDS")
    @classmethod
    def validate_sqs_visibility_timeout(cls, v: int) -> int:
        """Ensure the SQS visibility timeout is within the SQS-permitted range.

        SQS accepts a per-message visibility timeout from 0 to 43200 seconds (12 hours);
        values above that are rejected at ``ReceiveMessage`` time with
        ``InvalidParameterValue``. We require a positive value (a zero timeout would make
        a message immediately visible again) up to the service maximum, so bad
        configuration fails at startup rather than on the first poll. The lower bound is
        further constrained by :meth:`validate_visibility_covers_processing`.

        Args:
            v (int): The visibility timeout in seconds.

        Returns:
            int: The validated visibility timeout.

        Raises:
            ValueError: If the value is outside the range 1 to 43200 inclusive.
        """
        if not 1 <= v <= 43200:
            raise ValueError("SQS_VISIBILITY_TIMEOUT_SECONDS must be between 1 and 43200 inclusive")
        return v

    @field_validator("SQS_MAX_RECEIVE_COUNT")
    @classmethod
    def validate_sqs_max_receive_count(cls, v: int) -> int:
        """Ensure the DLQ max receive count is at least 1 so redrive can ever trigger.

        Args:
            v (int): The configured maximum receive count before redrive to the DLQ.

        Returns:
            int: The validated maximum receive count.

        Raises:
            ValueError: If the value is less than 1.
        """
        if v < 1:
            raise ValueError("SQS_MAX_RECEIVE_COUNT must be >= 1")
        return v

    @field_validator("MAX_BATCHES_PER_RUN")
    @classmethod
    def validate_max_batches_per_run(cls, v: int) -> int:
        """Ensure at least one batch can be started per run.

        Args:
            v (int): The configured maximum number of batches a single run may start.

        Returns:
            int: The validated maximum number of batches per run.

        Raises:
            ValueError: If the value is less than 1.
        """
        if v < 1:
            raise ValueError("MAX_BATCHES_PER_RUN must be >= 1")
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

    @model_validator(mode="after")
    def validate_visibility_covers_processing(self) -> "Settings":
        """Ensure the SQS visibility timeout covers worst-case message residence.

        A message stays hidden only for SQS_VISIBILITY_TIMEOUT_SECONDS. If that expires
        before the message is deleted, SQS makes it visible again and the document can be
        ingested a second time. The worst case is the message dispatched last in a batch:
        with more messages per poll than concurrent workers, it waits through
        ``ceil(SQS_MAX_MESSAGES_PER_POLL / MAX_CONCURRENT_DOCUMENTS)`` processing "waves",
        each of which can take up to TEXTRACT_API_JOB_TIMEOUT_SECONDS (Textract alone),
        before it is deleted. The visibility timeout must cover that whole residence, so
        the enforced lower bound is::

            ceil(batch_size / concurrency) * TEXTRACT_API_JOB_TIMEOUT_SECONDS

        Each wave's cost is not just the Textract timeout: after Textract returns, the
        document is still chunked, its page images uploaded, every chunk embedded, and
        two indexing calls made before the message is deleted. That non-Textract time is
        not modelled by any single setting, so SQS_PROCESSING_OVERHEAD_FACTOR applies a
        coarse multiplier to approximate it, making the per-wave cost
        ``TEXTRACT_API_JOB_TIMEOUT_SECONDS * SQS_PROCESSING_OVERHEAD_FACTOR``. This is
        still an estimate; a per-message visibility heartbeat (ChangeMessageVisibility
        while queued/in flight) is the robust fix and belongs with the
        concurrency/dispatch work (SQS stories 5/7).

        Returns:
            Settings: The validated settings object.

        Raises:
            ValueError: If the visibility timeout is below the worst-case residence bound.
        """
        waves = math.ceil(self.SQS_MAX_MESSAGES_PER_POLL / self.MAX_CONCURRENT_DOCUMENTS)
        per_document_cost = self.TEXTRACT_API_JOB_TIMEOUT_SECONDS * self.SQS_PROCESSING_OVERHEAD_FACTOR
        minimum_visibility = math.ceil(waves * per_document_cost)
        if self.SQS_VISIBILITY_TIMEOUT_SECONDS < minimum_visibility:
            raise ValueError(
                f"SQS_VISIBILITY_TIMEOUT_SECONDS ({self.SQS_VISIBILITY_TIMEOUT_SECONDS}) must be at least "
                f"{minimum_visibility} = ceil(ceil(SQS_MAX_MESSAGES_PER_POLL ({self.SQS_MAX_MESSAGES_PER_POLL}) / "
                f"MAX_CONCURRENT_DOCUMENTS ({self.MAX_CONCURRENT_DOCUMENTS})) * TEXTRACT_API_JOB_TIMEOUT_SECONDS "
                f"({self.TEXTRACT_API_JOB_TIMEOUT_SECONDS}) * SQS_PROCESSING_OVERHEAD_FACTOR "
                f"({self.SQS_PROCESSING_OVERHEAD_FACTOR})), so a received message stays hidden for at least the "
                "worst-case time it can spend queued behind other jobs plus its own full (Textract + "
                "chunking/embedding/indexing) processing."
            )
        return self

    @model_validator(mode="after")
    def validate_sentence_chunker_word_limits(self) -> "Settings":
        """Ensure min_words < max_words for sentence chunker.

        Returns:
            Settings: The validated settings object.

        Raises:
            ValueError: If min_words >= max_words.
        """
        if self.SENTENCE_CHUNKER_MIN_WORDS >= self.SENTENCE_CHUNKER_MAX_WORDS:
            raise ValueError(
                f"SENTENCE_CHUNKER_MIN_WORDS ({self.SENTENCE_CHUNKER_MIN_WORDS}) must be less than "
                f"SENTENCE_CHUNKER_MAX_WORDS ({self.SENTENCE_CHUNKER_MAX_WORDS})"
            )
        return self

    @model_validator(mode="after")
    def validate_wordstream_chunker_word_limits(self) -> "Settings":
        """Ensure min_words < max_words for word-stream chunker."""
        if self.WORDSTREAM_CHUNKER_MIN_WORDS >= self.WORDSTREAM_CHUNKER_MAX_WORDS:
            raise ValueError(
                f"WORDSTREAM_CHUNKER_MIN_WORDS ({self.WORDSTREAM_CHUNKER_MIN_WORDS}) must be less than "
                f"WORDSTREAM_CHUNKER_MAX_WORDS ({self.WORDSTREAM_CHUNKER_MAX_WORDS})"
            )
        return self

    @model_validator(mode="after")
    def derive_sqs_document_dlq(self) -> "Settings":
        """Default the DLQ name to ``<SQS_DOCUMENT_QUEUE>-dlq`` when left unset.

        A field default cannot reference another field, so the derived name is filled in
        here after ``SQS_DOCUMENT_QUEUE`` has been validated and stripped. An explicit
        ``SQS_DOCUMENT_DLQ`` (env/.env) is preserved.

        Returns:
            Settings: The validated settings object.
        """
        if not self.SQS_DOCUMENT_DLQ:
            self.SQS_DOCUMENT_DLQ = f"{self.SQS_DOCUMENT_QUEUE}-dlq"
        return self


settings = Settings()
