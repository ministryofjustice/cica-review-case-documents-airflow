# Local OpenSearch Quick Start

A condensed guide to getting the local OpenSearch development environment running from a fresh branch checkout.

## Prerequisites

- Docker Desktop installed and running
- Access to the MOJ Modernisation Platform AWS console (cica-sandbox-development account)
- Python 3.12 and `uv` installed

## 1. Install Python dependencies

From the repository root:

```bash
uv venv && uv sync
```

## 2. Configure `local-dev-environment/.env`

```bash
cp local-dev-environment/.env_template local-dev-environment/.env
```

Open `local-dev-environment/.env` and replace the placeholder credentials with fresh Mod Platform sandbox access keys:

```bash
AWS_MOD_PLATFORM_ACCESS_KEY_ID=<your key>
AWS_MOD_PLATFORM_SECRET_ACCESS_KEY=<your secret>
AWS_MOD_PLATFORM_SESSION_TOKEN=<your token>
```

To get these values:

1. Log in to the [Modernisation Platform AWS access portal](https://user-guide.modernisation-platform.service.justice.gov.uk/user-guide/accessing-the-aws-console.html#accessing-the-aws-console).
2. Select the **cica-sandbox-development** account.
3. Click the **modernisation-platform-sandbox Access Keys** link.
4. Copy the three credential values.

> **Important:** These credentials expire daily and must be rotated.

## 3. Spin up the local environment

From the `local-dev-environment` directory:

```bash
cd local-dev-environment
docker compose up -d --force-recreate
```

This starts:

| Container | Port | Purpose |
|-----------|------|---------|
| `opensearch` | 9200 | OpenSearch instance |
| `localstack-main` | 4566 | S3 buckets + SQS queue + test documents |
| `opensearch-dashboards` | 5601 | Dashboards UI |
| `sqs-admin` | 3999 | Dev-only web UI for the local SQS queue |

> **SQS queue GUI:** browse the local `cica-document-search-queue` at
> http://localhost:3999 — view, send, and purge messages. This is a
> development-only aid ([pacovk/sqs-admin](https://github.com/PacoVK/sqs-admin))
> and is not part of any deployed environment. To enqueue a contract-valid test
> message from the CLI instead, use `bin/send_test_message.sh`.

The init scripts run automatically during composition and:

1. Create S3 buckets and copy test documents from the sandbox bucket into LocalStack
2. Create OpenSearch index templates and indexes (`page_chunks`, `page_metadata`)
3. Set up the Bedrock connector for neural search

Wait for all containers to report **healthy** before proceeding:

```bash
docker compose ps
```

All three containers should show `healthy` status. LocalStack can take several minutes.

## 4. Configure the root `.env`

From the repository root:

```bash
cp .env_template .env
```

Update the Mod Platform credentials (same values as step 2):

```bash
AWS_MOD_PLATFORM_ACCESS_KEY_ID=<your key>
AWS_MOD_PLATFORM_SECRET_ACCESS_KEY=<your secret>
AWS_MOD_PLATFORM_SESSION_TOKEN=<your token>
```

Ensure these values are set for local development:

```bash
LOCAL_DEVELOPMENT_MODE=true
USE_MOD_PLATFORM_MODE=true

# LocalStack configuration
AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET=local-kta-documents-bucket
AWS_CICA_S3_PAGE_BUCKET_URI=http://localhost:4566
AWS_CICA_S3_PAGE_BUCKET=local-kta-documents-bucket
AWS_CICA_AWS_ACCESS_KEY_ID=test
AWS_CICA_AWS_SECRET_ACCESS_KEY=test
AWS_CICA_AWS_SESSION_TOKEN=test
```

## 5. Ingest documents

From the repository root:

```bash
bash run_locally_with_dot_env.sh
```

The default configuration processes:

```
Case: 26-700001
File: Case1_TC19_50_pages_brain_injury.pdf
```

## 6. Verify

Check OpenSearch has data:

```bash
curl -s http://localhost:9200/page_chunks/_count | jq
curl -s http://localhost:9200/page_metadata/_count | jq
```

Or browse via OpenSearch Dashboards at http://localhost:5601.

---

## Rebuilding indexes (without full Docker rebuild)

If you need to wipe and recreate the indexes without restarting everything:

```bash
docker compose exec -e CONFIRM_OVERWRITE=true localstack \
  bash /etc/localstack/init/ready.d/02-create-opensearch-resources.sh
```

Then re-run the Bedrock connector setup:

```bash
docker compose exec localstack \
  bash /etc/localstack/init/ready.d/03-setup-bedrock-connector-neural.sh
```

Then re-ingest documents from the project root:

```bash
bash run_locally_with_dot_env.sh
```

---

## Troubleshooting

### LocalStack container unhealthy

**Symptom:** `docker compose up` reports `Container localstack-main Error` or `dependency failed to start: container localstack-main is unhealthy`.

**Diagnosis:**

```bash
docker compose logs localstack
```

**Common causes:**

| Log message | Cause | Fix |
|-------------|-------|-----|
| `export: '[...]' not a valid identifier` | AWS profile header (e.g. `[957704842145_modernisation-platform-sandbox]`) accidentally pasted into `local-dev-environment/.env` | Remove the `[...]` line. The `.env` file must only contain `KEY=VALUE` pairs and `#` comments. |
| `AWS credentials not found` | Placeholder values not replaced in `local-dev-environment/.env` | Replace `MOD_AWS_ACCESS_KEY_ID` etc. with real values from the Mod Platform console. |
| `ExpiredTokenException` or `The security token included in the request is expired` | Mod Platform credentials have expired (they rotate daily) | Get fresh credentials from the Mod Platform console and update both `.env` files. |

After fixing, always do a full rebuild:

```bash
docker compose down
docker compose up -d --force-recreate
```

### `NoSuchBucket` when running the pipeline

**Symptom:** Pipeline error: `The specified bucket does not exist` for `local-kta-documents-bucket`.

**Cause:** LocalStack didn't start properly, so the S3 bucket was never created. This is a downstream effect of the LocalStack healthcheck failing.

**Fix:** Resolve the LocalStack issue first (see above). Once all containers are healthy, the bucket will exist and the pipeline will work.

### `UnrecognizedClientException` / `The security token included in the request is invalid`

**Symptom:** Textract call fails with invalid security token.

**Cause:** The `AWS_MOD_PLATFORM_*` values in the root `.env` are expired or incorrect.

**Fix:** Refresh the credentials in the root `.env` from the Mod Platform console. These are the same values used in `local-dev-environment/.env` — they can be copied across.

### Bedrock connector script fails but OpenSearch indexes are created

**Symptom:** Indexes exist but the Bedrock neural search connector is not set up. Searches that rely on query-time embeddings won't work.

**Cause:** The `03-setup-bedrock-connector-neural.sh` script failed (check logs for the specific error).

**Fix:** After resolving the root cause, re-run manually:

```bash
docker compose exec localstack \
  bash /etc/localstack/init/ready.d/03-setup-bedrock-connector-neural.sh
```

### Formatting rules for `.env` files

Both `.env` files (`local-dev-environment/.env` and root `.env`) must follow these rules:

- Only `KEY=VALUE` pairs, one per line
- Comments start with `#`
- No AWS profile section headers like `[profile-name]`
- No quotes around values (unless the value itself contains spaces)
- No trailing comments on the same line as a value (the init scripts may not strip them correctly)

**Example of correct format:**

```bash
# Mod Platform credentials
AWS_MOD_PLATFORM_ACCESS_KEY_ID=ASIAxxxxxxxxxx
AWS_MOD_PLATFORM_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxx
AWS_MOD_PLATFORM_SESSION_TOKEN=xxxxxxxxxxxxxxxx
```

**Example of incorrect format (will break LocalStack):**

```bash
[957704842145_modernisation-platform-sandbox]
aws_access_key_id=ASIAxxxxxxxxxx
```
