# Search Relevance Testing Framework

A framework for evaluating and optimizing OpenSearch configurations for the CICA document review system. It measures how well different search strategies (keyword, semantic, fuzzy, etc.) return relevant document chunks for predefined search terms.

## Quick Start

# Run a single evaluation
python -m evaluation_suite.search_evaluation.run_evaluation

# Run parameter optimization (30 trials)
python -m evaluation_suite.search_evaluation.optimize_search
```

**Prerequisites:**
- LocalStack/OpenSearch running locally
- Documents ingested into OpenSearch
- Valid AWS credentials in `.env` (see main project README)

---

## Contents

1. [Evaluation Workflow](#1-evaluation-workflow)
2. [Configuration](#2-configuration)
3. [Search Client](#3-search-client)
4. [Expected Chunks Generator](#4-expected-chunks-generator)
5. [Parameter Optimization](#5-parameter-optimization)
6. [Module Reference](#6-module-reference)

---

## 1. Evaluation Workflow

Measures how well search configurations return expected chunks for predefined search terms. Calculates precision, recall, and other metrics to compare configurations.

### Pipeline

```
search_terms.csv → search_looper → OpenSearch → term_matching → chunk_metrics → relevance_scoring → output
```

1. **Load terms** — `search_looper.py` reads from `testing_docs/search_terms.csv`
2. **Execute searches** — Each term queries OpenSearch via `search_client.py`
3. **Load chunks** — `chunks_loader.py` fetches all indexed chunks for term matching
4. **Match terms** — `term_matching.py` verifies returned chunks contain expected terms
5. **Calculate metrics** — `chunk_metrics.py` computes precision and recall
6. **Aggregate results** — `relevance_scoring.py` generates summary statistics
7. **Output** — Results written to timestamped CSVs and cumulative log

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

## 2. Configuration

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
| `K_QUERIES` | Results per search | 60 |
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

## 3. Search Client

Perform individual ad-hoc searches and export results to Excel. Useful for investigating unexpected evaluation results.

### Usage

```bash
python -m evaluation_suite.search_evaluation.search_client
```

### Configuration

Edit `SEARCH_TERM` at the top of `search_client.py`. All boost/filter settings are shared with `evaluation_settings.py`.

### Output

```
output/single-search-results/<date>/<timestamp>_<term>_search_results.xlsx
```

---

## 4. Expected Chunks Generator

Auto-generates expected chunk IDs in `search_terms.csv` based on local keyword matching against all indexed chunks. Uses `chunks_loader` to fetch chunks, separating the process from OpenSearch query logic.

### Usage

```bash
python -m evaluation_suite.search_evaluation.generate_expected_chunks
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

## 5. Parameter Optimization

Uses Bayesian optimization (Optuna) to find optimal boost parameters.

### How It Works

The optimizer uses a Tree-structured Parzen Estimator (TPE):

1. **Phase 1 (Coarse)** — 50 trials, step=0.3, broad exploration
2. **Phase 2 (Fine)** — 50 trials, step=0.05, refine promising regions

**Objective:** Maximize `optimization_score`:
```
optimization_score = avg_chunks_returned × (acceptable_term_precision)²
```

### Usage

```bash
python -m evaluation_suite.search_evaluation.optimize_search
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

## 6. Module Reference

| Module | Purpose |
|--------|---------|
| `run_evaluation.py` | Main evaluation entry point |
| `evaluation_settings.py` | Central configuration |
| `evaluation_config.py` | Path management and utilities |
| `search_looper.py` | Batch search execution |
| `search_client.py` | OpenSearch query builder |
| `chunks_loader.py` | Load chunks from OpenSearch |
| `term_matching.py` | Term verification (exact, wildcard, stemmed, fuzzy) |
| `chunk_metrics.py` | Precision/recall calculation |
| `relevance_scoring.py` | Summary statistics and output |
| `date_formats.py` | Date parsing and format variants |
| `generate_expected_chunks.py` | Auto-populate expected chunk IDs |
| `optimize_search.py` | Bayesian parameter optimization |

### Tests

Located in `tests/`:
- `test_term_matching.py` — Term matching strategy tests
- `test_chunk_metrics.py` — Precision/recall calculation tests
