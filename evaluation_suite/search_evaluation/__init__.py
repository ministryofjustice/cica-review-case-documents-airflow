"""Search evaluation framework for measuring search relevance.

This package contains modules for evaluating and optimizing OpenSearch
configurations for the CICA document review system.

Modules:
    run_evaluation: Main entry point for evaluation
    evaluation_settings: Configuration constants
    evaluation_config: Path and config management
    opensearch_client: Shared OpenSearch client factory
    search_client: OpenSearch query execution and Excel export
    search_query_builder: OpenSearch query construction and score filtering
    search_looper: Batch search execution
    chunks_loader: Load chunks from OpenSearch
    evaluation_models: EvaluationSummary dataclass
    evaluation_reporting: CSV and log file I/O
    relevance_scoring: Precision/recall calculation
    chunk_metrics: Per-chunk match metrics
    term_matching: Term verification strategies
    date_formats: Date parsing utilities
    generate_expected_chunks: Auto-populate expected chunks
    optimize_search: Bayesian parameter optimization
    optimization_results: Save and display optimization results
"""
