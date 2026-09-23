# Requirements Document

## Introduction

The ingestion pipeline drains an SQS document queue in batches and reports a single run summary. Today, when a producer emits a malformed message (for example, one missing the required `received_date`), `SqsDocumentSource.fetch_batch` logs an ERROR and permanently deletes the message. Deletion does not route the message to the Dead Letter Queue (DLQ), so the discard is invisible to the run summary: a run that receives only malformed messages reports `0 batch(es), 0 message(s), 0 succeeded, 0 failed; terminal_reason=queue drained.` — all zeros, hiding that a broken message was received and discarded.

This feature makes malformed discards visible and introduces two-tier structured reporting. The document source returns a structured `FetchResult` that carries both the valid jobs and the count of malformed messages discarded on that poll. Batch processing returns a structured `BatchResult` (a `BatchSummary` plus per-document results) and emits exactly one structured batch-summary log record per batch. The run drainer aggregates these into a `RunSummary` whose counts include discarded messages and satisfy the invariant `messages_received == jobs_processed + messages_discarded`, and emits exactly one structured run-summary record. The discard behaviour itself is unchanged — malformed messages are still deleted, not sent to the DLQ; only their visibility in the counts and logs is added.

The plain-text log formatter is retained. Both summaries render their key counts into the human-readable message string and attach the same counts as structured fields via the logging `extra` mechanism. A JSON/structured log sink is out of scope.

## Glossary

- **Ingestion_Pipeline**: The overall system that drains the SQS document queue, processes documents in parallel batches, and reports run and batch outcomes.
- **Document_Source**: The `DocumentSource` `typing.Protocol` in `document_source.py` that supplies batches of work and acknowledges completed jobs. `SqsDocumentSource` is the SQS-backed implementation.
- **Batch_Runner**: The `run_batch` function in `batch_runner.py` that processes one batch of jobs concurrently and returns the batch outcome.
- **Drain_Runner**: The `drain_queue` function in `runner.py` that repeatedly fetches and processes batches until the queue drains or the max-batches ceiling trips, then produces the run summary. `main()` emits the run summary.
- **DocumentJob**: A single self-describing unit of work (one document to ingest), carrying producer metadata and a computed deterministic `source_doc_id`.
- **DocumentResult**: The per-document outcome record produced for each processed batch owner, exposing `success` (True only when processing returned without raising).
- **FetchResult**: A frozen structured value returned by `Document_Source.fetch_batch`, with fields `jobs: list[DocumentJob]` and `malformed_discarded: int`.
- **BatchSummary**: A frozen structured value returned as part of a `BatchResult`, carrying the per-batch aggregate counts: `batch_number`, `jobs_in_batch`, `succeeded`, `failed`, `duplicates_collapsed`.
- **BatchResult**: A frozen structured composite returned by `Batch_Runner.run_batch`, with fields `summary: BatchSummary` and `results: list[DocumentResult]`.
- **RunSummary**: A frozen structured value produced by `Drain_Runner.drain_queue` summarising the whole run: `batches_processed`, `messages_received`, `messages_discarded`, `jobs_processed`, `successes`, `failures`, `terminal_reason`.
- **Malformed_Message**: An SQS message whose body fails to parse or validate (raising `MalformedMessageError`, for example a missing required `received_date`). It is logged and deleted immediately, and permanently discarded — deletion does not route it to the DLQ.
- **Malformed_Discard**: The act of deleting (and thereby permanently discarding) a malformed message. Counted per poll as `malformed_discarded`.
- **messages_received**: The total number of messages pulled off SQS during the run (valid plus malformed), accumulated across every poll including the terminating empty poll.
- **messages_discarded**: The total number of malformed messages discarded during the run, accumulated across every poll including the terminating empty poll.
- **jobs_processed**: The total number of valid jobs received into batches during the run (sum of `FetchResult.jobs` lengths across all polls).
- **jobs_in_batch**: The number of jobs received into a single batch.
- **duplicates_collapsed**: The total number of duplicate jobs folded onto their owners within a single batch (jobs sharing a `source_doc_id` with an earlier job in the same batch).
- **Terminating_Empty_Poll**: The single empty long-poll receive that signals the queue is drained and ends the drain loop. A terminating poll may still carry `malformed_discarded > 0`.
- **Terminal_Reason**: Why the drain loop stopped: `"queue drained"` or `"hit max-batches ceiling"`.
- **DLQ**: The SQS Dead Letter Queue that receives valid messages left unacknowledged after the max receive count. Malformed discards never reach the DLQ.

## Requirements

### Requirement 1: Structured fetch result with discard counting

**User Story:** As a pipeline operator, I want each fetch to report how many malformed messages it discarded, so that malformed producer output is visible rather than silently dropped.

#### Acceptance Criteria

1. THE Document_Source `fetch_batch` method SHALL return a `FetchResult` that exposes a `jobs` field of type `list[DocumentJob]` and a `malformed_discarded` field of type `int`.
2. THE `FetchResult` type SHALL be frozen so a returned value cannot be mutated after construction.
3. THE Document_Source Protocol SHALL declare the return type of `fetch_batch` as `FetchResult`.
4. WHEN `SqsDocumentSource.fetch_batch` completes a poll, THE Document_Source SHALL set `malformed_discarded` to the number of messages that poll deleted as malformed (the count of received messages minus the count of valid jobs).
5. WHEN a poll receives one or more messages and all of them are malformed, THE Document_Source SHALL return a `FetchResult` with an empty `jobs` list and `malformed_discarded` equal to the number of malformed messages discarded.
6. WHEN a poll receives no messages, THE Document_Source SHALL return a `FetchResult` with an empty `jobs` list and `malformed_discarded` equal to `0`.

### Requirement 2: Structured batch summary and result

**User Story:** As a pipeline operator, I want each batch to report a structured summary with its counts, so that I can see per-batch outcomes including how many duplicate jobs were collapsed.

#### Acceptance Criteria

1. THE Batch_Runner `run_batch` function SHALL accept a `batch_number` parameter of type `int` supplied by the caller, numbered from 1 for the first batch of a run.
2. THE Batch_Runner `run_batch` function SHALL return a `BatchResult` that exposes a `summary` field of type `BatchSummary` and a `results` field of type `list[DocumentResult]`.
3. THE `BatchResult` type and THE `BatchSummary` type SHALL each be frozen so a returned value cannot be mutated after construction.
4. THE `BatchSummary` SHALL expose the fields `batch_number`, `jobs_in_batch`, `succeeded`, `failed`, and `duplicates_collapsed`, and SHALL NOT expose a `messages_discarded` field.
5. WHEN `run_batch` processes a batch, THE Batch_Runner SHALL set `BatchSummary.batch_number` to the `batch_number` supplied by the caller.
6. WHEN `run_batch` processes a batch, THE Batch_Runner SHALL set `BatchSummary.jobs_in_batch` to the number of jobs received into the batch.
7. WHEN `run_batch` processes a batch, THE Batch_Runner SHALL set `BatchSummary.succeeded` to the number of `DocumentResult` records with `success` True and `BatchSummary.failed` to the number of `DocumentResult` records with `success` False.
8. WHEN `run_batch` processes a batch, THE Batch_Runner SHALL set `BatchSummary.duplicates_collapsed` to the total number of duplicate jobs folded onto their owners in that batch.
9. THE `BatchResult.results` field SHALL contain one `DocumentResult` per processed owner, consistent with the existing duplicate-collapsing behaviour.

### Requirement 3: Exactly one structured batch-summary log record per batch

**User Story:** As a pipeline operator, I want exactly one structured summary line per batch, so that batch outcomes are unambiguous and machine-readable without duplicate or legacy lines.

#### Acceptance Criteria

1. WHEN `run_batch` completes a batch, THE Batch_Runner SHALL emit exactly one batch-summary log record for that batch.
2. WHEN the Batch_Runner emits the batch-summary record, THE Batch_Runner SHALL render `batch_number`, `jobs_in_batch`, `succeeded`, `failed`, and `duplicates_collapsed` into the log message string.
3. WHEN the Batch_Runner emits the batch-summary record, THE Batch_Runner SHALL attach `batch_number`, `jobs_in_batch`, `succeeded`, `failed`, and `duplicates_collapsed` as structured fields via the logging `extra` mechanism.
4. THE Batch_Runner SHALL replace the legacy `"Batch complete: X succeeded, Y failed (of Z)."` log line with the batch-summary record and SHALL NOT emit both.

### Requirement 4: Run-level drain aggregation

**User Story:** As a pipeline operator, I want the drainer to own batch sequencing and aggregate fetch and batch results, so that the run summary reflects everything the run received, processed, and discarded.

#### Acceptance Criteria

1. THE Drain_Runner `drain_queue` function SHALL assign each started batch a 1-based `batch_number` in the order batches are started and SHALL pass that `batch_number` into `run_batch`.
2. WHEN `drain_queue` receives a `FetchResult`, THE Drain_Runner SHALL read the batch jobs from `FetchResult.jobs` and the discard count from `FetchResult.malformed_discarded`.
3. WHEN `drain_queue` processes a batch, THE Drain_Runner SHALL read the per-document outcomes from `BatchResult.results` and the batch counts from `BatchResult.summary`.
4. THE Drain_Runner SHALL delegate acknowledgement entirely to `run_batch` and the Document_Source and SHALL NOT acknowledge jobs itself.

### Requirement 5: Run summary field model

**User Story:** As a pipeline operator, I want the run summary to carry received, discarded, processed, success, and failure counts, so that I can alert on producer errors and processing outcomes from one record.

#### Acceptance Criteria

1. THE `RunSummary` type SHALL be frozen and SHALL expose the fields `batches_processed`, `messages_received`, `messages_discarded`, `jobs_processed`, `successes`, `failures`, and `terminal_reason`.
2. WHEN `drain_queue` completes a run, THE Drain_Runner SHALL set `messages_received` to the total number of messages pulled off SQS during the run, counting both valid jobs and malformed discards, accumulated across every poll including the terminating empty poll.
3. WHEN `drain_queue` completes a run, THE Drain_Runner SHALL set `messages_discarded` to the sum of `FetchResult.malformed_discarded` across every poll of the run, including the terminating empty poll.
4. WHEN `drain_queue` completes a run, THE Drain_Runner SHALL set `jobs_processed` to the total number of valid jobs received into batches during the run.
5. WHEN `drain_queue` completes a run, THE Drain_Runner SHALL set `successes` to the number of `DocumentResult` records with `success` True and `failures` to the number of `DocumentResult` records with `success` False, across all batches.
6. WHEN `drain_queue` completes a run, THE Drain_Runner SHALL set `batches_processed` to the number of batches started during the run.
7. WHEN the drain loop stops on a terminating empty poll, THE Drain_Runner SHALL set `terminal_reason` to `"queue drained"`.
8. WHEN the drain loop stops because it reached the `MAX_BATCHES_PER_RUN` ceiling, THE Drain_Runner SHALL set `terminal_reason` to `"hit max-batches ceiling"`.

### Requirement 6: Run summary conservation invariant

**User Story:** As a pipeline operator, I want the run summary counts to reconcile exactly, so that I can trust that every message received was either processed or discarded and none were lost from the accounting.

#### Acceptance Criteria

1. WHEN `drain_queue` completes any run, THE Drain_Runner SHALL produce a `RunSummary` in which `messages_received` equals `jobs_processed` plus `messages_discarded`.

### Requirement 7: Exactly one structured run-summary log record per run

**User Story:** As a pipeline operator, I want exactly one structured run-summary line per run, so that I have a single record to alert on with both readable text and machine-readable fields.

#### Acceptance Criteria

1. WHEN a run completes, THE Drain_Runner entry point (`main`) SHALL emit exactly one run-summary log record at INFO level.
2. WHEN `main` emits the run-summary record, THE Drain_Runner SHALL render `batches_processed`, `messages_received`, `messages_discarded`, `jobs_processed`, `successes`, `failures`, and `terminal_reason` into the log message string.
3. WHEN `main` emits the run-summary record, THE Drain_Runner SHALL attach `batches_processed`, `messages_received`, `messages_discarded`, `jobs_processed`, `successes`, `failures`, and `terminal_reason` as structured fields via the logging `extra` mechanism.

### Requirement 8: Motivating-bug regression — malformed-only run is visible

**User Story:** As a pipeline operator, I want a run that receives only malformed messages to report non-zero received and discarded counts, so that a producer emitting broken messages is not hidden behind an all-zero summary.

#### Acceptance Criteria

1. WHEN a run receives one or more messages during the run and all received messages are malformed and the queue then drains, THE Drain_Runner SHALL produce a `RunSummary` with `messages_received` greater than or equal to 1.
2. WHEN a run receives one or more messages during the run and all received messages are malformed and the queue then drains, THE Drain_Runner SHALL produce a `RunSummary` with `messages_discarded` greater than or equal to 1.
3. WHEN a run receives one or more messages during the run and all received messages are malformed and the queue then drains, THE Drain_Runner SHALL set `terminal_reason` to `"queue drained"`.

### Requirement 9: Preserve existing discard and acknowledgement behaviour

**User Story:** As a pipeline operator, I want the new reporting to leave message handling unchanged, so that adding visibility does not alter which messages are discarded, acknowledged, or redriven.

#### Acceptance Criteria

1. WHEN a malformed message is received, THE Document_Source SHALL delete the message and SHALL NOT route the message to the DLQ.
2. WHEN a document is processed successfully, THE Batch_Runner SHALL acknowledge the owner job and all of its collapsed duplicates.
3. IF a document fails processing, THEN THE Batch_Runner SHALL leave the owner job and all of its collapsed duplicates unacknowledged so SQS can redrive them toward the DLQ.

## Out of Scope

The following are explicitly excluded from this feature:

- A JSON or otherwise structured log sink, or a configurable log formatter. The current plain-text formatter is retained; structured fields are attached via `extra` only.
- Routing malformed messages to the DLQ. Malformed messages are still deleted and permanently discarded; only their visibility in counts and logs is added.
- Changing the message contract or `parse_message` behaviour.
- Any worker-pool or concurrency model changes to batch processing.
- Airflow DAG scheduling concerns.
- The known Textract timeout risk.
