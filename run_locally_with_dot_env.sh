#!/bin/bash

set -a
source .env
set +a
uv run src/ingestion_pipeline/runner.py

