# Document ingestion code for the document search airflow DAG

## Pre-requisites

- Follow instructions in the README inside `local-dev-environment`.
- Install Poetry using instructions [here](https://python-poetry.org/docs/#installation)

## Setup

To install the project dependencies, run in the terminal from the root folder:

```poetry install```

## Document ingestion

The code inside `src/ingestion_code` will:
- Extract text from a pdf with text.
- Split the text into chunks.
- Embed the chunks with a local embedding model.
- Insert the chunks (documents) into an OpenSearch index.

To run the whole process, run in the terminal from the root folder:

```python -m ingestion_code```

Logs will be written to a local log file at root level `ingestion.log`.

Configuration settings and secrets should be stored in a `.env` file.

## Testing

To run unit tests with `pytest`, run in the terminal from the root folder:

```pytest```

To get a test coverage report, run:

```pytest --cov=ingestion_code```

To generate interactive HTML report, run:

```pytest --cov=ingestion_code --cov-report=html```
