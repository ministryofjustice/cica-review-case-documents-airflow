# Runbooks

This project was built from the Analytical Platform Airflow Python template and currently targets the [Analytical Platform](https://user-guidance.analytical-platform.service.justice.gov.uk/) via [Airflow](https://user-guidance.analytical-platform.service.justice.gov.uk/services/airflow/index.html).

> **Status (paused):** This project is paused. The planned direction is to retire the
> Airflow DAG and re-home the ingestion service on the Cloud Platform or Modernisation
> Platform. The container entrypoint and deployment model (e.g. a long-lived Kubernetes
> Deployment running `runner.main`) will be finalised as part of that migration. Until
> then, the image entrypoint (`python src/ingestion_pipeline/main.py`) only configures
> logging and exits and does not start the SQS polling worker.

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

Note: the Airflow-on-Analytical-Platform model described above is expected to change. The
service is likely to move to the Cloud Platform or Modernisation Platform, with the
long-lived worker (`runner.main`) run as a Kubernetes Deployment rather than driven by an
Airflow DAG.










