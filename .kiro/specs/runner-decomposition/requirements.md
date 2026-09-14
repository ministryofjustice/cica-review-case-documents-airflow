# Requirements Document

## Introduction

`src/ingestion_pipeline/runner.py` (~290 lines) currently mixes six unrelated
concerns: S3 URI utilities, document identity/metadata construction, the
`DocumentResult` outcome model, per-document worker logic, batch orchestration,
and entry-point wiring. This feature is a behavior-preserving refactor that
extracts those concerns into focused modules and packages, deletes one piece of
dead code, and updates the tests and steering documentation to mirror the new
layout. The observable behavior of every retained public function MUST remain
identical; this is a pure structural move, not a logic change.

The work is broken into focused extractions so it can proceed step by step:
renaming `s3_file_downloader/` to `s3_utils/`, creating a `document_identity/`
package, creating an `orchestration/batch_processing/` package, and reducing
`runner.py` to a thin entry point exposing only `main()`.

## Glossary

- **Runner_Module**: The source file `src/ingestion_pipeline/runner.py`.
- **S3_Utils_Package**: The package `src/ingestion_pipeline/s3_utils/`, produced by renaming the existing `s3_file_downloader/` package.
- **S3_Downloader_Module**: The module `src/ingestion_pipeline/s3_utils/s3_downloader.py`, holding `download_pdf_from_s3`.
- **S3_Uri_Module**: The module `src/ingestion_pipeline/s3_utils/s3_uri.py`, holding `validate_s3_uri`.
- **Document_Identity_Package**: The package `src/ingestion_pipeline/document_identity/`.
- **Identity_Module**: The module `src/ingestion_pipeline/document_identity/identity.py`, holding `compute_source_doc_id` and `build_document_metadata`.
- **Batch_Processing_Package**: The package `src/ingestion_pipeline/orchestration/batch_processing/`.
- **Document_Result_Module**: The module `src/ingestion_pipeline/orchestration/batch_processing/document_result.py`, holding the `DocumentResult` dataclass.
- **Batch_Runner_Module**: The module `src/ingestion_pipeline/orchestration/batch_processing/batch_runner.py`, holding `process_document_job` and `run_batch`.
- **Dead_Code_Function**: The function `extract_case_ref`, defined in `runner.py` and never called anywhere in `src/` or `tests/`.
- **Structure_Steering_Doc**: The steering file `.kiro/steering/structure.md`.
- **Test_Suite**: The pytest suite under `tests/`.
- **Coverage_Threshold**: The 90% minimum line coverage enforced by `pytest-cov`.
- **Ruff**: The linter and formatter configured for the project (line length 120, Google-style docstrings, double quotes).
- **Behavior_Preservation**: The guarantee that each retained public function returns identical outputs and produces identical side effects and log/acknowledgement behavior for identical inputs before and after the refactor.
- **Verification_Process**: The set of quality-gate commands (`uv run pytest`, `ruff check`, `ruff format --check`, `deptry`) run to confirm the refactor is safe to merge.

## Requirements

### Requirement 1: Rename s3_file_downloader to s3_utils and split S3 URI validation

**User Story:** As a maintainer, I want S3 helpers grouped in a single `s3_utils` package, so that S3 URI validation and downloading live under one clear boundary.

#### Acceptance Criteria

1. THE S3_Utils_Package SHALL exist at `src/ingestion_pipeline/s3_utils/` and SHALL contain an `__init__.py` file, an S3_Downloader_Module, and an S3_Uri_Module.
2. THE S3_Downloader_Module SHALL expose the `download_pdf_from_s3(bucket_name, file_key, download_path)` function, which SHALL download the object identified by `file_key` from `bucket_name` and write it to `download_path`.
3. IF an S3 error occurs during download, THEN THE S3_Downloader_Module SHALL propagate the raised S3 client error to the caller without downloading the file.
4. THE S3_Uri_Module SHALL expose the `validate_s3_uri(s3_uri: str, expected_bucket: str) -> bool` function, which SHALL return True when `s3_uri` starts with `s3://{expected_bucket}/` immediately followed by a directory matching the pattern of two digits, a hyphen, a 7 or 8, then five digits, then `/` (e.g. `s3://bucket/26-711111/`), and SHALL return False for any other input.
5. THE S3_Downloader_Module SHALL contain a TODO comment stating that `download_pdf_from_s3` is currently unused by `src/` because the pipeline uses `S3DocumentService`, and that consolidation is deferred to future work.
6. WHEN the refactor is complete, THE source tree SHALL NOT contain a `src/ingestion_pipeline/s3_file_downloader/` package, AND THE source tree SHALL NOT contain any import referencing the `s3_file_downloader` module path.

### Requirement 2: Extract document identity and metadata construction

**User Story:** As a maintainer, I want document identity computation isolated in its own package, so that identity concerns are reusable and independently testable.

#### Acceptance Criteria

1. THE Document_Identity_Package SHALL exist at `src/ingestion_pipeline/document_identity/` and SHALL contain an `__init__.py` file.
2. THE Identity_Module SHALL expose `compute_source_doc_id(job: DocumentJob) -> str`, which SHALL construct a `DocumentIdentifier` from the job's `source_file_name`, `correspondence_type`, and `case_ref` and SHALL return that identifier's deterministic Version 5 UUID as a string.
3. WHEN `compute_source_doc_id` is invoked more than once with jobs whose `source_file_name`, `correspondence_type`, and `case_ref` are equal, THE Identity_Module SHALL return the same UUID string for each invocation, and WHEN any of those three fields differ THE Identity_Module SHALL return a different UUID string.
4. THE Identity_Module SHALL expose `build_document_metadata(job: DocumentJob, source_doc_id: str) -> DocumentMetadata`, which SHALL return a `DocumentMetadata` whose `source_doc_id` equals the passed `source_doc_id`, whose `source_file_name`, `source_file_s3_uri`, `case_ref`, and `correspondence_type` equal the corresponding job fields, whose `page_count` is None, and whose `received_date` is the current UTC time as a naive datetime.
5. THE Identity_Module SHALL import `DocumentIdentifier` from `ingestion_pipeline.uuid_generators.document_uuid` and `DocumentMetadata` from `ingestion_pipeline.chunking.schemas`.

### Requirement 3: Extract the DocumentResult outcome model

**User Story:** As a maintainer, I want the per-document outcome model in its own module, so that the batch data model is separate from batch execution logic.

#### Acceptance Criteria

1. THE Batch_Processing_Package SHALL exist at `src/ingestion_pipeline/orchestration/batch_processing/` and SHALL contain an `__init__.py` file.
2. THE Document_Result_Module SHALL reside within the Batch_Processing_Package and SHALL define the `DocumentResult` dataclass with exactly these fields, types, and default values: `job: DocumentJob`, `source_doc_id: str`, `success: bool`, `error: Exception | None = None`, `category: DlqCategory | None = None`, and `retryable: bool | None = None`.
3. THE Document_Result_Module SHALL import `DocumentJob` from `ingestion_pipeline.orchestration.document_source` and `DlqCategory` from `ingestion_pipeline.errors`.
4. THE Runner_Module SHALL NOT define the `DocumentResult` dataclass and SHALL reference `DocumentResult` only via import from the Document_Result_Module.

### Requirement 4: Extract per-document worker and batch orchestration

**User Story:** As a maintainer, I want the worker and batch orchestration logic in a dedicated module, so that batch execution is separated from application entry-point wiring.

#### Acceptance Criteria

1. THE Batch_Runner_Module SHALL contain the `process_document_job` function moved from Runner_Module, preserving Behavior_Preservation.
2. THE Batch_Runner_Module SHALL contain the `run_batch` function moved from Runner_Module, preserving Behavior_Preservation.
3. WHEN a batch contains multiple jobs that resolve to the same `source_doc_id`, THE `run_batch` function SHALL treat the first job in input order as the owner, submit only owners to the thread pool, leave duplicate jobs unprocessed, and return exactly one `DocumentResult` per owner and no result for any duplicate job.
4. WHEN an owner job returns a `DocumentResult` with `success` equal to True, THE `run_batch` function SHALL acknowledge the owner job and each of its collapsed duplicate jobs through the DocumentSource.
5. IF an owner job returns a `DocumentResult` with `success` equal to False, THEN THE `run_batch` function SHALL leave the owner job and each of its collapsed duplicate jobs unacknowledged.
6. WHEN `run_batch` receives an empty list of jobs, THE `run_batch` function SHALL return an empty list, log an informational message stating there are no documents to process, and not create a thread pool.
7. THE `run_batch` function SHALL size the thread pool to `min(MAX_CONCURRENT_DOCUMENTS, number_of_owners)`, where `number_of_owners` is the count of distinct `source_doc_id` values across the input jobs.
8. WHEN `process_document_job` is invoked, THE `process_document_job` function SHALL set `source_doc_id_context` to the job's computed `source_doc_id` for the duration of the call and reset that context token before returning, on both success and failure paths.
9. IF `validate_s3_uri` returns False for the job's S3 URI, THEN THE `process_document_job` function SHALL return a `DocumentResult` with `success` equal to False, `category` equal to `DlqCategory.UNEXPECTED`, and `retryable` equal to False, and SHALL emit a critical-level log entry, without acknowledging the job.
10. WHEN `pipeline.process_document` returns without raising, THE `process_document_job` function SHALL return a `DocumentResult` with `success` equal to True and with `error`, `category`, and `retryable` left at their default values.
11. IF `pipeline.process_document` raises a `PipelineError`, THEN THE `process_document_job` function SHALL return a `DocumentResult` with `success` equal to False, `error` set to the raised exception, `category` set to the exception's `category`, and `retryable` set to the exception's `retryable`, and SHALL emit an error-level log entry indicating the job is not acknowledged.
12. IF `pipeline.process_document` raises any exception that is not a `PipelineError`, THEN THE `process_document_job` function SHALL return a `DocumentResult` with `success` equal to False, `error` set to the raised exception, `category` equal to `DlqCategory.UNEXPECTED`, and `retryable` equal to False, and SHALL emit a critical-level log entry.

### Requirement 5: Reduce the runner to a thin entry point

**User Story:** As a maintainer, I want `runner.py` to be a thin entry point, so that its single responsibility is wiring the application together.

#### Acceptance Criteria

1. WHEN `main` is invoked with a healthy OpenSearch endpoint and a non-empty batch, THE Runner_Module SHALL, in order, log a start message, invoke `check_opensearch_health`, invoke `build_pipeline` exactly once, construct exactly one `SqsDocumentSource`, obtain the batch via `source.fetch_batch()`, invoke `run_batch(jobs, pipeline, source)` exactly once, and log a finished message.
2. THE Runner_Module SHALL import and reference only `setup_logging`, `check_opensearch_health`, `build_pipeline`, `SqsDocumentSource`, and `run_batch` for use by `main`, SHALL invoke `setup_logging` once at module import, and SHALL invoke `main` exactly once only when executed as the top-level entry point (`__name__ == "__main__"`).
3. WHEN the refactor is complete, THE Runner_Module SHALL NOT define any of the symbols `DocumentResult`, `validate_s3_uri`, `compute_source_doc_id`, `build_document_metadata`, `process_document_job`, or `run_batch`.
4. WHILE `LOCAL_DEVELOPMENT_MODE` is enabled, WHEN `main` is invoked, THE Runner_Module SHALL emit a single WARNING-level log entry indicating local-development mode before logging the start message, and WHILE `LOCAL_DEVELOPMENT_MODE` is disabled THE Runner_Module SHALL NOT emit that warning.
5. IF `check_opensearch_health` returns an unhealthy result, THEN THE Runner_Module SHALL emit a CRITICAL-level log entry indicating the health check failed, SHALL NOT invoke `build_pipeline`, `SqsDocumentSource`, `source.fetch_batch`, or `run_batch`, and SHALL return from `main` without raising.

### Requirement 6: Delete dead code

**User Story:** As a maintainer, I want unused code removed, so that the codebase does not carry misleading dead functions.

#### Acceptance Criteria

1. WHEN the refactor is complete, THE source tree SHALL NOT define the function `extract_case_ref` in any module under `src/` or `tests/`.
2. WHEN the refactor is complete, THE source tree SHALL NOT contain any import or call referencing `extract_case_ref`.
3. WHEN `extract_case_ref` is removed, THE refactor SHALL also remove its docstring and the preceding regex comment that accompany the function.
4. WHEN `uv run pytest` and `ruff check` run after the deletion, THE Test_Suite and Ruff SHALL report no errors caused by dangling references to `extract_case_ref`.

### Requirement 7: Preserve behavior

**User Story:** As a maintainer, I want the refactor to change structure only, so that no existing behavior regresses.

#### Acceptance Criteria

1. WHEN `compute_source_doc_id`, `build_document_metadata`, `validate_s3_uri`, `download_pdf_from_s3`, `process_document_job`, `run_batch`, or `main` is invoked with a given input in the refactored source, THE refactored source SHALL produce the same observable outcome as the pre-refactor source for that input, where "same observable outcome" means an identical return value, an identical raised exception type, and (for `process_document_job` and `run_batch`) an identical `success` flag, `DlqCategory`, and `retryable` classification on the resulting `DocumentResult`.
2. WHEN the Test_Suite runs against the refactored source, THE existing behavioral, property-based, and preservation tests for the moved functions SHALL pass with a 100% pass rate and zero regressions, with no test assertion weakened, skipped, or marked expected-fail relative to its pre-refactor form.
3. WHEN a moved function emits a log record or makes an acknowledgement decision in the refactored source, THE refactored source SHALL emit the same log level and message content and make the same `acknowledge()` / leave-unacknowledged decision per job as the pre-refactor source for the same input, and SHALL size the worker pool at `min(MAX_CONCURRENT_DOCUMENTS, owner_count)` as before.
4. IF any moved behavioral, property-based, or preservation test fails when run against the refactored source, THEN THE refactor SHALL be treated as incomplete, the failing test SHALL be reported with its failure detail, and the pre-refactor assertion semantics SHALL be retained unchanged (no test edited to make it pass).
5. WHEN the moved functions are imported after the refactor, THE refactored source SHALL preserve each function's public name and call signature so existing import paths and call sites resolve without modification.

### Requirement 8: Update tests to mirror the new layout

**User Story:** As a maintainer, I want tests organized to mirror the new module layout, so that each module has a corresponding, discoverable test module.

#### Acceptance Criteria

1. THE Test_Suite SHALL contain `tests/s3_utils/test_s3_downloader.py` with import paths updated to the S3_Downloader_Module, retaining its existing unittest-style TestCase structure with only the import path changed.
2. THE Test_Suite SHALL contain `tests/s3_utils/test_s3_uri.py` covering `validate_s3_uri`, including valid URIs, wrong-bucket URIs, and malformed case-reference patterns.
3. WHEN the refactor is complete, THE Test_Suite SHALL NOT contain a `tests/s3_file_downloader/` directory.
4. THE Test_Suite SHALL contain `tests/document_identity/test_identity.py` covering `compute_source_doc_id` determinism and `build_document_metadata` field mapping.
5. THE Test_Suite SHALL contain `tests/orchestration/batch_processing/test_document_result.py` covering the `DocumentResult` dataclass construction and default values.
6. THE Test_Suite SHALL contain `tests/orchestration/batch_processing/test_batch_runner.py` covering worker logic, batch orchestration, deduplication, concurrency, and the moved hypothesis property and preservation tests, with `mock.patch` targets updated to the new module paths.
7. THE new test directories `tests/s3_utils/`, `tests/document_identity/`, and `tests/orchestration/batch_processing/` SHALL each contain an `__init__.py` file consistent with the existing tests package structure.
8. THE `tests/test_runner.py` file SHALL be trimmed to cover only the `main` wiring behavior.

### Requirement 9: Follow package and docstring conventions

**User Story:** As a maintainer, I want the new modules to follow project conventions, so that they pass linting and match the existing codebase style.

#### Acceptance Criteria

1. THE S3_Utils_Package, Document_Identity_Package, and Batch_Processing_Package SHALL each contain an `__init__.py` file.
2. THE S3_Uri_Module, Identity_Module, Document_Result_Module, and Batch_Runner_Module SHALL each carry a Google-style module docstring, and every public function and class in each module SHALL carry a Google-style docstring.
3. THE new and modified source modules SHALL use double-quoted strings for all string literals and SHALL contain no source line exceeding 120 characters, where a line of exactly 120 characters passes and a line of 121 or more characters fails.
4. THE new and modified source modules SHALL contain no `print` statement.
5. WHEN the ruff linter and formatter are run against the new and modified source modules with rule sets E, F, W, I, T20, and D enabled and the Google docstring convention configured, THE ruff tooling SHALL report zero violations.

### Requirement 10: Update steering documentation

**User Story:** As a maintainer, I want the structure steering doc to reflect the new layout, so that documentation stays accurate.

#### Acceptance Criteria

1. THE Structure_Steering_Doc SHALL NOT contain the `s3_file_downloader/` module row, and SHALL contain an S3_Utils_Package row with a non-empty Responsibility cell in the source-code module table.
2. THE Structure_Steering_Doc SHALL contain a Document_Identity_Package row with a non-empty Responsibility cell in the source-code module table.
3. THE Structure_Steering_Doc SHALL contain a Batch_Processing_Package row with a non-empty Responsibility cell in the source-code module table.
4. WHEN the refactor is complete, THE Structure_Steering_Doc SHALL NOT contain any residual reference to the `s3_file_downloader` module name.

### Requirement 11: Verify coverage and lint cleanliness

**User Story:** As a maintainer, I want the refactor verified against quality gates, so that it is safe to merge.

#### Acceptance Criteria

1. WHEN `uv run pytest` runs against the refactored source and tests, THE Test_Suite SHALL complete with zero failing tests and zero errored tests, and SHALL report combined line coverage of 90% or greater (the Coverage_Threshold enforced by `--cov-fail-under=90`).
2. IF the reported combined line coverage is below the Coverage_Threshold of 90%, THEN THE Test_Suite SHALL exit with a non-zero status and produce output indicating the coverage shortfall, without merging the change.
3. WHEN `ruff check` runs against the new and modified source and test files, THE Verification_Process SHALL report zero lint violations.
4. WHEN `ruff format --check` runs against the new and modified source and test files, THE Verification_Process SHALL report zero formatting violations.
5. WHEN `deptry` runs against the project, THE Verification_Process SHALL report zero dependency issues and SHALL confirm that no new runtime dependencies were introduced by the refactor.
