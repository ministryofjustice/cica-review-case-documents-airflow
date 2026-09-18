# Implementation Plan: Runner Decomposition

## Overview

This is a behavior-preserving, structural refactor of `src/ingestion_pipeline/runner.py`.
It extracts six mixed concerns into focused modules and packages, deletes one dead
function, migrates the tests to mirror the new layout, and updates the `structure.md`
steering doc.

The plan follows the design's six-step ordering exactly. Each step is strictly
sequential: every step rewires `runner.py` imports, step 4 wires together the modules
created in steps 1–3, and step 5 depends on step 4. Each step must compile and its
tests must pass before the next step begins. All source moves are verbatim — no
logic, log message, log level, or acknowledgement decision changes.

Convert the feature design into a series of prompts for a code-generation LLM that
will implement each step with incremental progress. Make sure that each prompt builds
on the previous prompts, and ends with wiring things together. There should be no
hanging or orphaned code that isn't integrated into a previous step. Focus ONLY on
tasks that involve writing, modifying, or testing code.

## Tasks

- [x] 1. Rename `s3_file_downloader/` to `s3_utils/` and split S3 URI validation
  - [x] 1.1 Create the `s3_utils` package and move the downloader verbatim
    - Create `src/ingestion_pipeline/s3_utils/__init__.py` (empty package marker, mirroring the existing `s3_file_downloader/__init__.py`)
    - Move `s3_downloader.py` verbatim into `src/ingestion_pipeline/s3_utils/s3_downloader.py`, keeping `download_pdf_from_s3(bucket_name, file_key, download_path)` unchanged
    - Add a TODO comment in `s3_downloader.py` stating `download_pdf_from_s3` is currently unused by `src/` because the pipeline uses `S3DocumentService`, and that consolidation is deferred to future work
    - Delete the old `src/ingestion_pipeline/s3_file_downloader/` package so no `s3_file_downloader` module path remains
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_

  - [x] 1.2 Create `s3_uri.py` with `validate_s3_uri` moved verbatim
    - Create `src/ingestion_pipeline/s3_utils/s3_uri.py` with a Google-style module docstring
    - Move `validate_s3_uri(s3_uri: str, expected_bucket: str) -> bool` verbatim from `runner.py`, keeping the `re` import local to this module and the regex/return semantics identical
    - _Requirements: 1.1, 1.4, 9.1, 9.2_

  - [x] 1.3 Update `runner.py` to import `validate_s3_uri` from the new location (interim)
    - Change `runner.py` to import `validate_s3_uri` from `ingestion_pipeline.s3_utils.s3_uri` and remove its local definition
    - This is an interim wiring step; `runner.py` is fully slimmed in step 5
    - _Requirements: 1.6_

  - [x] 1.4 Rename the test directory and update the downloader test import
    - Rename `tests/s3_file_downloader/` to `tests/s3_utils/` and add `tests/s3_utils/__init__.py`
    - In `tests/s3_utils/test_s3_downloader.py`, update the import to `from ingestion_pipeline.s3_utils.s3_downloader import download_pdf_from_s3`, retaining the existing unittest `TestCase` structure with only the import path changed
    - Ensure no `tests/s3_file_downloader/` directory remains
    - _Requirements: 8.1, 8.3, 8.7_

  - [x] 1.5 Add `tests/s3_utils/test_s3_uri.py` for `validate_s3_uri`
    - Cover valid URIs (e.g. `s3://bucket/26-711111/...`), wrong-bucket URIs, and malformed case-reference patterns (wrong digit counts, missing leading `7`/`8`, missing trailing slash)
    - _Requirements: 1.4, 8.2, 8.7_

  - [x] 1.6 Verify step 1
    - Run `uv run pytest tests/s3_utils/` and the full suite; confirm green before proceeding
    - _Requirements: 9.1, 9.2_

- [x] 2. Extract the `document_identity/` package
  - [x] 2.1 Create the package and move identity functions verbatim
    - Create `src/ingestion_pipeline/document_identity/__init__.py` (empty package marker)
    - Create `src/ingestion_pipeline/document_identity/identity.py` with a Google-style module docstring
    - Move `compute_source_doc_id(job) -> str` and `build_document_metadata(job, source_doc_id) -> DocumentMetadata` verbatim from `runner.py`, including their `datetime` usage and Google-style docstrings
    - Import `DocumentIdentifier` from `ingestion_pipeline.uuid_generators.document_uuid`, `DocumentMetadata` from `ingestion_pipeline.chunking.schemas`, `DocumentJob` from `ingestion_pipeline.orchestration.document_source` (for type hints), and `datetime`
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 9.1, 9.2_

  - [x] 2.2 Update `runner.py` imports to reference the new location (interim)
    - Change `runner.py` to import `compute_source_doc_id` and `build_document_metadata` from `ingestion_pipeline.document_identity.identity` and remove their local definitions
    - This is an interim wiring step; `runner.py` is fully slimmed in step 5
    - _Requirements: 2.1_

  - [x] 2.3 Add `tests/document_identity/test_identity.py`
    - Create `tests/document_identity/__init__.py` and `test_identity.py`
    - Cover `compute_source_doc_id` determinism (equal `source_file_name`/`correspondence_type`/`case_ref` → same UUID; any differing field → different UUID)
    - Cover `build_document_metadata` field mapping (`page_count=None`, naive UTC `received_date`, and `source_doc_id`/`source_file_name`/`source_file_s3_uri`/`case_ref`/`correspondence_type` mapped from the job)
    - _Requirements: 2.3, 2.4, 8.4, 8.7_

  - [x] 2.4 Verify step 2
    - Run `uv run pytest tests/document_identity/` and the full suite; confirm green before proceeding
    - _Requirements: 9.1, 9.2_

- [x] 3. Extract `DocumentResult` into `orchestration/batch_processing/document_result.py`
  - [x] 3.1 Create the `batch_processing` package and move `DocumentResult` verbatim
    - Create `src/ingestion_pipeline/orchestration/batch_processing/__init__.py` (empty package marker)
    - Create `document_result.py` with a Google-style module docstring and the `DocumentResult` dataclass moved verbatim, including its class docstring and exact fields/types/defaults (`job: DocumentJob`, `source_doc_id: str`, `success: bool`, `error: Exception | None = None`, `category: DlqCategory | None = None`, `retryable: bool | None = None`)
    - Import `dataclass` from `dataclasses`, `DocumentJob` from `ingestion_pipeline.orchestration.document_source`, and `DlqCategory` from `ingestion_pipeline.errors`
    - _Requirements: 3.1, 3.2, 3.3, 9.1, 9.2_

  - [x] 3.2 Update `runner.py` import (interim)
    - Change `runner.py` to import `DocumentResult` from `ingestion_pipeline.orchestration.batch_processing.document_result` and remove its local definition
    - This is an interim wiring step; `runner.py` is fully slimmed in step 5
    - _Requirements: 3.4_

  - [x] 3.3 Add `tests/orchestration/batch_processing/test_document_result.py`
    - Create `tests/orchestration/batch_processing/__init__.py` and `test_document_result.py`
    - Cover `DocumentResult` construction and default values (`error`/`category`/`retryable` default to `None`)
    - _Requirements: 3.2, 8.5, 8.7_

  - [x] 3.4 Verify step 3
    - Run `uv run pytest tests/orchestration/batch_processing/` and the full suite; confirm green before proceeding
    - _Requirements: 9.1, 9.2_

- [x] 4. Extract worker and batch orchestration into `batch_processing/batch_runner.py`
  - [x] 4.1 Move `process_document_job` and `run_batch` verbatim into `batch_runner.py`
    - Create `src/ingestion_pipeline/orchestration/batch_processing/batch_runner.py` with a Google-style module docstring and a module-level `logger = logging.getLogger(__name__)`
    - Move `process_document_job(job, pipeline) -> DocumentResult` and `run_batch(jobs, pipeline, source) -> list[DocumentResult]` verbatim, preserving all logging (messages, levels, `exc_info`), dedup grouping, worker sizing, acknowledgement, and error classification
    - Wire imports: `DocumentResult` from `.document_result`; `compute_source_doc_id`, `build_document_metadata` from `ingestion_pipeline.document_identity.identity`; `validate_s3_uri` from `ingestion_pipeline.s3_utils.s3_uri`; `settings` from `ingestion_pipeline.config`; `source_doc_id_context` from `ingestion_pipeline.custom_logging.log_context`; `DlqCategory, PipelineError` from `ingestion_pipeline.errors`; `DocumentJob, DocumentSource` from `ingestion_pipeline.orchestration.document_source`; `Pipeline` from `ingestion_pipeline.orchestration.pipeline`; `logging`; `ThreadPoolExecutor, as_completed` from `concurrent.futures`
    - Update `runner.py` to import `process_document_job` and `run_batch` from `batch_runner` (interim, until step 5)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 7.1, 7.3, 7.5, 9.1, 9.2_

  - [x] 4.2 Migrate worker/batch/dedup/concurrency tests into `test_batch_runner.py`
    - Move the worker-logic, batch-orchestration, dedup, and concurrency tests from `tests/test_runner.py` into `tests/orchestration/batch_processing/test_batch_runner.py`
    - Retarget `mock.patch` paths from `ingestion_pipeline.runner.{settings,ThreadPoolExecutor,datetime}` to `ingestion_pipeline.orchestration.batch_processing.batch_runner.{settings,ThreadPoolExecutor,datetime}`
    - Import `compute_source_doc_id` from `ingestion_pipeline.document_identity.identity`; keep `DocumentIdentifier` sourced from `ingestion_pipeline.uuid_generators.document_uuid`
    - Do not weaken, skip, or xfail any assertion relative to its pre-refactor form
    - _Requirements: 7.2, 7.4, 8.6, 8.7_

  - [x] 4.3 Migrate the hypothesis property and preservation tests into `test_batch_runner.py`
    - Move the hypothesis Property 1 (dedup) and Property 2 (preservation of no-duplicate batches) tests from `tests/test_runner.py` into `test_batch_runner.py` verbatim, retargeting `mock.patch` paths to `batch_runner`
    - _Requirements: 7.2, 7.4, 8.6_

  - [x] 4.4 Verify step 4
    - Run `uv run pytest tests/orchestration/batch_processing/` and the full suite; confirm green before proceeding
    - _Requirements: 7.2, 9.2_

- [x] 5. Slim `runner.py` and delete dead code
  - [x] 5.1 Reduce `runner.py` to a thin entry point and delete `extract_case_ref`
    - Reduce `runner.py` to: module docstring, `setup_logging()` call at import, module `logger`, `main()` (body unchanged), and the `if __name__ == "__main__":` guard
    - Import `run_batch` from `ingestion_pipeline.orchestration.batch_processing.batch_runner`; keep imports for `main` only (`settings`, `setup_logging`, `check_opensearch_health`, `SqsDocumentSource`, `DocumentSource` for annotation, `build_pipeline`, `logging`)
    - Remove all moved symbols (`DocumentResult`, `validate_s3_uri`, `compute_source_doc_id`, `build_document_metadata`, `process_document_job`, `run_batch`) and now-unused imports (`datetime`, `re`, `dataclass`, `ThreadPoolExecutor`/`as_completed`, `DocumentMetadata`, `DocumentIdentifier`, `DlqCategory`/`PipelineError`, `DocumentJob`, `Pipeline`, `source_doc_id_context`)
    - Delete `extract_case_ref` entirely, including its docstring and the preceding `# /\d{2}[-][78]d{5}/gm` regex comment; leave no import or call referencing it
    - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4, 8.8_

  - [x] 5.2 Trim `tests/test_runner.py` to the three `main` wiring tests
    - Keep only: successful execution, health-check early exit, and metadata correctness
    - Retarget the `datetime` patch in the metadata-correctness test to `ingestion_pipeline.orchestration.batch_processing.batch_runner.datetime` (since `build_document_metadata` reads the clock there); keep `SqsDocumentSource`, `build_pipeline`, `check_opensearch_health`, and `logger` patched at `ingestion_pipeline.runner.*`
    - _Requirements: 5.4, 5.5, 8.8_

  - [x] 5.3 Verify step 5
    - Run `uv run pytest tests/test_runner.py` and the full suite; confirm green before proceeding
    - _Requirements: 6.4_

- [x] 6. Update steering docs and run full verification
  - [x] 6.1 Update `.kiro/steering/structure.md`
    - Replace the `s3_file_downloader/` row with an `s3_utils/` row (non-empty Responsibility cell)
    - Add a `document_identity/` row and an `orchestration/batch_processing/` row (each with a non-empty Responsibility cell)
    - Remove any residual reference to the `s3_file_downloader` module name
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 6.2 Run the full quality gates and fix any violations
    - Run `uv run pytest` and confirm zero failures/errors with combined line coverage of 90% or greater
    - Run `ruff check`, `ruff format --check`, and `deptry`; fix any lint, formatting, or dependency violations (confirm no new runtime dependencies were introduced)
    - _Requirements: 6.4, 9.3, 9.4, 9.5, 11.1, 11.2, 11.3, 11.4, 11.5_

## Notes

- This is a behavior-preserving structural refactor; the design derives no new correctness properties. Property 1 (dedup) and Property 2 (preservation) are moved verbatim, not re-authored, so they appear as migration tasks (4.3) rather than new property-test authoring tasks.
- All tasks are required; there are no optional (`*`) sub-tasks, because verification of preserved behavior is the core deliverable of this refactor.
- Steps are strictly sequential: each step rewires `runner.py` imports, step 4 wires together steps 1–3, and step 5 depends on step 4. Do not parallelize across steps.
- All source moves are verbatim — no logic, log message, log level, or acknowledgement decision changes.
- Each task references specific requirements for traceability.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "1.6"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 4, "tasks": ["3.1"] },
    { "id": 5, "tasks": ["3.2", "3.3", "3.4"] },
    { "id": 6, "tasks": ["4.1"] },
    { "id": 7, "tasks": ["4.2", "4.3", "4.4"] },
    { "id": 8, "tasks": ["5.1"] },
    { "id": 9, "tasks": ["5.2", "5.3"] },
    { "id": 10, "tasks": ["6.1"] },
    { "id": 11, "tasks": ["6.2"] }
  ]
}
```
