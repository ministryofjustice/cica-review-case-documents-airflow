"""OpenSearch health check utility."""

import logging
import time
from urllib.parse import urlparse

from opensearchpy import ConnectionError, OpenSearch

logger = logging.getLogger(__name__)


def check_opensearch_health(
    proxy_url: str,
    timeout_seconds: int = 10,
    interval_seconds: float = 1.0,
    verify_certs: bool = True,
    ssl_assert_hostname: bool = True,
) -> bool:
    """Checks the health of the OpenSearch cluster at the given proxy URL.

    Retries until healthy or timeout is reached.

    All timeout values are expressed in seconds.

    Defaults:
        - timeout_seconds=10 sets the overall health-check time budget.
        - interval_seconds=1.0 controls retry cadence and caps per-request timeout.
        - each cluster.health call uses request_timeout=min(interval_seconds, remaining budget).

    Args:
        proxy_url (str): The OpenSearch proxy/base URL.
        timeout_seconds (int): Maximum seconds to wait for health.
        interval_seconds (float): Seconds between retries.
        verify_certs (bool): Whether to verify TLS certificates. Defaults to True.
            Set to False only for development environments with self-signed certificates.
        ssl_assert_hostname (bool): Whether to assert the hostname in TLS certificates. Defaults to True.
            Set to False only for development environments with self-signed certificates.

    Returns:
        bool: True if healthy, False otherwise.

    Notes:
       - This function performs a connectivity/health check against the configured OpenSearch endpoint.
       - It does not manage application credentials directly.
       - TLS behavior is configurable via verify_certs and ssl_assert_hostname.
       - Authentication and authorization must be configured and enforced outside this function.
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
        verify_certs=verify_certs,
        ssl_assert_hostname=ssl_assert_hostname,
        timeout=min(interval_seconds, timeout_seconds),
        max_retries=0,
        retry_on_timeout=False,
    )
    start = time.monotonic()
    attempts = 0
    last_status = None
    last_error: Exception | None = None

    while True:
        elapsed_seconds = time.monotonic() - start
        if elapsed_seconds >= timeout_seconds:
            break

        remaining_budget_seconds = timeout_seconds - elapsed_seconds
        request_timeout_seconds = max(0.001, min(interval_seconds, remaining_budget_seconds))

        attempts += 1
        try:
            health = client.cluster.health(request_timeout=request_timeout_seconds)
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

        # Sleep only for the time remaining in the timeout budget (recalculate after attempt)
        elapsed_seconds = time.monotonic() - start
        remaining_budget_seconds = timeout_seconds - elapsed_seconds
        sleep_duration = min(interval_seconds, remaining_budget_seconds)
        if sleep_duration > 0:
            time.sleep(sleep_duration)

    elapsed = time.monotonic() - start
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
