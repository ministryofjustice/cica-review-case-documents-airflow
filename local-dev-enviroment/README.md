# Localstack local developer environment


Docker and LocalStack resorces to be created:

- [Localstack](https://www.localstack.cloud/)
- [OpenSearch](https://docs.localstack.cloud/aws/services/opensearch/) 
- [OpenSearch Dashboard](https://docs.opensearch.org/docs/latest/dashboards/)
- OpenSearch Domain:```case-document-search-domain```
- Opensearch Index:```case-documents```, [setup-opensearch.sh](./init-scripts/create-opensearch-resources.sh)
- AWS resources, [setup-aws-resources.sh](./init-scripts/create-aws-resources.sh)

## Pre-requisites

- [Docker](https://docs.docker.com/get-started/get-docker/)
- [LocalStack Desktop](https://docs.localstack.cloud/aws/capabilities/web-app/localstack-desktop/)

## Setup

Navigate into the local-dev-environment folder 

```cd cica-document-search-airflow/local-dev-enviroment```

and run

```docker compose up```

You should see 

```
:~/cica-document-search-airflow/local-dev-enviroment$ docker compose up -d --force-recreate
[+] Running 5/5
 ✔ Network local-dev-enviroment_default  Created                                             
 ✔ Volume "local-dev-enviroment_data01"  Created                                         
 ✔ Container opensearch                  Started                                             
 ✔ Container localstack-main             Healthy                                     
 ✔ Container opensearch-dashboards       Started   
```

View the localstack logs

```docker  logs localstack-main -f```

Look for 

```
Waiting for OpenSearch domain to be created...
2025-07-09T13:38:52.761  INFO --- [et.reactor-0] localstack.request.aws     : AWS opensearch.DescribeDomain => 200
        "Processing": false,
OpenSearch domain created.
2025-07-09T13:38:54.510  INFO --- [et.reactor-0] localstack.request.aws     : AWS opensearch.DescribeDomain => 200
DOMAIN_ENDPOINT: case-document-search-domain.eu-west-2.opensearch.localhost.localstack.cloud:4566
Waiting for OpenSearch to be ready...
```
There may be a short delay whilst the domain spins up then you should see


```
OpenSearch is ready! Creating index 'case-documents'...
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100  1168  100    73  100  1095    174   2610 --:--:-- --:--:-- --:--:--  2794
{"acknowledged":true,"shards_acknowledged":true,"index":"case-documents"}LocalStack resources configuration completed.
Ready.

```

The environment is then ready to be used and the domain enpoint should be: 
```case-document-search-domain.eu-west-2.opensearch.localhost.localstack.cloud:4566```

## Opensearch Dashboard

Navigate to http://127.0.0.1:5601/ to view the OpenSearch dashboard.

Navigate to [indices](http://127.0.0.1:5601/app/opensearch_index_management_dashboards#/indices?from=0&search=&showDataStreams=false&size=20&sortDirection=desc&sortField=index) to view the newly created index ```case-documents``` index.
