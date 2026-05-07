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

import asyncio
import enum
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .events import EventBus

logger = logging.getLogger(__name__)

# Default poll interval (s); override with BRIDGE_HEALTH_POLL_INTERVAL_S.
_DEFAULT_POLL_INTERVAL_S = 30.0
_DEFAULT_PROBE_TIMEOUT_S = 5.0
_JITTER_FRACTION = 0.10  # ±10% jitter on poll cadence


# ---------------------------------------------------------------------------
# Availability status
# ---------------------------------------------------------------------------


class K0AvailabilityStatus(enum.Enum):
    """K0 reachability state as observed by the Bridge."""

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


# MS-3b plan-aligned alias. The plan and the auto-derived DEGRADED matrix
# (Epic 3b.2) refer to the state machine as ``K0HealthState``; the legacy
# name ``K0AvailabilityStatus`` is retained for backward-compat with
# ``SinkBridgeClient`` and existing tests.
K0HealthState = K0AvailabilityStatus


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
        event_bus: "EventBus | None" = None,
        target_url: str | None = None,
        poll_interval_s: float | None = None,
        probe_timeout_s: float = _DEFAULT_PROBE_TIMEOUT_S,
        rng: random.Random | None = None,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._degraded_threshold_ms = degraded_threshold_ms
        self._snapshot = K0HealthSnapshot()
        self._event_bus = event_bus
        self._target_url = target_url
        env_interval = os.getenv("BRIDGE_HEALTH_POLL_INTERVAL_S")
        if poll_interval_s is not None:
            self._poll_interval_s = poll_interval_s
        elif env_interval:
            try:
                self._poll_interval_s = float(env_interval)
            except ValueError:
                self._poll_interval_s = _DEFAULT_POLL_INTERVAL_S
        else:
            self._poll_interval_s = _DEFAULT_POLL_INTERVAL_S
        self._probe_timeout_s = probe_timeout_s
        self._rng = rng or random.Random()
        self._poll_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

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
                self._emit_transition(old, K0AvailabilityStatus.DEGRADED, reason="latency_high")
        else:
            old = self._snapshot.status
            self._snapshot.status = K0AvailabilityStatus.ONLINE
            if old != K0AvailabilityStatus.ONLINE:
                logger.info(
                    "K0 health: %s → ONLINE (latency=%dms)",
                    old.value,
                    latency_ms,
                )
                self._emit_transition(old, K0AvailabilityStatus.ONLINE, reason="probe_success")

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
                self._emit_transition(
                    old, K0AvailabilityStatus.OFFLINE, reason=error or "probe_failed"
                )
        else:
            # Not enough failures yet — stay in current state or go DEGRADED
            if self._snapshot.status == K0AvailabilityStatus.ONLINE:
                old = self._snapshot.status
                self._snapshot.status = K0AvailabilityStatus.DEGRADED
                logger.warning(
                    "K0 health: ONLINE → DEGRADED (failure %d/%d: %s)",
                    self._snapshot.consecutive_failures,
                    self._failure_threshold,
                    error,
                )
                self._emit_transition(
                    old, K0AvailabilityStatus.DEGRADED, reason=error or "probe_failed"
                )

        return self._snapshot.status

    def force_offline(self, reason: str = "manual") -> None:
        """Force transition to OFFLINE (e.g. during shutdown)."""
        old = self._snapshot.status
        self._snapshot.status = K0AvailabilityStatus.OFFLINE
        self._snapshot.error_message = reason
        logger.info("K0 health: forced OFFLINE (%s)", reason)
        if old != K0AvailabilityStatus.OFFLINE:
            self._emit_transition(old, K0AvailabilityStatus.OFFLINE, reason=reason)

    # -- transition event emission ----------------------------------------

    def _emit_transition(
        self,
        old: K0AvailabilityStatus,
        new: K0AvailabilityStatus,
        *,
        reason: str = "",
    ) -> None:
        """Publish a :class:`HealthTransition` to the bus when one is wired.

        Per the MS-3b spec the drain worker subscribes only to
        ``OFFLINE → ONLINE``; we still publish every transition so the
        DEGRADED matrix and observability metrics see the full picture.
        """
        if self._event_bus is None or old == new:
            return
        # Local import to keep tooling out of the cold-start graph.
        from .events import HealthTransition, utc_now

        evt = HealthTransition(
            from_state=old.value,
            to_state=new.value,
            at_utc=utc_now(),
            consecutive_failures=self._snapshot.consecutive_failures,
            latency_ms=self._snapshot.latency_ms,
            reason=reason,
        )
        self._event_bus.publish(evt)

    # -- async poll loop --------------------------------------------------

    async def _probe_once(self) -> None:
        """Issue one ``HEAD /healthz`` and feed the result back in.

        Imports ``httpx`` lazily so unit tests that drive the state
        machine via ``record_success`` / ``record_failure`` do not pay
        for the import.
        """
        if not self._target_url:
            self.record_failure("no_target_url")
            return
        import httpx  # noqa: PLC0415 — lazy import (rule 3)

        url = self._target_url.rstrip("/") + "/healthz"
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._probe_timeout_s) as client:
                resp = await client.head(url)
            latency_ms = int((time.monotonic() - start) * 1000)
            if resp.status_code < 500:
                self.record_success(latency_ms)
            else:
                self.record_failure(f"http_{resp.status_code}")
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            self.record_failure(f"transport_error: {type(exc).__name__}")
        except Exception as exc:  # pragma: no cover — defensive
            self.record_failure(f"unexpected: {type(exc).__name__}")

    def _next_sleep_s(self) -> float:
        """Jittered cadence (±10%) to avoid thundering herd on transitions."""
        delta = self._poll_interval_s * _JITTER_FRACTION
        return self._poll_interval_s + self._rng.uniform(-delta, delta)

    async def _poll_loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            await self._probe_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._next_sleep_s())
            except asyncio.TimeoutError:
                continue

    async def start(self) -> None:
        """Spawn the background poll task. Idempotent."""
        if self._poll_task is not None and not self._poll_task.done():
            return
        self._stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()
        self._poll_task = loop.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Cancel the poll task and wait for it to settle."""
        if self._poll_task is None:
            return
        if self._stop_event is not None:
            self._stop_event.set()
        self._poll_task.cancel()
        try:
            await self._poll_task
        except (asyncio.CancelledError, Exception):
            pass
        self._poll_task = None
        self._stop_event = None


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
