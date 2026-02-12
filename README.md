# CICA Review Case Documents Airflow Ingestion Pipeline

 [![Ministry of Justice Repository Compliance Badge](https://github-community.service.justice.gov.uk/repository-standards/api/cica-review-case-documents-airflow/badge)](https://github-community.service.justice.gov.uk/repository-standards/cica-review-case-documents-airflow)

Note: This project has been built from the Analytical Platform Airflow Python Template and contains an [Analytical Platform Airflow workflow](https://user-guidance.analytical-platform.service.justice.gov.uk/services/airflow/index.html#overview).

Note: The project is under active private beta development, all features are still in development.

## Description

The aim of this project is to ingest CICA case documents, perform OCR to extract text and to store the extracted embedded text and text metadata within a vector database. The stored data will then be used to perform hybrid search and document highlighting.   


## Included Files

The repository comes with the following preset files:

- GitHub Actions workflows
  - Dependency review (if your repository is public) (`.github/workflows/dependency-review.yml`)
  - Container release to Analytical Platform's ECR (`.github/workflows/release-container.yml`)
  - Container scan with Trivy (`.github/workflows/scan-container.yml`)
  - Container structure test (`.github/workflows/test-container.yml`)
- CODEOWNERS
- Dependabot configuration
- Dockerfile
- MIT License

## Setup Instructions

See [CICA specific Windows WSL setup and confguration instructions](#windows-wsl-setup-instructions) instructions if developing on Windows

If using VSCode install the Microsoft Python extensions, Python Debugger, Python, Pylance, Python Environments

### Environment/package management

We recommend using [pyenv](https://pypi.org/project/pyenv/) to easily switch between multiple versions of Python.

This project uses [UV](https://docs.astral.sh/uv/) for packaging and dependency management.

#### Installing UV

To install `uv`, follow the [installation docs](https://docs.astral.sh/uv/getting-started/installation/).


#### Activating the environment

To [activate the virtual environment](https://docs.astral.sh/uv/pip/environments/)

```
uv venv 
```

#### Install packages/dependencies

To install the project's package requirements and their versions defined in `pyproject.toml` and `uv.lock`, run:

```
uv sync 
```

The `uv.lock` file is required to ensure the specific package versions defined there are installed, rather than their latest versions.
If you need to run a Python script from outside the `uv` environment, you can do so using the following format: `uv run src/ingestion_pipeline/main.py`

#### Managing Vulnerabilities and Dependency Overrides

This project uses uv's `constraint-dependencies` feature in `pyproject.toml` to ensure patched versions of sub-dependencies are installed, even if direct dependencies do not specify them. This is important for addressing vulnerabilities identified by tools like Trivy.

##### **Workflow:**
1. Add any required overrides (e.g., for security patches) to the `[tool.uv]` section in `pyproject.toml`
   Example:
   ```toml
      [tool.uv]
      constraint-dependencies = [
         "pillow>=12.1.1",
         "protobuf>=6.33.5",
      ]
   ```
2. Update the lock file to apply constraints:

```uv lock --upgrade```

3. Sync your environment:

```uv sync```

4. Commit the updated uv.lock and pyproject.toml files.

**Note:**  
- The Docker build and local environment will use the versions specified in `uv.lock`.
- Always update `uv.lock` after changing `constraints.txt` to ensure patched versions are installed.

##### Managing Trivy Exceptions:
Some vulnerabilities may need to be explicitly ignored if they:

Affect build-time only dependencies that are not controllable via pyproject.toml
Are false positives or not exploitable in your application context
Cannot be fixed due to upstream package constraints
To ignore a vulnerability, add it to the [trivyignore](.trivyignore) file with justification:

```
# wheel CVE-2026-24049 - Build-time only dependency from base image
# Not a runtime risk as application does not unpack untrusted wheel files
CVE-2026-24049
```
Document the reason for each exception to help future maintainers understand the security posture.

This approach ensures your project remains secure and reproducible, even when upstream packages are slow to update their dependencies.

##### Maintenance and Review Process:

###### For constraint-dependencies:
1. **Document when added:** Include dates in comments:
   ```toml
   "pillow>=12.1.1",  # CVE-2024-XXXXX - Added 2026-02-12, review after Q2 2026
2. Periodic review: After updating dependencies, test if constraints are still needed:
```
# Temporarily remove a constraint from pyproject.toml
uv lock
# Check if the patched version is now automatically included
# If yes, the constraint can be removed
```
3. Monitor upstream packages: Watch release notes of direct dependencies (e.g., amazon-textract-textractor, opensearch-protobufs) to see when they update their sub-dependencies.
4. Review schedule: Set a reminder to review constraints quarterly or when major dependency updates occur.

###### For .trivyignore:
1. Document thoroughly: Each ignored CVE should include:
   - The CVE ID
   - Why it's being ignored
   - When it was added
   - When it should be reviewed
2. Review regularly: Check ignored vulnerabilities during security reviews or dependency updates to see if they can be removed.
3. Link to issues: Consider creating GitHub issues to track ignored vulnerabilities and their resolution.

Example with dates:
```
# wheel CVE-2026-24049 - Added 2026-02-12
# Build-time only dependency from base image
# Review when base image updates or Q3 2026
CVE-2026-24049
```

#### Setting up pre-commit

#### Pre-requisite

Install [deptry](https://deptry.com/) 

[Pre-commit hooks](https://pre-commit.com/) have been included in the repo to automatically perform actions when performing git commits, such as stripping the output from Jupyter notebooks.

Pre-commit is framework for managing and maintaining pre-commit hooks.
To set up pre-commit, run the following code in the terminal:

```
uv tool install pre-commit
pre-commit install
```

After this, whenever you call `git commit` the defined pre-commit hooks will be ran against files staged for commit. Notification will be given where hooks fail and in some instances such as nbstrip out the failing file will be automatically modified. In these instances the modifications to the file will need to be added to the commit before calling `git commit` again.

**Dependency Synchronization:**

One of the key pre-commit hooks is `update-requirements`. This hook automatically compiles your dependencies from `pyproject.toml` into `requirements.txt` every time you commit. This ensures that your dependency files are always in sync. The `requirements.txt` file is maintained for compatibility with deployment environments like Docker and Airflow, which are often simpler to configure with a flat requirements file.

A corresponding GitHub Action (`regenerate-requirements.yml`) runs on every pull request to verify that `requirements.txt` is up-to-date, acting as a safeguard for the project's integrity.

### Windows WSL setup instructions

Microsoft recommends developing Pyhon Apps using WSL.
[CICA specific Windows WSL setup and configuration instructions](https://dsdmoj.atlassian.net/wiki/spaces/CICA/pages/5882806404/Set+up+instructions+for+WSL+for+windows)


## Running the project

The project has been designed to run as an airflow workflow, the project can also be run independently of airflow by running the project roots main.py file. 
This is still under development and will have no impact at the moment. 

### To run the project in it's current state and to write to the Opensearch database 

The project is still a WIP to ingest an S3 document, call textract to perform OCR, chunk and index a document. 


- set up the [local-dev-environment](./local-dev-environment/README.md)
- set up Env variables create a new file at the root of the project .env 
- copy the contents of [env_template](.env_template) to the .env file
- log in to the [modernisation aws console](https://user-guide.modernisation-platform.service.justice.gov.uk/user-guide/accessing-the-aws-console.html#logging-in)
- retireve access keys from the cica-sandbox-development aws account (if you can't see this make sure you have been added to the [cica-review-case-documents](https://github.com/orgs/ministryofjustice/teams/cica-review-case-documents) github team
- replace the aws env vars within the .env file
- run ```bash run_locally_with_dot_env.sh```
- watch the terminal logs, note Textract can take from ~30 secs to ~2 mins to process
- once the pipeline has completed use the Opensearch dashboard to view the extracted data

### New Page Image Feature

This project now includes a feature to generate and store PNG images for each page of a processed PDF document. This is useful for displaying page images alongside extracted text in a user interface.

**How it works:**

1.  When a PDF is processed, each page is converted into a PNG image.
2.  These images are uploaded to a dedicated S3 bucket (`document-page-bucket` in the local environment).
3.  The S3 URI of each page image is stored in the `page_metadata` index in OpenSearch, alongside the rest of the page's metadata.

**Configuration:**

The following new environment variables have been added to configure this feature. See the `.env_template` file for default values.
For [local development](/local-dev-environment/README.md) these will be the default Localstack keys.

-   `AWS_CICA_S3_PAGE_BUCKET_URI`: The endpoint URL for the page image S3 bucket (for local development).
-   `AWS_CICA_S3_PAGE_BUCKET`: The name of the S3 bucket for storing page images.
-   `AWS_CICA_AWS_ACCESS_KEY_ID`: AWS access key for the page image bucket.
-   `AWS_CICA_AWS_SECRET_ACCESS_KEY`: AWS secret key for the page image bucket.
-   `AWS_CICA_AWS_SESSION_TOKEN`: AWS session token for the page image bucket.

**Local Development:**

When running the local development environment, a sample document is now automatically downloaded from a source AWS S3 bucket and placed into the localstack S3 bucket (`local-kta-documents-bucket`), making it easier to test the full pipeline.

### Logging

The project has been set up to add the source document uuid (generated during ingestion) to a context var which results in all logs containing the source_doc_id for tracing purposes. 

```2025-11-06 15:05:03 INFO source_doc_id: 91c8ac49-2d20-5b35-b3f9-4563c8553a33 Step 1: Fetching and parsing document with Textract...```

### Testing the project

The project uses [pytest](https://docs.pytest.org/en/stable/) to run tests see [pytest.ini](`.pytest.ini`) for test configuration and [install pytest](https://docs.pytest.org/en/stable/getting-started.html#get-started)

To run the tests with coverage, coverage reports can be found under ```htmlcov/index.html```

```uv run pytest```

Alternatively and recommended use [VSCode Python Testing](https://code.visualstudio.com/docs/python/testing)

## Linting and Formatting

Install the [Ruff](https://astral.sh/) VSCode Extension, [ruff.toml](ruff.toml) holds the ruff configuration. 

To format and lint your code using Ruff (including auto-fixing pydocstyle issues), run:

```bash
uv run ruff format path/to/file.py
uv run ruff check --fix path/to/file.py
```

On commit the pre-commit hooks will attempt to ```FIX``` any issues. 

## Signing commits

The project has been set up to enforce signing commits, follow the [github signing-commits guide](https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits)

## WSL issues seen when committing
When working in a WSL environment you may experience some issues and messages that are not seen on a mac.

>### TLS issue on pre-commit
If you find the pre-commit fails with a message relating to TLS, check you have a `custom_ca_bundle.pem` in your home directory and if not follow the instructions here: [Manage CICA VPN SSL Certificates](https://dsdmoj.atlassian.net/wiki/spaces/CICA/pages/5882806404/CICA+set+up+instructions+for+WSL+for+windows#Manage-CICA-VPN-SSL-Certificates-within-your-Windows-Subsystem-for-Linux-environment)

>### Golang errors on pre-commit
If you find you are unable to commit and see an error like this:
```
An unexpected error has occurred: CalledProcessError: ...
...
go: downloading github...
...
golang-default/pkg/mod/...
...
```
You will need to add a `goproxy` to your environment.  Add this to your ~/.bashrc or ~/.zshrc (whichever one you're using):
```
export GOPROXY=https://goproxy.dev,direct
```
then run `source ~/.bashrc` or `source ~/.zshrc` to enable the setting.

>### Unable to enter signing pass-phrase
When running `git commit -S` in a terminal GPG tries to spawn pinentry but fails with this message: 
```
[GNUPG:] BEGIN_SIGNING H10
[GNUPG:] PINENTRY_LAUNCHED 226693 curses 1.2.1 - xterm-256color :0 - 1000/1000 -
gpg: signing failed: Inappropriate ioctl for device
[GNUPG:] FAILURE sign 83918950
gpg: signing failed: Inappropriate ioctl for device
```
The issue is caused by WSL's tty not being correctly defined which prevents this from running.

Add this to your ~/.bashrc or ~/.zshrc (whichever one you're using):
```
export GPG_TTY=$(tty)
```
then run `source ~/.bashrc` or `source ~/.zshrc` to enable the setting.


## Read about the GitHub repository standards

Familiarise yourself with the Ministry of Justice GitHub Repository Standards. These standards ensure consistency, maintainability, and best practices across all our repositories.

You can find the standards [here](https://github-community.service.justice.gov.uk/repository-standards/).


## Manage Outside Collaborators

To add an Outside Collaborator to the repository, follow the guidelines detailed [here](https://github.com/ministryofjustice/github-collaborators).

## Update CODEOWNERS

Modify the CODEOWNERS file to specify the teams or users authorized to approve pull requests.

