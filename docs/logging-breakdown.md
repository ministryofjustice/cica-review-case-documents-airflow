# Logging Breakdown — CICA Review Case Documents Ingestion Pipeline

A complete inventory of every log statement emitted by the production pipeline (`src/ingestion_pipeline`).

## Logging setup

- **Root logger format:** `%(asctime)s %(levelname)s %(message)s` (configured in `custom_logging`).
- **Context filter:** A `ContextFilter` prepends the current `source_doc_id` to every log record when it is set (via a `ContextVar`). This means most messages are effectively prefixed with the document's `source_doc_id`.
- **Default level:** `LOG_LEVEL = "INFO"` (from `config.py`). DEBUG messages are therefore suppressed unless the level is lowered.
- **Verbose page debug gating:** `DEBUG_PAGE_NUMBERS = {1}` by default. The verbose page debug logger only emits for page numbers in this set.
- **Levels used across the codebase:** DEBUG, INFO, WARNING, ERROR, CRITICAL.

Notes on the table:
- **Message** shows the log string with `{...}` f-string placeholders as they appear in code.
- **Interpolated attributes** lists the variables/values injected into the message.
- **exc_info** indicates whether the traceback is attached (`exc_info=True`).

---

## Entry point & orchestration

### `main.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| module load | INFO | `Running........` | — | No |

### `runner.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| `run` | WARNING | `Running in LOCAL_DEVELOPMENT_MODE. Ensure your S3 URI is accessible in LocalStack.` | — | No |
| `run` | INFO | `Pipeline runner started.` | — | No |
| `run` | CRITICAL | `OpenSearch health check failed. Exiting pipeline runner.` | — | No |
| `run` | INFO | `Generated source_doc_id: {source_doc_id} for document: {S3_DOCUMENT_URI}` | `source_doc_id`, `S3_DOCUMENT_URI` | No |
| `run` | INFO | `Validating S3 URI: {S3_DOCUMENT_URI}` | `S3_DOCUMENT_URI` | No |
| `run` | CRITICAL | `Invalid S3 URI: {S3_DOCUMENT_URI}` | `S3_DOCUMENT_URI` | No |
| `run` | INFO | `Processing document for case reference: {case_ref}` | `case_ref` | No |
| `run` | INFO | `Document metadata prepared: file={document_metadata.source_file_name}, case_ref={case_ref}` | `source_file_name`, `case_ref` | No |
| `run` | INFO | `Starting document processing in pipeline {S3_DOCUMENT_URI}` | `S3_DOCUMENT_URI` | No |
| `run` | INFO | `Pipeline runner finished successfully.` | — | No |
| `run` | CRITICAL | `Pipeline runner encountered a fatal error for source_doc_id={source_doc_id}, case_ref={case_ref}, s3_uri={S3_DOCUMENT_URI}: {type(exc).__name__}: {exc}` | `source_doc_id`, `case_ref`, `S3_DOCUMENT_URI`, exception type, exception | Yes |
| `run` | INFO | `Cleaning up context for document` | — | No |

### `orchestration/pipeline.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| `process_document` | WARNING | `Textract did not return a document. Skipping rest of pipeline.` | — | No |
| `process_document` | WARNING | `No chunks were generated. Indexing page metadata with defaults.` | — | No |
| `process_document` | INFO | `Generating embeddings for {len(processed_data.chunks)} chunks` | chunk count | No |
| `process_document` | INFO | `Finished generating embeddings for {len(processed_data.chunks)} chunks` | chunk count | No |
| `process_document` | INFO | `Successfully finished processing document` | — | No |
| `process_document` | CRITICAL | `Pipeline failed for document: {e}` | exception | Yes |
| `process_document` | CRITICAL | `An unexpected error occurred in the pipeline for document: {e}` | exception | Yes |
| `_cleanup_indexed_data` | INFO | `Cleaning up indexed data` | — | No |
| `_cleanup_indexed_data` | DEBUG | `Skipping verbose cleanup error log for connectivity issue on document %s: %s` | `source_doc_id`, `cleanup_error` | No |
| `_cleanup_indexed_data` | ERROR | `Failed to clean up indexed data for document {source_doc_id}: {cleanup_error}` | `source_doc_id`, `cleanup_error` | Yes |

---

## S3, Textract, embedding, indexing

### `s3_file_downloader/s3_downloader.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| download function | INFO | `Successfully downloaded {file_key} from bucket {bucket_name} to {download_path}` | `file_key`, `bucket_name`, `download_path` | No |

### `page_processor/s3_utils.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| download | ERROR | `Error downloading {key} from bucket {bucket}: {e}` | `key`, `bucket`, exception | No |
| upload (retry) | ERROR | `Upload failed for {key} (attempt {attempt}): {e}` | `key`, `attempt`, exception | No |
| delete | INFO | `Deleted {key} from bucket {bucket}` | `key`, `bucket` | No |
| delete | ERROR | `Failed to delete {key} from bucket {bucket}: {e}` | `key`, `bucket`, exception | No |

### `page_processor/s3_document_service.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| download PDF | INFO | `Downloading PDF from S3. Bucket='{self.source_bucket}', Key='{key}', S3 URI='{s3_uri}'.` | `source_bucket`, `key`, `s3_uri` | No |
| upload page images | INFO | `Uploading {len(images)} page images to S3 as {IMAGE_FORMAT} format. To bucket='{self.page_bucket}', CaseRef='{case_ref}'` | image count, `IMAGE_FORMAT`, `page_bucket`, `case_ref` | No |
| delete page images | INFO | `Deleting {len(s3_keys)} page images from S3. Bucket='{self.page_bucket}', Keys={s3_keys}.` | key count, `page_bucket`, `s3_keys` | No |

### `page_processor/processor.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| process pages | INFO | `Processing document pages` | — | No |

### `textract/textract_processor.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| start job | INFO | `Begin Textract job for {s3_document_uri}` | `s3_document_uri` | No |
| start job | INFO | `Textract Job: {document.job_id}` | `job_id` | No |
| poll status | INFO | `Textract Job {job_id} {status}` | `job_id`, `status` | No |
| fetch results | INFO | `Fetching results for Textract job {job_id}` | `job_id` | No |
| process document | INFO | `Processing s3 file: {s3_document_uri}` | `s3_document_uri` | No |
| process document | INFO | `Switched s3 file location for local development AWS Textract integration to: {s3_document_uri}` | `s3_document_uri` | No |
| process document | ERROR | `Textract job {job_id} did not succeed. Status: {final_status}` | `job_id`, `final_status` | No |
| process document | ERROR | `Failed to process s3 file {s3_document_uri}: {e}` | `s3_document_uri`, exception | No |

### `embedding/embedding_generator.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| generate embedding | DEBUG | `Generating embedding for text: {text}` | `text` (note: uses module `logging.debug`, not the `logger` instance) | No |
| generate embedding | ERROR | `Embedding generation failed: {e}` | exception | No |

### `indexing/healthcheck.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| `check_opensearch_health` | INFO | `OpenSearch health check passed: status={status}, attempts={attempts}` | `status`, `attempts` | No |
| `check_opensearch_health` | ERROR | `OpenSearch health check failed after %s attempts over %.2f seconds: %s` | `attempts`, `elapsed`, `last_error` | No |
| `check_opensearch_health` | ERROR | `OpenSearch health check failed after %s attempts over %.2f seconds: status=%s` | `attempts`, `elapsed`, `last_status` | No |

### `indexing/indexer.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| `__init__` | INFO | `OpenSearchIndexer using proxy URL host=%s port=%s` | host, port | No |
| `__init__` | INFO | `Client initialised for index '%s'` | `index_name` | No |
| `index_documents` | WARNING | `No documents provided to index.` | — | No |
| `index_documents` | INFO | `Attempting document deletion of existing documents from index {self.index_name} before reindexing` | `index_name` | No |
| `index_documents` | INFO | `Indexing {len(documents)} documents into index {self.index_name}` | document count, `index_name` | No |
| `index_documents` | DEBUG | `Bulk indexing errors for index %s: %s` | `index_name`, `errors` | No |
| `index_documents` | INFO | `Indexed {len(documents)} chunks into index {self.index_name}` | document count, `index_name` | No |
| `index_documents` | DEBUG | `BulkIndexError details for index %s: %s` | `index_name`, `e.errors` | No |
| `index_documents` | INFO | `An unexpected exception occurred indexing removing all associated chunks: {e}` | exception | No |
| `delete_documents_by_source_doc_id` | INFO | `Deleted {deleted_count} documents from index {self.index_name}` | `deleted_count`, `index_name` | No |
| `delete_documents_by_source_doc_id` | DEBUG | `Version conflict during delete (harmless): {e}` | exception | Yes |
| `delete_documents_by_source_doc_id` | ERROR | `Failed to delete documents by source_doc_id: {e}` | exception | Yes |

---

## UUID generation

### `uuid_generators/document_uuid.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| `generate_uuid` | DEBUG | `Generating UUID with data string: {data_string}` | `data_string` (filename + correspondence type + case ref) | No |

---

## Chunking (word-stream strategy only)

> Per request, only the **word-stream** chunking strategy is documented here. The layout and line-sentence strategies are intentionally excluded. The shared chunking components below (factory, schemas, verbose page debug logger) apply to all strategies but are included because they are on the word-stream path.

### Shared chunking components

#### `chunking/chunk_strategy_factory.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| `get_chunk_strategy` | INFO | `Initialising ChunkStrategy of type: {chunker_type}` | `chunker_type` | No |

#### `chunking/schemas.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| `DocumentChunk._generate_chunk_id` | DEBUG | `Generated 16-digit UUID: {chunk_uuid}` | `chunk_uuid` (uses module `logging.debug`, not a `logger` instance) | No |

#### `chunking/verbose_page_debug_logger.py`

Both messages are gated on the page number being in `DEBUG_PAGE_NUMBERS` (default `{1}`) and on the DEBUG level being enabled.

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| `is_verbose_page_debug` | DEBUG | `[{context}] Extra logging enabled for page {page_number}. To change, update DEBUG_PAGE_NUMBERS in config.` | `context`, `page_number` | No |
| `log_verbose_page_debug` | DEBUG | `[{context}] {message}` | `context`, caller-supplied `message` | No |

### Word-stream strategy

#### `chunking/strategies/word_stream/handler.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| `chunk` | INFO | `Word-stream chunking complete: %s chunks from %s pages` | chunk count, page count | No |
| `chunk` | ERROR | `Error extracting chunks from document using word-stream strategy: %s` | exception | No |
| `_process_page` | INFO | `Page %s has no words, skipping` | `page.page_num` | No |
| `_process_page` | DEBUG | `Page %s flagged as containing handwriting` | `page.page_num` | No |
| `_detect_handwriting` | DEBUG | `Handwriting detected: word='%s' bbox=%s` | word text, word bbox (`x`, `y`, `width`, `height`) or `None` | No |
| `_get_words_from_page` | WARNING | `Page %s has no get_text_and_words method; returning no words` | `page.page_num` | No |

#### `chunking/strategies/word_stream/chunker.py`

| Function | Level | Message | Interpolated attributes | exc_info |
|----------|-------|---------|-------------------------|----------|
| `_finalize_chunk` (chunk creation) | DEBUG | `Creating word-stream chunk page=%s index=%s words=%s reason=%s` | `page_number`, `chunk_index`, `state.word_count`, `reason` | No |

---

## Summary by level

| Level | Typical use |
|-------|-------------|
| DEBUG | Diagnostic detail — chunk creation, UUID generation, handwriting detection, verbose per-page tracing, harmless version conflicts. Suppressed at the default INFO level. |
| INFO | Normal progress — runner lifecycle, S3/Textract steps, embedding counts, indexing counts, health-check pass. |
| WARNING | Recoverable / skip conditions — local dev mode, no document from Textract, no chunks, empty pages, missing methods. |
| ERROR | Operation failures that are caught — S3 download/upload/delete, Textract failure, embedding failure, indexing delete failure, health-check failure. |
| CRITICAL | Fatal pipeline conditions — health check failed at startup, invalid S3 URI, pipeline failure, unexpected runner error. |

## Notes / observations

- Several statements use the module-level `logging.*` call rather than the module's named `logger` instance: `embedding_generator.py` (`logging.debug`) and `schemas.py` (`logging.debug`). These still emit via the root logger but are not namespaced to their module.
- `exc_info=True` (full traceback) is attached only in: `pipeline.py` (both CRITICAL handlers and the cleanup ERROR), `runner.py` (fatal CRITICAL), and `indexer.py` (`delete_documents_by_source_doc_id` DEBUG + ERROR).
- Because of the `ContextFilter`, most messages emitted during document processing are automatically prefixed with the active `source_doc_id`.
- One commented-out log call exists in `layout_text.py` (line 177) and is not counted, and layout/line-sentence strategies are excluded per request.
