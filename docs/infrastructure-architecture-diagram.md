# Infrastructure Architecture & Data Flow

Target infrastructure topology and data flow for the CICA Review Case Documents
system. This reflects the *proposed target design* described in
`infrastructure-review.md`, including items still to be built (SQS trigger,
temporary AP staging bucket, cross-account IRSA). Open decisions are noted on the
diagram.

> Legend: solid arrows = data/document flow; dashed arrows = control/trigger or
> access-scoped calls. Account/platform boundaries are shown as subgraphs.
>
> The topology reads left to right following the lifecycle of the data:
> **CICA AWS Account** (source of case documents) →
> **MoJ Analytical Platform** (ingestion processing) →
> **MoJ Cloud Platform** (data storage + UI). An invisible ordering link
> (`CICA ~~~ AP ~~~ CP`) pins this left-to-right layout so the platforms stay in
> lifecycle order regardless of the cross-boundary edges.

## Target Topology & Data Flow

```mermaid
flowchart LR
    subgraph CICA["CICA AWS Account"]
        direction TB
        SRC[("S3: Source Case Buckets<br/>PDFs")]
        PAGES[("S3: Page-Image Bucket")]
        PRODUCER[Message Producer]
        Q_CICA{{"SQS: Ingestion Queue<br/>(option A - CICA)"}}
    end

    subgraph AP["MoJ Analytical Platform"]
        direction TB
        AIRFLOW[Airflow<br/>orchestration]
        PIPE[Ingestion Pipeline<br/>container]
        TMP[("S3: Temporary<br/>Staging Bucket")]
        TEXTRACT[AWS Textract<br/>OCR + layout]
        BEDROCK_AP["AWS Bedrock<br/>Titan Embed v2<br/>chunk embedding<br/>(current - to be retired)"]
    end

    subgraph CP["MoJ Cloud Platform"]
        direction TB
        Q_CP{{"SQS: Ingestion Queue<br/>(option B - preferred)"}}
        OS[("OpenSearch<br/>text + vectors")]
        CONNECTOR[OpenSearch<br/>Bedrock connector]
        BEDROCK_CP[AWS Bedrock<br/>query + chunk embedding]
        UI[UI Application<br/>hybrid search]
    end

    %% Enforce left-to-right ordering of platforms: CICA -> AP -> CP
    CICA ~~~ AP ~~~ CP

    %% Trigger path
    PRODUCER -. "1 - send msg<br/>(corr. type + S3 URI)" .-> Q_CP
    PRODUCER -. "1 - alt" .-> Q_CICA
    Q_CP -. "2 - poll / drain" .-> AIRFLOW
    Q_CICA -. "2 - alt" .-> AIRFLOW
    AIRFLOW -. "3 - run" .-> PIPE

    %% Ingestion data flow
    SRC -- "4 - download source PDF<br/>(IRSA: read)" --> PIPE
    PIPE -- "5 - stage document" --> TMP
    TMP -- "6 - analyse" --> TEXTRACT
    TEXTRACT -- "7 - OCR text + layout" --> PIPE
    PIPE -. "8 - embed chunks<br/>(current)" .-> BEDROCK_AP
    BEDROCK_AP -. "9 - vectors" .-> PIPE
    PIPE -- "10 - write page images<br/>(IRSA: put/delete)" --> PAGES
    PIPE -- "11 - index chunks + page meta<br/>(IRSA or Transit GW)" --> OS

    %% Read path
    UI -- "12 - hybrid search" --> OS
    OS -- "13 - query embedding<br/>via connector" --> CONNECTOR
    OS -. "PLANNED - chunk embedding<br/>via connector at index time" .-> CONNECTOR
    CONNECTOR -- "14 - embed (query + chunks)" --> BEDROCK_CP
    UI -- "15 - fetch page images" --> PAGES

    classDef cica fill:#fde2c4,stroke:#b5651d,color:#000;
    classDef cp fill:#cfe8ff,stroke:#1f6feb,color:#000;
    classDef ap fill:#d7f5d7,stroke:#2e7d32,color:#000;
    classDef retire fill:#fff3bf,stroke:#e6a700,color:#000;
    class SRC,PAGES,PRODUCER,Q_CICA cica;
    class Q_CP,OS,CONNECTOR,BEDROCK_CP,UI cp;
    class AIRFLOW,PIPE,TMP,TEXTRACT ap;
    class BEDROCK_AP retire;
```

## Notes on the Diagram

- **Ingestion queue placement (open decision).** Shown as option A (CICA) and
  option B (Cloud Platform, preferred). Messages originate in CICA either way.
  Only one queue will exist in the final design.
- **Temporary staging bucket.** Because AP cannot run Textract cross-account
  against CICA S3, the pipeline stages the source document into an AP-side
  temporary bucket (step 5) and Textract reads from there (step 6). This bucket
  needs a short lifecycle expiry and explicit cleanup on success and failure.
- **Cross-account access via IRSA.** Steps 4, 10, and 11 cross account
  boundaries. The AP workload role must have: `s3:GetObject` on CICA source
  buckets (step 4); `s3:PutObject` **and** `s3:DeleteObject` on the CICA
  page-image bucket (step 10 + failure cleanup); and OpenSearch access (step 11)
  via cross-account IRSA or the MoJO Transit Gateway.
- **Embedding via the OpenSearch Bedrock connector (CP).** Query embedding is
  handled by an OpenSearch Bedrock connector that calls a Bedrock instance on
  Cloud Platform (steps 13-14) — not by the UI directly. **Chunk embedding is
  planned to move to the same connector** (dashed "PLANNED" edge), performed at
  index time on CP. This would retire the AP-side Bedrock embedding step
  (currently steps 8-9, shown amber) and mean the pipeline sends text rather than
  vectors to OpenSearch. Using one connector/model for both query and chunk
  embedding keeps the vectors in a shared space. (Textract does not perform
  embedding.)
- **Data classification.** Case documents (OFFICIAL / OFFICIAL-SENSITIVE) transit
  CICA -> AP temp bucket -> Textract, and extracted text + vectors land in
  OpenSearch on CP. Once chunk embedding moves to the CP connector, chunk text is
  also sent to CP Bedrock at index time. Confirm encryption at rest on the temp
  bucket and CP OpenSearch, and keep Textract in-region and both Bedrock
  instances (AP current, CP connector) in-region (`eu-west-2`).

## Failure / Cleanup Flow

```mermaid
flowchart TB
    START([Pipeline processes document]) --> UPLOAD[Upload page images to CICA bucket]
    UPLOAD --> LATER[Chunk / embed / index stages]
    LATER -->|success| DONE([Complete])
    LATER -->|failure| CLEANUP{Cleanup on failure}
    CLEANUP --> DEL_OS[Delete chunks + page meta from OpenSearch<br/>_cleanup_indexed_data]
    CLEANUP --> DEL_IMG[Delete page images from CICA bucket<br/>PLANNED - issue 6a]
    CLEANUP --> DEL_TMP[Delete staged doc from AP temp bucket<br/>PLANNED]
    DEL_OS --> RAISE[Propagate error to Airflow<br/>PLANNED - when Airflow enabled]
    DEL_IMG --> RAISE
    DEL_TMP --> RAISE

    classDef planned fill:#fff3bf,stroke:#e6a700,color:#000;
    class DEL_IMG,DEL_TMP,RAISE planned;
```

Highlighted (amber) nodes are planned work, not yet implemented:

- **Page-image deletion on failure** (issue 6a in `infrastructure-review.md`):
  currently only OpenSearch data is cleaned up on a late-stage failure; uploaded
  page images are orphaned.
- **Temp staging bucket cleanup**: lifecycle + explicit deletion still to be
  designed.
- **Error propagation to Airflow**: `runner.py` currently exits 0 on failure;
  will re-raise / exit non-zero once Airflow is configured, with a DLQ on the
  ingestion queue.
