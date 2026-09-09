# JIRA Tickets — SQS Queue-Driven Document Processing (with requirement traceability)

> Traceability version. Each story links back to the requirement numbers in `requirements.md`.
> The epic groups the work; stories are independently deliverable slices.

---

## Epic: Add SQS queue-driven document processing to the ingestion pipeline

**Summary:** Add SQS queue-driven document processing to the ingestion pipeline

**Description:**
The runner currently processes a single hard-coded document. This epic replaces that
with an SQS consumer that reads document-processing requests from the
`cica-document-search-queue`, processes each document and its S3 object in parallel,
and manages the message lifecycle (delete on success, redrive/DLQ on failure).

Messages are produced externally. Each carries the metadata needed to build a
`DocumentMetadata`; `source_doc_id` and `page_count` are derived during ingestion.

**In scope:** message consumption, validation, parallel processing, failure isolation,
message lifecycle, graceful shutdown, config, LocalStack support.

**Out of scope:** the external producer; DLQ / redrive policy provisioning (infra, not code).

**Covers requirements:** 1-12

---

## Story 1: SQS client factory and configuration settings

**Covers:** Requirement 1 (SQS Client Provisioning), Requirement 2 (Configuration Settings)

**Description:** Add a dedicated boto3 SQS client factory in `aws_client` that respects
`LOCAL_DEVELOPMENT_MODE` (LocalStack endpoint vs AWS), and add the SQS settings to the
`pydantic-settings` singleton with validation.

**Acceptance criteria:**
- SQS client is created via a dedicated factory; uses LocalStack endpoint in local mode, AWS credentials/region otherwise.
- Queue URL is resolved from `SQS_DOCUMENT_QUEUE` at startup; an unresolvable queue logs a critical error and exits non-zero.
- Settings expose `SQS_DOCUMENT_QUEUE`, `SQS_POLL_WAIT_TIME_SECONDS`, `SQS_MAX_MESSAGES_PER_POLL`, `SQS_MAX_CONCURRENCY`, `SQS_VISIBILITY_TIMEOUT_SECONDS` with sensible defaults.
- Out-of-range values raise a validation error at initialisation naming the offending setting.

---

## Story 2: Message consumption via long polling

**Covers:** Requirement 3 (Message Consumption via Long Polling)

**Description:** Poll the queue in batches using long polling; dispatch received messages for processing; survive transient receive errors.

**Acceptance criteria:**
- Each poll uses the configured long-poll wait time, max messages, and visibility timeout.
- All returned messages are dispatched before the next poll cycle.
- A receive error is logged and the loop continues without terminating.

---

## Story 3: Message contract parsing and validation

**Covers:** Requirement 4 (Message Schema and Contract), Requirement 5 (Metadata Derivation)

**Description:** Parse message bodies into a validated request. Distinguish producer-supplied
fields from derived fields. Derive `source_doc_id` and `source_file_name`; validate the S3 URI.

**Acceptance criteria:**
- Message body parsed as JSON; `correspondence_type` and `case_ref` (pattern `^\d{2}-[78]\d{5}$`) required; source location supplied as a full URI or component parts.
- Optional `received_date` used when supplied; otherwise set to receipt time in UTC.
- `source_doc_id` derived deterministically via `DocumentIdentifier`; `source_file_name` taken from the URI; `page_count` derived by the pipeline.
- Resolved S3 URI validated against `^s3://{bucket}/\d{2}-[78]\d{5}/`; failures rejected as malformed.

---

## Story 4: Malformed message handling

**Covers:** Requirement 6 (Malformed Message Handling)

**Description:** Handle unparseable or invalid messages deterministically so they neither block the queue nor crash the consumer.

**Acceptance criteria:**
- JSON parse failures and validation failures are logged (with message id / failed field) and routed for dead-letter handling.
- Malformed messages are deleted so they do not reappear after the visibility timeout.
- Other messages in the batch continue processing.

---

## Story 5: Parallel processing and failure isolation

**Covers:** Requirement 7 (Parallel Document Processing), Requirement 8 (Failure Isolation)

**Description:** Process documents concurrently up to a configurable limit; isolate per-document failures.

**Acceptance criteria:**
- Documents processed concurrently, capped at `SQS_MAX_CONCURRENCY`; slots freed as documents complete.
- A single document exception is recorded and logged (with `source_doc_id`, `case_ref`, `source_file_s3_uri`) without stopping other documents.
- Each dispatched message resolves its own outcome independently.

---

## Story 6: Message lifecycle management

**Covers:** Requirement 9 (Message Lifecycle Management)

**Description:** Tie message deletion to processing outcome; leave failures for redrive/DLQ.

**Acceptance criteria:**
- Successful processing deletes the message using its receipt handle.
- Failed processing leaves the message for redrive after the visibility timeout; DLQ handled by the queue redrive policy.
- Deletion errors are logged (with `source_doc_id`) without terminating the consumer.

---

## Story 7: Graceful shutdown and stop conditions

**Covers:** Requirement 10 (Graceful Shutdown and Stop Conditions)

**Description:** Exit cleanly when the queue drains so the Airflow container task terminates deterministically.

**Acceptance criteria:**
- An empty poll cycle is treated as drained and stops polling.
- In-flight documents finish before returning; then exit zero.
- OpenSearch health check failure at startup logs a critical error and terminates before polling.

---

## Story 8: Observability and structured logging

**Covers:** Requirement 11 (Observability and Structured Logging)

**Description:** Bind `source_doc_id` into the logging context per document, isolated across concurrent documents, and log per-cycle summaries.

**Acceptance criteria:**
- Log records during a document's processing carry its `source_doc_id`; context cleared on completion.
- Concurrent documents keep isolated logging context.
- Each poll cycle logs received / succeeded / failed counts.

---

## Story 9: Local development (LocalStack) compatibility

**Covers:** Requirement 12 (Local Development Compatibility)

**Description:** Ensure the consumer runs against the existing LocalStack queue without AWS access.

**Acceptance criteria:**
- In local mode, consumes from the LocalStack queue created by the init script under `SQS_DOCUMENT_QUEUE`.
- Logs a startup warning indicating local infrastructure.
- Message contract behaviour is identical in local and deployed modes.
