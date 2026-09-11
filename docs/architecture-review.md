# Architecture & Application Review

A review of the CICA Review Case Documents Airflow ingestion pipeline covering
pipeline orchestration, module boundaries, configuration, AWS integration,
containerisation, and CI/CD.

> **Status:** The system is being built up and out. This review separates
> **Issues** (present in the code today and worth fixing on their own merits)
> from **Planned Work** (items that resolve as the build progresses toward the
> target design — see `infrastructure-review.md`). Infrastructure/deployment
> topology is covered in `infrastructure-review.md`; this document focuses on the
> application code.

## Overall Architecture

The pipeline is a well-structured single-document ingestion flow centred on a
clean composition root (`pipeline_builder.build_pipeline()`) that wires
dependencies into a coordinating `Pipeline` orchestrator.

Stages:

1. Textract OCR
2. Page processing (image render + S3 upload)
3. Chunking (strategy-selected)
4. Embedding generation (Bedrock)
5. OpenSearch indexing

Compensating cleanup runs on failure. The layering is sound: stage classes
receive dependencies via constructor injection, chunking uses a strategy pattern
with per-strategy config objects, and data flows through well-defined pydantic
models (`DocumentMetadata` -> `DocumentPage` / `ProcessedDocument`).

## What's Working Well

- **Composition root with DI.** `build_pipeline()` constructs everything in one
  place and injects into `Pipeline`. Stages are decoupled and unit-testable.
- **Strategy pattern for chunking.** Three interchangeable chunkers behind a
  `ChunkStrategy` ABC, each with a `from_settings()` classmethod bridging the
  global config to a strategy-local config. Strategies are not bound to the full
  `Settings` object, keeping them isolated and testable.
- **Deterministic UUIDs.** `DocumentIdentifier` uses uuid5 over a fixed
  namespace, giving idempotent re-ingestion (same doc -> same IDs -> overwrite
  rather than duplicate).
- **Compensating cleanup.** Both page upload and indexing delete partial work on
  failure. The indexer deletes existing docs by `source_doc_id` before
  reindexing, so retries are safe.
- **Robust config validation.** Extensive pydantic `@field_validator`s (positive
  ints, 0-1 ratios, min<max word bounds) catch misconfiguration at startup.
- **Structured logging with context.** A `ContextVar` injects `source_doc_id`
  into every log line, aiding tracing of a document through the pipeline.
- **Hardened container and CI.** The Dockerfile runs as non-root, pins the base
  image and `uv` by digest, removes `uv` from the runtime image, and bundles only
  `src/ingestion_pipeline`. CI pins actions by SHA, uses least-privilege
  permissions, and the MoJ shared workflows cover Grype scanning, CodeQL,
  dependency review, and container structure tests.

## Issues

These are present in the code today and are worth addressing on their own merits,
independent of the infrastructure roadmap.

### 1. Inconsistent AWS client construction

S3 and Textract clients are built via factory functions and injected at the
composition root (good). But Bedrock (`EmbeddingGenerator.__init__`) and
OpenSearch (`OpenSearchIndexer.__init__`) construct their clients inline. This
breaks the DI pattern, makes those clients harder to mock, and scatters
credential handling.

- **Impact:** Reduced testability and inconsistent patterns.
- **Fix:** Move Bedrock and OpenSearch client creation into `aws_client/`
  factories and inject them.
- **Note:** Chunk embedding is planned to move out of the pipeline entirely, to
  the OpenSearch Bedrock connector on CP (embedding at index time), which would
  remove `EmbeddingGenerator` from the ingestion path — see
  `infrastructure-review.md`, Planned Work item 7. OpenSearch client construction
  will also change with the connectivity work. Given that, prioritise unifying
  the OpenSearch client construction; the Bedrock client may simply be deleted
  rather than refactored.
- **Files:** `src/ingestion_pipeline/embedding/embedding_generator.py`,
  `src/ingestion_pipeline/indexing/indexer.py`,
  `src/ingestion_pipeline/aws_client/clients.py`

### 2. Structure docs vs reality drift

`data_models/` is effectively empty and `date_extraction/` contains only
`__pycache__` with no source, yet both are documented as modules. The real
shared models live in `chunking/schemas.py`. The `s3_file_downloader/` module is
documented but the active download path is
`page_processor/s3_document_service.py`. Placing the core data models under
`chunking/` is also a slight smell given they are used across all stages.

- **Impact:** Misleads newcomers; structure documentation is inaccurate.
- **Fix:** Remove the dead directories or update the structure documentation.
  Consider relocating shared models out of `chunking/`.
- **Files:** `src/ingestion_pipeline/data_models/`,
  `src/ingestion_pipeline/date_extraction/`,
  `src/ingestion_pipeline/s3_file_downloader/`,
  `src/ingestion_pipeline/chunking/schemas.py`

### 3. Python version mismatch between CI and the pinned runtime

The tech stack pins Python 3.12 (`.python-version`), but `test.yml` sets up
Python 3.13. Tests run against a different minor version than production, which
can mask version-specific behaviour.

- **Impact:** Tests may not reflect production runtime behaviour.
- **Fix:** Align CI to Python 3.12.
- **Files:** `.github/workflows/test.yml`, `.python-version`

## Planned Work

These reflect the in-progress build toward the target design. They are expected
gaps rather than defects, captured here so they are not lost. The infrastructure
counterparts are tracked in `infrastructure-review.md`.

### 4. Entrypoint wiring: `main.py` does not yet run the pipeline

The Dockerfile's `CMD` is `python src/ingestion_pipeline/main.py`, but `main.py`
only sets up logging and logs `"Running........"`. The functional orchestration
lives in `runner.py::main()` under an `if __name__ == "__main__"` guard, which is
currently the single-document test harness.

- **Status:** Expected while the SQS/Airflow trigger is still being built. The
  entrypoint will be wired up as part of that work (see
  `infrastructure-review.md`, Planned Work item 5).
- **Direction:** Point the container at the real ingestion entry once the
  queue-driven runner exists, rather than the placeholder `main.py`.
- **Files:** `Dockerfile`, `src/ingestion_pipeline/main.py`,
  `src/ingestion_pipeline/runner.py`

### 5. Single-document harness in the runner (awaiting SQS trigger)

`runner.py` builds the S3 URI from three settings with a comment noting it is a
placeholder for a real SQS message; `correspondence_type` is hardcoded to
`"TC19 - ADDITIONAL INFO REQUEST"`.

- **Status:** Intentional interim harness. Replaced when the document-ingestion
  SQS consumer / Airflow parameter input lands (see `infrastructure-review.md`,
  Planned Work item 5).
- **Files:** `src/ingestion_pipeline/runner.py`

### 6. Error propagation (awaiting Airflow)

`runner.py::main()` catches all exceptions, logs critical, and does not re-raise
or `exit(1)`. On Airflow, a process that exits 0 after a fatal error would show
the task as succeeded, hiding failures.

- **Status:** Errors will be propagated once Airflow is enabled and configured
  (confirmed direction). Ties to `infrastructure-review.md` Planned Work items 6
  (re-raise / non-zero exit + DLQ) and 6a (page-image cleanup on failure).
- **Files:** `src/ingestion_pipeline/runner.py`

### 7. `get_textractor_instance()` mutates process-wide env vars

Because Textractor reads credentials from environment variables, the factory
temporarily sets `AWS_*` env vars and restores them in a `finally`. It is
documented but not thread/process-safe; concurrent construction would race on
global state.

- **Status:** Superseded by the move to cross-account IRSA (static keys are
  local-dev only). Retire this hack when IRSA lands — see
  `infrastructure-review.md`, Planned Work item 3. Until then, avoid concurrent
  Textractor construction.
- **Files:** `src/ingestion_pipeline/aws_client/clients.py`

### 8. OpenSearch client auth is empty

`OpenSearchIndexer` passes `http_auth=()` and relies on a proxy sidecar for auth.
The indexer has no credentials of its own.

- **Status:** The OpenSearch access model is changing to Transit Gateway or
  (likely) cross-account IRSA, with local-dev proxy support retained — see
  `infrastructure-review.md`, Planned Work item 4. Ensure auth is enforced and
  transport is TLS end-to-end (production URL must be `https://`) as part of that
  work.
- **Files:** `src/ingestion_pipeline/indexing/indexer.py`,
  `src/ingestion_pipeline/config.py`

## Suggested Priorities

Standalone issues, do independently of the roadmap:

1. Align CI Python to 3.12. *(Issue 3)*
2. Unify AWS client construction (move Bedrock + OpenSearch into factories,
   inject them). *(Issue 1)*
3. Reconcile the structure docs with reality (remove or populate `data_models/`,
   `date_extraction/`, `s3_file_downloader/`). *(Issue 2)*

Planned work, sequence with the infrastructure build:

4. Entrypoint wiring + queue-driven runner. *(Planned Work 4, 5)*
5. Error propagation + page-image cleanup once Airflow lands. *(Planned Work 6)*
6. Retire the Textractor env-var hack with IRSA; finalise OpenSearch auth.
   *(Planned Work 7, 8)*
