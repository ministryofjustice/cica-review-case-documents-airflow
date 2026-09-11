# Requirements — Parallel Document Processing

## Overview

The ingestion pipeline previously processed a single, hardcoded document per run
(`runner.py` built one `S3_DOCUMENT_URI` from settings and called
`pipeline.process_document` once). This feature transforms the runner to process
**multiple documents concurrently**, sourced through a stubbed SQS-batch interface
that anticipates the production queue integration.

Because the pipeline is overwhelmingly IO/wait-bound (Textract polling can block up
to 600s per document, plus S3, Bedrock, and OpenSearch calls), thread-based
concurrency is the appropriate mechanism.

The word-stream chunker (`textractor-word-stream`) is the only chunking strategy
going forward; the design accounts for this but does not require removing the other
strategies as part of this feature.

## Requirements

### Requirement 1 — Process a batch of documents concurrently

**User story:** As an operator of the ingestion pipeline, I want a batch of
documents to be processed in parallel, so that throughput scales beyond one
document per run.

#### Acceptance criteria

1. WHEN the runner starts THEN it SHALL obtain a batch of documents from a document
   source rather than a single hardcoded URI.
2. WHEN a batch contains multiple documents THEN the runner SHALL process them using
   a thread pool with a configurable maximum concurrency.
3. WHEN the configured maximum concurrency exceeds the batch size THEN the number of
   workers SHALL be capped at the batch size.
4. WHEN the batch is empty THEN the runner SHALL log that there is nothing to process
   and complete without error.

### Requirement 2 — Per-document error isolation

**User story:** As an operator, I want one failing document not to abort the rest of
the batch, so that a single bad document does not block others.

#### Acceptance criteria

1. WHEN a single document fails during processing THEN the runner SHALL contain the
   error, log it with traceback metadata, and continue processing the remaining
   documents.
2. WHEN a document's S3 URI is invalid THEN it SHALL be treated as a failed document
   (not raised) and reported in the batch result.
3. WHEN the batch completes THEN the runner SHALL log a summary of how many documents
   succeeded and how many failed.
4. WHEN a document is processed successfully THEN the runner SHALL acknowledge it back
   to the document source; failed documents SHALL NOT be acknowledged.

### Requirement 3 — Correct per-document log attribution across threads

**User story:** As an operator reading logs, I want each log line attributed to the
correct document, so that concurrent processing does not produce mislabeled logs.

#### Acceptance criteria

1. WHEN a document is processed in a worker thread THEN the `source_doc_id` logging
   context SHALL be set within that thread for the duration of processing.
2. WHEN a document finishes processing (success or failure) THEN the logging context
   SHALL be reset so no value leaks to subsequent work on that thread.

### Requirement 4 — Thread-safe shared pipeline

**User story:** As a developer, I want the pipeline and its clients to be safe to
share across worker threads, so that parallel processing does not corrupt shared
state.

#### Acceptance criteria

1. WHEN multiple documents are processed concurrently by a single shared `Pipeline`
   instance THEN no per-document mutable state SHALL be shared between threads.
2. WHEN the page processor runs concurrently for different documents THEN its
   image-upload tracking used for cleanup SHALL be local to each call.
3. WHEN AWS and OpenSearch clients are constructed THEN construction SHALL NOT rely on
   process-wide mutable state (e.g. environment variables), so construction is safe
   from any thread.

### Requirement 5 — Stubbed SQS-batch document source

**User story:** As a developer, I want a document-source abstraction shaped like the
future SQS integration, so that the real queue can be dropped in with minimal change.

#### Acceptance criteria

1. THE document source SHALL expose a way to fetch a batch of documents and a way to
   acknowledge a successfully processed document.
2. THE stub implementation SHALL synthesise a batch from configuration so the parallel
   runner is exercisable end-to-end without a live queue.
3. THE document unit of work SHALL carry the natural-key metadata required to build
   `DocumentMetadata` and generate the deterministic `source_doc_id`, plus an opaque
   handle for message acknowledgement.
4. THE stub SHALL include clear markers indicating where real SQS receive/delete calls
   belong.

### Requirement 6 — Configurable concurrency

**User story:** As an operator, I want to configure how many documents process at
once, so that I can tune throughput against downstream limits.

#### Acceptance criteria

1. THE system SHALL provide a `MAX_CONCURRENT_DOCUMENTS` setting via the existing
   pydantic-settings configuration.
2. THE setting SHALL be validated as a positive integer.

### Requirement 7 — Quality gates

#### Acceptance criteria

1. THE full test suite SHALL pass.
2. THE test coverage SHALL remain at or above the enforced 90% threshold.
3. THE code SHALL pass `ruff` lint and format checks.
