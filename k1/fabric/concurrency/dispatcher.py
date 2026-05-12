"""
k1.fabric.concurrency.dispatcher -- Async request dispatcher with bounded parallelism.

Implements FAB-003 decision: Hybrid async facade + WFQ-scheduled agent execution.
Replaces the FABRIC_MAILBOX with asyncio.Semaphore-based backpressure and
async dispatching.

Design:
  - asyncio.Semaphore(max_concurrent) bounds total in-flight requests
  - Backpressure levels: NORMAL -> WARNING (80%) -> SHEDDING (95%) -> SATURATED (100%)
  - At SHEDDING level: BACKGROUND priority requests are rejected
  - At SATURATED level: all new requests are rejected
  - Events emitted at WARNING and SHEDDING transitions
  - Thread-safe counters for in-flight tracking
  - Graceful shutdown with drain support

References:
  - FAB-003 (Fabric Concurrency Model ADR)
  - FAB-009 (WFQ scheduling, performance budgets)
  - ADR-0028 (WFQ priority classes)
  - k1_cognitive_architecture_skeleton.mmd (FABRIC_MAILBOX -> replaced by dispatcher)

Exports:
  FabricDispatcher
  FabricDispatcherConfig
  DispatchResult
  DispatcherHealth
  DispatcherError
  DispatcherOverloadedError
  DispatcherShutdownError
  BackpressureLevel
  DEFAULT_MAX_CONCURRENT
  DEFAULT_WARNING_THRESHOLD
  DEFAULT_SHEDDING_THRESHOLD
  PRESSURE_WARNING_TOPIC
  PRESSURE_SHEDDING_TOPIC
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional

from k1.fabric.types import CapabilityRequest, CapabilityResult, WFQPriority

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_CONCURRENT: int = 10
"""Default maximum concurrent requests (semaphore limit). From FAB-003."""

DEFAULT_WARNING_THRESHOLD: float = 0.80
"""Queue depth ratio at which WARNING backpressure is signaled (80%)."""

DEFAULT_SHEDDING_THRESHOLD: float = 0.95
"""Queue depth ratio at which BACKGROUND requests are shed (95%)."""

PRESSURE_WARNING_TOPIC: str = "k1.fabric.pressure.warning.v1"
"""Event topic emitted when backpressure reaches WARNING level."""

PRESSURE_SHEDDING_TOPIC: str = "k1.fabric.pressure.shedding.v1"
"""Event topic emitted when backpressure reaches SHEDDING level."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BackpressureLevel(str, Enum):
    """Backpressure level of the dispatcher."""

    NORMAL = "NORMAL"
    """Below warning threshold. All requests accepted."""

    WARNING = "WARNING"
    """Above warning threshold (80%). All requests accepted, event emitted."""

    SHEDDING = "SHEDDING"
    """Above shedding threshold (95%). BACKGROUND requests rejected."""

    SATURATED = "SATURATED"
    """At 100% capacity. All new requests rejected."""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DispatcherError(Exception):
    """Base exception for dispatcher operations."""

    pass


class DispatcherOverloadedError(DispatcherError):
    """
    Raised when the dispatcher rejects a request due to backpressure.

    Attributes:
        level: Current BackpressureLevel at rejection time
        in_flight: Number of in-flight requests
        max_concurrent: Configured maximum concurrent requests
        rejected_priority: WFQ priority of the rejected request
    """

    def __init__(
        self,
        message: str,
        level: BackpressureLevel,
        in_flight: int,
        max_concurrent: int,
        rejected_priority: str = "",
    ) -> None:
        super().__init__(message)
        self.level = level
        self.in_flight = in_flight
        self.max_concurrent = max_concurrent
        self.rejected_priority = rejected_priority


class DispatcherShutdownError(DispatcherError):
    """Raised when dispatch is called after shutdown."""

    pass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FabricDispatcherConfig:
    """
    Configuration for FabricDispatcher.

    Attributes:
        max_concurrent: Maximum in-flight requests (semaphore limit).
            Default 10 per FAB-003.
        warning_threshold: Ratio of in-flight/max at which WARNING is signaled.
            Default 0.80 (80%).
        shedding_threshold: Ratio of in-flight/max at which BACKGROUND is shed.
            Default 0.95 (95%).
        emit_events: Whether to emit backpressure events via event_callback.
            Default True.
    """

    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    warning_threshold: float = DEFAULT_WARNING_THRESHOLD
    shedding_threshold: float = DEFAULT_SHEDDING_THRESHOLD
    emit_events: bool = True

    def __post_init__(self) -> None:
        if self.max_concurrent < 1:
            raise ValueError(f"max_concurrent must be >= 1, got {self.max_concurrent}")
        if not (0.0 < self.warning_threshold < 1.0):
            raise ValueError(f"warning_threshold must be in (0, 1), got {self.warning_threshold}")
        if not (0.0 < self.shedding_threshold <= 1.0):
            raise ValueError(f"shedding_threshold must be in (0, 1], got {self.shedding_threshold}")
        if self.shedding_threshold <= self.warning_threshold:
            raise ValueError(
                f"shedding_threshold ({self.shedding_threshold}) must be > "
                f"warning_threshold ({self.warning_threshold})"
            )


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DispatchResult:
    """
    Result of a dispatch operation.

    Wraps CapabilityResult with dispatcher metadata: queue wait time,
    backpressure level at dispatch time, and whether the request was
    priority-shed.

    Attributes:
        result: The underlying CapabilityResult from execution.
        wait_ms: Time spent waiting for semaphore acquisition (ms).
        backpressure_at_entry: BackpressureLevel when request entered dispatcher.
        dispatched: Whether the request was actually dispatched (False if rejected).
    """

    result: CapabilityResult = field(default_factory=CapabilityResult)
    wait_ms: int = 0
    backpressure_at_entry: str = BackpressureLevel.NORMAL.value
    dispatched: bool = True


@dataclass(frozen=True)
class DispatcherHealth:
    """
    Health snapshot of the dispatcher.

    Attributes:
        in_flight: Current number of in-flight requests.
        max_concurrent: Configured maximum.
        utilization: in_flight / max_concurrent ratio.
        backpressure_level: Current BackpressureLevel.
        total_dispatched: Total requests dispatched since creation.
        total_rejected: Total requests rejected due to backpressure/shutdown.
        total_completed: Total requests that completed (success or failure).
        is_shutdown: Whether the dispatcher has been shut down.
    """

    in_flight: int = 0
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    utilization: float = 0.0
    backpressure_level: str = BackpressureLevel.NORMAL.value
    total_dispatched: int = 0
    total_rejected: int = 0
    total_completed: int = 0
    is_shutdown: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "in_flight": self.in_flight,
            "max_concurrent": self.max_concurrent,
            "utilization": round(self.utilization, 4),
            "backpressure_level": self.backpressure_level,
            "total_dispatched": self.total_dispatched,
            "total_rejected": self.total_rejected,
            "total_completed": self.total_completed,
            "is_shutdown": self.is_shutdown,
        }


# ---------------------------------------------------------------------------
# FabricDispatcher
# ---------------------------------------------------------------------------


class FabricDispatcher:
    """
    Async request dispatcher with bounded parallelism.

    Replaces the FABRIC_MAILBOX from the architecture skeleton (FAB-003).
    Uses asyncio.Semaphore for backpressure and async dispatching for
    zero-overhead on the fast path (Retrieval + Resolution).

    Concurrency model:
      - Semaphore(max_concurrent) limits total in-flight requests
      - Backpressure levels escalate based on utilization ratio
      - BACKGROUND requests are shed at SHEDDING level (95%)
      - All requests rejected at SATURATED level (100%)

    Thread safety:
      - _lock protects counter mutations (_in_flight, _total_*)
      - asyncio.Semaphore handles async concurrency
      - Safe for use from multiple asyncio tasks + external threads

    Usage:
        config = FabricDispatcherConfig(max_concurrent=10)
        dispatcher = FabricDispatcher(config)

        # dispatch calls the execute_fn under semaphore guard
        result = await dispatcher.dispatch(request, execute_fn)
    """

    __slots__ = (
        "_config",
        "_semaphore",
        "_semaphore_lock",
        "_in_flight",
        "_total_dispatched",
        "_total_rejected",
        "_total_completed",
        "_lock",
        "_event_callback",
        "_is_shutdown",
        "_last_level",
        "_per_priority_in_flight",
    )

    def __init__(
        self,
        config: Optional[FabricDispatcherConfig] = None,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        """
        Initialize FabricDispatcher.

        Args:
            config: Dispatcher configuration. Defaults to FabricDispatcherConfig().
            event_callback: Optional callback for backpressure events.
                Signature: (topic: str, payload: dict) -> None.
                Called when backpressure level transitions to WARNING or SHEDDING.
        """
        self._config = config or FabricDispatcherConfig()
        # Issue 1 fix: create Semaphore lazily on first dispatch() call so it
        # binds to the correct running event loop, not the one active at
        # construction time (which may not exist or be a different loop).
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._semaphore_lock = threading.Lock()  # guards one-time init
        self._in_flight: int = 0
        self._total_dispatched: int = 0
        self._total_rejected: int = 0
        self._total_completed: int = 0
        self._lock = threading.RLock()
        self._event_callback = event_callback
        self._is_shutdown: bool = False
        self._last_level: BackpressureLevel = BackpressureLevel.NORMAL
        self._per_priority_in_flight: Dict[str, int] = {p.value: 0 for p in WFQPriority}

    # ---- Properties ----

    @property
    def config(self) -> FabricDispatcherConfig:
        """Return dispatcher configuration."""
        return self._config

    @property
    def in_flight(self) -> int:
        """Current number of in-flight requests."""
        with self._lock:
            return self._in_flight

    @property
    def max_concurrent(self) -> int:
        """Configured maximum concurrent requests."""
        return self._config.max_concurrent

    @property
    def utilization(self) -> float:
        """Current utilization ratio (in_flight / max_concurrent)."""
        with self._lock:
            return self._in_flight / self._config.max_concurrent

    @property
    def is_shutdown(self) -> bool:
        """Whether the dispatcher has been shut down."""
        return self._is_shutdown

    # ---- Backpressure ----

    def backpressure_level(self) -> BackpressureLevel:
        """
        Compute current backpressure level from utilization.

        Returns:
            BackpressureLevel based on current in_flight / max_concurrent ratio.
        """
        with self._lock:
            ratio = self._in_flight / self._config.max_concurrent
        if ratio >= 1.0:
            return BackpressureLevel.SATURATED
        if ratio >= self._config.shedding_threshold:
            return BackpressureLevel.SHEDDING
        if ratio >= self._config.warning_threshold:
            return BackpressureLevel.WARNING
        return BackpressureLevel.NORMAL

    def _should_reject(self, request: CapabilityRequest) -> Optional[str]:
        """
        Check if request should be rejected based on backpressure.

        Returns:
            Rejection reason string, or None if request is accepted.
        """
        level = self.backpressure_level()

        if level == BackpressureLevel.SATURATED:
            return (
                f"Dispatcher saturated ({self._in_flight}/{self._config.max_concurrent}). "
                f"All requests rejected."
            )

        if (
            level == BackpressureLevel.SHEDDING
            and request.wfq_priority == WFQPriority.BACKGROUND.value
        ):
            return (
                f"Dispatcher shedding BACKGROUND at "
                f"{self._in_flight}/{self._config.max_concurrent}. "
                f"BACKGROUND requests rejected."
            )

        return None

    def _emit_backpressure_event(self, level: BackpressureLevel) -> None:
        """Emit backpressure transition event if configured and level escalated."""
        if not self._config.emit_events or self._event_callback is None:
            return

        if level == self._last_level:
            return

        topic: Optional[str] = None
        if level == BackpressureLevel.WARNING:
            topic = PRESSURE_WARNING_TOPIC
        elif level == BackpressureLevel.SHEDDING:
            topic = PRESSURE_SHEDDING_TOPIC

        if topic is not None:
            payload = {
                "level": level.value,
                "in_flight": self._in_flight,
                "max_concurrent": self._config.max_concurrent,
                "utilization": round(self._in_flight / self._config.max_concurrent, 4),
                "timestamp_ms": int(time.time() * 1000),
            }
            try:
                self._event_callback(topic, payload)
            except Exception:
                pass  # Event emission must not break dispatch path

        self._last_level = level

    # ---- Dispatch ----

    async def dispatch(
        self,
        request: CapabilityRequest,
        execute_fn: Callable[[CapabilityRequest], Coroutine[Any, Any, CapabilityResult]],
    ) -> DispatchResult:
        """
        Dispatch a capability request through bounded parallelism.

        Flow:
          1. Check shutdown state
          2. Check backpressure (reject if SATURATED or shedding BACKGROUND)
          3. Acquire semaphore (back-pressure to caller if at limit)
          4. Track in-flight, emit backpressure events
          5. Execute via execute_fn
          6. Decrement in-flight, return DispatchResult

        Args:
            request: CapabilityRequest to dispatch.
            execute_fn: Async callable that executes the request and returns
                CapabilityResult. This is typically FabricFacade._execute_pipeline().

        Returns:
            DispatchResult wrapping the CapabilityResult with dispatcher metadata.

        Raises:
            DispatcherShutdownError: If dispatcher has been shut down.
            DispatcherOverloadedError: If request is rejected due to backpressure.
        """
        if self._is_shutdown:
            raise DispatcherShutdownError(
                "Dispatcher has been shut down. No new requests accepted."
            )

        # Lazy semaphore init: create inside the running event loop so it
        # is bound to the correct loop (Issue 1 fix).
        if self._semaphore is None:
            with self._semaphore_lock:
                if self._semaphore is None:
                    self._semaphore = asyncio.Semaphore(self._config.max_concurrent)

        # Pre-semaphore backpressure check (fast reject for shed/saturated)
        rejection = self._should_reject(request)
        if rejection is not None:
            level = self.backpressure_level()
            with self._lock:
                self._total_rejected += 1
            raise DispatcherOverloadedError(
                message=rejection,
                level=level,
                in_flight=self._in_flight,
                max_concurrent=self._config.max_concurrent,
                rejected_priority=request.wfq_priority,
            )

        entry_level = self.backpressure_level()
        wait_start = time.monotonic()

        # Acquire semaphore (blocks if at capacity -- back-pressure to caller)
        await self._semaphore.acquire()

        wait_ms = int((time.monotonic() - wait_start) * 1000)

        # Track in-flight
        with self._lock:
            self._in_flight += 1
            self._total_dispatched += 1
            self._per_priority_in_flight[request.wfq_priority] = (
                self._per_priority_in_flight.get(request.wfq_priority, 0) + 1
            )

        # Emit backpressure event if level changed
        current_level = self.backpressure_level()
        self._emit_backpressure_event(current_level)

        try:
            result = await execute_fn(request)
            return DispatchResult(
                result=result,
                wait_ms=wait_ms,
                backpressure_at_entry=entry_level.value,
                dispatched=True,
            )
        finally:
            with self._lock:
                self._in_flight -= 1
                self._total_completed += 1
                self._per_priority_in_flight[request.wfq_priority] = max(
                    0,
                    self._per_priority_in_flight.get(request.wfq_priority, 1) - 1,
                )
            self._semaphore.release()
            # Emit de-escalation event
            new_level = self.backpressure_level()
            self._emit_backpressure_event(new_level)

    # ---- Health ----

    def health(self) -> DispatcherHealth:
        """
        Return a health snapshot of the dispatcher.

        Returns:
            DispatcherHealth with current counters and state.
        """
        with self._lock:
            return DispatcherHealth(
                in_flight=self._in_flight,
                max_concurrent=self._config.max_concurrent,
                utilization=round(self._in_flight / self._config.max_concurrent, 4),
                backpressure_level=self.backpressure_level().value,
                total_dispatched=self._total_dispatched,
                total_rejected=self._total_rejected,
                total_completed=self._total_completed,
                is_shutdown=self._is_shutdown,
            )

    def per_priority_snapshot(self) -> Dict[str, int]:
        """
        Return in-flight count per WFQ priority class.

        Returns:
            Dict mapping WFQPriority value -> in-flight count.
        """
        with self._lock:
            return dict(self._per_priority_in_flight)

    # ---- Shutdown ----

    async def shutdown(self) -> int:
        """
        Gracefully shut down the dispatcher.

        Sets shutdown flag so no new requests are accepted.
        Waits for all in-flight requests to complete by acquiring
        all semaphore permits.

        Returns:
            Number of requests that were in-flight when shutdown started.
        """
        self._is_shutdown = True
        with self._lock:
            was_in_flight = self._in_flight

        # If semaphore was never initialised there are no in-flight requests.
        if self._semaphore is not None:
            # Drain: acquire all permits to ensure all in-flight complete
            for _ in range(self._config.max_concurrent):
                await self._semaphore.acquire()

        return was_in_flight

    # ---- Repr ----

    def __repr__(self) -> str:
        level = self.backpressure_level().value
        return (
            f"FabricDispatcher("
            f"in_flight={self._in_flight}, "
            f"max={self._config.max_concurrent}, "
            f"level={level}, "
            f"shutdown={self._is_shutdown})"
        )
