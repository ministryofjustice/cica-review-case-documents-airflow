# Requirements Document

## Introduction

Propagate the `page_contains_handwriting` boolean flag from chunk-level data to the page metadata OpenSearch index. Handwriting detection already runs during word-stream chunking (in `_detect_handwriting()`) and is stored on each `DocumentChunk`. This feature surfaces that per-page handwriting status to the `page_metadata` index so the downstream UI can display a handwriting indicator without querying the chunks index.

The core change requires reordering the pipeline: page metadata must be indexed AFTER chunking completes, so the handwriting flag derived from chunks can be propagated to the corresponding page metadata records before they are persisted.

## Glossary

- **Pipeline**: The document processing orchestrator (`Pipeline` class) that coordinates Textract analysis, page processing, chunking, embedding generation, and indexing.
- **Page_Metadata_Index**: The `page_metadata` OpenSearch index that stores per-page information (image URI, dimensions, text, received date) for UI rendering.
- **Page_Chunks_Index**: The `page_chunks` OpenSearch index that stores text chunks with embeddings and metadata for vector search.
- **DocumentPage**: The Pydantic model representing a single page's metadata for indexing into Page_Metadata_Index.
- **DocumentChunk**: The Pydantic model representing a text chunk, which already carries a `page_contains_handwriting` boolean field.
- **Handwriting_Flag**: The `page_contains_handwriting` boolean field indicating whether any word on a page was classified as handwritten by Textract.
- **PageProcessor**: The component responsible for generating page images, uploading them to S3, and constructing DocumentPage objects.
- **Chunker**: The chunking strategy (currently word-stream) that produces chunks from a Textract document and performs per-page handwriting detection.

## Requirements

### Requirement 1: DocumentPage Model Field

**User Story:** As a pipeline developer, I want the `DocumentPage` model to include a `page_contains_handwriting` field, so that handwriting status can be persisted to the page metadata index.

#### Acceptance Criteria

1. THE DocumentPage SHALL include a `page_contains_handwriting` field of type `bool` with a default value of `False`.
2. THE DocumentPage SHALL allow the `page_contains_handwriting` field to be updated via direct attribute assignment after initial construction.
3. WHEN a DocumentPage is serialized for indexing via `model_dump()`, THE DocumentPage SHALL include the `page_contains_handwriting` key in its top-level output with the current boolean value of the field.

### Requirement 2: OpenSearch Page Metadata Index Template

**User Story:** As a platform operator, I want the `page_metadata` index template to include the `page_contains_handwriting` mapping, so that the field is correctly stored and queryable in OpenSearch.

#### Acceptance Criteria

1. THE Page_Metadata_Index template SHALL define a `page_contains_handwriting` property with type `boolean` in the `mappings.properties` section of the `page_metadata_template` index template.
2. WHEN a DocumentPage containing `page_contains_handwriting` set to `True` or `False` is indexed, THE Page_Metadata_Index SHALL store the boolean value without mapping errors or type coercion failures.
3. WHEN the Page_Metadata_Index is queried and page metadata is retrieved, THE response SHALL include the `page_contains_handwriting` field with the exact boolean value (`true` or `false`) that was indexed.
4. WHEN a DocumentPage is indexed without an explicit `page_contains_handwriting` value, THE Page_Metadata_Index SHALL store the field with the default value of `false` as provided by the DocumentPage model serialization.

### Requirement 3: Handwriting Flag Propagation from Chunks to Page Metadata

**User Story:** As a CICA case worker, I want page metadata to indicate which pages contain handwriting, so that the UI can show me a handwriting indicator per page without needing to query the chunks index.

#### Acceptance Criteria

1. WHEN any DocumentChunk for a given page has `page_contains_handwriting` equal to `True`, THE Pipeline SHALL set `page_contains_handwriting` to `True` on the corresponding DocumentPage for that page.
2. WHEN all DocumentChunks for a given page have `page_contains_handwriting` equal to `False`, THE Pipeline SHALL leave `page_contains_handwriting` as `False` on the corresponding DocumentPage for that page.
3. THE Pipeline SHALL match chunks to pages by comparing the `page_number` field on DocumentChunk to the `page_num` field on DocumentPage using integer equality within the same document.
4. WHEN a page has no corresponding chunks, THE Pipeline SHALL leave `page_contains_handwriting` as the default value of `False` on that page's DocumentPage.
5. IF a DocumentChunk references a `page_number` that does not correspond to any DocumentPage in the current document, THEN THE Pipeline SHALL raise a PipelineError indicating the mismatched page number and source document ID, as this represents a data integrity violation.

### Requirement 4: Pipeline Execution Order

**User Story:** As a pipeline developer, I want page metadata to be indexed after chunking completes, so that handwriting detection results from chunking can be propagated to page metadata before it is persisted.

#### Acceptance Criteria

1. THE Pipeline SHALL execute Textract document processing as the first step.
2. THE Pipeline SHALL create page metadata records (DocumentPage objects) before chunking.
3. THE Pipeline SHALL execute chunking after page metadata records are created.
4. THE Pipeline SHALL propagate handwriting flags from chunks to page metadata records after chunking completes and before page metadata is indexed.
5. THE Pipeline SHALL generate embeddings for chunks after handwriting flag propagation.
6. THE Pipeline SHALL index chunks into the Page_Chunks_Index after embedding generation.
7. THE Pipeline SHALL index page metadata into the Page_Metadata_Index after chunk indexing.

### Requirement 5: Existing Chunk Data Preservation

**User Story:** As a pipeline developer, I want existing chunk data including the `page_contains_handwriting` field on DocumentChunk to remain unchanged, so that no regressions are introduced in the chunks index.

#### Acceptance Criteria

1. WHEN a document is processed, THE Pipeline SHALL produce DocumentChunk objects with the same fields, values, count, and ordering as would be produced without the page metadata handwriting propagation logic.
2. THE Chunker SHALL detect handwriting and set `page_contains_handwriting` on each DocumentChunk using only the Textract word-level `text_type` classification, without reading from or depending on DocumentPage state.
3. WHEN the Page_Chunks_Index is queried after ingestion, THE response SHALL include all DocumentChunk fields (`chunk_id`, `source_doc_id`, `chunk_text`, `source_file_name`, `page_count`, `page_number`, `chunk_index`, `source_file_s3_uri`, `chunk_type`, `confidence`, `bounding_box`, `embedding`, `case_ref`, `received_date`, `correspondence_type`, `page_contains_handwriting`, `character_count`, `word_count`) with values identical to those produced by the chunking and embedding stages.
4. IF the handwriting propagation step fails, THEN THE Pipeline SHALL not modify any DocumentChunk data that has already been produced by the Chunker.

### Requirement 6: Debug Logging of Handwriting Detection

**User Story:** As a pipeline developer, I want handwriting detection to log each handwritten word's text and bounding box at DEBUG level, so that I can troubleshoot detection behavior.

#### Acceptance Criteria

1. WHEN a word is classified as handwriting, THE Handwriting_Flag detection logic SHALL log at DEBUG level: the word text, bounding box coordinates (x, y, width, height), and the page number where the handwriting was detected.
2. WHEN a word is classified as handwriting but its bounding box is unavailable, THE Handwriting_Flag detection logic SHALL log the word text and page number at DEBUG level with "None" in place of bounding box coordinates.
3. WHEN no words on a page are classified as handwriting, THE Handwriting_Flag detection logic SHALL not emit any word-level DEBUG log entries for that page.
4. WHEN at least one word on a page is classified as handwriting, THE Handwriting_Flag detection logic SHALL log a page-level DEBUG summary indicating the page number was flagged as containing handwriting.
