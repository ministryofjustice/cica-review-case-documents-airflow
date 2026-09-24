# Requirements Document

## Introduction

This feature turns the ingestion pipeline runner from a single-batch processor into a
queue-draining runner. Today `main()` fetches exactly one batch from the SQS document
queue and processes it. This change introduces a bounded drain loop that repeatedly
fetches and processes batches until the queue is empty or a per-run batch ceiling is
reached, extracts a testable `drain_queue` function, wires a Dead Letter Queue (DLQ)
with a redrive policy for repeatedly failing messages, adds the supporting
configuration settings, and emits a single structured per-run summary log record.

The pilot runs on the Ministry of Justice Analytical Platform under Airflow, processing
CICA case documents (each up to 100 pages in the pilot). The production DLQ and redrive
policy are provisioned by Analytical Platform infrastructure-as-code outside this
repository; the LocalStack init script represents that wiring for local development.

## Glossary

- **Drain_Runner**: The queue-draining runner component. Comprises the thin `main()`
  wiring and the extracted `drain_queue(source, pipeline)` function that repeatedly
  fetches and processes batches until termination.
- **Drain_Loop**: The bounded loop inside `drain_queue` that repeats
  `fetch_batch` then `run_batch` until termination.
- **Source**: A `DocumentSource` implementation (`SqsDocumentSource` in production) that
  supplies batches of `DocumentJob` items and acknowledges completed work.
- **Batch**: One set of `DocumentJob` items returned by a single `fetch_batch`
  long-poll receive and processed by one `run_batch` call.
- **Empty_Poll**: A single long-poll `fetch_batch` receive that returns zero jobs,
  interpreted by the Drain_Runner as the queue being drained.
- **Run_Summary**: A run-summary object returned by `drain_queue` carrying
  `batches_processed`, `messages_received`, `successes`, `failures`, and
  `terminal_reason`.
- **Terminal_Reason**: The reason the Drain_Loop stopped, one of
  `"queue drained"` or `"hit max-batches ceiling"`.
- **Batch_Ceiling**: The maximum number of batches a single run may start, configured by
  `MAX_BATCHES_PER_RUN`.
- **DLQ**: The Dead Letter Queue that receives messages redriven from the main queue
  after they reach the maximum receive count.
- **Redrive_Policy**: The SQS main-queue attribute pairing a `deadLetterTargetArn` with a
  `maxReceiveCount`, causing SQS to move a message to the DLQ once it has been received
  `maxReceiveCount` times without deletion.
- **Init_Script**: The LocalStack local-development init script
  `local-dev-environment/init-scripts/01-create-aws-resources.sh` that provisions local
  AWS resources.
- **Settings**: The `pydantic-settings` configuration object in
  `src/ingestion_pipeline/config.py`.
- **Config_Author**: A developer or operator who configures the pipeline via environment
  variables or `.env`.
- **Operator**: A person responsible for running and monitoring the pipeline.

## Requirements

### Requirement 1: Bounded drain loop

**User Story:** As an Operator, I want a single run to keep processing batches until the
queue is empty, so that a scheduled run drains outstanding work instead of leaving most
of the queue for the next run.

#### Acceptance Criteria

1. WHEN a run starts, THE Drain_Runner SHALL repeat the sequence of one `fetch_batch`
   followed by one `run_batch` until a termination condition is reached.
2. WHEN a `fetch_batch` receive returns zero jobs, THE Drain_Runner SHALL stop the
   Drain_Loop and set Terminal_Reason to `"queue drained"`.
3. THE Drain_Runner SHALL treat a single Empty_Poll as the signal that the queue is
   drained.
4. WHILE the count of started batches is below `MAX_BATCHES_PER_RUN` and the most recent
   `fetch_batch` returned one or more jobs, THE Drain_Runner SHALL start a further batch.

### Requirement 2: Batch-boundary-only termination

**User Story:** As an Operator, I want the run to stop only between batches, so that a
document already being processed is never abandoned mid-flight.

#### Acceptance Criteria

1. THE Drain_Runner SHALL evaluate termination conditions only between batches, after
   the current `run_batch` call has returned.
2. WHILE a `run_batch` call is executing, THE Drain_Runner SHALL allow that batch to
   complete with all in-flight jobs finished before evaluating any termination condition.
3. WHEN the Batch_Ceiling is reached, THE Drain_Runner SHALL prevent a new batch from
   starting and SHALL NOT interrupt any batch that is already executing.

### Requirement 3: Graceful ceiling stop

**User Story:** As an Operator, I want the run to stop cleanly when it hits the batch
ceiling, so that a long backlog does not cause an unbounded or crashing run and remaining
work is left safely for the next run.

#### Acceptance Criteria

1. WHEN the number of started batches reaches `MAX_BATCHES_PER_RUN`, THE Drain_Runner
   SHALL stop the Drain_Loop and set Terminal_Reason to `"hit max-batches ceiling"`.
2. WHEN the Batch_Ceiling terminates the Drain_Loop, THE Drain_Runner SHALL emit one
   WARNING log record recording that the run stopped at the Batch_Ceiling.
3. WHEN the Batch_Ceiling terminates the Drain_Loop, THE Drain_Runner SHALL complete
   without raising an exception.
4. WHEN the Batch_Ceiling terminates the Drain_Loop, THE Drain_Runner SHALL leave
   messages that were not acknowledged during the run in the main queue for a subsequent
   run.

### Requirement 4: Testable drain function and thin main wiring

**User Story:** As a developer, I want the drain logic extracted into a testable
function, so that termination behaviour can be unit tested without exercising the full
`main()` wiring.

#### Acceptance Criteria

1. THE Drain_Runner SHALL expose a `drain_queue(source, pipeline)` function that runs the
   Drain_Loop and returns a Run_Summary.
2. WHEN `drain_queue` returns, THE Run_Summary SHALL carry `batches_processed`,
   `messages_received`, `successes`, `failures`, and `terminal_reason`.
3. WHEN `main()` runs, THE Drain_Runner SHALL perform the OpenSearch health check, build
   the pipeline, construct an `SqsDocumentSource`, call `drain_queue`, and log the
   Run_Summary.
4. IF constructing the `SqsDocumentSource` raises a `QueueResolutionError`, THEN THE
   Drain_Runner SHALL exit the process with status code 1.

### Requirement 5: Structured per-run summary logging

**User Story:** As an Operator, I want one structured summary log line at the end of each
run, so that I can alert on run outcomes without parsing multi-line output.

#### Acceptance Criteria

1. WHEN a run finishes, THE Drain_Runner SHALL emit exactly one structured INFO log
   record summarising the run.
2. THE Drain_Runner SHALL include the fields `batches_processed`, `messages_received`,
   `successes`, `failures`, and `terminal_reason` in the summary log record.
3. THE Drain_Runner SHALL emit the summary using the existing `custom_logging` context
   and structured `extra` mechanism.
4. THE Drain_Runner SHALL set `terminal_reason` in the summary to `"queue drained"` when
   the run ended on an Empty_Poll and to `"hit max-batches ceiling"` when the run ended
   at the Batch_Ceiling.

### Requirement 6: DLQ redrive after repeated receives

**User Story:** As an Operator, I want repeatedly failing messages to move to a DLQ, so
that poison messages stop being retried indefinitely and can be inspected separately.

#### Acceptance Criteria

1. WHERE the local development environment is used, THE Init_Script SHALL configure the
   main queue with a Redrive_Policy whose `maxReceiveCount` is 3.
2. WHEN a message has been received 3 times without being acknowledged, THE main queue
   SHALL move that message to the DLQ.
3. THE Drain_Runner SHALL leave a job that fails processing unacknowledged so that SQS
   can redrive it.
4. WHILE a run is in progress, THE Drain_Runner SHALL rely on
   `SQS_VISIBILITY_TIMEOUT_SECONDS` (default 1800 seconds) exceeding a single pilot
   run's duration so that an unacknowledged failed message does not reappear within the
   same run.
5. WHEN a failed message's visibility timeout expires between runs, THE main queue SHALL
   increment that message's receive count on the next scheduled run until the count
   reaches 3.

### Requirement 7: LocalStack DLQ wiring idempotency

**User Story:** As a developer, I want the local init script to set up the DLQ and
redrive policy repeatably, so that re-running the local environment produces the same
wiring without errors.

#### Acceptance Criteria

1. THE Init_Script SHALL derive the DLQ queue name from the main queue name with the
   default form `<SQS_DOCUMENT_QUEUE>-dlq`.
2. WHEN the Init_Script runs, THE Init_Script SHALL create the DLQ if the DLQ does not
   already exist.
3. WHEN the Init_Script runs, THE Init_Script SHALL fetch the DLQ ARN using
   `get-queue-attributes` with attribute `QueueArn`.
4. WHEN the Init_Script runs, THE Init_Script SHALL set the main queue Redrive_Policy
   using `set-queue-attributes` with `deadLetterTargetArn` set to the DLQ ARN and
   `maxReceiveCount` set to 3.
5. WHILE the main queue already exists, THE Init_Script SHALL still apply the
   Redrive_Policy to the main queue.
6. WHEN the Init_Script runs more than once, THE Init_Script SHALL produce the same
   resources and redrive wiring without failing, remaining sentinel-aware.

### Requirement 8: Configuration settings and validation

**User Story:** As a Config_Author, I want the new drain and DLQ settings validated at
startup, so that invalid configuration fails during Settings construction rather than
mid-run.

#### Acceptance Criteria

1. THE Settings SHALL provide a DLQ queue name setting that defaults to the derived value
   `<SQS_DOCUMENT_QUEUE>-dlq`.
2. THE Settings SHALL provide `SQS_MAX_RECEIVE_COUNT` with a default of 3.
3. IF `SQS_MAX_RECEIVE_COUNT` is less than 1, THEN THE Settings SHALL raise a validation
   error during construction.
4. THE Settings SHALL provide `MAX_BATCHES_PER_RUN` with a default of 50.
5. IF `MAX_BATCHES_PER_RUN` is less than 1, THEN THE Settings SHALL raise a validation
   error during construction.
6. THE Settings SHALL implement the new setting validators using the existing
   `@field_validator` style.
7. WHILE `MAX_CONCURRENT_DOCUMENTS` is 4 and `SQS_MAX_MESSAGES_PER_POLL` is 4, THE
   Settings SHALL continue to satisfy the existing `validate_visibility_covers_processing`
   validator with the new settings at their defaults.

### Requirement 9: Steering documentation updates

**User Story:** As a developer, I want the steering docs to describe the drain-loop and
DLQ behaviour, so that project documentation reflects the runner's actual orchestration.

#### Acceptance Criteria

1. WHEN this feature is delivered, THE Drain_Runner delivery SHALL update the Current
   Status section of `.kiro/steering/product.md` to reflect the drain-loop and DLQ
   behaviour.
2. WHEN this feature is delivered, THE Drain_Runner delivery SHALL update the
   orchestration description in `.kiro/steering/structure.md` to reflect the drain-loop
   and DLQ behaviour.

## Assumptions

- The production DLQ and Redrive_Policy are provisioned by Analytical Platform
  infrastructure-as-code outside this repository. The Init_Script only represents that
  wiring for local development.
- `SQS_VISIBILITY_TIMEOUT_SECONDS` (default 1800 seconds) exceeds the duration of a
  single pilot run, so unacknowledged failed messages do not reappear within the same
  run and instead accumulate receive count across subsequent scheduled runs.
- The external-kill case (Airflow task timeout, SIGKILL, or pod eviction) is a
  redelivery path, not a Drain_Loop exit: in-flight jobs die, their unacknowledged
  messages become visible again after `SQS_VISIBILITY_TIMEOUT_SECONDS`, and a later run
  reprocesses them (at-least-once delivery).
- `run_batch` uses `with ThreadPoolExecutor(...)`, so its context-manager exit performs
  `shutdown(wait=True)` and guarantees no jobs are in flight once `run_batch` returns.

## Out of Scope

- A worker-pool model for batch dispatch.
- Airflow DAG scheduling concerns, including `max_active_runs=1`.
- Any maximum-runtime or wall-clock ceiling on a run; the only ceiling in this feature is
  `MAX_BATCHES_PER_RUN`.

## Known Risk / TODO (document only, not addressed by this feature)

- `TEXTRACT_API_JOB_TIMEOUT_SECONDS` is 600 seconds (10 minutes), which is below the
  approximately 20 minutes a roughly 1500-page document can take. The pilot's documents
  of up to 100 pages are unaffected. This gap requires further analysis and is
  intentionally not fixed by this feature.
