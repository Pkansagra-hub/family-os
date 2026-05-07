"""Tests for CircuitBreaker (E-MW-5.3).

Covers the 3-state circuit breaker: CLOSED, OPEN, HALF_OPEN.
All tests use a fake clock for deterministic time control.

22 tests organized in 5 test classes.
"""

from __future__ import annotations

import pytest

from k1.memory_writer.health.circuit_breaker import CircuitBreaker, CircuitBreakerState

# ---------------------------------------------------------------------------
# Initial State
# ---------------------------------------------------------------------------


class TestCircuitBreakerInitialState:
    """Tests for initial CircuitBreaker state."""

    def test_initial_state_closed(self) -> None:
        """new CB -> state == CLOSED."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_initial_is_open_false(self) -> None:
        """new CB -> is_open == False."""
        cb = CircuitBreaker()
        assert cb.is_open is False

    def test_initial_consecutive_failures_zero(self) -> None:
        """new CB -> consecutive_failures == 0."""
        cb = CircuitBreaker()
        assert cb.consecutive_failures == 0


# ---------------------------------------------------------------------------
# CLOSED State
# ---------------------------------------------------------------------------


class TestCircuitBreakerClosedState:
    """Tests for CLOSED state behavior."""

    def test_success_keeps_closed(self) -> None:
        """record_success -> still CLOSED."""
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_single_failure_stays_closed(self) -> None:
        """1 failure (threshold=3) -> still CLOSED."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.consecutive_failures == 1

    def test_threshold_minus_one_stays_closed(self) -> None:
        """2 failures (threshold=3) -> still CLOSED."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.consecutive_failures == 2

    def test_success_resets_failure_count(self) -> None:
        """2 failures + 1 success -> consecutive_failures=0."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.consecutive_failures == 0
        assert cb.state == CircuitBreakerState.CLOSED


# ---------------------------------------------------------------------------
# OPEN State
# ---------------------------------------------------------------------------


class TestCircuitBreakerOpenState:
    """Tests for OPEN state behavior."""

    @pytest.fixture()
    def fake_time(self) -> list:
        return [0.0]

    @pytest.fixture()
    def cb(self, fake_time: list) -> CircuitBreaker:
        return CircuitBreaker(
            failure_threshold=3,
            recovery_probe_seconds=30.0,
            clock=lambda: fake_time[0],
        )

    def _trip_open(self, cb: CircuitBreaker) -> None:
        """Helper: push CB from CLOSED to OPEN."""
        for _ in range(3):
            cb.record_failure()

    def test_threshold_failures_opens(self, cb: CircuitBreaker) -> None:
        """3 failures (threshold=3) -> OPEN."""
        self._trip_open(cb)
        assert cb.state == CircuitBreakerState.OPEN

    def test_is_open_true_when_open(self, cb: CircuitBreaker) -> None:
        """OPEN state -> is_open == True."""
        self._trip_open(cb)
        assert cb.is_open is True

    def test_total_trips_incremented(self, cb: CircuitBreaker) -> None:
        """CLOSED -> OPEN -> total_trips == 1."""
        self._trip_open(cb)
        assert cb.total_trips == 1

    def test_open_blocks_within_recovery_window(self, cb: CircuitBreaker, fake_time: list) -> None:
        """OPEN + 10s elapsed (probe=30s) -> still is_open=True."""
        self._trip_open(cb)
        fake_time[0] = 10.0
        assert cb.is_open is True

    def test_open_allows_probe_after_recovery(self, cb: CircuitBreaker, fake_time: list) -> None:
        """OPEN + 31s elapsed -> is_open=False (HALF_OPEN)."""
        self._trip_open(cb)
        fake_time[0] = 31.0
        assert cb.is_open is False
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_consecutive_failures_tracked(self, cb: CircuitBreaker) -> None:
        """3 failures -> consecutive_failures == 3."""
        self._trip_open(cb)
        assert cb.consecutive_failures == 3


# ---------------------------------------------------------------------------
# HALF_OPEN State
# ---------------------------------------------------------------------------


class TestCircuitBreakerHalfOpenState:
    """Tests for HALF_OPEN state behavior."""

    @pytest.fixture()
    def fake_time(self) -> list:
        return [0.0]

    @pytest.fixture()
    def cb_half_open(self, fake_time: list) -> CircuitBreaker:
        """Return a CB in HALF_OPEN state."""
        cb = CircuitBreaker(
            failure_threshold=3,
            recovery_probe_seconds=30.0,
            clock=lambda: fake_time[0],
        )
        # Trip to OPEN
        for _ in range(3):
            cb.record_failure()
        # Advance past recovery window
        fake_time[0] = 31.0
        # Trigger OPEN -> HALF_OPEN transition
        _ = cb.is_open
        assert cb.state == CircuitBreakerState.HALF_OPEN
        return cb

    def test_half_open_allows_one_call(self, cb_half_open: CircuitBreaker) -> None:
        """HALF_OPEN -> is_open=False."""
        assert cb_half_open.is_open is False

    def test_probe_success_closes(self, cb_half_open: CircuitBreaker) -> None:
        """HALF_OPEN + record_success -> CLOSED."""
        cb_half_open.record_success()
        assert cb_half_open.state == CircuitBreakerState.CLOSED

    def test_probe_success_resets_failures(self, cb_half_open: CircuitBreaker) -> None:
        """HALF_OPEN + success -> consecutive_failures=0."""
        cb_half_open.record_success()
        assert cb_half_open.consecutive_failures == 0

    def test_probe_failure_reopens(self, cb_half_open: CircuitBreaker) -> None:
        """HALF_OPEN + record_failure -> OPEN."""
        cb_half_open.record_failure()
        assert cb_half_open.state == CircuitBreakerState.OPEN

    def test_reopen_restarts_recovery_timer(
        self, cb_half_open: CircuitBreaker, fake_time: list
    ) -> None:
        """HALF_OPEN -> OPEN -> must wait full recovery_probe_seconds again."""
        # Fail probe at t=31
        cb_half_open.record_failure()
        assert cb_half_open.state == CircuitBreakerState.OPEN

        # At t=31 + 29 = 60, still within new recovery window
        fake_time[0] = 60.0
        assert cb_half_open.is_open is True

        # At t=31 + 31 = 62, past new recovery window
        fake_time[0] = 62.0
        assert cb_half_open.is_open is False
        assert cb_half_open.state == CircuitBreakerState.HALF_OPEN

    def test_multiple_trips_counted(self, fake_time: list) -> None:
        """CLOSED->OPEN->HALF_OPEN->OPEN -> total_trips==2."""
        cb = CircuitBreaker(
            failure_threshold=3,
            recovery_probe_seconds=30.0,
            clock=lambda: fake_time[0],
        )
        # First trip: CLOSED -> OPEN
        for _ in range(3):
            cb.record_failure()
        assert cb.total_trips == 1

        # OPEN -> HALF_OPEN
        fake_time[0] = 31.0
        _ = cb.is_open

        # HALF_OPEN -> CLOSED (success)
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

        # Second trip: CLOSED -> OPEN
        for _ in range(3):
            cb.record_failure()
        assert cb.total_trips == 2


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


class TestCircuitBreakerReset:
    """Tests for CircuitBreaker.reset()."""

    def test_reset_from_open(self) -> None:
        """OPEN + reset() -> CLOSED, consecutive_failures=0."""
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.consecutive_failures == 0

    def test_reset_from_half_open(self) -> None:
        """HALF_OPEN + reset() -> CLOSED."""
        fake_time = [0.0]
        cb = CircuitBreaker(
            failure_threshold=3,
            recovery_probe_seconds=30.0,
            clock=lambda: fake_time[0],
        )
        for _ in range(3):
            cb.record_failure()
        fake_time[0] = 31.0
        _ = cb.is_open  # trigger HALF_OPEN
        assert cb.state == CircuitBreakerState.HALF_OPEN

        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_reset_idempotent(self) -> None:
        """CLOSED + reset() -> still CLOSED."""
        cb = CircuitBreaker()
        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.consecutive_failures == 0
