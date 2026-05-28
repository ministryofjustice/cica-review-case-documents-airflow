#!/bin/bash

if [[ ! -f .env ]]; then
    echo "ERROR: .env file not found in the current directory."
    echo "Run setup-local-dev-wsl.sh from the repository root first."
    exit 1
fi

# Guard against unresolved template placeholders like KEY=<value>.
if grep -qE '^[A-Za-z_][A-Za-z0-9_]*=<[^>]+>$' .env; then
    echo "ERROR: .env contains unresolved template placeholders."
    echo "Replace placeholder values (e.g. <mod_platform_access_key_id>) and rerun."
    exit 1
fi

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
    timestamp=$(date +"%Y%m%d_%H%M%S")
    logfile="debug_${timestamp}.log"
    
    echo "Logging output to $logfile..."
    rm -f "$logfile"
    
    uv run src/ingestion_pipeline/runner.py > "$logfile" 2>&1
    
    echo "Complete. View output: cat $logfile"
else
    echo "Running with terminal output. Use --log-to-file to redirect to a timestamped log file"
    uv run src/ingestion_pipeline/runner.py
fi

