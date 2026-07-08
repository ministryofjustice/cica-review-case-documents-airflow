# OpenSearch Indexes Runbook

This runbook documents how `page_chunks` and `page_metadata` indexes are created, configured, and validated across local and port-forward workflows.

## Source of truth

Index settings and mappings are defined in:

- `init-scripts/lib/opensearch_templates.inc`

These templates are applied by both setup entrypoints before index creation:

- LocalStack init flow: `init-scripts/02-create-opensearch-resources.sh`
- Port-forward flow: `setup-opensearch-indexes-portforward.sh`

Indexes are then created with an empty payload (`{}`) so template settings/mappings are applied consistently.

## Why templates instead of inline index JSON

Templates avoid schema drift between scripts and environments.

- One canonical place for mappings/settings.
- Consistent index shape across setup paths.
- Easy environment-specific shard/replica overrides via environment variables.

## Topology configuration

Shard and replica settings are controlled by environment variables consumed by templates:

- `OPENSEARCH_NUMBER_OF_SHARDS` (default: `2`)
- `OPENSEARCH_NUMBER_OF_REPLICAS` (default: `1`)

Default/current non-prod example:

```bash
OPENSEARCH_NUMBER_OF_SHARDS=2 OPENSEARCH_NUMBER_OF_REPLICAS=1 \
OPENSEARCH_ENDPOINT=http://127.0.0.1:9200 \
CONFIRM_OVERWRITE=true \
./setup-opensearch-indexes-portforward.sh
```

If you do not set these variables explicitly, the port-forward setup script uses `2` shards and `1` replica by default.

Notes:

- Primary shards cannot be changed in-place for an existing index; recreate/reindex is required.
- Replica count can be changed in-place, but this runbook keeps values template-driven for parity.
- For semantic search, shard topology can affect kNN recall/latency characteristics.

## Recreate behavior

`setup-opensearch-indexes-portforward.sh` supports:

- `CONFIRM_OVERWRITE=prompt` (default): asks before deleting/recreating indexes
- `CONFIRM_OVERWRITE=true`: delete and recreate existing indexes
- `CONFIRM_OVERWRITE=false`: do not recreate existing indexes

When changing template settings that must apply to existing indexes (for example shard count), run with `CONFIRM_OVERWRITE=true`.

After recreating indexes, rerun `setup-bedrock-connector-portforward.sh` for the same environment so the `default_pipeline` and `search.default_pipeline` settings are reattached. 

To re-ingest documents into OpenSearch, run the ingestion pipeline from the project root:

```bash
cd ..
bash run_locally_with_dot_env.sh
```

## Recommended parity workflow

Until a production environment exists, keep DEV and UAT aligned.

1. Choose a shared topology (for example `2` shards / `1` replica).
2. Recreate indexes in DEV with those values.
3. Recreate indexes in UAT with the same values.
4. Re-run Bedrock connector setup if required to ensure index pipeline settings are reattached.
5. Verify settings in both environments.

## Verification commands

Check template definitions:

```bash
curl -s http://127.0.0.1:9200/_index_template/page_chunks_template | jq
curl -s http://127.0.0.1:9200/_index_template/page_metadata_template | jq
```

Check actual index settings:

```bash
curl -s http://127.0.0.1:9200/page_chunks/_settings \
| jq '.page_chunks.settings.index | {number_of_shards, number_of_replicas, default_pipeline, search_default_pipeline: (."search.default_pipeline" // .search.default_pipeline)}'

curl -s http://127.0.0.1:9200/page_metadata/_settings \
| jq '.page_metadata.settings.index | {number_of_shards, number_of_replicas}'
```

If your OpenSearch version requires POST for simulation:

```bash
curl -s -X POST http://127.0.0.1:9200/_index_template/_simulate_index/page_chunks \
| jq
```

## Troubleshooting

### Template missing (404)

If `/_index_template/page_chunks_template` returns 404:

- The template has not been applied in that environment.
- Re-run index setup script with the correct endpoint and credentials.

### Simulate output shows null shard/replica

If simulation returns null values:

- No matching composable template may be applied.
- Check both composable and legacy templates:

```bash
curl -s http://127.0.0.1:9200/_index_template | jq '.index_templates[].name'
curl -s http://127.0.0.1:9200/_template/page_chunks* | jq
```

