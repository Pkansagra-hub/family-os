"""
Tests for E-0.5.16 -- Concierge POC Circuit Breakers Need HALF_OPEN.

Verifies the degradation CircuitBreaker now supports the full 3-state
pattern (CLOSED / OPEN / HALF_OPEN) matching k1.fabric.circuit_breaker.

State machine:
    CLOSED  --[failure threshold]--> OPEN
    OPEN    --[half_open_after_ms]--> HALF_OPEN
    HALF_OPEN --[success]--> CLOSED
    HALF_OPEN --[failure]--> OPEN
"""

from __future__ import annotations

from unittest.mock import patch

from k1.concierge.orchestrator.degradation import (
    CircuitBreaker,
    cb_fabric,
    cb_orchestrator,
    cb_planner,
)
from k1.fabric.circuit_breaker import CircuitBreakerState

# =====================================================================
# State enum integration
# =====================================================================


class TestCircuitBreakerStateEnum:
    """CircuitBreaker.state returns CircuitBreakerState enum values."""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitBreakerState.CLOSED

    def test_state_enum_values(self):
        assert CircuitBreakerState.CLOSED == "CLOSED"
        assert CircuitBreakerState.OPEN == "OPEN"
        assert CircuitBreakerState.HALF_OPEN == "HALF_OPEN"

    def test_is_closed_initially(self):
        cb = CircuitBreaker("test")
        assert cb.is_closed() is True
        assert cb.is_open() is False
        assert cb.is_half_open() is False


# =====================================================================
# Failure threshold → OPEN transition
# =====================================================================


class TestFailureThresholdOpensBreaker:
    """When failure count reaches threshold, breaker transitions to OPEN."""

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 2

    def test_opens_at_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.is_open() is True

    def test_failure_count_tracks_sliding_window(self):
        cb = CircuitBreaker("test", failure_threshold=5, failure_window_ms=100)
        # Record 2 failures
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2


# =====================================================================
# OPEN → HALF_OPEN transition (recovery timeout)
# =====================================================================


class TestOpenToHalfOpen:
    """After half_open_after_ms elapses, OPEN transitions to HALF_OPEN."""

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=1, half_open_after_ms=100)
        cb.record_failure()  # → OPEN
        assert cb.state == CircuitBreakerState.OPEN

        # Simulate time passing beyond half_open_after_ms
        with patch.object(
            CircuitBreaker,
            "_now_ms",
            staticmethod(lambda: cb._opened_at_ms + 200),
        ):
            assert cb.state == CircuitBreakerState.HALF_OPEN
            assert cb.is_half_open() is True

    def test_stays_open_before_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=1, half_open_after_ms=10_000)
        cb.record_failure()  # → OPEN
        # Without time manipulation, still OPEN (timeout hasn't elapsed)
        assert cb.state == CircuitBreakerState.OPEN


# =====================================================================
# HALF_OPEN → CLOSED (probe success)
# =====================================================================


class TestHalfOpenProbeSuccess:
    """A successful probe in HALF_OPEN resets to CLOSED."""

    def test_success_in_half_open_closes(self):
        cb = CircuitBreaker("test", failure_threshold=1, half_open_after_ms=0)
        cb.record_failure()  # → OPEN

        # Immediately transition to HALF_OPEN (half_open_after_ms=0)
        with patch.object(
            CircuitBreaker,
            "_now_ms",
            staticmethod(lambda: cb._opened_at_ms + 1),
        ):
            assert cb.state == CircuitBreakerState.HALF_OPEN
            cb.record_success()
            assert cb.state == CircuitBreakerState.CLOSED
            assert cb.failure_count == 0


# =====================================================================
# HALF_OPEN → OPEN (probe failure)
# =====================================================================


class TestHalfOpenProbeFailure:
    """A failed probe in HALF_OPEN re-opens the breaker."""

    def test_failure_in_half_open_reopens(self):
        cb = CircuitBreaker("test", failure_threshold=1, half_open_after_ms=100)
        cb.record_failure()  # → OPEN

        # Advance time past half_open_after_ms to reach HALF_OPEN
        base_time = cb._opened_at_ms + 200
        with patch.object(
            CircuitBreaker,
            "_now_ms",
            staticmethod(lambda: base_time),
        ):
            assert cb.state == CircuitBreakerState.HALF_OPEN
            cb.record_failure()  # → OPEN (probe failed, new opened_at_ms = base_time)

        # After re-open, the new opened_at_ms is base_time.
        # Without advancing time further, should still be OPEN.
        with patch.object(
            CircuitBreaker,
            "_now_ms",
            staticmethod(lambda: base_time + 10),  # only 10ms, not past 100ms timeout
        ):
            assert cb.state == CircuitBreakerState.OPEN


# =====================================================================
# trip() and reset() (force methods)
# =====================================================================


class TestForceTransitions:
    """trip() and reset() force state transitions."""

    def test_trip_opens_breaker(self):
        cb = CircuitBreaker("test")
        cb.trip()
        assert cb.state == CircuitBreakerState.OPEN

    def test_reset_closes_breaker(self):
        cb = CircuitBreaker("test")
        cb.trip()
        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_force_open_alias(self):
        cb = CircuitBreaker("test")
        cb.force_open()
        assert cb.state == CircuitBreakerState.OPEN

    def test_force_closed_alias(self):
        cb = CircuitBreaker("test")
        cb.force_open()
        cb.force_closed()
        assert cb.state == CircuitBreakerState.CLOSED


# =====================================================================
# Named module-level breakers
# =====================================================================


class TestNamedBreakers:
    """Module-level cb_planner, cb_orchestrator, cb_fabric use 3-state CB."""

    def test_cb_planner_is_circuit_breaker(self):
        assert isinstance(cb_planner, CircuitBreaker)
        assert cb_planner.name == "CB_PLANNER"

    def test_cb_orchestrator_is_circuit_breaker(self):
        assert isinstance(cb_orchestrator, CircuitBreaker)
        assert cb_orchestrator.name == "CB_ORCHESTRATOR"

    def test_cb_fabric_is_circuit_breaker(self):
        assert isinstance(cb_fabric, CircuitBreaker)
        assert cb_fabric.name == "CB_FABRIC"

    def test_named_breakers_have_state_property(self):
        for cb in (cb_planner, cb_orchestrator, cb_fabric):
            assert hasattr(cb, "state")
            assert cb.state in (
                CircuitBreakerState.CLOSED,
                CircuitBreakerState.OPEN,
                CircuitBreakerState.HALF_OPEN,
            )

    def test_named_breakers_support_3_state(self):
        """Each named breaker supports the full 3-state lifecycle."""
        for cb in (cb_planner, cb_orchestrator, cb_fabric):
            cb.reset()  # ensure clean state
            assert cb.is_closed()

            cb.trip()
            assert cb.is_open()

            cb.reset()
            assert cb.is_closed()


# =====================================================================
# Backward compatibility (is_open used by degradation cascade)
# =====================================================================


class TestBackwardCompatibility:
    """is_open() still works for degradation cascade logic."""

    def test_is_open_false_when_closed(self):
        cb = CircuitBreaker("test")
        assert cb.is_open() is False

    def test_is_open_true_when_tripped(self):
        cb = CircuitBreaker("test")
        cb.trip()
        assert cb.is_open() is True

    def test_is_open_false_when_half_open(self):
        """HALF_OPEN allows probe traffic — is_open() returns False."""
        cb = CircuitBreaker("test", failure_threshold=1, half_open_after_ms=0)
        cb.record_failure()  # → OPEN
        with patch.object(
            CircuitBreaker,
            "_now_ms",
            staticmethod(lambda: cb._opened_at_ms + 1),
        ):
            assert cb.is_half_open() is True
            assert cb.is_open() is False  # allows probe

    def test_reset_after_trip(self):
        cb = CircuitBreaker("test")
        cb.trip()
        cb.reset()
        assert cb.is_open() is False
