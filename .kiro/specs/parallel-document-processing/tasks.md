# Implementation Plan — Parallel Document Processing

All tasks below are complete. The full suite passes (583 tests), coverage is 92.89%
(≥90% gate), and `ruff` lint + format are clean.

- [x] 1. Make `PageProcessor` thread-safe
  - Removed the `self.uploaded_results` instance attribute; `process()` now uses a
    local `uploaded_results` list so a single instance is safe to share across threads.
  - _Requirements: 4.1, 4.2_
  - _Files: `src/ingestion_pipeline/page_processor/processor.py`_

- [x] 2. Add the stubbed SQS-batch document source
  - New `orchestration/document_source.py` with `DocumentJob` (frozen model +
    `source_file_name` property + `receipt_handle`), `DocumentSource` protocol
    (`fetch_batch`/`acknowledge`), and `SqsDocumentSource` stub that synthesises a
    batch from settings, with TODOs marking where real `sqs.receive_message` /
    `sqs.delete_message` calls belong.
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Files: `src/ingestion_pipeline/orchestration/document_source.py`_

- [x] 3. Add `MAX_CONCURRENT_DOCUMENTS` configuration
  - Added `MAX_CONCURRENT_DOCUMENTS: int = 4` to `Settings`, included in the existing
    positive-integer validator.
  - _Requirements: 6.1, 6.2_
  - _Files: `src/ingestion_pipeline/config.py`_

- [x] 4. Transform the runner into a parallel batch runner
  - Build the pipeline once and share it; fetch a batch from the document source; run a
    `ThreadPoolExecutor` sized `min(MAX_CONCURRENT_DOCUMENTS, len(jobs))`.
  - `process_document_job` worker sets/resets `source_doc_id_context` per thread, builds
    metadata, validates the URI, runs the pipeline, and contains errors into a
    `DocumentResult`.
  - Acknowledge only successful jobs; log a success/failure summary. Retained
    `extract_case_ref` / `validate_s3_uri`.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2_
  - _Files: `src/ingestion_pipeline/runner.py`_

- [x] 5. Make Textractor construction thread-safe (remove env-var race)
  - Replaced the `os.environ` credential mutation in `get_textractor_instance()` with an
    explicitly-credentialed `boto3.Session` whose Textract/S3 clients are injected into
    the `Textractor` instance. Removed the now-unused `import os`.
  - _Requirements: 4.3_
  - _Files: `src/ingestion_pipeline/aws_client/clients.py`_

- [x] 6. Tests and verification
  - Rewrote `tests/test_runner.py` for the worker/batch/main shape; added
    `tests/orchestration/test_document_source.py`; updated
    `tests/page_processor/test_processor.py` for local `uploaded_results`; replaced the
    env-var tests in `tests/aws_client/test_clients.py` with explicit-session-credential
    and no-environment-mutation assertions.
  - Verified: full `pytest` suite green (583 passed), coverage 92.89%, `ruff` clean.
  - _Requirements: 7.1, 7.2, 7.3_
  - _Files: `tests/test_runner.py`, `tests/orchestration/test_document_source.py`,
    `tests/page_processor/test_processor.py`, `tests/aws_client/test_clients.py`_

## Follow-up (not part of this feature)

- [ ] Remove the unused `layout` and `linear-sentence-splitter` chunking strategies and
      related config, tightening `ALLOWED_CHUNKER_TYPES` to `{"textractor-word-stream"}`.
      Prerequisite: relocate `SentenceDetector` (currently imported by the word-stream
      chunker from the `line_sentence` package) before deleting that package.
