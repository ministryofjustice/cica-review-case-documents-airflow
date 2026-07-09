# Running the project

## Local development

- Follow the [local development environment set up instructions](/local-dev-environment/README.md)
- Set Environment variable as per the instructions within [.env_template](.env_template)

### Key env vars

```bash
USE_MOD_PLATFORM_MODE=true
AWS_LOCAL_DEV_TEXTRACT_S3_ROOT_BUCKET=mod-platform-sandbox-kta-documents-bucket

AWS_MOD_PLATFORM_ACCESS_KEY_ID=<mod_platform_access_key_id>
AWS_MOD_PLATFORM_SECRET_ACCESS_KEY=<mod_platform_secret_access_key>
AWS_MOD_PLATFORM_SESSION_TOKEN=<mod_platform_session_token>

LOCAL_DEVELOPMENT_MODE=true

AWS_CICA_S3_SOURCE_DOCUMENT_CASE_PREFIX=26-700001
AWS_CICA_S3_SOURCE_DOCUMENT_FILENAME=Case1_TC19_50_pages_brain_injury.pdf

# LOCAL STACK CONFIGURATION FOR LOCAL DEVELOPMENT
AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET=local-kta-documents-bucket
AWS_CICA_S3_PAGE_BUCKET_URI=http://localhost:4566
AWS_CICA_S3_PAGE_BUCKET=document-page-bucket
AWS_CICA_AWS_ACCESS_KEY_ID=test
AWS_CICA_AWS_SECRET_ACCESS_KEY=test
AWS_CICA_AWS_SESSION_TOKEN=test
```

Ensure the DEV and UAT CONFIGURATION FOR CICA AWS RESOURCES are commented out


## Remote port forwarding

### Pre-requisites

- You have been added to the [CICA FIND AWS IAM USERS](https://github.com/CriminalInjuriesCompensationAuthority/cicainfrastructure-documentsearch-find-ai/blob/main/iam_user.tf)
- You have enable MFA on your account
- The CRN and source documents you are ingesting are present within the MOD SANDBOX environment and the CICA AWS environments.
- You can access CICA AWS environments
- You have the [aws cli installed](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- You have an [AWS Access Key](https://docs.aws.amazon.com/keyspaces/latest/devguide/create.keypair.html)
- You have [configured aws profiles](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)  

### Running the ingestion script

- Follow the [Connecting to the Cloud Platform’s Kubernetes cluster](https://user-guide.cloud-platform.service.justice.gov.uk/documentation/getting-started/kubectl-config.html) guide.
- run 
    ```bash
    kubectl port-forward service/opensearch-proxy-service-cloud-platform-<id> 9200:8080 --namespace cica-review-case-documents-<env>
    ```
    The remote Opensearch cluster is now available on port 127.0.0.1:9200
- Set Environment variable as per the instructions within [.env_template](.env_template)

    Key changes
    ```bash
    LOCAL_DEVELOPMENT_MODE=false 
    ```

    Comment out the **LOCAL STACK CONFIGURATION FOR LOCAL DEVELOPMENT** Env vars 
    and uncomment either the DEV or UAT **CONFIGURATION FOR CICA AWS RESOURCES** Env vars

    Example
    ```bash
    AWS_CICA_S3_SOURCE_DOCUMENT_ROOT_BUCKET=dev-documentsearch-kta-bucket
    AWS_CICA_S3_PAGE_BUCKET_URI=s3://dev-documentsearch-kta-bucket
    AWS_CICA_S3_PAGE_BUCKET=dev-documentsearch-kta-bucket
    AWS_CICA_AWS_ACCESS_KEY_ID=<cica_dev_access_key_id>
    AWS_CICA_AWS_SECRET_ACCESS_KEY=<cica_dev_secret_access_key>
    AWS_CICA_AWS_SESSION_TOKEN=<cica_dev_session_token>
    ```

- Get your CICA AWS ACCESS KEYS
    ```bash
    aws sts get-session-token   --serial-number arn:aws:iam::<cica-aws-account-id>:mfa/<mfa-device> --token-code <authenticator token>  --profile <configure-aws-cica-aws-env-profile>
    ```
- Set these ENV VARS within the root .env file
- Run the ingestion script
    ```bash
    bash run_locally_with_dot_env.sh
    ```

    Note: running the ingestion script with the same CRN and source document will remove all document entries from the indexes and then re-ingest.






