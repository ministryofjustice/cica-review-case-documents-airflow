# Data Science Scope — CICA Document Search

Status: Draft for resourcing discussion
Purpose: Inform Data Science resource scope mapping.
Related: `search-ranking-improvement-plan.md`

## Headline

The data-science need on this project is **narrow but foundational**. It is the
**search-quality measurement and optimisation layer**: building the evaluation harness
that makes every search improvement (score normalisation, reranking, weight tuning)
provable, and driving the metrics methodology behind it. Roughly one focused
workstream, front-loaded in effort.

## The core deliverable: an independent evaluation dataset + metrics

The project needs a **graded relevance dataset** — a neutral ground truth answering,
per (query, chunk) pair, "is this chunk relevant to this query?" graded 0/1/2 — plus
**rank-aware metrics** (NDCG@5/@10 primary, MRR secondary) computed against it.

Two properties make this a data-science problem rather than a data-entry one:

- **Retrieval-mechanism-agnostic.** The dataset measures *relevance*, not how a result
  was found. It must not be built around keyword-hit vs semantic-hit buckets, and it
  must not be graded using the production embeddings / search scoring — grading with
  the system under test rigs the evaluation in favour of the status quo. Knowing to
  require this independence is itself the DS expertise.
- **Fit for measuring ranking.** Order-blind metrics (e.g. F1) miss the point of the
  work; the dataset and metrics must be rank-aware, statistically sized for stable
  means, and deliberately include synonym cases and true negatives.

## The design vs verification split (the crux of the resourcing question)

**Data science owns the design and construction; domain experts own the final
relevance judgement.** These are different jobs and neither role can do the other's.

| Responsibility | Owner |
|----------------|-------|
| Define what a valid dataset requires (rank-aware, mechanism-agnostic, sizing, synonym/true-negative coverage) | Data Science |
| Design the schema, the 0/1/2 grading rubric, and the query mix | Data Science |
| Build the assisted pre-labelling pipeline (multi-retriever candidate pooling + LLM-as-judge) to turn a blank sheet into a graded draft | Data Science |
| Build the rank-aware metrics (NDCG/MRR) that consume the verified set | Data Science |
| Measure agreement between machine pre-labels and human corrections | Data Science |
| **Final relevance grade on each (query, chunk) pair** | **Domain expert** |
| Sanity-check that queries reflect real case-worker searches | Domain expert |

Why the final check must sit with the expert: the dataset's value as ground truth comes
*from* an independent domain sign-off. A data scientist can build the machine and
pre-fill every grade, but is not qualified to certify a chunk is clinically/legally
relevant to a CICA query. If DS both generated and approved the labels it would no
longer be an independent ground truth — the same coupling trap as grading with the
search system itself.

**Flow:** DS designs and drafts → domain expert verifies and owns the final grade →
DS consumes the verified set into metrics.

## Downstream Data Science work (gated on the harness existing)

- Own the metrics / SLO methodology argument (NDCG over F1, relative-to-baseline before
  absolute targets, defining "score calibration" properly). Needs a DS voice in the
  technical-architect discussion.
- Tune hybrid keyword/semantic weights against NDCG via Optuna.
- Evaluate candidate reranker models for a measurable NDCG lift.

These are blocked until the evaluation harness exists. Right now there is exactly one
actionable DS task: build the graded dataset (schema + rubric + assisted pre-labelling
+ seed examples) and the metric module. Effort is front-loaded, then intermittent.

## Scoping caveats to raise in the meeting

- **Domain expert is on the critical path, not an optional reviewer.** The pre-labelling
  pipeline reduces their effort (edit, don't author) but does not remove them. Confirm
  **who** the expert is and their time commitment (currently an open question), and agree
  a **grading rubric** between DS and the expert up front so grade-2 vs grade-1 means the
  same thing to both.
- **Skill profile:** applied ML / information-retrieval evaluation (retrieval metrics,
  offline experimentation, LLM-as-judge, model evaluation), not classical
  modelling/statistics. Needs enough engineering fluency to work inside the eval suite.
- **Data governance:** an LLM-as-judge pre-labeller sends case medical text to a model —
  same data-handling consideration as the reranker; keep it within the approved AWS
  account/VPC boundary if compliance requires.
- **DS is a shared dependency:** other search changes are only *provable* through the DS
  harness, so DS validates others' work as well as delivering its own.

## One-line for the resourcing decision

> One applied-ML / IR data scientist, front-loaded on building the search-evaluation
> harness (independent graded dataset + rank-aware metrics), then part-time for weight
> tuning and reranker model evaluation. Data Science designs and drafts the dataset; a
> domain expert owns the final relevance grading and is a hard dependency on the path.
