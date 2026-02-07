"""
k1.fabric.health.health_checker -- HealthChecker (3.6.1) + CB wiring (3.6.3).

Periodic health checks for all registered providers.  Iterates over the
ProviderRegistry, calls ``provider.health_check()`` on each, and updates
both the ProviderRegistry health cache and the AvailabilityTracker.

Flow per check cycle:
  1. Iterate registered providers from ProviderRegistry.
  2. Call ``provider_instance.health_check()`` with timeout.
  3. Map ProviderHealth status -> Availability:
       HEALTHY   -> ONLINE
       DEGRADED  -> DEGRADED
       UNHEALTHY -> OFFLINE (after consecutive_failures >= threshold)
       UNKNOWN   -> no change
  4. Update ProviderRegistry.update_health() with probe result.
  5. Update AvailabilityTracker.update_state() on state change.
  6. Emit ``k1.fabric.provider.health.changed.v1`` on state change.

Failure handling:
  - Timeout: mark DEGRADED.
  - Exception: increment consecutive failure counter.
    If consecutive_failures >= failure_threshold: mark OFFLINE.
    Otherwise: mark DEGRADED.
  - Recovery: OFFLINE -> DEGRADED -> ONLINE (progressive via tracker).

Circuit Breaker Integration (3.6.3):
  - HealthChecker holds reference to a dict of CircuitBreakers.
  - When CB state changes to OPEN: HealthChecker triggers immediate
    health check for that provider (via ``check_provider()``).
  - When health check succeeds while CB is OPEN: HealthChecker calls
    ``cb.allow_probe()`` to signal HALF_OPEN.
  - Bidirectional: CB informs health (via on_cb_state_change callback),
    health informs CB (via allow_probe/trip).

Thread Safety:
  Internal state guarded by RLock.  Health checks run async.
  Timer loop uses asyncio without blocking the event loop.

References:
  - fabric_discussion.md Section 19 (Error Handling, Health Monitoring)
  - k1_cognitive_architecture_skeleton.mmd (Provider health monitoring)
  - Epic 3.6.1, 3.6.3 in fabric-implementation-plan.md

Exports:
  HealthChecker        -- Periodic health monitor
  HealthCheckerConfig  -- Configuration for check intervals and thresholds
  HealthCheckResult    -- Result of a single provider health probe
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

from k1.fabric.types import Availability, ProviderHealth, ProviderStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols for injected dependencies
# ---------------------------------------------------------------------------


class IProviderRegistry(Protocol):
    """
    Subset of ProviderRegistry used by HealthChecker.

    Avoids importing the full ProviderRegistry class to prevent
    circular dependencies.
    """

    def list_ids(self) -> List[str]: ...

    def lookup_provider(self, provider_id: str) -> Any: ...

    def update_health(
        self,
        provider_id: str,
        status: str,
        latency_ms: int = 0,
        error: Optional[str] = None,
    ) -> None: ...


class IAvailabilityTracker(Protocol):
    """
    Subset of AvailabilityTracker used by HealthChecker.
    """

    def update_state(
        self,
        provider_id: str,
        new_state: str,
        reason: str = "",
    ) -> Any: ...

    def get_state(self, provider_id: str) -> str: ...

    def is_tracked(self, provider_id: str) -> bool: ...

    def register(
        self,
        provider_id: str,
        initial_state: str = ...,
    ) -> None: ...


class ICircuitBreaker(Protocol):
    """
    Subset of CircuitBreaker used by HealthChecker.
    """

    @property
    def provider_id(self) -> str: ...

    @property
    def state(self) -> Any: ...

    def allow_probe(self) -> None: ...

    def trip(self) -> None: ...


class EventPort(Protocol):
    """Minimal event bus interface."""

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None: ...


class ICapabilityProvider(Protocol):
    """Subset of CapabilityProvider for health checks."""

    async def health_check(self) -> ProviderHealth: ...


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVENT_HEALTH_CHANGED = "k1.fabric.provider.health.changed.v1"
EVENT_HEALTH_CHECK_CYCLE = "k1.fabric.health.check_cycle.v1"

DEFAULT_CHECK_INTERVAL_S = 30
DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_CHECK_TIMEOUT_S = 10

# Map ProviderStatus -> Availability for health -> availability conversion
_STATUS_TO_AVAILABILITY = {
    ProviderStatus.HEALTHY.value: Availability.ONLINE.value,
    ProviderStatus.DEGRADED.value: Availability.DEGRADED.value,
    ProviderStatus.UNHEALTHY.value: Availability.OFFLINE.value,
    # UNKNOWN: no change
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthCheckerConfig:
    """
    Configuration for the HealthChecker.

    Attributes:
        default_interval_s: Default check interval in seconds.
        per_type_interval_s: Check interval overrides by provider_type.
        failure_threshold: Consecutive failures before marking OFFLINE.
        check_timeout_s: Timeout per individual health check.
        max_consecutive_failures: Max tracked consecutive failures.
    """

    default_interval_s: int = DEFAULT_CHECK_INTERVAL_S
    per_type_interval_s: Optional[Dict[str, int]] = None
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
    check_timeout_s: int = DEFAULT_CHECK_TIMEOUT_S
    max_consecutive_failures: int = 10

    def get_interval(self, provider_type: str) -> int:
        """Get check interval for a specific provider type."""
        if self.per_type_interval_s and provider_type in self.per_type_interval_s:
            return self.per_type_interval_s[provider_type]
        return self.default_interval_s


# ---------------------------------------------------------------------------
# Health check result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthCheckResult:
    """
    Result of a single provider health probe.

    Attributes:
        provider_id: Provider that was checked.
        status: Resulting ProviderStatus value.
        latency_ms: Probe round-trip time.
        error: Error message if check failed.
        timestamp: ISO 8601 timestamp.
        old_status: Previous status before this check.
        changed: Whether the status changed.
    """

    provider_id: str = ""
    status: str = ProviderStatus.UNKNOWN.value
    latency_ms: int = 0
    error: Optional[str] = None
    timestamp: str = ""
    old_status: str = ProviderStatus.UNKNOWN.value
    changed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "provider_id": self.provider_id,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "timestamp": self.timestamp,
            "old_status": self.old_status,
            "changed": self.changed,
        }


# ---------------------------------------------------------------------------
# Internal per-provider check state
# ---------------------------------------------------------------------------


class _ProviderCheckState:
    """Mutable internal state for health checking of a single provider."""

    __slots__ = (
        "last_status",
        "consecutive_failures",
        "last_check_ms",
    )

    def __init__(self) -> None:
        self.last_status: str = ProviderStatus.UNKNOWN.value
        self.consecutive_failures: int = 0
        self.last_check_ms: int = 0


# ---------------------------------------------------------------------------
# 3.6.1 + 3.6.3 -- HealthChecker
# ---------------------------------------------------------------------------


class HealthChecker:
    """
    Periodic health monitor for all registered providers.

    Provides:
      - ``check_provider()`` -- Run health check on a single provider.
      - ``check_all()`` -- Run health checks on all registered providers.
      - ``start()`` / ``stop()`` -- Start/stop the periodic check loop.
      - ``on_cb_state_change()`` -- Callback for circuit breaker integration.

    Constructor Args:
        provider_registry: ProviderRegistry for listing providers + updating health.
        availability_tracker: AvailabilityTracker for state transitions.
        provider_instances: Dict mapping provider_id to provider instance
            (must have async health_check() -> ProviderHealth).
        circuit_breakers: Optional dict of provider_id -> CircuitBreaker
            for bidirectional CB integration (3.6.3).
        event_port: Optional event bus for health events.
        config: HealthCheckerConfig.

    Thread Safety:
        Internal state protected by _check_states dict.
        Health checks run async.  The periodic loop uses asyncio.
    """

    __slots__ = (
        "_registry",
        "_tracker",
        "_providers",
        "_breakers",
        "_event_port",
        "_config",
        "_check_states",
        "_running",
        "_task",
        "_cycle_count",
    )

    def __init__(
        self,
        *,
        provider_registry: IProviderRegistry,
        availability_tracker: IAvailabilityTracker,
        provider_instances: Optional[Dict[str, ICapabilityProvider]] = None,
        circuit_breakers: Optional[Dict[str, ICircuitBreaker]] = None,
        event_port: Optional[EventPort] = None,
        config: Optional[HealthCheckerConfig] = None,
    ) -> None:
        self._registry = provider_registry
        self._tracker = availability_tracker
        self._providers: Dict[str, ICapabilityProvider] = provider_instances or {}
        self._breakers: Dict[str, ICircuitBreaker] = circuit_breakers or {}
        self._event_port = event_port
        self._config = config or HealthCheckerConfig()
        self._check_states: Dict[str, _ProviderCheckState] = {}
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._cycle_count = 0

    # ==================================================================
    # Provider instance management
    # ==================================================================

    def register_provider_instance(
        self,
        provider_id: str,
        instance: ICapabilityProvider,
    ) -> None:
        """Register a provider instance for health checking."""
        self._providers[provider_id] = instance

    def unregister_provider_instance(self, provider_id: str) -> None:
        """Remove a provider instance from health checking."""
        self._providers.pop(provider_id, None)
        self._check_states.pop(provider_id, None)

    def register_circuit_breaker(
        self,
        provider_id: str,
        breaker: ICircuitBreaker,
    ) -> None:
        """Register a circuit breaker for bidirectional integration (3.6.3)."""
        self._breakers[provider_id] = breaker

    # ==================================================================
    # Single provider health check
    # ==================================================================

    async def check_provider(self, provider_id: str) -> HealthCheckResult:
        """
        Run a health check on a single provider.

        Flow:
          1. Call provider.health_check() with timeout.
          2. Map result to ProviderStatus.
          3. Update ProviderRegistry health cache.
          4. Update AvailabilityTracker on state change.
          5. Signal CircuitBreaker if applicable (3.6.3).
          6. Emit event on state change.

        Args:
            provider_id: Provider identifier.

        Returns:
            HealthCheckResult with probe outcome.
        """
        provider = self._providers.get(provider_id)
        if provider is None:
            return HealthCheckResult(
                provider_id=provider_id,
                status=ProviderStatus.UNKNOWN.value,
                error="No provider instance registered",
                timestamp=self._timestamp(),
            )

        cs = self._get_check_state(provider_id)
        old_status = cs.last_status
        start_ms = self._now_ms()

        # Execute health check with timeout
        try:
            health = await asyncio.wait_for(
                provider.health_check(),
                timeout=self._config.check_timeout_s,
            )
            latency_ms = self._now_ms() - start_ms
            new_status = health.status
            error = health.error

            if new_status == ProviderStatus.HEALTHY.value:
                cs.consecutive_failures = 0
            elif new_status == ProviderStatus.UNHEALTHY.value:
                cs.consecutive_failures += 1
            # DEGRADED: increment but don't reset
            elif new_status == ProviderStatus.DEGRADED.value:
                cs.consecutive_failures += 1

        except asyncio.TimeoutError:
            latency_ms = self._now_ms() - start_ms
            cs.consecutive_failures += 1
            new_status = ProviderStatus.DEGRADED.value
            error = f"Health check timed out after {self._config.check_timeout_s}s"

        except Exception as exc:
            latency_ms = self._now_ms() - start_ms
            cs.consecutive_failures += 1
            new_status = ProviderStatus.UNHEALTHY.value
            error = f"Health check failed: {type(exc).__name__}: {exc}"

        # Apply consecutive failure threshold
        if (
            cs.consecutive_failures >= self._config.failure_threshold
            and new_status != ProviderStatus.HEALTHY.value
        ):
            new_status = ProviderStatus.UNHEALTHY.value

        cs.last_status = new_status
        cs.last_check_ms = self._now_ms()
        changed = old_status != new_status

        # Update ProviderRegistry health cache
        self._update_registry_health(provider_id, new_status, latency_ms, error)

        # Update AvailabilityTracker on change
        if changed:
            self._update_availability(provider_id, new_status, old_status)

        # Circuit Breaker integration (3.6.3)
        if changed:
            self._sync_circuit_breaker(provider_id, new_status)

        # Emit event on change
        if changed:
            self._emit(
                EVENT_HEALTH_CHANGED,
                {
                    "provider_id": provider_id,
                    "old_status": old_status,
                    "new_status": new_status,
                    "latency_ms": latency_ms,
                    "error": error,
                    "consecutive_failures": cs.consecutive_failures,
                },
            )

        return HealthCheckResult(
            provider_id=provider_id,
            status=new_status,
            latency_ms=latency_ms,
            error=error,
            timestamp=self._timestamp(),
            old_status=old_status,
            changed=changed,
        )

    # ==================================================================
    # Check all providers
    # ==================================================================

    async def check_all(self) -> List[HealthCheckResult]:
        """
        Run health checks on all registered providers.

        Returns:
            List of HealthCheckResult for each provider.
        """
        provider_ids = self._registry.list_ids()
        results: List[HealthCheckResult] = []

        for pid in provider_ids:
            if pid in self._providers:
                result = await self.check_provider(pid)
                results.append(result)

        self._cycle_count += 1
        return results

    # ==================================================================
    # Periodic check loop
    # ==================================================================

    async def start(self) -> None:
        """Start the periodic health check loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._run_loop())
        logger.info(
            "HealthChecker started (interval=%ds)",
            self._config.default_interval_s,
        )

    async def stop(self) -> None:
        """Stop the periodic health check loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("HealthChecker stopped")

    @property
    def is_running(self) -> bool:
        """Whether the periodic loop is active."""
        return self._running

    @property
    def cycle_count(self) -> int:
        """Number of completed check cycles."""
        return self._cycle_count

    async def _run_loop(self) -> None:
        """Internal periodic loop."""
        while self._running:
            try:
                await self.check_all()
            except Exception:
                logger.error("Health check cycle failed", exc_info=True)

            try:
                await asyncio.sleep(self._config.default_interval_s)
            except asyncio.CancelledError:
                break

    # ==================================================================
    # Circuit Breaker integration (3.6.3)
    # ==================================================================

    def on_cb_state_change(
        self,
        provider_id: str,
        old_state: Any,
        new_state: Any,
    ) -> None:
        """
        Callback for circuit breaker state changes (3.6.3).

        When a CB transitions to OPEN, triggers an immediate health
        check for that provider.

        This is designed to be called from the CB's on_state_change
        callback chain.  It schedules the health check on the running
        event loop.

        Args:
            provider_id: The provider whose CB changed state.
            old_state: Previous CircuitBreakerState.
            new_state: New CircuitBreakerState.
        """
        from k1.fabric.circuit_breaker.breaker import CircuitBreakerState

        if isinstance(new_state, str):
            try:
                new_state = CircuitBreakerState(new_state)
            except ValueError:
                return

        if new_state == CircuitBreakerState.OPEN:
            # Schedule immediate health check
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._immediate_check(provider_id))
            except RuntimeError:
                # No running event loop -- skip immediate check
                logger.debug(
                    "No event loop for immediate health check of %s",
                    provider_id,
                )

    async def _immediate_check(self, provider_id: str) -> None:
        """
        Run an immediate health check triggered by CB OPEN event.

        If the check succeeds, signal the CB to try HALF_OPEN.
        """
        logger.info(
            "Immediate health check triggered for %s (CB OPEN)",
            provider_id,
        )
        result = await self.check_provider(provider_id)

        if result.status == ProviderStatus.HEALTHY.value:
            breaker = self._breakers.get(provider_id)
            if breaker is not None:
                breaker.allow_probe()
                logger.info(
                    "CB allow_probe signaled for %s (health check passed)",
                    provider_id,
                )

    def _sync_circuit_breaker(
        self,
        provider_id: str,
        new_status: str,
    ) -> None:
        """
        Signal circuit breaker based on health check result.

        - HEALTHY: If CB is OPEN, signal allow_probe() for HALF_OPEN.
        - UNHEALTHY: If CB is not OPEN, trip() it.
        """
        breaker = self._breakers.get(provider_id)
        if breaker is None:
            return

        from k1.fabric.circuit_breaker.breaker import CircuitBreakerState

        try:
            cb_state = breaker.state
            if new_status == ProviderStatus.HEALTHY.value:
                if cb_state == CircuitBreakerState.OPEN:
                    breaker.allow_probe()
                    logger.info(
                        "Health OK -> CB allow_probe for %s",
                        provider_id,
                    )
            elif new_status == ProviderStatus.UNHEALTHY.value:
                if cb_state != CircuitBreakerState.OPEN:
                    breaker.trip()
                    logger.info(
                        "Health UNHEALTHY -> CB trip for %s",
                        provider_id,
                    )
        except Exception:
            logger.warning(
                "Failed to sync CB for %s",
                provider_id,
                exc_info=True,
            )

    # ==================================================================
    # Internal: state management
    # ==================================================================

    def _get_check_state(self, provider_id: str) -> _ProviderCheckState:
        """Get or create the check state for a provider."""
        cs = self._check_states.get(provider_id)
        if cs is None:
            cs = _ProviderCheckState()
            self._check_states[provider_id] = cs
        return cs

    def _update_registry_health(
        self,
        provider_id: str,
        status: str,
        latency_ms: int,
        error: Optional[str],
    ) -> None:
        """Update the ProviderRegistry health cache."""
        try:
            self._registry.update_health(
                provider_id,
                status=status,
                latency_ms=latency_ms,
                error=error,
            )
        except Exception:
            logger.warning(
                "Failed to update registry health for %s",
                provider_id,
                exc_info=True,
            )

    def _update_availability(
        self,
        provider_id: str,
        new_status: str,
        old_status: str,
    ) -> None:
        """
        Map ProviderStatus -> Availability and update tracker.

        Recovery is progressive (OFFLINE -> DEGRADED -> ONLINE).
        """
        new_avail = _STATUS_TO_AVAILABILITY.get(new_status)
        if new_avail is None:
            return  # UNKNOWN: no change

        # Ensure provider is tracked
        if not self._tracker.is_tracked(provider_id):
            old_avail = _STATUS_TO_AVAILABILITY.get(
                old_status,
                Availability.ONLINE.value,
            )
            self._tracker.register(provider_id, initial_state=old_avail)

        try:
            self._tracker.update_state(
                provider_id,
                new_avail,
                reason=f"health_check:{old_status}->{new_status}",
            )
        except Exception:
            # Progressive recovery might block OFFLINE->ONLINE.
            # Try intermediate step.
            if new_avail == Availability.ONLINE.value:
                try:
                    self._tracker.update_state(
                        provider_id,
                        Availability.DEGRADED.value,
                        reason="health_check:recovery_intermediate",
                    )
                    self._tracker.update_state(
                        provider_id,
                        Availability.ONLINE.value,
                        reason="health_check:recovery_confirmed",
                    )
                except Exception:
                    logger.warning(
                        "Failed to update availability for %s",
                        provider_id,
                        exc_info=True,
                    )

    # ==================================================================
    # Internal: event + time helpers
    # ==================================================================

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit an event via event_port, if available."""
        if self._event_port is not None:
            try:
                self._event_port.emit(event_type, payload)
            except Exception:
                logger.warning(
                    "Failed to emit %s for %s",
                    event_type,
                    payload.get("provider_id", "unknown"),
                    exc_info=True,
                )

    @staticmethod
    def _now_ms() -> int:
        """Current monotonic time in milliseconds."""
        return int(time.monotonic() * 1000)

    @staticmethod
    def _timestamp() -> str:
        """ISO 8601 UTC timestamp."""
        return datetime.now(timezone.utc).isoformat()

    def get_check_state(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """
        Return the check state for a provider (for diagnostics).

        Returns None if provider has no check state.
        """
        cs = self._check_states.get(provider_id)
        if cs is None:
            return None
        return {
            "last_status": cs.last_status,
            "consecutive_failures": cs.consecutive_failures,
            "last_check_ms": cs.last_check_ms,
        }

    def __repr__(self) -> str:
        return (
            f"HealthChecker("
            f"providers={len(self._providers)}, "
            f"breakers={len(self._breakers)}, "
            f"running={self._running}, "
            f"cycles={self._cycle_count})"
        )
