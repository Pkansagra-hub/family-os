"""
k1.fabric.circuit_breaker.breaker -- CircuitBreaker (3.4.1) + retry (3.4.3).

Per-provider circuit breaker that wraps ``CapabilityProvider.execute()`` calls.
Sits between Resolver output (3.1.5) and Provider.execute() (3.3.x).

States (classic circuit breaker pattern):
  CLOSED   -- Normal operation; requests pass through.
  OPEN     -- Failing; reject ALL requests immediately.
  HALF_OPEN -- Trying ONE request to test recovery.

Sliding window failure tracking:
  Failures within ``failure_window_ms`` are counted.  When count reaches
  ``failure_threshold`` the breaker opens.  After ``half_open_after_ms``
  the breaker moves to HALF_OPEN and allows a single probe request.

Retry strategy (3.4.3):
  Attempt 1: Execute normally.
  Attempt 2: Same provider, same params (confirm persistent failure).
  Attempt 3: NOT automatic -- return ``CapabilityResult{success=False,
             retriable=False}``.  Max 2 retries for transient failures.

Thread safety:
  All mutable state protected by ``threading.Lock``.  The breaker is safe
  for concurrent async usage from a single event loop and from multiple
  threads (e.g., HealthChecker background thread).

Wiring (from plan):
  - Wraps every provider's execute() call.
  - On state change: calls ``on_state_change`` callback (bound to
    AvailabilityTracker.update_state / Registry.update_availability).
  - FabricFactory creates one CircuitBreaker per registered provider.
  - Consumed by FabricFacade.execute() execution path (5.3.2).

References:
  - fabric_discussion.md Section 19 (Error Handling and Circuit Breakers)
  - FAB-004 (every execution returns within CB timeout)
  - Epic 3.4.1, 3.4.3 in fabric-implementation-plan.md

Exports:
  CircuitBreaker       -- Per-provider circuit breaker wrapper
  CircuitBreakerState  -- CLOSED / OPEN / HALF_OPEN enum
  CircuitBreakerError  -- Base CB exception
  CircuitBreakerOpen   -- Request rejected because CB is open
  FailureRecord        -- Timestamped failure entry in sliding window
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Protocol

from k1.fabric.types import CapabilityRequest, CapabilityResult, ExecutionContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Circuit breaker states
# ---------------------------------------------------------------------------


class CircuitBreakerState(str, Enum):
    """State of a circuit breaker instance."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# ---------------------------------------------------------------------------
# Configuration (consumed from BreakerConfig 3.4.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """
    Configuration for a single circuit breaker instance.

    Attributes:
        timeout_ms: Per-invocation timeout applied to provider.execute().
        failure_threshold: Number of failures in the sliding window
            before the breaker opens.
        failure_window_ms: Sliding window duration for failure counting.
        half_open_after_ms: How long the breaker stays OPEN before
            transitioning to HALF_OPEN for a probe request.
        max_retries: Maximum automatic retries on transient failure
            (default 2 per 3.4.3 spec).
        fallback_error_code: Error code returned when the breaker is open.
    """

    timeout_ms: int = 30000
    failure_threshold: int = 5
    failure_window_ms: int = 60000
    half_open_after_ms: int = 30000
    max_retries: int = 2
    fallback_error_code: str = "circuit_breaker_open"

    def __post_init__(self) -> None:
        # Validate invariants (frozen dataclass, so we object.__setattr__)
        if self.timeout_ms <= 0:
            object.__setattr__(self, "timeout_ms", 30000)
        if self.failure_threshold <= 0:
            object.__setattr__(self, "failure_threshold", 5)
        if self.failure_window_ms <= 0:
            object.__setattr__(self, "failure_window_ms", 60000)
        if self.half_open_after_ms <= 0:
            object.__setattr__(self, "half_open_after_ms", 30000)
        if self.max_retries < 0:
            object.__setattr__(self, "max_retries", 0)


# ---------------------------------------------------------------------------
# Failure record (sliding window entry)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FailureRecord:
    """
    Timestamped failure entry in the sliding window.

    Attributes:
        timestamp_ms: Monotonic time when the failure occurred (ms).
        error_code: Machine-readable error code.
        error_message: Human-readable description.
        retriable: Whether the failure was marked as retriable.
    """

    timestamp_ms: int = 0
    error_code: str = ""
    error_message: str = ""
    retriable: bool = False


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CircuitBreakerError(Exception):
    """Base exception for circuit breaker operations."""

    def __init__(self, provider_id: str, message: str) -> None:
        self.provider_id = provider_id
        super().__init__(f"[CB:{provider_id}] {message}")


class CircuitBreakerOpen(CircuitBreakerError):
    """Request rejected because the circuit breaker is OPEN."""

    def __init__(
        self,
        provider_id: str,
        remaining_ms: int = 0,
    ) -> None:
        self.remaining_ms = remaining_ms
        super().__init__(
            provider_id,
            f"Circuit breaker is OPEN (recovery in {remaining_ms}ms)",
        )


# ---------------------------------------------------------------------------
# State change callback protocol
# ---------------------------------------------------------------------------


class IStateChangeListener(Protocol):
    """
    Callback invoked when the circuit breaker changes state.

    Wired to AvailabilityTracker.update_state() and
    Registry.update_availability() in production.
    """

    def on_state_change(
        self,
        provider_id: str,
        old_state: CircuitBreakerState,
        new_state: CircuitBreakerState,
    ) -> None:
        """Called when CB state changes."""
        ...


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """
    Per-provider circuit breaker with retry strategy.

    Wraps a provider's ``execute()`` call and provides:
      - Timeout enforcement (asyncio.wait_for)
      - Sliding-window failure tracking
      - State machine: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
      - Automatic retry (up to max_retries) for transient failures
      - State change notification via callback

    Constructor Args:
        provider_id: The provider this breaker wraps.
        config: CircuitBreakerConfig with timeout, threshold, etc.
        on_state_change: Optional callback for state transitions.

    Usage::

        cb = CircuitBreaker("mcp-weather", config=mcp_local_config)
        result = await cb.call(provider.execute, request, context, trace_id)

    Thread-safe: All mutable state protected by threading.Lock.
    """

    __slots__ = (
        "_provider_id",
        "_config",
        "_on_state_change",
        "_lock",
        "_state",
        "_failures",
        "_opened_at_ms",
        "_half_open_permit",
        "_consecutive_successes",
    )

    def __init__(
        self,
        provider_id: str,
        config: CircuitBreakerConfig,
        on_state_change: Optional[IStateChangeListener] = None,
    ) -> None:
        self._provider_id = provider_id
        self._config = config
        self._on_state_change = on_state_change
        self._lock = threading.Lock()
        self._state = CircuitBreakerState.CLOSED
        self._failures: List[FailureRecord] = []
        self._opened_at_ms: int = 0
        self._half_open_permit: bool = False
        self._consecutive_successes: int = 0

    # ==================================================================
    # Properties
    # ==================================================================

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def config(self) -> CircuitBreakerConfig:
        return self._config

    @property
    def state(self) -> CircuitBreakerState:
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        """Number of failures in the current sliding window."""
        with self._lock:
            self._prune_failures()
            return len(self._failures)

    # ==================================================================
    # Public API
    # ==================================================================

    async def call(
        self,
        execute_fn: Any,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        """
        Execute a provider call through the circuit breaker.

        Implements the retry strategy (3.4.3):
          Attempt 1: Execute normally.
          Attempt 2: Same provider, same params (retry on transient failure).
          Return failure after max_retries exhausted.

        Args:
            execute_fn: The provider's execute() coroutine function.
            request: Capability request.
            context: Execution context.
            trace_id: Cognitive trace ID.

        Returns:
            CapabilityResult (never raises to caller).
        """
        last_result: Optional[CapabilityResult] = None

        for attempt in range(1, self._config.max_retries + 1 + 1):
            # Check state before each attempt
            allowed, reject_result = self._check_state(request, trace_id)
            if not allowed:
                return reject_result  # type: ignore[return-value]

            # Execute with timeout
            result = await self._execute_with_timeout(execute_fn, request, context, trace_id)

            # Record outcome
            if result.success:
                self._record_success()
                return result

            # Failure path
            is_retriable = result.error is not None and result.error.retriable
            self._record_failure(result)
            last_result = result

            # Only retry if failure is retriable and we have attempts left
            if not is_retriable or attempt > self._config.max_retries:
                break

            logger.info(
                "[CB:%s] retry %d/%d for %s (error=%s)",
                self._provider_id,
                attempt,
                self._config.max_retries,
                request.capability_name,
                result.error.code if result.error else "unknown",
            )

        # All retries exhausted -- return final failure as non-retriable
        if last_result is not None and last_result.error is not None:
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code=last_result.error.code,
                error_message=f"{last_result.error.message} (after {self._config.max_retries + 1} attempts)",
                retriable=False,
                provider_id=self._provider_id,
                trace_id=trace_id,
                duration_ms=last_result.duration_ms,
            )
        return last_result or CapabilityResult.failure_result(
            request_id=request.request_id,
            error_code="circuit_breaker_error",
            error_message="Unknown error in circuit breaker",
            retriable=False,
            provider_id=self._provider_id,
            trace_id=trace_id,
        )

    def reset(self) -> None:
        """
        Force-reset the breaker to CLOSED state.

        Used by HealthChecker when a provider recovers.
        """
        with self._lock:
            old = self._state
            self._state = CircuitBreakerState.CLOSED
            self._failures.clear()
            self._opened_at_ms = 0
            self._half_open_permit = False
            self._consecutive_successes = 0
        if old != CircuitBreakerState.CLOSED:
            self._notify_state_change(old, CircuitBreakerState.CLOSED)

    def trip(self) -> None:
        """
        Force-open the breaker (e.g., from HealthChecker on failure).
        """
        with self._lock:
            old = self._state
            if old == CircuitBreakerState.OPEN:
                return
            self._state = CircuitBreakerState.OPEN
            self._opened_at_ms = self._now_ms()
        self._notify_state_change(old, CircuitBreakerState.OPEN)

    def allow_probe(self) -> None:
        """
        Signal the breaker to allow a single HALF_OPEN probe.

        Called by HealthChecker when a health check succeeds while
        the breaker is OPEN.
        """
        with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                old = self._state
                self._state = CircuitBreakerState.HALF_OPEN
                self._half_open_permit = True
                self._notify_state_change_locked(old, CircuitBreakerState.HALF_OPEN)

    def get_failures(self) -> List[FailureRecord]:
        """Return a copy of the current failure window."""
        with self._lock:
            self._prune_failures()
            return list(self._failures)

    # ==================================================================
    # Internal: state machine
    # ==================================================================

    def _check_state(
        self,
        request: CapabilityRequest,
        trace_id: str,
    ) -> tuple[bool, Optional[CapabilityResult]]:
        """
        Check whether the current state allows a request.

        Returns:
            (True, None) if allowed.
            (False, reject_result) if the breaker is open.
        """
        with self._lock:
            if self._state == CircuitBreakerState.CLOSED:
                return (True, None)

            if self._state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_permit:
                    self._half_open_permit = False  # consume the permit
                    return (True, None)
                # Already have a probe in flight -- reject
                return (
                    False,
                    CapabilityResult.failure_result(
                        request_id=request.request_id,
                        error_code=self._config.fallback_error_code,
                        error_message=(
                            f"Circuit breaker HALF_OPEN: probe in flight "
                            f"for provider '{self._provider_id}'"
                        ),
                        retriable=True,
                        provider_id=self._provider_id,
                        trace_id=trace_id,
                    ),
                )

            # OPEN: check if half_open_after_ms has elapsed
            assert self._state == CircuitBreakerState.OPEN
            elapsed = self._now_ms() - self._opened_at_ms
            if elapsed >= self._config.half_open_after_ms:
                old = self._state
                self._state = CircuitBreakerState.HALF_OPEN
                self._half_open_permit = False  # this request IS the probe
                self._notify_state_change_locked(old, CircuitBreakerState.HALF_OPEN)
                return (True, None)

            remaining = self._config.half_open_after_ms - elapsed
            return (
                False,
                CapabilityResult.failure_result(
                    request_id=request.request_id,
                    error_code=self._config.fallback_error_code,
                    error_message=(
                        f"Circuit breaker OPEN for provider '{self._provider_id}' "
                        f"(recovery in {remaining}ms)"
                    ),
                    retriable=True,
                    provider_id=self._provider_id,
                    trace_id=trace_id,
                ),
            )

    def _record_success(self) -> None:
        """Record a successful execution."""
        with self._lock:
            self._consecutive_successes += 1

            if self._state == CircuitBreakerState.HALF_OPEN:
                # Probe succeeded -> close the breaker
                old = self._state
                self._state = CircuitBreakerState.CLOSED
                self._failures.clear()
                self._opened_at_ms = 0
                self._consecutive_successes = 0
                self._notify_state_change_locked(old, CircuitBreakerState.CLOSED)

    def _record_failure(self, result: CapabilityResult) -> None:
        """Record a failed execution in the sliding window."""
        with self._lock:
            self._consecutive_successes = 0
            now = self._now_ms()
            record = FailureRecord(
                timestamp_ms=now,
                error_code=result.error.code if result.error else "unknown",
                error_message=result.error.message if result.error else "",
                retriable=result.error.retriable if result.error else False,
            )
            self._failures.append(record)
            self._prune_failures()

            if self._state == CircuitBreakerState.HALF_OPEN:
                # Probe failed -> re-open
                old = self._state
                self._state = CircuitBreakerState.OPEN
                self._opened_at_ms = now
                self._notify_state_change_locked(old, CircuitBreakerState.OPEN)
                return

            if (
                self._state == CircuitBreakerState.CLOSED
                and len(self._failures) >= self._config.failure_threshold
            ):
                old = self._state
                self._state = CircuitBreakerState.OPEN
                self._opened_at_ms = now
                self._notify_state_change_locked(old, CircuitBreakerState.OPEN)

    # ==================================================================
    # Internal: execution with timeout
    # ==================================================================

    async def _execute_with_timeout(
        self,
        execute_fn: Any,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        """Execute the provider function with CB timeout enforcement."""
        timeout_s = self._config.timeout_ms / 1000.0
        try:
            result = await asyncio.wait_for(
                execute_fn(request, context, trace_id),
                timeout=timeout_s,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(
                "[CB:%s] timeout after %dms for %s",
                self._provider_id,
                self._config.timeout_ms,
                request.capability_name,
            )
            return CapabilityResult.timeout_result(
                request_id=request.request_id,
                timeout_ms=self._config.timeout_ms,
                provider_id=self._provider_id,
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.error(
                "[CB:%s] unexpected error: %s: %s",
                self._provider_id,
                type(exc).__name__,
                exc,
            )
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="provider_error",
                error_message=f"Unexpected error: {type(exc).__name__}: {exc}",
                retriable=False,
                provider_id=self._provider_id,
                trace_id=trace_id,
            )

    # ==================================================================
    # Internal: sliding window
    # ==================================================================

    def _prune_failures(self) -> None:
        """Remove failures outside the sliding window. Caller holds _lock."""
        if not self._failures:
            return
        cutoff = self._now_ms() - self._config.failure_window_ms
        self._failures = [f for f in self._failures if f.timestamp_ms >= cutoff]

    # ==================================================================
    # Internal: notifications
    # ==================================================================

    def _notify_state_change(
        self,
        old: CircuitBreakerState,
        new: CircuitBreakerState,
    ) -> None:
        """Notify listener of state change (outside lock)."""
        logger.info(
            "[CB:%s] state change: %s -> %s",
            self._provider_id,
            old.value,
            new.value,
        )
        if self._on_state_change is not None:
            try:
                self._on_state_change.on_state_change(self._provider_id, old, new)
            except Exception as exc:
                logger.error(
                    "[CB:%s] on_state_change callback error: %s",
                    self._provider_id,
                    exc,
                )

    def _notify_state_change_locked(
        self,
        old: CircuitBreakerState,
        new: CircuitBreakerState,
    ) -> None:
        """
        Notify listener of state change (while holding _lock).

        Releases the lock, notifies, re-acquires.
        """
        self._lock.release()
        try:
            self._notify_state_change(old, new)
        finally:
            self._lock.acquire()

    # ==================================================================
    # Internal: time
    # ==================================================================

    @staticmethod
    def _now_ms() -> int:
        """Current monotonic time in milliseconds."""
        return int(time.monotonic() * 1000)

    # ==================================================================
    # Dunder
    # ==================================================================

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker("
            f"provider_id={self._provider_id!r}, "
            f"state={self._state.value}, "
            f"failures={self.failure_count}, "
            f"timeout={self._config.timeout_ms}ms)"
        )
