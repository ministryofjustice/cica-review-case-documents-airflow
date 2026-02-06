#!/bin/bash

set -a
source .env
set +a
rm debug.log
uv run src/ingestion_pipeline/runner.py > debug.log 2>&1

