# Malformed Message Handling

How the SQS document source treats messages it cannot parse or validate, and why.

Relevant code:

- `src/ingestion_pipeline/orchestration/document_source.py` (`SqsDocumentSource.fetch_batch`)
- `src/ingestion_pipeline/orchestration/document_ingress.py` (`parse_message`, `MalformedMessageError`)

## Current behaviour

When `parse_message` raises `MalformedMessageError` (invalid JSON, missing/invalid
required field, S3 URI contract violation, etc.), the source:

1. Logs an `ERROR` with the `message_id`, the failing field, the error, and the raw
   message body (truncated to `_MAX_LOGGED_BODY_CHARS` and control-char escaped).
2. **Leaves the message on the queue** (it does not delete it).

Because the message is not deleted, SQS redelivers it on subsequent polls and, after
`SQS_MAX_RECEIVE_COUNT` receives, redrives it to the DLQ. The DLQ then holds the
original payload for inspection and, where appropriate, redrive.

This is the standard SQS "poison pill" pattern: a message that cannot be processed is
isolated in the DLQ rather than silently discarded.

## Why not delete malformed messages

An earlier implementation deleted malformed messages immediately, leaving the log line
as the only record. That was changed because:

- `MalformedMessageError` means "*this* consumer version could not parse *this*
  message", which is not always a permanently bad payload. A producer schema change the
  consumer has not caught up to, or a consumer bug, can misclassify an otherwise valid
  message. Deleting permanently throws away a document request on the consumer's say-so.
- The DLQ is a diagnostic and isolation mechanism, not only a redrive staging area.
  Retaining the payload supports debugging (which producer, which document, whether a
  deployment introduced incompatible messages) even when the exact bytes can never pass
  `parse_message`.
- Deletion is irreversible; a DLQ message can be inspected and, if the failure was
  consumer-side, redriven once the consumer is fixed.

## Counting / observability

`FetchResult.malformed_received` counts malformed messages seen in a single poll, and
the runner accumulates `RunTotals.malformed_receives`. Because malformed messages stay
on the queue until redriven, the same message is re-counted on each redelivery, so this
counter reflects malformed *receives*, not distinct messages. The accounting invariant
`messages_received == jobs_processed + malformed_receives` still holds per poll.

## Known trade-offs and a possible future refinement (low priority)

Routing malformed messages to the operational DLQ is good enough for now, but has two
rough edges:

- A deterministically malformed message is received `SQS_MAX_RECEIVE_COUNT` times
  (re-logged each time) before it reaches the DLQ. For a genuine contract failure those
  retries cannot succeed, so they are wasted work.
- Malformed messages share the operational DLQ with recoverable processing failures,
  which makes a bulk redrive of that DLQ risky (the never-redrivable entries will just
  fail again).

A cleaner design would separate retry policy from failure retention: classify errors as
retryable (throttling, service unavailable, timeouts) vs non-retryable (contract /
validation failures), and route non-retryable messages to a dedicated
invalid-message queue (or an S3 archive) before deleting the original, instead of
cycling them through the normal DLQ. This is a deliberate architectural choice, not
something SQS does for us, and is deferred as low priority.
