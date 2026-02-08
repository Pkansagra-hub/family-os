"""
k1.fabric.concurrency.timeout -- Deadline enforcement for capability requests.

Implements FAB-003 decision: TimeoutGuard wraps async execution with
per-request deadline enforcement. Each CapabilityRequest carries a
timeout_ms field; TimeoutGuard converts that to an asyncio.wait_for
deadline and raises DeadlineExceededError on expiry.

Design:
  - Wraps any async callable with asyncio.wait_for(timeout=...)
  - Reads deadline from CapabilityRequest.timeout_ms
  - Configurable default and minimum timeouts
  - Returns CapabilityResult.failure on deadline breach (retriable=True)
  - Thread-safe tracking of active guards for observability

References:
  - FAB-003 (Fabric Concurrency Model ADR, Backpressure Strategy table)
  - FAB-009 (WFQ scheduling, performance budgets)
  - CapabilityRequest.timeout_ms field

Exports:
  TimeoutGuard
  TimeoutGuardConfig
  DeadlineExceededError
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Dict, Optional

from k1.fabric.types import CapabilityRequest, CapabilityResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_MS: int = 30_000
"""Default timeout for requests that specify 0 or negative timeout_ms."""

MIN_TIMEOUT_MS: int = 100
"""Minimum enforceable timeout (100ms). Prevents unreasonably tight deadlines."""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DeadlineExceededError(Exception):
    """
    Raised when a capability request exceeds its deadline.

    Attributes:
        request_id: ID of the timed-out request.
        timeout_ms: The deadline that was exceeded.
        elapsed_ms: Actual elapsed time at cancellation.
        trace_id: Trace ID for correlation.
    """

    def __init__(
        self,
        message: str,
        request_id: str = "",
        timeout_ms: int = 0,
        elapsed_ms: int = 0,
        trace_id: str = "",
    ) -> None:
        super().__init__(message)
        self.request_id = request_id
        self.timeout_ms = timeout_ms
        self.elapsed_ms = elapsed_ms
        self.trace_id = trace_id


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeoutGuardConfig:
    """
    Configuration for TimeoutGuard.

    Attributes:
        default_timeout_ms: Timeout for requests with unset/zero timeout_ms.
            Default 30_000 (30 seconds).
        min_timeout_ms: Minimum enforceable timeout. Requests with timeout_ms
            below this are clamped up. Default 100ms.
        track_active: Whether to track active guard count for observability.
            Default True.
    """

    default_timeout_ms: int = DEFAULT_TIMEOUT_MS
    min_timeout_ms: int = MIN_TIMEOUT_MS
    track_active: bool = True

    def __post_init__(self) -> None:
        if self.default_timeout_ms < 1:
            raise ValueError(f"default_timeout_ms must be >= 1, got {self.default_timeout_ms}")
        if self.min_timeout_ms < 1:
            raise ValueError(f"min_timeout_ms must be >= 1, got {self.min_timeout_ms}")


# ---------------------------------------------------------------------------
# TimeoutGuard
# ---------------------------------------------------------------------------


class TimeoutGuard:
    """
    Deadline enforcement for capability requests.

    Wraps async execution callables with asyncio.wait_for to enforce
    the timeout_ms deadline from each CapabilityRequest. On timeout,
    raises DeadlineExceededError or returns CapabilityResult.failure
    depending on usage mode.

    Thread safety:
      - _lock protects _active_count for observability
      - asyncio handles async concurrency

    Usage:
        guard = TimeoutGuard()

        # Mode 1: execute_with_guard raises DeadlineExceededError
        result = await guard.execute_with_guard(request, execute_fn)

        # Mode 2: execute_safe returns CapabilityResult.failure on timeout
        result = await guard.execute_safe(request, execute_fn)
    """

    __slots__ = ("_config", "_active_count", "_total_timeouts", "_lock")

    def __init__(self, config: Optional[TimeoutGuardConfig] = None) -> None:
        """
        Initialize TimeoutGuard.

        Args:
            config: Guard configuration. Defaults to TimeoutGuardConfig().
        """
        self._config = config or TimeoutGuardConfig()
        self._active_count: int = 0
        self._total_timeouts: int = 0
        self._lock = threading.Lock()

    # ---- Properties ----

    @property
    def config(self) -> TimeoutGuardConfig:
        """Return guard configuration."""
        return self._config

    @property
    def active_count(self) -> int:
        """Number of requests currently under deadline enforcement."""
        with self._lock:
            return self._active_count

    @property
    def total_timeouts(self) -> int:
        """Total number of deadline breaches since creation."""
        with self._lock:
            return self._total_timeouts

    # ---- Timeout Resolution ----

    def resolve_timeout_ms(self, request: CapabilityRequest) -> int:
        """
        Resolve the effective timeout for a request.

        Priority:
          1. request.timeout_ms if > 0
          2. config.default_timeout_ms otherwise
          3. Clamped to >= config.min_timeout_ms

        Args:
            request: The capability request.

        Returns:
            Effective timeout in milliseconds.
        """
        raw = request.timeout_ms if request.timeout_ms > 0 else self._config.default_timeout_ms
        return max(raw, self._config.min_timeout_ms)

    # ---- Guard Execution ----

    async def execute_with_guard(
        self,
        request: CapabilityRequest,
        execute_fn: Callable[[CapabilityRequest], Coroutine[Any, Any, CapabilityResult]],
    ) -> CapabilityResult:
        """
        Execute with deadline enforcement. Raises DeadlineExceededError on timeout.

        Args:
            request: CapabilityRequest with timeout_ms deadline.
            execute_fn: Async callable that executes the request.

        Returns:
            CapabilityResult from execute_fn.

        Raises:
            DeadlineExceededError: If execution exceeds the deadline.
        """
        timeout_ms = self.resolve_timeout_ms(request)
        timeout_s = timeout_ms / 1000.0

        if self._config.track_active:
            with self._lock:
                self._active_count += 1

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(execute_fn(request), timeout=timeout_s)
            return result
        except asyncio.TimeoutError:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            with self._lock:
                self._total_timeouts += 1
            raise DeadlineExceededError(
                message=(
                    f"Request {request.request_id} exceeded deadline of "
                    f"{timeout_ms}ms (elapsed: {elapsed_ms}ms)"
                ),
                request_id=request.request_id,
                timeout_ms=timeout_ms,
                elapsed_ms=elapsed_ms,
                trace_id=request.trace_id,
            )
        finally:
            if self._config.track_active:
                with self._lock:
                    self._active_count -= 1

    async def execute_safe(
        self,
        request: CapabilityRequest,
        execute_fn: Callable[[CapabilityRequest], Coroutine[Any, Any, CapabilityResult]],
    ) -> CapabilityResult:
        """
        Execute with deadline enforcement. Returns failure result on timeout.

        Unlike execute_with_guard, this method catches DeadlineExceededError
        and converts it to a CapabilityResult.failure_result. Safe for use
        in pipelines that expect CapabilityResult return values.

        Args:
            request: CapabilityRequest with timeout_ms deadline.
            execute_fn: Async callable that executes the request.

        Returns:
            CapabilityResult -- success from execute_fn, or failure on timeout.
        """
        try:
            return await self.execute_with_guard(request, execute_fn)
        except DeadlineExceededError as exc:
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="deadline_exceeded",
                error_message=str(exc),
                retriable=True,
                trace_id=request.trace_id,
            )

    # ---- Stats ----

    def stats(self) -> Dict[str, Any]:
        """
        Return observability stats.

        Returns:
            Dict with active_count, total_timeouts, and config values.
        """
        with self._lock:
            return {
                "active_count": self._active_count,
                "total_timeouts": self._total_timeouts,
                "default_timeout_ms": self._config.default_timeout_ms,
                "min_timeout_ms": self._config.min_timeout_ms,
            }

    # ---- Repr ----

    def __repr__(self) -> str:
        return (
            f"TimeoutGuard("
            f"active={self._active_count}, "
            f"timeouts={self._total_timeouts}, "
            f"default={self._config.default_timeout_ms}ms)"
        )
