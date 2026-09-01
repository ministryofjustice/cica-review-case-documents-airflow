# Requirements Document

## Introduction

This feature adds SQS-driven consumption to the CICA ingestion pipeline. Today the runner (`src/ingestion_pipeline/runner.py`) processes a single hard-coded document built from configuration values, with a hard-coded correspondence type and a comment noting the S3 URI is a placeholder for a real SQS message.

This feature replaces that single-document flow with a consumer that reads document-processing requests from an existing SQS queue (`SQS_DOCUMENT_QUEUE=cica-document-search-queue`). Messages are produced externally (not by this pipeline) and each carries the document metadata required to construct a `DocumentMetadata` and invoke `Pipeline.process_document`. Some metadata is derived during ingestion (the `source_doc_id` UUID, `page_count`) rather than supplied by the producer.

The Consumer must process multiple messages and their associated S3 objects in parallel with a configurable concurrency limit, isolate failures so one bad document does not stop others, manage the SQS message lifecycle (delete on success, allow redrive on failure), shut down gracefully when the queue is drained, and emit structured logs carrying `source_doc_id` context per document. Configuration is added to the existing `pydantic-settings` singleton, and the LocalStack local-development path is preserved.

## Glossary

- **Ingestion_Pipeline**: The existing document processing pipeline exposed via `Pipeline.process_document(document_metadata)`, constructed by `build_pipeline()`.
- **SQS_Consumer**: The new component that polls the configured SQS queue, parses and validates messages, dispatches documents for parallel processing, and manages each message's lifecycle. This is the primary `System_Name` for this feature.
- **Message_Parser**: The subcomponent of the SQS_Consumer responsible for parsing raw SQS message bodies into a validated request object.
- **Document_Request**: The validated, in-memory representation of a single SQS message body containing producer-supplied document metadata fields.
- **Document_Queue**: The AWS SQS queue named by the `SQS_DOCUMENT_QUEUE` setting from which document-processing requests are received.
- **Dead_Letter_Queue (DLQ)**: An SQS queue, configured on the Document_Queue via a redrive policy, that receives messages exceeding the maximum receive count. The DLQ and redrive policy are provisioned in infrastructure, not by this feature's code.
- **DocumentMetadata**: The existing frozen Pydantic model in `chunking/schemas.py` passed to `Pipeline.process_document`.
- **Producer**: The external system that places messages onto the Document_Queue. Out of scope for implementation; referenced only to define the message contract.
- **Derived_Field**: A `DocumentMetadata` field the SQS_Consumer computes during ingestion rather than reading from the message: `source_doc_id` and `page_count`.
- **Producer_Supplied_Field**: A field the Producer must include in the message body: `source_file_s3_uri` (or the components needed to build it), `correspondence_type`, and `case_ref`.
- **Visibility_Timeout**: The SQS per-message period during which a received message is hidden from other receives.
- **Concurrency_Limit**: The maximum number of documents the SQS_Consumer processes simultaneously, set by configuration.
- **Poll_Cycle**: One long-poll receive request to the Document_Queue plus the processing of the messages it returns.
- **Settings**: The `pydantic-settings` singleton defined in `config.py`.
- **LOCAL_DEVELOPMENT_MODE**: The existing boolean setting that routes AWS clients to LocalStack at `http://localhost:4566`.

## Requirements

### Requirement 1: SQS Client Provisioning

**User Story:** As a pipeline operator, I want the SQS_Consumer to obtain an SQS client that respects the existing environment configuration, so that the same code runs against LocalStack locally and AWS SQS in the deployed environment.

#### Acceptance Criteria

1. THE SQS_Consumer SHALL obtain a boto3 SQS client from a dedicated client factory in the `aws_client` module.
2. WHILE LOCAL_DEVELOPMENT_MODE is true, THE SQS client factory SHALL create a client whose endpoint URL is `http://localhost:4566` using local test credentials.
3. WHILE LOCAL_DEVELOPMENT_MODE is false, THE SQS client factory SHALL create a client using the AWS credentials and region defined in Settings.
4. WHEN the SQS_Consumer starts, THE SQS_Consumer SHALL resolve the Document_Queue URL from the queue name in the `SQS_DOCUMENT_QUEUE` setting.
5. IF the Document_Queue URL cannot be resolved from the configured queue name, THEN THE SQS_Consumer SHALL log a critical error identifying the queue name and terminate with a non-zero exit status.

### Requirement 2: Configuration Settings

**User Story:** As a pipeline operator, I want SQS behaviour controlled through environment-backed settings, so that I can tune polling and concurrency per environment without code changes.

#### Acceptance Criteria

1. THE Settings SHALL expose a `SQS_DOCUMENT_QUEUE` string setting that defaults to `cica-document-search-queue`.
2. THE Settings SHALL expose an `SQS_POLL_WAIT_TIME_SECONDS` integer setting, used as the SQS long-poll wait time, that defaults to a value between 1 and 20 inclusive.
3. THE Settings SHALL expose an `SQS_MAX_MESSAGES_PER_POLL` integer setting, used as the maximum messages requested per Poll_Cycle, that defaults to a value between 1 and 10 inclusive.
4. THE Settings SHALL expose an `SQS_MAX_CONCURRENCY` integer setting, used as the Concurrency_Limit, that defaults to a positive integer.
5. THE Settings SHALL expose an `SQS_VISIBILITY_TIMEOUT_SECONDS` integer setting that defaults to a positive integer.
6. IF `SQS_POLL_WAIT_TIME_SECONDS` is provided outside the inclusive range 0 to 20, THEN THE Settings SHALL raise a validation error at initialisation identifying the offending setting.
7. IF `SQS_MAX_MESSAGES_PER_POLL` is provided outside the inclusive range 1 to 10, THEN THE Settings SHALL raise a validation error at initialisation identifying the offending setting.
8. IF `SQS_MAX_CONCURRENCY` is provided as a value less than 1, THEN THE Settings SHALL raise a validation error at initialisation identifying the offending setting.
9. IF `SQS_VISIBILITY_TIMEOUT_SECONDS` is provided as a value less than 1, THEN THE Settings SHALL raise a validation error at initialisation identifying the offending setting.

### Requirement 3: Message Consumption via Long Polling

**User Story:** As a pipeline operator, I want the SQS_Consumer to receive messages using long polling in batches, so that the pipeline drains the queue efficiently without busy-waiting.

#### Acceptance Criteria

1. WHEN a Poll_Cycle begins, THE SQS_Consumer SHALL request messages from the Document_Queue using a long-poll wait time equal to `SQS_POLL_WAIT_TIME_SECONDS`.
2. WHEN a Poll_Cycle begins, THE SQS_Consumer SHALL request at most `SQS_MAX_MESSAGES_PER_POLL` messages in a single receive request.
3. WHEN the SQS_Consumer requests messages, THE SQS_Consumer SHALL apply a per-message visibility timeout equal to `SQS_VISIBILITY_TIMEOUT_SECONDS`.
4. WHEN a Poll_Cycle returns one or more messages, THE SQS_Consumer SHALL dispatch each message for processing before beginning the next Poll_Cycle.
5. IF a receive request raises an AWS client error, THEN THE SQS_Consumer SHALL log the error and continue with the next Poll_Cycle without terminating the consumer.

### Requirement 4: Message Schema and Contract

**User Story:** As an integrator building the external Producer, I want a defined message contract distinguishing supplied fields from derived fields, so that I send exactly the metadata the pipeline needs.

#### Acceptance Criteria

1. THE Message_Parser SHALL parse each SQS message body as JSON into a Document_Request.
2. THE Document_Request SHALL require the Producer to supply `correspondence_type` as a non-empty string.
3. THE Document_Request SHALL require the Producer to supply `case_ref` as a non-empty string matching the pattern `^\d{2}-[78]\d{5}$`.
4. THE Document_Request SHALL require the Producer to supply the source document location either as a full `source_file_s3_uri` string or as the bucket, case-prefix, and filename components needed to construct the `source_file_s3_uri`.
5. WHERE the Producer supplies an optional `received_date` in the message body, THE Message_Parser SHALL use the supplied `received_date` as the `DocumentMetadata.received_date`.
6. WHERE the Producer omits `received_date` from the message body, THE SQS_Consumer SHALL set `DocumentMetadata.received_date` to the message receipt time in UTC.
7. THE SQS_Consumer SHALL treat `source_doc_id` and `page_count` as Derived_Fields and SHALL ignore any values for those fields present in the message body.

### Requirement 5: Metadata Derivation

**User Story:** As a pipeline operator, I want the SQS_Consumer to derive the document identity and page count during ingestion, so that identifiers stay deterministic and consistent with the existing pipeline.

#### Acceptance Criteria

1. WHEN a Document_Request is validated, THE SQS_Consumer SHALL derive `source_doc_id` as the deterministic UUID produced by `DocumentIdentifier(source_file_name, correspondence_type, case_ref)`.
2. WHEN a Document_Request is validated, THE SQS_Consumer SHALL determine `source_file_name` as the final path segment of the resolved `source_file_s3_uri`.
3. WHEN the SQS_Consumer constructs the DocumentMetadata for a Document_Request, THE SQS_Consumer SHALL set `page_count` to the value derived by the Ingestion_Pipeline during processing rather than a producer-supplied value.
4. WHEN the SQS_Consumer builds the DocumentMetadata, THE SQS_Consumer SHALL validate the resolved `source_file_s3_uri` against the pattern `^s3://{bucket}/\d{2}-[78]\d{5}/`.
5. IF the resolved `source_file_s3_uri` fails the S3 URI pattern validation, THEN THE SQS_Consumer SHALL reject the message as malformed and SHALL NOT invoke the Ingestion_Pipeline for that message.

### Requirement 6: Malformed Message Handling

**User Story:** As a pipeline operator, I want malformed messages handled deterministically, so that unusable messages do not block the queue or crash the consumer.

#### Acceptance Criteria

1. IF a message body cannot be parsed as JSON, THEN THE SQS_Consumer SHALL classify the message as malformed, log an error including the SQS message identifier, and route the message for dead-letter handling.
2. IF a parsed message is missing a required Producer_Supplied_Field or fails field validation, THEN THE SQS_Consumer SHALL classify the message as malformed, log an error identifying the failed field, and route the message for dead-letter handling.
3. WHEN the SQS_Consumer routes a malformed message for dead-letter handling, THE SQS_Consumer SHALL delete the malformed message from the Document_Queue so the message does not return after its visibility timeout.
4. WHEN the SQS_Consumer classifies a message as malformed, THE SQS_Consumer SHALL continue processing all other messages in the current batch.

### Requirement 7: Parallel Document Processing

**User Story:** As a pipeline operator, I want multiple documents processed concurrently up to a limit, so that throughput improves while resource use stays bounded.

#### Acceptance Criteria

1. WHEN a batch of valid Document_Requests is received, THE SQS_Consumer SHALL process the associated documents concurrently.
2. THE SQS_Consumer SHALL limit the number of documents processed simultaneously to at most `SQS_MAX_CONCURRENCY`.
3. WHILE the number of in-flight documents equals `SQS_MAX_CONCURRENCY`, THE SQS_Consumer SHALL defer dispatch of additional documents until an in-flight document completes.
4. WHEN a document's processing completes, THE SQS_Consumer SHALL make its concurrency slot available for a subsequent document.

### Requirement 8: Failure Isolation

**User Story:** As a pipeline operator, I want one failing document to be isolated, so that other documents in the same batch still complete.

#### Acceptance Criteria

1. IF the Ingestion_Pipeline raises an exception while processing one document, THEN THE SQS_Consumer SHALL record the failure for that document and continue processing the remaining documents.
2. WHEN a document raises an exception during processing, THE SQS_Consumer SHALL log the failure with the document's `source_doc_id`, `case_ref`, and `source_file_s3_uri`.
3. THE SQS_Consumer SHALL complete every Poll_Cycle by resolving the lifecycle outcome (success or failure) of each dispatched message independently of the outcomes of other messages.

### Requirement 9: Message Lifecycle Management

**User Story:** As a pipeline operator, I want message deletion tied to processing outcome, so that successful work is removed and failed work is retried or dead-lettered.

#### Acceptance Criteria

1. WHEN the Ingestion_Pipeline completes processing a document without raising an exception, THE SQS_Consumer SHALL delete the corresponding message from the Document_Queue.
2. IF processing a document fails with an exception, THEN THE SQS_Consumer SHALL leave the corresponding message in the Document_Queue without deleting it so the message becomes visible again after its visibility timeout for redrive.
3. WHEN a message becomes visible again after a failed processing attempt and its receive count exceeds the Document_Queue redrive policy maximum, THE Document_Queue SHALL move the message to the Dead_Letter_Queue.
4. WHEN the SQS_Consumer deletes a message, THE SQS_Consumer SHALL use the receipt handle from the specific received message.
5. IF deleting a message raises an AWS client error, THEN THE SQS_Consumer SHALL log the deletion error including the `source_doc_id` and continue processing without terminating the consumer.

### Requirement 10: Graceful Shutdown and Stop Conditions

**User Story:** As a pipeline operator running the consumer as an Airflow container task, I want the consumer to stop cleanly when the queue is drained, so that the task exits deterministically rather than running forever.

#### Acceptance Criteria

1. WHEN a Poll_Cycle returns zero messages, THE SQS_Consumer SHALL treat the Document_Queue as drained and SHALL stop polling.
2. WHEN the SQS_Consumer stops polling, THE SQS_Consumer SHALL wait for all in-flight documents to reach a lifecycle outcome before returning control.
3. WHEN all in-flight documents have reached a lifecycle outcome and no further messages remain, THE SQS_Consumer SHALL terminate with a zero exit status.
4. IF the OpenSearch health check fails at startup, THEN THE SQS_Consumer SHALL log a critical error and terminate before beginning any Poll_Cycle.

### Requirement 11: Observability and Structured Logging

**User Story:** As a pipeline operator, I want per-document log context, so that I can trace all log lines for a single document by its `source_doc_id`.

#### Acceptance Criteria

1. WHILE a document is being processed, THE SQS_Consumer SHALL bind the document's `source_doc_id` into the logging context so log records emitted during that document's processing include the `source_doc_id`.
2. WHEN a document reaches a lifecycle outcome, THE SQS_Consumer SHALL clear the `source_doc_id` from the logging context for that processing unit.
3. WHILE documents are processed concurrently, THE SQS_Consumer SHALL keep each document's `source_doc_id` logging context isolated from the contexts of other concurrently processed documents.
4. WHEN a Poll_Cycle completes, THE SQS_Consumer SHALL log a summary including the count of messages received, the count processed successfully, and the count failed.

### Requirement 12: Local Development Compatibility

**User Story:** As a developer, I want the SQS_Consumer to work against the existing LocalStack setup, so that I can exercise the queue-driven flow locally without AWS access.

#### Acceptance Criteria

1. WHILE LOCAL_DEVELOPMENT_MODE is true, THE SQS_Consumer SHALL consume from the LocalStack Document_Queue created by the local init script under the `SQS_DOCUMENT_QUEUE` name.
2. WHILE LOCAL_DEVELOPMENT_MODE is true, THE SQS_Consumer SHALL log a warning at startup indicating the consumer is running against local infrastructure.
3. THE SQS_Consumer SHALL consume messages from the Document_Queue whose bodies conform to the Requirement 4 contract regardless of whether LOCAL_DEVELOPMENT_MODE is true or false.
