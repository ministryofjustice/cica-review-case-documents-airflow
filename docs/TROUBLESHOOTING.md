# Troubleshooting

Use this guide for quick symptom -> cause -> fix workflows.

## OpenSearch index template returns 404

Symptom:
- `/_index_template/page_chunks_template` returns 404.

Likely cause:
- Index templates have not been applied in the current environment.

Fix:
- Re-run index setup for the relevant environment.

```bash
# LocalStack
docker compose exec -e CONFIRM_OVERWRITE=true localstack \
  bash /etc/localstack/init/ready.d/02-create-opensearch-resources.sh

# Port-forward
cd local-dev-environment
OPENSEARCH_ENDPOINT=http://127.0.0.1:9200 CONFIRM_OVERWRITE=true \
  ./setup-opensearch-indexes-portforward.sh
```

## Simulate index output shows null shard or replica values

Symptom:
- `/_index_template/_simulate_index/page_chunks` returns null for shard or replica settings.

Likely cause:
- No matching composable template is applied, or the wrong endpoint is being queried.

Fix:
- Verify available templates and re-apply index setup.

```bash
curl -s http://127.0.0.1:9200/_index_template | jq '.index_templates[].name'
curl -s http://127.0.0.1:9200/_template/page_chunks* | jq
```

## Bedrock connector fails with expired AWS token

Symptom:
- `The security token included in the request is expired`.

Likely cause:
- `AWS_MOD_PLATFORM_*` temporary credentials have expired.

Fix:
- Rotate credentials and recreate connector/model resources.

```bash
# LocalStack
cd local-dev-environment
docker compose restart localstack
docker compose exec -e BEDROCK_FORCE_RECREATE_CONNECTOR=true localstack \
  bash /etc/localstack/init/ready.d/03-setup-bedrock-connector-neural.sh

# Port-forward
cd local-dev-environment
BEDROCK_FORCE_RECREATE_CONNECTOR=true CONFIRM_OVERWRITE=true \
  ./setup-bedrock-connector-portforward.sh
```

## Bedrock model remains PARTIALLY_DEPLOYED

Symptom:
- Model state remains `PARTIALLY_DEPLOYED`.

Likely cause:
- Expected behavior on smaller development clusters.

Fix:
- Verify whether search queries still succeed before taking corrective action.

```bash
curl -s http://127.0.0.1:9200/_plugins/_ml/models/<MODEL_ID> | jq '.model_state'
```

If queries fail:
- Re-run connector setup with `BEDROCK_FORCE_RECREATE_CONNECTOR=true`.
- Verify index `default_pipeline` and `search.default_pipeline` settings.

## WSL pre-commit TLS failures

Symptom:
- Pre-commit fails with TLS or certificate trust errors.

Likely cause:
- Missing custom CA bundle in WSL or LocalStack runtime trust configuration.

Fix:
- Create the `custom_ca_bundle.pem` as described in WSL setup guidance.
- Configure LocalStack CA bundle environment variables if needed:

```bash
export LOCALSTACK_REQUESTS_CA_BUNDLE="/home/your_user/custom_ca_bundle.pem"
export LOCALSTACK_HOST_MOUNTS="/home/your_user/custom_ca_bundle.pem:/etc/ssl/certs/custom_ca_bundle.pem"
```

## WSL pre-commit Go module download failures

Symptom:
- Commit fails with Go download errors from pre-commit hooks.

Likely cause:
- Proxy resolution problems in network-restricted environments.

Fix:
- Configure `GOPROXY`:

```bash
export GOPROXY=https://goproxy.dev,direct
```

Then reload your shell:

```bash
source ~/.bashrc
# or
source ~/.zshrc
```

## WSL git commit -S pinentry failure

Symptom:
- `gpg: signing failed: Inappropriate ioctl for device`.

Likely cause:
- WSL tty is not exported for GPG pinentry.

Fix:
- Export `GPG_TTY` and reload shell:

```bash
export GPG_TTY=$(tty)
source ~/.bashrc
# or
source ~/.zshrc
```

## Logging and ingestion diagnostics

For runner-level failure diagnosis:
- Search for `CRITICAL` entries from `runner.py`.
- Trace all related logs using `source_doc_id`.
- Review accompanying `INFO` logs for remediation actions.

For page-level chunking and bounding box debugging:

```bash
# Enable page-specific debugging
DEBUG_PAGE_NUMBERS={1,3,5}

# Disable page-specific debugging
DEBUG_PAGE_NUMBERS={}
```

Run with optional file logging:

```bash
./run_locally_with_dot_env.sh --log-to-file
```