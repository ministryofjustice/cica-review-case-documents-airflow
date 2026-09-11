# Ingestion Pipeline Application Architecture

Internal architecture of the ingestion pipeline application code
(`src/ingestion_pipeline/`). This reflects the code as it exists today. See
`architecture-review.md` for the accompanying review and `infrastructure-review.md`
for deployment topology.

## Composition & Dependency Injection

`build_pipeline()` is the composition root: it constructs every component (via
AWS client factories and the chunk-strategy factory) and injects them into the
`Pipeline` orchestrator.

```mermaid
flowchart TB
    subgraph BUILD["pipeline_builder.build_pipeline() - composition root"]
        direction TB
        FACT_AWS["aws_client factories<br/>get_s3_client / get_textract_client<br/>get_textractor_instance"]
        FACT_CHUNK["get_chunk_strategy()<br/>chunk strategy factory"]
        SETTINGS["settings (pydantic-settings singleton)"]
    end

    SETTINGS -. "config" .-> FACT_AWS
    SETTINGS -. "config" .-> FACT_CHUNK
    SETTINGS -. "config" .-> BUILD

    FACT_AWS --> TP[TextractProcessor]
    FACT_AWS --> S3SVC[S3DocumentService]
    FACT_CHUNK --> CHUNKER[ChunkStrategy impl]

    BUILD --> TP
    BUILD --> S3SVC
    BUILD --> EMB[EmbeddingGenerator]
    BUILD --> IDX_C[OpenSearchIndexer<br/>chunk index]
    BUILD --> IDX_P[OpenSearchIndexer<br/>page-metadata index]
    BUILD --> PP[PageProcessor]

    S3SVC --> PP
    IMGC[ImageConverter] --> PP
    PF[DocumentPageFactory] --> PP

    TP --> PIPE[[Pipeline]]
    CHUNKER --> PIPE
    EMB --> PIPE
    IDX_C --> PIPE
    IDX_P --> PIPE
    PP --> PIPE

    classDef root fill:#e7d9ff,stroke:#7c3aed,color:#000;
    classDef comp fill:#cfe8ff,stroke:#1f6feb,color:#000;
    class FACT_AWS,FACT_CHUNK,SETTINGS,BUILD root;
    class TP,S3SVC,CHUNKER,EMB,IDX_C,IDX_P,PP,IMGC,PF,PIPE comp;
```

## Per-Document Processing Flow

`Pipeline.process_document(document_metadata)` orchestrates the stages for a
single document.

```mermaid
flowchart TB
    IN[/DocumentMetadata/] --> T

    subgraph PIPELINE["Pipeline.process_document()"]
        direction TB
        T["1 - Textract analysis<br/>TextractProcessor.process_document()"]
        T --> TCHECK{Document<br/>returned?}
        TCHECK -->|no| SKIP([Skip - warn and return])
        TCHECK -->|yes| MC["2 - update page_count<br/>metadata.model_copy"]
        MC --> PPROC["3 - page processing<br/>render images, upload to S3,<br/>build DocumentPage list"]
        PPROC --> CH["4 - chunk<br/>ChunkStrategy.chunk()"]
        CH --> CCHECK{Chunks<br/>produced?}
        CCHECK -->|no| NOCHUNK["delete existing chunks,<br/>index page meta, return"]
        CCHECK -->|yes| HW["5 - propagate handwriting flags<br/>chunks to pages"]
        HW --> EMB["6 - generate embeddings<br/>per chunk via Bedrock"]
        EMB --> IDXC["7 - index chunks<br/>OpenSearch chunk index"]
        IDXC --> IDXP["8 - index page metadata<br/>OpenSearch page index"]
        IDXP --> OK([Success])
    end

    T -. "on error" .-> ERR
    PPROC -. "on error" .-> ERR
    CH -. "on error" .-> ERR
    EMB -. "on error" .-> ERR
    IDXC -. "on error" .-> ERR
    IDXP -. "on error" .-> ERR
    ERR["_cleanup_indexed_data()<br/>delete chunks + page meta from OpenSearch"] --> RERAISE([Re-raise])

    classDef stage fill:#d7f5d7,stroke:#2e7d32,color:#000;
    classDef err fill:#ffd6d6,stroke:#c92a2a,color:#000;
    class T,MC,PPROC,CH,HW,EMB,IDXC,IDXP stage;
    class ERR,RERAISE err;
```

> Note: on a late-stage failure, `_cleanup_indexed_data()` currently removes only
> OpenSearch data — uploaded page images are not deleted (planned work, issue 6a
> in `infrastructure-review.md`).

## Chunking Strategy Selection

`get_chunk_strategy()` selects one `ChunkStrategy` implementation from
`settings.DOCUMENT_CHUNKING_STRATEGY`. All implement the same ABC and return a
`ProcessedDocument`.

```mermaid
flowchart TB
    CFG["settings.DOCUMENT_CHUNKING_STRATEGY"] --> FACT{{"get_chunk_strategy()"}}
    FACT -->|"textractor-word-stream<br/>(default)"| WS["TextractorWordStreamDocumentChunker"]
    FACT -->|"layout"| LO["TextractLayoutDocumentChunker"]
    FACT -->|"linear-sentence-splitter"| LS["LineBasedDocumentChunker"]

    LO --> SUB["per-layout-type sub-strategies:<br/>Text / Table / KeyValue / List"]

    WS -. implements .-> ABC["ChunkStrategy (ABC)<br/>chunk(doc, metadata) to ProcessedDocument"]
    LO -. implements .-> ABC
    LS -. implements .-> ABC

    classDef abc fill:#e7d9ff,stroke:#7c3aed,color:#000;
    classDef impl fill:#cfe8ff,stroke:#1f6feb,color:#000;
    class ABC abc;
    class WS,LO,LS,SUB impl;
```

## Core Data Models

Pydantic models passed between stages (defined in `chunking/schemas.py`).

```mermaid
flowchart LR
    DM["DocumentMetadata<br/>(frozen)"] --> DP[DocumentPage]
    DM --> DC[DocumentChunk]
    DC --> PD["ProcessedDocument<br/>(chunks list)"]
    BB["DocumentBoundingBox<br/>(frozen)"] --> DC
    DC -. "embedding filled<br/>at embed stage" .-> DC

    classDef model fill:#d7f5d7,stroke:#2e7d32,color:#000;
    class DM,DP,DC,PD,BB model;
```

- **DocumentMetadata** (frozen): source doc id, filename, S3 URI, case ref,
  received date, correspondence type, page count (filled after Textract).
- **DocumentPage**: per-page metadata for the page-metadata index (page id, image
  S3 URI, dimensions, handwriting flag).
- **DocumentChunk**: chunk text + bounding box + embedding (filled at the embed
  stage) + case metadata; computed `character_count` / `word_count`.
- **ProcessedDocument**: container holding the list of `DocumentChunk`.
- **DocumentBoundingBox** (frozen): wrapper around the Textractor bounding box.
