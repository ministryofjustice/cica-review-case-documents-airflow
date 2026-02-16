#!/bin/bash

set -a
source .env
set +a

# Check if --log-to-file flag is provided
if [[ "$1" == "--log-to-file" ]]; then
    echo "Logging output to debug.log..."
    rm -f debug.log
    uv run src/ingestion_pipeline/runner.py > debug.log 2>&1
    echo "Complete. View output: cat debug.log"
else
    echo "Running with terminal output. Use --log-to-file to redirect to debug.log"
    uv run src/ingestion_pipeline/runner.py
fi

