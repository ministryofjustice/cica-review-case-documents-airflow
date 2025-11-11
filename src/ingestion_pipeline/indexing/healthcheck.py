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
    )
    start = time.time()
    while time.time() - start < timeout:
        try:
            health = client.cluster.health()
            status = health.get("status")
            if status in ("green", "yellow"):
                logger.info(f"OpenSearch health check passed: status={status}")
                return True
            else:
                logger.warning(f"OpenSearch unhealthy: status={status}")
        except ConnectionError as e:
            logger.warning(f"OpenSearch not reachable: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during OpenSearch health check: {e}")
        time.sleep(interval)
    logger.error("OpenSearch health check failed: timeout reached.")
    return False
