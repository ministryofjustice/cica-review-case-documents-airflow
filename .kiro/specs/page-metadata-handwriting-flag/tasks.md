# Implementation Tasks

## Task 1: Add `page_contains_handwriting` field to DocumentPage model

### Description
Add the `page_contains_handwriting` boolean field to the `DocumentPage` Pydantic model with a default value of `False`.

### Files to modify
- `src/ingestion_pipeline/chunking/schemas.py`

### Requirements met
- Requirement 1 (AC 1, 2, 3)

### Acceptance criteria
1. `DocumentPage` has a `page_contains_handwriting: bool` field defaulting to `False`
2. Setting `page_contains_handwriting = True` on a constructed instance works without error
3. `model_dump()` output includes `page_contains_handwriting` with the correct boolean value

---

## Task 2: Add `page_contains_handwriting` to the page_metadata OpenSearch index template

### Description
Add the `page_contains_handwriting` boolean mapping to the `page_metadata_template` in the local dev environment OpenSearch init script.

### Files to modify
- `local-dev-environment/init-scripts/lib/opensearch_templates.inc`

### Requirements met
- Requirement 2 (AC 1, 2, 3, 4)

### Acceptance criteria
1. The `page_metadata_template` mappings include `"page_contains_handwriting": { "type": "boolean" }`
2. The field is placed alongside the other property definitions in the template

---

## Task 3: Add `_propagate_handwriting_flags()` method to Pipeline

### Description
Add a static method to the `Pipeline` class that iterates over chunks, collects page numbers where `page_contains_handwriting` is `True`, and sets the flag on corresponding `DocumentPage` objects.

### Files to modify
- `src/ingestion_pipeline/orchestration/pipeline.py`

### Requirements met
- Requirement 3 (AC 1, 2, 3, 4, 5)

### Acceptance criteria
1. If any chunk for a page has `page_contains_handwriting=True`, the corresponding `DocumentPage` is set to `True`
2. If all chunks for a page have `page_contains_handwriting=False`, the `DocumentPage` remains `False`
3. Matching uses `DocumentChunk.page_number` == `DocumentPage.page_num` (integer equality)
4. Pages with no corresponding chunks retain the default `False`
5. If any chunk references a `page_number` not present in `page_documents`, a `PipelineError` is raised with the mismatched page number and source document ID

---

## Task 4: Reorder pipeline execution — defer page metadata indexing

### Description
Modify `Pipeline.process_document()` to:
1. Create `DocumentPage` objects (page processing) before chunking (unchanged)
2. Chunk the document
3. Call `_propagate_handwriting_flags()` after chunking
4. Generate embeddings
5. Index chunks into `page_chunks`
6. Index page metadata into `page_metadata` (moved to after chunk indexing)

Handle the edge case where no chunks are generated: page metadata should still be indexed with default `False` flags.

### Files to modify
- `src/ingestion_pipeline/orchestration/pipeline.py`

### Requirements met
- Requirement 4 (AC 1, 2, 3, 4, 5, 6, 7)
- Requirement 5 (AC 1, 4)

### Acceptance criteria
1. `page_indexer.index_documents` is called AFTER `chunk_indexer.index_documents` in the normal flow
2. When chunking produces no chunks, `page_indexer.index_documents` is still called (pages exist even if empty)
3. `_propagate_handwriting_flags()` is called after `self.chunker.chunk()` and before embedding generation
4. On any pipeline failure, `_cleanup_indexed_data()` continues to delete from both indices
5. `DocumentChunk` objects are not modified by the propagation step (Requirement 5 AC 4)

---

## Task 5: Add unit tests for `_propagate_handwriting_flags()`

### Description
Write unit tests covering the propagation logic as an isolated static method.

### Files to modify
- `tests/orchestration/test_pipeline.py`

### Requirements met
- Requirement 3 (AC 1, 2, 3, 4, 5)

### Test cases
1. Single page with one handwriting chunk → page flag set to `True`
2. Single page with multiple chunks, one has handwriting → page flag set to `True`
3. Single page with all chunks `page_contains_handwriting=False` → page flag remains `False`
4. Multiple pages: page 1 has handwriting, page 2 does not → only page 1 flagged
5. Page with no corresponding chunks → page flag remains `False`
6. Chunk references a `page_number` not in `page_documents` → `PipelineError` raised with descriptive message
7. Empty chunks list → all page flags remain `False`

---

## Task 6: Update pipeline execution order tests

### Description
Update existing pipeline tests and add new ones to verify the new execution order and that page metadata documents contain the correct handwriting flag values after processing.

### Files to modify
- `tests/orchestration/test_pipeline.py`

### Requirements met
- Requirement 4 (AC 1-7)
- Requirement 5 (AC 1, 2, 3)

### Test cases
1. Verify `page_indexer.index_documents` is called after `chunk_indexer.index_documents` (call order assertion)
2. Verify `page_indexer.index_documents` receives `DocumentPage` objects with handwriting flags propagated
3. Verify when no chunks generated, page metadata is still indexed with `page_contains_handwriting=False`
4. Verify chunk objects passed to `chunk_indexer` retain all original fields unchanged
5. Verify on `ChunkError`, cleanup deletes from both indices and page metadata was not yet indexed
6. Verify on `IndexingError` from chunk indexer, cleanup deletes from both indices

---

## Task 7: Add DocumentPage model field test

### Description
Add a test to the schemas test file verifying the new `page_contains_handwriting` field on `DocumentPage`.

### Files to modify
- `tests/chunking/test_schemas.py`

### Requirements met
- Requirement 1 (AC 1, 2, 3)

### Test cases
1. `DocumentPage` constructed without explicit `page_contains_handwriting` → field is `False`
2. `DocumentPage` constructed with `page_contains_handwriting=True` → field is `True`
3. `model_dump()` includes `page_contains_handwriting` key with correct value
4. Field can be updated via assignment after construction

---

## Task 8: Verify existing handwriting detection and logging (no code changes expected)

### Description
Confirm that the existing `_detect_handwriting()` method in `TextractorWordStreamDocumentChunker` already satisfies Requirement 6 (debug logging). Review the implementation against the acceptance criteria and add any missing log statements if needed.

### Files to review
- `src/ingestion_pipeline/chunking/strategies/word_stream/handler.py`

### Requirements met
- Requirement 5 (AC 2, 3)
- Requirement 6 (AC 1, 2, 3, 4)

### Acceptance criteria
1. Handwritten words log text + bounding box coordinates at DEBUG level ✓ (already implemented)
2. Missing bounding box logs "None" ✓ (already implemented — `"None"` string via conditional format)
3. Non-handwriting pages produce no word-level DEBUG entries ✓ (only logs inside `if text_type == HANDWRITING`)
4. Page-level summary logged when handwriting detected ✓ (already implemented — `"Page %s flagged as containing handwriting"`)
