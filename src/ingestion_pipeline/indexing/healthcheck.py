"""OpenSearch health check utility."""

import logging
import time
from urllib.parse import urlparse

from opensearchpy import ConnectionError, OpenSearch

logger = logging.getLogger(__name__)


def check_opensearch_health(proxy_url: str, timeout: int = 10, interval: float = 1.0) -> bool:
    """Checks the health of the OpenSearch cluster at the given proxy URL.

    Retries until healthy or timeout is reached.

    Args:
        proxy_url (str): The OpenSearch proxy/base URL.
        timeout (int): Maximum seconds to wait for health.
        interval (float): Seconds between retries.

    Returns:
        bool: True if healthy, False otherwise.
    """
    parsed = urlparse(proxy_url)
    host_entry = {
        "host": parsed.hostname,
        "port": parsed.port or (443 if parsed.scheme == "https" else 80),
        "scheme": parsed.scheme,
    }
    hosts = [host_entry]
    client = OpenSearch(
        hosts=hosts,
        http_auth=(),
        use_ssl=host_entry["scheme"] == "https",
        verify_certs=False,
        ssl_assert_hostname=False,
        timeout=1,  # Match interval to allow multiple retries within timeout budget
        max_retries=0,
        retry_on_timeout=False,
    )
    start = time.time()
    attempts = 0
    last_status = None
    last_error: Exception | None = None

    while time.time() - start < timeout:
        attempts += 1
        try:
            health = client.cluster.health()
            status = health.get("status")
            if status in ("green", "yellow"):
                logger.info(f"OpenSearch health check passed: status={status}, attempts={attempts}")
                return True
            last_status = status
            last_error = None
        except ConnectionError as e:
            last_error = e
        except Exception as e:
            last_error = e
        time.sleep(interval)

    elapsed = time.time() - start
    if last_error is not None:
        logger.error(
            "OpenSearch health check failed after %s attempts over %.2f seconds: %s",
            attempts,
            elapsed,
            last_error,
        )
    else:
        logger.error(
            "OpenSearch health check failed after %s attempts over %.2f seconds: status=%s",
            attempts,
            elapsed,
            last_status,
        )
    return False
