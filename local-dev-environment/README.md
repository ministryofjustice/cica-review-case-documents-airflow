# Localstack local developer environment

Docker and LocalStack resources to be created:

- [Localstack](https://www.localstack.cloud/)
- [OpenSearch](https://docs.localstack.cloud/aws/services/opensearch/)
- [OpenSearch Dashboard](https://docs.opensearch.org/docs/latest/dashboards/)
- OpenSearch Index: `page_chunks`, [create-opensearch-resources.sh](./init-scripts/create-opensearch-resources.sh)
- AWS resources, [create-aws-resources.sh](./init-scripts/create-aws-resources.sh)

## Pre-requisites

- [Docker](https://docs.docker.com/get-started/get-docker/)
- [Docker Desktop](https://docs.docker.com/desktop/)
- [LocalStack Desktop](https://docs.localstack.cloud/aws/capabilities/web-app/localstack-desktop/)
- [uv](https://docs.astral.sh/uv/) for Python dependency management
- LocalStack image version is pinned by default in `docker-compose.yml` to avoid auth/license regressions on newer releases. Override with `LOCALSTACK_IMAGE` in `local-dev-environment/.env` when needed.

Optional image override example:

```bash
LOCALSTACK_IMAGE=localstack/localstack:2.3.2
```

 - Ensure `local-dev-environment/.env` variables are set; note the `AWS_MOD_PLATFORM_*` variables will require daily rotation. You can refresh connector credentials without a full Docker rebuild by rerunning the Bedrock setup script with `BEDROCK_FORCE_RECREATE_CONNECTOR=true`.

### For VPN WSL users

If you are running the local environment from behind a corporate VPN with SSL inspection, and encounter SSL certificate issues, you may need to set the following environment variables in your .bashrc to allow LocalStack to trust your custom certificates:
```
# Ensures LocalStack and its internal services trust the custom CA
export LOCALSTACK_REQUESTS_CA_BUNDLE="/home/your_user/custom_ca_bundle.pem"
export LOCALSTACK_HOST_MOUNTS="/home/your_user/custom_ca_bundle.pem:/etc/ssl/certs/custom_ca_bundle.pem"
```
This assumes you have already created the custom_ca_bundle.pem file as described in the main project README, CICA specific Windows WSL setup and configuration instructions.

 - Ensure `local-dev-environment/.env` variables are set; note the `AWS_MOD_PLATFORM_*` variables will require daily rotation. You can refresh connector credentials without a full Docker rebuild by rerunning the Bedrock setup script with `BEDROCK_FORCE_RECREATE_CONNECTOR=true`.

### For VPN WSL users

If you are running the local environment from behind a corporate VPN with SSL inspection, and encounter SSL certificate issues, you may need to set the following environment variables in your .bashrc to allow LocalStack to trust your custom certificates:
```
# Ensures LocalStack and its internal services trust the custom CA
export LOCALSTACK_REQUESTS_CA_BUNDLE="/home/your_user/custom_ca_bundle.pem"
export LOCALSTACK_HOST_MOUNTS="/home/your_user/custom_ca_bundle.pem:/etc/ssl/certs/custom_ca_bundle.pem"
```
This assumes you have already created the custom_ca_bundle.pem file as described in the main project README, CICA specific Windows WSL setup and configuration instructions.

## Setup

Navigate into the local-dev-environment folder

```bash
cd cica-review-case-documents-airflow/local-dev-environment
```

and run

```bash
docker compose up -d --force-recreate
```

You should see

```
:~/cica-review-case-documents-airflow/local-dev-environment$ docker compose up -d --force-recreate
[+] Running 5/5
 ✔ Network local-dev-environment_default  Created                                       
 ✔ Volume "local-dev-environment_data01"  Created                                   
 ✔ Container opensearch                  Started                                       
 ✔ Container localstack-main             Healthy                               
 ✔ Container opensearch-dashboards       Started   
```

View the localstack logs

``docker  logs localstack-main -f``

Look for

```
Waiting for OpenSearch domain to be created...
2025-07-09T13:38:52.761  INFO --- [et.reactor-0] localstack.request.aws     : AWS opensearch.DescribeDomain => 200
        "Processing": false,
OpenSearch domain created.
2025-07-09T13:38:54.510  INFO --- [et.reactor-0] localstack.request.aws     : AWS opensearch.DescribeDomain => 200
DOMAIN_ENDPOINT: case-document-search-domain.eu-west-2.opensearch.localhost.localstack.cloud:4566
Waiting for OpenSearch to be ready...
```

There may be a short delay whilst the domain spins up then you should see

```
OpenSearch is ready! Creating index 'case-documents'...
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100  1168  100    73  100  1095    174   2610 --:--:-- --:--:-- --:--:--  2794
{"acknowledged":true,"shards_acknowledged":true,"index":"page_chunks"}LocalStack resources configuration completed.
Ready.

```

The environment is then ready to be used. OpenSearch is accessible at `http://localhost:9200`.

## Docker Desktop

If Docker Desktop has been installed you can view, pause, stop, run and view logs for the environment and the individual containers from within the Docker Desktop UI (recommended).

## Opensearch Dashboard

Navigate to http://127.0.0.1:5601/ to view the OpenSearch dashboard.

Navigate to [indices](http://127.0.0.1:5601/app/opensearch_index_management_dashboards#/indices?from=0&search=&showDataStreams=false&size=20&sortDirection=desc&sortField=index) to view the `page_chunks` index.

### Loading Documents

To ingest documents into OpenSearch, run the ingestion pipeline from the project root:

```bash
cd ..
bash run_locally_with_dot_env.sh
```

This will process a sample document and index the chunks into OpenSearch. After ingestion, you can create an [index pattern](https://docs.opensearch.org/latest/dashboards/management/index-patterns/) named `page_chunks` and start searching. See the [quickstart](https://docs.opensearch.org/latest/dashboards/quickstart/) for more details.

## Bedrock Connector Notes

For a focused setup and troubleshooting guide, see [BEDROCK_CONNECTOR_README.md](./BEDROCK_CONNECTOR_README.md).

Bedrock connector setup is managed in [03-setup-bedrock-connector-neural.sh](./init-scripts/03-setup-bedrock-connector-neural.sh).

Canonical explanation of search pipeline behavior (including when requests do or do not need to specify a pipeline explicitly) is documented in [../README.md](../README.md#opensearch-search-pipeline-behavior).

### Shared setup implementation

Both setup entrypoints now reuse shared helper functions in [init-scripts/lib/bedrock_connector_common.inc](./init-scripts/lib/bedrock_connector_common.inc):

- LocalStack init flow: [03-setup-bedrock-connector-neural.sh](./init-scripts/03-setup-bedrock-connector-neural.sh)
- Port-forward flow: [setup-bedrock-connector-portforward.sh](./setup-bedrock-connector-portforward.sh)

For maintenance, update connector/model/pipeline logic in the shared helper first, then keep entrypoint scripts focused on environment-specific auth and bootstrapping.

### Rotating AWS credentials without rebuilding

When `AWS_MOD_PLATFORM_*` credentials expire, you do not need to rebuild the full local environment.

1. Update `local-dev-environment/.env` with fresh `AWS_MOD_PLATFORM_ACCESS_KEY_ID`, `AWS_MOD_PLATFORM_SECRET_ACCESS_KEY`, and `AWS_MOD_PLATFORM_SESSION_TOKEN`.
2. Restart only LocalStack:

```bash
cd local-dev-environment
docker compose restart localstack
```

3. Force connector/model recreation so OpenSearch stores fresh Bedrock credentials:

```bash
docker compose exec -e BEDROCK_FORCE_RECREATE_CONNECTOR=true localstack \
        bash /etc/localstack/init/ready.d/03-setup-bedrock-connector-neural.sh
```

This refreshes connector/model auth without recreating OpenSearch indexes.

For the port-forward setup script, `CONFIRM_OVERWRITE` controls behavior when existing pipelines or index settings are found:

- `prompt` (default): ask before overwriting
- `true`: overwrite without prompting
- `false`: fail instead of overwriting

### Port-forward usage and security notes

The port-forward setup script is intended for manual, local execution only:

- Run `kubectl port-forward` first on the same machine where the script runs (loopback binding expected, for example `127.0.0.1:9200`).
- Do not use this workflow on shared hosts or jump boxes.
- Required local tools include `curl`, `kubectl`, and `base64`.

Credential handling considerations:

- Avoid storing `OPENSEARCH_PASSWORD` / `OPENSEARCH_BEARER_TOKEN` in shell startup files.
- Prefer short-lived terminal environment variables and clear them after use.
- Stop the port-forward session when setup is complete.

This is a temporary operational workaround to configure a remote OpenSearch instance through a local port-forward.

If credentials backing the connector have rotated, force recreation during port-forward setup with either of these flags:

- `FORCE_RECREATE_CONNECTOR=true`
- `BEDROCK_FORCE_RECREATE_CONNECTOR=true`

Example:

```bash
FORCE_RECREATE_CONNECTOR=true CONFIRM_OVERWRITE=true ./setup-bedrock-connector-portforward.sh
```

### Port-forward index setup helper

To create or recreate `page_chunks` and `page_metadata` mappings against a port-forwarded OpenSearch instance, use:

```bash
./setup-opensearch-indexes-portforward.sh
```

Overwrite behavior is controlled with `CONFIRM_OVERWRITE`:

- `prompt` (default): ask before deleting/recreating indexes
- `true`: recreate existing indexes without prompting
- `false`: keep existing indexes and skip creation

### Troubleshooting Bedrock setup

1. Error: `The security token included in the request is expired`

This means the connector is using stale temporary AWS credentials.

For local-only setup:

```bash
cd local-dev-environment
docker compose restart localstack
docker compose exec -e BEDROCK_FORCE_RECREATE_CONNECTOR=true localstack \
        bash /etc/localstack/init/ready.d/03-setup-bedrock-connector-neural.sh
```

For port-forward setup:

```bash
FORCE_RECREATE_CONNECTOR=true CONFIRM_OVERWRITE=true ./setup-bedrock-connector-portforward.sh
```

2. Model state remains `PARTIALLY_DEPLOYED`

On small or limited-node dev clusters this can be normal. If search works, this state can be acceptable.

Check model state:

```bash
curl -s http://127.0.0.1:9200/_plugins/_ml/models/<MODEL_ID> | jq '.model_state'
```

If state stays `PARTIALLY_DEPLOYED` but queries succeed, proceed. If queries fail, re-run setup with force recreate and verify index search pipeline settings.

### Ingest-time embedding toggle

Use `BEDROCK_ENABLE_INGEST_PIPELINE` to control whether OpenSearch generates embeddings at index time:

- `false` (default): ingest pipeline is not used (`default_pipeline` is set to `_none`)
- `true`: ingest pipeline `bedrock-embedding-pipeline` is configured and used

Recommended local default: keep `BEDROCK_ENABLE_INGEST_PIPELINE=false` and rely on app-side embedding during ingestion.

### Current embedding behavior

When `BEDROCK_ENABLE_INGEST_PIPELINE=false`:

- Document embeddings are generated by the ingestion app before indexing.
- Query embeddings are still generated at search time via the default search pipeline.

### Hybrid search score fusion

The default search pipeline currently configures query-time neural enrichment (`neural_query_enricher`) only.
Hybrid-score normalization and branch score-combination processors are intentionally not configured at this time.

## Python Environment Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management. Local dependencies are defined in a separate `pyproject.toml`.

```bash
cd local-dev-environment

# Create virtual environment and install dependencies
uv sync

# Activate the virtual environment
source .venv/bin/activate
```

## Evaluation Workflow

For details on running the search evaluation workflow (measuring precision/recall of different search configurations), see the [Evaluation Suite README](../evaluation_suite/EVALUATION_SUITE.md).
