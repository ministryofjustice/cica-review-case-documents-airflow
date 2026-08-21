# Project Structure

## Top-Level Layout

```
├── src/ingestion_pipeline/   # Production pipeline code (bundled in Docker)
├── tests/                    # Unit tests for src/ingestion_pipeline
├── evaluation_suite/         # Search evaluation & optimization tooling (NOT production)
├── local-dev-environment/    # Docker Compose, LocalStack, OpenSearch local setup
├── runbooks/                 # Operational runbooks for local and remote dev
├── docs/                     # Project documentation
├── bin/                      # Utility scripts
├── .github/workflows/        # CI/CD pipelines
```

## Source Code (`src/ingestion_pipeline/`)

| Module | Responsibility |
|--------|---------------|
| `main.py` | Entrypoint — sets up logging |
| `runner.py` | Orchestrates single-document pipeline execution |
| `pipeline_builder.py` | Constructs the pipeline with all dependencies |
| `config.py` | Pydantic Settings configuration (env vars + .env) |
| `aws_client/` | AWS client factories (S3, Textract, Bedrock) |
| `chunking/` | Text chunking strategies (layout, sentence, word-stream) |
| `custom_logging/` | Structured logging setup and context |
| `data_models/` | Shared data models |
| `date_extraction/` | Date parsing from document text |
| `embedding/` | Bedrock embedding generation |
| `indexing/` | OpenSearch indexing and health checks |
| `orchestration/` | Pipeline orchestration logic |
| `page_processor/` | Per-page processing (OCR + image) |
| `s3_file_downloader/` | S3 document retrieval |
| `textract/` | AWS Textract integration |
| `uuid_generators/` | Deterministic UUID generation for documents |

## Test Structure (`tests/`)

Mirrors `src/ingestion_pipeline/` — each source module has a corresponding test directory. Tests use `pytest` with `moto` for AWS mocking and `pytest-mock` for general mocking.

## Evaluation Suite (`evaluation_suite/`)

Separate from production. Contains:
- `search_evaluation/` — OpenSearch query evaluation and parameter optimization (uses optuna, pandas)
- Its own `tests/` directory
- Output data in `search_evaluation/output/`

Installed via `uv sync --extra evaluation`. Never included in the Docker image.

## Configuration

- `pyproject.toml` — Project metadata, dependencies, tool config
- `ruff.toml` — Ruff linter/formatter settings
- `pytest.ini` — Pytest configuration (90% coverage threshold)
- `.env` / `.env_template` — Environment variables (pydantic-settings loads these)
- `Dockerfile` — Production container definition

## Conventions

- Configuration is centralized in `src/ingestion_pipeline/config.py` using `pydantic-settings`
- Environment variables are the primary config mechanism (with `.env` fallback for local dev)
- The `Settings` class is instantiated as a module-level singleton (`settings`)
- Test files do not require docstrings (ruff D-rules suppressed)
- All source code requires Google-style docstrings
