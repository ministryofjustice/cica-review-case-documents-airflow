# Design Document

## Overview

This design propagates the `page_contains_handwriting` boolean from chunk-level data to the `page_metadata` OpenSearch index. The pipeline already detects handwriting during word-stream chunking via Textract's `text_type` classification. This change surfaces that signal at the page level so the UI can display a handwriting indicator without querying the `page_chunks` index.

The key architectural change is reordering the pipeline: page metadata `DocumentPage` objects are still created early (they depend on image upload, not chunking), but their indexing into OpenSearch is deferred until after chunking completes and the handwriting flag has been propagated.

## Architecture

### Current Pipeline Execution Order

```
1. Textract processing → Document
2. Page processing (images + DocumentPage creation) → List[DocumentPage]
3. Page metadata indexing (page_indexer.index_documents)
4. Chunking → ProcessedDocument(chunks: List[DocumentChunk])
5. Embedding generation (per chunk)
6. Chunk indexing (chunk_indexer.index_documents)
```

### New Pipeline Execution Order

```
1. Textract processing → Document
2. Page processing (images + DocumentPage creation) → List[DocumentPage]
3. Chunking → ProcessedDocument(chunks: List[DocumentChunk])
4. Handwriting flag propagation (chunks → page metadata)
5. Embedding generation (per chunk)
6. Chunk indexing (chunk_indexer.index_documents)
7. Page metadata indexing (page_indexer.index_documents)
```

### Data Flow Diagram

```
Textract Document
       │
       ├──► PageProcessor.process() ──► List[DocumentPage]
       │                                      │
       └──► Chunker.chunk() ──► List[DocumentChunk]
                                      │       │
                                      │       ▼
                                      │   propagate_handwriting_flags()
                                      │       │
                                      │       ▼
                                      │   List[DocumentPage] (updated)
                                      │       │
                                      ▼       ▼
                              chunk_indexer   page_indexer
```

## Components Affected

### 1. `DocumentPage` Model (`src/ingestion_pipeline/chunking/schemas.py`)

Add `page_contains_handwriting: bool = False` field.

```python
class DocumentPage(BaseModel):
    """Represents a single page's metadata for indexing."""

    source_doc_id: str = Field(..., description="The unique ID of the source document.")
    page_num: int = Field(..., description="The page number (1-based).")
    page_count: int = Field(..., description="Total number of pages in the document.")
    page_id: str = Field(..., description="UUID for the index.")
    s3_page_image_s3_uri: str = Field(..., description="S3 URI of the page image.")
    text: str = Field(..., description="Structured ocr content for the front end rendering.")
    page_width: float
    page_height: float
    received_date: datetime
    correspondence_type: str = Field(..., description="Type of correspondence.")
    page_contains_handwriting: bool = Field(
        default=False, description="Whether any word on this page was classified as handwritten."
    )
```

No changes to `DocumentPageFactory` are needed — the field defaults to `False` and will be set by the propagation step.

### 2. Pipeline Orchestration (`src/ingestion_pipeline/orchestration/pipeline.py`)

Reorder `process_document()` to defer page metadata indexing and add a propagation step:

```python
def process_document(self, document_metadata: DocumentMetadata):
    # ... existing setup and textract processing ...

    # Create page metadata records (images uploaded, DocumentPage objects constructed)
    page_documents = self.page_processor.process(document, updated_metadata)

    # Chunk the document (handwriting detection happens here per page)
    processed_data = self.chunker.chunk(document, updated_metadata)
    if not processed_data.chunks:
        logger.warning("No chunks were generated. Skipping embedding and indexing.")
        # Still index page metadata even if no chunks (pages exist but may be empty)
        self.page_indexer.index_documents(page_documents, id_field="page_id")
        return

    # Propagate handwriting flags from chunks to page metadata
    self._propagate_handwriting_flags(page_documents, processed_data.chunks)

    # Generate embeddings
    for chunk in processed_data.chunks:
        chunk.embedding = self.embedding_generator.generate_embedding(chunk.chunk_text)

    # Index chunks first, then page metadata
    self.chunk_indexer.index_documents(processed_data.chunks)
    self.page_indexer.index_documents(page_documents, id_field="page_id")
```

Add a private method for propagation:

```python
@staticmethod
def _propagate_handwriting_flags(
    page_documents: List[DocumentPage],
    chunks: List[DocumentChunk],
) -> None:
    """Set page_contains_handwriting on DocumentPage objects using chunk data.

    For each page, if any chunk on that page has page_contains_handwriting=True,
    the corresponding DocumentPage is updated to True.

    Raises PipelineError if any chunk references a page_number that has no
    corresponding DocumentPage — this indicates a data integrity violation.

    Args:
        page_documents: List of DocumentPage objects to update in place.
        chunks: List of DocumentChunk objects containing handwriting flags.

    Raises:
        PipelineError: If a chunk references a page_number not in page_documents.
    """
    page_num_set = {page_doc.page_num for page_doc in page_documents}

    pages_with_handwriting: set[int] = set()
    for chunk in chunks:
        if chunk.page_number not in page_num_set:
            raise PipelineError(
                f"Chunk '{chunk.chunk_id}' references page_number={chunk.page_number} "
                f"which has no corresponding DocumentPage (source_doc_id={chunk.source_doc_id}). "
                f"Available page numbers: {sorted(page_num_set)}"
            )
        if chunk.page_contains_handwriting:
            pages_with_handwriting.add(chunk.page_number)

    for page_doc in page_documents:
        if page_doc.page_num in pages_with_handwriting:
            page_doc.page_contains_handwriting = True
```

### 3. OpenSearch Page Metadata Index Template (`local-dev-environment/init-scripts/lib/opensearch_templates.inc`)

Add `page_contains_handwriting` to the `page_metadata_template` mappings:

```json
"page_contains_handwriting": { "type": "boolean" }
```

This field does not need to be indexed for search (the UI will just read it when fetching page metadata), but having it as a standard boolean field allows future filtering if needed.

### 4. Error Handling and Cleanup

The existing `_cleanup_indexed_data()` method already deletes from both `chunk_indexer` and `page_indexer` indices. With the new ordering (chunks indexed before page metadata), the failure scenarios are:

| Failure Point | Chunks in OpenSearch | Page Metadata in OpenSearch | Cleanup |
|---|---|---|---|
| After chunk indexing, before page metadata indexing | Yes | No | `_cleanup_indexed_data` deletes both |
| After both indexed | Yes | Yes | Success path, no cleanup needed |
| Before chunk indexing | No | No | Nothing to clean up |

The existing cleanup logic handles all cases because it unconditionally attempts deletion from both indices.

## Downstream Consumer Impact (cica-review-case-documents)

### Search Results (no change needed)

Search results already display the handwriting tag using `page_contains_handwriting` from the `page_chunks` index (`search/macro/search-result-item/template.njk`). This continues to work as-is.

### Page Viewers (minor changes needed in the UI project)

The API's `getPageMetadataByDocumentIdAndPageNumber()` in `api/DAL/document-dal.js` uses a hardcoded `_source` filter:

```javascript
_source: ['correspondence_type', 'page_count', 'page_num', 's3_page_image_s3_uri', 'text']
```

To expose the handwriting flag to the page viewers:
1. Add `'page_contains_handwriting'` to this `_source` array
2. Pass it through the `page-metadata-service.js` response
3. Include it in the template context for `imageview.njk` and `textview.njk`
4. Render a GOV.UK tag (same pattern as the search result template)

These are frontend-only changes in the sibling project and are outside the scope of this pipeline spec.

## Test Strategy

### Unit Tests

1. **DocumentPage model** — Verify `page_contains_handwriting` defaults to `False`, can be set to `True`, and is included in `model_dump()` output.

2. **Pipeline `_propagate_handwriting_flags()`** — Test cases:
   - Single page with handwriting chunks → flag set to `True`
   - Single page without handwriting chunks → flag remains `False`
   - Multiple pages with mixed handwriting → only correct pages flagged
   - Page with no corresponding chunks → flag remains `False`
   - Chunks referencing non-existent page numbers → no error raised

3. **Pipeline `process_document()` execution order** — Verify:
   - `page_indexer.index_documents` is called AFTER `chunk_indexer.index_documents`
   - `page_indexer.index_documents` receives DocumentPage objects with correct handwriting flags
   - When no chunks are generated, page metadata is still indexed (with default `False` flags)

4. **Existing chunk tests** — Ensure no regressions in `DocumentChunk` field values, ordering, or count.

### Integration-Level Verification

- Verify the OpenSearch `page_metadata_template` accepts documents with `page_contains_handwriting` field without mapping errors (covered by existing local-dev-environment setup).

## File Changes Summary

| File | Change |
|------|--------|
| `src/ingestion_pipeline/chunking/schemas.py` | Add `page_contains_handwriting` field to `DocumentPage` |
| `src/ingestion_pipeline/orchestration/pipeline.py` | Reorder indexing, add `_propagate_handwriting_flags()` method |
| `local-dev-environment/init-scripts/lib/opensearch_templates.inc` | Add `page_contains_handwriting` boolean mapping to `page_metadata_template` |
| `tests/orchestration/test_pipeline.py` | New/updated tests for execution order and propagation |
| `tests/chunking/test_schemas.py` | Test new `DocumentPage` field |
