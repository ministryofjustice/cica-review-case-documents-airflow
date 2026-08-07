# Runbooks

This project is an [Airflow](https://user-guidance.analytical-platform.service.justice.gov.uk/services/airflow/index.html) Python project designed to run on the [Analytical Platform](https://user-guidance.analytical-platform.service.justice.gov.uk/).

The repository includes:
- an ingestion pipeline for document processing
- local development environment tooling
- remote setup tooling for DEV/UAT OpenSearch environments

## Choose Your Path

Use this page as the entry point for setup, operation, and troubleshooting.

1. I want to set up and run everything locally.
See [LOCAL_DEVELOPMENT_RUNBOOK.md](LOCAL_DEVELOPMENT_RUNBOOK.md).

2. I want to configure DEV or UAT through port forwarding.
See [REMOTE_PORT_FORWARDING_RUNBOOK.md](REMOTE_PORT_FORWARDING_RUNBOOK.md).

3. I want to (re)create or validate OpenSearch indexes.
See [/local-dev-environment/OPENSEARCH_INDEXES_README.md](/local-dev-environment/OPENSEARCH_INDEXES_README.md).

4. I want to (re)create or troubleshoot the Bedrock connector.
See [/local-dev-environment/BEDROCK_CONNECTOR_README.md](/local-dev-environment/BEDROCK_CONNECTOR_README.md).

5. I want to understand vulnerability scanning and dependency overrides.
See [/docs/VULNERABILITY_MANAGEMENT.md](/docs/VULNERABILITY_MANAGEMENT.md).

6. I need quick troubleshooting steps.
See [/docs/TROUBLESHOOTING.md](/docs/TROUBLESHOOTING.md).

7. I need documentation and terminology conventions.
See [/docs/DOCS_CONVENTIONS.md](/docs/DOCS_CONVENTIONS.md).

## Target Architecture

See the [Architectural proposal](https://dsdmoj.atlassian.net/wiki/spaces/CICAIET/pages/5770674447/Architectural+proposal).










