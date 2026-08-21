# Tech Stack & Build System

## Language & Runtime

- Python 3.12 (pinned in `.python-version`)
- Package manager: **uv** (not pip)
- Build backend: **Hatchling**

## Key Dependencies

| Library | Purpose |
|---------|---------|
| `opensearch-py` | Vector database client |
| `pydantic` / `pydantic-settings` | Configuration and data models |
| `amazon-textract-textractor` | OCR text extraction |
| `amazon-textract-caller` | Textract API calls |
| `boto3` | AWS SDK (S3, Textract, Bedrock) |
| `pdf2image` | PDF page to image conversion |

## Testing

| Tool | Purpose |
|------|---------|
| `pytest` | Test runner |
| `pytest-cov` | Coverage (minimum 90% enforced) |
| `pytest-mock` | Mocking |
| `moto` | AWS service mocking |

## Linting & Formatting

| Tool | Purpose |
|------|---------|
| `ruff` | Linter and formatter (replaces black, isort, flake8) |
| `deptry` | Dependency checker |
| `gitleaks` | Secret detection |

### Ruff Configuration

- Line length: 120
- Docstring convention: Google style
- Enabled rule sets: E, F, W, I, T20, D
- Docstring rules (D*) are relaxed in test files
- Format: double quotes, space indent

## Common Commands

```bash
# Create virtual environment and install all deps
uv venv && uv sync

# Run all tests (production + evaluation suite)
uv run pytest

# Run production tests only
uv run pytest tests/

# Install evaluation-only deps
uv sync --extra evaluation

# Run the pipeline locally (loads .env)
bash run_locally_with_dot_env.sh

# Lock dependencies
uv lock
```

## Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:
1. `ruff-format` — auto-format
2. `ruff` — lint with auto-fix
3. `gitleaks` — secret scanning
4. `nbstripout` — strip notebook outputs
5. `uv-lock` — ensure lock file is up to date
6. `deptry` — dependency issues
7. `pytest` — run tests with coverage

## Container

- Base image: `analytical-platform-airflow-python-base`
- Production entrypoint: `python src/ingestion_pipeline/main.py`
- Only `src/ingestion_pipeline` is bundled into the Docker image (no evaluation suite, no dev deps)

## CI/CD (GitHub Actions)

- `test.yml` — Run tests
- `release-container.yml` — Build and push to ECR
- `scan-container.yml` — Grype vulnerability scanning
- `test-container.yml` — Container structure tests
- `codeQL-review.yml` — CodeQL analysis
- `dependency-review.yml` — Dependency review
