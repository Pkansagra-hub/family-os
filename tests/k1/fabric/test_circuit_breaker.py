"""
Epic 6.2.9 -- Test CircuitBreaker (state machine + retry strategy).

Covers:
  - State machine: CLOSED -> OPEN -> HALF_OPEN -> CLOSED cycle.
  - Sliding window: failures within window trigger OPEN.
  - Retry strategy: max 2 retries for transient failures (3.4.3).
  - Timeout enforcement: asyncio.wait_for wrapping execute_fn.
  - State change notifications: IStateChangeListener callback.
  - Force operations: reset(), trip(), allow_probe().
  - CircuitBreakerOpen: rejection while OPEN + remaining_ms.
  - HALF_OPEN: single probe request, success closes, failure re-opens.

NO MOCKS -- all tests use real async functions and real CircuitBreaker.

References:
  - fabric-implementation-plan.md Epic 6.2.9
  - fabric_discussion.md Section 19 (Error Handling and Circuit Breakers)
  - FAB-004 (every execution returns within CB timeout)
  - Epic 3.4.1 (CircuitBreaker), 3.4.3 (RetryStrategy)
"""

from __future__ import annotations

import asyncio

from k1.fabric.circuit_breaker.breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    FailureRecord,
)
from k1.fabric.types import CapabilityRequest, CapabilityResult, ExecutionContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(name: str = "tool.read.test") -> CapabilityRequest:
    return CapabilityRequest(
        capability_name=name,
        caller="test",
        trace_id="tr-cb-test",
    )


def _make_context() -> ExecutionContext:
    return ExecutionContext(trace_id="tr-cb-test")


async def _success_fn(
    request: CapabilityRequest,
    context: ExecutionContext,
    trace_id: str,
) -> CapabilityResult:
    """Simulates a successful provider execution."""
    return CapabilityResult.success_result(
        request_id=request.request_id,
        data={"result": "ok"},
        provider_id="test-provider",
        trace_id=trace_id,
    )


async def _failure_fn(
    request: CapabilityRequest,
    context: ExecutionContext,
    trace_id: str,
) -> CapabilityResult:
    """Simulates a failed provider execution (retriable)."""
    return CapabilityResult.failure_result(
        request_id=request.request_id,
        error_code="provider_error",
        error_message="Something went wrong",
        retriable=True,
        provider_id="test-provider",
        trace_id=trace_id,
    )


async def _non_retriable_failure_fn(
    request: CapabilityRequest,
    context: ExecutionContext,
    trace_id: str,
) -> CapabilityResult:
    """Simulates a non-retriable failure."""
    return CapabilityResult.failure_result(
        request_id=request.request_id,
        error_code="fatal_error",
        error_message="Fatal failure",
        retriable=False,
        provider_id="test-provider",
        trace_id=trace_id,
    )


async def _slow_fn(
    request: CapabilityRequest,
    context: ExecutionContext,
    trace_id: str,
) -> CapabilityResult:
    """Simulates a provider that exceeds the timeout."""
    await asyncio.sleep(10)  # will be cancelled by CB timeout
    return CapabilityResult.success_result(
        request_id=request.request_id,
        data={"result": "late"},
        provider_id="test-provider",
        trace_id=trace_id,
    )


async def _exception_fn(
    request: CapabilityRequest,
    context: ExecutionContext,
    trace_id: str,
) -> CapabilityResult:
    """Simulates a provider that raises an unexpected exception."""
    raise RuntimeError("Unexpected crash")


class StateChangeTracker:
    """Real listener that records state change notifications."""

    def __init__(self) -> None:
        self.changes: list[tuple[str, CircuitBreakerState, CircuitBreakerState]] = []

    def on_state_change(
        self,
        provider_id: str,
        old_state: CircuitBreakerState,
        new_state: CircuitBreakerState,
    ) -> None:
        self.changes.append((provider_id, old_state, new_state))


# ===========================================================================
# CircuitBreaker: State Machine
# ===========================================================================


class TestCircuitBreakerStateMachine:
    """Tests for CB state transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""

    def _make_cb(
        self,
        threshold: int = 3,
        window_ms: int = 60000,
        half_open_after_ms: int = 100,
        timeout_ms: int = 5000,
        max_retries: int = 0,
        listener: StateChangeTracker | None = None,
    ) -> CircuitBreaker:
        return CircuitBreaker(
            provider_id="test-prov",
            config=CircuitBreakerConfig(
                failure_threshold=threshold,
                failure_window_ms=window_ms,
                half_open_after_ms=half_open_after_ms,
                timeout_ms=timeout_ms,
                max_retries=max_retries,
            ),
            on_state_change=listener,
        )

    def test_initial_state_closed(self):
        cb = self._make_cb()
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_success_stays_closed(self):
        cb = self._make_cb()
        result = await cb.call(_success_fn, _make_request(), _make_context(), "tr-1")
        assert result.success
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_failures_below_threshold_stay_closed(self):
        cb = self._make_cb(threshold=5)
        for _ in range(4):
            await cb.call(_failure_fn, _make_request(), _make_context(), "tr-1")
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_failures_at_threshold_opens(self):
        cb = self._make_cb(threshold=3, max_retries=0)
        for _ in range(3):
            await cb.call(_failure_fn, _make_request(), _make_context(), "tr-1")
        assert cb.state == CircuitBreakerState.OPEN

    async def test_open_rejects_requests(self):
        cb = self._make_cb(threshold=2, max_retries=0, half_open_after_ms=60000)
        # Trip the breaker
        for _ in range(2):
            await cb.call(_failure_fn, _make_request(), _make_context(), "tr-1")
        assert cb.state == CircuitBreakerState.OPEN

        # Next call should be rejected immediately
        result = await cb.call(_success_fn, _make_request(), _make_context(), "tr-2")
        assert not result.success
        assert result.error is not None
        assert result.error.code == "circuit_breaker_open"

    async def test_open_transitions_to_half_open_after_delay(self):
        cb = self._make_cb(threshold=2, max_retries=0, half_open_after_ms=50)
        for _ in range(2):
            await cb.call(_failure_fn, _make_request(), _make_context(), "tr-1")
        assert cb.state == CircuitBreakerState.OPEN

        # Wait for half_open_after_ms
        await asyncio.sleep(0.1)

        # Next call should be allowed (probe)
        result = await cb.call(_success_fn, _make_request(), _make_context(), "tr-2")
        assert result.success
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_half_open_success_closes(self):
        cb = self._make_cb(threshold=2, max_retries=0, half_open_after_ms=50)
        for _ in range(2):
            await cb.call(_failure_fn, _make_request(), _make_context(), "tr-1")

        await asyncio.sleep(0.1)
        result = await cb.call(_success_fn, _make_request(), _make_context(), "tr-2")
        assert result.success
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_half_open_failure_reopens(self):
        cb = self._make_cb(threshold=2, max_retries=0, half_open_after_ms=50)
        for _ in range(2):
            await cb.call(_failure_fn, _make_request(), _make_context(), "tr-1")

        await asyncio.sleep(0.1)
        # Probe with failure
        result = await cb.call(_failure_fn, _make_request(), _make_context(), "tr-2")
        assert not result.success
        assert cb.state == CircuitBreakerState.OPEN


# ===========================================================================
# CircuitBreaker: Retry Strategy (3.4.3)
# ===========================================================================


class TestCircuitBreakerRetry:
    """Tests for retry strategy: max 2 retries for transient failures."""

    def _make_cb(self, max_retries: int = 2, threshold: int = 10) -> CircuitBreaker:
        return CircuitBreaker(
            provider_id="retry-prov",
            config=CircuitBreakerConfig(
                failure_threshold=threshold,
                max_retries=max_retries,
                timeout_ms=5000,
            ),
        )

    async def test_retry_on_transient_failure(self):
        """Transient failure retried up to max_retries."""
        call_count = 0

        async def counting_fail_fn(req, ctx, tid):
            nonlocal call_count
            call_count += 1
            return CapabilityResult.failure_result(
                request_id=req.request_id,
                error_code="transient",
                error_message="Transient error",
                retriable=True,
                provider_id="retry-prov",
                trace_id=tid,
            )

        cb = self._make_cb(max_retries=2)
        result = await cb.call(counting_fail_fn, _make_request(), _make_context(), "tr-r")
        assert not result.success
        assert call_count == 3  # 1 initial + 2 retries

    async def test_no_retry_on_non_retriable(self):
        """Non-retriable failure: no retries attempted."""
        call_count = 0

        async def counting_non_retriable(req, ctx, tid):
            nonlocal call_count
            call_count += 1
            return CapabilityResult.failure_result(
                request_id=req.request_id,
                error_code="fatal",
                error_message="Fatal",
                retriable=False,
                provider_id="retry-prov",
                trace_id=tid,
            )

        cb = self._make_cb(max_retries=2)
        result = await cb.call(counting_non_retriable, _make_request(), _make_context(), "tr-r")
        assert not result.success
        assert call_count == 1  # no retries

    async def test_retry_succeeds_on_second_attempt(self):
        """Transient failure on first attempt, success on second."""
        call_count = 0

        async def flaky_fn(req, ctx, tid):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CapabilityResult.failure_result(
                    request_id=req.request_id,
                    error_code="transient",
                    error_message="Flaky",
                    retriable=True,
                    provider_id="retry-prov",
                    trace_id=tid,
                )
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={"recovered": True},
                provider_id="retry-prov",
                trace_id=tid,
            )

        cb = self._make_cb(max_retries=2)
        result = await cb.call(flaky_fn, _make_request(), _make_context(), "tr-r")
        assert result.success
        assert call_count == 2

    async def test_zero_retries(self):
        """max_retries=0 means only one attempt."""
        call_count = 0

        async def counting_fail(req, ctx, tid):
            nonlocal call_count
            call_count += 1
            return CapabilityResult.failure_result(
                request_id=req.request_id,
                error_code="err",
                error_message="Fail",
                retriable=True,
                provider_id="retry-prov",
                trace_id=tid,
            )

        cb = self._make_cb(max_retries=0)
        result = await cb.call(counting_fail, _make_request(), _make_context(), "tr-r")
        assert not result.success
        assert call_count == 1


# ===========================================================================
# CircuitBreaker: Timeout
# ===========================================================================


class TestCircuitBreakerTimeout:
    """Tests for timeout enforcement via asyncio.wait_for."""

    async def test_timeout_returns_timeout_result(self):
        cb = CircuitBreaker(
            provider_id="slow-prov",
            config=CircuitBreakerConfig(timeout_ms=100, max_retries=0),
        )
        result = await cb.call(_slow_fn, _make_request(), _make_context(), "tr-t")
        assert not result.success
        assert result.error is not None
        # After all retries exhausted, the error is marked non-retriable
        assert "timeout" in result.error.code or "after" in result.error.message

    async def test_exception_returns_failure(self):
        cb = CircuitBreaker(
            provider_id="crash-prov",
            config=CircuitBreakerConfig(timeout_ms=5000, max_retries=0),
        )
        result = await cb.call(_exception_fn, _make_request(), _make_context(), "tr-e")
        assert not result.success
        assert result.error is not None
        assert result.error.code == "provider_error"


# ===========================================================================
# CircuitBreaker: Force operations
# ===========================================================================


class TestCircuitBreakerForceOps:
    """Tests for reset(), trip(), allow_probe()."""

    def test_trip_forces_open(self):
        cb = CircuitBreaker(
            provider_id="force-prov",
            config=CircuitBreakerConfig(),
        )
        assert cb.state == CircuitBreakerState.CLOSED
        cb.trip()
        assert cb.state == CircuitBreakerState.OPEN

    def test_reset_forces_closed(self):
        cb = CircuitBreaker(
            provider_id="force-prov",
            config=CircuitBreakerConfig(),
        )
        cb.trip()
        assert cb.state == CircuitBreakerState.OPEN
        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_allow_probe_moves_open_to_half_open(self):
        cb = CircuitBreaker(
            provider_id="force-prov",
            config=CircuitBreakerConfig(),
        )
        cb.trip()
        assert cb.state == CircuitBreakerState.OPEN
        cb.allow_probe()
        assert cb.state == CircuitBreakerState.HALF_OPEN


# ===========================================================================
# CircuitBreaker: State Change Notifications
# ===========================================================================


class TestCircuitBreakerNotifications:
    """Tests for IStateChangeListener callback."""

    async def test_state_change_notified_on_open(self):
        tracker = StateChangeTracker()
        cb = CircuitBreaker(
            provider_id="notify-prov",
            config=CircuitBreakerConfig(
                failure_threshold=2,
                max_retries=0,
            ),
            on_state_change=tracker,
        )
        for _ in range(2):
            await cb.call(_failure_fn, _make_request(), _make_context(), "tr-n")

        assert len(tracker.changes) >= 1
        # Should have CLOSED -> OPEN transition
        found_open = any(new == CircuitBreakerState.OPEN for _, _, new in tracker.changes)
        assert found_open

    def test_state_change_on_trip(self):
        tracker = StateChangeTracker()
        cb = CircuitBreaker(
            provider_id="notify-prov",
            config=CircuitBreakerConfig(),
            on_state_change=tracker,
        )
        cb.trip()
        assert len(tracker.changes) == 1
        pid, old, new = tracker.changes[0]
        assert pid == "notify-prov"
        assert old == CircuitBreakerState.CLOSED
        assert new == CircuitBreakerState.OPEN

    def test_state_change_on_reset(self):
        tracker = StateChangeTracker()
        cb = CircuitBreaker(
            provider_id="notify-prov",
            config=CircuitBreakerConfig(),
            on_state_change=tracker,
        )
        cb.trip()
        cb.reset()
        assert len(tracker.changes) == 2
        # Second change: OPEN -> CLOSED
        _, old2, new2 = tracker.changes[1]
        assert old2 == CircuitBreakerState.OPEN
        assert new2 == CircuitBreakerState.CLOSED


# ===========================================================================
# CircuitBreaker: Sliding Window
# ===========================================================================


class TestCircuitBreakerSlidingWindow:
    """Tests for sliding window failure tracking."""

    async def test_failures_expire_outside_window(self):
        cb = CircuitBreaker(
            provider_id="window-prov",
            config=CircuitBreakerConfig(
                failure_threshold=3,
                failure_window_ms=100,  # 100ms window
                max_retries=0,
            ),
        )
        # Record 2 failures
        await cb.call(_failure_fn, _make_request(), _make_context(), "tr-w")
        await cb.call(_failure_fn, _make_request(), _make_context(), "tr-w")
        assert cb.failure_count == 2

        # Wait for window to expire
        await asyncio.sleep(0.15)

        # Failures should have expired
        assert cb.failure_count == 0
        assert cb.state == CircuitBreakerState.CLOSED

    async def test_get_failures_returns_records(self):
        cb = CircuitBreaker(
            provider_id="window-prov",
            config=CircuitBreakerConfig(
                failure_threshold=10,
                max_retries=0,
            ),
        )
        await cb.call(_failure_fn, _make_request(), _make_context(), "tr-w")
        failures = cb.get_failures()
        assert len(failures) == 1
        assert isinstance(failures[0], FailureRecord)
        assert failures[0].error_code == "provider_error"


# ===========================================================================
# CircuitBreaker: Properties
# ===========================================================================


class TestCircuitBreakerProperties:
    """Tests for CB properties and repr."""

    def test_provider_id(self):
        cb = CircuitBreaker("my-prov", CircuitBreakerConfig())
        assert cb.provider_id == "my-prov"

    def test_config_property(self):
        cfg = CircuitBreakerConfig(timeout_ms=1000)
        cb = CircuitBreaker("p", cfg)
        assert cb.config.timeout_ms == 1000

    def test_repr(self):
        cb = CircuitBreaker("my-prov", CircuitBreakerConfig())
        r = repr(cb)
        assert "my-prov" in r
        assert "CLOSED" in r
