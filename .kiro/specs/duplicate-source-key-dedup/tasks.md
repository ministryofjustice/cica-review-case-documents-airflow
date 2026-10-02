# Implementation Plan

This plan follows the exploratory bugfix workflow: explore (surface counterexamples
on UNFIXED code), preserve (capture existing behavior for non-buggy inputs),
implement (apply the minimal fix at the `run_batch` seam), then validate.

The fix lives entirely in `src/ingestion_pipeline/runner.py` (new pure helper
`compute_source_doc_id` + grouping/acknowledgement in `run_batch`). `fetch_batch`
(throwaway stub) and `_cleanup_document` (structurally safe once deduped) are NOT
modified. Tests live under `tests/` mirroring `src/ingestion_pipeline/`
(`tests/test_runner.py`). Property-based tests use `hypothesis` — add it as a dev
dependency first (`uv add --dev hypothesis`) if not already present.

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Duplicate source_doc_id is processed once with defined acknowledgement
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug (duplicate-keyed jobs invoked more than once / overlapping)
  - **Scoped PBT Approach**: For this deterministic seam, scope the property to concrete failing batches (the same natural key repeated N≥2 times) so the counterexample is reproducible; a `hypothesis` strategy generating batches that repeat a key N times is preferred where practical
  - Add to `tests/test_runner.py`. Build a batch of two-or-more jobs whose natural key `(source_file_name, correspondence_type, case_ref)` resolves to the same `source_doc_id` (see `isBugCondition` in design: `computeSourceDocId(job) = DocumentIdentifier(job.source_file_name, job.correspondence_type, job.case_ref).generate_uuid()`)
  - Use a fake/instrumented `Pipeline` that records every `process_document` invocation keyed by `document_metadata.source_doc_id`, plus timestamps to detect overlap; use a recording `DocumentSource` (in-memory, captures `acknowledge` calls) rather than moto since no direct AWS call is made at this seam
  - Assertions (matching Property 1 / Expected Behavior in design):
    - For each distinct `source_doc_id` in the batch, `count(pipelineInvocations(id)) <= 1`
    - No two invocations for the same `source_doc_id` overlap in time (use a slow fake pipeline: enter → sleep → exit, and assert no concurrent entry for the same id)
    - Every input job reaches a defined acknowledgement outcome ∈ { ack_as_processed, dropped_as_duplicate, left_for_redrive }
  - Cover the design's exploratory test cases: (1) duplicate-key single invocation, (2) concurrent collision with slow fake pipeline, (3) cleanup isolation when one duplicate fails, (4) duplicate acknowledgement — both jobs acknowledged on success
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists: pipeline invoked twice for one `source_doc_id`, invocations overlap, and the duplicate job is not acknowledged)
  - Document counterexamples found (e.g. "batch of 2 identical-key jobs → `process_document` invoked 2x for the same source_doc_id; invocations overlapped; only 1 job acknowledged")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 2.1, 2.2, 2.3, 2.5_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - No-duplicate batches behave exactly as before
  - **IMPORTANT**: Follow observation-first methodology — run the UNFIXED `run_batch` on distinct-key batches, record the actual outputs, then assert those observed outputs
  - Add to `tests/test_runner.py`. Prefer `hypothesis` to generate distinct-key batches of varying size (guaranteed-distinct natural keys), covering size boundaries around `MAX_CONCURRENT_DOCUMENTS`, single-job batches, and the empty batch
  - Observe on UNFIXED code and encode as properties (from Preservation Requirements / design test cases):
    - Distinct-key concurrency: a distinct-key batch runs up to `MAX_CONCURRENT_DOCUMENTS` workers (`max_workers == min(MAX_CONCURRENT_DOCUMENTS, len(jobs))`)
    - Success acknowledgement: each succeeding distinct-key job is acknowledged exactly once via the `DocumentSource`
    - Failure classification/cleanup: a failing distinct-key job is left unacknowledged and its `DocumentResult` carries `success=False` with `category`/`retryable` set (cleanup is owned by the pipeline)
    - One `DocumentResult` per job; the deterministic `source_doc_id` per job is unchanged
    - Empty batch: `run_batch([], ...) == []`
  - **EXPECTED OUTCOME**: Tests PASS on UNFIXED code (this confirms the baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix for duplicate source_doc_id racing in run_batch

  - [x] 3.1 Extract `compute_source_doc_id` helper and refactor `process_document_job`
    - Add a pure helper in `src/ingestion_pipeline/runner.py`:
      `def compute_source_doc_id(job: DocumentJob) -> str:` returning
      `DocumentIdentifier(source_file_name=job.source_file_name, correspondence_type=job.correspondence_type, case_ref=job.case_ref).generate_uuid()`
    - Refactor `process_document_job` to call `compute_source_doc_id(job)` instead of constructing `DocumentIdentifier` inline, so dedup and processing compute `source_doc_id` identically (single source of truth)
    - Add a Google-style docstring
    - _Bug_Condition: isBugCondition(batch) = hasDuplicates([computeSourceDocId(job) for job in batch])_
    - _Expected_Behavior: source_doc_id derived identically for dedup and processing (no change to the computation)_
    - _Preservation: Preservation Requirements — deterministic source_doc_id unchanged_
    - _Requirements: 3.4_

  - [x] 3.2 Add order-preserving grouping in `run_batch`
    - Preserving input order, build an ordered mapping `source_doc_id -> list[DocumentJob]` using `compute_source_doc_id`; the first job seen for an id is the **owner**, the rest are **duplicates**
    - Submit only owners to the `ThreadPoolExecutor`; set `max_workers = min(settings.MAX_CONCURRENT_DOCUMENTS, number_of_owners)`
    - This guarantees at most one in-flight unit per `source_doc_id`
    - When one or more duplicates are detected for a `source_doc_id`, emit a structured observability log entry via the module `logger` naming the affected `source_doc_id`, the count of duplicates collapsed, and the duplicate jobs' S3 URIs / `case_ref` where available (purely observational — does not change the dedup or acknowledgement behavior)
    - _Bug_Condition: isBugCondition(batch) from design_
    - _Expected_Behavior: each distinct source_doc_id handed to the pipeline at most once; no two in-flight units share a source_doc_id_
    - _Preservation: no-duplicate batches — grouping is a no-op, max_workers unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 2.6, 3.1_

  - [x] 3.3 Implement the duplicate acknowledgement policy
    - When an owner's future completes:
      - On success: acknowledge the owner (unchanged), then acknowledge every duplicate job for that `source_doc_id` so SQS does not redeliver them
      - On failure: leave the owner unacknowledged (unchanged) and also leave its duplicates unacknowledged for redrive
    - The retained unit's outcome determines acknowledgement for its duplicates
    - _Bug_Condition: isBugCondition(batch) from design_
    - _Expected_Behavior: every input job reaches a defined acknowledgement outcome ∈ { ack_as_processed, dropped_as_duplicate, left_for_redrive }_
    - _Preservation: success→acknowledge and failure→unacknowledged unchanged for distinct-key jobs_
    - _Requirements: 2.5, 3.2, 3.3_

  - [x] 3.4 Return one DocumentResult per owner; preserve distinct-key and empty-batch behavior
    - `run_batch` returns one `DocumentResult` per processed owner (at most one per distinct `source_doc_id`); duplicate jobs are not processed and produce no `DocumentResult`
    - For a no-duplicate batch every job is its own owner with an empty duplicate list, so the returned list is identical to today
    - Empty batch still short-circuits to `[]`
    - Do NOT modify `SqsDocumentSource.fetch_batch` (throwaway stub) or `_cleanup_document` (structurally safe once deduped)
    - _Bug_Condition: isBugCondition(batch) from design_
    - _Expected_Behavior: one owner result per distinct source_doc_id_
    - _Preservation: Property 2 — distinct-key and empty batches identical to original_
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.5 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Duplicate source_doc_id is processed once with defined acknowledgement
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior; when it passes it confirms each distinct `source_doc_id` is processed at most once, no two units overlap, and every job has a defined acknowledgement outcome
    - Run the bug condition exploration test from task 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms the bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** - No-duplicate batches behave exactly as before
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run the preservation property tests from task 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions for distinct-key and empty batches)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Add unit, property-based, and integration tests

  - [x] 4.1 Unit tests for `compute_source_doc_id` and `run_batch`
    - `compute_source_doc_id` returns the same value as the previous inline `DocumentIdentifier(...).generate_uuid()` for representative jobs; equal-key jobs collide and distinct-key jobs do not
    - `run_batch` grouping: a duplicate-key batch submits exactly one owner per `source_doc_id`; duplicate jobs are acknowledged on owner success and left unacknowledged on owner failure
    - `run_batch` distinct-key batch: one `DocumentResult` per job, correct success/failure acknowledgement, `max_workers == min(MAX_CONCURRENT_DOCUMENTS, n)`
    - `run_batch` duplicate-collapse logging: assert via `caplog` that the duplicate-collapse log entry is emitted for a duplicate-keyed batch (naming the affected `source_doc_id`, the count of duplicates collapsed, and the duplicate jobs' S3 URIs / `case_ref`), and that no such entry is emitted for a distinct-key batch
    - Empty batch returns `[]`
    - _Requirements: 2.1, 2.2, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 4.2 Property-based tests (hypothesis)
    - Generate batches mixing duplicate and distinct keys; assert each distinct `source_doc_id` is processed at most once and every input job has a defined acknowledgement outcome (Fix Checking / Property 1)
    - Generate distinct-key batches of varying size; assert the fixed runner's observable outcome (results per job, acknowledgements, classification) matches the original (Preservation Checking / Property 2)
    - Generate batches with the same key repeated N times; assert exactly one owner is processed and N-1 duplicates are acknowledged on success
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 4.3 Integration tests with a fake pipeline + recording DocumentSource
    - Duplicate-keyed batch against a fake pipeline and a recording `DocumentSource`: assert single processing, single S3 prefix / OpenSearch id ownership, and acknowledgement of all duplicate handles on success
    - Failing owner: assert the owner and its duplicates are left unacknowledged for redrive, and cleanup affects only the single de-duplicated unit
    - Distinct-key batch: assert end-to-end behavior is identical to the pre-fix baseline (concurrency, acknowledgement, classification)
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 3.1, 3.2, 3.3_

- [x] 5. Checkpoint - Ensure all tests pass and quality gates are met
  - Run `uv run pytest` and confirm all tests pass (bug condition + preservation + unit + property-based + integration)
  - Confirm coverage stays at or above the enforced 90% (`pytest-cov`)
  - Run `uv run ruff format` and `uv run ruff check` (Google-style docstrings on new source; D-rules relaxed in tests)
  - If `hypothesis` was added, confirm `uv lock` is up to date and `deptry` reports no issues
  - Ensure all tests pass; ask the user if questions arise
