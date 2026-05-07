"""M4 Resilience & Cost -- Test CircuitBreakerManager [F48].

Tests per-provider circuit breaker state machine:
CLOSED -> OPEN -> HALF_OPEN -> CLOSED transitions, sliding window
failure counting, cooldown, manifest-driven config.

Covers:
  - CircuitTransition: construction, frozen
  - Registration / unregistration
  - State machine: CLOSED -> OPEN on threshold breach
  - State machine: OPEN -> HALF_OPEN on cooldown expiry
  - State machine: HALF_OPEN -> CLOSED on success
  - State machine: HALF_OPEN -> OPEN on failure
  - Sliding window: failures outside window discarded
  - ICircuitBreakerQuery protocol compliance
  - Multiple providers independent (MH-17)
  - Transition history recording
"""

from __future__ import annotations

import time

import pytest

from k1.model_hub.manifest import CircuitBreakerConfig
from k1.model_hub.services.capability_router import ICircuitBreakerQuery
from k1.model_hub.services.circuit_breaker_manager import CircuitBreakerManager, CircuitTransition
from k1.model_hub.types import CircuitState

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def cbm() -> CircuitBreakerManager:
    mgr = CircuitBreakerManager()
    mgr.register_provider("openai")
    return mgr


@pytest.fixture
def fast_cbm() -> CircuitBreakerManager:
    """CBM with low threshold for quick testing."""
    mgr = CircuitBreakerManager()
    mgr.register_provider(
        "openai",
        config=CircuitBreakerConfig(
            failure_threshold=2,
            failure_window_s=10,
            cooldown_s=1,
        ),
    )
    return mgr


# ===========================================================================
# CircuitTransition Tests
# ===========================================================================


class TestCircuitTransition:
    def test_construction(self) -> None:
        ct = CircuitTransition(
            provider_id="openai",
            old_state=CircuitState.CLOSED,
            new_state=CircuitState.OPEN,
            failure_count=3,
        )
        assert ct.provider_id == "openai"
        assert ct.old_state == CircuitState.CLOSED
        assert ct.new_state == CircuitState.OPEN
        assert ct.failure_count == 3

    def test_frozen(self) -> None:
        ct = CircuitTransition(
            provider_id="openai",
            old_state=CircuitState.CLOSED,
            new_state=CircuitState.OPEN,
        )
        with pytest.raises(AttributeError):
            ct.provider_id = "other"  # type: ignore[misc]


# ===========================================================================
# Registration Tests
# ===========================================================================


class TestRegistration:
    def test_register_provider(self) -> None:
        cbm = CircuitBreakerManager()
        cbm.register_provider("openai")
        assert cbm.is_registered("openai")

    def test_unregister_provider(self) -> None:
        cbm = CircuitBreakerManager()
        cbm.register_provider("openai")
        cbm.unregister_provider("openai")
        assert not cbm.is_registered("openai")

    def test_unregister_unknown_no_error(self) -> None:
        cbm = CircuitBreakerManager()
        cbm.unregister_provider("nonexistent")  # Should not raise

    def test_register_with_config(self) -> None:
        cbm = CircuitBreakerManager()
        config = CircuitBreakerConfig(failure_threshold=5, cooldown_s=60)
        cbm.register_provider("openai", config=config)
        assert cbm.is_registered("openai")

    def test_register_idempotent(self) -> None:
        cbm = CircuitBreakerManager()
        cbm.register_provider("openai")
        cbm.register_provider("openai")  # Should not raise or duplicate
        assert cbm.is_registered("openai")


# ===========================================================================
# Protocol Compliance
# ===========================================================================


class TestProtocolCompliance:
    def test_implements_icircuitbreakerquery(self) -> None:
        cbm = CircuitBreakerManager()
        assert isinstance(cbm, ICircuitBreakerQuery)


# ===========================================================================
# CLOSED State Tests
# ===========================================================================


class TestClosedState:
    def test_initial_state_closed(self, cbm: CircuitBreakerManager) -> None:
        assert cbm.get_state("openai") == CircuitState.CLOSED

    def test_unknown_provider_returns_closed(self) -> None:
        cbm = CircuitBreakerManager()
        assert cbm.get_state("unknown") == CircuitState.CLOSED

    def test_acquire_returns_closed(self, cbm: CircuitBreakerManager) -> None:
        state = cbm.acquire("openai")
        assert state == CircuitState.CLOSED

    def test_failures_below_threshold_stay_closed(self, cbm: CircuitBreakerManager) -> None:
        cbm.record_failure("openai")
        cbm.record_failure("openai")
        # Default threshold is 3, so 2 failures stays CLOSED
        assert cbm.get_state("openai") == CircuitState.CLOSED

    def test_success_in_closed_no_op(self, cbm: CircuitBreakerManager) -> None:
        cbm.record_success("openai")
        assert cbm.get_state("openai") == CircuitState.CLOSED

    def test_failure_count_tracks(self, cbm: CircuitBreakerManager) -> None:
        cbm.record_failure("openai")
        assert cbm.failure_count("openai") >= 1


# ===========================================================================
# CLOSED -> OPEN Transition
# ===========================================================================


class TestClosedToOpen:
    def test_threshold_breach_opens_circuit(self, cbm: CircuitBreakerManager) -> None:
        """3 failures (default threshold) -> OPEN."""
        for _ in range(3):
            cbm.record_failure("openai")
        assert cbm.get_state("openai") == CircuitState.OPEN

    def test_fast_threshold_breach(self, fast_cbm: CircuitBreakerManager) -> None:
        """2 failures (custom threshold=2) -> OPEN."""
        fast_cbm.record_failure("openai")
        fast_cbm.record_failure("openai")
        assert fast_cbm.get_state("openai") == CircuitState.OPEN

    def test_transition_recorded(self, cbm: CircuitBreakerManager) -> None:
        for _ in range(3):
            cbm.record_failure("openai")

        transitions = cbm.transitions
        assert len(transitions) >= 1
        last = transitions[-1]
        assert last.old_state == CircuitState.CLOSED
        assert last.new_state == CircuitState.OPEN
        assert last.provider_id == "openai"

    def test_acquire_returns_open(self, cbm: CircuitBreakerManager) -> None:
        for _ in range(3):
            cbm.record_failure("openai")
        state = cbm.acquire("openai")
        assert state == CircuitState.OPEN


# ===========================================================================
# OPEN -> HALF_OPEN Transition (cooldown)
# ===========================================================================


class TestOpenToHalfOpen:
    def test_cooldown_transitions_to_half_open(self, fast_cbm: CircuitBreakerManager) -> None:
        """After cooldown_s (1s), OPEN -> HALF_OPEN."""
        fast_cbm.record_failure("openai")
        fast_cbm.record_failure("openai")
        assert fast_cbm.get_state("openai") == CircuitState.OPEN

        # Shift opened_at back past cooldown instead of mocking time
        circuit = fast_cbm._circuits["openai"]
        circuit.opened_at = time.monotonic() - 2.0  # 2s > 1s cooldown
        assert fast_cbm.get_state("openai") == CircuitState.HALF_OPEN

    def test_before_cooldown_stays_open(self, fast_cbm: CircuitBreakerManager) -> None:
        fast_cbm.record_failure("openai")
        fast_cbm.record_failure("openai")
        # Immediately after opening, should still be OPEN (cooldown not elapsed)
        assert fast_cbm.get_state("openai") == CircuitState.OPEN


# ===========================================================================
# HALF_OPEN State Tests
# ===========================================================================


class TestHalfOpenState:
    def _make_half_open(self, fast_cbm: CircuitBreakerManager) -> None:
        """Helper to get provider into HALF_OPEN state."""
        fast_cbm.record_failure("openai")
        fast_cbm.record_failure("openai")
        # Force cooldown expiry by patching opened_at
        circuit = fast_cbm._circuits["openai"]
        circuit.opened_at = time.monotonic() - 10.0  # Well past cooldown

    def test_half_open_success_closes(self, fast_cbm: CircuitBreakerManager) -> None:
        """HALF_OPEN + success -> CLOSED."""
        self._make_half_open(fast_cbm)
        assert fast_cbm.get_state("openai") == CircuitState.HALF_OPEN

        fast_cbm.record_success("openai")
        assert fast_cbm.get_state("openai") == CircuitState.CLOSED

    def test_half_open_failure_reopens(self, fast_cbm: CircuitBreakerManager) -> None:
        """HALF_OPEN + failure -> OPEN."""
        self._make_half_open(fast_cbm)
        assert fast_cbm.get_state("openai") == CircuitState.HALF_OPEN

        fast_cbm.record_failure("openai")
        assert fast_cbm.get_state("openai") == CircuitState.OPEN

    def test_half_open_single_probe(self, fast_cbm: CircuitBreakerManager) -> None:
        """Only one probe request in HALF_OPEN."""
        self._make_half_open(fast_cbm)
        state1 = fast_cbm.acquire("openai")
        assert state1 == CircuitState.HALF_OPEN

        # Second acquire should return OPEN (probe in flight)
        state2 = fast_cbm.acquire("openai")
        assert state2 == CircuitState.OPEN


# ===========================================================================
# Multiple Providers (MH-17)
# ===========================================================================


class TestMultipleProviders:
    def test_independent_states(self) -> None:
        """Each provider has independent circuit state."""
        cbm = CircuitBreakerManager()
        cbm.register_provider("openai")
        cbm.register_provider("anthropic")

        # Open openai
        for _ in range(3):
            cbm.record_failure("openai")
        assert cbm.get_state("openai") == CircuitState.OPEN
        assert cbm.get_state("anthropic") == CircuitState.CLOSED

    def test_independent_configs(self) -> None:
        cbm = CircuitBreakerManager()
        cbm.register_provider("openai", CircuitBreakerConfig(failure_threshold=2))
        cbm.register_provider("anthropic", CircuitBreakerConfig(failure_threshold=5))

        cbm.record_failure("openai")
        cbm.record_failure("openai")
        assert cbm.get_state("openai") == CircuitState.OPEN

        cbm.record_failure("anthropic")
        cbm.record_failure("anthropic")
        assert cbm.get_state("anthropic") == CircuitState.CLOSED


# ===========================================================================
# Sliding Window Tests
# ===========================================================================


class TestSlidingWindow:
    def test_failures_outside_window_discarded(self) -> None:
        """Failures older than failure_window_s are not counted."""
        cbm = CircuitBreakerManager()
        cbm.register_provider(
            "openai",
            CircuitBreakerConfig(failure_threshold=3, failure_window_s=5),
        )
        # Record 2 failures
        cbm.record_failure("openai")
        cbm.record_failure("openai")

        # Age them out by manipulating timestamps
        circuit = cbm._circuits["openai"]
        circuit.failure_timestamps = [time.monotonic() - 10.0, time.monotonic() - 10.0]

        # New failure should NOT breach threshold (old ones pruned)
        cbm.record_failure("openai")
        assert cbm.get_state("openai") == CircuitState.CLOSED

    def test_failure_count_unknown_provider(self) -> None:
        cbm = CircuitBreakerManager()
        assert cbm.failure_count("unknown") == 0


# ===========================================================================
# Record on unknown provider
# ===========================================================================


class TestUnknownProvider:
    def test_record_failure_unknown_no_error(self) -> None:
        cbm = CircuitBreakerManager()
        cbm.record_failure("unknown")  # Should not raise

    def test_record_success_unknown_no_error(self) -> None:
        cbm = CircuitBreakerManager()
        cbm.record_success("unknown")  # Should not raise


# ===========================================================================
# Re-exports
# ===========================================================================


class TestCircuitBreakerReExports:
    def test_manager_reexport(self) -> None:
        from k1.model_hub.services import CircuitBreakerManager as Reexported

        assert Reexported is CircuitBreakerManager

    def test_transition_reexport(self) -> None:
        from k1.model_hub.services import CircuitTransition as Reexported

        assert Reexported is CircuitTransition
