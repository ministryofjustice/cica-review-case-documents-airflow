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

See [Windows WSL setup](#windows-wsl-setup-instructions) instructions if developing on Windows

If using VSCode install the Microsoft Python extensions, Python Debugger, Python, Pylance, Python Environments

### Environment/package management

We recommend using [pyenv](https://pypi.org/project/pyenv/) to easily switch between multiple versions of Python.

This project uses the [UV](https://docs.astral.sh/uv/) for packaging and dependency management.

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

### Windows WSL setup instructions

Microsoft recommends developing Pyhon Apps using WSL.
[Windows WSL setup instructions](https://dsdmoj.atlassian.net/wiki/spaces/CICA/pages/5882806404/Set+up+instructions+for+WSL+for+windows)


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
- run ```uv run src/ingestion_pipeline/textract_processor.py```
- watch the terminal logs, note Textract can take from ~30 secs to ~2 mins to process
- once the pipeline has completed use the Opensearch dashboard to view the extracted data
  

### Testing the project

The project uses [pytest](https://docs.pytest.org/en/stable/) to run tests see [pytest.ini](`.pytest.ini`) for test configuration and [install pytest](https://docs.pytest.org/en/stable/getting-started.html#get-started)

To run the tests with coverage, coverage reports can be found under ```htmlcov/index.html```

```uv run pytest```

Alternatively and recommended use [VSCode Python Testing](https://code.visualstudio.com/docs/python/testing)

## Formatting

Install the [Ruff](https://astral.sh/) VSCode Extension, [ruff.toml](ruff.toml) holds the ruff configuration. 

## Signing commits

The project has been set up to enforce signing commits, follow the [github signing-commits guide](https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits)

## Read about the GitHub repository standards

Familiarise yourself with the Ministry of Justice GitHub Repository Standards. These standards ensure consistency, maintainability, and best practices across all our repositories.

You can find the standards [here](https://github-community.service.justice.gov.uk/repository-standards/).


## Manage Outside Collaborators

To add an Outside Collaborator to the repository, follow the guidelines detailed [here](https://github.com/ministryofjustice/github-collaborators).

## Update CODEOWNERS

Modify the CODEOWNERS file to specify the teams or users authorized to approve pull requests.

