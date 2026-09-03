# Search Ranking Improvement Plan

Status: Draft / design
Owner: TBD
Scope: Evaluation harness, hybrid score normalization, and reranking for the CICA
document search system.

## 1. Background

The CICA review-case-documents system lets case workers search the OCR'd text of a
case's medical reports (e.g. a TC-19 bundle). Search returns **chunks** of text drawn
from pages; the case worker can click a chunk to view it highlighted both on the page
image (via bounding boxes) and in the page's text view. It is a **hybrid search that
returns passages**, not a question-answering system.

The query DSL is built by the frontend application (`cica-review-case-documents`) and
is **mirrored** in this repo's evaluation suite (`evaluation_suite/search_evaluation`)
for offline evaluation. The ingestion pipeline in this repo (`src/ingestion_pipeline`)
only ingests, embeds, and indexes; it does not build search queries.

### UI contract shown to users

The tool's own guidance promises three query shapes and semantic matching:

- a word, e.g. `jaw`
- a phrase, e.g. `knee injuries`
- a whole question, e.g. `What injuries did the applicant have?`
- "If you search for 'jaw' it will find similar words like 'mandible'."
- "The tool might not find all the information you need, so you might have to check
  the document manually."

These statements are treated as **requirements** in this plan (see Section 3).

## 1a. Items to raise with architect / deck owner

Consolidated decisions/clarifications needed from others. Details in the referenced
sections; this list exists so they can be resolved in a single conversation.

| # | Item | Ask | Reference |
|---|------|-----|-----------|
| 1 | Primary quality metric | Proposed SLO uses **F1**, which is order-blind and conflicts with the ranking work. Adopt **NDCG@10 primary**, F1/recall as guardrail? | §5.2, §5.3 |
| 2 | "Relevance-score calibration" metric | Does not parse as written (threshold, not a quantity; target repeats F1). Is it **score calibration** (→ precision-at-threshold, depends on Step 2) or a **precision ≥ 0.95** target? | §5.2, §5.3 |
| 3 | Absolute SLO targets (0.90 / 0.95) | Defer fixed numbers until a **baseline** exists on the approved set; keep the relative "X% below baseline" alert now? | §5.2, §5.3 |
| 4 | Observability "search-quality spike > 2× baseline in 24h" | Which **quantity** does it count? Keep as a relabelled **zero/near-zero-result rate** alert; drop "low score" as a signal (uncalibrated). Premature until go-live. | §5.5 |
| 5 | Frontend repo scope | Is `cica-review-case-documents` in scope for the production query/`min_score` change, or is this eval-suite prototyping only for now? | §6 |
| 6 | Reranker query volume | Expected **query volume / concurrency** at go-live — the input that decides real-time endpoint vs serverless vs Bedrock. | §3.1, §7 |
| 7 | Relevance labelling ownership | Who owns domain labelling, and is there a rubric for direct-answer vs supporting-context grading? | §7 |

Underlying root cause for items 1-4: the current `_score` is **uncalibrated and
keyword-dominated** (§2.2), so score-based metrics/alerts are unreliable until score
normalization (Step 2) lands.

## 2. Current state (verified)

### 2.1 Actual production query DSL (reference)

```json
{
  "query": {
    "bool": {
      "filter": [{ "term": { "case_ref": "26-700001" } }],
      "should": [
        { "match":  { "chunk_text": { "query": "What injuries did the applicant have?", "_name": "keyword", "boost": 20 } } },
        { "neural": { "embedding":  { "query_text": "What injuries did the applicant have?", "k": 250,
                                      "filter": { "term": { "case_ref": "26-700001" } }, "boost": 4, "_name": "semantic" } } }
      ],
      "minimum_should_match": 1
    }
  },
  "min_score": 2.25,
  "from": 0,
  "size": 10
}
```

### 2.2 Scoring behaviour

Final score is a raw additive combination inside `bool.should`:

```
final_score = 20 * bm25(chunk_text) + 4 * cosine_similarity(embedding)
```

- BM25 is unbounded (commonly 5-30+); cosine similarity is bounded in ~[0,1].
- After boosts, the keyword term dominates by roughly an order of magnitude; the
  semantic clause behaves as a tie-breaker, not a ranking force.
- `min_score: 2.25` is tuned to the raw keyword scale. It is **scale-coupled**: any
  normalization change will move scores into a ~0-1 range and this threshold would
  then reject everything. Must be revisited alongside any normalization work.
- The ANN clause retrieves `k: 250` candidates but only `size: 10` are returned — a
  wide candidate pool is discarded, which is exactly what a reranker would consume.
- Two `case_ref` filters (outer `bool.filter` and inner `neural.filter`) are both
  correct and required: the inner one scopes ANN candidate selection to the case
  before scoring. Preserve both.

### 2.3 No normalization, no reranking, no rank-aware metrics

Confirmed by repo-wide search: there is no score normalization (min-max, z-score,
softmax, RRF), no reranking / cross-encoder stage, no OpenSearch hybrid search
pipeline / normalization-processor, and no MRR/NDCG metrics anywhere.

### 2.4 What is indexed (relevant to reranking)

Chunk index (`page_chunks*`) per-chunk fields include: `chunk_id`, `chunk_text`
(analyzer `stop`, with an unused `chunk_text.english` stemmed sub-field), `embedding`
(`knn_vector`, dim **1024**, faiss/hnsw/cosinesimil), `page_number`, `case_ref`,
`correspondence_type`, `received_date`, bounding-box geometry. Page-level full text
lives in a separate `page_metadata*` index. Embeddings use Amazon Titan Text
Embeddings V2 (`amazon.titan-embed-text-v2:0`), generated at ingestion and,
server-side via a Bedrock connector, at query time (the `neural` clause).

> Field-name mismatches flagged during investigation, to verify against a live index
> before relying on them for reranking features:
> - Bounding box: Pydantic model serializes top-level `bounding_box`, but the index
>   mapping declares `geometry.bounding_box`.
> - Eval `_SOURCE_FIELDS` requests `document_id`, but the stored field is
>   `source_doc_id`.

### 2.5 Current evaluation suite

- `search_terms.csv` is keyword/phrase oriented; no natural-language questions.
- Metrics are **set-based** precision/recall/F1 plus an `optimization_score`
  = `(total_chunks_returned / total_queries) * (avg_acceptable_term_precision)^2`,
  which Optuna maximizes. All metrics ignore result **order**.
- The looper collapses hits into a set, discarding rank order.

## 3. Requirements

- **R1 — One query path for all three shapes.** A single ranking configuration must
  handle word, phrase, and question queries well. No per-query-type routing. (UI
  promises all three equally.)
- **R2 — Semantic/synonym retrieval must actually surface.** "jaw" must be able to
  retrieve "mandible". The evaluation set must include synonym cases where the
  answer chunk uses different words than the query, and the metric must detect them.
- **R3 — Optimize for whole-window relevance, not first-hit.** The UI tells users to
  scan results and fall back to manual review, so recall into the visible window
  matters. NDCG@k is the primary metric; MRR is a secondary diagnostic only.
- **R4 — Do not regress single-keyword lookups.** "jaw" as a lone keyword is likely
  the most common real usage. Tuning that favours questions must not degrade it; the
  unified evaluation set and a mixed optimization objective guard against this.

## 4. Approach and sequencing

Rationale: you cannot tell whether normalization or reranking helped without
rank-aware metrics on realistic queries; and normalization is a small change that may
capture much of the benefit before taking on the operational cost of a reranker.

### Step 1 — Evaluation harness (this repo, self-contained)

1a. **Unified graded relevance dataset** (long format), spanning all three query
shapes and deliberately including synonym cases (R2).

Proposed schema (`query, query_type, chunk_id, relevance_grade`):

| Column | Meaning |
|--------|---------|
| `query` | The search string (word / phrase / question) |
| `query_type` | `word` \| `phrase` \| `question` (for per-shape breakdowns) |
| `chunk_id` | An expected chunk UUID |
| `relevance_grade` | `2` = directly answers/matches, `1` = related/supporting, `0` = not relevant |

Grade tiers map onto the existing CSV's implicit structure (primary
`expected_chunk_id` -> grade 2; "acceptable associated terms" chunks -> grade 1).

**Dataset sizing.** Evaluation reliability is driven by the number of **labelled
queries**, not corpus size. The corpus (currently ~200 chunks from one case) is the
haystack; each query is one independent NDCG/recall measurement, and the headline
metric is the mean across queries — its stability depends on query count.

- **< ~20 queries:** smoke-testing / gross-regression only; too noisy for small deltas.
- **~30-50 queries:** practical sweet spot for the current single-case dev phase.
- **~50-100+ queries:** needed before hardening *absolute* SLO targets (ties to §5).

**Product boundary: search is always within a single case (1:1 with its document).**
Search is *always* scoped to one case, and each case has exactly one document, so
`case_ref` scoping is equivalent to scoping to that one document. This is intended
product behaviour, and the evaluation mirrors it. Consequences:
- No within-case document disambiguation or multi-document ranking to evaluate
  (removes a class of Phase B complexity).
- **Cross-case retrieval is out of scope by design, not a gap.** Every query is
  single-case-scoped in production, so the evaluation is too. Having many cases buys
  **query/vocabulary diversity** and confidence a config generalizes across documents;
  it does not (and should not) introduce cross-case ranking.
- Cross-case **leakage** (a case-A query returning a case-B chunk) would be a filter
  bug. It is cheap to guard with a **functional assertion** in the harness (every
  returned chunk shares the queried `case_ref`) — a correctness check, not a relevance
  metric.

Two-phase plan matched to the ingestion timeline:

- **Phase A (now, 1 case ~200 chunks): 30-50 graded queries.** Spread across
  word/phrase/question, include synonym cases (jaw→mandible, R2) and a few true
  negatives (should return little/nothing, §5.4). Purpose: build/validate the harness,
  get a **provisional** baseline, prototype normalization. Numbers are directional,
  not SLO-grade.
- **Phase B (after ~30 partial cases land, 1 doc each): ~3-5 queries per case ≈
  100-150 total.** The 1:1 mapping makes the budget map cleanly onto cases: per case,
  write a couple of keyword lookups, a phrase, a question, and one true negative. This
  spreads coverage across documents/shapes, gives per-case breakdowns for free, and is
  small and parallelizable per case. This is the set for hardening absolute SLO targets.

**Caveats specific to being in development:**
- With **one case**, metrics are likely **optimistic** (small homogeneous corpus) and
  cannot detect case-filter/leakage bugs. Reinforces §5's "relative-to-baseline until
  measured" stance; the leakage check above is a functional test, not a metric.
- **Chunk IDs are not stable across re-chunking**, and the chunking strategy is still
  evolving. Do not over-invest in Phase A labelling. **Mitigation:** anchor ground
  truth at the **page level** (`expected_page_number`, stable across re-chunks) in
  addition to `chunk_id` (precise but volatile). A re-chunk then only requires
  re-deriving chunk IDs from stable page anchors, not re-judging relevance.

Revised schema carrying both anchors:

| Column | Meaning |
|--------|---------|
| `query` | The search string (word / phrase / question) |
| `query_type` | `word` \| `phrase` \| `question` |
| `expected_page_number` | Durable page-level anchor (survives re-chunking) |
| `chunk_id` | Precise chunk anchor (re-derivable from page + text) |
| `relevance_grade` | `2` = directly answers/matches, `1` = related/supporting, `0` = not relevant |

1b. **Rank-aware metrics module** (`rank_metrics.py`): NDCG@5 and NDCG@10 (primary),
MRR (secondary). Requires threading **ordered** hit lists through
`run_search_loop` / `_process_hits` (currently collapsed into a set).

Labelling is owned by a domain expert; engineering provides the schema, the metric
code, and a seed of ~10-15 labelled queries to bootstrap.

### Step 2 — Score normalization (measurable once Step 1 exists)

Reframed as **correctness**, not just optimization: the UI promises semantic matching
(R2) that the current 20:4 raw-additive scoring suppresses.

- **Preferred:** OpenSearch **normalization-processor** (hybrid search pipeline). It
  min-max normalizes each sub-query's scores independently, then combines with
  configurable weights — a natural fit since the query already uses a `neural` clause.
  Requires restructuring the `bool.should` into the pipeline's `hybrid` query form.
- **Baseline to compare:** Reciprocal Rank Fusion (RRF), scale-free, no infra change.
- **Must also:** re-derive `min_score` for the normalized score range (Section 2.2).
- **Weights are tuned, not guessed:** once NDCG over the mixed dataset is the Optuna
  objective, "should semantic outweigh keyword?" becomes a measured result (R1, R4).

> **Normalization is a prerequisite for score-based observability, not only a relevance
> improvement.** Today's `_score` (`20 × BM25 + 4 × cosine`) is uncalibrated,
> keyword-dominated, and not comparable across queries, so *any* score-based signal
> built on it is unreliable — this is the common root cause behind several observability
> issues in §5: the ambiguous "calibration" metric (§5.2), why "low score" is rejected
> as an alert signal (§5.5), and why absolute score thresholds (incl. `min_score: 2.25`)
> must be re-derived. Until Step 2 lands, observability must lean on **score-independent**
> signals (zero / near-zero results, NDCG on the labelled set). After Step 2, scores
> become 0-1-ish and query-comparable, unlocking **precision-at-threshold** (§5.3) as a
> trustworthy production quality signal.

### Step 3 — Reranking (evidence-based, after normalization is measured)

- **Preferred model type:** a **cross-encoder** reranking the top-N of the existing
  `k=250` pool. No retrieval changes needed; directly addresses the UI's
  manual-fallback caveat (R3) by recovering relevant chunks into the visible window.
- **Considered and deprioritized:** late-interaction (ColBERT-style) retrieval would
  require storing per-token vectors — an ingestion/index overhaul — and is unnecessary
  given the healthy candidate pool already retrieved.

#### 3.1 Hosting: SageMaker (self-hosted) vs Bedrock (managed)

Available: **Bedrock** and **SageMaker**. Preference stated is **self-hosted on
SageMaker to reduce cost** — but the cost tradeoff depends on traffic pattern and is
not clear-cut for a business-hours, bursty case-worker tool:

| Option | Billing | Best when | Watch out for |
|--------|---------|-----------|---------------|
| SageMaker real-time endpoint | Per instance-hour, always on | Sustained/high volume | Pays for idle time; a mostly-idle GPU endpoint can cost **more** than per-request managed at low volume |
| SageMaker Serverless Inference | Per request, scales to zero | Low/bursty volume | Cold-start latency (seconds) hurts an interactive search box; limited GPU support |
| Bedrock Rerank (managed) | Per request, no idle cost | Low volume, minimal ops | Ongoing per-request price at scale; data leaves your account boundary |

Implications:
- **Decision deferred, deliberately.** Build the rerank stage behind a small
  `Reranker` interface (`rerank(query, chunks) -> scored_chunks`) with a local /
  self-hosted cross-encoder implementation and a managed (Bedrock) implementation.
  The evaluation suite measures **ranking quality independent of hosting** — the
  decision that matters first.
- **Choose hosting after** (a) confirming a model that yields a real NDCG lift and
  (b) estimating query volume. Self-hosted wins on cost at sustained volume; at
  low/bursty volume, Bedrock or SageMaker Serverless may be cheaper and simpler.
- **Prototype needs no AWS infra:** the cross-encoder runs locally (model download)
  during evaluation, keeping the harness self-contained in this repo.
- **Candidate self-hosted models:** BGE reranker family (e.g. `bge-reranker-v2-m3`)
  or Jina rerankers — deploy cleanly to a SageMaker endpoint and run locally for eval.
  Treat model choice as something the evaluation harness selects, not a decision now.
- **Data-governance angle (may outweigh cost):** self-hosting on SageMaker keeps
  medical-report text inside your own AWS account/VPC, which can be a compliance
  advantage over a managed API under MoJ AP data-handling terms. A governance call,
  flagged here as a consideration, not a conclusion.

## 5. Metrics and SLOs

This section responds to a proposed set of SLOs from the technical architect. The
proposal's **intent is right** and its **relative-regression alerting is the strongest
part**, but the specific metric choices work against the goals of this plan and one is
ambiguous as written. This is a counter-proposal for discussion, not a final decision.

### 5.1 Architect's proposal (as received)

| # | Service area | What we measure | Target | Alerted when |
|---|--------------|-----------------|--------|--------------|
| 1 | Search quality | Retrieval relevance on approved test queries | F1 ≥ 0.90 | Below 0.90, or 5% below baseline |
| 2 | Relevance-score calibration | (stated) "at or above 0.95" | F1 ≥ 0.90 | Below 0.95 |

### 5.2 Concerns

**Metric 1 — F1 is order-blind, which conflicts with the whole plan.**
F1 measures set membership, not ranking. The UI's value is that a case worker scans a
**ranked** list, so the improvement work (normalization, reranking) is precisely about
*order*. A reranker could move the answer from position 9 to position 1 — a large UX
win — and F1 would not move at all. Worse, F1 can be inflated by returning more results
(higher recall), flooding the case worker with noise, the opposite of the goal. An
F1-only gate would be blind to, and could even penalize, the work it is meant to govern.

**The 0.90 absolute target predates any baseline.**
There is currently no rank-aware measurement and the scorer is keyword-dominated. 0.90
F1 may be trivial or unreachable depending on labelling — nobody has measured it. Fixing
an absolute target before a baseline exists is premature. The **"5% below baseline"
relative alert is the sound half** and should be kept.

**Metric 2 does not parse as written.**
"What we measure: at or above 0.95" states a threshold, not a quantity (0.95 *of what?*),
and the target row repeats F1. It appears to conflate two different things:
- *Score calibration proper* — whether relevance **scores** are consistent/meaningful
  across queries. This is a real and relevant gap: today's `20 × BM25 + 4 × cosine`
  mixes unbounded and bounded scales and `min_score: 2.25` is coupled to that raw scale
  (Section 2.2). But **F1 does not measure calibration.**
- *A precision target of 0.95* — "95% of what we return above the cutoff is relevant."
  Legitimate, but that is **precision-at-threshold**, and should be named as such, not F1.

### 5.3 Counter-proposal

| Service area | Primary metric | Guardrail metric | Target | Alerting |
|--------------|----------------|------------------|--------|----------|
| Search quality (ranking) | **NDCG@10** | Recall@10 / F1 | Relative to baseline until measured, then hardened | X% below baseline **and** absolute floor once set |
| Relevance-score calibration | **Precision-at-threshold** (fraction of results above `min_score` that are relevant, and its stability across queries) | — | Set after normalization lands (Step 2) | Below agreed precision floor, or drift across queries |

Rationale:
- **NDCG@10 primary** — captures "are the right chunks ranked high," the thing the UI
  depends on and the thing the work improves. (See R3.)
- **Recall@10 / F1 as guardrail** — catches the different failure of *missing* relevant
  chunks entirely. Keep both; they measure different failures.
- **Calibration as precision-at-threshold** — measures what "metric 2" seems to intend,
  using the right tool. It **depends on the normalization work (Step 2)** landing first:
  you cannot calibrate a threshold on an uncalibrated score.
- **Targets relative-to-baseline first, absolutes later** — keep the architect's
  regression alerting; defer fixed numbers until the approved set yields a baseline.

### 5.4 Dependencies and caveats

- Both metrics depend on the **approved, labelled test set that does not yet exist**
  (Step 1). Targets are only as trustworthy as that dataset.
- The set must include **true negatives** (queries that should return little/nothing),
  or precision targets are trivially inflated. The current `search_terms.csv` already
  has some zero-expected rows; the graded set must preserve this deliberately.
- **Action:** clarify metric 2's intent with the architect (calibration vs precision)
  before implementation.

### 5.5 Observability deck: "Search-quality report spike > 2× baseline in 24h"

Flagged from a work-in-progress observability deck. **Ambiguous as written**; whether
it is sensible depends entirely on *what is counted*, which the phrase does not state.

- **If it counts an event rate** (e.g. number of **zero / near-zero-result** searches,
  or user "unhelpful result" reports): a "> 2× baseline in 24h" spike alert is
  **reasonable and useful** — it catches ingestion/index/embedding-endpoint breakage or
  a bad config ship. Keep it, but **relabel** it to name the exact count.
  - **Avoid "low score" as the signal.** The only score line today is the raw
    `min_score: 2.25`, which is an **uncalibrated, keyword-dominated, per-query-varying**
    artefact (see §2.2), not a relevance measure — a genuinely good semantic match with
    little lexical overlap (jaw→mandible) can score low, and a keyword-heavy but
    irrelevant match can score high. Prefer **zero / near-zero result count**, which is
    score-independent and stable across the normalization work. A score-based quality
    signal only becomes trustworthy *after* normalization, re-expressed as
    **precision-at-threshold** (§5.3), never the raw 2.25 cutoff.
- **If it means a quality *metric* (NDCG/F1) spiking:** **incoherent.** (1) Quality
  metrics degrade *downward*, so alerting on an *upward* spike is meaningless — and
  NDCG/F1 are bounded at 1.0, so "2×" is often mathematically impossible. (2) NDCG/F1
  are **offline** metrics computed by re-running the harness on the labelled set; they
  do not move on a 24h production clock. A 24h spike window is a category error here.

**Recommendation:** keep the two concerns separate.
- *Operational rate alert* (live, directional-up on a bad-event count): "rate of
  **zero / near-zero-result** searches > 2× trailing baseline over 24h." Score-
  independent; valuable and distinct from the offline SLOs. (Not "low score" — see
  above.)
- *Offline quality SLOs* (§5.3): NDCG/recall/precision-at-threshold on the labelled
  set, alerting when they drop *below* baseline. Directional-down, not spike-based.

**Dev-phase caveat:** any "2× baseline" alert needs a **stable production baseline**,
which does not exist yet (no live traffic). Premature until go-live — same rationale as
deferring absolute SLO targets. **Action:** confirm with the deck owner which quantity
this alert watches before implementing.

## 6. Cross-repo and deployment notes

- Query construction and `min_score` live in the **frontend** repo
  (`cica-review-case-documents`). This eval suite is the right place to prototype and
  prove ranking changes, but production changes land in the frontend. Ownership TBD.
- Reranking is a **query-time serving** concern, not ingestion — it does not belong in
  this Airflow pipeline. Production hosting under the MoJ Analytical Platform (SageMaker
  self-hosted preferred, Bedrock as fallback) is covered in Section 3.1; final choice
  pending a query-volume estimate.

## 7. Open questions

1. Is the frontend repo (`cica-review-case-documents`) in scope for the eventual
   production change, or should work stay confined to this eval suite for now?
2. ~~Managed vs self-hosted reranking~~ — **Resolved (with caveat):** Bedrock and
   SageMaker both available; preference is self-hosted on SageMaker for cost. Final
   hosting choice deferred until a model shows an NDCG lift and query volume is
   estimated, since idle cost can invert the economics at low/bursty volume
   (Section 3.1). Prototype stays hosting-agnostic behind a `Reranker` interface.
   - Sub-question: **expected query volume / concurrency** at go-live? This is the
     key input that decides real-time endpoint vs serverless vs Bedrock.
3. Who owns relevance labelling, and is there an existing rubric for
   direct-answer vs supporting-context grading in a CICA context?

## 8. Immediate next step

Build Step 1: the unified graded dataset schema + a seed of labelled queries, and the
NDCG/MRR metric module fed by ordered hits. This creates the measurement harness that
makes Steps 2 and 3 evidence-based.
