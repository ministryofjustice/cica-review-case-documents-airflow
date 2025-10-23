#!/bin/bash
set -euo pipefail

echo "Starting LocalStack OpenSearch domain and index setup..."

LOCALSTACK_OPENSEARCH_DOMAIN_NAME="case-document-search-domain"
DIRECT_OPENSEARCH_ENDPOINT="opensearch:9200"
OPENSEARCH_AUTH="admin:really-secure-passwordAa!1"

# --- Step 1: Create the OpenSearch domain within LocalStack ---
echo "Creating LocalStack OpenSearch domain '${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}'..."
if awslocal opensearch describe-domain --domain-name "${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}" 2>/dev/null; then
  echo "LocalStack OpenSearch domain '${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}' already exists."
else
  awslocal opensearch create-domain --cli-input-json file:///etc/localstack/init/ready.d/opensearch_domain.json
  echo "LocalStack OpenSearch domain creation initiated."
fi

# --- Step 2: Wait for the LocalStack-managed domain to become active ---
echo "Waiting for LocalStack OpenSearch domain '${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}' to be active..."
until awslocal opensearch describe-domain --domain-name "${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}" | grep '"Processing": false' > /dev/null; do
  echo -n "."
  sleep 5
done
echo -e "\nLocalStack OpenSearch domain '${LOCALSTACK_OPENSEARCH_DOMAIN_NAME}' is active."

# --- Step 3: Wait for the actual OpenSearch container to be ready ---
echo "Waiting for actual OpenSearch container at ${DIRECT_OPENSEARCH_ENDPOINT} to be ready..."
until curl --silent --fail -u "${OPENSEARCH_AUTH}" "http://${DIRECT_OPENSEARCH_ENDPOINT}/_cluster/health" > /dev/null; do
    echo -n "."
    sleep 2
done
echo -e "\nActual OpenSearch container is ready!"

# --- Step 4: Create the index in the actual OpenSearch container ---
INDEX_NAME="page_chunks"
if curl --silent --fail -u "${OPENSEARCH_AUTH}" "http://${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" > /dev/null; then
  echo "Index '${INDEX_NAME}' already exists. Skipping creation."
else
  echo "Creating index '${INDEX_NAME}'..."
  CREATE_RESPONSE=$(curl -s -XPUT -u "${OPENSEARCH_AUTH}" "http://${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" -H 'Content-Type: application/json' --data-binary @- <<EOF
{
    "settings": {
        "index.knn": true
    },
    "mappings": {
        "properties": {
            "chunk_id": {
                "type": "keyword"
            },
            "document_id": {
                "type": "keyword"
            },
            "chunk_text": {
                "type": "text"
            },
            "embedding": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "faiss",
                    "parameters": {
                        "ef_construction": 128,
                        "m": 24
                    }
                }
            },
            "source_file_name": {
                "type": "keyword"
            },
            "page_id": {
                "type": "keyword",
                "index": false
            },
            "case_ref": {
                "type": "keyword"
            },
            "correspondence_type": {
                "type": "keyword"
            },
            "received_date": {
                "type": "date",
                "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||epoch_millis"
            },
            "page_count": {
                "type": "integer"
            },
            "page_number": {
                "type": "integer"
            },
            "chunk_index": {
                "type": "integer"
            },
            "chunk_type": {
                "type": "keyword"
            },
            "confidence": {
                "type": "float"
            },
            "geometry": {
                "type": "object",
                "enabled": false
            }
        }
    }
}
EOF
)

  if echo "${CREATE_RESPONSE}" | grep -q '"acknowledged":true'; then
    echo "Index '${INDEX_NAME}' created successfully."
  else
    echo "Failed to create index '${INDEX_NAME}'. Response: ${CREATE_RESPONSE}"
    exit 1
  fi
fi

# --- Step 5: Create the search pipeline ---
PIPELINE_NAME="hybrid-search-pipeline"
if curl --silent --fail -u "${OPENSEARCH_AUTH}" "http://${DIRECT_OPENSEARCH_ENDPOINT}/_search/pipeline/${PIPELINE_NAME}" > /dev/null; then
  echo "Pipeline '${PIPELINE_NAME}' already exists. Skipping creation."
else
  echo "Creating Pipeline '${PIPELINE_NAME}'..."
  CREATE_PIPELINE=$(curl -s -XPUT -u "${OPENSEARCH_AUTH}" "http://${DIRECT_OPENSEARCH_ENDPOINT}/_search/pipeline/${PIPELINE_NAME}" -H 'Content-Type: application/json' --data-binary @- <<EOF
{
  "description": "Pipeline for combining k-NN and BM25 scores",
  "phase_results_processors": [
    {
      "normalization-processor": {
        "normalization": {
          "technique": "min_max"
        },
        "combination": {
          "technique": "arithmetic_mean",
          "parameters": {
            "weights": [0.5, 0.5]
          }
        }
      }
    }
  ]
}
EOF
)

  if echo "${CREATE_PIPELINE}" | grep -q '"acknowledged":true'; then
    echo "Pipeline '${PIPELINE_NAME}' created successfully."
  else
    echo "Failed to create pipeline '${PIPELINE_NAME}'. Response: ${CREATE_PIPELINE}"
    exit 1
  fi
fi

# --- Step 6: Create the page index in the OpenSearch container ---
INDEX_NAME="page_metadata"
if curl --silent --fail -u "${OPENSEARCH_AUTH}" "http://${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" > /dev/null; then
  echo "Index '${INDEX_NAME}' already exists. Skipping creation."
else
  echo "Creating index '${INDEX_NAME}'..."
  CREATE_RESPONSE=$(curl -s -XPUT -u "${OPENSEARCH_AUTH}" "http://${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" -H 'Content-Type: application/json' --data-binary @- <<EOF
{
    
    "mappings": {
        "properties": {
            "page_id": {
                "type": "keyword"
            },
            "document_id": {
                "type": "keyword"
            },
            "page_text": {
                "type": "keyword",
                "index": false
            },
            "source_file_name": {
                "type": "keyword",
                "index": false
            },
            "s3_page_image_uri": {
                "type": "keyword",
                "index": false
            },
            "case_ref": {
                "type": "keyword",
                "index": false
            },
            "correspondence_type": {
                "type": "keyword",
                "index": false
            },
            "received_date": {
                "type": "date",
                "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||epoch_millis",
                "index": false
            },
            "page_count": {
                "type": "integer",
                "index": false
            },
            "page_number": {
                "type": "integer",
                "index": false
            },
            "geometry": {
                "type": "object",
                "enabled": false
            }
        }
    }
}
EOF
)

  if echo "${CREATE_RESPONSE}" | grep -q '"acknowledged":true'; then
    echo "Index '${INDEX_NAME}' created successfully."
  else
    echo "Failed to create index '${INDEX_NAME}'. Response: ${CREATE_RESPONSE}"
    exit 1
  fi
fi

# --- Step 7: Create a marker file for the LocalStack health check ---
touch /tmp/opensearch_index_ready
echo "LocalStack OpenSearch Domain and Index resources completed successfully."
