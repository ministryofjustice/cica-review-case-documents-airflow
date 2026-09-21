# Design Document

## Overview

This design turns the ingestion pipeline runner from a single-batch processor into a
bounded queue-draining runner. Today `runner.main()` fetches exactly one batch from the
SQS document queue and processes it once. This change:

1. Extracts the drain logic into a testable `drain_queue(source, pipeline)` function that
   repeatedly runs `fetch_batch` then `run_batch` until the queue is empty or a per-run
   batch ceiling is reached, returning a `RunSummary`. (Requirements 1, 2, 3, 4)
2. Reduces `main()` to thin wiring that builds the pipeline, constructs the source, calls
   `drain_queue`, and emits one structured INFO summary log. (Requirements 4, 5)
3. Adds a DLQ redrive policy for repeatedly failing messages, represented locally by the
   LocalStack init script (production DLQ/redrive is provisioned by Analytical Platform
   IaC outside this repository). (Requirements 6, 7)
4. Adds and validates the supporting settings: a derived DLQ queue name,
   `SQS_MAX_RECEIVE_COUNT`, and `MAX_BATCHES_PER_RUN`. (Requirement 8)
5. Updates the steering docs to describe the drain-loop and DLQ behaviour.
   (Requirement 9)

The change is deliberately small and additive. It reuses the existing
`DocumentSource`/`SqsDocumentSource`, `run_batch`, `DocumentResult`, `config.Settings`
validator conventions, and `custom_logging` mechanisms rather than introducing new
abstractions.

### Language and Tooling

- Python 3.12, managed with `uv` and built with Hatchling.
- Data models use `pydantic` (frozen `BaseModel` / `ConfigDict(frozen=True)`), consistent
  with `DocumentJob`. Simple internal outcome records use `@dataclass`, consistent with
  `DocumentResult`.
- Tests use `pytest` with `pytest-mock` and `moto`; property tests use `hypothesis`
  (already present in the repo, per `.hypothesis/`). 90% coverage is enforced; test files
  are exempt from Google-style docstring rules (ruff D-rules suppressed). Line length 120.

## Architecture

### Current flow (single batch)

```
main()
 ├─ check_opensearch_health()          # fatal on failure -> return
 ├─ build_pipeline()
 ├─ SqsDocumentSource()                # fatal QueueResolutionError -> sys.exit(1)
 ├─ jobs = source.fetch_batch()        # ONE poll
 └─ run_batch(jobs, pipeline, source)  # ONE batch
```

### New flow (bounded drain loop)

```
main()                                       # thin wiring (Req 4.3, 5)
 ├─ check_opensearch_health()                # fatal on failure -> return
 ├─ build_pipeline()
 ├─ SqsDocumentSource()                       # fatal QueueResolutionError -> sys.exit(1) (Req 4.4)
 ├─ summary = drain_queue(source, pipeline)   # bounded loop (Req 1,2,3,4)
 └─ logger.info("run summary", extra={...})   # exactly one structured INFO record (Req 5)

drain_queue(source, pipeline) -> RunSummary
 └─ loop (Req 1,2,3):
      while batches_processed < MAX_BATCHES_PER_RUN:
        jobs = source.fetch_batch()            # one long-poll receive
        if not jobs:                            # Empty_Poll (Req 1.2, 1.3)
          terminal_reason = "queue drained"
          break
        batches_processed += 1                  # count STARTED batches (Req 1.4, 3.1)
        messages_received += len(jobs)          # (Req 4.2)
        results = run_batch(jobs, pipeline, source)   # blocks; shutdown(wait=True) joins (Req 2.1, 2.2)
        successes += sum(1 for r in results if r.success)     # (Req 4.2)
        failures  += sum(1 for r in results if not r.success) # (Req 4.2)
      else:                                     # loop exhausted the ceiling (Req 3.1)
        terminal_reason = "hit max-batches ceiling"
        logger.warning(...)                     # exactly one WARNING (Req 3.2)
      return RunSummary(...)
```

Termination is evaluated only between batches: the loop condition is checked before each
`fetch_batch`, and `run_batch` is a blocking call whose `ThreadPoolExecutor` context
manager performs `shutdown(wait=True)` on exit, so no jobs are in flight once it returns
(Requirements 2.1, 2.2, 2.3). The ceiling prevents a *new* batch from starting; it never
interrupts a batch already running.

### Component boundaries

| Component | Location | Responsibility | Requirements |
|-----------|----------|----------------|--------------|
| `drain_queue` | `src/ingestion_pipeline/runner.py` | Bounded drain loop; aggregates counts; returns `RunSummary` | 1, 2, 3, 4.1, 4.2 |
| `RunSummary` | `src/ingestion_pipeline/runner.py` | Immutable per-run summary object | 4.2, 5.2 |
| `main` | `src/ingestion_pipeline/runner.py` | Thin wiring + single structured summary log | 4.3, 4.4, 5 |
| `Settings` additions | `src/ingestion_pipeline/config.py` | `SQS_DOCUMENT_DLQ`, `SQS_MAX_RECEIVE_COUNT`, `MAX_BATCHES_PER_RUN` + validators | 8 |
| Init script | `local-dev-environment/init-scripts/01-create-aws-resources.sh` | Idempotent DLQ + redrive wiring | 6, 7 |
| Steering docs | `.kiro/steering/product.md`, `structure.md` | Describe drain-loop and DLQ | 9 |

## Components and Interfaces

### 1. `drain_queue(source, pipeline)`

**Placement:** in `runner.py`, alongside `main()`. The requirements name it as part of the
Drain_Runner (Glossary) and Requirement 4 pairs it with the thin `main()`; keeping both in
`runner.py` keeps the entry point and its extracted loop in one module and matches the
existing "runner" boundary.

**Signature:**

```python
def drain_queue(source: DocumentSource, pipeline: Pipeline) -> RunSummary:
    """Repeatedly fetch and process batches until the queue drains or the ceiling trips.

    Runs the bounded drain loop: on each iteration it fetches one batch from ``source``
    and, if non-empty, processes it with ``run_batch``. The loop stops on the first
    empty poll (the queue is drained) or once ``settings.MAX_BATCHES_PER_RUN`` batches
    have been started (the ceiling). Termination is evaluated only between batches, so a
    batch already running is always allowed to finish; ``run_batch``'s ThreadPoolExecutor
    joins all workers before returning.

    Args:
        source (DocumentSource): Supplies batches and acknowledges completed jobs.
        pipeline (Pipeline): The shared, thread-safe pipeline instance.

    Returns:
        RunSummary: Aggregate counts and the terminal reason for the run.
    """
```

**Behaviour and accounting:**

- The loop counts **started** batches, not returned results, so hitting the ceiling
  reflects "how many batches this run began" (Requirements 1.4, 3.1).
- `messages_received` accumulates `len(jobs)` from each non-empty `fetch_batch`
  (Requirement 4.2). Note this counts valid jobs after `SqsDocumentSource` has already
  discarded malformed messages; that matches "messages received as work".
- `successes` / `failures` accumulate over `DocumentResult.success` across each
  `run_batch` result list (Requirement 4.2). Because `run_batch` collapses duplicate
  `source_doc_id`s, `successes + failures` equals the number of processed owners, which
  can be `<= messages_received` when a batch contains duplicates. This is intentional and
  documented; the three counts are reported independently.
- `terminal_reason` is `"queue drained"` when the loop breaks on an empty poll, and
  `"hit max-batches ceiling"` when the `while` condition falls through at the ceiling
  (Requirements 1.2, 3.1, 5.4).
- The loop is expressed as `while batches_processed < MAX_BATCHES_PER_RUN:` with a
  `for/else`-style ceiling branch (or an explicit post-loop check) so the ceiling reason
  is set exactly when the loop exits without an empty poll. `drain_queue` returns normally
  in both cases — it never raises on the ceiling path (Requirement 3.3).
- `drain_queue` performs **no** acknowledgement itself: acknowledgement is entirely
  `run_batch`/`source`'s responsibility (delete on success, leave unacknowledged on
  failure). Thus messages for failed jobs are naturally left in the queue for redrive,
  including when the ceiling trips (Requirements 3.4, 6.3).

**WARNING placement decision:** the ceiling WARNING is emitted **inside `drain_queue`**, at
the point the loop exits on the ceiling, not in `main()`. Justification: `drain_queue` is
the component that knows *why* it stopped and owns the `MAX_BATCHES_PER_RUN` decision;
emitting there keeps the warning colocated with the condition and means any caller (not
just `main`) gets the operator signal. `main()` still emits the single structured INFO
summary regardless of terminal reason, so the two log records are complementary: one
WARNING (only on the ceiling path, Requirement 3.2) and always exactly one INFO summary
(Requirement 5.1).

### 2. `RunSummary`

**Definition:** a small frozen `pydantic` `BaseModel`, defined in `runner.py`.

```python
class RunSummary(BaseModel):
    """Immutable summary of a single drain run.

    Carries the aggregate counts the operator alerts on plus the reason the drain loop
    stopped. Frozen so a returned summary cannot be mutated by a caller before it is
    logged.
    """

    model_config = ConfigDict(frozen=True)

    batches_processed: int
    messages_received: int
    successes: int
    failures: int
    terminal_reason: str  # "queue drained" | "hit max-batches ceiling"
```

**Placement justification:** local to `runner.py` rather than in `data_models/`. The
`data_models/` directory does not currently exist in the source tree (the steering table
lists it aspirationally), and `RunSummary` is only produced by `drain_queue` and consumed
by `main()` in the same module — it is not a shared cross-module model like `DocumentJob`.
Keeping it beside its single producer/consumer avoids a new package for one internal type,
consistent with how `DocumentResult` lives next to `run_batch`.

**Type choice justification:** a frozen `pydantic.BaseModel` (matching `DocumentJob`'s
`ConfigDict(frozen=True)`) rather than a `@dataclass`. It is returned across a function
boundary and then logged; immutability guards against accidental mutation between creation
and logging, and `model_dump()` gives a clean dict for the structured `extra` payload. A
`@dataclass(frozen=True)` would also be acceptable and consistent with `DocumentResult`;
`BaseModel` is chosen because the object crosses a boundary and is serialised into a log
record, where `model_dump()` is convenient. (Requirements 4.2, 5.2)

### 3. `main()` thin wiring

```python
def main():
    """Entry point: health check, build pipeline, drain the queue, log one summary."""
    if settings.LOCAL_DEVELOPMENT_MODE:
        logger.warning("Running in LOCAL_DEVELOPMENT_MODE. Ensure your S3 URIs are accessible in LocalStack.")

    logger.info("Pipeline runner started.")
    if not check_opensearch_health(
        settings.OPENSEARCH_PROXY_URL,
        verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
        ssl_assert_hostname=settings.OPENSEARCH_SSL_ASSERT_HOSTNAME,
    ):
        logger.critical("OpenSearch health check failed. Exiting pipeline runner.")
        return

    pipeline = build_pipeline()

    try:
        source: DocumentSource = SqsDocumentSource()
    except QueueResolutionError as exc:
        logger.critical(f"Could not connect to the SQS document queue; exiting: {exc}")
        sys.exit(1)

    summary = drain_queue(source, pipeline)

    # Exactly one structured INFO summary record, via the existing custom_logging setup.
    logger.info(
        "Pipeline run summary.",
        extra={
            "batches_processed": summary.batches_processed,
            "messages_received": summary.messages_received,
            "successes": summary.successes,
            "failures": summary.failures,
            "terminal_reason": summary.terminal_reason,
        },
    )
```

- The health-check-fail path keeps the existing `return` (not `sys.exit`), matching
  current behaviour; only the `QueueResolutionError` path exits with code 1
  (Requirement 4.4).
- The order health check → `build_pipeline` → `SqsDocumentSource` → `drain_queue` → log is
  preserved from today's `main()` (Requirement 4.3).
- The summary is emitted with `extra={...}` carrying exactly the five fields
  (Requirements 5.1, 5.2, 5.3). `custom_logging.setup_logging()` (already called at module
  import) installs the `ContextFilter`; passing structured data via `extra` is the
  existing mechanism and does not conflict with the `source_doc_id` context filter, which
  operates on `record.msg`. The message string stays constant so operators can match on it
  and read the fields from `extra`.
- Whether the run drained or hit the ceiling, `main()` emits this one INFO record; the
  WARNING (ceiling only) comes from `drain_queue`.

### 4. Config additions (`config.py`)

Three settings are added, following the existing `@field_validator` conventions:

```python
# -- Drain loop --
# Maximum number of batches a single run may START. A safety ceiling so a large backlog
# cannot produce an unbounded run; remaining work is left for the next scheduled run.
MAX_BATCHES_PER_RUN: int = 50

# -- SQS DLQ / redrive --
# Number of times a message may be received without being deleted before SQS redrives it
# to the DLQ. Mirrors the RedrivePolicy maxReceiveCount used by the init script / IaC.
SQS_MAX_RECEIVE_COUNT: int = 3

# The DLQ queue name. Empty by default; the derived value "<SQS_DOCUMENT_QUEUE>-dlq" is
# filled in by a model validator so it always tracks the main queue name unless overridden.
SQS_DOCUMENT_DLQ: str = ""
```

**Validators** (existing style — `@field_validator` for single-field range checks,
`@model_validator(mode="after")` for the cross-field derivation):

```python
@field_validator("SQS_MAX_RECEIVE_COUNT")
@classmethod
def validate_sqs_max_receive_count(cls, v: int) -> int:
    """Ensure the DLQ max receive count is at least 1 so redrive can ever trigger."""
    if v < 1:
        raise ValueError("SQS_MAX_RECEIVE_COUNT must be >= 1")
    return v

@field_validator("MAX_BATCHES_PER_RUN")
@classmethod
def validate_max_batches_per_run(cls, v: int) -> int:
    """Ensure at least one batch can be started per run."""
    if v < 1:
        raise ValueError("MAX_BATCHES_PER_RUN must be >= 1")
    return v
```

**Derived DLQ name — approach and justification (Requirements 7.1, 8.1):**

A pydantic field default cannot reference another field's value, so the derived
`"<SQS_DOCUMENT_QUEUE>-dlq"` cannot be expressed as a plain field default. Two viable
approaches:

- **(A) `@model_validator(mode="after")`** that fills `SQS_DOCUMENT_DLQ` from
  `SQS_DOCUMENT_QUEUE` when it was left blank, preserving any explicit override. Runs after
  `SQS_DOCUMENT_QUEUE` has been validated and stripped, so the derived name uses the clean
  value. Because the model is mutable during validation (settings is not frozen), the
  validator assigns the field and returns `self`, matching the existing
  `@model_validator(mode="after")` pattern in this file.
- **(B) a computed `@property`** `sqs_document_dlq` with no stored field.

**Chosen: (A) model validator writing a real field.** Justification: it produces a
concrete, overridable setting (`SQS_DOCUMENT_DLQ` can be set via env/.env, satisfying "a
DLQ queue name setting"), it is consistent with the file's several existing
`@model_validator(mode="after")` methods, and a stored value is easier to log and to feed
to code/scripts than a property. A property (B) cannot be overridden by configuration,
which conflicts with Requirement 8.1's "setting that defaults to the derived value".

```python
@model_validator(mode="after")
def derive_sqs_document_dlq(self) -> "Settings":
    """Default the DLQ name to ``<SQS_DOCUMENT_QUEUE>-dlq`` when left unset.

    A field default cannot reference another field, so the derived name is filled in
    here after ``SQS_DOCUMENT_QUEUE`` has been validated and stripped. An explicit
    ``SQS_DOCUMENT_DLQ`` (env/.env) is preserved.
    """
    if not self.SQS_DOCUMENT_DLQ:
        self.SQS_DOCUMENT_DLQ = f"{self.SQS_DOCUMENT_QUEUE}-dlq"
    return self
```

**`validate_visibility_covers_processing` regression (Requirement 8.7):** the new settings
do not touch `SQS_MAX_MESSAGES_PER_POLL` (4), `MAX_CONCURRENT_DOCUMENTS` (4),
`TEXTRACT_API_JOB_TIMEOUT_SECONDS` (600), `SQS_PROCESSING_OVERHEAD_FACTOR` (1.5), or
`SQS_VISIBILITY_TIMEOUT_SECONDS` (1800). The enforced minimum is
`ceil(ceil(4/4) * 600 * 1.5) = 900`, and `1800 >= 900`, so the existing validator still
passes at unchanged defaults. A regression test pins this.

### 5. LocalStack init script changes (Requirements 6, 7)

The DLQ name is derived consistently with config: `<SQS_DOCUMENT_QUEUE>-dlq`. The redrive
policy is applied after both queues exist, **including when the main queue already exists**
(Requirement 7.5), so re-running produces the same wiring (Requirement 7.6). The script is
already sentinel-aware (`AWS_READY_SENTINEL` / `AWS_FAILED_SENTINEL`) and uses idempotent
`create-if-absent` checks; the DLQ block follows the same shape as the existing main-queue
block.

Inserted after the main-queue create/skip block (replacing the current single-queue
section), using `awslocal`:

```bash
# --- Create SQS main queue (idempotent) ---
if ! awslocal sqs get-queue-url --queue-name "${SQS_DOCUMENT_QUEUE_NAME}" >/dev/null 2>&1; then
  echo "Creating queue ${SQS_DOCUMENT_QUEUE_NAME}..."
  awslocal sqs create-queue --queue-name "${SQS_DOCUMENT_QUEUE_NAME}"
else
  echo "Queue ${SQS_DOCUMENT_QUEUE_NAME} already exists. Skipping creation."
fi

# --- Create DLQ (idempotent) ---
# Derive the DLQ name from the main queue name (matches Settings.SQS_DOCUMENT_DLQ default).
SQS_DOCUMENT_DLQ_NAME="${SQS_DOCUMENT_DLQ:-${SQS_DOCUMENT_QUEUE_NAME}-dlq}"
if ! awslocal sqs get-queue-url --queue-name "${SQS_DOCUMENT_DLQ_NAME}" >/dev/null 2>&1; then
  echo "Creating DLQ ${SQS_DOCUMENT_DLQ_NAME}..."
  awslocal sqs create-queue --queue-name "${SQS_DOCUMENT_DLQ_NAME}"
else
  echo "DLQ ${SQS_DOCUMENT_DLQ_NAME} already exists. Skipping creation."
fi

# --- Wire the redrive policy on the main queue (applied every run, even if the
#     main queue already existed, so re-runs converge to the same wiring) ---
DLQ_URL="$(awslocal sqs get-queue-url --queue-name "${SQS_DOCUMENT_DLQ_NAME}" --query 'QueueUrl' --output text)"
DLQ_ARN="$(awslocal sqs get-queue-attributes \
  --queue-url "${DLQ_URL}" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)"

MAIN_QUEUE_URL="$(awslocal sqs get-queue-url --queue-name "${SQS_DOCUMENT_QUEUE_NAME}" --query 'QueueUrl' --output text)"
REDRIVE_POLICY="$(printf '{"deadLetterTargetArn":"%s","maxReceiveCount":"3"}' "${DLQ_ARN}")"
awslocal sqs set-queue-attributes \
  --queue-url "${MAIN_QUEUE_URL}" \
  --attributes "$(printf '{"RedrivePolicy":%s}' "$(printf '%s' "${REDRIVE_POLICY}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")"
echo "Applied RedrivePolicy (maxReceiveCount=3) targeting ${DLQ_ARN}."
```

Notes:
- `maxReceiveCount` is `3`, matching `SQS_MAX_RECEIVE_COUNT` (Requirements 6.1, 7.4). The
  `RedrivePolicy` attribute value must itself be a JSON *string* (SQS requires the value
  JSON-encoded), which is why it is double-encoded above; a simpler equivalent is to write
  the policy to a temp file and pass `--attributes file://...`. Either form is acceptable
  as long as `RedrivePolicy` is a JSON-encoded string.
- The ARN is fetched via `get-queue-attributes ... QueueArn` (Requirement 7.3).
- The `set-queue-attributes` runs unconditionally after the create/skip blocks, so it
  applies even when the main queue already existed (Requirement 7.5) and is idempotent on
  re-run (Requirement 7.6). Sentinel handling is unchanged.
- `SQS_DOCUMENT_QUEUE` is already a required env var in the script; `SQS_DOCUMENT_DLQ` is
  optional and falls back to the derived name, matching config.

### 6. Steering doc updates (Requirement 9)

- `.kiro/steering/product.md` → **Current Status**: note that the runner drains the queue
  across multiple batches per run up to `MAX_BATCHES_PER_RUN`, and that repeatedly failing
  messages are redriven to a DLQ after `SQS_MAX_RECEIVE_COUNT` receives.
- `.kiro/steering/structure.md` → the `runner.py` row and `orchestration/` description:
  change "run batch" to describe the bounded drain loop (`drain_queue`) and the DLQ
  redrive behaviour.

## Data Models

### `RunSummary` (new)

| Field | Type | Meaning |
|-------|------|---------|
| `batches_processed` | `int` | Number of batches **started** this run. |
| `messages_received` | `int` | Sum of `len(jobs)` over each non-empty `fetch_batch`. |
| `successes` | `int` | Count of `DocumentResult.success is True` across all `run_batch` results. |
| `failures` | `int` | Count of `DocumentResult.success is False` across all `run_batch` results. |
| `terminal_reason` | `str` | `"queue drained"` or `"hit max-batches ceiling"`. |

### Existing models reused (unchanged)

- `DocumentJob` — supplies `len(jobs)` per batch and travels through `run_batch`.
- `DocumentResult` — `.success` drives `successes`/`failures` aggregation.
- `DocumentSource` protocol — `fetch_batch()` / `acknowledge()`; `drain_queue` only calls
  `fetch_batch`, delegating `acknowledge` to `run_batch`.

## Error Handling

- **Empty poll:** not an error — the drained terminal condition (Requirement 1.2).
- **Transient receive errors:** already handled inside `SqsDocumentSource.fetch_batch`,
  which returns `[]`. This makes a transient blip look like an empty poll and ends the run
  as "queue drained". This is an accepted, pre-existing behaviour of the source; the drain
  loop does not attempt to distinguish it and Requirement 1.3 explicitly treats a single
  empty poll as drained. (Documented, not changed.)
- **Permanent receive errors:** `fetch_batch` re-raises; the exception propagates out of
  `drain_queue` and `main()`, failing the run visibly rather than reporting a false
  "drained". No new handling added.
- **Per-document failures:** contained by `run_batch`/`process_document_job` as
  `DocumentResult(success=False)`; counted in `failures` and left unacknowledged for
  redrive.
- **`QueueResolutionError`:** caught in `main()` → `sys.exit(1)` (Requirement 4.4).
- **Ceiling:** not an error — clean stop; one WARNING, no exception (Requirements 3.2,
  3.3).

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Drain loop consumes every non-empty batch then stops on the first empty poll

*For any* finite sequence of non-empty batches followed by an empty poll, where the number
of non-empty batches is below `MAX_BATCHES_PER_RUN`, `drain_queue` calls `run_batch` exactly
once per non-empty batch in order, stops on the empty poll, and returns a `RunSummary` whose
`terminal_reason` is `"queue drained"`.

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: Run summary counts are the exact aggregates of the batches processed

*For any* sequence of batches drained before the ceiling, the returned `RunSummary` satisfies:
`batches_processed` equals the number of non-empty batches started, `messages_received`
equals the sum of the job counts of those batches, and `successes` and `failures` equal the
counts of `DocumentResult.success` being true and false respectively across all `run_batch`
results.

**Validates: Requirements 1.4, 4.1, 4.2, 5.4**

### Property 3: The ceiling stops the run at a batch boundary after exactly `MAX_BATCHES_PER_RUN` batches

*For any* batch ceiling `n >= 1` and any source that never returns an empty batch,
`drain_queue` starts exactly `n` batches, never requests an `(n+1)`-th batch, returns
normally without raising, and returns a `RunSummary` with `batches_processed == n` and
`terminal_reason == "hit max-batches ceiling"`.

**Validates: Requirements 2.3, 3.1, 3.3, 5.4**

### Property 4: The DLQ name setting defaults to the derived value and preserves overrides

*For any* valid `SQS_DOCUMENT_QUEUE` name, constructing `Settings` without
`SQS_DOCUMENT_DLQ` yields `SQS_DOCUMENT_DLQ == f"{SQS_DOCUMENT_QUEUE}-dlq"`, and for any
valid explicit override the provided value is preserved unchanged.

**Validates: Requirements 7.1, 8.1**

### Property 5: Bounds validators reject values below one and accept values at or above one

*For any* integer less than 1 assigned to `SQS_MAX_RECEIVE_COUNT` or `MAX_BATCHES_PER_RUN`,
`Settings` construction raises a validation error; *for any* integer greater than or equal
to 1, construction succeeds with that value.

**Validates: Requirements 8.3, 8.5**

## Testing Strategy

Dual approach: property-based tests (hypothesis, minimum 100 iterations each) for the
input-varying invariants above, and example/integration tests for fixed scenarios,
wiring, and external-service behaviour. 90% coverage is enforced; test files are exempt
from Google-style docstring rules.

Each property test is tagged: **Feature: queue-drain-runner, Property {number}: {property_text}**.

### `drain_queue` unit tests (`tests/.../test_runner.py`)

Use a **fake `DocumentSource`** implementing the protocol: it is seeded with a list of
batches to return from successive `fetch_batch` calls and records `acknowledge` calls.
`run_batch` is patched/faked to return a caller-supplied list of `DocumentResult`s per
batch (so no real pipeline runs), and to record its call order.

- **Property 1 (drained path):** hypothesis generates a list of non-empty batches (varied
  counts/sizes) below the ceiling; the fake yields them then `[]`. Assert `run_batch`
  invoked once per non-empty batch in order, and `RunSummary.terminal_reason == "queue
  drained"`.
- **Property 2 (accounting):** hypothesis generates per-batch job counts and per-job
  success/failure outcomes; the fake `run_batch` returns matching `DocumentResult`s.
  Assert all five `RunSummary` fields equal independently computed expectations, and the
  return type is `RunSummary`.
- **Property 3 (ceiling path):** hypothesis generates a ceiling `n >= 1` (monkeypatch
  `settings.MAX_BATCHES_PER_RUN`); the fake source is inexhaustible (always non-empty).
  Assert exactly `n` batches started, `fetch_batch` called exactly `n` times (never an
  `(n+1)`-th that would start a new batch), no exception raised, `batches_processed == n`,
  and `terminal_reason == "hit max-batches ceiling"`.
- **Batch-boundary termination (example, Req 2.3):** with the ceiling reached, assert the
  loop does not call `fetch_batch` again after the last allowed batch, and that a batch
  already handed to `run_batch` is always allowed to return before any termination check
  (the fake `run_batch` records that it returned before the loop stopped).
- **Delegation (example, Req 3.4, 6.3):** assert `drain_queue` itself makes no
  `source.acknowledge` calls beyond those performed inside `run_batch` (acknowledgement is
  delegated), so failed-job messages are left in the queue.
- **WARNING emission (example, Req 3.2):** with `caplog`, assert exactly one WARNING record
  on the ceiling path and zero such WARNINGs on the drained path.

### `main()` wiring tests (`tests/.../test_runner.py`)

- **Wiring order (example, Req 4.3):** mock `check_opensearch_health`, `build_pipeline`,
  `SqsDocumentSource`, and `drain_queue`; assert call order and that `drain_queue` receives
  the built source and pipeline.
- **Summary log (example, Req 5.1, 5.2, 5.3):** make `drain_queue` return a known
  `RunSummary`; with `caplog`, assert exactly one INFO summary record whose `extra`
  contains `{batches_processed, messages_received, successes, failures, terminal_reason}`
  equal to the summary, emitted via `logger.info(..., extra=...)`.
- **Queue resolution failure (example, Req 4.4):** make `SqsDocumentSource()` raise
  `QueueResolutionError`; assert `SystemExit` with code 1.
- **Health-check failure (example):** make the health check return `False`; assert
  `main()` returns without building a source or draining.

### Config validator tests (`tests/.../test_config.py`)

- **Property 4 (derived DLQ name):** hypothesis generates valid queue names (regex
  `[A-Za-z0-9_-]{1,80}`); assert unset `SQS_DOCUMENT_DLQ` resolves to `name + "-dlq"` and a
  valid explicit override is preserved. (Construct `Settings(SQS_DOCUMENT_QUEUE=..., ...)`
  directly.)
- **Property 5 (bounds):** hypothesis generates ints `< 1` (expect `ValidationError`) and
  ints `>= 1` (expect acceptance) for `SQS_MAX_RECEIVE_COUNT` and `MAX_BATCHES_PER_RUN`.
- **Defaults (examples, Req 8.2, 8.4):** assert `SQS_MAX_RECEIVE_COUNT == 3` and
  `MAX_BATCHES_PER_RUN == 50` on a default `Settings`.
- **Visibility regression (example, Req 8.7):** construct `Settings` at defaults
  (`MAX_CONCURRENT_DOCUMENTS=4`, `SQS_MAX_MESSAGES_PER_POLL=4`) and assert construction
  succeeds — `validate_visibility_covers_processing` still passes (`1800 >= 900`).

### DLQ redrive integration test (`tests/.../test_dlq_redrive.py`, moto)

moto supports SQS `RedrivePolicy` and moves messages to the DLQ after `maxReceiveCount`
receives, so the end-to-end redrive is testable in-process without LocalStack.

1. Under `@mock_aws`, create the DLQ, read its `QueueArn`, then create the main queue with
   `RedrivePolicy = {"deadLetterTargetArn": <dlq_arn>, "maxReceiveCount": "3"}` and a short
   `VisibilityTimeout` (e.g. 0) so receives can be repeated immediately.
2. Send one message to the main queue.
3. Receive it 3 times **without deleting** (allowing visibility to lapse between receives).
4. Assert the main queue is now empty and the DLQ holds exactly that message
   (Requirements 6.2, 6.5). This validates the redrive wiring the init script/IaC
   configures (Requirements 6.1, 7.4) without asserting on LocalStack shell behaviour.

This is an **integration** test (1 representative message), not property-based: the redrive
count is a fixed constant (3) and the behaviour is SQS's, not our code's.

### Not unit-tested (SMOKE / infra)

The init-script steps (create DLQ, fetch ARN, set redrive, idempotent re-run —
Requirements 7.2, 7.3, 7.5, 7.6) and the steering-doc edits (Requirement 9) are shell/
documentation changes verified by local re-runs, not Python unit tests. Their *effect*
(redrive after 3 receives) is covered by the moto integration test.

## Out of Scope

- A worker-pool model for batch dispatch.
- Airflow DAG scheduling concerns, including `max_active_runs=1`.
- Any maximum-runtime or wall-clock ceiling on a run; the only ceiling is
  `MAX_BATCHES_PER_RUN`.

## Known Risk / TODO (document only, not addressed by this feature)

- `TEXTRACT_API_JOB_TIMEOUT_SECONDS` is 600 seconds (10 minutes), below the ~20 minutes a
  ~1500-page document can take. The pilot's documents of up to 100 pages are unaffected.
  This gap requires further analysis and is intentionally not fixed here. (Carried forward
  from requirements.)
