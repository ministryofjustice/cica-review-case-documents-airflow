# Copilot Instructions — CICA Document Search Airflow Pipeline

## Project Overview

An AWS-based ingestion pipeline that processes CICA case documents through OCR (Textract), chunks extracted text, generates vector embeddings (Bedrock), and indexes into OpenSearch for hybrid search. Built on the MoJ Analytical Platform Airflow template.

## Architecture

```
S3 Document → Textract OCR → Page Processing → Chunking (strategy pattern) → Embedding → OpenSearch Indexing
```

**Key modules** under `src/ingestion_pipeline/`:
- `orchestration/pipeline.py` — main workflow coordinator
- `pipeline_builder.py` — composition root / dependency injection
- `config.py` — Pydantic `BaseSettings`, all config from env vars
- `chunking/` — dual-strategy chunking system (see Chunking Architecture below)
- `embedding/` — Bedrock Titan Embed Text v2
- `indexing/` — OpenSearch bulk indexing (chunk + page metadata indexes)
- `page_processor/` — PDF→image conversion, S3 upload
- `textract/` — AWS Textract async job orchestration

**Evaluation suite** (`evaluation_suite/`) is independent tooling for search parameter tuning with Optuna. Not part of the production image.

## Build & Run Commands

| Task | Command |
|---|---|
| Install dependencies | `uv sync` |
| Install with evaluation extras | `uv sync --extra evaluation` |
| Run all tests | `uv run pytest` |
| Run specific test file | `uv run pytest tests/chunking/test_document_chunker.py` |
| Run single test | `uv run pytest tests/chunking/test_document_chunker.py -k test_name` |
| Lint | `ruff check src tests evaluation_suite` |
| Format | `ruff format src tests evaluation_suite` |
| Dependency check | `deptry .` |
| Run pipeline locally | `./run_locally_with_dot_env.sh` |
| Start local dev env | `docker compose -f local-dev-environment/docker-compose.yml up` |

## Conventions

### Python
- **Python 3.12+**, managed with `uv` (not pip)
- **Pydantic v2** for data models and settings — use `BaseSettings` with env var binding
- **Ruff** for linting and formatting (line length 120, Google-style docstrings)
- **Double quotes** for strings
- **Google-style docstrings** (`pydocstyle convention = "google"`)
- Import sorting: `isort` via ruff with `combine-as-imports = true`

### Project Structure
- Production code: `src/ingestion_pipeline/`
- Tests mirror source layout: `tests/chunking/` tests `src/ingestion_pipeline/chunking/`
- Evaluation code: `evaluation_suite/` (separate optional dependency group, excluded from Docker image)
- Test data fixtures: `tests/chunking/data/` (JSON Textract responses)

### Testing
- **pytest** with `pytest-cov` — **90% coverage required** (`--cov-fail-under=90`)
- Coverage scope: `src/` and `evaluation_suite.search_evaluation`
- Test paths: `tests/` and `evaluation_suite/tests/`
- Use **factory fixtures** for flexible test data (pattern: `@pytest.fixture` returning inner `_factory(**overrides)` function)
- Use **`pytest-mock`** (`mocker` fixture) and `unittest.mock` for mocking
- Use **`moto`** (`@mock_aws`) for AWS service mocking
- No global `conftest.py` — fixtures are defined inline in test files
- Descriptive test names: `test_<method>_<scenario>` or `test_<behavior_description>`

### Chunking Architecture

Two chunking strategies share the `ChunkStrategy` ABC (`chunk_strategy.py`), selected at runtime via `DOCUMENT_CHUNKING_STRATEGY` env var:

| Strategy | Key | Entry Point |
|---|---|---|
| Line-sentence (default) | `linear-sentence-splitter` | `strategies/line_sentence/line_sentence_handler.py` |
| Layout-based | `layout` | `strategies/layout/layout_chunk_handler.py` |

**Factory**: `chunk_strategy_factory.py` → `get_chunk_strategy()` instantiates the selected strategy with its config.

**Line-sentence strategy** (`strategies/line_sentence/`):
- Processes Textract LINE blocks directly in a single pass
- Sentence-aware splitting at `.?!` boundaries after reaching `min_words`
- Force-breaks on large vertical gaps (`max_vertical_gap_ratio`) or `max_words` exceeded
- Lookahead/backward scanning for sentence boundaries (±3 lines)
- Key files: `chunker.py` (core algorithm), `chunk_builder.py`, `sentence_detector.py`, `config.py`

**Layout strategy** (`strategies/layout/`):
- Uses Textract LAYOUT block types (TEXT, TABLE, KEY_VALUE, LIST, etc.)
- Layout type handlers extend `LayoutType` base class (`types/base.py`)
- Produces atomic chunks per block → `ChunkMerger` groups into page-level chunks
- Type mapping lives in `layout_chunk_handler.py`

**Shared conventions**:
- Chunk indices reset to 0 per page (not global across document)
- Deterministic UUIDs (v5) for chunk and document IDs via `uuid_generators/`
- Both strategies return `ProcessedDocument` with `List[DocumentChunk]`

### Pre-commit
Hooks run on commit and push: ruff format, ruff lint, gitleaks (secret scanning), nbstripout, uv-lock, deptry, pytest.

## Pitfalls

- **Don't add evaluation dependencies to `[project.dependencies]`** — they go in `[project.optional-dependencies]` to stay out of the Docker image.
- **`deptry` doesn't check optional-dependencies for DEP002** — review unused evaluation packages manually.
- **Coverage threshold is enforced in CI** — new code must maintain ≥90% coverage. Check with `uv run pytest` before pushing.
- **Textract response mocking is complex** — use the builder in `tests/chunking/test_utils/textract_response_builder.py` and existing JSON fixtures in `tests/chunking/data/`.
- **Config values come from env vars** — when testing `config.py`, use `monkeypatch.setenv()` to set values.
- **`uv.lock` must stay in sync** — run `uv lock` after changing dependencies. The pre-commit hook enforces this.
