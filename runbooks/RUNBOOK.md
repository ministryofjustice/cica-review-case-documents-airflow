# Runbooks

This project was built from the Analytical Platform Airflow Python template and currently targets the [Analytical Platform](https://user-guidance.analytical-platform.service.justice.gov.uk/) via [Airflow](https://user-guidance.analytical-platform.service.justice.gov.uk/services/airflow/index.html).

> **Status (paused):** This project is paused. The planned direction is to retire the
> Airflow DAG and re-home the ingestion service on the **Cloud Platform** (the
> recommended target, where OpenSearch already lives), with **CICA AWS** as the main
> alternative. Analytical Platform is blocked for this pipeline and Modernisation
> Platform remains only the current manual workaround. The container entrypoint and
> deployment model (e.g. a long-lived Kubernetes Deployment running `runner.main`, or a
> scheduled run) will be finalised as part of that migration. See
> [/docs/INGESTION_HOSTING_ASSESSMENT.md](/docs/INGESTION_HOSTING_ASSESSMENT.md) for the
> full assessment. Until then, the image entrypoint
> (`python src/ingestion_pipeline/main.py`) only configures logging and exits and does
> not start the SQS polling worker.

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

8. I want to understand where the ingestion service should be hosted and the
cross-account connectivity trade-offs (Cloud Platform vs Analytical Platform vs
Modernisation Platform vs CICA AWS).
See [/docs/INGESTION_HOSTING_ASSESSMENT.md](/docs/INGESTION_HOSTING_ASSESSMENT.md).

## Target Architecture

See the [Architectural proposal](https://dsdmoj.atlassian.net/wiki/spaces/CICAIET/pages/5770674447/Architectural+proposal).

Note: the Airflow-on-Analytical-Platform model described above is expected to change.
The recommended target is to run the ingestion service on **Cloud Platform** (where
OpenSearch already lives) with **AWS Textract enabled on Cloud Platform**; running on
**CICA AWS** is the main alternative. Analytical Platform is blocked for this pipeline
(cross-account OpenSearch is unsupported) and Modernisation Platform is only the current
manual workaround, not a target. The deployment model (long-lived worker via
`runner.main` vs a scheduled/drain-until-empty run) will be finalised as part of that
work.

For the full assessment of the hosting options and the networking/IAM reasons behind the
recommendation, see
[/docs/INGESTION_HOSTING_ASSESSMENT.md](/docs/INGESTION_HOSTING_ASSESSMENT.md).










