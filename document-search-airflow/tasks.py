# Example running in a terminal: invoke start-localstack

import subprocess

from invoke import task


# Start LocalStack in detached mode
@task(name="start-localstack")
def start_localstack(c):
    c.run("localstack start -d")


# End LocalStack
@task(name="stop-localstack")
def stop_localstack(c):
    c.run("localstack stop")


# Create an OpenSearch cluster
@task(name="create-opensearch-cluster")
def create_opensearch_cluster(c, name):
    c.run(f"awslocal opensearch create-domain --domain-name {name}")


# Create OpenSearch cluster using a json file
@task(name="create-opensearch-cluster-json")
def create_opensearch_cluster_json(c):
    """
    Create an OpenSearch domain in LocalStack using a json file.
    """
    c.run(
        "awslocal opensearch create-domain --cli-input-json file://./opensearch_domain.json"
    )


# Check the cluster health
@task(name="check-cluster-health")
def check_cluster_health(c, name):
    c.run(
        f"curl -s http://{name}.us-east-1.opensearch.localhost.localstack.cloud:4566/_cluster/health | jq ."
    )


# Check the secure cluster health
@task(name="check-secure-cluster-health")
def check_secure_cluster_health(c, name):
    c.run(
        f"curl -u 'admin:really-secure-passwordAa!1' http://{name}.us-east-1.opensearch.localhost.localstack.cloud:4566/_cluster/health | jq ."
    )


# Check OpenSearch Service cluster status
@task(name="check-cluster-status")
def check_cluster_status(c, name):
    c.run(f"awslocal opensearch describe-domain --domain-name {name}")


@task(name="get-localstack-ip")
def get_localstack_ip(c):
    """
    Get the IP address of the localstack-main container.
    Returns it as a string.
    """
    result = subprocess.run(
        ["docker", "inspect", "localstack-main"],
        capture_output=True,
        check=True,
    )
    inspect_json = result.stdout.decode("utf-8")

    ip_result = subprocess.run(
        [
            "jq",
            "-r",
            ".[0].NetworkSettings.Networks | to_entries | .[].value.IPAddress",
        ],
        input=inspect_json,
        capture_output=True,
        text=True,
        check=True,
    )

    ip = ip_result.stdout.strip()
    c.run(f"echo LocalStack IP: {ip}")
    return ip


@task(name="run-dashboards")
def run_dashboards(c):
    """
    Get IP from get_localstack_ip and start OpenSearch Dashboards.
    """
    # Call get_localstack_ip and pass context
    ip = get_localstack_ip(c)

    cmd = (
        "docker run --rm -p 5601:5601 "
        "--network ls "
        f"--dns {ip} "
        '-e "OPENSEARCH_HOSTS=http://secure-domain.us-east-1.opensearch.localhost.localstack.cloud:4566" '
        '-e "OPENSEARCH_USERNAME=admin" '
        '-e "OPENSEARCH_PASSWORD=really-secure-passwordAa!1" '
        "opensearchproject/opensearch-dashboards:2.11.0"
    )

    print("Starting OpenSearch Dashboards...")
    c.run(cmd, pty=True, shell=True)
