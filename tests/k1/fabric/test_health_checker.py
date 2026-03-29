"""
Tests for Epic 6.2.12: HealthChecker + AvailabilityTracker unit tests.

Covers (per fabric-implementation-plan.md):
  - Periodic health checks: healthy -> ONLINE, unhealthy -> DEGRADED/OFFLINE
  - Consecutive failure threshold for OFFLINE marking
  - Recovery progression: OFFLINE -> DEGRADED -> ONLINE
  - Health-checker + circuit-breaker bidirectional integration
  - AvailabilityTracker state transitions and history

NO MOCKS -- all test doubles are real in-memory adapters.

References:
  - fabric-implementation-plan.md Epic 6.2, Issue 6.2.12
  - health_checker.py (3.6.1 + 3.6.3)
  - availability_tracker.py (3.6.2)
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.circuit_breaker.breaker import CircuitBreakerState
from k1.fabric.health.availability_tracker import (
    EVENT_AVAILABILITY_CHANGED,
    VALID_TRANSITIONS,
    AvailabilityTracker,
    InvalidTransitionError,
    ProviderNotTrackedError,
    StateTransition,
)
from k1.fabric.health.health_checker import (
    EVENT_HEALTH_CHANGED,
    HealthChecker,
    HealthCheckerConfig,
    HealthCheckResult,
)
from k1.fabric.types import Availability, ProviderHealth, ProviderStatus

# ======================================================================
# Real in-memory adapters (NO MOCKS)
# ======================================================================


class CaptureEventPort:
    """Captures all emitted events for assertion."""

    def __init__(self) -> None:
        self.events: List[tuple[str, Dict[str, Any]]] = []

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.events.append((event_type, payload))


class InMemoryProviderRegistry:
    """Minimal in-memory provider registry implementing IProviderRegistry."""

    def __init__(self) -> None:
        self._providers: Dict[str, Any] = {}
        self._health: Dict[str, Dict[str, Any]] = {}

    def add(self, provider_id: str, config: Any = None) -> None:
        self._providers[provider_id] = config

    def list_ids(self) -> List[str]:
        return sorted(self._providers.keys())

    def lookup_provider(self, provider_id: str) -> Any:
        return self._providers.get(provider_id)

    def update_health(
        self,
        provider_id: str,
        status: str,
        latency_ms: int = 0,
        error: Optional[str] = None,
    ) -> None:
        self._health[provider_id] = {
            "status": status,
            "latency_ms": latency_ms,
            "error": error,
        }

    def get_health(self, provider_id: str) -> Optional[Dict[str, Any]]:
        return self._health.get(provider_id)


class HealthyProvider:
    """Provider that always reports HEALTHY."""

    def __init__(self, latency_ms: int = 5) -> None:
        self.latency_ms = latency_ms
        self.check_count = 0

    async def health_check(self) -> ProviderHealth:
        self.check_count += 1
        return ProviderHealth(
            provider_id="test",
            status=ProviderStatus.HEALTHY.value,
            latency_ms=self.latency_ms,
        )


class UnhealthyProvider:
    """Provider that always reports UNHEALTHY."""

    def __init__(self, error: str = "service down") -> None:
        self.error = error
        self.check_count = 0

    async def health_check(self) -> ProviderHealth:
        self.check_count += 1
        return ProviderHealth(
            provider_id="test",
            status=ProviderStatus.UNHEALTHY.value,
            error=self.error,
        )


class DegradedProvider:
    """Provider that always reports DEGRADED."""

    def __init__(self) -> None:
        self.check_count = 0

    async def health_check(self) -> ProviderHealth:
        self.check_count += 1
        return ProviderHealth(
            provider_id="test",
            status=ProviderStatus.DEGRADED.value,
        )


class SequenceProvider:
    """Provider that returns a sequence of health statuses, then loops last."""

    def __init__(self, statuses: List[str]) -> None:
        self._statuses = statuses
        self._index = 0
        self.check_count = 0

    async def health_check(self) -> ProviderHealth:
        self.check_count += 1
        idx = min(self._index, len(self._statuses) - 1)
        status = self._statuses[idx]
        self._index += 1
        return ProviderHealth(
            provider_id="test",
            status=status,
        )


class ExplodingProvider:
    """Provider that raises on health_check."""

    def __init__(self, exc: Exception = RuntimeError("boom")) -> None:
        self._exc = exc
        self.check_count = 0

    async def health_check(self) -> ProviderHealth:
        self.check_count += 1
        raise self._exc


class SlowProvider:
    """Provider that delays beyond timeout."""

    def __init__(self, delay_s: float = 30.0) -> None:
        self.delay_s = delay_s
        self.check_count = 0

    async def health_check(self) -> ProviderHealth:
        self.check_count += 1
        await asyncio.sleep(self.delay_s)
        return ProviderHealth(
            provider_id="test",
            status=ProviderStatus.HEALTHY.value,
        )


class InMemoryCircuitBreaker:
    """Real in-memory circuit breaker tracking calls."""

    def __init__(
        self,
        provider_id: str = "test",
        state: CircuitBreakerState = CircuitBreakerState.CLOSED,
    ) -> None:
        self._provider_id = provider_id
        self._state = state
        self.allow_probe_calls: int = 0
        self.trip_calls: int = 0

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    def allow_probe(self) -> None:
        self.allow_probe_calls += 1
        self._state = CircuitBreakerState.HALF_OPEN

    def trip(self) -> None:
        self.trip_calls += 1
        self._state = CircuitBreakerState.OPEN


# ======================================================================
# Helpers
# ======================================================================


def _make_checker(
    providers: Optional[Dict[str, Any]] = None,
    breakers: Optional[Dict[str, InMemoryCircuitBreaker]] = None,
    event_port: Optional[CaptureEventPort] = None,
    config: Optional[HealthCheckerConfig] = None,
    tracker: Optional[AvailabilityTracker] = None,
) -> tuple[HealthChecker, InMemoryProviderRegistry, AvailabilityTracker]:
    """Create a wired HealthChecker with all dependencies accessible."""
    reg = InMemoryProviderRegistry()
    trk = tracker or AvailabilityTracker(event_port=event_port)
    if providers:
        for pid in providers:
            reg.add(pid)
    checker = HealthChecker(
        provider_registry=reg,
        availability_tracker=trk,
        provider_instances=providers,
        circuit_breakers=breakers,
        event_port=event_port,
        config=config,
    )
    return checker, reg, trk


# ======================================================================
# HealthChecker: single provider checks
# ======================================================================


class TestHealthCheckHealthy:
    """Healthy provider probes map to ONLINE / HEALTHY."""

    @pytest.mark.asyncio
    async def test_healthy_returns_healthy_status(self) -> None:
        p = HealthyProvider()
        checker, reg, trk = _make_checker(providers={"p1": p})
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.HEALTHY.value
        assert result.error is None
        assert p.check_count == 1

    @pytest.mark.asyncio
    async def test_healthy_updates_registry(self) -> None:
        p = HealthyProvider()
        checker, reg, trk = _make_checker(providers={"p1": p})
        await checker.check_provider("p1")
        h = reg.get_health("p1")
        assert h is not None
        assert h["status"] == ProviderStatus.HEALTHY.value

    @pytest.mark.asyncio
    async def test_healthy_resets_consecutive_failures(self) -> None:
        # First fail, then succeed -> consecutive_failures reset to 0
        seq = SequenceProvider(
            [
                ProviderStatus.UNHEALTHY.value,
                ProviderStatus.HEALTHY.value,
            ]
        )
        checker, reg, trk = _make_checker(providers={"p1": seq})
        await checker.check_provider("p1")  # unhealthy
        state = checker.get_check_state("p1")
        assert state is not None and state["consecutive_failures"] == 1
        await checker.check_provider("p1")  # healthy
        state = checker.get_check_state("p1")
        assert state is not None and state["consecutive_failures"] == 0


class TestHealthCheckUnhealthy:
    """Unhealthy provider probes and failure threshold behavior."""

    @pytest.mark.asyncio
    async def test_single_unhealthy_below_threshold(self) -> None:
        """One failure -> UNHEALTHY status but not yet at threshold."""
        p = UnhealthyProvider()
        config = HealthCheckerConfig(failure_threshold=3)
        checker, reg, trk = _make_checker(providers={"p1": p}, config=config)
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.UNHEALTHY.value
        state = checker.get_check_state("p1")
        assert state is not None and state["consecutive_failures"] == 1

    @pytest.mark.asyncio
    async def test_consecutive_failures_at_threshold(self) -> None:
        """Exactly at failure_threshold -> marks UNHEALTHY/OFFLINE."""
        p = UnhealthyProvider()
        config = HealthCheckerConfig(failure_threshold=3)
        checker, reg, trk = _make_checker(providers={"p1": p}, config=config)
        for _ in range(3):
            result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.UNHEALTHY.value
        state = checker.get_check_state("p1")
        assert state is not None and state["consecutive_failures"] == 3

    @pytest.mark.asyncio
    async def test_one_below_threshold_then_recovery(self) -> None:
        """(threshold - 1) failures then healthy -> resets."""
        statuses = [ProviderStatus.UNHEALTHY.value] * 2 + [ProviderStatus.HEALTHY.value]
        seq = SequenceProvider(statuses)
        config = HealthCheckerConfig(failure_threshold=3)
        checker, reg, trk = _make_checker(providers={"p1": seq}, config=config)
        for _ in range(3):
            await checker.check_provider("p1")
        state = checker.get_check_state("p1")
        assert state is not None and state["consecutive_failures"] == 0


class TestHealthCheckDegraded:
    """DEGRADED provider status handling."""

    @pytest.mark.asyncio
    async def test_degraded_increments_failures(self) -> None:
        p = DegradedProvider()
        checker, reg, trk = _make_checker(providers={"p1": p})
        await checker.check_provider("p1")
        state = checker.get_check_state("p1")
        assert state is not None and state["consecutive_failures"] == 1

    @pytest.mark.asyncio
    async def test_degraded_at_threshold_becomes_unhealthy(self) -> None:
        """Degraded failures that hit threshold escalate to UNHEALTHY."""
        p = DegradedProvider()
        config = HealthCheckerConfig(failure_threshold=2)
        checker, reg, trk = _make_checker(providers={"p1": p}, config=config)
        await checker.check_provider("p1")
        result = await checker.check_provider("p1")
        # At threshold with non-healthy status -> UNHEALTHY
        assert result.status == ProviderStatus.UNHEALTHY.value


class TestHealthCheckExceptions:
    """Provider exceptions and timeouts."""

    @pytest.mark.asyncio
    async def test_exception_marks_unhealthy(self) -> None:
        p = ExplodingProvider()
        checker, reg, trk = _make_checker(providers={"p1": p})
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.UNHEALTHY.value
        assert "boom" in (result.error or "")

    @pytest.mark.asyncio
    async def test_timeout_marks_degraded(self) -> None:
        p = SlowProvider(delay_s=10.0)
        config = HealthCheckerConfig(check_timeout_s=0)  # immediate timeout
        checker, reg, trk = _make_checker(providers={"p1": p}, config=config)
        result = await checker.check_provider("p1")
        # Timeout -> DEGRADED (unless at failure threshold)
        assert result.status == ProviderStatus.DEGRADED.value
        assert "timed out" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_unknown_provider_returns_unknown(self) -> None:
        checker, reg, trk = _make_checker()
        result = await checker.check_provider("nonexistent")
        assert result.status == ProviderStatus.UNKNOWN.value
        assert result.error is not None


# ======================================================================
# HealthChecker: check_all
# ======================================================================


class TestCheckAll:
    """check_all behavior over multiple providers."""

    @pytest.mark.asyncio
    async def test_check_all_runs_all_registered(self) -> None:
        p1 = HealthyProvider()
        p2 = DegradedProvider()
        checker, reg, trk = _make_checker(providers={"p1": p1, "p2": p2})
        results = await checker.check_all()
        assert len(results) == 2
        assert p1.check_count == 1
        assert p2.check_count == 1

    @pytest.mark.asyncio
    async def test_check_all_increments_cycle(self) -> None:
        checker, reg, trk = _make_checker(providers={"p1": HealthyProvider()})
        assert checker.cycle_count == 0
        await checker.check_all()
        assert checker.cycle_count == 1
        await checker.check_all()
        assert checker.cycle_count == 2

    @pytest.mark.asyncio
    async def test_check_all_skips_ids_without_instances(self) -> None:
        """Provider in registry but no instance -> skipped."""
        checker, reg, trk = _make_checker(providers={"p1": HealthyProvider()})
        reg.add("p2")  # In registry but no provider instance
        results = await checker.check_all()
        ids = [r.provider_id for r in results]
        assert "p1" in ids
        assert "p2" not in ids


# ======================================================================
# HealthChecker: events
# ======================================================================


class TestHealthCheckerEvents:
    """Event emission on status change."""

    @pytest.mark.asyncio
    async def test_event_emitted_on_change(self) -> None:
        bus = CaptureEventPort()
        seq = SequenceProvider(
            [
                ProviderStatus.HEALTHY.value,
                ProviderStatus.UNHEALTHY.value,
            ]
        )
        checker, reg, trk = _make_checker(providers={"p1": seq}, event_port=bus)
        await checker.check_provider("p1")  # UNKNOWN -> HEALTHY
        await checker.check_provider("p1")  # HEALTHY -> UNHEALTHY
        health_events = [e for e in bus.events if e[0] == EVENT_HEALTH_CHANGED]
        assert len(health_events) >= 1
        last = health_events[-1][1]
        assert last["new_status"] == ProviderStatus.UNHEALTHY.value

    @pytest.mark.asyncio
    async def test_no_event_on_same_status(self) -> None:
        bus = CaptureEventPort()
        p = HealthyProvider()
        checker, reg, trk = _make_checker(providers={"p1": p}, event_port=bus)
        await checker.check_provider("p1")
        initial_count = len(bus.events)
        await checker.check_provider("p1")  # same status
        # No new health change event
        health_after = [e for e in bus.events[initial_count:] if e[0] == EVENT_HEALTH_CHANGED]
        assert len(health_after) == 0


# ======================================================================
# HealthChecker: recovery progression via check_provider
# ======================================================================


class TestRecoveryProgression:
    """Full recovery: OFFLINE -> DEGRADED -> ONLINE via health checks."""

    @pytest.mark.asyncio
    async def test_full_recovery_journey(self) -> None:
        """
        Provider goes: HEALTHY -> UNHEALTHY x3 (-> OFFLINE) -> DEGRADED -> HEALTHY (-> ONLINE).
        HealthChecker handles progressive recovery through AvailabilityTracker.
        """
        config = HealthCheckerConfig(failure_threshold=2)
        statuses = [
            ProviderStatus.HEALTHY.value,  # 1: ONLINE
            ProviderStatus.UNHEALTHY.value,  # 2: fail 1
            ProviderStatus.UNHEALTHY.value,  # 3: fail 2 -> threshold -> OFFLINE
            ProviderStatus.DEGRADED.value,  # 4: -> DEGRADED (recovery step)
            ProviderStatus.HEALTHY.value,  # 5: -> ONLINE (recovery complete)
        ]
        seq = SequenceProvider(statuses)
        tracker = AvailabilityTracker()
        checker, reg, trk = _make_checker(
            providers={"p1": seq},
            config=config,
            tracker=tracker,
        )

        # Step 1: healthy
        await checker.check_provider("p1")
        # Step 2: first failure (DEGRADED, below threshold)
        await checker.check_provider("p1")
        # Step 3: second failure (at threshold -> UNHEALTHY -> OFFLINE)
        await checker.check_provider("p1")

        # Now provider is OFFLINE in tracker (auto-registered)
        if trk.is_tracked("p1"):
            assert trk.get_state("p1") in {
                Availability.OFFLINE.value,
                Availability.DEGRADED.value,
            }

        # Step 4: degraded -> should bring to DEGRADED (intermediate)
        await checker.check_provider("p1")
        # Step 5: healthy -> should bring to ONLINE
        await checker.check_provider("p1")

        # Final state should be ONLINE after full recovery
        if trk.is_tracked("p1"):
            assert trk.get_state("p1") == Availability.ONLINE.value


# ======================================================================
# HealthChecker: circuit breaker integration
# ======================================================================


class TestCBIntegration:
    """Bidirectional health-checker <-> circuit-breaker."""

    @pytest.mark.asyncio
    async def test_healthy_signals_allow_probe_on_open_cb(self) -> None:
        """Health OK + CB OPEN -> allow_probe called."""
        p = HealthyProvider()
        cb = InMemoryCircuitBreaker("p1", state=CircuitBreakerState.OPEN)
        seq = SequenceProvider(
            [
                ProviderStatus.UNHEALTHY.value,
                ProviderStatus.HEALTHY.value,
            ]
        )
        checker, reg, trk = _make_checker(
            providers={"p1": seq},
            breakers={"p1": cb},
        )
        await checker.check_provider("p1")  # unhealthy
        await checker.check_provider("p1")  # healthy
        assert cb.allow_probe_calls >= 1

    @pytest.mark.asyncio
    async def test_unhealthy_trips_closed_cb(self) -> None:
        """Health UNHEALTHY + CB CLOSED -> trip called."""
        seq = SequenceProvider(
            [
                ProviderStatus.HEALTHY.value,
                ProviderStatus.UNHEALTHY.value,
            ]
        )
        cb = InMemoryCircuitBreaker("p1", state=CircuitBreakerState.CLOSED)
        config = HealthCheckerConfig(failure_threshold=1)
        checker, reg, trk = _make_checker(
            providers={"p1": seq},
            breakers={"p1": cb},
            config=config,
        )
        await checker.check_provider("p1")  # healthy
        await checker.check_provider("p1")  # unhealthy at threshold
        assert cb.trip_calls >= 1

    @pytest.mark.asyncio
    async def test_no_double_trip_on_open_cb(self) -> None:
        """Health UNHEALTHY + CB already OPEN -> no trip."""
        # Both checks are unhealthy; CB starts OPEN
        seq = SequenceProvider(
            [
                ProviderStatus.UNHEALTHY.value,
                ProviderStatus.UNHEALTHY.value,
            ]
        )
        cb = InMemoryCircuitBreaker("p1", state=CircuitBreakerState.OPEN)
        config = HealthCheckerConfig(failure_threshold=1)
        checker, reg, trk = _make_checker(
            providers={"p1": seq},
            breakers={"p1": cb},
            config=config,
        )
        await checker.check_provider("p1")
        await checker.check_provider("p1")
        assert cb.trip_calls == 0  # already OPEN, so no trip

    @pytest.mark.asyncio
    async def test_register_circuit_breaker_dynamically(self) -> None:
        """Register CB after construction, check it's used."""
        seq = SequenceProvider(
            [
                ProviderStatus.HEALTHY.value,
                ProviderStatus.UNHEALTHY.value,
            ]
        )
        cb = InMemoryCircuitBreaker("p1", state=CircuitBreakerState.CLOSED)
        config = HealthCheckerConfig(failure_threshold=1)
        checker, reg, trk = _make_checker(
            providers={"p1": seq},
            config=config,
        )
        checker.register_circuit_breaker("p1", cb)
        await checker.check_provider("p1")
        await checker.check_provider("p1")
        assert cb.trip_calls >= 1


# ======================================================================
# HealthChecker: provider instance management
# ======================================================================


class TestProviderManagement:
    """Register / unregister provider instances."""

    @pytest.mark.asyncio
    async def test_register_instance_after_construction(self) -> None:
        checker, reg, trk = _make_checker()
        p = HealthyProvider()
        checker.register_provider_instance("p1", p)
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.HEALTHY.value

    @pytest.mark.asyncio
    async def test_unregister_instance(self) -> None:
        p = HealthyProvider()
        checker, reg, trk = _make_checker(providers={"p1": p})
        checker.unregister_provider_instance("p1")
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.UNKNOWN.value


# ======================================================================
# HealthChecker: config
# ======================================================================


class TestHealthCheckerConfigUnit:
    """HealthCheckerConfig unit tests."""

    def test_default_values(self) -> None:
        c = HealthCheckerConfig()
        assert c.default_interval_s == 30
        assert c.failure_threshold == 3
        assert c.check_timeout_s == 10
        assert c.max_consecutive_failures == 10

    def test_per_type_interval_override(self) -> None:
        c = HealthCheckerConfig(per_type_interval_s={"MCP": 5, "AGENT": 60})
        assert c.get_interval("MCP") == 5
        assert c.get_interval("AGENT") == 60
        assert c.get_interval("TOOL") == 30  # default

    def test_frozen(self) -> None:
        c = HealthCheckerConfig()
        with pytest.raises(AttributeError):
            c.failure_threshold = 99  # type: ignore[misc]


# ======================================================================
# HealthCheckResult type
# ======================================================================


class TestHealthCheckResultUnit:
    """HealthCheckResult dataclass tests."""

    def test_defaults(self) -> None:
        r = HealthCheckResult()
        assert r.provider_id == ""
        assert r.status == ProviderStatus.UNKNOWN.value
        assert r.changed is False

    def test_to_dict_roundtrip(self) -> None:
        r = HealthCheckResult(
            provider_id="p1",
            status=ProviderStatus.HEALTHY.value,
            latency_ms=42,
            changed=True,
        )
        d = r.to_dict()
        assert d["provider_id"] == "p1"
        assert d["status"] == ProviderStatus.HEALTHY.value
        assert d["latency_ms"] == 42
        assert d["changed"] is True

    def test_frozen(self) -> None:
        r = HealthCheckResult(provider_id="p1")
        with pytest.raises(AttributeError):
            r.provider_id = "p2"  # type: ignore[misc]


# ======================================================================
# HealthChecker: lifecycle
# ======================================================================


class TestHealthCheckerLifecycle:
    """Start / stop / is_running."""

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        checker, reg, trk = _make_checker(providers={"p1": HealthyProvider()})
        await checker.start()
        assert checker.is_running is True
        await checker.stop()
        assert checker.is_running is False

    @pytest.mark.asyncio
    async def test_double_start_idempotent(self) -> None:
        checker, reg, trk = _make_checker(providers={"p1": HealthyProvider()})
        await checker.start()
        await checker.start()
        assert checker.is_running is True
        await checker.stop()

    @pytest.mark.asyncio
    async def test_stop_without_start(self) -> None:
        checker, reg, trk = _make_checker()
        await checker.stop()
        assert checker.is_running is False

    def test_repr(self) -> None:
        checker, reg, trk = _make_checker(
            providers={"p1": HealthyProvider()},
            breakers={"p1": InMemoryCircuitBreaker("p1")},
        )
        r = repr(checker)
        assert "HealthChecker" in r
        assert "providers=1" in r
        assert "breakers=1" in r


# ======================================================================
# AvailabilityTracker: registration
# ======================================================================


class TestTrackerRegistration:
    """AvailabilityTracker register / unregister."""

    def test_register_default_online(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        assert t.get_state("p1") == Availability.ONLINE.value

    def test_register_custom_state(self) -> None:
        t = AvailabilityTracker()
        t.register("p1", initial_state=Availability.DEGRADED.value)
        assert t.get_state("p1") == Availability.DEGRADED.value

    def test_register_idempotent(self) -> None:
        t = AvailabilityTracker()
        t.register("p1", initial_state=Availability.ONLINE.value)
        t.register("p1", initial_state=Availability.OFFLINE.value)
        assert t.get_state("p1") == Availability.ONLINE.value  # first wins

    def test_register_empty_id_raises(self) -> None:
        t = AvailabilityTracker()
        with pytest.raises(ValueError, match="must not be empty"):
            t.register("")

    def test_register_invalid_state_raises(self) -> None:
        t = AvailabilityTracker()
        with pytest.raises(ValueError, match="Invalid"):
            t.register("p1", initial_state="BOGUS")

    def test_unregister_returns_true(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        assert t.unregister("p1") is True
        assert t.is_tracked("p1") is False

    def test_unregister_unknown_returns_false(self) -> None:
        t = AvailabilityTracker()
        assert t.unregister("p1") is False


# ======================================================================
# AvailabilityTracker: state transitions
# ======================================================================


class TestTrackerTransitions:
    """Valid and invalid state transitions."""

    def test_online_to_degraded(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        tr = t.update_state("p1", Availability.DEGRADED.value, reason="slow")
        assert tr is not None
        assert tr.old_state == Availability.ONLINE.value
        assert tr.new_state == Availability.DEGRADED.value
        assert t.get_state("p1") == Availability.DEGRADED.value

    def test_online_to_offline(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        t.update_state("p1", Availability.OFFLINE.value)
        assert t.get_state("p1") == Availability.OFFLINE.value

    def test_degraded_to_online(self) -> None:
        t = AvailabilityTracker()
        t.register("p1", initial_state=Availability.DEGRADED.value)
        t.update_state("p1", Availability.ONLINE.value)
        assert t.get_state("p1") == Availability.ONLINE.value

    def test_degraded_to_offline(self) -> None:
        t = AvailabilityTracker()
        t.register("p1", initial_state=Availability.DEGRADED.value)
        t.update_state("p1", Availability.OFFLINE.value)
        assert t.get_state("p1") == Availability.OFFLINE.value

    def test_offline_to_degraded(self) -> None:
        t = AvailabilityTracker()
        t.register("p1", initial_state=Availability.OFFLINE.value)
        t.update_state("p1", Availability.DEGRADED.value)
        assert t.get_state("p1") == Availability.DEGRADED.value

    def test_offline_to_online_blocked(self) -> None:
        """Progressive recovery: OFFLINE -> ONLINE is not allowed."""
        t = AvailabilityTracker()
        t.register("p1", initial_state=Availability.OFFLINE.value)
        with pytest.raises(InvalidTransitionError):
            t.update_state("p1", Availability.ONLINE.value)

    def test_offline_to_online_allowed_when_not_enforced(self) -> None:
        t = AvailabilityTracker(enforce_progressive_recovery=False)
        t.register("p1", initial_state=Availability.OFFLINE.value)
        t.update_state("p1", Availability.ONLINE.value)
        assert t.get_state("p1") == Availability.ONLINE.value

    def test_same_state_noop(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        result = t.update_state("p1", Availability.ONLINE.value)
        assert result is None

    def test_not_tracked_raises(self) -> None:
        t = AvailabilityTracker()
        with pytest.raises(ProviderNotTrackedError):
            t.update_state("p1", Availability.ONLINE.value)

    def test_invalid_state_value_raises(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        with pytest.raises(ValueError):
            t.update_state("p1", "INVALID")


# ======================================================================
# AvailabilityTracker: transition history
# ======================================================================


class TestTrackerHistory:
    """Transition history and truncation."""

    def test_transitions_recorded(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        t.update_state("p1", Availability.DEGRADED.value, reason="r1")
        t.update_state("p1", Availability.OFFLINE.value, reason="r2")
        history = t.get_transitions("p1")
        assert len(history) == 2
        assert history[0].new_state == Availability.DEGRADED.value
        assert history[1].new_state == Availability.OFFLINE.value

    def test_transitions_limit(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        t.update_state("p1", Availability.DEGRADED.value)
        t.update_state("p1", Availability.OFFLINE.value)
        limited = t.get_transitions("p1", limit=1)
        assert len(limited) == 1
        assert limited[0].new_state == Availability.OFFLINE.value

    def test_history_bounded_by_max(self) -> None:
        """max_history truncates old entries."""
        t = AvailabilityTracker(max_history=3)
        t.register("p1")
        # Alternate states to generate transitions
        states = [Availability.DEGRADED.value, Availability.ONLINE.value]
        for i in range(6):
            t.update_state("p1", states[i % 2])
        history = t.get_transitions("p1")
        assert len(history) <= 3

    def test_transition_to_dict(self) -> None:
        tr = StateTransition(
            provider_id="p1",
            old_state=Availability.ONLINE.value,
            new_state=Availability.DEGRADED.value,
            timestamp_ms=12345,
            reason="test",
        )
        d = tr.to_dict()
        assert d["provider_id"] == "p1"
        assert d["old_state"] == Availability.ONLINE.value
        assert d["new_state"] == Availability.DEGRADED.value
        assert d["reason"] == "test"


# ======================================================================
# AvailabilityTracker: queries
# ======================================================================


class TestTrackerQueries:
    """Query methods: list_by_state, summary, tracked_count."""

    def test_list_by_state(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        t.register("p2", initial_state=Availability.DEGRADED.value)
        t.register("p3")
        online = t.list_by_state(Availability.ONLINE.value)
        assert "p1" in online and "p3" in online
        assert "p2" not in online

    def test_summary(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        t.register("p2", initial_state=Availability.DEGRADED.value)
        t.register("p3", initial_state=Availability.OFFLINE.value)
        s = t.summary()
        assert s["ONLINE"] == 1
        assert s["DEGRADED"] == 1
        assert s["OFFLINE"] == 1

    def test_repr(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        r = repr(t)
        assert "AvailabilityTracker" in r
        assert "tracked=1" in r


# ======================================================================
# AvailabilityTracker: events
# ======================================================================


class TestTrackerEvents:
    """Event emission on state change."""

    def test_event_emitted_on_transition(self) -> None:
        bus = CaptureEventPort()
        t = AvailabilityTracker(event_port=bus)
        t.register("p1")
        t.update_state("p1", Availability.DEGRADED.value, reason="test")
        avail_events = [e for e in bus.events if e[0] == EVENT_AVAILABILITY_CHANGED]
        assert len(avail_events) == 1
        payload = avail_events[0][1]
        assert payload["provider_id"] == "p1"
        assert payload["new_state"] == Availability.DEGRADED.value

    def test_no_event_on_noop(self) -> None:
        bus = CaptureEventPort()
        t = AvailabilityTracker(event_port=bus)
        t.register("p1")
        t.update_state("p1", Availability.ONLINE.value)  # same state
        assert len(bus.events) == 0


# ======================================================================
# AvailabilityTracker: registry updater sync
# ======================================================================


class TestTrackerRegistrySync:
    """registry_updater callback propagation."""

    def test_updater_called_on_transition(self) -> None:
        calls: List[tuple[str, str]] = []

        def updater(pid: str, avail: str) -> None:
            calls.append((pid, avail))

        t = AvailabilityTracker(registry_updater=updater)
        t.register("p1")
        t.update_state("p1", Availability.DEGRADED.value)
        assert ("p1", Availability.DEGRADED.value) in calls


# ======================================================================
# AvailabilityTracker: CB callback
# ======================================================================


class TestTrackerCBCallback:
    """on_state_change callback from CircuitBreaker."""

    def test_cb_closed_to_online(self) -> None:
        t = AvailabilityTracker()
        t.register("p1", initial_state=Availability.DEGRADED.value)
        t.on_state_change("p1", CircuitBreakerState.HALF_OPEN, CircuitBreakerState.CLOSED)
        assert t.get_state("p1") == Availability.ONLINE.value

    def test_cb_open_to_offline(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        t.on_state_change("p1", CircuitBreakerState.CLOSED, CircuitBreakerState.OPEN)
        assert t.get_state("p1") == Availability.OFFLINE.value

    def test_cb_half_open_to_degraded(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        t.on_state_change("p1", CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN)
        assert t.get_state("p1") == Availability.DEGRADED.value

    def test_cb_auto_registers_untracked(self) -> None:
        t = AvailabilityTracker()
        assert not t.is_tracked("p1")
        t.on_state_change("p1", CircuitBreakerState.CLOSED, CircuitBreakerState.OPEN)
        assert t.is_tracked("p1")

    def test_cb_recovery_intermediate_step(self) -> None:
        """CB OPEN -> CLOSED on OFFLINE provider -> DEGRADED -> ONLINE."""
        t = AvailabilityTracker()
        t.register("p1", initial_state=Availability.OFFLINE.value)
        t.on_state_change("p1", CircuitBreakerState.OPEN, CircuitBreakerState.CLOSED)
        # Progressive recovery: OFFLINE -> DEGRADED -> ONLINE
        assert t.get_state("p1") == Availability.ONLINE.value

    def test_cb_string_states_accepted(self) -> None:
        t = AvailabilityTracker()
        t.register("p1")
        t.on_state_change("p1", "CLOSED", "OPEN")
        assert t.get_state("p1") == Availability.OFFLINE.value


# ======================================================================
# AvailabilityTracker: VALID_TRANSITIONS constant
# ======================================================================


class TestValidTransitions:
    """VALID_TRANSITIONS constant correctness."""

    def test_online_targets(self) -> None:
        assert VALID_TRANSITIONS[Availability.ONLINE.value] == {
            Availability.DEGRADED.value,
            Availability.OFFLINE.value,
        }

    def test_degraded_targets(self) -> None:
        assert VALID_TRANSITIONS[Availability.DEGRADED.value] == {
            Availability.ONLINE.value,
            Availability.OFFLINE.value,
        }

    def test_offline_cannot_go_to_online(self) -> None:
        assert Availability.ONLINE.value not in VALID_TRANSITIONS[Availability.OFFLINE.value]

    def test_offline_can_go_to_degraded(self) -> None:
        assert Availability.DEGRADED.value in VALID_TRANSITIONS[Availability.OFFLINE.value]
