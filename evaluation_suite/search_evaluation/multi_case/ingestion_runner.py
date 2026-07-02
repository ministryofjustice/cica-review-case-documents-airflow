"""Subprocess entry point for evaluation ingestion with Textract response caching.

Patches :class:`~ingestion_pipeline.textract.textract_processor.TextractProcessor`
**before** the production pipeline is imported, so every
``TextractProcessor.process_document`` call in this process reads from the
local JSON cache when available rather than starting a new AWS Textract job.

Used by :func:`~evaluation_suite.search_evaluation.multi_case.multi_case_bootstrap._ingest_case_subprocess`
instead of calling ``ingestion_pipeline.runner`` directly.
"""

from evaluation_suite.search_evaluation.multi_case.textract_cache import install_cache

# Patch the TextractProcessor class methods BEFORE ingestion_pipeline is imported
# so every instance created in this process uses the local response cache.
install_cache()

if __name__ == "__main__":
    from ingestion_pipeline.runner import main

    main()
