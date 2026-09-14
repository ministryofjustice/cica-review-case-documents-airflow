# Bugfix Requirements Document

## Introduction

When a batch of documents is fetched for ingestion, each `DocumentJob` carries a
natural key `(source_file_name, correspondence_type, case_ref)` that is fed into
`DocumentIdentifier.generate_uuid()` to produce a deterministic `source_doc_id`.
That identifier keys every downstream side effect: the page-image S3 prefix
(`{case_ref}/{source_doc_id}/pages/`) and the OpenSearch chunk/page document IDs.

Nothing in the batch pipeline prevents two jobs in the same batch from sharing a
natural key. `SqsDocumentSource.fetch_batch` builds one job per configured
`SRC_S3_KEY` entry without deduplicating, so repeating a key in the config
produces duplicate jobs. The real SQS source can produce the same situation when
a message is redelivered (at-least-once delivery). `run_batch` then processes
those jobs concurrently in a `ThreadPoolExecutor`, so two workers operate on the
same deterministic IDs at the same time.

Because the two workers share the same `source_doc_id`, S3 page-image prefix and
OpenSearch document IDs, they race: one worker's index write can overwrite the
other's, and one worker's failure-path cleanup (`_cleanup_document`, which
prefix-deletes page images and deletes OpenSearch docs by `source_doc_id`) can
delete or corrupt the other worker's data. The outcome is silent data loss or
partial ingestion that neither worker detects, and there is no explicit policy
for acknowledging or dropping the duplicate.

This bugfix ensures duplicate natural keys within a batch cannot race, and
defines an explicit acknowledgement policy for the duplicates.

## Bug Analysis

### Current Behavior (Defect)

The batch runner processes duplicate-keyed jobs concurrently, allowing their
shared deterministic identifiers to collide and corrupt each other's data.

1.1 WHEN a batch contains two or more jobs whose natural key `(source_file_name, correspondence_type, case_ref)` resolves to the same `source_doc_id` THEN the system submits all of them to the thread pool and processes them concurrently
1.2 WHEN two concurrent workers share the same `source_doc_id` THEN the system lets them write to the same OpenSearch chunk/page IDs and the same `{case_ref}/{source_doc_id}/pages/` S3 prefix, so one worker's output can overwrite the other's
1.3 WHEN one of the duplicate-keyed workers fails and runs `_cleanup_document` (prefix-deleting page images and deleting OpenSearch docs by `source_doc_id`) THEN the system deletes or corrupts the data of the other worker that shares the same `source_doc_id`
1.4 WHEN `SqsDocumentSource.fetch_batch` reads a `SRC_S3_KEY` value that repeats the same key THEN the system emits one `DocumentJob` per occurrence with no deduplication
1.5 WHEN duplicate-keyed jobs are present THEN the system has no explicit acknowledgement policy for the duplicate messages, so redelivered/repeated documents are neither deliberately acknowledged nor deliberately dropped

### Expected Behavior (Correct)

Duplicate natural keys within a batch are collapsed to a single processed unit,
and the redundant copies are handled by an explicit acknowledgement policy
rather than racing.

2.1 WHEN a batch contains two or more jobs that resolve to the same `source_doc_id` THEN the system SHALL process that `source_doc_id` at most once (deduplicate or serialize) so that no two workers hold the same deterministic identifier concurrently
2.2 WHEN two jobs resolve to the same `source_doc_id` THEN the system SHALL guarantee that only one owner writes to the shared OpenSearch chunk/page IDs and the shared `{case_ref}/{source_doc_id}/pages/` S3 prefix for that batch
2.3 WHEN a duplicate-keyed job fails and its cleanup runs THEN the system SHALL ensure cleanup only affects the single de-duplicated unit and cannot delete or corrupt another job's data, because no other in-flight job shares that `source_doc_id`
2.4 WHEN `SqsDocumentSource.fetch_batch` produces jobs whose keys repeat THEN the system SHALL deduplicate them so the returned batch contains at most one job per distinct `source_doc_id`
2.5 WHEN a duplicate document message is encountered (config repeat or SQS redelivery) THEN the system SHALL apply an explicit acknowledgement policy that acknowledges/drops the duplicate rather than silently racing, and the outcome of the retained unit SHALL determine acknowledgement for its duplicates
2.6 WHEN `run_batch` detects and collapses/drops one or more duplicate jobs that resolve to the same `source_doc_id` THEN the system SHALL emit a structured log entry (via the module logger, consistent with the rest of `runner.py`) identifying the affected `source_doc_id`, the number of duplicate jobs collapsed, and where available their S3 URIs / `case_ref`, so operators can observe that redelivered or repeated documents were deduplicated rather than silently discarded

### Unchanged Behavior (Regression Prevention)

Batches without duplicates must behave exactly as they do today.

3.1 WHEN a batch contains only jobs with distinct `source_doc_id` values THEN the system SHALL CONTINUE TO process every job concurrently up to `MAX_CONCURRENT_DOCUMENTS`
3.2 WHEN a job succeeds THEN the system SHALL CONTINUE TO acknowledge that job via the `DocumentSource` exactly as it does today
3.3 WHEN a job fails THEN the system SHALL CONTINUE TO leave it unacknowledged, clean up its side effects, and classify the failure (`category`/`retryable`) for downstream redrive/DLQ handling
3.4 WHEN a document is processed THEN the system SHALL CONTINUE TO derive the same deterministic `source_doc_id` from `(source_file_name, correspondence_type, case_ref)` via `DocumentIdentifier.generate_uuid()`
3.5 WHEN an empty batch is fetched THEN the system SHALL CONTINUE TO return no results without error

## Bug Condition and Properties

### Bug Condition

The bug is triggered by a batch that contains more than one job resolving to the
same deterministic `source_doc_id`.

```pascal
FUNCTION isBugCondition(batch)
  INPUT: batch of type List<DocumentJob>
  OUTPUT: boolean

  // ids: the deterministic source_doc_id for each job in the batch
  ids ← [ generateSourceDocId(job) FOR job IN batch ]

  // true when at least two jobs share a source_doc_id
  RETURN hasDuplicates(ids)
END FUNCTION
```

Where `generateSourceDocId(job)` is
`DocumentIdentifier(source_file_name, correspondence_type, case_ref).generate_uuid()`.

### Property: Fix Checking

For any batch that contains duplicate source doc IDs, each distinct
`source_doc_id` is processed at most once and its duplicates are acknowledged/
dropped rather than processed concurrently.

```pascal
// Property: Fix Checking - Duplicate source_doc_id is processed once
FOR ALL batch WHERE isBugCondition(batch) DO
  results ← runBatch'(batch)

  // Each distinct source_doc_id is handed to the pipeline at most once
  ASSERT FOR ALL id IN distinct(sourceDocIds(batch)):
           count(pipelineInvocations(id)) <= 1

  // No two in-flight units ever share a source_doc_id (no concurrent collision)
  ASSERT no_concurrent_units_share_source_doc_id(batch)

  // Every input job reaches a defined acknowledgement outcome (retained or
  // duplicate), none is left silently racing
  ASSERT FOR ALL job IN batch:
           acknowledgementOutcome(job) IN { ack_as_processed, dropped_as_duplicate, left_for_redrive }
END FOR
```

### Property: Preservation Checking

For any batch with no duplicate source doc IDs, the fixed runner behaves
identically to the original.

```pascal
// Property: Preservation Checking - no duplicates behaves as before
FOR ALL batch WHERE NOT isBugCondition(batch) DO
  ASSERT runBatch(batch) = runBatch'(batch)
END FOR
```

Where `runBatch` is the original (unfixed) behaviour `F` and `runBatch'` is the
fixed behaviour `F'`.
