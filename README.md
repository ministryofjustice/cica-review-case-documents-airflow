# CICA Review Case Documents Airflow Ingestion Pipeline

 [![Ministry of Justice Repository Compliance Badge](https://github-community.service.justice.gov.uk/repository-standards/api/cica-review-case-documents-airflow/badge)](https://github-community.service.justice.gov.uk/repository-standards/cica-review-case-documents-airflow)

Note: This project is built from the Analytical Platform Airflow Python Template and contains an [Analytical Platform Airflow workflow](https://user-guidance.analytical-platform.service.justice.gov.uk/services/airflow/index.html#overview).


## Description

This project ingests CICA case documents, performs OCR to extract text, creates copies of document pages, and stores text plus metadata embeddings in a vector database. It is the backend ingestion service used by the [UI application](https://github.com/ministryofjustice/cica-review-case-documents), which enables case workers to query the vector database and view highlighted search results against page images.

Note: The project is in active private beta and features are still evolving.

## Quick Start

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Create the virtual environment and sync dependencies:

```
uv venv
uv sync
```

3. Run the ingestion pipeline from the repository root:

```bash
bash run_locally_with_dot_env.sh
```

For local and remote environment setup, see [runbooks/RUNBOOK.md](/runbooks/RUNBOOK.md).

## Running Tests

The project uses [pytest](https://docs.pytest.org/en/stable/).

Install evaluation dependencies when running the full suite (includes `evaluation_suite/tests/`):

```
uv sync --extra evaluation
```

Run all tests:

```
uv run pytest
```

Run production tests only:

```
uv run pytest tests/
```

Coverage reports are generated under `htmlcov/index.html`.

## Documentation Map

- Environment setup index: [runbooks/RUNBOOK.md](/runbooks/RUNBOOK.md)
- Local development runbook: [runbooks/LOCAL_DEVELOPMENT_RUNBOOK.md](/runbooks/LOCAL_DEVELOPMENT_RUNBOOK.md)
- Remote port-forward runbook: [runbooks/REMOTE_PORT_FORWARDING_RUNBOOK.md](/runbooks/REMOTE_PORT_FORWARDING_RUNBOOK.md)
- OpenSearch indexes guide: [local-dev-environment/OPENSEARCH_INDEXES_README.md](/local-dev-environment/OPENSEARCH_INDEXES_README.md)
- Bedrock connector guide: [local-dev-environment/BEDROCK_CONNECTOR_README.md](/local-dev-environment/BEDROCK_CONNECTOR_README.md)
- Troubleshooting guide: [docs/TROUBLESHOOTING.md](/docs/TROUBLESHOOTING.md)
- Vulnerability management: [docs/VULNERABILITY_MANAGEMENT.md](/docs/VULNERABILITY_MANAGEMENT.md)
- Docs conventions: [docs/DOCS_CONVENTIONS.md](/docs/DOCS_CONVENTIONS.md)

## Repository Contents

The repository comes with the following preset files:

- GitHub Actions workflows
  - Dependency review (if your repository is public) (`.github/workflows/dependency-review.yml`)
  - Container release to Analytical Platform's ECR (`.github/workflows/release-container.yml`)
  - Container scan with Grype (`.github/workflows/scan-container.yml`)
  - Container structure test (`.github/workflows/test-container.yml`)
- CODEOWNERS
- Dependabot configuration
- Dockerfile
- MIT License

## Project Structure

This repository contains three distinct components:

### `src/ingestion_pipeline`
The pipeline code responsible for:
- ingesting CICA case documents
- performing OCR
- embedding text
- storing data in a vector database
- copying page images and storing the images within AWS S3

### `evaluation_suite`
Independent tooling for evaluating and optimising the OpenSearch search configuration. This code is **not** part of the production pipeline and is **not** bundled into the Docker image.

Evaluation-specific dependencies (e.g. `pandas`, `optuna`, `snowballstemmer`) are declared separately under `[project.optional-dependencies]` as the `evaluation` extra in `pyproject.toml` to keep them out of the production environment.

To install evaluation dependencies locally:
```
uv sync --extra evaluation
```

> **Note:** `deptry` (the dependency checker used in pre-commit) does not enforce unused package detection (`DEP002`) for `[project.optional-dependencies]`. Unused evaluation dependencies must be reviewed manually.

### `local-dev-environment`

See the [runbooks](/runbooks/RUNBOOK.md) for local and remote environment workflows.

## Contributor Setup

- Pre-commit setup and workflow: [docs/DOCS_CONVENTIONS.md](/docs/DOCS_CONVENTIONS.md)
- Troubleshooting common local/dev issues (including WSL): [docs/TROUBLESHOOTING.md](/docs/TROUBLESHOOTING.md)
- Vulnerability management and dependency overrides: [docs/VULNERABILITY_MANAGEMENT.md](/docs/VULNERABILITY_MANAGEMENT.md)

## Governance

- GitHub repository standards: [Ministry of Justice Repository Standards](https://github-community.service.justice.gov.uk/repository-standards/)
- Manage outside collaborators: [github-collaborators](https://github.com/ministryofjustice/github-collaborators)
- Update CODEOWNERS to define approving teams or users

