# Search Relevance Testing Framework

A framework for evaluating and optimizing OpenSearch configurations for the CICA document review system. It measures how well different search strategies (keyword, semantic, fuzzy, etc.) return relevant document chunks for predefined search terms.

## Quick Start

```bash
# Run a single evaluation (single case, requires LocalStack + OpenSearch)
python -m evaluation_suite.search_evaluation.run_evaluation

# Compare all three chunking strategies on a single case
python -m evaluation_suite.search_evaluation.run_chunking_comparison

# Run multi-case evaluation across all 30 UAT cases (uses real AWS — no LocalStack needed)
./run_multi_case_evaluation.sh

# Run parameter optimization (100 trials)
python -m evaluation_suite.search_evaluation.optimization.optimize_search
```

**Prerequisites:**
- Docker Desktop running (OpenSearch + LocalStack started automatically by `run_multi_case_evaluation.sh`)
- Valid AWS credentials in `.env` (rotated daily — see main project README)

---

## Contents

1. [Evaluation Workflow](#1-evaluation-workflow)
2. [Multi-Case Evaluation](#2-multi-case-evaluation)
3. [Chunking Strategy Comparison](#3-chunking-strategy-comparison)
4. [Configuration](#4-configuration)
5. [Search Client](#5-search-client)
6. [Expected Chunks Generator](#6-expected-chunks-generator)
7. [Parameter Optimization](#7-parameter-optimization)
8. [Module Reference](#8-module-reference)

---

## 1. Evaluation Workflow

Measures how well search configurations return expected chunks for predefined search terms. Calculates ranked precision/recall at fixed cutoffs (@10 and @20) to compare configurations.

### Pipeline

```
search_terms.csv → search_looper → OpenSearch → term_matching → chunk_metrics → relevance_scoring → output
```

1. **Load terms** — `search_looper.py` reads from `testing_docs/search_terms.csv`
2. **Execute searches** — Each term queries OpenSearch via `search_client.py`
3. **Load chunks** — `chunks_loader.py` fetches all indexed chunks for term matching
4. **Generate ground truth** — `ground_truth.py` derives the relevant chunk IDs per query from the indexed corpus, and `synonym_generator.py` generates acceptable (similar) terms via scispaCy word vectors
5. **Match terms** — `term_matching.py` verifies returned chunks contain expected terms
6. **Calculate metrics** — `chunk_metrics.py` computes ranked precision@10/@20 and recall@10/@20
7. **Aggregate results** — `relevance_scoring.py` generates summary statistics
8. **Output** — Results written to timestamped CSVs and cumulative log

### Metrics

All precision/recall metrics are reported at two rank cutoffs, **@10** and **@20** (the top-k returned chunks):

| Metric | Meaning |
|--------|---------|
| `precision_at_{k}` / `recall_at_{k}` | Chunk-level precision/recall against the auto-generated expected chunk IDs, over the top-k results |
| `term_based_precision_at_{k}` | Fraction of the top-k chunks that contain the **search term** |
| `acceptable_term_based_precision_at_{k}` | Fraction of the top-k chunks that contain the search term **or** an acceptable (similar) term |
| `missing_chunk_ids` | Expected chunks never retrieved anywhere in the result set |

**Ground truth and acceptable terms are auto-generated each run** from whatever chunks are currently indexed, so both stay valid across chunking strategies. Hand-curated `expected_chunk_id` / `acceptable_terms` values in the CSV, if present, are preserved as overrides.

### Usage

```bash
python -m evaluation_suite.search_evaluation.run_evaluation
```

### Output

| Location | Description |
|----------|-------------|
| `output/evaluation/<date>/<search_type>/<timestamp>_relevance_results.csv` | Detailed per-term results |
| `output/evaluation/evaluation_log.csv` | Cumulative summary across all runs |

---

## 2. Multi-Case Evaluation

Evaluates search relevance across all 30 UAT cases in a single pipeline run. All cases are indexed into a shared OpenSearch index; source documents are fetched directly from `mod-platform-sandbox-kta-documents-bucket` (real AWS S3) — **LocalStack is not required for multi-case evaluation**.

### Usage

```bash
# Run all cases (discovers all 26-700xxx cases in S3)
./run_multi_case_evaluation.sh

# Run a subset of cases
./run_multi_case_evaluation.sh --cases 26-700001,26-700002,26-700003

# Skip .docx → CSV extraction step (search terms already generated)
./run_multi_case_evaluation.sh --skip-extract

# Skip ingestion (all cases already indexed in OpenSearch)
./run_multi_case_evaluation.sh --skip-ingest
```

### Prerequisites

1. **Docker Desktop** running — the script starts OpenSearch and LocalStack automatically via docker-compose and waits for them to be healthy before proceeding
2. **AWS credentials** in `.env`: `AWS_MOD_PLATFORM_ACCESS_KEY_ID`, `AWS_MOD_PLATFORM_SECRET_ACCESS_KEY`, `AWS_MOD_PLATFORM_SESSION_TOKEN` (rotated daily — check they are current before running)
3. `USE_MOD_PLATFORM_MODE=true` in `.env` (default)

### Pipeline Phases

| Phase | Step | Description |
|-------|------|-------------|
| 1 | Extract | Parse `.docx` case files into per-case `search_terms.csv` |
| 2 | Ingest | Index all cases into OpenSearch (idempotent — skips already-indexed cases) |
| 3 | Expected chunks | Auto-generate ground-truth expected chunk IDs per case |
| 4 | Evaluate | Run search evaluation for each case |
| 5 | Aggregate | Combine per-case results into a single summary report |

### Output

| Location | Description |
|----------|-------------|
| `evaluation_suite/output/evaluation/<date>/multi_case_<timestamp>.csv` | Aggregated multi-case results |
| `evaluation_suite/output/evaluation/evaluation_log.csv` | Cumulative run log (all strategies and cases) |

---

## 3. Chunking Strategy Comparison

Sweeps all three supported chunking strategies and runs a full single-case evaluation for each. Each run resets and re-ingests the chunk index with that strategy, then appends a row (stamped with `chunking_strategy` and `num_chunks_indexed`) to the cumulative `evaluation_log.csv` for direct comparison.

### Usage

```bash
python -m evaluation_suite.search_evaluation.run_chunking_comparison
```

> ⚠️ **This resets the OpenSearch chunk index once per strategy.** The final index state will reflect the last strategy in the sweep (`layout`).

### Prerequisites

Same as single-case evaluation (see [Section 1](#1-evaluation-workflow)): OpenSearch running, LocalStack running with `local-kta-documents-bucket` populated, and valid AWS credentials in `.env`.

> **After a Docker restart LocalStack loses all state.** If ingestion fails with a `NoSuchBucket` error, re-create the buckets and re-upload the source PDF (see `local-dev-environment/init-scripts/01-create-aws-resources.sh`).

### Changing the Chunking Strategy for a Single Run

To evaluate a single specific strategy without sweeping all three, set `DOCUMENT_CHUNKING_STRATEGY` in `.env` before running the standard evaluation:

```env
# Options: textractor-word-stream | linear-sentence-splitter | layout
DOCUMENT_CHUNKING_STRATEGY=layout
```

Then run:

```bash
python -m evaluation_suite.search_evaluation.run_evaluation
```

The strategy name is stamped on every row in `evaluation_log.csv` so results remain comparable even when the setting changes over time.

### Strategies

| Strategy | Description |
|----------|-------------|
| `textractor-word-stream` | Raw word-stream from AWS Textract — high token density, maximum recall |
| `linear-sentence-splitter` | Sentence-boundary splits applied to the Textract word stream |
| `layout` | Textract layout blocks (headings, paragraphs, tables) — maps to visual document structure |

---

## 4. Configuration

All settings are in `evaluation_settings.py`.

### Search Boosts

Set to `0` to disable, or `>0` to enable and weight.

| Setting | Description | Example |
|---------|-------------|---------|
| `KEYWORD_BOOST` | Exact keyword matching | 1.0 |
| `ANALYSER_BOOST` | English analyzer (stemming, stopwords) | 0.0 |
| `SEMANTIC_BOOST` | Vector/embedding similarity | 0.0 |
| `FUZZY_BOOST` | Typo-tolerant matching | 0.0 |
| `WILDCARD_BOOST` | Wildcard pattern matching | 0.0 |

### Search Parameters

| Setting | Description | Example |
|---------|-------------|---------|
| `RESULT_SIZE` | Results per search | 60 |
| `SCORE_FILTER` | Minimum score threshold | 0.56 |
| `FUZZINESS` | Fuzzy tolerance | "Auto" |
| `MAX_EXPANSIONS` | Max fuzzy expansions | 50 |
| `FUZZY_MATCH_THRESHOLD` | Term verification threshold (0-100) | 80 |

### Programmatic Overrides

Override settings at runtime without editing files:

```python
from evaluation_suite.search_evaluation.run_evaluation import main

result = main(settings_overrides={"KEYWORD_BOOST": 2.0, "SEMANTIC_BOOST": 0.5})
```

---

## 5. Search Client

Perform individual ad-hoc searches and export results to Excel. Useful for investigating unexpected evaluation results.

### Usage

```bash
python -m evaluation_suite.search_evaluation.query.search_client
```

### Configuration

Edit `SEARCH_TERM` at the top of `search_client.py`. All boost/filter settings are shared with `evaluation_settings.py`.

### Output

```
output/single-search-results/<date>/<timestamp>_<term>_search_results.xlsx
```

---

## 6. Expected Chunks Generator

Auto-generates expected chunk IDs in `search_terms.csv` based on local keyword matching against all indexed chunks. Uses `chunks_loader` to fetch chunks, separating the process from OpenSearch query logic.

### Usage

```bash
python -m evaluation_suite.search_evaluation.legacy.generate_expected_chunks
```

### Matching Logic

| Term Type | Matching Method |
|-----------|-----------------|
| Single word (`brain`) | Keyword match (case-insensitive), optionally stemmed |
| Multi-word (`mental health`) | Any word appearing in chunk is a match (case-insensitive), optionally stemmed |
| Date (`28/01/2018`) | Format variants or phrase match (see below) |

### Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| `DATE_FORMAT_VARIANTS` | When `True`, dates match any format variant (e.g., 28/01/2018, 2018-01-28). When `False`, dates are searched as exact phrase matches. | `False` |
| `USE_STEMMING` | When `True`, words are stemmed before matching (e.g., "injuries" matches "injury"). When `False`, exact word matching is used. | `False` |

### When to Run

- After changing chunking strategy
- After re-ingesting documents
- After adding new search terms to CSV

---

## 7. Parameter Optimization

Uses Bayesian optimization (Optuna) to find optimal boost parameters.

### How It Works

The optimizer uses a Tree-structured Parzen Estimator (TPE):

1. **Phase 1 (Coarse)** — 50 trials, step=0.3, broad exploration
2. **Phase 2 (Fine)** — 50 trials, step=0.05, refine promising regions

**Objective:** Maximize `optimization_score`:
```
optimization_score = avg_chunks_returned × (acceptable_term_precision@10)²
```

### Usage

```bash
python -m evaluation_suite.search_evaluation.optimization.optimize_search
```

Default: 100 trials. Modify `main(n_trials=X)` to change.

### Output

```
output/optimization/
├── <timestamp>/
│   ├── summary.json        # Best parameters
│   └── trial_history.json  # All trials
└── latest/                 # Symlink to most recent
```

### After Optimization

1. Review best parameters in `summary.json`
2. Update `evaluation_settings.py` with optimal values
3. Confirm: `python -m evaluation_suite.search_evaluation.run_evaluation`

---

## 8. Module Reference

| Module | Purpose |
|--------|---------|
| `run_evaluation.py` | Main evaluation entry point |
| `evaluation_settings.py` | Central configuration |
| `evaluation_config.py` | Path management and utilities |
| `search_looper.py` | Batch search execution |
| `search_client.py` | OpenSearch query builder |
| `chunks_loader.py` | Load chunks from OpenSearch |
| `term_matching.py` | Term verification (exact, wildcard, stemmed, fuzzy) |
| `chunk_metrics.py` | Ranked precision@10/@20 and recall@10/@20 calculation |
| `ground_truth.py` | Auto-generate expected chunk IDs from the indexed corpus |
| `synonym_generator.py` | Generate acceptable (similar) terms via scispaCy word vectors |
| `relevance_scoring.py` | Summary statistics and output |
| `date_formats.py` | Date parsing and format variants |
| `generate_expected_chunks.py` | Auto-populate expected chunk IDs |
| `optimize_search.py` | Bayesian parameter optimization |

### Tests

Located in `tests/`:
- `test_term_matching.py` — Term matching strategy tests
- `test_chunk_metrics.py` — Ranked precision@10/@20 and recall@10/@20 tests
- `test_ground_truth.py` — Auto ground-truth generation tests
- `test_synonym_generator.py` — Acceptable-term (synonym) generation tests
