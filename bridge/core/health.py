"""K0 health checking and degraded mode management.

E-2.6: Offline awareness for the Bridge layer.

K0AvailabilityStatus — enum: ONLINE / DEGRADED / OFFLINE
K0HealthChecker      — periodic /healthz ping with circuit breaker
DegradedModeManager  — policy engine for offline behaviour

Degradation policy:
  ONLINE   → all ports operate normally
  DEGRADED → Query uses extended timeout, Obs drops LOW priority
  OFFLINE  → Command→LocalOutbox, Query→empty, SSE→reconnect loop,
             Obs→drop LOW, IFL→NotImplementedError (already)
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Availability status
# ---------------------------------------------------------------------------


class K0AvailabilityStatus(enum.Enum):
    """K0 reachability state as observed by the Bridge."""

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


# ---------------------------------------------------------------------------
# Health snapshot
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class K0HealthSnapshot:
    """Point-in-time K0 health observation.

    Attributes:
        status: Current availability status.
        last_success_ns: Monotonic ns of last successful health check.
        last_failure_ns: Monotonic ns of last failed health check.
        consecutive_failures: Number of consecutive health check failures.
        latency_ms: Last observed round-trip latency to K0.
        error_message: Last error message (empty when healthy).
    """

    status: K0AvailabilityStatus = K0AvailabilityStatus.OFFLINE
    last_success_ns: int = 0
    last_failure_ns: int = 0
    consecutive_failures: int = 0
    latency_ms: int = 0
    error_message: str = ""


# ---------------------------------------------------------------------------
# Health checker
# ---------------------------------------------------------------------------


class K0HealthChecker:
    """Periodic K0 health checker.

    Pings K0 ``/healthz`` endpoint and tracks availability transitions.
    Does NOT own the polling loop — the caller (BridgeClient or kernel)
    drives ``check_once()`` on its own schedule (e.g. every 30s).

    Thresholds:
        ONLINE→DEGRADED:  latency_ms > degraded_threshold_ms
        ONLINE→OFFLINE:   consecutive_failures >= failure_threshold
        DEGRADED→OFFLINE: consecutive_failures >= failure_threshold
        OFFLINE→ONLINE:   1 successful health check
        DEGRADED→ONLINE:  latency_ms <= degraded_threshold_ms

    Parameters:
        failure_threshold: Consecutive failures before OFFLINE.
        degraded_threshold_ms: Latency above this = DEGRADED.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        degraded_threshold_ms: int = 2000,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._degraded_threshold_ms = degraded_threshold_ms
        self._snapshot = K0HealthSnapshot()

    @property
    def snapshot(self) -> K0HealthSnapshot:
        """Current health snapshot (read-only copy)."""
        return K0HealthSnapshot(
            status=self._snapshot.status,
            last_success_ns=self._snapshot.last_success_ns,
            last_failure_ns=self._snapshot.last_failure_ns,
            consecutive_failures=self._snapshot.consecutive_failures,
            latency_ms=self._snapshot.latency_ms,
            error_message=self._snapshot.error_message,
        )

    @property
    def status(self) -> K0AvailabilityStatus:
        """Current availability status."""
        return self._snapshot.status

    def record_success(self, latency_ms: int) -> K0AvailabilityStatus:
        """Record a successful health check.

        Args:
            latency_ms: Round-trip latency in ms.

        Returns:
            New availability status after this observation.
        """
        now = time.monotonic_ns()
        self._snapshot.last_success_ns = now
        self._snapshot.consecutive_failures = 0
        self._snapshot.latency_ms = latency_ms
        self._snapshot.error_message = ""

        if latency_ms > self._degraded_threshold_ms:
            old = self._snapshot.status
            self._snapshot.status = K0AvailabilityStatus.DEGRADED
            if old != K0AvailabilityStatus.DEGRADED:
                logger.warning(
                    "K0 health: %s → DEGRADED (latency=%dms > %dms)",
                    old.value,
                    latency_ms,
                    self._degraded_threshold_ms,
                )
        else:
            old = self._snapshot.status
            self._snapshot.status = K0AvailabilityStatus.ONLINE
            if old != K0AvailabilityStatus.ONLINE:
                logger.info(
                    "K0 health: %s → ONLINE (latency=%dms)",
                    old.value,
                    latency_ms,
                )

        return self._snapshot.status

    def record_failure(self, error: str = "") -> K0AvailabilityStatus:
        """Record a failed health check.

        Args:
            error: Error message describing the failure.

        Returns:
            New availability status after this observation.
        """
        now = time.monotonic_ns()
        self._snapshot.last_failure_ns = now
        self._snapshot.consecutive_failures += 1
        self._snapshot.error_message = error

        if self._snapshot.consecutive_failures >= self._failure_threshold:
            old = self._snapshot.status
            self._snapshot.status = K0AvailabilityStatus.OFFLINE
            if old != K0AvailabilityStatus.OFFLINE:
                logger.error(
                    "K0 health: %s → OFFLINE (%d consecutive failures: %s)",
                    old.value,
                    self._snapshot.consecutive_failures,
                    error,
                )
        else:
            # Not enough failures yet — stay in current state or go DEGRADED
            if self._snapshot.status == K0AvailabilityStatus.ONLINE:
                self._snapshot.status = K0AvailabilityStatus.DEGRADED
                logger.warning(
                    "K0 health: ONLINE → DEGRADED (failure %d/%d: %s)",
                    self._snapshot.consecutive_failures,
                    self._failure_threshold,
                    error,
                )

        return self._snapshot.status

    def force_offline(self, reason: str = "manual") -> None:
        """Force transition to OFFLINE (e.g. during shutdown)."""
        self._snapshot.status = K0AvailabilityStatus.OFFLINE
        self._snapshot.error_message = reason
        logger.info("K0 health: forced OFFLINE (%s)", reason)


# ---------------------------------------------------------------------------
# Degraded mode manager
# ---------------------------------------------------------------------------


class DegradedModeManager:
    """Policy engine that decides per-port behaviour based on K0 availability.

    Used by BridgeClient to gate operations:
      - should_queue_command()   → True when OFFLINE (use LocalOutbox)
      - should_drop_obs()        → True for LOW priority when not ONLINE
      - should_use_cache()       → True for queries when OFFLINE
      - query_timeout_ms()       → Extended timeout when DEGRADED

    Parameters:
        health: K0HealthChecker instance to read status from.
        default_query_timeout_ms: Normal query timeout.
        degraded_query_timeout_factor: Multiplier for DEGRADED mode.
    """

    def __init__(
        self,
        health: K0HealthChecker,
        *,
        default_query_timeout_ms: int = 5000,
        degraded_query_timeout_factor: float = 2.0,
    ) -> None:
        self._health = health
        self._default_query_timeout_ms = default_query_timeout_ms
        self._degraded_factor = degraded_query_timeout_factor

    @property
    def status(self) -> K0AvailabilityStatus:
        """Current K0 availability status."""
        return self._health.status

    def should_queue_command(self) -> bool:
        """True when commands should be queued to LocalOutbox."""
        return self._health.status == K0AvailabilityStatus.OFFLINE

    def should_drop_obs(self, priority: str = "NORMAL") -> bool:
        """True when observability emissions should be dropped.

        LOW priority is dropped in DEGRADED and OFFLINE.
        NORMAL and HIGH are only dropped in OFFLINE.
        """
        status = self._health.status
        if priority == "LOW":
            return status != K0AvailabilityStatus.ONLINE
        return False

    def should_use_cache(self) -> bool:
        """True when queries should return cached/empty results."""
        return self._health.status == K0AvailabilityStatus.OFFLINE

    def query_timeout_ms(self) -> int:
        """Query timeout, extended when DEGRADED."""
        if self._health.status == K0AvailabilityStatus.DEGRADED:
            return int(self._default_query_timeout_ms * self._degraded_factor)
        return self._default_query_timeout_ms

    def is_online(self) -> bool:
        """True when K0 is fully available."""
        return self._health.status == K0AvailabilityStatus.ONLINE
