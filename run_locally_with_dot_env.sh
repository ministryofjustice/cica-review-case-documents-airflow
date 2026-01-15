#!/bin/bash
# run_locally_with_dot_env.sh

# used for local development with uv and a .env file

set -a
source .env
set +a

uv run src/ingestion_pipeline/runner.py
