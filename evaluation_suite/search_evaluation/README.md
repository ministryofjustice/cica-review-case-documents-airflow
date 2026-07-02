# `search_evaluation` package

Tooling for building, running and scoring OpenSearch queries against the CICA
case-document index, plus parameter optimisation. Modules are grouped into
subpackages by responsibility.

```
search_evaluation/
├── evaluation_settings.py     # Tunable boosts/filters + override helpers (shared config)
├── pipeline_config.py         # Output paths, log file, active-search-type resolution
├── generate_expected_chunks.py# Auto-fills expected chunk IDs in search_terms.csv
├── run_single_evaluation.py   # ENTRY POINT: single-case evaluation → CSV report
├── run_evaluation.py          # Backwards-compatible wrapper for run_single_evaluation
├── run_chunking_comparison.py # ENTRY POINT: compare all chunking strategies
├── opensearch/                # OpenSearch connectivity
│   ├── opensearch_client.py     # OpenSearch client + health check (CHUNK_INDEX_NAME)
│   ├── chunks_loader.py         # Loads indexed chunks from OpenSearch (data access)
│   └── bootstrap.py             # Index creation, health-check, ingestion trigger
├── query/                     # Building & executing search queries
│   ├── search_type_config.py    # SearchType enum, QueryDslConfig, resolve_search_type()
│   ├── search_query_builder.py  # Builds the hybrid (keyword + kNN + date) query DSL
│   ├── search_client.py         # ENTRY POINT: ad-hoc single search → .xlsx
│   ├── search_looper.py         # Runs the search-terms CSV through the client
│   └── date_formats.py          # Date detection / variant expansion for date queries
├── relevance/                 # Scoring how relevant returned chunks are
│   ├── relevance_scoring.py     # Orchestrates relevance evaluation of search hits
│   ├── ground_truth.py          # Auto-generates expected chunk IDs from the index
│   ├── synonym_generator.py     # Generates acceptable (similar) terms via scispaCy / Bedrock
│   ├── term_matching.py         # Exact/stemmed/fuzzy/wildcard term matching
│   ├── chunk_metrics.py         # Chunk-level match metrics
│   ├── evaluation_models.py     # Dataclasses for evaluation results/summaries
│   └── evaluation_reporting.py  # Writes evaluation CSV + appends to the log
├── multi_case/                # 30-case evaluation pipeline
│   ├── search_term_extractor.py # Extracts search terms from caseworker .docx summaries
│   ├── case_discovery.py        # Discovers evaluation cases from S3
│   ├── multi_case_bootstrap.py  # Ingests all cases into OpenSearch (subprocess per case)
│   ├── ingestion_runner.py      # Subprocess entry point: installs Textract cache then runs ingestion
│   ├── textract_cache.py        # Local JSON cache for Textract responses (avoids repeat AWS calls)
│   ├── multi_case_runner.py     # Runs per-case relevance evaluation
│   └── multi_case_aggregator.py # Aggregates per-case results → summary CSV
└── optimization/              # Hyper-parameter search over query settings
    ├── optimize_search.py       # ENTRY POINT: run parameter optimisation
    ├── optimization_engine.py   # Optuna study driver
    ├── optimization_objective.py# Objective function over QueryDslConfig settings
    └── optimization_results.py  # Persist/print optimisation results (OUTPUT_DIR)
```

## Entry points

| Command | Produces |
| --- | --- |
| `./run_multi_case_evaluation.sh --cases 26-700001,...` | Per-date report CSV in `output/<YYYYMMDD>/multi_case_<HHMMSS>.csv` |
| `python -m evaluation_suite.search_evaluation.run_single_evaluation` | Evaluation CSV in `output/evaluation/<date>/<search_type>/` |
| `python -m evaluation_suite.search_evaluation.run_chunking_comparison` | Comparison across all chunking strategies |
| `python -m evaluation_suite.search_evaluation.query.search_client` | Single-search results `.xlsx` in `output/single-search-results/<date>/` |
| `python -m evaluation_suite.search_evaluation.optimization.optimize_search` | Optimisation results in `output/optimization/` |

All entry points need a reachable OpenSearch (`page_chunks` index with a
`knn_vector` mapping), indexed documents, and AWS Bedrock credentials for
client-side query embeddings.

## Query DSL

`query/search_query_builder.py` mirrors the frontend hybrid search DSL:
keyword `match` (lexical boost), optional date `match_phrase` clauses, a kNN
clause (neural boost) and a `bool.filter` scoping to the case. It differs from
the frontend in transport only — embeddings are generated **client-side**
(Titan via `EmbeddingGenerator`) and sent as a `knn`/`vector` clause rather than
the server-side `neural`/`query_text` clause. See the module docstring for
details. Supported search types today: `hybrid` and `hybrid-dates`.
