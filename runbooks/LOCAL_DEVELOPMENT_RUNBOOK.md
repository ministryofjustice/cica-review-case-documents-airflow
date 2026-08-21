# Working with a Local Development Environment

Use this runbook to build, manage, and use a local development environment that simulates the intended [target architecture](https://dsdmoj.atlassian.net/wiki/spaces/CICAIET/pages/5770674447/Architectural+proposal).

Your local development environment includes:
1. OpenSearch resources
    - OpenSearch instance: [docker compose file](/local-dev-environment/docker-compose.yml)
    - OpenSearch indexes: [02-create-opensearch-resources.sh](/local-dev-environment/init-scripts/02-create-opensearch-resources.sh) and [opensearch_templates.inc](/local-dev-environment/init-scripts/lib/opensearch_templates.inc)
    - OpenSearch Bedrock connector: [03-setup-bedrock-connector-neural.sh](/local-dev-environment/init-scripts/03-setup-bedrock-connector-neural.sh) and [bedrock_connector_common.inc](/local-dev-environment/init-scripts/lib/bedrock_connector_common.inc)

2. LocalStack emulated AWS resources
    - LocalStack instance: [docker compose file](/local-dev-environment/docker-compose.yml)
    - S3 bucket(s) for source documents and page images: [01-create-aws-resources.sh](/local-dev-environment/init-scripts/01-create-aws-resources.sh)
    - Redacted development documents copied from an external sandbox S3 bucket into LocalStack

3. Init scripts and templates
    The init scripts are mounted into containers and create resources, indexes, and connectors during composition.
    - [01-create-aws-resources.sh](/local-dev-environment/init-scripts/01-create-aws-resources.sh)
    - [02-create-opensearch-resources.sh](/local-dev-environment/init-scripts/02-create-opensearch-resources.sh)
    - [03-setup-bedrock-connector-neural.sh](/local-dev-environment/init-scripts/03-setup-bedrock-connector-neural.sh)
    - [opensearch_templates.inc](/local-dev-environment/init-scripts/lib/opensearch_templates.inc)
    - [bedrock_connector_common.inc](/local-dev-environment/init-scripts/lib/bedrock_connector_common.inc)

Note: `opensearch_templates.inc` and `bedrock_connector_common.inc` are shared by init scripts and port-forward scripts. See [REMOTE_PORT_FORWARDING_RUNBOOK.md](/runbooks/REMOTE_PORT_FORWARDING_RUNBOOK.md).

## Diagrams

- [OpenSearch index creation flow](/local-dev-environment/diagrams/opensearch-index-creation-flow.mermaid)
- [Bedrock connector flow](/local-dev-environment/diagrams/bedrock-connector-flow.mermaid)


## Getting Started

1. Clone the repo into a directory of your choice
```bash
    git clone https://github.com/ministryofjustice/cica-review-case-documents-airflow.git
```
2. Change into the newly created repo directory
```bash
    cd cica-review-case-documents-airflow
```
3. Create `local-dev-environment/.env` using [local-dev-environment/.env_template](/local-dev-environment/.env_template)
4. Ask a FIND team member to add you to the [cica-review-case-documents](https://github.com/orgs/ministryofjustice/teams/cica-review-case-documents) GitHub team.
5. [Access and log in](https://user-guide.modernisation-platform.service.justice.gov.uk/user-guide/accessing-the-aws-console.html#accessing-the-aws-console) to the Modernisation Platform AWS console.
6. From the AWS access portal select the cica-sandbox-development AWS account.
7. Select the modernisation-platform-sandbox Access Keys link.
8. Copy the access keys into your local-dev-environment/.env file.

    Replace 
    ```bash
    AWS_MOD_PLATFORM_ACCESS_KEY_ID=MOD_AWS_ACCESS_KEY_ID
    AWS_MOD_PLATFORM_SECRET_ACCESS_KEY=MOD_AWS_SECRET_ACCESS_KEY
    AWS_MOD_PLATFORM_SESSION_TOKEN=MOD_AWS_SESSION_TOKEN
    ```

### Spin up the local environment

1. Ensure [Docker](https://www.docker.com/) is installed and running on your local machine: we recommend installing [Docker Desktop](https://docs.docker.com/desktop/).
2. From the repository root, change to the `local-dev-environment` directory
```
    cd local-dev-environment
```
3. Use Docker and the local development [docker compose file](/local-dev-environment/docker-compose.yml) to spin up the local development environment
```bash
    docker compose up -d --force-recreate
```

### Processing redacted documents

#### Configuration and Access Keys

Note: the following steps ask you to create another `.env` file at the project root.

1. Ensure you are in the repository root.
2. Create a root `.env` file by copying [.env_template](../.env_template).
3. [Access and log in](https://user-guide.modernisation-platform.service.justice.gov.uk/user-guide/accessing-the-aws-console.html#accessing-the-aws-console) to the Modernisation Platform AWS console.
4. From the AWS access portal, select the cica-sandbox-development AWS account.
5. Select the modernisation-platform-sandbox Access Keys link.
6. Copy the Mod Platform access keys into your root `.env` file and replace placeholder values.

    These are the only key values you need to replace within the .env file.

    ```bash
    AWS_MOD_PLATFORM_ACCESS_KEY_ID=<AWS_MOD_PLATFORM_ACCESS_KEY_ID>
    AWS_MOD_PLATFORM_SECRET_ACCESS_KEY=<AWS_MOD_PLATFORM_SECRET_ACCESS_KEY>
    AWS_MOD_PLATFORM_SESSION_TOKEN=<AWS_MOD_PLATFORM_SESSION_TOKEN>
    ```
    Note: these env vars can also be copied from `local-dev-environment/.env` if they have not expired.

    Note: `AWS_MOD_PLATFORM_*` values require daily rotation.

    Key env var values for local development environment

    ```bash
    # Development AWS Textract OCR processing runs within the project's MOD PLATFORM sandbox account. 
    # A copy of the document to be processed must also be present within the 
    # AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET MOD PLATFORM sandbox bucket
    # This is to mock retrieving a message from an SQS queue, retrieving the S3 object from CICA AWS S3
    # and copying the object to a temporary bucket within the analytical platform for Textract Processing.  
    # This is used, for now, for all development activities, 
    # that is for local development and port forwarding to remote (DEV and UAT) OpenSearch instances.
    USE_MOD_PLATFORM_MODE=true
    AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET=mod-platform-sandbox-kta-documents-bucket

    AWS_MOD_PLATFORM_ACCESS_KEY_ID=<mod_platform_access_key_id>
    AWS_MOD_PLATFORM_SECRET_ACCESS_KEY=<mod_platform_secret_access_key>
    AWS_MOD_PLATFORM_SESSION_TOKEN=<mod_platform_session_token>

    # Set LOCAL_DEVELOPMENT_MODE to true when processing documents to a local development environment
    LOCAL_DEVELOPMENT_MODE=true

    # The case and document to be processed
    AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX=26-700001
    AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME=Case1_TC19_50_pages_brain_injury.pdf

    # LOCAL STACK CONFIGURATION FOR LOCAL DEVELOPMENT
    AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET=local-kta-documents-bucket
    AWS_CICA_S3_PAGE_BUCKET_URI=http://localhost:4566
    AWS_CICA_S3_PAGE_BUCKET=local-kta-documents-bucket
    AWS_CICA_AWS_ACCESS_KEY_ID=test
    AWS_CICA_AWS_SECRET_ACCESS_KEY=test
    AWS_CICA_AWS_SESSION_TOKEN=test
    ```

#### Ingesting scanned documents

From the project root directory run this [script](/run_locally_with_dot_env.sh) to run the python code and process documents.

```bash
bash run_locally_with_dot_env.sh
```

**Example**: The default project root .env configuration will process this document.

```bash
AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX=26-700001
AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME=Case1_TC19_50_pages_brain_injury.pdf
```

When a document is processed, the following actions occur:
- the document is retrieved, via _CASE_PREFIX and _DOCUMENT_FILENAME from a localstack S3 bucket 
    created during the local development setup: ```AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET=local-kta-documents-bucket```.
- an image copy is made of each page within the document.
- the image copies are stored within the localstack S3 bucket created during the local development setup under ```AWS_CICA_S3_PAGE_BUCKET/_DOCUMENT_CASE_PREFIX/<DOCUMENT_GUID>/pages/```.

    Example:  ```s3://local-kta-documents-bucket/26-700001/535aaa3d-41df-58d4-8eb1-897a5d39830a/pages/1.png```

    The default `.env_template` key and value: ```AWS_CICA_S3_PAGE_BUCKET=local-kta-documents-bucket```.

    Note: by default this is set to the same value as ```AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET=local-kta-documents-bucket```.
    You can optionally set a distinct page bucket to decouple page image storage from source document storage.

- chunks of text are extracted from the document pages using [AWS Textract](https://aws.amazon.com/textract/). 

    Note: this step temporarily uses a copy of the original document stored within the Mod Platform sandbox because AWS Textract cannot process a LocalStack S3 object.
- the text is embedded using [Amazon Bedrock](https://aws.amazon.com/bedrock/?trk=4add6476-cc7c-4d85-8694-998bf2855ab0&sc_channel=ps&ef_id=db11636edfac103f7208091e72333f91:G:s&msads_camp=487441873&msads_ag=1147891988117018&msads_ad=71743417930149&msads_kw=aws%20bedrock&msads_matchtype=e&msads_network=o&msads_device=c&msads_geo={LocationId}&msclkid=db11636edfac103f7208091e72333f91). 

    Note: this step does not use the Bedrock connector; a boto3 client is used to embed each chunk independently.
- page metadata is stored within an OpenSearch index [page_metadata]. 
    The mapping can be found within the [opensearch template](/local-dev-environment/init-scripts/lib/opensearch_templates.inc).
- page chunk text, embeddings, bounding box information, and additional metadata are stored within an OpenSearch index [page_chunks].
    The mapping can be found within the [opensearch template](/local-dev-environment/init-scripts/lib/opensearch_templates.inc).

Note: running the ingestion script again with the same document metadata removes associated entries from the indexes and associated page images, then recreates both index data and page images.

## Further reading

- [local development environment README](/local-dev-environment/README.md)
- [OpenSearch index creation README](/local-dev-environment/OPENSEARCH_INDEXES_README.md)
- [Bedrock connector README](/local-dev-environment/BEDROCK_CONNECTOR_README.md)
