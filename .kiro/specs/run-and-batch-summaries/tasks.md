# Implementation Plan: run-and-batch-summaries

## Overview

Make malformed-message discards visible via two-tier structured reporting. Work proceeds
bottom-up along the orchestration seam so each return-type change is immediately followed
by fixing the tests it breaks: first the leaf models (`FetchResult`, `BatchSummary`,
`BatchResult`), then the producers that return them (`fetch_batch`, `run_batch`), then a
checkpoint to confirm the ripple is contained, and finally `drain_queue`/`RunSummary`/`main`
in `runner.py`. Each production task is paired with the test UPDATES that keep the existing
suite green, plus the new assertions the feature requires. Language: Python 3.12 (uv,
Hatchling, pytest + moto + pytest-mock + hypothesis, ruff line length 120, Google-style
docstrings on source only, 90% coverage enforced).

## Tasks

- [x] 1. Add batch-summary data models in `document_result.py`
  - [x] 1.1 Add `BatchSummary` and `BatchResult` frozen dataclasses
    - In `src/ingestion_pipeline/orchestration/batch_processing/document_result.py`, after `DocumentResult`, add `@dataclass(frozen=True) BatchSummary` with `int` fields `batch_number`, `jobs_in_batch`, `succeeded`, `failed`, `duplicates_collapsed` (no `messages_discarded` field)
    - Add `@dataclass(frozen=True) BatchResult` with `summary: BatchSummary` and `results: list[DocumentResult]`
    - Google-style docstrings on both
    - _Requirements: 2.3, 2.4_

  - [ ]* 1.2 Unit-test field set and frozen behaviour for both models
    - In `tests/orchestration/batch_processing/test_document_result.py`, assert `BatchSummary` exposes exactly the five fields and no `messages_discarded`; assert `BatchResult` exposes `summary` and `results`
    - Assert both raise on attribute mutation (frozen)
    - _Requirements: 2.3, 2.4_

- [x] 2. Add `FetchResult` and thread it through the document source
  - [x] 2.1 Add `FetchResult` model and change `fetch_batch` return type
    - In `src/ingestion_pipeline/orchestration/document_source.py`, after `DocumentJob`, add frozen pydantic `FetchResult(BaseModel)` with `model_config = ConfigDict(frozen=True)`, `jobs: list[DocumentJob] = Field(default_factory=list)`, `malformed_discarded: int = Field(default=0, ge=0)`
    - Change `DocumentSource` Protocol `fetch_batch` return annotation to `FetchResult`
    - Change `SqsDocumentSource.fetch_batch` return annotation to `FetchResult`; normal path returns `FetchResult(jobs=jobs, malformed_discarded=len(messages) - len(jobs))`; transient-error early return returns `FetchResult(jobs=[], malformed_discarded=0)`; empty receive yields `jobs=[]`, `malformed_discarded=0`
    - Leave the malformed-delete path (`_delete_message`) untouched — malformed messages are still deleted, never DLQ'd
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 9.1_

  - [x] 2.2 Update `test_document_source.py` for the `FetchResult` return type
    - In `tests/orchestration/test_document_source.py`, change `test_fetch_batch_returns_jobs_for_valid_messages`, `test_fetch_batch_deletes_malformed_and_continues`, and `test_fetch_batch_and_acknowledge_end_to_end_with_moto` to read `result.jobs` instead of treating the return as a list
    - Change the empty-receive and both transient-receive-error tests to assert `FetchResult(jobs=[], malformed_discarded=0)`
    - Add a mixed valid+malformed test asserting `malformed_discarded` equals the discarded count; add an all-malformed test asserting `jobs == []` and `malformed_discarded >= 1`
    - Confirm `test_fetch_batch_permanent_receive_error_propagates` still raises (unaffected)
    - _Requirements: 1.1, 1.4, 1.5, 1.6_

  - [ ]* 2.3 Property test for fetch discard accounting
    - In `tests/orchestration/test_document_source.py`, against a mocked SQS client generate polls with `V >= 0` valid and `M >= 0` malformed bodies; assert `len(result.jobs) == V` and `result.malformed_discarded == M`
    - **Feature: run-and-batch-summaries, Property 1: Fetch discard accounting**
    - **Validates: Requirements 1.4, 1.5, 1.6**

- [x] 3. Change `run_batch` to accept `batch_number` and return `BatchResult`
  - [x] 3.1 Update `run_batch` signature, counts, and batch-summary log record
    - In `src/ingestion_pipeline/orchestration/batch_processing/batch_runner.py`, change signature to `run_batch(jobs, pipeline, source, batch_number: int) -> BatchResult`
    - Empty-batch guard returns `BatchResult(summary=BatchSummary(batch_number, 0, 0, 0, 0), results=[])`
    - After the executor block compute `succeeded = sum(r.success for r)`, `failed = len(results) - succeeded`, `duplicates_collapsed = sum(len(dups) for dups in duplicates_by_id.values())`, `jobs_in_batch = len(jobs)`
    - Replace the legacy `"Batch complete: ..."` `logger.info` with exactly one batch-summary record rendering `batch_number`, `jobs_in_batch`, `succeeded`, `failed`, `duplicates_collapsed` into the message AND attaching the same five via `extra`; return `BatchResult(summary, results)`
    - Preserve all internals verbatim: owner/`duplicates_by_id` collapsing, per-duplicate WARNING, `max_workers`, `ThreadPoolExecutor`, acknowledge-owner-and-duplicates-on-success
    - _Requirements: 2.1, 2.2, 2.5, 2.6, 2.7, 2.8, 2.9, 3.1, 3.2, 3.3, 3.4, 9.2, 9.3_

  - [x] 3.2 Update `test_batch_runner.py` call sites to consume `BatchResult`
    - In `tests/orchestration/batch_processing/test_batch_runner.py`, pass `batch_number` at every `run_batch` call site and read `.results` for existing assertions in `test_run_batch_empty_returns_no_results`, `test_run_batch_processes_all_and_acknowledges_only_successes`, `test_run_batch_caps_workers_at_max_concurrent_documents`, `test_run_batch_caps_workers_at_job_count_when_fewer_jobs`, `test_run_batch_executes_documents_concurrently`, `test_run_batch_does_not_acknowledge_pipeline_failure`
    - Update the duplicate-key exploration tests (`test_explore_*`, `test_explore_property_duplicate_key_repeated_n_times`) and the preservation property tests (`test_preserve_*`) to consume `BatchResult`
    - Add a test asserting exactly one batch-summary record and NO `"Batch complete"` record, with the five counts in message and `extra`
    - _Requirements: 2.1, 2.2, 2.6, 2.7, 2.8, 2.9, 3.1, 3.4_

  - [ ]* 3.3 Property test for BatchSummary counts
    - Generate batches with arbitrary duplicate structure and per-owner outcomes; assert `summary.jobs_in_batch == len(jobs)`, `summary.succeeded + summary.failed == len(results) == distinct owners`, `summary.duplicates_collapsed == len(jobs) - distinct owners`, and `jobs_in_batch == succeeded + failed + duplicates_collapsed`
    - **Feature: run-and-batch-summaries, Property 2: BatchSummary counts equal the batch aggregates**
    - **Validates: Requirements 2.6, 2.7, 2.8, 2.9**

  - [ ]* 3.4 Property test for preserved batch acknowledgement
    - Extend the retained preservation test to consume `BatchResult`: on owner success the owner and all collapsed duplicates are acknowledged; on owner failure they are all left unacknowledged
    - **Feature: run-and-batch-summaries, Property 5: Batch acknowledgement preserved**
    - **Validates: Requirements 9.2, 9.3**

- [x] 4. Checkpoint — confirm the return-type ripple is fixed
  - Run `uv run pytest tests/orchestration/` to confirm `document_source` and `batch_runner` and their dependents are green before touching `runner.py`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Update `runner.py` — `RunSummary`, `drain_queue`, and `main`
  - [x] 5.1 Extend `RunSummary` to the seven-field model
    - In `src/ingestion_pipeline/runner.py`, add `messages_discarded: int` and `jobs_processed: int` to the frozen `RunSummary`
    - Update the `Attributes:` docstring to document all seven fields and correct the stale `messages_received` description (now valid jobs plus malformed discards, not "sum of `len(jobs)`")
    - _Requirements: 5.1_

  - [x] 5.2 Rework `drain_queue` to aggregate fetch and batch results
    - Read `fetch_result.jobs` and `fetch_result.malformed_discarded`; account every poll — `messages_received += len(jobs) + malformed_discarded`, `messages_discarded += malformed_discarded`, `jobs_processed += len(jobs)` — BEFORE the empty-poll `break`
    - Increment `batches_processed` before calling `run_batch(jobs, pipeline, source, batch_number=batches_processed)` for 1-based sequencing; consume `BatchResult.results` for `successes`/`failures`
    - Set `terminal_reason` `"queue drained"` on empty poll and `"hit max-batches ceiling"` on the loop `else`; construct the seven-field `RunSummary`; never call `source.acknowledge`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.1_

  - [x] 5.3 Update `main` run-summary log record
    - Render all seven fields into the INFO message (keeping the `"Pipeline run summary"` prefix) and attach the same seven via `extra`
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 5.4 Update `test_runner.py` fakes, patches, and constructions
    - Make `_FakeDocumentSource.fetch_batch` and `_InexhaustibleDocumentSource.fetch_batch` return `FetchResult`; make `run_batch` patches accept `batch_number` and return `BatchResult`
    - Add the two new fields to every `RunSummary(...)` construction in `test_main_*`; update `test_main_emits_single_structured_summary_log` to assert the new message substrings and the new `extra` attributes; update `drain_queue` tests to assert the new fields
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.1, 7.2, 7.3_

- [x] 6. Regression, invariant, and behaviour-preservation tests
  - [x] 6.1 Motivating-bug regression test (malformed-only run)
    - In `tests/test_runner.py`, a fake source yields `FetchResult(jobs=[], malformed_discarded>=1)` then a terminating empty poll; assert `messages_received >= 1`, `messages_discarded >= 1`, `terminal_reason == "queue drained"`
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 6.2 Exactly-one run-summary record test
    - Mock `drain_queue`; assert exactly one INFO `"Pipeline run summary"` record carrying all seven values in message and `extra`
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 6.3 `batch_number` sequencing test
    - Multi-batch drain; assert `run_batch` received `batch_number` 1, 2, 3… in start order
    - _Requirements: 4.1_

  - [x] 6.4 Preserved discard / no-direct-ack test
    - Assert malformed messages are deleted and not DLQ'd (moto/mock) and that `drain_queue` never calls `source.acknowledge` directly (delegation intact)
    - _Requirements: 4.4, 9.1_

  - [ ]* 6.5 Property test for run-summary field aggregation
    - Generate finite poll sequences (scripted `FetchResult`s ending in an empty terminating poll that may still carry discards) with a patched `run_batch` returning matching `BatchResult`s; assert `messages_received`, `messages_discarded`, `jobs_processed`, `batches_processed`, `successes`/`failures` equal their cross-poll totals, including the terminating poll's discards
    - **Feature: run-and-batch-summaries, Property 3: Run summary field aggregation across all polls**
    - **Validates: Requirements 5.2, 5.3, 5.4, 5.5, 5.6**

  - [ ]* 6.6 Property test for run-summary conservation invariant
    - For any completed run (drained or ceiling-terminated), assert `messages_received == jobs_processed + messages_discarded`
    - **Feature: run-and-batch-summaries, Property 4: Run summary conservation invariant**
    - **Validates: Requirements 6.1**

- [x] 7. Final checkpoint — full suite, coverage, and lint
  - Run `uv run pytest tests/` (must meet the 90% coverage threshold); run `uv run ruff format` and `uv run ruff check` on changed files
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (property-based tests) and can be skipped for a faster MVP; all production changes, the test UPDATES that fix broken existing tests, the motivating-bug regression, the exactly-one-record tests, and the checkpoints are REQUIRED.
- Each task references specific requirement IDs for traceability; each property test is tagged with its property number and the requirements it validates.
- Ordering pairs each return-type change with its test fixes so the suite never stays red across tasks; the checkpoint at task 4 confirms the `document_source`/`batch_runner` ripple is contained before `runner.py` changes begin.
- Out of scope (no tasks): JSON/structured log sink or configurable formatter, DLQ routing of malformed messages, message-contract/`parse_message` changes, worker-pool/concurrency changes, Airflow scheduling, Textract timeout risk.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "3.1"] },
    { "id": 2, "tasks": ["2.3", "3.2"] },
    { "id": 3, "tasks": ["3.3"] },
    { "id": 4, "tasks": ["3.4"] },
    { "id": 5, "tasks": ["5.1"] },
    { "id": 6, "tasks": ["5.2"] },
    { "id": 7, "tasks": ["5.3"] },
    { "id": 8, "tasks": ["5.4"] },
    { "id": 9, "tasks": ["6.1"] },
    { "id": 10, "tasks": ["6.2"] },
    { "id": 11, "tasks": ["6.3"] },
    { "id": 12, "tasks": ["6.4"] },
    { "id": 13, "tasks": ["6.5"] },
    { "id": 14, "tasks": ["6.6"] }
  ]
}
```
