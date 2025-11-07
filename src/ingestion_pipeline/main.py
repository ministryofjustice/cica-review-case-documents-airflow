"""Main entry point for the ingestion pipeline."""

import logging

from ingestion_pipeline.custom_logging.log_context import setup_logging

setup_logging()
log = logging.getLogger(__name__)

log.info("Running........")
