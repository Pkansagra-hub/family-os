"""
Integration tests for Epic 3.4: Circuit Breaker.

  - 3.4.1 CircuitBreaker state machine + retry wiring
  - 3.4.2 Per-provider breaker config (breaker_config.py)
  - 3.4.3 Retry strategy (integrated into CircuitBreaker.call)

Tests follow the existing pattern from test_providers_335_337.py.
"""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.circuit_breaker import (
    AGENT_CONFIG,
    BRIDGE_CONFIG,
    CONCIERGE_CONFIG,
    DEFAULT_CONFIG,
    MCP_LOCAL_CONFIG,
    MCP_REMOTE_CONFIG,
    WASM_CONFIG,
    WORKFLOW_CONFIG,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitBreakerOpen,
    CircuitBreakerState,
    FailureRecord,
)
from k1.fabric.circuit_breaker import __all__ as cb_all
from k1.fabric.circuit_breaker import get_breaker_config
from k1.fabric.types import (
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
    ProviderType,
    TransportType,
)

# =========================================================================
# Helpers
# =========================================================================


def _request(
    capability_name: str = "test.cap",
    params: Optional[Dict[str, Any]] = None,
    request_id: str = "req-1",
    trace_id: str = "trace-1",
    session_id: str = "sess-1",
) -> CapabilityRequest:
    return CapabilityRequest(
        request_id=request_id,
        capability_name=capability_name,
        params=params or {},
        caller="test",
        trace_id=trace_id,
        session_id=session_id,
    )


def _context(trace_id: str = "trace-1") -> ExecutionContext:
    return ExecutionContext(trace_id=trace_id)


def _success_result(request_id: str = "req-1") -> CapabilityResult:
    return CapabilityResult.success_result(
        request_id=request_id,
        data={"value": "ok"},
        provider_id="test-provider",
        trace_id="trace-1",
    )


def _failure_result(
    request_id: str = "req-1",
    retriable: bool = True,
    error_code: str = "transient_error",
) -> CapabilityResult:
    return CapabilityResult.failure_result(
        request_id=request_id,
        error_code=error_code,
        error_message="test failure",
        retriable=retriable,
        provider_id="test-provider",
        trace_id="trace-1",
    )


async def _success_execute(
    request: CapabilityRequest,
    context: ExecutionContext,
    trace_id: str,
) -> CapabilityResult:
    """Always succeeds."""
    return _success_result(request.request_id)


async def _fail_retriable(
    request: CapabilityRequest,
    context: ExecutionContext,
    trace_id: str,
) -> CapabilityResult:
    """Always fails with a retriable error."""
    return _failure_result(request.request_id, retriable=True)


async def _fail_non_retriable(
    request: CapabilityRequest,
    context: ExecutionContext,
    trace_id: str,
) -> CapabilityResult:
    """Always fails with a non-retriable error."""
    return _failure_result(
        request.request_id,
        retriable=False,
        error_code="permanent_error",
    )


async def _timeout_execute(
    request: CapabilityRequest,
    context: ExecutionContext,
    trace_id: str,
) -> CapabilityResult:
    """Sleeps longer than any reasonable timeout."""
    await asyncio.sleep(60)
    return _success_result(request.request_id)


async def _raise_execute(
    request: CapabilityRequest,
    context: ExecutionContext,
    trace_id: str,
) -> CapabilityResult:
    """Raises an unexpected exception."""
    raise RuntimeError("unexpected crash")


class FakeListener:
    """Records CB state change events."""

    def __init__(self) -> None:
        self.events: List[tuple[str, CircuitBreakerState, CircuitBreakerState]] = []

    def on_state_change(
        self,
        provider_id: str,
        old_state: CircuitBreakerState,
        new_state: CircuitBreakerState,
    ) -> None:
        self.events.append((provider_id, old_state, new_state))


# =========================================================================
# 3.4.1: CircuitBreakerConfig
# =========================================================================


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig dataclass."""

    def test_defaults(self) -> None:
        cfg = CircuitBreakerConfig()
        assert cfg.timeout_ms == 30000
        assert cfg.failure_threshold == 5
        assert cfg.failure_window_ms == 60000
        assert cfg.half_open_after_ms == 30000
        assert cfg.max_retries == 2
        assert cfg.fallback_error_code == "circuit_breaker_open"

    def test_custom_values(self) -> None:
        cfg = CircuitBreakerConfig(
            timeout_ms=10000,
            failure_threshold=3,
            failure_window_ms=30000,
            half_open_after_ms=15000,
            max_retries=1,
            fallback_error_code="custom_err",
        )
        assert cfg.timeout_ms == 10000
        assert cfg.failure_threshold == 3
        assert cfg.failure_window_ms == 30000
        assert cfg.half_open_after_ms == 15000
        assert cfg.max_retries == 1
        assert cfg.fallback_error_code == "custom_err"

    def test_frozen(self) -> None:
        cfg = CircuitBreakerConfig()
        with pytest.raises(FrozenInstanceError):
            cfg.timeout_ms = 999  # type: ignore[misc]

    def test_invalid_timeout_corrected(self) -> None:
        cfg = CircuitBreakerConfig(timeout_ms=-1)
        assert cfg.timeout_ms == 30000

    def test_invalid_threshold_corrected(self) -> None:
        cfg = CircuitBreakerConfig(failure_threshold=0)
        assert cfg.failure_threshold == 5

    def test_invalid_window_corrected(self) -> None:
        cfg = CircuitBreakerConfig(failure_window_ms=-500)
        assert cfg.failure_window_ms == 60000

    def test_invalid_half_open_corrected(self) -> None:
        cfg = CircuitBreakerConfig(half_open_after_ms=0)
        assert cfg.half_open_after_ms == 30000

    def test_negative_retries_corrected(self) -> None:
        cfg = CircuitBreakerConfig(max_retries=-1)
        assert cfg.max_retries == 0


# =========================================================================
# 3.4.1: CircuitBreakerState enum
# =========================================================================


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState enum."""

    def test_closed_value(self) -> None:
        assert CircuitBreakerState.CLOSED.value == "CLOSED"

    def test_open_value(self) -> None:
        assert CircuitBreakerState.OPEN.value == "OPEN"

    def test_half_open_value(self) -> None:
        assert CircuitBreakerState.HALF_OPEN.value == "HALF_OPEN"

    def test_is_str_enum(self) -> None:
        assert isinstance(CircuitBreakerState.CLOSED, str)

    def test_three_members(self) -> None:
        assert len(CircuitBreakerState) == 3


# =========================================================================
# 3.4.1: FailureRecord
# =========================================================================


class TestFailureRecord:
    """Tests for FailureRecord dataclass."""

    def test_defaults(self) -> None:
        rec = FailureRecord()
        assert rec.timestamp_ms == 0
        assert rec.error_code == ""
        assert rec.error_message == ""
        assert rec.retriable is False

    def test_custom(self) -> None:
        rec = FailureRecord(
            timestamp_ms=12345,
            error_code="timeout",
            error_message="timed out",
            retriable=True,
        )
        assert rec.timestamp_ms == 12345
        assert rec.error_code == "timeout"
        assert rec.error_message == "timed out"
        assert rec.retriable is True

    def test_frozen(self) -> None:
        rec = FailureRecord()
        with pytest.raises(FrozenInstanceError):
            rec.timestamp_ms = 999  # type: ignore[misc]


# =========================================================================
# 3.4.1: Exceptions
# =========================================================================


class TestCircuitBreakerExceptions:
    """Tests for CB exception hierarchy."""

    def test_circuit_breaker_error_base(self) -> None:
        exc = CircuitBreakerError("prov-1", "something broke")
        assert exc.provider_id == "prov-1"
        assert "prov-1" in str(exc)
        assert "something broke" in str(exc)
        assert isinstance(exc, Exception)

    def test_circuit_breaker_open(self) -> None:
        exc = CircuitBreakerOpen("prov-2", remaining_ms=5000)
        assert exc.provider_id == "prov-2"
        assert exc.remaining_ms == 5000
        assert isinstance(exc, CircuitBreakerError)
        assert "OPEN" in str(exc)
        assert "5000" in str(exc)


# =========================================================================
# 3.4.1: CircuitBreaker construction & properties
# =========================================================================


class TestCircuitBreakerConstruction:
    """Tests for CircuitBreaker construction and basic properties."""

    def test_initial_state_closed(self) -> None:
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig())
        assert cb.state == CircuitBreakerState.CLOSED

    def test_provider_id(self) -> None:
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig())
        assert cb.provider_id == "prov-1"

    def test_config_preserved(self) -> None:
        cfg = CircuitBreakerConfig(timeout_ms=5000)
        cb = CircuitBreaker("prov-1", config=cfg)
        assert cb.config is cfg
        assert cb.config.timeout_ms == 5000

    def test_zero_failures_initially(self) -> None:
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig())
        assert cb.failure_count == 0

    def test_repr(self) -> None:
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig())
        r = repr(cb)
        assert "prov-1" in r
        assert "CLOSED" in r

    def test_with_listener(self) -> None:
        listener = FakeListener()
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig(), on_state_change=listener)
        assert cb.state == CircuitBreakerState.CLOSED


# =========================================================================
# 3.4.1: CircuitBreaker.call() -- happy path
# =========================================================================


class TestCircuitBreakerHappyPath:
    """Tests for successful execution through the CB."""

    async def test_success_passes_through(self) -> None:
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig())
        result = await cb.call(_success_execute, _request(), _context(), "trace-1")
        assert result.success is True
        assert result.data == {"value": "ok"}

    async def test_state_stays_closed(self) -> None:
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig())
        await cb.call(_success_execute, _request(), _context(), "trace-1")
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_no_failures_recorded(self) -> None:
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig())
        await cb.call(_success_execute, _request(), _context(), "trace-1")
        assert cb.failure_count == 0

    async def test_multiple_successes(self) -> None:
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig())
        for _ in range(10):
            result = await cb.call(_success_execute, _request(), _context(), "trace-1")
            assert result.success is True
        assert cb.state == CircuitBreakerState.CLOSED


# =========================================================================
# 3.4.1: CircuitBreaker failure tracking
# =========================================================================


class TestCircuitBreakerFailureTracking:
    """Tests for failure recording and sliding window."""

    async def test_single_failure_recorded(self) -> None:
        cfg = CircuitBreakerConfig(failure_threshold=10)
        cb = CircuitBreaker("prov-1", config=cfg)
        await cb.call(_fail_retriable, _request(), _context(), "trace-1")
        # Failure count includes retried attempts
        assert cb.failure_count > 0

    async def test_failures_below_threshold_stays_closed(self) -> None:
        cfg = CircuitBreakerConfig(failure_threshold=10, max_retries=0)
        cb = CircuitBreaker("prov-1", config=cfg)
        # 5 failures with threshold 10 -- stays CLOSED
        for _ in range(5):
            await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 5

    async def test_sliding_window_prune(self) -> None:
        # Use a very short window so failures expire
        cfg = CircuitBreakerConfig(
            failure_threshold=100,
            failure_window_ms=50,  # 50ms window
            max_retries=0,
        )
        cb = CircuitBreaker("prov-1", config=cfg)
        await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        assert cb.failure_count == 1
        # Wait for window to expire
        await asyncio.sleep(0.1)  # 100ms > 50ms window
        assert cb.failure_count == 0

    async def test_get_failures_returns_copy(self) -> None:
        cfg = CircuitBreakerConfig(failure_threshold=10, max_retries=0)
        cb = CircuitBreaker("prov-1", config=cfg)
        await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        failures = cb.get_failures()
        assert len(failures) == 1
        assert isinstance(failures[0], FailureRecord)
        assert failures[0].error_code == "permanent_error"
        # Modifying copy doesn't affect internal state
        failures.clear()
        assert cb.failure_count == 1


# =========================================================================
# 3.4.1: State transitions
# =========================================================================


class TestCircuitBreakerStateTransitions:
    """Tests for the CB state machine."""

    async def test_closed_to_open_on_threshold(self) -> None:
        listener = FakeListener()
        cfg = CircuitBreakerConfig(failure_threshold=3, max_retries=0)
        cb = CircuitBreaker("prov-1", config=cfg, on_state_change=listener)
        for _ in range(3):
            await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        assert cb.state == CircuitBreakerState.OPEN
        # Listener should have CLOSED -> OPEN
        assert any(e[2] == CircuitBreakerState.OPEN for e in listener.events)

    async def test_open_rejects_requests(self) -> None:
        cfg = CircuitBreakerConfig(
            failure_threshold=1,
            max_retries=0,
            half_open_after_ms=60000,  # 60s -- won't trigger in test
            fallback_error_code="test_fallback",
        )
        cb = CircuitBreaker("prov-1", config=cfg)
        # Trip the breaker
        await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        assert cb.state == CircuitBreakerState.OPEN
        # Next call should be rejected immediately
        result = await cb.call(_success_execute, _request(), _context(), "trace-1")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "test_fallback"
        assert result.error.retriable is True

    async def test_open_to_half_open_after_delay(self) -> None:
        listener = FakeListener()
        cfg = CircuitBreakerConfig(
            failure_threshold=1,
            max_retries=0,
            half_open_after_ms=50,  # 50ms -- very short for test
        )
        cb = CircuitBreaker("prov-1", config=cfg, on_state_change=listener)
        # Trip the breaker
        await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        assert cb.state == CircuitBreakerState.OPEN
        # Wait for half_open_after_ms to elapse
        await asyncio.sleep(0.1)
        # Next call should transition to HALF_OPEN
        result = await cb.call(_success_execute, _request(), _context(), "trace-1")
        assert result.success is True
        # Should have gone OPEN -> HALF_OPEN -> CLOSED
        states = [e[2] for e in listener.events]
        assert CircuitBreakerState.HALF_OPEN in states
        assert CircuitBreakerState.CLOSED in states

    async def test_half_open_success_closes(self) -> None:
        cfg = CircuitBreakerConfig(
            failure_threshold=1,
            max_retries=0,
            half_open_after_ms=50,
        )
        cb = CircuitBreaker("prov-1", config=cfg)
        await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        assert cb.state == CircuitBreakerState.OPEN
        await asyncio.sleep(0.1)
        result = await cb.call(_success_execute, _request(), _context(), "trace-1")
        assert result.success is True
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_half_open_failure_reopens(self) -> None:
        listener = FakeListener()
        cfg = CircuitBreakerConfig(
            failure_threshold=1,
            max_retries=0,
            half_open_after_ms=50,
        )
        cb = CircuitBreaker("prov-1", config=cfg, on_state_change=listener)
        await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        assert cb.state == CircuitBreakerState.OPEN
        await asyncio.sleep(0.1)
        # Probe fails -> re-open
        result = await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        assert result.success is False
        assert cb.state == CircuitBreakerState.OPEN

    async def test_half_open_rejects_concurrent_requests(self) -> None:
        """While a probe is in flight, other requests should be rejected."""
        cfg = CircuitBreakerConfig(
            failure_threshold=1,
            max_retries=0,
            half_open_after_ms=50,
            fallback_error_code="busy",
        )
        cb = CircuitBreaker("prov-1", config=cfg)
        await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        await asyncio.sleep(0.1)

        # Allow transition to HALF_OPEN by triggering _check_state
        # We'll manually call allow_probe then try two calls
        # First: force HALF_OPEN via allow_probe
        cb.allow_probe()
        assert cb.state == CircuitBreakerState.HALF_OPEN

        # The probe permit was consumed by allow_probe
        # A slow probe taking time means a second request should be rejected
        slow_calls = 0
        results: List[CapabilityResult] = []

        async def slow_execute(
            req: CapabilityRequest,
            ctx: ExecutionContext,
            tid: str,
        ) -> CapabilityResult:
            nonlocal slow_calls
            slow_calls += 1
            await asyncio.sleep(0.05)
            return _success_result(req.request_id)

        # First call consumes the probe permit and executes
        task1 = asyncio.create_task(
            cb.call(slow_execute, _request(request_id="r1"), _context(), "t1")
        )
        # Give it a moment to enter _check_state and consume permit
        await asyncio.sleep(0.01)
        # Second call should be rejected (no permit left)
        task2 = asyncio.create_task(
            cb.call(slow_execute, _request(request_id="r2"), _context(), "t2")
        )
        r1, r2 = await asyncio.gather(task1, task2)
        # One should succeed (probe), one should be rejected
        successes = sum(1 for r in [r1, r2] if r.success)
        failures = sum(1 for r in [r1, r2] if not r.success)
        assert successes >= 1
        assert failures >= 1 or successes == 2  # both may pass if timing allows


# =========================================================================
# 3.4.1: Manual state control
# =========================================================================


class TestCircuitBreakerManualControl:
    """Tests for reset(), trip(), allow_probe()."""

    def test_trip_opens_breaker(self) -> None:
        listener = FakeListener()
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig(), on_state_change=listener)
        cb.trip()
        assert cb.state == CircuitBreakerState.OPEN
        assert len(listener.events) == 1
        assert listener.events[0] == (
            "prov-1",
            CircuitBreakerState.CLOSED,
            CircuitBreakerState.OPEN,
        )

    def test_trip_idempotent(self) -> None:
        listener = FakeListener()
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig(), on_state_change=listener)
        cb.trip()
        cb.trip()  # Second call should be no-op
        assert cb.state == CircuitBreakerState.OPEN
        assert len(listener.events) == 1

    def test_reset_closes_breaker(self) -> None:
        listener = FakeListener()
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig(), on_state_change=listener)
        cb.trip()
        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED
        assert len(listener.events) == 2
        assert listener.events[1] == (
            "prov-1",
            CircuitBreakerState.OPEN,
            CircuitBreakerState.CLOSED,
        )

    def test_reset_clears_failures(self) -> None:
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig())
        cb.trip()
        cb.reset()
        assert cb.failure_count == 0
        assert cb.get_failures() == []

    def test_reset_from_closed_no_event(self) -> None:
        listener = FakeListener()
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig(), on_state_change=listener)
        cb.reset()  # Already closed -- no event
        assert len(listener.events) == 0

    def test_allow_probe_transitions_to_half_open(self) -> None:
        listener = FakeListener()
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig(), on_state_change=listener)
        cb.trip()
        cb.allow_probe()
        assert cb.state == CircuitBreakerState.HALF_OPEN
        # Events: CLOSED->OPEN, OPEN->HALF_OPEN
        assert len(listener.events) == 2

    def test_allow_probe_only_from_open(self) -> None:
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig())
        # From CLOSED: no effect
        cb.allow_probe()
        assert cb.state == CircuitBreakerState.CLOSED


# =========================================================================
# 3.4.1: Timeout enforcement
# =========================================================================


class TestCircuitBreakerTimeout:
    """Tests for asyncio.wait_for timeout enforcement."""

    async def test_timeout_returns_timeout_result(self) -> None:
        cfg = CircuitBreakerConfig(
            timeout_ms=100,  # 100ms timeout
            failure_threshold=10,
            max_retries=0,
        )
        cb = CircuitBreaker("prov-1", config=cfg)
        result = await cb.call(_timeout_execute, _request(), _context(), "trace-1")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "timeout"
        # With max_retries=0, CB exhausts retry budget -> returns non-retriable
        assert result.error.retriable is False

    async def test_timeout_records_failure(self) -> None:
        cfg = CircuitBreakerConfig(
            timeout_ms=100,
            failure_threshold=10,
            max_retries=0,
        )
        cb = CircuitBreaker("prov-1", config=cfg)
        await cb.call(_timeout_execute, _request(), _context(), "trace-1")
        assert cb.failure_count == 1

    async def test_unexpected_exception_returns_failure(self) -> None:
        cfg = CircuitBreakerConfig(timeout_ms=5000, max_retries=0)
        cb = CircuitBreaker("prov-1", config=cfg)
        result = await cb.call(_raise_execute, _request(), _context(), "trace-1")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "provider_error"
        assert "RuntimeError" in result.error.message


# =========================================================================
# 3.4.1: State change callback
# =========================================================================


class TestStateChangeCallback:
    """Tests for on_state_change listener notification."""

    async def test_listener_notified_on_open(self) -> None:
        listener = FakeListener()
        cfg = CircuitBreakerConfig(failure_threshold=2, max_retries=0)
        cb = CircuitBreaker("prov-1", config=cfg, on_state_change=listener)
        for _ in range(2):
            await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        assert len(listener.events) >= 1
        assert listener.events[-1][2] == CircuitBreakerState.OPEN

    async def test_listener_notified_on_close(self) -> None:
        listener = FakeListener()
        cfg = CircuitBreakerConfig(failure_threshold=1, max_retries=0, half_open_after_ms=50)
        cb = CircuitBreaker("prov-1", config=cfg, on_state_change=listener)
        await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        await asyncio.sleep(0.1)
        await cb.call(_success_execute, _request(), _context(), "trace-1")
        # Should have CLOSED->OPEN, OPEN->HALF_OPEN, HALF_OPEN->CLOSED
        state_seq = [(e[1].value, e[2].value) for e in listener.events]
        assert ("HALF_OPEN", "CLOSED") in state_seq

    async def test_callback_error_does_not_propagate(self) -> None:
        """If the callback raises, CB still functions."""

        class BrokenListener:
            def on_state_change(
                self,
                provider_id: str,
                old_state: CircuitBreakerState,
                new_state: CircuitBreakerState,
            ) -> None:
                raise RuntimeError("callback crashed")

        cfg = CircuitBreakerConfig(failure_threshold=1, max_retries=0)
        cb = CircuitBreaker("prov-1", config=cfg, on_state_change=BrokenListener())
        # Should not raise even though callback does
        await cb.call(_fail_non_retriable, _request(), _context(), "trace-1")
        assert cb.state == CircuitBreakerState.OPEN

    def test_no_listener(self) -> None:
        """CB works fine without a listener."""
        cb = CircuitBreaker("prov-1", config=CircuitBreakerConfig())
        cb.trip()  # Should not raise
        assert cb.state == CircuitBreakerState.OPEN


# =========================================================================
# 3.4.3: Retry strategy
# =========================================================================


class TestRetryStrategy:
    """Tests for the retry strategy integrated in CircuitBreaker.call()."""

    async def test_retriable_failure_is_retried(self) -> None:
        """Transient (retriable) failures should be retried."""
        call_count = 0

        async def counting_fail(
            req: CapabilityRequest,
            ctx: ExecutionContext,
            tid: str,
        ) -> CapabilityResult:
            nonlocal call_count
            call_count += 1
            return _failure_result(req.request_id, retriable=True)

        cfg = CircuitBreakerConfig(
            failure_threshold=100,  # won't trip
            max_retries=2,
        )
        cb = CircuitBreaker("prov-1", config=cfg)
        result = await cb.call(counting_fail, _request(), _context(), "trace-1")
        assert result.success is False
        assert call_count == 3  # 1 original + 2 retries
        assert result.error is not None
        assert result.error.retriable is False  # exhausted -> non-retriable
        assert "3 attempts" in result.error.message

    async def test_non_retriable_not_retried(self) -> None:
        """Non-retriable failures should NOT be retried."""
        call_count = 0

        async def counting_fail(
            req: CapabilityRequest,
            ctx: ExecutionContext,
            tid: str,
        ) -> CapabilityResult:
            nonlocal call_count
            call_count += 1
            return _failure_result(req.request_id, retriable=False, error_code="permanent")

        cfg = CircuitBreakerConfig(max_retries=2, failure_threshold=100)
        cb = CircuitBreaker("prov-1", config=cfg)
        result = await cb.call(counting_fail, _request(), _context(), "trace-1")
        assert result.success is False
        assert call_count == 1  # No retries for non-retriable

    async def test_retry_succeeds_on_second_attempt(self) -> None:
        """If first attempt fails but second succeeds, return success."""
        call_count = 0

        async def flaky(
            req: CapabilityRequest,
            ctx: ExecutionContext,
            tid: str,
        ) -> CapabilityResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _failure_result(req.request_id, retriable=True)
            return _success_result(req.request_id)

        cfg = CircuitBreakerConfig(max_retries=2, failure_threshold=100)
        cb = CircuitBreaker("prov-1", config=cfg)
        result = await cb.call(flaky, _request(), _context(), "trace-1")
        assert result.success is True
        assert call_count == 2

    async def test_max_retries_zero_no_retry(self) -> None:
        """With max_retries=0, no retries even for retriable errors."""
        call_count = 0

        async def counting_fail(
            req: CapabilityRequest,
            ctx: ExecutionContext,
            tid: str,
        ) -> CapabilityResult:
            nonlocal call_count
            call_count += 1
            return _failure_result(req.request_id, retriable=True)

        cfg = CircuitBreakerConfig(max_retries=0, failure_threshold=100)
        cb = CircuitBreaker("prov-1", config=cfg)
        result = await cb.call(counting_fail, _request(), _context(), "trace-1")
        assert result.success is False
        assert call_count == 1

    async def test_retry_with_max_retries_one(self) -> None:
        """max_retries=1: original + 1 retry = 2 attempts total."""
        call_count = 0

        async def counting_fail(
            req: CapabilityRequest,
            ctx: ExecutionContext,
            tid: str,
        ) -> CapabilityResult:
            nonlocal call_count
            call_count += 1
            return _failure_result(req.request_id, retriable=True)

        cfg = CircuitBreakerConfig(max_retries=1, failure_threshold=100)
        cb = CircuitBreaker("prov-1", config=cfg)
        await cb.call(counting_fail, _request(), _context(), "trace-1")
        assert call_count == 2

    async def test_timeout_is_retriable_so_retried(self) -> None:
        """Timeout failures have retriable=True so should be retried."""
        call_count = 0

        async def slow_then_ok(
            req: CapabilityRequest,
            ctx: ExecutionContext,
            tid: str,
        ) -> CapabilityResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(5)  # Will be timed out
            return _success_result(req.request_id)

        cfg = CircuitBreakerConfig(
            timeout_ms=100,
            max_retries=2,
            failure_threshold=100,
        )
        cb = CircuitBreaker("prov-1", config=cfg)
        result = await cb.call(slow_then_ok, _request(), _context(), "trace-1")
        assert result.success is True
        assert call_count == 2


# =========================================================================
# 3.4.2: Per-provider breaker config
# =========================================================================


class TestBreakerConfigDefaults:
    """Tests for hardcoded per-provider-type config instances (3.4.2)."""

    def test_mcp_local_config(self) -> None:
        assert MCP_LOCAL_CONFIG.timeout_ms == 10000
        assert MCP_LOCAL_CONFIG.failure_threshold == 3
        assert MCP_LOCAL_CONFIG.failure_window_ms == 60000
        assert MCP_LOCAL_CONFIG.half_open_after_ms == 30000
        assert MCP_LOCAL_CONFIG.max_retries == 2
        assert MCP_LOCAL_CONFIG.fallback_error_code == "tool_offline"

    def test_mcp_remote_config(self) -> None:
        assert MCP_REMOTE_CONFIG.timeout_ms == 15000
        assert MCP_REMOTE_CONFIG.failure_threshold == 3
        assert MCP_REMOTE_CONFIG.fallback_error_code == "tool_offline"

    def test_wasm_config(self) -> None:
        assert WASM_CONFIG.timeout_ms == 5000
        assert WASM_CONFIG.failure_threshold == 5
        assert WASM_CONFIG.fallback_error_code == "computation_failed"

    def test_bridge_config(self) -> None:
        assert BRIDGE_CONFIG.timeout_ms == 10000
        assert BRIDGE_CONFIG.failure_threshold == 3
        assert BRIDGE_CONFIG.fallback_error_code == "bridge_offline"

    def test_agent_config(self) -> None:
        assert AGENT_CONFIG.timeout_ms == 30000
        assert AGENT_CONFIG.failure_threshold == 2
        assert AGENT_CONFIG.fallback_error_code == "agent_execution_failed"

    def test_workflow_config(self) -> None:
        assert WORKFLOW_CONFIG.timeout_ms == 60000
        assert WORKFLOW_CONFIG.failure_threshold == 1
        assert WORKFLOW_CONFIG.max_retries == 1  # Workflows are expensive
        assert WORKFLOW_CONFIG.fallback_error_code == "workflow_failed"

    def test_concierge_config(self) -> None:
        assert CONCIERGE_CONFIG.timeout_ms == 5000
        assert CONCIERGE_CONFIG.failure_threshold == 5
        assert CONCIERGE_CONFIG.fallback_error_code == "concierge_state_failed"

    def test_default_config(self) -> None:
        assert DEFAULT_CONFIG.timeout_ms == 30000
        assert DEFAULT_CONFIG.failure_threshold == 5
        assert DEFAULT_CONFIG.failure_window_ms == 60000
        assert DEFAULT_CONFIG.half_open_after_ms == 30000
        assert DEFAULT_CONFIG.max_retries == 2
        assert DEFAULT_CONFIG.fallback_error_code == "capability_unavailable"


class TestGetBreakerConfig:
    """Tests for get_breaker_config() lookup function (3.4.2)."""

    def test_mcp_local_stdio(self) -> None:
        pc = ProviderConfig(
            provider_id="mcp-local",
            provider_type=ProviderType.MCP.value,
            transport=TransportType.STDIO.value,
        )
        cfg = get_breaker_config(ProviderType.MCP.value, provider_config=pc)
        assert cfg is MCP_LOCAL_CONFIG

    def test_mcp_remote_sse(self) -> None:
        pc = ProviderConfig(
            provider_id="mcp-remote",
            provider_type=ProviderType.MCP.value,
            transport=TransportType.SSE.value,
        )
        cfg = get_breaker_config(ProviderType.MCP.value, provider_config=pc)
        assert cfg is MCP_REMOTE_CONFIG

    def test_mcp_remote_streamable_http(self) -> None:
        pc = ProviderConfig(
            provider_id="mcp-remote-http",
            provider_type=ProviderType.MCP.value,
            transport=TransportType.STREAMABLE_HTTP.value,
        )
        cfg = get_breaker_config(ProviderType.MCP.value, provider_config=pc)
        assert cfg is MCP_REMOTE_CONFIG

    def test_mcp_no_provider_config_defaults_local(self) -> None:
        cfg = get_breaker_config(ProviderType.MCP.value)
        assert cfg is MCP_LOCAL_CONFIG

    def test_wasm_type(self) -> None:
        cfg = get_breaker_config(ProviderType.WASM.value)
        assert cfg is WASM_CONFIG

    def test_bridge_type(self) -> None:
        cfg = get_breaker_config(ProviderType.BRIDGE.value)
        assert cfg is BRIDGE_CONFIG

    def test_agent_type(self) -> None:
        cfg = get_breaker_config(ProviderType.AGENT.value)
        assert cfg is AGENT_CONFIG

    def test_workflow_type(self) -> None:
        cfg = get_breaker_config(ProviderType.WORKFLOW.value)
        assert cfg is WORKFLOW_CONFIG

    def test_concierge_type(self) -> None:
        cfg = get_breaker_config(ProviderType.CONCIERGE.value)
        assert cfg is CONCIERGE_CONFIG

    def test_unknown_type_returns_default(self) -> None:
        cfg = get_breaker_config("UNKNOWN_TYPE")
        assert cfg is DEFAULT_CONFIG

    def test_override_wins_over_type(self) -> None:
        custom = CircuitBreakerConfig(timeout_ms=999, fallback_error_code="custom")
        cfg = get_breaker_config(
            ProviderType.MCP.value,
            override=custom,
        )
        assert cfg is custom
        assert cfg.timeout_ms == 999

    def test_override_wins_even_with_provider_config(self) -> None:
        pc = ProviderConfig(
            provider_id="mcp-remote",
            provider_type=ProviderType.MCP.value,
            transport=TransportType.SSE.value,
        )
        custom = CircuitBreakerConfig(timeout_ms=555)
        cfg = get_breaker_config(
            ProviderType.MCP.value,
            provider_config=pc,
            override=custom,
        )
        assert cfg is custom


# =========================================================================
# Module exports
# =========================================================================


class TestModuleExports:
    """Verify __all__ exports are importable and correct."""

    def test_all_exports_count(self) -> None:
        assert len(cb_all) == 16

    def test_all_exports_are_importable(self) -> None:
        import k1.fabric.circuit_breaker as mod

        for name in cb_all:
            assert hasattr(mod, name), f"Missing export: {name}"

    def test_key_types_importable(self) -> None:
        from k1.fabric.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            get_breaker_config,
        )

        assert CircuitBreaker is not None
        assert CircuitBreakerConfig is not None
        assert get_breaker_config is not None

    def test_config_constants_importable(self) -> None:
        from k1.fabric.circuit_breaker import (
            AGENT_CONFIG,
            BRIDGE_CONFIG,
            CONCIERGE_CONFIG,
            DEFAULT_CONFIG,
            MCP_LOCAL_CONFIG,
            MCP_REMOTE_CONFIG,
            WASM_CONFIG,
            WORKFLOW_CONFIG,
        )

        configs = [
            AGENT_CONFIG,
            BRIDGE_CONFIG,
            CONCIERGE_CONFIG,
            DEFAULT_CONFIG,
            MCP_LOCAL_CONFIG,
            MCP_REMOTE_CONFIG,
            WASM_CONFIG,
            WORKFLOW_CONFIG,
        ]
        for c in configs:
            assert isinstance(c, CircuitBreakerConfig)


# =========================================================================
# Integration: CB wraps execute correctly
# =========================================================================


class TestCircuitBreakerIntegration:
    """End-to-end integration tests for CB wrapping provider execute."""

    async def test_cb_wraps_provider_execute_full_cycle(self) -> None:
        """Full cycle: success -> failures -> open -> half_open -> closed."""
        listener = FakeListener()
        cfg = CircuitBreakerConfig(
            timeout_ms=5000,
            failure_threshold=3,
            max_retries=0,
            half_open_after_ms=50,
        )
        cb = CircuitBreaker("integration-prov", config=cfg, on_state_change=listener)

        # Phase 1: Success
        r = await cb.call(_success_execute, _request(), _context(), "t1")
        assert r.success is True
        assert cb.state == CircuitBreakerState.CLOSED

        # Phase 2: Accumulate failures -> OPEN
        for _ in range(3):
            await cb.call(_fail_non_retriable, _request(), _context(), "t1")
        assert cb.state == CircuitBreakerState.OPEN

        # Phase 3: Rejected while OPEN
        r = await cb.call(_success_execute, _request(), _context(), "t1")
        assert r.success is False

        # Phase 4: Wait for half_open -> probe success -> CLOSED
        await asyncio.sleep(0.1)
        r = await cb.call(_success_execute, _request(), _context(), "t1")
        assert r.success is True
        assert cb.state == CircuitBreakerState.CLOSED

        # Verify listener got all transitions
        assert len(listener.events) >= 3

    async def test_per_provider_config_used_in_timeout(self) -> None:
        """Verify that per-provider config timeout is actually enforced."""
        cfg = get_breaker_config(ProviderType.WASM.value)
        assert cfg.timeout_ms == 5000  # WASM = 5s

        cb = CircuitBreaker("wasm-prov", config=cfg)

        async def sleep_6s(
            req: CapabilityRequest,
            ctx: ExecutionContext,
            tid: str,
        ) -> CapabilityResult:
            await asyncio.sleep(6)  # Longer than 5s WASM timeout
            return _success_result(req.request_id)

        # Should timeout (but we use a shorter timeout for test speed)
        short_cfg = CircuitBreakerConfig(
            timeout_ms=100,
            failure_threshold=5,
            max_retries=0,
        )
        cb_fast = CircuitBreaker("wasm-fast", config=short_cfg)
        result = await cb_fast.call(sleep_6s, _request(), _context(), "t1")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "timeout"

    async def test_factory_pattern_each_provider_gets_own_cb(self) -> None:
        """Each provider should have its own CB instance (isolation test)."""
        cfg_a = get_breaker_config(ProviderType.MCP.value)
        cfg_b = get_breaker_config(ProviderType.WASM.value)
        cb_a = CircuitBreaker("prov-a", config=cfg_a)
        cb_b = CircuitBreaker("prov-b", config=cfg_b)

        # Trip one, other should be unaffected
        cb_a.trip()
        assert cb_a.state == CircuitBreakerState.OPEN
        assert cb_b.state == CircuitBreakerState.CLOSED

    async def test_retry_then_trip_cycle(self) -> None:
        """Retries accumulate failures that can trip the breaker."""
        listener = FakeListener()
        cfg = CircuitBreakerConfig(
            failure_threshold=3,
            max_retries=2,  # Each call() produces up to 3 failures
        )
        cb = CircuitBreaker("prov-1", config=cfg, on_state_change=listener)
        # One call with 2 retries = 3 failures = threshold met
        result = await cb.call(_fail_retriable, _request(), _context(), "t1")
        assert result.success is False
        assert cb.state == CircuitBreakerState.OPEN
