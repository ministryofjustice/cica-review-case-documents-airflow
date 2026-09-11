# Infrastructure Architecture Review

A review of the proposed infrastructure architecture for the CICA Review Case
Documents system, cross-referenced against the current ingestion pipeline code.

> **Status:** The system is being built up and out — several components below are
> intentionally not yet implemented. This review distinguishes *planned design*
> from *current code* and flags decisions still to be worked out, rather than
> treating unbuilt pieces as defects.

## Proposed High-Level Process Flow

1. A message is sent to an SQS queue containing a correspondence type and an S3
   URI (the document location in a CICA AWS S3 bucket). Messages are sent from
   within the CICA account.
2. An Airflow workflow (on the Analytical Platform) listens/polls for new
   messages.
3. When a new message is found, the ingestion pipeline:
   - Retrieves the document from its CICA AWS S3 bucket and stores it in a
     temporary S3 bucket within the Analytical Platform processing environment.
   - Performs OCR text and layout extraction using AWS Textract (against the
     temporary AP bucket).
   - Performs vector embedding on extracted text chunks. *(Currently in-process
     via AP Bedrock; planned to move to the OpenSearch Bedrock connector on CP,
     embedding at index time — see Planned Work item 7.)*
   - Writes the data to an OpenSearch vector DB (Cloud Platform).
   - Writes page images to a page-image bucket within the CICA AWS account.
4. The UI application performs ranked hybrid searches on the OpenSearch vector DB.
5. The UI application displays the search results.

## Proposed Components

| Component      | AWS Location                     | Used For                                    |
| -------------- | -------------------------------- | ------------------------------------------- |
| Airflow        | Analytical Platform              | Orchestrate ingestion pipeline              |
| AWS Textract   | Analytical Platform              | OCR text and layout extraction              |
| AWS Bedrock    | Analytical Platform              | Chunk embedding (current — to be retired)   |
| AWS Bedrock    | Cloud Platform                   | Query + chunk embedding via OpenSearch connector (target) |
| OpenSearch Bedrock connector | Cloud Platform     | Query embedding now; chunk embedding (planned) |
| AWS SQS Queue  | Cloud Platform (likely) or CICA  | Document ingestion messages                 |
| Temporary S3   | Analytical Platform              | Staging documents for Textract processing   |
| OpenSearch     | Cloud Platform                   | Text and vector storage and retrieval       |
| AWS S3 Bucket  | CICA AWS                         | Case buckets containing source PDFs         |
| Page-image S3  | CICA AWS                         | Rendered page images for UI display         |

## Summary

The proposed topology is a sound, MoJ-idiomatic split: Analytical Platform (AP)
for the compute-heavy, AWS-service-rich ingestion (Airflow + Textract +
Bedrock), Cloud Platform (CP) for the user-facing UI and OpenSearch, and CICA's
own AWS account as the system of record for source PDFs and rendered page images.
Each platform is used for what it is designed for.

A key constraint shapes the design: **AP cannot support cross-account Textract
running against CICA's S3 bucket directly.** The design therefore pulls the
document from CICA S3 into a temporary AP-side bucket and runs Textract against
that staging bucket. This removes the cross-account Textract -> S3 dependency but
introduces a document-staging lifecycle that needs designing (see Planned Work).

The items below separate **planned work** (agreed direction, not yet built) from
**decisions still open** and **notes for the current code**.

## Planned Work (agreed direction, not yet implemented)

### 1. Document staging into a temporary AP bucket for Textract

Because AP cannot run Textract cross-account against CICA S3, the pipeline will
download the source document from CICA S3 and stage it in a temporary AP-side S3
bucket for Textract to process.

- **To work out:**
  - Lifecycle of the temporary bucket — objects should be deleted promptly after
    Textract completes (and on failure) so sensitive case documents do not linger
    in AP storage. A short S3 lifecycle expiry plus explicit cleanup is worth
    considering.
  - How this staging step reconciles with local development (LocalStack) and the
    existing `USE_MOD_PLATFORM_MODE` URI-remapping logic in
    `textract_processor.py`, which currently remaps to a sandbox bucket.
  - Data classification: case documents transit CICA -> AP temp bucket -> Textract.
    Confirm the temp bucket is encrypted at rest and access-scoped.
- **Files:** `src/ingestion_pipeline/textract/textract_processor.py`,
  `src/ingestion_pipeline/page_processor/s3_document_service.py`

### 2. Textract implementation to support both local dev and Airflow

The Textract implementation will change to support local development and running
on Airflow, in conjunction with the temporary staging bucket (exact mechanism
still to be determined).

- **Current code:** `_start_textract_job()` uses synchronous polling
  (`get_document_analysis` every 5s up to a 600s timeout) with no
  `NotificationChannel`. Given ingestion is low-volume and scheduled outside UI
  usage windows (see below), synchronous polling is a reasonable interim model;
  the 600s timeout ceiling is the main thing to keep an eye on for large
  documents.
- **To work out:** How Textract input/output buckets and job invocation behave
  identically enough across LocalStack and Airflow to keep one code path.
- **Files:** `src/ingestion_pipeline/textract/textract_processor.py`

### 3. Cross-account access via IRSA (replacing static keys)

The static keys in the code (`AWS_MOD_PLATFORM_*`, `AWS_CICA_AWS_*`) are for
local development only and will be replaced with cross-account IRSA (IAM Roles
for Service Accounts) in the deployed environment.

- **Note:** This resolves the earlier credential concern. IRSA also removes the
  need for the `get_textractor_instance()` process-wide env-var mutation hack
  (see architecture review, issue 3) — worth retiring that when IRSA lands.
- **To confirm:** CICA-side trust policy granting the AP service-account role
  read access to the source case buckets, and write access to the CICA page-image
  bucket.
- **Permission dependency for cleanup:** The page-image bucket is in the CICA
  account, so the failure-path cleanup in issue 6a requires the cross-account
  role to include `s3:DeleteObject` on the page bucket — not just `s3:PutObject`.
  If prefix-based deletion is used, `s3:ListBucket` (scoped to the
  `{case_ref}/{source_doc_id}/pages/` prefix) is also needed. Ensure the IRSA
  policy grants delete/list, or the cleanup will fail with access-denied and
  images will remain orphaned.
- **Files:** `src/ingestion_pipeline/aws_client/clients.py`,
  `src/ingestion_pipeline/config.py`

### 4. OpenSearch access via Transit Gateway or cross-account IRSA

OpenSearch access from AP will change to use either the MoJO Transit Gateway or
(most likely) cross-account IRSA. The local-development implementation
(`OPENSEARCH_PROXY_URL`, proxy sidecar) will continue to be supported.

- **To confirm for the deployed path:**
  - Authentication: the current client passes empty `http_auth=()`. Whichever
    connectivity model is chosen, ensure auth is enforced and the transport is
    TLS end-to-end (`OPENSEARCH_VERIFY_CERTS` defaults to `True`; production URL
    must be `https://`).
  - DNS/ingress: the k8s service-DNS example only resolves inside CP, so the AP
    side needs an appropriate ingress or IRSA-based access path.
- **Files:** `src/ingestion_pipeline/indexing/indexer.py`,
  `src/ingestion_pipeline/indexing/healthcheck.py`,
  `src/ingestion_pipeline/config.py`

### 5. SQS ingestion trigger consumer

A document-ingestion SQS queue (messages sent from within CICA) will trigger the
Airflow pipeline. This replaces the hardcoded single-document harness in
`runner.py` (the `# This is a placeholder for a real message from an SQS queue`
comment marks the spot).

- **Open decision:** Queue placement — Cloud Platform (leaning towards) or CICA.
  Messages originate in CICA regardless.
- **To work out:** Scheduled DAG draining the queue in batches vs sensor-based
  trigger. Given ingestion runs outside UI usage windows, a scheduled batch
  drain is likely sufficient.
- **Files:** `src/ingestion_pipeline/runner.py`

### 6. Error propagation via Airflow

Fatal errors will be propagated once Airflow is enabled and configured. Today
`runner.py` catches all exceptions, logs critical, and returns without re-raising
(exits 0).

- **To do when Airflow lands:** Re-raise / non-zero exit so Airflow marks the
  task failed, plus a dead-letter queue on the ingestion SQS queue for
  poison/failed messages.
- **Files:** `src/ingestion_pipeline/runner.py`

### 6a. On ingestion failure, page images are not deleted (cleanup gap)

Failure-path cleanup is currently asymmetric:

- Inside `PageProcessor.process()`, if the image *upload itself* fails partway,
  already-uploaded images are cleaned up via `S3DocumentService.delete_images()`.
- But once page processing *succeeds* and the pipeline proceeds to chunking,
  embedding, or indexing, a failure there calls
  `Pipeline._cleanup_indexed_data()`, which only deletes from the two OpenSearch
  indices. The successfully-uploaded page images are **not** removed.

**Result:** a document that fails after page-image upload but during
chunking/embedding/indexing leaves orphaned page images in the CICA page bucket.

- **Fix:** Extend the pipeline-level failure cleanup to also delete the uploaded
  page images. `S3DocumentService.delete_images(s3_keys)` already exists — the
  page S3 keys (or the `PageImageUploadResult` list / `DocumentPage`
  `s3_page_image_s3_uri` values) need to be made available to the cleanup path so
  the pipeline can call it alongside `_cleanup_indexed_data()`. Consider whether
  deletion should be keyed by the `{case_ref}/{source_doc_id}/pages/` prefix for
  robustness against partial knowledge of which keys were written.
- **Cross-account permission:** The page bucket is in CICA, so this cleanup
  depends on the IRSA role having `s3:DeleteObject` (and `s3:ListBucket` if
  deleting by prefix) on the page bucket — see Planned Work item 3.
- **Files:** `src/ingestion_pipeline/orchestration/pipeline.py`,
  `src/ingestion_pipeline/page_processor/processor.py`,
  `src/ingestion_pipeline/page_processor/s3_document_service.py`

### 7. Embedding moves to the OpenSearch Bedrock connector (CP)

Query embedding is handled by an OpenSearch Bedrock connector that calls a
Bedrock instance on Cloud Platform (not by the UI directly, and not by the AP
pipeline). **Chunk embedding is planned to move to the same connector**,
performed at index time on CP.

- **Current state:** The pipeline embeds chunks in-process via
  `EmbeddingGenerator` (a `bedrock-runtime` client calling `invoke_model` against
  AP Bedrock), then indexes vectors into OpenSearch.
- **Target:** The pipeline sends chunk *text* to OpenSearch, and the Bedrock
  connector embeds at index time using the same model/connector as query
  embedding — keeping query and document vectors in a shared space and retiring
  the AP-side embedding step.
- **Implications:**
  - `EmbeddingGenerator` and the per-chunk embedding loop in
    `Pipeline.process_document()` are removed from the ingestion path.
  - The AP workload no longer needs Bedrock access for embedding; the OpenSearch
    index needs an ingest pipeline / connector configured with the embedding
    model.
  - Chunk text (OFFICIAL / OFFICIAL-SENSITIVE) reaches CP Bedrock at index time —
    confirm the connector's Bedrock instance is in-region (`eu-west-2`).
- **Files:** `src/ingestion_pipeline/embedding/embedding_generator.py`,
  `src/ingestion_pipeline/orchestration/pipeline.py`,
  `src/ingestion_pipeline/pipeline_builder.py`

## Open Decisions to Record

- **Ingestion queue placement:** Cloud Platform (preferred) vs CICA. Messages are
  produced in CICA either way.
- **OpenSearch connectivity:** Transit Gateway vs cross-account IRSA (leaning
  IRSA).
- **Temporary staging bucket lifecycle:** expiry policy + explicit cleanup
  semantics on success and failure.
- **OpenSearch index/connector setup as a deployment prerequisite:** once chunk
  embedding moves to the connector (Planned Work item 7), the pipeline stops
  producing vectors and relies on the OpenSearch index having a configured
  ingest pipeline / Bedrock connector *before* any documents are indexed. Decide
  who owns and provisions that index setup (e.g. CP Terraform vs the ingestion
  deploy), and how index-mapping/connector changes are versioned and rolled out
  ahead of pipeline runs.
- **Textract local-dev vs Airflow parity:** how one code path serves both with
  the staging bucket in the mix.

## Corrections Applied From Review Feedback

- **Textract does not perform embedding.** The earlier component-table entry was
  an old error; embedding is done by Bedrock. Query embedding runs via the
  OpenSearch Bedrock connector on CP, and chunk embedding is planned to move to
  the same connector (see Planned Work item 7).
- **Cross-account Textract-on-CICA-S3 is not viable on AP.** Replaced by the
  download-to-temporary-AP-bucket staging pattern.
- **Static keys are local-dev only** and will be replaced by cross-account IRSA.
- **Ingestion is low-volume** and scheduled outside UI usage times, so the
  earlier concern about heavy ingestion degrading search does not apply. Cluster
  sizing for concurrent read/write contention is not a priority.

## Strengths Worth Calling Out

- **Platform split is well judged.** AP for AWS-service-rich batch compute, CP for
  the user-facing service, CICA AWS as system of record for source PDFs and page
  images — each platform used as intended.
- **Staging pattern neatly sidesteps the AP cross-account Textract limitation**
  while keeping source documents and derived page images in CICA's account.
- **Idempotency de-risks at-least-once delivery.** The deterministic UUID scheme
  means re-delivered SQS messages (SQS is at-least-once) overwrite rather than
  duplicate in OpenSearch — a genuine strength for a queue-driven ingestion layer.

## Data Residency and Classification (still worth tracking)

Documents are OFFICIAL / likely OFFICIAL-SENSITIVE case material. AP is designed
for OFFICIAL and OFFICIAL-SENSITIVE.

- Source PDFs and rendered page images reside in CICA AWS (confirmed).
- Case documents transit into the temporary AP staging bucket — confirm
  encryption at rest, access scoping, and prompt deletion.
- Extracted text + embeddings land in OpenSearch on CP — confirm CP OpenSearch
  encryption at rest and include this flow (with classification) on the data-flow
  diagram.
- Textract and Bedrock invoked in-region (`eu-west-2`, the code default) to keep
  data in the UK; confirm Titan Embed v2 availability in-region for both the
  current AP Bedrock and the CP connector's Bedrock instance.
- Once chunk embedding moves to the CP connector, chunk text reaches CP Bedrock
  at index time — include this flow on the data-flow diagram.

## What to Add to the Diagram Before Sign-Off

1. The CICA S3 -> temporary AP bucket -> Textract staging path, with account
   boundaries and the IRSA roles involved.
2. IRSA-based access arrows for both CICA S3 (read source / write page images)
   and OpenSearch (from AP).
3. The chosen OpenSearch connectivity path (Transit Gateway or IRSA) with the
   auth/TLS boundary marked.
4. The ingestion SQS queue labelled with its final placement (CP or CICA) and the
   CICA message producer.
5. Data classification on each flow carrying case text/images, including the temp
   staging bucket.

## References

- Analytical Platform user guidance:
  <https://user-guidance.analytical-platform.service.justice.gov.uk/index.html#overview>
- Cloud Platform user guide:
  <https://user-guide.cloud-platform.service.justice.gov.uk/documentation/concepts/what-is-the-cloud-platform.html>
