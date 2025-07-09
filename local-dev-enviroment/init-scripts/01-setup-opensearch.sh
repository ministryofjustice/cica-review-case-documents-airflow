#!/bin/bash

# Create an OpenSearch domain
awslocal opensearch create-domain --cli-input-json file:///etc/localstack/init/ready.d/opensearch_domain.json

# Wait for the domain to become active
echo "Waiting for OpenSearch domain to be created..."
until awslocal opensearch describe-domain --domain-name case-document-search-domain | grep '"Processing": false'; do
  sleep 5
done
echo "OpenSearch domain created."

# Create an index in the domain
DOMAIN_ENDPOINT=$(awslocal opensearch describe-domain --domain-name case-document-search-domain | grep -o '"Endpoint": "[^"]*' | grep -o '[^"]*$')
echo "DOMAIN_ENDPOINT: ${DOMAIN_ENDPOINT}"


DIRECT_OPENSEARCH_ENDPOINT="opensearch:9200"

echo "Waiting for OpenSearch to be ready..."

# Loop until the OpenSearch health endpoint returns a successful status
# We use curl's --silent and --fail flags. 
# --fail causes curl to return a non-zero exit code on server errors (like 404 or 503),
# which is perfect for this check.
until curl --silent --fail -u 'admin:really-secure-passwordAa!1' "http://${DIRECT_OPENSEARCH_ENDPOINT}/_cluster/health" > /dev/null; do
    printf '.'
    sleep 2
done

INDEX_NAME="case-documents"

echo -e "\nOpenSearch is ready! Creating index '${INDEX_NAME}'..."

# To change the embedding model, you can modify the "dimension" field in the index settings.    
# For example, if you are using a different embedding model with a different dimension size, update it accordingly.
curl -XPUT -u 'admin:really-secure-passwordAa!1' "http://${DIRECT_OPENSEARCH_ENDPOINT}/${INDEX_NAME}" -H 'Content-Type: application/json' -d'
{
    "settings": {
        "index": {
            "knn": true,
            "knn.algo_param.ef_search": 100
        }
    },
    "mappings": {
        "properties": {
            "embedding": {
                "type": "knn_vector",
                "dimension": 384,
                "method": {
                    "name": "hnsw",
                    "space_type": "l2",
                    "engine": "nmslib",
                    "parameters": {
                        "ef_construction": 128,
                        "m": 24
                    }
                }
            },
            "s3_uri": {"type": "keyword"},
            "case_ref": {"type": "keyword"},
            "correspondence_type": {"type": "keyword"},
            "page_count": {"type": "integer"},
            "page_number": {"type": "integer"},
            "chunk_id": {"type": "keyword"},
            "chunk_text": {"type": "text", "index": false},
            "received_date": {
                "type": "date",
                "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd||epoch_millis"
            }
        }
    }
}
' || echo "Warning: Failed to create OpenSearch index"

echo "LocalStack resources configuration completed."
