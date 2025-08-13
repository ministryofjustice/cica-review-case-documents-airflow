# Document ingestion code for the document search airflow DAG

## Pre-requisites

- Follow instructions in the README inside `local-dev-environment` to spin up the Local Stack environement.
- Install Poetry using instructions [here](https://python-poetry.org/docs/#installation)

## Setup

To install the project dependencies, run in the terminal from the root folder:

```poetry install```

## Document ingestion

The code inside `src/ingestion_code` will:
- Extract text from a pdf (with text) stored in a root level folder whose name is defined by the `DATA_DIR` variable.
- Split the text into chunks.
- Embed the chunks with an embedding model.
- Insert the chunks (documents) into an OpenSearch index.

To run the whole process, first activate the virtual environment:

```source .venv/bin/activate```

Ensure a `.env` file exists in the root of the repo with the correct AWS credentials copied in.

Then run in the terminal from the root folder:

```python -m ingestion_code```

Logs will be written to a local log file at root level `ingestion.log`.

Secrets and environement variables should be defined in a `.env` file. These and other configuration is stored in a `settings` object defined in `src/ingestion_code/config.py`.

## Testing

To run unit tests with `pytest`, run in the terminal from the root folder:

```pytest```

To get a test coverage report, run:

```pytest --cov=ingestion_code```

To generate interactive HTML report, run:

```pytest --cov=ingestion_code --cov-report=html```
