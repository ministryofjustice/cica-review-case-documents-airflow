#!/bin/bash

set -a
source .env
set +a

# Pre-flight: verify OpenSearch is reachable before starting the pipeline.
# kubectl port-forward sessions drop silently after inactivity — this catches
# a stale tunnel early and gives a clear message instead of 10s of timeouts.
OPENSEARCH_URL="${OPENSEARCH_PROXY_URL:-http://localhost:9200}"
OPENSEARCH_HOST=$(echo "$OPENSEARCH_URL" | sed 's|http[s]*://||' | cut -d: -f1)
OPENSEARCH_PORT=$(echo "$OPENSEARCH_URL" | sed 's|http[s]*://||' | cut -d: -f2 | cut -d/ -f1)

if ! curl --silent --fail --max-time 3 "${OPENSEARCH_URL}" > /dev/null 2>&1; then
    echo ""
    echo "ERROR: Cannot reach OpenSearch at ${OPENSEARCH_URL}"
    echo ""
    echo "  Port-forward may have dropped. Restart it with:"
    echo "    kubectl port-forward service/opensearch-proxy-service-cloud-platform-5b4b8d7c ${OPENSEARCH_PORT}:8080 --namespace cica-review-case-documents-dev"
    echo ""
    exit 1
fi

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

