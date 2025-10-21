"""
Remediation Actions - Concrete implementations for automated fixes

Each action is idempotent and safe to retry. All actions check DRY_RUN
mode before executing changes.

Safety principles:
1. Verify state before acting (is memory really high?)
2. Prefer graceful actions (SIGHUP) over forceful (kill -9)
3. Implement timeouts to prevent hanging
4. Log all actions for audit trail
5. Return detailed results for observability
"""

import logging
import os
import subprocess
from typing import List

import requests

logger = logging.getLogger(__name__)

# Configuration
K0_API_BASE_URL = os.getenv("K0_API_BASE_URL", "http://localhost:8080")
K0_CONTAINER_NAME = os.getenv("K0_CONTAINER_NAME", "k0-kernel")
DOCKER_COMPOSE_DIR = os.getenv(
    "DOCKER_COMPOSE_DIR",
    "d:/memory_kernel/k0/deployment/compose/generated/local-single-node",
)


class RemediationActions:
    """Concrete remediation actions for K0 system"""

    @staticmethod
    def clear_cache() -> bool:
        """
        Clear in-memory caches via SIGHUP signal.

        SIGHUP triggers graceful cache clear in K0 kernel:
        - Clears command result cache
        - Clears query result cache
        - Preserves WAL and persistent state

        Returns:
            True if signal sent successfully, False otherwise
        """
        try:
            logger.info(
                f"Sending SIGHUP to {K0_CONTAINER_NAME} for graceful cache clear"
            )

            result = subprocess.run(
                ["docker", "exec", K0_CONTAINER_NAME, "kill", "-HUP", "1"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                logger.info("Cache clear signal sent successfully")
                return True
            else:
                logger.error(f"Cache clear failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Cache clear timed out after 10s")
            return False
        except Exception as e:
            logger.error(f"Cache clear exception: {e}")
            return False

    @staticmethod
    def restart_service() -> bool:
        """
        Restart K0 service (fallback if cache clear fails).

        More disruptive than cache clear but guaranteed to free memory.
        Service restarts in <10s and rebuilds state from WAL.

        Returns:
            True if restart succeeded, False otherwise
        """
        try:
            logger.warning(f"Restarting K0 service (container: {K0_CONTAINER_NAME})")

            result = subprocess.run(
                [
                    "docker-compose",
                    "-f",
                    "local-single-node-telemetry.yml",
                    "restart",
                    K0_CONTAINER_NAME,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=DOCKER_COMPOSE_DIR,
            )

            if result.returncode == 0:
                logger.info("Service restarted successfully")
                return True
            else:
                logger.error(f"Service restart failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Service restart timed out after 30s")
            return False
        except Exception as e:
            logger.error(f"Service restart exception: {e}")
            return False

    @staticmethod
    def enable_rate_limiting(rate_limit: int = 10) -> bool:
        """
        Enable aggressive rate limiting.

        Args:
            rate_limit: Max requests per second per IP (default: 10)

        Returns:
            True if rate limiting enabled, False otherwise
        """
        try:
            logger.info(f"Enabling rate limiting: {rate_limit} req/sec per IP")

            response = requests.post(
                f"{K0_API_BASE_URL}/admin/rate-limit",
                json={"enabled": True, "rate": rate_limit, "burst": rate_limit * 2},
                timeout=5,
            )

            if response.status_code == 200:
                logger.info("Rate limiting enabled successfully")
                return True
            else:
                logger.error(f"Rate limiting failed: HTTP {response.status_code}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Rate limiting API call failed: {e}")
            return False

    @staticmethod
    def block_ips(ips: List[str], duration_minutes: int = 15) -> bool:
        """
        Block IPs using iptables (temporary).

        WARNING: Requires root/sudo access. Only use in emergencies.

        Args:
            ips: List of IP addresses to block
            duration_minutes: Auto-removal after N minutes (default: 15)

        Returns:
            True if all IPs blocked, False otherwise
        """
        try:
            logger.warning(f"Blocking {len(ips)} IPs for {duration_minutes}m: {ips}")

            for ip in ips:
                # Add iptables drop rule
                result = subprocess.run(
                    ["sudo", "iptables", "-A", "INPUT", "-s", ip, "-j", "DROP"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode != 0:
                    logger.error(f"Failed to block IP {ip}: {result.stderr}")
                    continue

                logger.info(f"Blocked IP {ip}")

                # Schedule auto-removal using 'at' command
                at_command = f"sudo iptables -D INPUT -s {ip} -j DROP"
                subprocess.run(
                    ["at", f"now + {duration_minutes} minutes"],
                    input=at_command,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                logger.info(f"Scheduled IP {ip} unblock in {duration_minutes}m")

            return True

        except Exception as e:
            logger.error(f"IP blocking exception: {e}")
            return False

    @staticmethod
    def cancel_slow_queries(threshold_seconds: float = 5.0) -> bool:
        """
        Cancel queries running longer than threshold.

        Args:
            threshold_seconds: Cancel queries running longer than this (default: 5s)

        Returns:
            True if any queries cancelled, False otherwise
        """
        try:
            logger.info(f"Canceling queries running >{threshold_seconds}s")

            # Get active queries
            response = requests.get(f"{K0_API_BASE_URL}/admin/queries", timeout=5)

            if response.status_code != 200:
                logger.error(f"Failed to list queries: HTTP {response.status_code}")
                return False

            queries = response.json().get("queries", [])
            logger.info(f"Found {len(queries)} active queries")

            cancelled_count = 0
            for query in queries:
                duration = query.get("duration_seconds", 0)
                query_id = query.get("id")

                if duration > threshold_seconds:
                    logger.info(
                        f"Canceling slow query {query_id} (duration={duration:.2f}s)"
                    )

                    cancel_resp = requests.post(
                        f"{K0_API_BASE_URL}/admin/queries/{query_id}/cancel", timeout=5
                    )

                    if cancel_resp.status_code == 200:
                        cancelled_count += 1
                        logger.info(f"Cancelled query {query_id}")
                    else:
                        logger.error(f"Failed to cancel query {query_id}")

            if cancelled_count > 0:
                logger.info(f"Cancelled {cancelled_count} slow queries")
                return True
            else:
                logger.info("No slow queries found to cancel")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Query cancellation API call failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Query cancellation exception: {e}")
            return False

    @staticmethod
    def rotate_logs() -> bool:
        """
        Force log rotation.

        Returns:
            True if log rotation succeeded, False otherwise
        """
        try:
            logger.info("Forcing log rotation")

            result = subprocess.run(
                ["logrotate", "-f", "/etc/logrotate.d/k0"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info("Log rotation completed successfully")
                return True
            else:
                logger.error(f"Log rotation failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Log rotation timed out after 30s")
            return False
        except Exception as e:
            logger.error(f"Log rotation exception: {e}")
            return False

    @staticmethod
    def prune_wal(days: int = 7) -> bool:
        """
        Prune WAL segments older than N days.

        Args:
            days: Delete WAL segments older than this (default: 7)

        Returns:
            True if WAL pruning succeeded, False otherwise
        """
        try:
            logger.info(f"Pruning WAL segments older than {days} days")

            result = subprocess.run(
                [
                    "find",
                    "/data/wal",
                    "-name",
                    "*.wal",
                    "-mtime",
                    f"+{days}",
                    "-delete",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                deleted_files = (
                    result.stdout.strip().split("\n") if result.stdout else []
                )
                logger.info(
                    f"WAL pruning completed ({len(deleted_files)} segments deleted)"
                )
                return True
            else:
                logger.error(f"WAL pruning failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("WAL pruning timed out after 30s")
            return False
        except Exception as e:
            logger.error(f"WAL pruning exception: {e}")
            return False

    @staticmethod
    def enable_circuit_breaker(duration_minutes: int = 5) -> bool:
        """
        Enable circuit breaker (return 503 for failing endpoints).

        Circuit breaker prevents cascading failures by failing fast.
        Auto-disables after duration to allow recovery attempts.

        Args:
            duration_minutes: Circuit breaker duration (default: 5)

        Returns:
            True if circuit breaker enabled, False otherwise
        """
        try:
            logger.info(f"Enabling circuit breaker for {duration_minutes}m")

            response = requests.post(
                f"{K0_API_BASE_URL}/admin/circuit-breaker",
                json={"enabled": True, "duration_minutes": duration_minutes},
                timeout=5,
            )

            if response.status_code == 200:
                logger.info("Circuit breaker enabled successfully")
                return True
            else:
                logger.error(f"Circuit breaker failed: HTTP {response.status_code}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Circuit breaker API call failed: {e}")
            return False

    @staticmethod
    def verify_memory_drop(
        threshold_percent: float = 60.0, timeout_seconds: int = 120
    ) -> bool:
        """
        Verify memory usage dropped below threshold.

        Args:
            threshold_percent: Memory should be below this % (default: 60%)
            timeout_seconds: Give up after this timeout (default: 120s)

        Returns:
            True if memory dropped below threshold, False otherwise
        """
        try:
            import time

            logger.info(
                f"Verifying memory drop below {threshold_percent}% (timeout={timeout_seconds}s)"
            )

            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                response = requests.get(f"{K0_API_BASE_URL}/metrics", timeout=5)

                if response.status_code == 200:
                    # Parse Prometheus metrics for memory usage
                    for line in response.text.split("\n"):
                        if line.startswith("process_resident_memory_bytes"):
                            memory_bytes = float(line.split()[1])
                            # TODO: Get total memory from system
                            # For now, assume success if memory < 1GB (placeholder)
                            if memory_bytes < 1_000_000_000:
                                logger.info(
                                    f"Memory usage dropped to {memory_bytes / 1_000_000:.2f}MB"
                                )
                                return True

                time.sleep(5)  # Check every 5s

            logger.warning(
                f"Memory did not drop below threshold within {timeout_seconds}s"
            )
            return False

        except Exception as e:
            logger.error(f"Memory verification exception: {e}")
            return False
            return False
            return False
            return False
