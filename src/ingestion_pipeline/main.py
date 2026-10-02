"""Main entry point for the ingestion pipeline.

NOTE (project paused): this module currently only configures logging and exits. The
long-lived SQS polling worker lives in ``ingestion_pipeline.runner.main`` and is NOT
started here, so the Docker image (whose entrypoint runs this file) does not run the
worker. When the service is re-homed on the Cloud Platform or Modernisation Platform,
wire the container entrypoint to ``runner.main`` (or have this module delegate to it).
See the README and runbooks/RUNBOOK.md for the migration status.
"""

import logging

from ingestion_pipeline.custom_logging.log_context import setup_logging

setup_logging()
log = logging.getLogger(__name__)

log.info("Running........")
