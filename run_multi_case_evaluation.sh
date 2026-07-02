#!/bin/bash
# Run the multi-case evaluation pipeline.
#
# Loads credentials from .env, starts the required Docker services, waits for
# them to be healthy, then executes the five-phase pipeline:
#   extract → ingest → expected chunks → evaluate → aggregate report
#
# Usage (from repo root):
#   ./run_multi_case_evaluation.sh [options]
#
# Options are forwarded to the Python script:
#   --cases 26-700001,26-700002   run a subset of cases (default: all 30)
#   --skip-extract                skip step 1 (CSVs already generated)
#   --skip-ingest                 skip step 2 (cases already indexed)
#   --output path/to/report.csv   override default output path
#
# Prerequisites (must be in place before running):
#   1. Docker Desktop running
#   2. .env file at the repo root populated with:
#        - AWS_MOD_PLATFORM_* credentials  (S3, Textract, Bedrock)
#        - OPENSEARCH_* settings
#        - USE_MOD_PLATFORM_MODE=true
#   3. local-dev-environment/.env populated with LocalStack settings
#      (this is used by docker-compose for the LocalStack container)
#
# The script starts opensearch and localstack from docker-compose automatically
# and waits up to 120 s for each to become healthy before proceeding.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="$SCRIPT_DIR/local-dev-environment/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/.env"

# ---------------------------------------------------------------------------
# Helper: wait for an HTTP endpoint to return a healthy response
# ---------------------------------------------------------------------------
wait_healthy() {
    local name="$1"
    local url="$2"
    local jq_filter="$3"   # python one-liner to extract status from JSON
    local max_attempts=24   # 24 × 5 s = 120 s
    echo "Waiting for $name to become healthy …"
    for i in $(seq 1 "$max_attempts"); do
        local status
        status=$(curl -sf "$url" 2>/dev/null \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print($jq_filter)" 2>/dev/null || true)
        if [[ "$status" == "green" || "$status" == "yellow" || "$status" == "running" ]]; then
            echo "  $name is healthy ($status)."
            return 0
        fi
        echo "  [$i/$max_attempts] $name not ready yet (status='$status') — retrying in 5 s …"
        sleep 5
    done
    echo "ERROR: $name did not become healthy within 120 s." >&2
    exit 1
}

# ---------------------------------------------------------------------------
# Start Docker services
# ---------------------------------------------------------------------------
echo "Starting opensearch and localstack …"
docker-compose -f "$COMPOSE" up -d opensearch localstack

wait_healthy "OpenSearch"  "http://localhost:9200/_cluster/health" \
    "d.get('status','?')"

wait_healthy "LocalStack"  "http://localhost:4566/_localstack/health" \
    "'running' if d.get('services', {}).get('s3') in ('running', 'available') else 'not_ready'"

# ---------------------------------------------------------------------------
# Load credentials and run the Python pipeline
# ---------------------------------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: credentials file not found at $ENV_FILE" >&2
    exit 1
fi

set -a
# Normalise spaces around = before sourcing (handles "KEY = value" syntax)
source <(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$' | sed 's/[[:space:]]*=[[:space:]]*/=/')
set +a

exec "$SCRIPT_DIR/.venv/bin/python" -m evaluation_suite.run_multi_case_evaluation "$@"
