"""
Tests for Epic 3.6: Health Checker Service (3.6.1 + 3.6.2 + 3.6.3).

Covers:
  - 3.6.1: HealthChecker -- periodic health monitoring
  - 3.6.2: AvailabilityTracker -- state tracking + transition history
  - 3.6.3: CB wiring -- bidirectional circuit breaker integration

Test doubles:
  - FakeProviderRegistry: In-memory provider registry stub
  - FakeProvider: Provider with configurable health_check()
  - FakeEventPort: Captures emitted events
  - FakeCircuitBreaker: Tracks allow_probe/trip calls

References:
  - fabric-implementation-plan.md Epic 3.6
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
    DEFAULT_CHECK_INTERVAL_S,
    DEFAULT_CHECK_TIMEOUT_S,
    DEFAULT_FAILURE_THRESHOLD,
    EVENT_HEALTH_CHANGED,
    HealthChecker,
    HealthCheckerConfig,
    HealthCheckResult,
)
from k1.fabric.types import Availability, ProviderHealth, ProviderStatus

# ======================================================================
# Test doubles
# ======================================================================


class FakeEventPort:
    """Captures all emitted events for assertion."""

    def __init__(self) -> None:
        self.events: List[tuple[str, Dict[str, Any]]] = []

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.events.append((event_type, payload))


class FailingEventPort:
    """Event port that raises on emit."""

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        raise RuntimeError("Event port failure")


class FakeProviderRegistry:
    """Minimal provider registry for testing HealthChecker."""

    def __init__(self) -> None:
        self._providers: Dict[str, Any] = {}
        self._health: Dict[str, Dict[str, Any]] = {}

    def register(self, provider_id: str, config: Any = None) -> None:
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


class FakeProvider:
    """Provider with configurable health_check() behavior."""

    def __init__(
        self,
        status: str = ProviderStatus.HEALTHY.value,
        error: Optional[str] = None,
        latency_ms: int = 5,
        raise_on_check: Optional[Exception] = None,
        delay_s: float = 0.0,
    ) -> None:
        self.status = status
        self.error = error
        self.latency_ms = latency_ms
        self.raise_on_check = raise_on_check
        self.delay_s = delay_s
        self.check_count = 0

    async def health_check(self) -> ProviderHealth:
        self.check_count += 1
        if self.delay_s > 0:
            await asyncio.sleep(self.delay_s)
        if self.raise_on_check is not None:
            raise self.raise_on_check
        return ProviderHealth(
            provider_id="test",
            status=self.status,
            latency_ms=self.latency_ms,
            error=self.error,
        )


class FakeCircuitBreaker:
    """Tracks CB interactions for testing."""

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


def _tracker(**kwargs: Any) -> AvailabilityTracker:
    """Create a tracker with test defaults."""
    return AvailabilityTracker(**kwargs)


def _checker(
    providers: Optional[Dict[str, FakeProvider]] = None,
    breakers: Optional[Dict[str, FakeCircuitBreaker]] = None,
    event_port: Optional[Any] = None,
    config: Optional[HealthCheckerConfig] = None,
    registry: Optional[FakeProviderRegistry] = None,
    tracker: Optional[AvailabilityTracker] = None,
) -> HealthChecker:
    """Create a HealthChecker with test defaults."""
    reg = registry or FakeProviderRegistry()
    trk = tracker or AvailabilityTracker()
    # Register provider IDs in the fake registry
    if providers:
        for pid in providers:
            reg.register(pid)
    return HealthChecker(
        provider_registry=reg,
        availability_tracker=trk,
        provider_instances=providers,
        circuit_breakers=breakers,
        event_port=event_port,
        config=config,
    )


# ======================================================================
# 3.6.2: AvailabilityTracker tests
# ======================================================================


class TestAvailabilityTrackerRegistration:
    """Test provider registration and unregistration."""

    def test_register_and_get_state(self) -> None:
        t = _tracker()
        t.register("p1")
        assert t.get_state("p1") == Availability.ONLINE.value

    def test_register_custom_initial_state(self) -> None:
        t = _tracker()
        t.register("p1", initial_state=Availability.DEGRADED.value)
        assert t.get_state("p1") == Availability.DEGRADED.value

    def test_register_idempotent(self) -> None:
        t = _tracker()
        t.register("p1", initial_state=Availability.ONLINE.value)
        t.register("p1", initial_state=Availability.OFFLINE.value)
        # First registration wins
        assert t.get_state("p1") == Availability.ONLINE.value

    def test_register_empty_id_raises(self) -> None:
        t = _tracker()
        with pytest.raises(ValueError):
            t.register("")

    def test_register_invalid_state_raises(self) -> None:
        t = _tracker()
        with pytest.raises(ValueError):
            t.register("p1", initial_state="INVALID")

    def test_unregister_existing(self) -> None:
        t = _tracker()
        t.register("p1")
        assert t.unregister("p1") is True
        assert t.is_tracked("p1") is False

    def test_unregister_nonexistent(self) -> None:
        t = _tracker()
        assert t.unregister("p1") is False

    def test_tracked_count(self) -> None:
        t = _tracker()
        assert t.tracked_count == 0
        t.register("p1")
        t.register("p2")
        assert t.tracked_count == 2

    def test_is_tracked(self) -> None:
        t = _tracker()
        assert t.is_tracked("p1") is False
        t.register("p1")
        assert t.is_tracked("p1") is True


class TestAvailabilityTrackerStateTransitions:
    """Test state transitions and validation."""

    def test_online_to_degraded(self) -> None:
        t = _tracker()
        t.register("p1")
        result = t.update_state("p1", Availability.DEGRADED.value, reason="test")
        assert result is not None
        assert result.old_state == Availability.ONLINE.value
        assert result.new_state == Availability.DEGRADED.value
        assert t.get_state("p1") == Availability.DEGRADED.value

    def test_online_to_offline(self) -> None:
        t = _tracker()
        t.register("p1")
        result = t.update_state("p1", Availability.OFFLINE.value)
        assert result is not None
        assert t.get_state("p1") == Availability.OFFLINE.value

    def test_degraded_to_online(self) -> None:
        t = _tracker()
        t.register("p1", initial_state=Availability.DEGRADED.value)
        result = t.update_state("p1", Availability.ONLINE.value)
        assert result is not None
        assert t.get_state("p1") == Availability.ONLINE.value

    def test_degraded_to_offline(self) -> None:
        t = _tracker()
        t.register("p1", initial_state=Availability.DEGRADED.value)
        result = t.update_state("p1", Availability.OFFLINE.value)
        assert result is not None
        assert t.get_state("p1") == Availability.OFFLINE.value

    def test_offline_to_degraded(self) -> None:
        t = _tracker()
        t.register("p1", initial_state=Availability.OFFLINE.value)
        result = t.update_state("p1", Availability.DEGRADED.value)
        assert result is not None
        assert t.get_state("p1") == Availability.DEGRADED.value

    def test_offline_to_online_blocked(self) -> None:
        """Progressive recovery: OFFLINE -> ONLINE must go through DEGRADED."""
        t = _tracker(enforce_progressive_recovery=True)
        t.register("p1", initial_state=Availability.OFFLINE.value)
        with pytest.raises(InvalidTransitionError):
            t.update_state("p1", Availability.ONLINE.value)

    def test_offline_to_online_allowed_when_not_enforced(self) -> None:
        t = _tracker(enforce_progressive_recovery=False)
        t.register("p1", initial_state=Availability.OFFLINE.value)
        result = t.update_state("p1", Availability.ONLINE.value)
        assert result is not None
        assert t.get_state("p1") == Availability.ONLINE.value

    def test_same_state_noop(self) -> None:
        t = _tracker()
        t.register("p1")
        result = t.update_state("p1", Availability.ONLINE.value)
        assert result is None

    def test_not_tracked_raises(self) -> None:
        t = _tracker()
        with pytest.raises(ProviderNotTrackedError):
            t.update_state("unknown", Availability.ONLINE.value)

    def test_invalid_state_raises(self) -> None:
        t = _tracker()
        t.register("p1")
        with pytest.raises(ValueError):
            t.update_state("p1", "BROKEN")


class TestAvailabilityTrackerHistory:
    """Test transition history tracking."""

    def test_transitions_recorded(self) -> None:
        t = _tracker()
        t.register("p1")
        t.update_state("p1", Availability.DEGRADED.value, reason="test1")
        t.update_state("p1", Availability.OFFLINE.value, reason="test2")
        transitions = t.get_transitions("p1")
        assert len(transitions) == 2
        assert transitions[0].new_state == Availability.DEGRADED.value
        assert transitions[1].new_state == Availability.OFFLINE.value

    def test_transitions_limit(self) -> None:
        t = _tracker()
        t.register("p1")
        t.update_state("p1", Availability.DEGRADED.value)
        t.update_state("p1", Availability.OFFLINE.value)
        limited = t.get_transitions("p1", limit=1)
        assert len(limited) == 1
        assert limited[0].new_state == Availability.OFFLINE.value

    def test_transitions_not_tracked_raises(self) -> None:
        t = _tracker()
        with pytest.raises(ProviderNotTrackedError):
            t.get_transitions("unknown")

    def test_history_bounded(self) -> None:
        t = _tracker(max_history=3)
        t.register("p1")
        # Create 5 transitions (toggle between states)
        for i in range(5):
            state = Availability.DEGRADED.value if i % 2 == 0 else Availability.ONLINE.value
            t.update_state("p1", state, reason=f"cycle-{i}")
        transitions = t.get_transitions("p1")
        assert len(transitions) <= 3

    def test_transition_has_reason(self) -> None:
        t = _tracker()
        t.register("p1")
        result = t.update_state("p1", Availability.DEGRADED.value, reason="bad probe")
        assert result is not None
        assert result.reason == "bad probe"

    def test_transition_has_timestamp(self) -> None:
        t = _tracker()
        t.register("p1")
        result = t.update_state("p1", Availability.DEGRADED.value)
        assert result is not None
        assert result.timestamp_ms > 0

    def test_transition_to_dict(self) -> None:
        t = StateTransition(
            provider_id="p1",
            old_state=Availability.ONLINE.value,
            new_state=Availability.DEGRADED.value,
            timestamp_ms=12345,
            reason="test",
        )
        d = t.to_dict()
        assert d["provider_id"] == "p1"
        assert d["old_state"] == "ONLINE"
        assert d["new_state"] == "DEGRADED"


class TestAvailabilityTrackerQueries:
    """Test query methods."""

    def test_list_by_state(self) -> None:
        t = _tracker()
        t.register("p1")
        t.register("p2", initial_state=Availability.DEGRADED.value)
        t.register("p3")
        online = t.list_by_state(Availability.ONLINE.value)
        assert sorted(online) == ["p1", "p3"]

    def test_summary(self) -> None:
        t = _tracker()
        t.register("p1")
        t.register("p2", initial_state=Availability.DEGRADED.value)
        t.register("p3", initial_state=Availability.OFFLINE.value)
        s = t.summary()
        assert s[Availability.ONLINE.value] == 1
        assert s[Availability.DEGRADED.value] == 1
        assert s[Availability.OFFLINE.value] == 1

    def test_repr(self) -> None:
        t = _tracker()
        t.register("p1")
        r = repr(t)
        assert "AvailabilityTracker" in r
        assert "tracked=1" in r


class TestAvailabilityTrackerEvents:
    """Test event emission."""

    def test_event_emitted_on_change(self) -> None:
        port = FakeEventPort()
        t = _tracker(event_port=port)
        t.register("p1")
        t.update_state("p1", Availability.DEGRADED.value, reason="test")
        assert len(port.events) == 1
        etype, payload = port.events[0]
        assert etype == EVENT_AVAILABILITY_CHANGED
        assert payload["provider_id"] == "p1"
        assert payload["old_state"] == Availability.ONLINE.value
        assert payload["new_state"] == Availability.DEGRADED.value

    def test_no_event_on_noop(self) -> None:
        port = FakeEventPort()
        t = _tracker(event_port=port)
        t.register("p1")
        t.update_state("p1", Availability.ONLINE.value)  # same state
        assert len(port.events) == 0

    def test_failing_event_port_no_crash(self) -> None:
        port = FailingEventPort()
        t = _tracker(event_port=port)
        t.register("p1")
        # Should not raise
        t.update_state("p1", Availability.DEGRADED.value)


class TestAvailabilityTrackerRegistrySync:
    """Test CapabilityRegistry synchronization callback."""

    def test_registry_updater_called(self) -> None:
        calls: List[tuple[str, str]] = []

        def updater(pid: str, avail: str) -> None:
            calls.append((pid, avail))

        t = _tracker(registry_updater=updater)
        t.register("p1")
        t.update_state("p1", Availability.DEGRADED.value)
        assert len(calls) == 1
        assert calls[0] == ("p1", Availability.DEGRADED.value)

    def test_failing_updater_no_crash(self) -> None:
        def bad_updater(pid: str, avail: str) -> None:
            raise RuntimeError("sync fail")

        t = _tracker(registry_updater=bad_updater)
        t.register("p1")
        t.update_state("p1", Availability.DEGRADED.value)


class TestAvailabilityTrackerCBCallback:
    """Test the on_state_change callback for CircuitBreaker integration."""

    def test_cb_closed_maps_to_online(self) -> None:
        t = _tracker()
        t.register("p1", initial_state=Availability.DEGRADED.value)
        t.on_state_change("p1", CircuitBreakerState.HALF_OPEN, CircuitBreakerState.CLOSED)
        assert t.get_state("p1") == Availability.ONLINE.value

    def test_cb_half_open_maps_to_degraded(self) -> None:
        t = _tracker()
        t.register("p1")
        t.on_state_change("p1", CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN)
        assert t.get_state("p1") == Availability.DEGRADED.value

    def test_cb_open_maps_to_offline(self) -> None:
        t = _tracker()
        t.register("p1")
        t.on_state_change("p1", CircuitBreakerState.CLOSED, CircuitBreakerState.OPEN)
        # ONLINE -> OFFLINE is valid (allowed)
        assert t.get_state("p1") == Availability.OFFLINE.value

    def test_cb_auto_registers_provider(self) -> None:
        t = _tracker()
        t.on_state_change("new_p", CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN)
        assert t.is_tracked("new_p")
        assert t.get_state("new_p") == Availability.DEGRADED.value

    def test_cb_recovery_through_intermediate(self) -> None:
        """CB CLOSED from OPEN should recover via DEGRADED intermediate."""
        t = _tracker()
        t.register("p1", initial_state=Availability.OFFLINE.value)
        t.on_state_change("p1", CircuitBreakerState.OPEN, CircuitBreakerState.CLOSED)
        # Should have gone OFFLINE -> DEGRADED -> ONLINE
        assert t.get_state("p1") == Availability.ONLINE.value

    def test_cb_string_states_accepted(self) -> None:
        t = _tracker()
        t.register("p1")
        t.on_state_change("p1", "CLOSED", "OPEN")
        assert t.get_state("p1") == Availability.OFFLINE.value


class TestStateTransitionFrozen:
    """Test that StateTransition is immutable."""

    def test_frozen(self) -> None:
        st = StateTransition(provider_id="p1")
        with pytest.raises(AttributeError):
            st.provider_id = "p2"  # type: ignore[misc]


class TestAvailabilityTrackerValidTransitions:
    """Test the VALID_TRANSITIONS constant."""

    def test_online_can_go_to_degraded_and_offline(self) -> None:
        valid = VALID_TRANSITIONS[Availability.ONLINE.value]
        assert Availability.DEGRADED.value in valid
        assert Availability.OFFLINE.value in valid

    def test_offline_cannot_go_to_online(self) -> None:
        valid = VALID_TRANSITIONS[Availability.OFFLINE.value]
        assert Availability.ONLINE.value not in valid

    def test_degraded_can_go_either_way(self) -> None:
        valid = VALID_TRANSITIONS[Availability.DEGRADED.value]
        assert Availability.ONLINE.value in valid
        assert Availability.OFFLINE.value in valid


# ======================================================================
# 3.6.1: HealthChecker tests
# ======================================================================


class TestHealthCheckerSingleProvider:
    """Test check_provider() with various outcomes."""

    async def test_healthy_provider(self) -> None:
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
        )
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.HEALTHY.value
        assert result.error is None
        assert result.latency_ms >= 0

    async def test_unhealthy_provider(self) -> None:
        provider = FakeProvider(
            status=ProviderStatus.UNHEALTHY.value,
            error="connection refused",
        )
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
            config=HealthCheckerConfig(failure_threshold=1),
        )
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.UNHEALTHY.value
        assert result.changed is True

    async def test_degraded_provider(self) -> None:
        provider = FakeProvider(status=ProviderStatus.DEGRADED.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
        )
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.DEGRADED.value

    async def test_provider_exception(self) -> None:
        provider = FakeProvider(raise_on_check=RuntimeError("crash"))
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
            config=HealthCheckerConfig(failure_threshold=1),
        )
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.UNHEALTHY.value
        assert "crash" in (result.error or "")

    async def test_provider_timeout(self) -> None:
        provider = FakeProvider(delay_s=5.0)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
            config=HealthCheckerConfig(check_timeout_s=0),
        )
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.DEGRADED.value
        assert "timed out" in (result.error or "")

    async def test_unknown_provider(self) -> None:
        checker = _checker()
        result = await checker.check_provider("nonexistent")
        assert result.status == ProviderStatus.UNKNOWN.value
        assert "No provider instance" in (result.error or "")

    async def test_status_change_tracked(self) -> None:
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
        )
        result = await checker.check_provider("p1")
        assert result.changed is True  # UNKNOWN -> HEALTHY
        assert result.old_status == ProviderStatus.UNKNOWN.value

    async def test_no_change_on_same_status(self) -> None:
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
        )
        await checker.check_provider("p1")
        result = await checker.check_provider("p1")
        assert result.changed is False


class TestHealthCheckerConsecutiveFailures:
    """Test the consecutive failure threshold logic."""

    async def test_single_failure_marks_degraded(self) -> None:
        """With threshold > 1, first failure should not mark UNHEALTHY."""
        provider = FakeProvider(
            status=ProviderStatus.UNHEALTHY.value,
            error="fail",
        )
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
            config=HealthCheckerConfig(failure_threshold=3),
        )
        result = await checker.check_provider("p1")
        # First failure, consecutive < threshold(3), stays UNHEALTHY
        # because the provider itself returns UNHEALTHY
        assert result.status == ProviderStatus.UNHEALTHY.value

    async def test_consecutive_failures_reach_threshold(self) -> None:
        provider = FakeProvider(raise_on_check=RuntimeError("fail"))
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
            config=HealthCheckerConfig(failure_threshold=2),
        )
        # First check (consecutive=1, < threshold=2)
        r1 = await checker.check_provider("p1")
        # Second check (consecutive=2, >= threshold=2)
        r2 = await checker.check_provider("p1")
        assert r2.status == ProviderStatus.UNHEALTHY.value

    async def test_success_resets_consecutive_failures(self) -> None:
        provider = FakeProvider(raise_on_check=RuntimeError("fail"))
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
            config=HealthCheckerConfig(failure_threshold=3),
        )
        await checker.check_provider("p1")
        await checker.check_provider("p1")
        # Now make provider healthy
        provider.raise_on_check = None
        provider.status = ProviderStatus.HEALTHY.value
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.HEALTHY.value

        # Check internal state
        state = checker.get_check_state("p1")
        assert state is not None
        assert state["consecutive_failures"] == 0


class TestHealthCheckerCheckAll:
    """Test check_all() across multiple providers."""

    async def test_check_all_multiple_providers(self) -> None:
        providers = {
            "p1": FakeProvider(status=ProviderStatus.HEALTHY.value),
            "p2": FakeProvider(status=ProviderStatus.DEGRADED.value),
        }
        reg = FakeProviderRegistry()
        reg.register("p1")
        reg.register("p2")
        tracker = AvailabilityTracker()
        checker = _checker(
            providers=providers,
            registry=reg,
            tracker=tracker,
        )
        results = await checker.check_all()
        assert len(results) == 2
        statuses = {r.provider_id: r.status for r in results}
        assert statuses["p1"] == ProviderStatus.HEALTHY.value
        assert statuses["p2"] == ProviderStatus.DEGRADED.value

    async def test_check_all_increments_cycle_count(self) -> None:
        checker = _checker(providers={"p1": FakeProvider()})
        assert checker.cycle_count == 0
        await checker.check_all()
        assert checker.cycle_count == 1
        await checker.check_all()
        assert checker.cycle_count == 2

    async def test_check_all_skips_unregistered_instances(self) -> None:
        """Only checks providers that are in both registry AND instances."""
        reg = FakeProviderRegistry()
        reg.register("p1")
        reg.register("p2")
        # Only p1 has an instance
        checker = _checker(
            providers={"p1": FakeProvider()},
            registry=reg,
        )
        results = await checker.check_all()
        assert len(results) == 1
        assert results[0].provider_id == "p1"


class TestHealthCheckerEvents:
    """Test event emission."""

    async def test_event_on_status_change(self) -> None:
        port = FakeEventPort()
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
            event_port=port,
        )
        await checker.check_provider("p1")
        health_events = [e for e in port.events if e[0] == EVENT_HEALTH_CHANGED]
        assert len(health_events) == 1
        _, payload = health_events[0]
        assert payload["provider_id"] == "p1"
        assert payload["new_status"] == ProviderStatus.HEALTHY.value

    async def test_no_event_on_same_status(self) -> None:
        port = FakeEventPort()
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
            event_port=port,
        )
        await checker.check_provider("p1")
        port.events.clear()
        await checker.check_provider("p1")
        health_events = [e for e in port.events if e[0] == EVENT_HEALTH_CHANGED]
        assert len(health_events) == 0

    async def test_failing_event_port_no_crash(self) -> None:
        port = FailingEventPort()
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
            event_port=port,
        )
        # Should not raise
        await checker.check_provider("p1")


class TestHealthCheckerRegistryUpdate:
    """Test ProviderRegistry health cache updates."""

    async def test_registry_health_updated(self) -> None:
        reg = FakeProviderRegistry()
        reg.register("p1")
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            registry=reg,
            tracker=tracker,
        )
        await checker.check_provider("p1")
        assert reg._health["p1"]["status"] == ProviderStatus.HEALTHY.value

    async def test_registry_health_error_recorded(self) -> None:
        reg = FakeProviderRegistry()
        reg.register("p1")
        provider = FakeProvider(raise_on_check=RuntimeError("oops"))
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            registry=reg,
            tracker=tracker,
        )
        await checker.check_provider("p1")
        assert "oops" in (reg._health["p1"]["error"] or "")


# ======================================================================
# 3.6.3: Circuit Breaker integration tests
# ======================================================================


class TestHealthCheckerCBIntegration:
    """Test bidirectional CB <-> HealthChecker integration."""

    async def test_healthy_signals_allow_probe_on_open_cb(self) -> None:
        """When health check succeeds and CB is OPEN, signal allow_probe."""
        cb = FakeCircuitBreaker("p1", state=CircuitBreakerState.OPEN)
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            breakers={"p1": cb},
            tracker=tracker,
        )
        await checker.check_provider("p1")
        assert cb.allow_probe_calls == 1

    async def test_unhealthy_trips_closed_cb(self) -> None:
        """When health check fails and CB is CLOSED, trip the CB."""
        cb = FakeCircuitBreaker("p1", state=CircuitBreakerState.CLOSED)
        provider = FakeProvider(
            status=ProviderStatus.UNHEALTHY.value,
            error="down",
        )
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            breakers={"p1": cb},
            tracker=tracker,
            config=HealthCheckerConfig(failure_threshold=1),
        )
        await checker.check_provider("p1")
        assert cb.trip_calls == 1

    async def test_healthy_no_action_on_closed_cb(self) -> None:
        """Healthy check on already-CLOSED CB should not call allow_probe."""
        cb = FakeCircuitBreaker("p1", state=CircuitBreakerState.CLOSED)
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            breakers={"p1": cb},
            tracker=tracker,
        )
        await checker.check_provider("p1")
        assert cb.allow_probe_calls == 0
        assert cb.trip_calls == 0

    async def test_unhealthy_no_double_trip_on_open_cb(self) -> None:
        """UNHEALTHY check on already-OPEN CB should not trip again."""
        cb = FakeCircuitBreaker("p1", state=CircuitBreakerState.OPEN)
        provider = FakeProvider(
            status=ProviderStatus.UNHEALTHY.value,
            error="down",
        )
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            breakers={"p1": cb},
            tracker=tracker,
            config=HealthCheckerConfig(failure_threshold=1),
        )
        await checker.check_provider("p1")
        assert cb.trip_calls == 0  # Already open, no trip

    async def test_no_cb_registered_works(self) -> None:
        """HealthChecker works fine without CB integration."""
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
        )
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.HEALTHY.value

    async def test_register_circuit_breaker(self) -> None:
        """Test dynamic CB registration."""
        cb = FakeCircuitBreaker("p1", state=CircuitBreakerState.OPEN)
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
        )
        checker.register_circuit_breaker("p1", cb)
        await checker.check_provider("p1")
        assert cb.allow_probe_calls == 1


class TestHealthCheckerCBCallback:
    """Test the on_cb_state_change callback (3.6.3)."""

    async def test_cb_open_triggers_immediate_check(self) -> None:
        """When CB goes OPEN, an immediate health check should be scheduled."""
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        cb = FakeCircuitBreaker("p1", state=CircuitBreakerState.OPEN)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            breakers={"p1": cb},
            tracker=tracker,
        )
        # Trigger the callback (this should schedule immediate check)
        checker.on_cb_state_change("p1", CircuitBreakerState.CLOSED, CircuitBreakerState.OPEN)
        # Allow tasks to run
        await asyncio.sleep(0.05)
        # The immediate check should have checked the provider
        assert provider.check_count >= 1

    async def test_cb_non_open_no_immediate_check(self) -> None:
        """Non-OPEN transitions should not trigger immediate check."""
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
        )
        checker.on_cb_state_change("p1", CircuitBreakerState.OPEN, CircuitBreakerState.HALF_OPEN)
        await asyncio.sleep(0.05)
        assert provider.check_count == 0


class TestHealthCheckerStartStop:
    """Test the periodic loop."""

    async def test_start_stop(self) -> None:
        checker = _checker(
            providers={"p1": FakeProvider()},
            config=HealthCheckerConfig(default_interval_s=60),
        )
        await checker.start()
        assert checker.is_running is True
        await checker.stop()
        assert checker.is_running is False

    async def test_double_start_idempotent(self) -> None:
        checker = _checker(config=HealthCheckerConfig(default_interval_s=60))
        await checker.start()
        await checker.start()
        assert checker.is_running is True
        await checker.stop()

    async def test_stop_without_start(self) -> None:
        checker = _checker()
        await checker.stop()
        assert checker.is_running is False


class TestHealthCheckerConfig:
    """Test HealthCheckerConfig."""

    def test_defaults(self) -> None:
        c = HealthCheckerConfig()
        assert c.default_interval_s == DEFAULT_CHECK_INTERVAL_S
        assert c.failure_threshold == DEFAULT_FAILURE_THRESHOLD
        assert c.check_timeout_s == DEFAULT_CHECK_TIMEOUT_S

    def test_per_type_interval(self) -> None:
        c = HealthCheckerConfig(
            per_type_interval_s={"MCP": 10, "WASM": 5},
        )
        assert c.get_interval("MCP") == 10
        assert c.get_interval("WASM") == 5
        assert c.get_interval("BRIDGE") == DEFAULT_CHECK_INTERVAL_S

    def test_frozen(self) -> None:
        c = HealthCheckerConfig()
        with pytest.raises(AttributeError):
            c.default_interval_s = 99  # type: ignore[misc]


class TestHealthCheckResultType:
    """Test HealthCheckResult data type."""

    def test_defaults(self) -> None:
        r = HealthCheckResult()
        assert r.provider_id == ""
        assert r.status == ProviderStatus.UNKNOWN.value
        assert r.changed is False

    def test_to_dict(self) -> None:
        r = HealthCheckResult(
            provider_id="p1",
            status=ProviderStatus.HEALTHY.value,
            latency_ms=10,
            changed=True,
        )
        d = r.to_dict()
        assert d["provider_id"] == "p1"
        assert d["status"] == "HEALTHY"
        assert d["latency_ms"] == 10
        assert d["changed"] is True

    def test_frozen(self) -> None:
        r = HealthCheckResult()
        with pytest.raises(AttributeError):
            r.provider_id = "x"  # type: ignore[misc]


class TestHealthCheckerProviderManagement:
    """Test provider instance registration."""

    async def test_register_provider_instance(self) -> None:
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        checker = _checker()
        checker.register_provider_instance("p1", provider)
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.HEALTHY.value

    async def test_unregister_provider_instance(self) -> None:
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        checker = _checker(providers={"p1": provider})
        checker.unregister_provider_instance("p1")
        result = await checker.check_provider("p1")
        assert result.status == ProviderStatus.UNKNOWN.value

    def test_repr(self) -> None:
        checker = _checker(
            providers={"p1": FakeProvider()},
            breakers={"p1": FakeCircuitBreaker("p1")},
        )
        r = repr(checker)
        assert "HealthChecker" in r
        assert "providers=1" in r
        assert "breakers=1" in r


class TestHealthCheckerDiagnostics:
    """Test get_check_state diagnostics."""

    async def test_get_check_state(self) -> None:
        provider = FakeProvider(status=ProviderStatus.HEALTHY.value)
        tracker = AvailabilityTracker()
        checker = _checker(
            providers={"p1": provider},
            tracker=tracker,
        )
        await checker.check_provider("p1")
        state = checker.get_check_state("p1")
        assert state is not None
        assert state["last_status"] == ProviderStatus.HEALTHY.value
        assert state["consecutive_failures"] == 0

    def test_get_check_state_not_checked(self) -> None:
        checker = _checker()
        assert checker.get_check_state("p1") is None


# ======================================================================
# Module exports
# ======================================================================


class TestModuleExports:
    """Test that __init__.py exports are accessible."""

    def test_all_exports_importable(self) -> None:
        import k1.fabric.health as mod
        from k1.fabric.health import __all__

        for name in __all__:
            assert hasattr(mod, name), f"Missing export: {name}"

    def test_all_list_count(self) -> None:
        from k1.fabric.health import __all__

        assert len(__all__) == 16

    def test_event_constants(self) -> None:
        from k1.fabric.health import EVENT_AVAILABILITY_CHANGED, EVENT_HEALTH_CHANGED

        assert "availability" in EVENT_AVAILABILITY_CHANGED
        assert "health" in EVENT_HEALTH_CHANGED

    def test_default_constants(self) -> None:
        from k1.fabric.health import (
            DEFAULT_CHECK_INTERVAL_S,
            DEFAULT_CHECK_TIMEOUT_S,
            DEFAULT_FAILURE_THRESHOLD,
            DEFAULT_MAX_HISTORY,
        )

        assert DEFAULT_CHECK_INTERVAL_S == 30
        assert DEFAULT_CHECK_TIMEOUT_S == 10
        assert DEFAULT_FAILURE_THRESHOLD == 3
        assert DEFAULT_MAX_HISTORY == 100
