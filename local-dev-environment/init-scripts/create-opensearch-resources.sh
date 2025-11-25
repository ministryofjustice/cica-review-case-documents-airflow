#!/bin/bash
set -euo pipefail

echo "Starting OpenSearch index setup..."

# With OPENSEARCH_ENDPOINT_STRATEGY=path, LocalStack provides a direct proxy.
# This script now interacts directly with the OpenSearch container, bypassing
# the need to create a LocalStack-managed AWS OpenSearch domain.
DIRECT_OPENSEARCH_ENDPOINT="http://opensearch:9200"

# --- Step 1: Wait for the OpenSearch container to be ready ---
echo "Waiting for OpenSearch container at ${DIRECT_OPENSEARCH_ENDPOINT} to be ready..."
# In the compose file, DISABLE_SECURITY_PLUGIN=true, so we don't need auth.
until curl --silent --fail "${DIRECT_OPENSEARCH_ENDPOINT}/_cluster/health?wait_for_status=yellow" > /dev/null; do
    echo -n "."
    sleep 5
done
echo -e "\nOpenSearch container is ready!"

# --- Step 2: Create the index directly in the OpenSearch container ---
INDEX_NAME="page_chunks"
# No auth needed due to DISABLE_SECURITY_PLUGIN=true
if curl --silent --fail -I "${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" > /dev/null; then
  echo "Index '${INDEX_NAME}' already exists. Skipping creation."
else
  echo "Creating index '${INDEX_NAME}'..."
  CREATE_RESPONSE=$(curl -s -XPUT "${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" -H 'Content-Type: application/json' --data-binary @- <<EOF
{
    "settings": {
        "index.knn": true
    },
    "mappings": {
        "properties": {
            "chunk_id": {
                "type": "keyword"
            },
            "source_doc_id": {
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
                "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||epoch_millis||yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
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
                "properties": {
                    "bounding_box": {
                        "properties": {
                            "top": {
                                "type": "float"
                            },
                            "left": {
                                "type": "float"
                            },
                            "width": {
                                "type": "float"
                            },
                            "height": {
                                "type": "float"
                            }
                        }
                    }
                }
            }
        }
    }
}
EOF
)
  echo "Index creation response: ${CREATE_RESPONSE}"
  if [[ ! $(echo "${CREATE_RESPONSE}" | grep '"acknowledged":true') ]]; then
    echo "Error: Index creation not acknowledged."
    exit 1
  fi
fi

echo "Signaling that OpenSearch index is ready."
touch /tmp/opensearch_index_ready

echo "OpenSearch setup complete."
