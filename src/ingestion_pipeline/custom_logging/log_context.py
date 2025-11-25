"""Custom logging context to include source document IDs in log messages."""

import logging
from contextvars import ContextVar
from typing import Optional

from ingestion_pipeline.config import settings

# Store the current source document id in a context variable.
# ContextVar is context-safe.
source_doc_id_context: ContextVar[Optional[str]] = ContextVar("source_doc_id", default=None)


class ContextFilter(logging.Filter):
    """Injects source_doc_id into log records if present."""

    def filter(self, record):
        """Injects source_doc_id into log records if present.

        Args:
            record (logging.LogRecord): The log record to modify.

        Returns:
            bool: Always returns True.
        """
        source_doc_id = source_doc_id_context.get()
        if source_doc_id:
            record.msg = f"{source_doc_id} {record.msg}"
        return True


def setup_logging():
    """Call this once at app startup."""
    # Get root logger
    root_logger = logging.getLogger()

    # Clear any existing handlers (prevents duplicates)
    root_logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler()

    # Set format
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)

    # Add filter to handler
    handler.addFilter(ContextFilter())

    # Configure root logger
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.LOG_LEVEL)
