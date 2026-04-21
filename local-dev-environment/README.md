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
- **For VPN WSL users**: If you are running the local environment from behind a corporate VPN with SSL inspection, you must also set the following environment variables in your .bashrc to allow LocalStack to trust your custom certificates:

```
# Ensures LocalStack and its internal services trust the custom CA
export LOCALSTACK_REQUESTS_CA_BUNDLE="/home/your_user/custom_ca_bundle.pem"
export LOCALSTACK_HOST_MOUNTS="/home/your_user/custom_ca_bundle.pem:/etc/ssl/certs/custom_ca_bundle.pem"
```

This assumes you have already created the custom_ca_bundle.pem file as described in the main project README, CICA specific Windows WSL setup and confguration instructions.

- Ensure your `local-dev-environment/.env` file is created and contains valid AWS credentials for the `AWS_MOD_PLATFORM_*` variables. You can copy the structure from the `local-dev-environment/.env_template` file.

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

Bedrock connector setup is managed in [03-setup-bedrock-connector-neural.sh](./init-scripts/03-setup-bedrock-connector-neural.sh).

### Shared setup implementation

Both setup entrypoints now reuse shared helper functions in [init-scripts/lib/bedrock_connector_common.inc](./init-scripts/lib/bedrock_connector_common.inc):

- LocalStack init flow: [03-setup-bedrock-connector-neural.sh](./init-scripts/03-setup-bedrock-connector-neural.sh)
- Port-forward flow: [setup-bedrock-connector-portforward.sh](./setup-bedrock-connector-portforward.sh)

For maintenance, update connector/model/pipeline logic in the shared helper first, then keep entrypoint scripts focused on environment-specific auth and bootstrapping.

For the port-forward setup script, `CONFIRM_OVERWRITE` controls behavior when existing pipelines or index settings are found:

- `prompt` (default): ask before overwriting
- `true`: overwrite without prompting
- `false`: fail instead of overwriting

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

Hybrid result normalization and branch score combination are configured in the default search pipeline created by [03-setup-bedrock-connector-neural.sh](./init-scripts/03-setup-bedrock-connector-neural.sh), not in [02-create-opensearch-resources.sh](./init-scripts/02-create-opensearch-resources.sh).

### Hybrid query tuning options (quick guidance)

If you want stable behavior without deep tuning, use this order of controls:

1. Branch weights in the search pipeline (primary control)
2. Candidate depth (`k` on `neural`, `pagination_depth` on `hybrid`)
3. Per-query boosts (secondary, optional)

Recommended starting point:

- Keep normalization enabled (`min_max` + `arithmetic_mean`)
- Use moderate lexical boosts (for example: `match_phrase.boost=3`, `match.boost=1.5`)
- Use larger semantic candidate pool (for example: `neural.k=40`, `hybrid.pagination_depth=20`)

Suggested operating modes:

- Balanced (default): pipeline weights `[0.6, 0.2, 0.2]`
- Precision-first lexical: try `[0.5, 0.3, 0.2]`
- Recall/semantic-first: try `[0.5, 0.2, 0.3]`

Notes:

- Boosts are still valid with normalization, but mainly influence ranking within each branch.
- Weights are the main lever for balancing lexical vs semantic contribution after normalization.

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
