# Design — Parallel Document Processing

## Context

The runner is the composition/entry point for the pipeline. Before this change it
processed one hardcoded document. The pipeline itself (`orchestration/pipeline.py`)
is a stateless orchestrator that, per document, runs: Textract analysis → page image
upload → chunking → per-chunk embedding → OpenSearch indexing, with cleanup on
failure.

An analysis of every component established that the workload is IO/wait-bound and that
almost every component is already safe to share across threads. Two issues stood in
the way of concurrency, and both are addressed here.

## Concurrency model

Thread-based concurrency via `concurrent.futures.ThreadPoolExecutor`. Justification:

- Textract processing (`textract/textract_processor.py`) is a synchronous polling loop
  that blocks in `time.sleep` for up to `TEXTRACT_API_JOB_TIMEOUT_SECONDS` (default
  600s) per document.
- S3 download/upload, per-chunk Bedrock `invoke_model`, and OpenSearch bulk/delete are
  all blocking network IO.
- The only meaningfully CPU-bound step (PDF→image via `pdf2image`/poppler) runs largely
  in a subprocess and releases the GIL.

Therefore threads give real concurrency here without the overhead/complexity of
processes.

## Component thread-safety assessment

| Component | Per-document mutable state? | Safe to share? | Notes |
|-----------|-----------------------------|----------------|-------|
| `Pipeline` | No (all locals) | Yes, once deps are safe | Pure orchestration |
| `PageProcessor` | **Yes → fixed** | Yes after fix | `uploaded_results` made local |
| `S3DocumentService` | No | Yes | config-only fields |
| `ImageConverter` | No | Yes | stateless; CPU/subprocess |
| `DocumentPageFactory` | No | Yes | stateless |
| `TextractProcessor` | No | Yes | blocking poll loop |
| word-stream chunker/handler | No | Yes | fresh `WordChunkState` per call |
| `EmbeddingGenerator` | No | Yes | boto3 client safe to call |
| `OpenSearchIndexer` | No | Yes | unique `source_doc_id` per doc → no cross-doc interference |
| `DocumentIdentifier` | No | Yes | frozen pydantic model |
| `source_doc_id_context` | N/A | **Requires per-thread set** | ContextVar, see below |

### Fix 1 — `PageProcessor` local state

`PageProcessor.process` previously stored the uploaded-image results on
`self.uploaded_results` (an instance attribute, reset per call). Two threads sharing
one instance would clobber each other's cleanup list. The fix makes `uploaded_results`
a local variable within `process`, so a single shared `PageProcessor` (and therefore a
single shared `Pipeline`) is thread-safe.

### Fix 2 — Thread-safe Textractor construction

`get_textractor_instance()` previously mutated process-wide `os.environ` (AWS
credentials) to build the `Textractor`, then restored them. That construction-time
mutation races if called concurrently and can affect anything else in the process
reading those vars.

The fix removes the environment mutation entirely: build a `boto3.Session` with the
MOD-platform credentials passed explicitly, construct `Textractor(region_name=...)`,
then inject the credentialed clients by assigning `textractor.session`,
`textractor.textract_client`, and `textractor.s3_client`. This matches how the S3 and
Textract client factories already pass credentials explicitly, and removes the "build
only on the main thread" constraint.

> Library-contract note: this relies on `Textractor.__init__` exposing `session`,
> `textract_client`, and `s3_client` (verified against the pinned
> `amazon-textract-textractor` 1.10.0). A unit test guards against a future library
> change silently breaking this.

### Fix 3 — Per-thread logging context

`source_doc_id_context` is a `contextvars.ContextVar`. `ThreadPoolExecutor` workers do
not inherit a value `.set()` in the submitting thread, so the context must be set
**inside** each worker and reset in a `finally` (using the token from `.set()`), rather
than once globally in `main`.

## Document source abstraction (stubbed SQS)

New module `orchestration/document_source.py`:

- `DocumentJob` — a frozen pydantic model: `source_file_s3_uri`,
  `correspondence_type`, `case_ref`, optional `receipt_handle` (the SQS acknowledgement
  handle), plus a `source_file_name` derived property.
- `DocumentSource` — a `typing.Protocol` with `fetch_batch() -> list[DocumentJob]` and
  `acknowledge(job) -> None`. Decouples the runner from the transport.
- `SqsDocumentSource` — the stub. `fetch_batch()` synthesises a one-document batch from
  settings; `acknowledge()` is a no-op. Both carry TODOs mapping to
  `sqs.receive_message` / `sqs.delete_message`, and the constructor already takes
  `queue_url` / `max_messages`.

## Runner design

```
main()
 ├─ health check (OpenSearch)              # unchanged, once per run
 ├─ pipeline = build_pipeline()            # once, shared across workers
 ├─ source = SqsDocumentSource()
 ├─ jobs = source.fetch_batch()
 └─ run_batch(jobs, pipeline, source)

run_batch(jobs, pipeline, source)
 ├─ if empty → log & return []
 ├─ workers = min(MAX_CONCURRENT_DOCUMENTS, len(jobs))
 ├─ ThreadPoolExecutor: submit process_document_job(job, pipeline) per job
 ├─ as_completed → collect DocumentResult; acknowledge only successes
 └─ log "N succeeded, M failed"

process_document_job(job, pipeline) -> DocumentResult   # runs in worker thread
 ├─ identifier → source_doc_id
 ├─ token = source_doc_id_context.set(source_doc_id)
 ├─ try: validate URI → build metadata → pipeline.process_document(...)
 │      → DocumentResult(success=True)
 ├─ except: log critical w/ traceback → DocumentResult(success=False, error=exc)
 └─ finally: source_doc_id_context.reset(token)
```

`DocumentResult` is a small dataclass: `job`, `source_doc_id`, `success`, `error`.
`extract_case_ref` and `validate_s3_uri` are retained from the original runner.

## Configuration

`config.py` adds `MAX_CONCURRENT_DOCUMENTS: int = 4`, added to the existing
positive-integer field validator.

## Error handling

- Per-document errors are caught in `process_document_job` and reported via
  `DocumentResult`, never propagated to abort the batch.
- Existing pipeline-internal cleanup (delete indexed chunks/pages by `source_doc_id`
  on failure) is unchanged and is safe across documents because IDs are unique per
  document.

## Testing strategy

- `tests/test_runner.py` — worker success/invalid-URI/exception containment, log-context
  reset, `run_batch` empty + mixed success/failure with selective acknowledgement, and
  `main` wiring (build once, fetch batch, process, acknowledge; health-check early exit).
- `tests/orchestration/test_document_source.py` — `DocumentJob` filename derivation and
  the `SqsDocumentSource` stub batch/acknowledge behavior.
- `tests/page_processor/test_processor.py` — updated to reflect local `uploaded_results`.
- `tests/aws_client/test_clients.py` — Textractor factory uses explicit session
  credentials and does not mutate the environment.

## Out of scope (deliberate)

Removing the unused `layout` and `linear-sentence-splitter` chunking strategies. The
word-stream chunker still imports `SentenceDetector` from the `line_sentence` package,
so that dependency must be relocated before those packages can be deleted. Tracked as a
follow-up.
