# Duplicate Source Key Dedup Bugfix Design

## Overview

A batch of `DocumentJob` items can contain more than one job whose natural key
`(source_file_name, correspondence_type, case_ref)` resolves to the same
deterministic `source_doc_id`. Today this happens when a `SRC_S3_KEY` entry is
repeated in the local-dev stub, and it will happen in production when SQS
redelivers a message (at-least-once delivery). `run_batch` submits every job to a
`ThreadPoolExecutor`, so two workers sharing one `source_doc_id` race on the same
OpenSearch chunk/page document IDs and the same `{case_ref}/{source_doc_id}/pages/`
S3 prefix. One worker's index write can overwrite the other's, and one worker's
failure-path `_cleanup_document` (prefix-deletes page images and deletes OpenSearch
docs by `source_doc_id`) can destroy the other in-flight worker's data. The result
is silent data loss with no explicit policy for acknowledging the duplicates.

The fix collapses duplicate `source_doc_id`s to a single processed unit **at the
batch-processing seam (`run_batch`)**, not at the source. This is deliberate: the
`SRC_S3_KEY` comma-split fan-out in `SqsDocumentSource.fetch_batch` is a throwaway
local-development stub that will be deleted once real SQS is implemented. The real
SQS source will itself produce duplicate-keyed jobs via redelivery, so the
protection must live at the layer that receives a `list[DocumentJob]` and survives
after SQS replaces the stub. `run_batch` is that durable seam.

The dedup keeps exactly one job per distinct `source_doc_id` (the retained
"owner"), processes only the owner, and maps each owner to the full set of jobs
that share its key so that when the owner finishes, every duplicate is
acknowledged (on success) or handled per the failure policy (on failure) —
satisfying the explicit acknowledgement requirement and preventing SQS from
redelivering the dropped duplicates.

## Glossary

- **Bug_Condition (C)**: A batch contains two or more `DocumentJob`s that resolve
  to the same `source_doc_id`.
- **Property (P)**: For a batch triggering the bug, each distinct `source_doc_id`
  is handed to the pipeline at most once, no two in-flight units share a
  `source_doc_id`, and every input job reaches a defined acknowledgement outcome.
- **Preservation**: For a batch with no duplicate `source_doc_id`s, the fixed
  runner behaves exactly as the original — same concurrency, acknowledgement,
  cleanup, classification, deterministic UUID, and empty-batch handling.
- **source_doc_id**: The deterministic Version 5 UUID produced by
  `DocumentIdentifier(source_file_name, correspondence_type, case_ref).generate_uuid()`.
  Keys the OpenSearch chunk/page document IDs and the S3 page-image prefix.
- **owner / retained unit**: The single `DocumentJob` chosen to represent a
  distinct `source_doc_id` in a batch and actually processed by the pipeline.
- **duplicate job**: Any other `DocumentJob` in the same batch sharing an owner's
  `source_doc_id`. Not processed; acknowledged according to the owner's outcome.
- **run_batch**: The function in `src/ingestion_pipeline/runner.py` that receives a
  `list[DocumentJob]` and processes them concurrently — the durable seam where the
  fix lives.
- **process_document_job**: The worker function in `src/ingestion_pipeline/runner.py`
  that computes `source_doc_id` (via `DocumentIdentifier.generate_uuid()`) and runs
  the pipeline for one job.
- **DocumentSource.acknowledge**: The method in
  `src/ingestion_pipeline/orchestration/document_source.py` that marks a job as
  successfully processed so it is not redelivered.

## Bug Details

### Bug Condition

The bug manifests when a batch contains more than one `DocumentJob` resolving to
the same deterministic `source_doc_id`. `run_batch` submits every job to the
`ThreadPoolExecutor` without deduplication, so two or more workers hold the same
`source_doc_id` at once. Those workers then either overwrite each other's
OpenSearch chunk/page documents and shared S3 page-image prefix, or one worker's
failure-path cleanup deletes the other's data. No explicit policy governs which
duplicate is acknowledged.

**Formal Specification:**
```
FUNCTION isBugCondition(batch)
  INPUT: batch of type List<DocumentJob>
  OUTPUT: boolean

  // compute the deterministic source_doc_id for every job
  ids ← [ computeSourceDocId(job) FOR job IN batch ]

  // true when at least two jobs share a source_doc_id
  RETURN hasDuplicates(ids)
END FUNCTION
```

Where `computeSourceDocId(job)` is
`DocumentIdentifier(job.source_file_name, job.correspondence_type, job.case_ref).generate_uuid()`
— the SAME computation `process_document_job` uses today.

### Examples

- **Config repeat (stub, today)**: `SRC_S3_KEY="26-700030/case30.pdf,26-700030/case30.pdf"`.
  `fetch_batch` emits two identical jobs. Both resolve to the same `source_doc_id`.
  Two workers write to the same chunk/page IDs and `26-700030/{source_doc_id}/pages/`
  prefix. Expected: process once; acknowledge both. Actual: they race and can
  overwrite each other.
- **SQS redelivery (production, future)**: SQS delivers a message, then redelivers
  it (at-least-once) within the same batch. Two jobs share a `source_doc_id`.
  Expected: process once; acknowledge both receipt handles per the owner's outcome.
  Actual: two workers race.
- **Failure-path corruption**: Two duplicate-keyed workers run; one fails and calls
  `_cleanup_document`, prefix-deleting page images and deleting OpenSearch docs by
  `source_doc_id`. Expected: cleanup only affects one de-duplicated unit. Actual:
  it deletes the other in-flight worker's just-written data.
- **Edge case (distinct keys)**: A batch of three jobs with three distinct
  `source_doc_id`s. Expected behavior — process all three concurrently, unchanged.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- A batch of only distinct-key jobs is processed concurrently up to
  `MAX_CONCURRENT_DOCUMENTS`, exactly as today.
- A successful job is acknowledged via `DocumentSource.acknowledge` exactly as today.
- A failed job is left unacknowledged, its side effects are cleaned up, and its
  failure is classified (`category`/`retryable`) for downstream redrive/DLQ, exactly
  as today.
- The deterministic `source_doc_id` is derived from
  `(source_file_name, correspondence_type, case_ref)` via
  `DocumentIdentifier.generate_uuid()`, unchanged.
- An empty batch returns `[]` without error.

**Scope:**
All batches that do NOT satisfy the bug condition (i.e. every `source_doc_id` in
the batch is distinct) MUST be completely unaffected by this fix. This includes:
- Single-job batches
- Empty batches
- Multi-job batches where all natural keys are distinct
- The success/failure classification and acknowledgement of each such job

**Note:** The expected correct behavior for the buggy case is defined in the
Correctness Properties section (Property 1). This section focuses on what must NOT
change.

## Hypothesized Root Cause

Based on the bug description, the most likely issues are:

1. **No deduplication at the batch seam**: `run_batch` builds
   `future_to_job = {executor.submit(process_document_job, job, pipeline): job for job in jobs}`
   over the raw `jobs` list. Any duplicate natural keys become concurrent workers
   sharing one `source_doc_id`. There is no grouping by `source_doc_id` before
   submission.

2. **`source_doc_id` computed too late to dedup on it**: The natural-key →
   `source_doc_id` computation currently lives inside `process_document_job`
   (via `DocumentIdentifier(...).generate_uuid()`), i.e. after submission. Dedup
   needs that identifier *before* deciding which jobs to submit, so the computation
   must be extracted into a small pure helper shared by both dedup and processing.

3. **Shared deterministic keys with no ownership**: Because `source_doc_id`
   deterministically keys the OpenSearch chunk/page IDs and the
   `{case_ref}/{source_doc_id}/pages/` S3 prefix, two workers with the same id have
   no isolation. `_cleanup_document` is keyed solely by `source_doc_id`/`case_ref`,
   so a failing duplicate's cleanup is indistinguishable from cleanup of the other
   in-flight unit.

4. **No acknowledgement policy for duplicates**: Only successful jobs are
   acknowledged and only the exact `result.job` is acknowledged. Duplicate jobs
   (extra SQS receipt handles / repeated config entries) have no defined outcome,
   so redelivered duplicates would be left to race again.

The primary root cause is (1)+(2): the durable batch seam never groups jobs by
their deterministic identifier before dispatching them concurrently.

## Correctness Properties

Property 1: Bug Condition - Duplicate source_doc_id is processed once with defined acknowledgement

_For any_ batch where the bug condition holds (`isBugCondition` returns true), the
fixed `run_batch` SHALL hand each distinct `source_doc_id` to the pipeline at most
once (one retained owner per id), SHALL never let two in-flight units share a
`source_doc_id`, and SHALL give every input job a defined acknowledgement outcome —
the retained owner acknowledged/left-for-redrive per its own success/failure, and
each duplicate acknowledged as processed (dropped) when the owner succeeds, or left
for redrive when the owner fails. The collapse of duplicates SHALL be observable: a
structured log entry via the module `logger` identifies the affected `source_doc_id`,
the number of duplicates collapsed, and their S3 URIs / `case_ref` where available.

**Validates: Requirements 2.1, 2.2, 2.3, 2.5, 2.6**

Property 2: Preservation - No-duplicate batches behave exactly as before

_For any_ batch where the bug condition does NOT hold (`isBugCondition` returns
false — every `source_doc_id` distinct), the fixed `run_batch` SHALL produce the
same result as the original `run_batch`: every job processed concurrently up to
`MAX_CONCURRENT_DOCUMENTS`, the same acknowledgement on success, the same
unacknowledged/cleaned-up/classified outcome on failure, the same deterministic
`source_doc_id`, and `[]` for an empty batch.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct, the fix lives entirely at the durable
batch seam (`run_batch`) plus one shared helper. The throwaway `fetch_batch` stub is
intentionally left untouched — its fan-out will be deleted when real SQS lands, and
the real SQS source's redelivered duplicates are caught by the same `run_batch`
dedup.

**File**: `src/ingestion_pipeline/runner.py`

**Function**: `run_batch` (with a new pure helper `compute_source_doc_id`)

**Specific Changes**:

1. **Extract a shared `source_doc_id` helper (single source of truth)**: Add a small
   pure function
   ```
   def compute_source_doc_id(job: DocumentJob) -> str:
       return DocumentIdentifier(
           source_file_name=job.source_file_name,
           correspondence_type=job.correspondence_type,
           case_ref=job.case_ref,
       ).generate_uuid()
   ```
   Refactor `process_document_job` to call this helper instead of constructing the
   identifier inline, so dedup and processing compute `source_doc_id` identically
   (satisfies 3.4 — no change to the computation).

2. **Group jobs by `source_doc_id` in `run_batch` before submission**: Preserving
   input order, build an ordered mapping `source_doc_id -> list[DocumentJob]`. The
   first job seen for an id is the **owner**; the rest are **duplicates**. Submit
   only owners to the `ThreadPoolExecutor`. `max_workers` becomes
   `min(MAX_CONCURRENT_DOCUMENTS, number_of_owners)`. This guarantees at most one
   in-flight unit per `source_doc_id` (2.1, 2.2, 2.3). When one or more duplicates
   are detected for a `source_doc_id`, `run_batch` emits a structured observability
   log entry via the module `logger` (`logger.info`, or `logger.warning`) that names
   the affected `source_doc_id`, the count of duplicate jobs collapsed, and the
   duplicate jobs' S3 URIs / `case_ref` where available — so operators can see that
   redelivered or repeated documents were deduplicated rather than silently
   discarded. This log is emitted at grouping time (when duplicates are identified)
   and/or at acknowledgement time when the collapsed duplicates are dropped
   (satisfies 2.6). It is purely observational and does not alter the dedup or
   acknowledgement behaviour.

3. **Propagate the owner's outcome to its duplicates (acknowledgement policy)**:
   When an owner's future completes:
   - On success: acknowledge the owner (unchanged), then acknowledge every duplicate
     job for that `source_doc_id` (drop the redundant messages so SQS does not
     redeliver them).
   - On failure: leave the owner unacknowledged (unchanged) and also leave its
     duplicates unacknowledged (they will be redelivered/redriven with the owner).
   This satisfies 2.5: the retained unit's outcome determines acknowledgement for
   its duplicates.

4. **Return one `DocumentResult` per owner**: `run_batch` returns results keyed by
   the processed owners (at most one per distinct `source_doc_id`). Duplicate jobs
   are not processed and produce no `DocumentResult`; their handling is captured by
   the acknowledgement policy above. (For a no-duplicate batch every job is its own
   owner, so the returned list is identical to today — Property 2.)

5. **Keep behavior identical for the common path**: When no id repeats, every job is
   an owner with an empty duplicate list, so grouping is a no-op over the input
   order, `max_workers` is unchanged, submission/acknowledge/cleanup/classification
   are unchanged, and an empty batch still short-circuits to `[]` (3.1–3.5).

**Note on `_cleanup_document`**: No change needed. Once dedup guarantees a single
owner per `source_doc_id`, cleanup keyed by `source_doc_id`/`case_ref` can only
affect that one de-duplicated unit, so 2.3 is satisfied structurally by the dedup
rather than by editing cleanup.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples
that demonstrate the bug on unfixed code (duplicate-keyed jobs run concurrently and
can corrupt each other), then verify the fix processes each `source_doc_id` at most
once, applies the acknowledgement policy, and leaves distinct-key batches unchanged.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the
fix. Confirm or refute the root cause (no dedup at the `run_batch` seam). If refuted,
re-hypothesize.

**Test Plan**: Construct batches containing two or more jobs that resolve to the same
`source_doc_id`, run them through the current `run_batch` with a fake/instrumented
pipeline that records every `process_document` invocation (by `source_doc_id`), and
assert on invocation count and concurrency. Run on the UNFIXED code to observe the
duplicate invocations.

**Test Cases**:
1. **Duplicate key single invocation**: Batch of two identical-key jobs; assert the
   pipeline is invoked once for that `source_doc_id` (will fail on unfixed code —
   invoked twice).
2. **Concurrent collision**: Batch of two identical-key jobs with a slow fake
   pipeline; assert no two invocations for the same `source_doc_id` overlap in time
   (will fail on unfixed code — they overlap).
3. **Cleanup isolation**: Batch of two identical-key jobs where one is made to fail;
   assert cleanup for the failing unit does not delete the succeeding unit's data
   (will fail on unfixed code — shared `source_doc_id` cleanup collides).
4. **Duplicate acknowledgement (edge)**: Batch of two identical-key jobs that
   succeed; assert both jobs are acknowledged via the source (may fail on unfixed
   code — only the single processed job is acknowledged, the duplicate is silent).

**Expected Counterexamples**:
- The pipeline `process_document` is invoked more than once for a single
  `source_doc_id`, and invocations overlap concurrently.
- Possible causes: no grouping by `source_doc_id` before submission; `source_doc_id`
  computed inside the worker (too late to dedup); no acknowledgement policy for
  duplicate jobs.

### Fix Checking

**Goal**: Verify that for all batches where the bug condition holds, the fixed
`run_batch` processes each `source_doc_id` at most once and gives every input job a
defined acknowledgement outcome.

**Pseudocode:**
```
FOR ALL batch WHERE isBugCondition(batch) DO
  results := run_batch_fixed(batch)

  // each distinct id handed to the pipeline at most once
  ASSERT FOR ALL id IN distinct(sourceDocIds(batch)):
           count(pipelineInvocations(id)) <= 1

  // no two in-flight units share a source_doc_id
  ASSERT no_concurrent_units_share_source_doc_id(batch)

  // every input job has a defined acknowledgement outcome
  ASSERT FOR ALL job IN batch:
           acknowledgementOutcome(job) IN { ack_as_processed, dropped_as_duplicate, left_for_redrive }
END FOR
```

### Preservation Checking

**Goal**: Verify that for all batches where the bug condition does NOT hold, the
fixed `run_batch` produces the same result as the original.

**Pseudocode:**
```
FOR ALL batch WHERE NOT isBugCondition(batch) DO
  ASSERT run_batch_original(batch) = run_batch_fixed(batch)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking
because:
- It generates many distinct-key batches automatically across the input domain.
- It catches edge cases (batch size boundaries around `MAX_CONCURRENT_DOCUMENTS`,
  single-job and empty batches) that manual unit tests might miss.
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs.

**Test Plan**: Observe behavior on UNFIXED code first for distinct-key batches
(order of results, which jobs are acknowledged, worker count, classification), then
write property-based tests generating batches of jobs with guaranteed-distinct
natural keys and asserting the fixed runner matches the original's observable
outcome.

**Test Cases**:
1. **Distinct-key concurrency**: Observe that a distinct-key batch runs up to
   `MAX_CONCURRENT_DOCUMENTS` workers on unfixed code, then verify this continues
   after the fix.
2. **Success acknowledgement**: Observe that each succeeding distinct-key job is
   acknowledged exactly once on unfixed code, then verify unchanged after the fix.
3. **Failure classification/cleanup**: Observe that a failing distinct-key job is
   left unacknowledged, cleaned up, and classified on unfixed code, then verify
   unchanged after the fix.
4. **Empty batch**: Observe `run_batch([]) == []` on unfixed code, then verify
   unchanged after the fix.

### Unit Tests

- `compute_source_doc_id` returns the same value as the previous inline
  `DocumentIdentifier(...).generate_uuid()` for representative jobs, and equal-key
  jobs collide while distinct-key jobs do not.
- `run_batch` grouping: duplicate-key batch submits one owner per `source_doc_id`;
  duplicate jobs are acknowledged on owner success and left unacknowledged on owner
  failure.
- `run_batch` duplicate-collapse logging: for a duplicate-keyed batch, assert (e.g.
  via `caplog`) that a structured log entry is emitted via the module `logger`
  naming the affected `source_doc_id`, the count of collapsed duplicates, and their
  S3 URIs / `case_ref` where available (2.6); assert no such entry is emitted for a
  distinct-key batch.
- `run_batch` distinct-key batch: one `DocumentResult` per job, correct
  success/failure acknowledgement, `max_workers == min(MAX_CONCURRENT_DOCUMENTS, n)`.
- Empty batch returns `[]`.

### Property-Based Tests

- Generate batches mixing duplicate and distinct keys; assert each distinct
  `source_doc_id` is processed at most once and every input job has a defined
  acknowledgement outcome (Fix Checking / Property 1).
- Generate distinct-key batches of varying size; assert the fixed runner's
  observable outcome (results per job, acknowledgements, classification) matches the
  original (Preservation Checking / Property 2).
- Generate batches with the same key repeated N times; assert exactly one owner is
  processed and N-1 duplicates are acknowledged on success.

### Integration Tests

- Full `run_batch` flow with a duplicate-keyed batch against a fake pipeline and a
  recording `DocumentSource`: assert single processing, single S3 prefix / OpenSearch
  id ownership, and acknowledgement of all duplicate handles on success.
- Full flow with a failing owner: assert the owner and its duplicates are left
  unacknowledged for redrive, and cleanup affects only the single de-duplicated unit.
- Full flow with a distinct-key batch: assert end-to-end behavior is identical to
  the pre-fix baseline (concurrency, acknowledgement, classification).
