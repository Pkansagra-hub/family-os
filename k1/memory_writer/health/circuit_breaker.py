"""
k1.memory_writer.health.circuit_breaker -- LLM circuit breaker.

Three states:
  CLOSED:    Normal operation. Tracks consecutive failures.
  OPEN:      All calls blocked. Timer running for recovery probe.
  HALF_OPEN: One probe call allowed. Success → CLOSED, failure → OPEN.

Uses consecutive failure count (not sliding window) for simplicity.
Single-session MW means single-threaded access.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Callable, Optional

log = logging.getLogger(__name__)


class CircuitBreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """LLM circuit breaker for Memory Writer.

    Three states:
      CLOSED:    Normal operation. Tracks consecutive failures.
      OPEN:      All calls blocked. Timer running for recovery probe.
      HALF_OPEN: One probe call allowed. Success → CLOSED, failure → OPEN.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_probe_seconds: float = 30.0,
        *,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_probe_seconds = recovery_probe_seconds
        self._clock = clock or time.monotonic

        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures: int = 0
        self._last_failure_time: float = 0.0
        self._total_trips: int = 0

    @property
    def is_open(self) -> bool:
        """Check if calls should be blocked.

        Returns True for OPEN state (unless recovery time elapsed).
        HALF_OPEN returns False (allow one probe call).
        """
        if self._state == CircuitBreakerState.CLOSED:
            return False

        if self._state == CircuitBreakerState.HALF_OPEN:
            return False  # Allow one probe call

        # OPEN: check if recovery time elapsed
        elapsed = self._clock() - self._last_failure_time
        if elapsed >= self._recovery_probe_seconds:
            self._state = CircuitBreakerState.HALF_OPEN
            return False  # Allow probe

        return True  # Still OPEN

    @property
    def state(self) -> CircuitBreakerState:
        """Current circuit breaker state (triggers OPEN → HALF_OPEN check)."""
        _ = self.is_open
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def total_trips(self) -> int:
        """Total number of CLOSED → OPEN transitions (lifetime)."""
        return self._total_trips

    def record_success(self) -> None:
        """Record a successful LLM call.

        CLOSED: reset failure count.
        HALF_OPEN: transition to CLOSED.
        """
        if self._state == CircuitBreakerState.HALF_OPEN:
            log.info("MW: circuit breaker HALF_OPEN → CLOSED (probe succeeded)")
        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed LLM call.

        CLOSED: increment failure count. If >= threshold → OPEN.
        HALF_OPEN: probe failed → back to OPEN.
        """
        self._consecutive_failures += 1
        self._last_failure_time = self._clock()

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.OPEN
            log.info("MW: circuit breaker HALF_OPEN → OPEN (probe failed)")
            return

        if self._consecutive_failures >= self._failure_threshold:
            self._state = CircuitBreakerState.OPEN
            self._total_trips += 1
            log.warning(
                "MW: circuit breaker CLOSED → OPEN, failures=%d, threshold=%d",
                self._consecutive_failures,
                self._failure_threshold,
            )

    def reset(self) -> None:
        """Force reset to CLOSED state (for testing/admin)."""
        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
