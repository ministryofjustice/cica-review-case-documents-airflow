# Remote OpenSearch Index and Bedrock Connector Creation

Creation of indexes, Bedrock connectors, and document processing is currently carried out from a secure remote development machine.

If you want to create or recreate indexes or Bedrock connectors for a remote environment (DEV or UAT), follow this runbook.
## Cloud Platform Terraform Files

The [OpenSearch suite](https://opensearch.org/) has been provisioned via terraform files within the [MOJ cloud platform environment](https://user-guide.cloud-platform.service.justice.gov.uk/#cloud-platform-user-guide).
- [DEV namespace](https://github.com/ministryofjustice/cloud-platform-environments/tree/main/namespaces/live.cloud-platform.service.justice.gov.uk/cica-review-case-documents-dev). 
- [UAT namespace](https://github.com/ministryofjustice/cloud-platform-environments/tree/main/namespaces/live.cloud-platform.service.justice.gov.uk/cica-review-case-documents-uat).

## Getting Started

### Cloud Platform guide

- Follow the [Connecting to the Cloud Platform’s Kubernetes cluster](https://user-guide.cloud-platform.service.justice.gov.uk/documentation/getting-started/kubectl-config.html) guide.

### Connecting to the OpenSearch service proxy

1. Get the OpenSearch service proxy value for the Cloud Platform namespace you want to port forward to.

    The namespace value can be obtained from the [cloud platform environments repo](https://github.com/ministryofjustice/cloud-platform-environments/blob/main/namespaces/live.cloud-platform.service.justice.gov.uk/cica-review-case-documents-dev/00-namespace.yaml)

    Example namespace: ```cica-review-case-documents-dev```
    ```bash
    kubectl --namespace <namespace>  get services
    ```
2. Replace the ```<opensearch-service-proxy>``` placeholder with the value retrieved in the previous step and start port forwarding.
    ```bash
    kubectl --namespace <namespace> port-forward service/<opensearch-service-proxy> 9200:8080 
    ```

The remote OpenSearch instance is now available at ```http://localhost:9200```.

### Create or recreate indexes and Bedrock connector

1. From the repository root, change to `local-dev-environment` and create/recreate indexes.
    ```bash
    cd local-dev-environment
    ./setup-opensearch-indexes-portforward.sh
    ```
    See the [OpenSearch index setup script](/local-dev-environment/setup-opensearch-indexes-portforward.sh) for details.

2. Recreate the Bedrock connector.
    ```bash
    ./setup-bedrock-connector-portforward.sh
    ```
    See the [Bedrock connector script](/local-dev-environment/setup-bedrock-connector-portforward.sh) for usage.


Note: recreating indexes deletes all existing index data.

### Document Processing (Ingestion)

#### Prerequisites

- You are a member of the [cica-review-case-documents](https://github.com/orgs/ministryofjustice/teams/cica-review-case-documents) GitHub team, ask a FIND team member for support.
- You have been added to the CICA FIND AWS [IAM users policies](https://github.com/CriminalInjuriesCompensationAuthority/cicainfrastructure-documentsearch-find-ai/blob/main/iam_user.tf), contact the CICA INFRA team for support. 
- You can access CICA AWS environments
    - You have enabled MFA on your CICA AWS account with an Authenticator App.
    - You have the [AWS CLI installed](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
    - You have an [AWS Access Key](https://docs.aws.amazon.com/keyspaces/latest/devguide/create.keypair.html)
    - You have [configured AWS profiles](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)  
    - You have added the AWS Access key to your profile. 

- The CRN and source documents you are ingesting are present within the MOD SANDBOX environment and the CICA AWS environments.

    Example: 
    ```bash
    AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX=26-700001
    AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME=Case1_TC19_50_pages_brain_injury.pdf
    ```

#### Environment variable configuration

1. If you have not already done so, create a root `.env` file from [.env_template](../.env_template).
2. Create or rotate the `AWS_MOD_PLATFORM_*` values:
    1. Ask a team member to add you to the [cica-review-case-documents](https://github.com/orgs/ministryofjustice/teams/cica-review-case-documents) GitHub team.
    2. [Access and log in to the Modernisation Platform AWS console](https://user-guide.modernisation-platform.service.justice.gov.uk/user-guide/accessing-the-aws-console.html#accessing-the-aws-console).
    3. From the AWS access portal, select the cica-sandbox-development AWS account.
    4. Select the modernisation-platform-sandbox Access Keys link.
    5. Copy the access keys into your root `.env` file.
3. Set local development mode to false:
    ```bash
    # -- Local Development Mode --       
    # Defaults to false
    # Set LOCAL_DEVELOPMENT_MODE to false because you are port forwarding to a remote environment
    # and will be using a CICA AWS S3 bucket (NOT a local stack bucket) to store the processed documents page images 
    LOCAL_DEVELOPMENT_MODE=false
    ```
4. Comment out the LocalStack AWS variables
    ```bash
    # CICA S3 bucket for KTA documents, localstack configuration for local development
    # AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET=local-kta-documents-bucket
    # AWS_CICA_S3_PAGE_BUCKET_URI=http://localhost:4566
    # AWS_CICA_S3_PAGE_BUCKET=local-kta-documents-bucket
    # AWS_CICA_AWS_ACCESS_KEY_ID=test
    # AWS_CICA_AWS_SECRET_ACCESS_KEY=test
    # AWS_CICA_AWS_SESSION_TOKEN=test
    ```
5. Uncomment the AWS variables for the environment you are port forwarding to.
    For example, if you are port forwarding to DEV:
    ```bash
    # DEV configuration for CICA AWS resources
    # CICA S3 bucket for KTA documents
    AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET=dev-documentsearch-kta-bucket
    AWS_CICA_S3_PAGE_BUCKET_URI=s3://dev-documentsearch-kta-bucket
    AWS_CICA_S3_PAGE_BUCKET=dev-documentsearch-kta-bucket
    AWS_CICA_AWS_ACCESS_KEY_ID=<AWS_CICA_AWS_ACCESS_KEY_ID>
    AWS_CICA_AWS_SECRET_ACCESS_KEY=<AWS_CICA_AWS_SECRET_ACCESS_KEY>
    AWS_CICA_AWS_SESSION_TOKEN=<AWS_CICA_AWS_SESSION_TOKEN>
    ```
6. Create or rotate the environment-specific CICA AWS key values.
    1. Get an authenticator token code for the environment using your Authenticator app
    2. Generate a Session Token
        ```bash
        aws sts get-session-token   --serial-number arn:aws:iam::<cica-aws-account-id>:mfa/<mfa-device> --token-code <authenticator token>  --profile <configure-aws-cica-aws-env-profile>
        ```
    3. Add the session token values to your `.env` file.
        ```bash
        AWS_CICA_AWS_ACCESS_KEY_ID=<AWS_CICA_AWS_ACCESS_KEY_ID>
        AWS_CICA_AWS_SECRET_ACCESS_KEY=<AWS_CICA_AWS_SECRET_ACCESS_KEY>
        AWS_CICA_AWS_SESSION_TOKEN=<AWS_CICA_AWS_SESSION_TOKEN>
        ```

#### Ingesting documents

From the project root directory run this [script](/run_locally_with_dot_env.sh) to run the python code and process documents.

```bash
bash run_locally_with_dot_env.sh
```

Note: running the ingestion script with the same CRN (`DOCUMENT_CASE_PREFIX`) and source document removes associated index entries before re-ingesting.

**Example**: The default project root .env configuration will process this document.

```bash
AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX=26-700001
AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME=Case1_TC19_50_pages_brain_injury.pdf
```