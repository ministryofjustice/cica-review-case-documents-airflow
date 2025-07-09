# Localstack local developer environment

Following these instructions shall create a Docker environment containg
[Localstack](https://www.localstack.cloud/), [OpenSearch](https://docs.localstack.cloud/aws/services/opensearch/) and [OpenSearch Dashboard](https://docs.opensearch.org/docs/latest/dashboards/).

An OpenSearch Domain:```case-document-search-domain``` and Opensearch Index:```case-documents``` shall also be created.

## Pre-requisites

- [Docker](https://docs.docker.com/get-started/get-docker/)

### Setup

Navigate into the local-dev-environment folder 

```cd cica-document-search-airflow/local-dev-enviroment```

```docker compose up```

You should see 

:~/cica-document-search-airflow/local-dev-enviroment$ docker compose up -d --force-recreate
[+] Running 5/5
 ✔ Network local-dev-enviroment_default  Created                                                                                          0.1s
 ✔ Volume "local-dev-enviroment_data01"  Created                                                                                          0.0s
 ✔ Container opensearch                  Started                                                                                          1.0s
 ✔ Container localstack-main             Healthy                                                                                         23.5s
 ✔ Container opensearch-dashboards       Started   


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

The environment is then ready to be used the domain enpoint should be: 
```case-document-search-domain.eu-west-2.opensearch.localhost.localstack.cloud:4566```
