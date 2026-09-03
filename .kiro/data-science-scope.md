# Data Science Scope — CICA Document Search

Status: Draft for resourcing discussion
Purpose: Inform Data Science resource scope mapping.
Related: `search-ranking-improvement-plan.md`

## Glossary

| Term | Meaning in this document |
|------|--------------------------|
| **Domain expert** | A CICA case worker (or equivalent subject-matter authority) who can authoritatively judge whether a document chunk is clinically/legally relevant to a query. Owns the final relevance grade. |
| **Case worker** | The end user of the search tool; reviews case documents. Synonymous with domain expert in the relevance-grading context. |
| **DS** | Data Science / data scientist. |
| **UR** | User Research / user researcher (and service design), a distinct role that often owns pilot workflow evaluation in government services. |
| **Chunk** | A passage of text extracted from a document page; the unit that search returns and that relevance is graded against. |
| **Graded relevance dataset** | The ground-truth set of (query, chunk) pairs each labelled 0/1/2 for relevance, used to measure search quality. |
| **Relevance grade** | `2` = directly answers/matches, `1` = related/supporting, `0` = not relevant. |
| **Offline harness** | The evaluation suite that runs queries against the graded dataset and computes metrics — measured "offline," not on live traffic. |
| **Rank-aware metric** | A metric that accounts for result *order* (NDCG, MRR), as opposed to order-blind set metrics (precision/recall/F1). |
| **NDCG** | Normalised Discounted Cumulative Gain — rank-aware quality metric; primary measure of "are the right chunks ranked high." |
| **MRR** | Mean Reciprocal Rank — rank-aware metric focused on the position of the first relevant result; secondary diagnostic. |
| **Hybrid search** | Retrieval combining keyword (BM25) and semantic (embedding) matching. |
| **Semantic / embedding search** | Retrieval by meaning via vector similarity, so "jaw" can match "mandible." |
| **Reranker** | A second-stage model that reorders an initial candidate set to improve ranking quality. |
| **LLM-as-judge** | Using a large language model to propose draft relevance grades for human verification. |
| **True negative** | A query that *should* return little or nothing; included so precision targets are not trivially inflated. |
| **Miss rate** | Under manual review, the fraction of relevant information present in the documents that a case worker fails to find. See the dedicated subsection. |
| **Baseline** | A measurement of the current (manual) process against which the tool's benefit is compared. |

## Headline

The data-science need on this project splits into **two distinct roles**:

1. **Search-quality measurement & optimisation (applied ML / IR).** Build the evaluation
   harness that makes every search improvement (score normalisation, reranking, weight
   tuning) provable, and drive the metrics methodology behind it. Front-loaded in effort.
2. **Pilot / private-beta value evaluation (product / experimental DS).** Design the lean
   pilot as a measurable comparison of the tool against the current fully-manual review,
   to answer "is this actually valuable to case workers?"

Both are data science but different skill emphases; one person may cover both if they
have the range. Role 2 overlaps with user research — see that section.

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

## Pilot / private-beta value evaluation (second DS role)

The pilot's purpose is not "is the search technically good?" (the offline harness answers
that) but **"is the system valuable to case workers, and better than the current fully
manual review of scanned PDFs?"** Offline metrics like NDCG cannot answer this — a system
can rank well and still fail to help, or help in ways NDCG never captures. The DS
contribution here is **designing the pilot as an evaluation**, not running search metrics.

What that involves:

- **Define "valuable" as measurable outcomes up front** — e.g. time-to-find relevant
  information per case, number of pages/documents opened manually, task completion,
  user trust, and how often workers still fall back to manual review.
- **Establish a baseline for the manual process.** No benefit claim over manual review is
  possible without measuring manual review first. Easy-to-measure baselines: time per
  bundle, pages/documents opened. High-value but harder: **current miss rate** (see
  below). Without a baseline, "faster/better" is unfalsifiable.
- **Choose a study design that survives a tiny pilot.** Small n means no statistical
  significance; be honest about that. Prefer within-subject / paired design (same worker,
  same case, with vs without the tool) and lean on directional + qualitative evidence.
- **Instrument for measurement.** Specify what usage signals to log (queries, result
  clicks, manual fallbacks, session times). The repo already has structured logging
  (`docs/logging-breakdown.md`); DS should state what the pilot needs captured.
- **Guard against pilot biases** — novelty effect, volunteer selection bias, Hawthorne
  effect. Naming and mitigating these is a core DS/research contribution.
- **Combine quantitative and qualitative.** At pilot scale, structured interviews and
  observed sessions ("did it find something you'd have missed?") often carry more weight
  than the numbers; DS designs how that evidence is gathered and synthesised.

### On "current miss rate"

**Definition:** how often, under the existing fully-manual process, a case worker fails
to surface information that was present in the documents and relevant — because a long
bundle was skimmed, a detail was buried deep in a report, handwriting was hard to read,
or there wasn't time to read every page. The miss rate is the fraction of relevant items
that slip through.

**Why it matters:** the strongest potential benefit of this tool may not be "faster" but
"catches what a human scanning under time pressure would miss." The UI even primes users
toward this (it warns them to still check manually). But "the tool reduces misses" is
only a claim you can make if you know roughly how often misses happen *today*.

**Why it's hard:** a miss is by definition something that *wasn't* found — you can't just
ask a worker what they missed. It has to be approximated:

- **Expert ground truth (most rigorous):** an expert exhaustively reads a set of cases and
  catalogues every relevant fact; measure how many a worker finds under normal, time-boxed
  manual review. The gap is the miss rate. Accurate but effort-heavy.
- **Paired comparison (pragmatic):** same worker + case, with and without the tool; count
  relevant items the tool surfaced that the manual pass didn't — and vice versa, since the
  tool can also miss things. Cheaper, gives a directional signal at pilot scale.
- **Downstream proxy (weak):** rework, appeals, or complaints traceable to missed
  information. Noisy and lagging; treat as supporting evidence only.

**Recommendation for a lean pilot:** don't over-invest. Lead with the cheap baselines
(time-to-find, pages opened) and treat miss rate via the paired-comparison approach as a
directional signal. Reserve expert-ground-truth miss-rate measurement for a later,
harder-evidence phase — the same "relative signal now, hardened numbers later" stance the
offline harness takes. **Action:** decide in the meeting whether miss rate is in scope for
this pilot and, if so, which approximation is affordable.

**Relationship to the offline harness:** complementary. The pilot study tells you
*whether* the tool helped; the offline harness tells you *why* (was retrieval the
bottleneck?). You want both to interpret a pilot correctly.

**DS vs User Research boundary (settle in the meeting).** In a MoJ / government-service
context, a user researcher / service designer often owns exactly this kind of pilot
evaluation. So the question is not only "does DS do this" but "is this DS, UR, or a
collaboration?" Flag the boundary explicitly to avoid either double-staffing it or
leaving a gap. A likely split: UR owns qualitative workflow research and participant
engagement; DS owns metric definition, baseline measurement, study design, and bias
control — working together.

## Scoping caveats of note

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

> Data Science plays two roles: (1) applied-ML/IR — front-loaded on building the
> search-evaluation harness (independent graded dataset + rank-aware metrics), then
> part-time for weight tuning and reranker evaluation; (2) product/experimental DS —
> designing the private-beta pilot as a measurable comparison against manual review.
> A domain expert owns final relevance grading (hard dependency); the pilot-value role
> overlaps with user research and that boundary needs settling.
