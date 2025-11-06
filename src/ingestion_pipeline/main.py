"""Main entry point for the ingestion pipeline."""

import logging

from ingestion_pipeline.custom_logging.log_context import setup_logging, source_doc_id_context

setup_logging()
log = logging.getLogger(__name__)
source_doc_id_context.set("91c8ac49-2d20-5b35-b3f9-4563c8553a33")
log.info("Running........")
