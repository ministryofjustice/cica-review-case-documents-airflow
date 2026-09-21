# Implementation Plan: Queue Drain Runner

## Overview

This plan turns the single-batch runner into a bounded queue-draining runner. Work proceeds
bottom-up: first the config settings and their validators (the drain loop and init script
both depend on them), then the `RunSummary` model and `drain_queue` loop, then the thin
`main()` wiring that consumes them, then the DLQ redrive integration test and LocalStack
init-script wiring, and finally the steering-doc updates and a verification pass. Each task
builds on the previous ones and ends by wiring the new code into `main()` so nothing is left
orphaned.

Language: Python 3.12 (uv, Hatchling). Tests use `pytest` with `pytest-mock`, `moto`, and
`hypothesis`. Ruff line length 120, Google-style docstrings on source only (test files exempt),
90% coverage enforced.

Property-based tests and the moto DLQ integration test are marked optional (`*`); example/unit
tests, all implementation, the init-script change, and steering updates are required.

## Tasks

- [x] 1. Add drain-loop and DLQ settings to `config.py`
  - [x] 1.1 Add the three settings and their validators
    - Add `MAX_BATCHES_PER_RUN: int = 50`, `SQS_MAX_RECEIVE_COUNT: int = 3`, and `SQS_DOCUMENT_DLQ: str = ""` to `Settings` in `src/ingestion_pipeline/config.py`
    - Add `@field_validator("MAX_BATCHES_PER_RUN")` and `@field_validator("SQS_MAX_RECEIVE_COUNT")` class methods that raise `ValueError` when the value is `< 1`, matching the existing `@field_validator` style
    - Add `@model_validator(mode="after")` `derive_sqs_document_dlq` that sets `SQS_DOCUMENT_DLQ = f"{self.SQS_DOCUMENT_QUEUE}-dlq"` only when it is unset, preserving explicit overrides, and returns `self`
    - Add Google-style docstrings to each validator
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 1.2 Write property test for the derived DLQ name
    - **Feature: queue-drain-runner, Property 4: The DLQ name setting defaults to the derived value and preserves overrides**
    - Hypothesis-generate valid queue names (regex `[A-Za-z0-9_-]{1,80}`); assert unset `SQS_DOCUMENT_DLQ` resolves to `name + "-dlq"` and a valid explicit override is preserved
    - **Validates: Requirements 7.1, 8.1**

  - [ ]* 1.3 Write property test for the bounds validators
    - **Feature: queue-drain-runner, Property 5: Bounds validators reject values below one and accept values at or above one**
    - Hypothesis-generate ints `< 1` (expect `ValidationError`) and ints `>= 1` (expect acceptance) for both `SQS_MAX_RECEIVE_COUNT` and `MAX_BATCHES_PER_RUN`
    - **Validates: Requirements 8.3, 8.5**

  - [x] 1.4 Write example/unit tests for defaults and the visibility regression
    - In `tests/test_config.py`: assert `SQS_MAX_RECEIVE_COUNT == 3` and `MAX_BATCHES_PER_RUN == 50` on a default `Settings`
    - Add a regression example constructing `Settings` at defaults (`MAX_CONCURRENT_DOCUMENTS=4`, `SQS_MAX_MESSAGES_PER_POLL=4`) and assert construction succeeds so `validate_visibility_covers_processing` still passes (`1800 >= 900`)
    - _Requirements: 8.2, 8.4, 8.7_

- [x] 2. Implement `RunSummary` and `drain_queue` in `runner.py`
  - [x] 2.1 Add the `RunSummary` model
    - Define a frozen `pydantic` `BaseModel` `RunSummary` in `src/ingestion_pipeline/runner.py` with `model_config = ConfigDict(frozen=True)` and fields `batches_processed: int`, `messages_received: int`, `successes: int`, `failures: int`, `terminal_reason: str`
    - Add a Google-style docstring
    - _Requirements: 4.2, 5.2_

  - [x] 2.2 Implement the `drain_queue(source, pipeline)` function
    - Add `drain_queue(source: DocumentSource, pipeline: Pipeline) -> RunSummary` to `runner.py`
    - Implement the bounded loop `while batches_processed < settings.MAX_BATCHES_PER_RUN:`; on each iteration call `source.fetch_batch()`; on an empty poll set `terminal_reason = "queue drained"` and break; otherwise increment `batches_processed`, add `len(jobs)` to `messages_received`, call `run_batch(jobs, pipeline, source)`, and accumulate `successes`/`failures` from `DocumentResult.success`
    - On the ceiling path (loop condition falls through) set `terminal_reason = "hit max-batches ceiling"` and emit exactly one `logger.warning(...)` inside `drain_queue`; return normally without raising
    - Do not call `source.acknowledge` in `drain_queue`; delegate acknowledgement entirely to `run_batch`
    - Return a `RunSummary` with the accumulated counts and terminal reason; add a Google-style docstring
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2_

  - [ ]* 2.3 Write property test for the drained path
    - **Feature: queue-drain-runner, Property 1: Drain loop consumes every non-empty batch then stops on the first empty poll**
    - Use a fake `DocumentSource` seeded with non-empty batches (varied counts/sizes, below the ceiling) then `[]`; patch/fake `run_batch` to record call order; assert `run_batch` invoked once per non-empty batch in order and `terminal_reason == "queue drained"`
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [ ]* 2.4 Write property test for summary accounting
    - **Feature: queue-drain-runner, Property 2: Run summary counts are the exact aggregates of the batches processed**
    - Hypothesis-generate per-batch job counts and per-job success/failure outcomes; fake `run_batch` returns matching `DocumentResult`s; assert all five `RunSummary` fields equal independently computed expectations and the return type is `RunSummary`
    - **Validates: Requirements 1.4, 4.1, 4.2, 5.4**

  - [ ]* 2.5 Write property test for the ceiling path
    - **Feature: queue-drain-runner, Property 3: The ceiling stops the run at a batch boundary after exactly `MAX_BATCHES_PER_RUN` batches**
    - Hypothesis-generate a ceiling `n >= 1` (monkeypatch `settings.MAX_BATCHES_PER_RUN`) with an inexhaustible fake source; assert exactly `n` batches started, `fetch_batch` called exactly `n` times (never an `(n+1)`-th), no exception raised, `batches_processed == n`, and `terminal_reason == "hit max-batches ceiling"`
    - **Validates: Requirements 2.3, 3.1, 3.3, 5.4**

  - [x] 2.6 Write example/unit tests for termination, delegation, and WARNING emission
    - Batch-boundary termination: assert the loop does not call `fetch_batch` again after the last allowed batch and that a batch handed to `run_batch` always returns before termination is evaluated
    - Delegation: assert `drain_queue` itself makes no `source.acknowledge` calls beyond those inside `run_batch`, leaving failed-job messages in the queue
    - WARNING emission: with `caplog`, assert exactly one WARNING record on the ceiling path and zero on the drained path
    - _Requirements: 2.3, 3.2, 3.4, 6.3_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Refactor `main()` to thin wiring in `runner.py`
  - [x] 4.1 Reduce `main()` to health-check → build → source → drain → summary log
    - Preserve the order: `check_opensearch_health` (return early on failure), `build_pipeline`, construct `SqsDocumentSource` (on `QueueResolutionError` log critical and `sys.exit(1)`), call `drain_queue(source, pipeline)`
    - Emit exactly one structured INFO record via `logger.info("Pipeline run summary.", extra={...})` carrying the five fields `batches_processed`, `messages_received`, `successes`, `failures`, `terminal_reason` from the returned `RunSummary`
    - Remove the old single-poll/single-`run_batch` logic now superseded by `drain_queue`
    - _Requirements: 4.3, 4.4, 5.1, 5.2, 5.3_

  - [x] 4.2 Write example/unit tests for `main()` wiring
    - Wiring order: mock `check_opensearch_health`, `build_pipeline`, `SqsDocumentSource`, `drain_queue`; assert call order and that `drain_queue` receives the built source and pipeline
    - Summary log: make `drain_queue` return a known `RunSummary`; with `caplog`, assert exactly one INFO summary record whose `extra` contains the five fields equal to the summary
    - Queue resolution failure: make `SqsDocumentSource()` raise `QueueResolutionError`; assert `SystemExit` with code 1
    - Health-check failure: make the health check return `False`; assert `main()` returns without building a source or draining
    - _Requirements: 4.3, 4.4, 5.1, 5.2, 5.3, 5.4_

- [ ] 5. Add the DLQ redrive integration test
  - [ ]* 5.1 Write the moto DLQ redrive integration test
    - In `tests/orchestration/test_dlq_redrive.py`, under `@mock_aws`: create the DLQ, read its `QueueArn`, create the main queue with `RedrivePolicy = {"deadLetterTargetArn": <dlq_arn>, "maxReceiveCount": "3"}` and a short `VisibilityTimeout`
    - Send one message; receive it 3 times without deleting; assert the main queue is empty and the DLQ holds exactly that message
    - _Requirements: 6.1, 6.2, 6.5, 7.4_

- [x] 6. Wire the DLQ and redrive policy into the LocalStack init script
  - [x] 6.1 Add idempotent DLQ creation and redrive wiring
    - In `local-dev-environment/init-scripts/01-create-aws-resources.sh`, derive the DLQ name as `${SQS_DOCUMENT_DLQ:-${SQS_DOCUMENT_QUEUE_NAME}-dlq}`, consistent with `Settings.SQS_DOCUMENT_DLQ`
    - Create the DLQ only if it does not already exist (idempotent create/skip)
    - Fetch the DLQ ARN via `get-queue-attributes --attribute-names QueueArn`
    - Apply the main-queue `RedrivePolicy` (JSON-encoded string) with `deadLetterTargetArn` and `maxReceiveCount=3` via `set-queue-attributes`, running unconditionally after the create/skip blocks so it applies even when the main queue already exists, remaining sentinel-aware and idempotent on re-run
    - _Requirements: 6.1, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 7. Update steering documentation
  - [x] 7.1 Update product and structure steering docs
    - In `.kiro/steering/product.md`, update the Current Status section to note the runner drains the queue across multiple batches per run up to `MAX_BATCHES_PER_RUN` and that repeatedly failing messages are redriven to a DLQ after `SQS_MAX_RECEIVE_COUNT` receives
    - In `.kiro/steering/structure.md`, update the `runner.py` row and `orchestration/` description to describe the bounded drain loop (`drain_queue`) and the DLQ redrive behaviour
    - _Requirements: 9.1, 9.2_

- [x] 8. Final checkpoint - Verify build, tests, coverage, and lint
  - [x] 8.1 Run the production test suite and linters
    - Run `uv run pytest tests/` and confirm all tests pass with the enforced 90% coverage still holding
    - Run `uv run ruff format` and `uv run ruff check` and resolve any issues on changed files
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 8.1, 8.2, 8.4_

## Notes

- Tasks marked with `*` are optional (property-based tests and the moto DLQ integration test) and can be skipped for a faster MVP; example/unit tests, implementation, the init-script change, and steering updates are required.
- Each task references specific requirement IDs for traceability.
- Checkpoints ensure incremental validation.
- Property tests validate the universal correctness properties (1–5) from the design; unit/example tests cover fixed scenarios, wiring, and external-service behaviour.
- The LocalStack init-script change (task 6.1) is verified by a local re-run, not a Python unit test.
- Out of scope (no tasks): worker-pool model, Airflow DAG scheduling, and any wall-clock/runtime ceiling. `TEXTRACT_API_JOB_TIMEOUT_SECONDS` is a documented known-risk TODO and is intentionally not changed by this feature.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4", "2.5", "2.6"] },
    { "id": 4, "tasks": ["4.1"] },
    { "id": 5, "tasks": ["4.2", "5.1", "6.1", "7.1"] },
    { "id": 6, "tasks": ["8.1"] }
  ]
}
```
