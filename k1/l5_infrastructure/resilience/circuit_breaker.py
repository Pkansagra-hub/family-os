"""
Layer 5 Resilience — Circuit Breaker Core (ADR-0009 / ADR-0009a / ADR-0009c)

Implements the three-state circuit breaker finite state machine (CLOSED → OPEN →
HALF_OPEN) defined in ADR-0009 and ADR-0009a. Provides fail-fast protection for
external dependencies, automatic recovery probing, structured observability, and
fallback handling that complies with the circuit breaker contracts under
``k1/contracts/error_recovery/circuit_breaker``.

Key behaviours (per contracts):
- Track failures within a rolling time window and open the circuit once the
  failure threshold is exceeded.
- Use monotonic clocks for all timeout calculations to avoid clock skew issues.
- Allow only a single probe request while HALF_OPEN and reject concurrent
  requests immediately (fail-fast).
- Emit Prometheus metrics for state, transitions, call outcomes, failures,
  fallbacks, and latency histograms.
- Propagate ``cognitive_trace_id`` through tracing spans and structured logs to
  preserve observability guarantees.
- Provide optional fallback invocation when the circuit is OPEN.

Performance budget (ADR-0009): <1ms state transition, <1ms rejection latency,
<5ms failure recording when running on CPython 3.11.

Threading Model:
    All circuit breaker APIs are async and require an event loop. The circuit breaker
    uses asyncio.Lock for state synchronization and must be called from within an
    async context. Do not use threading.Thread or multiprocessing; K1 follows the
    async/await concurrency model exclusively.

    Example:
        >>> breaker = CircuitBreaker(config)
        >>> result = await breaker.call(async_operation)  # ✓ Correct
        >>> # breaker.call(sync_operation)  # ✗ Wrong: missing await

    For background tasks, use asyncio.create_task() instead of threads.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any, Awaitable, Callable, Deque, Optional

from k1.l5_infrastructure.observability import get_metrics, get_tracer

try:  # pragma: no cover - structlog may be absent during unit tests
    import structlog  # type: ignore

    logger = structlog.get_logger(__name__)  # type: ignore
except ImportError:  # pragma: no cover - fallback for minimal environments
    import logging

    class _StructLogShim:
        """Shim that mimics structlog's API using stdlib logging."""

        def __init__(self, base_logger: logging.Logger) -> None:
            self._base = base_logger

        def _log(self, level: int, event: str, **kwargs: object) -> None:
            if kwargs:
                self._base.log(level, "%s %s", event, kwargs)
            else:
                self._base.log(level, "%s", event)

        def debug(self, event: str, **kwargs: object) -> None:
            self._log(logging.DEBUG, event, **kwargs)

        def info(self, event: str, **kwargs: object) -> None:
            self._log(logging.INFO, event, **kwargs)

        def warning(self, event: str, **kwargs: object) -> None:
            self._log(logging.WARNING, event, **kwargs)

        def error(self, event: str, **kwargs: object) -> None:
            self._log(logging.ERROR, event, **kwargs)

        def exception(self, event: str, **kwargs: object) -> None:
            self._base.exception("%s %s", event, kwargs)

    logger = _StructLogShim(logging.getLogger(__name__))


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerError",
    "CircuitBreakerOpenError",
    "FallbackUnavailableError",
    "CircuitState",
    "FailureClassification",
]


OperationCallable = Callable[..., Awaitable[Any] | Any]
FallbackCallable = Callable[[], Awaitable[Any] | Any]
FailurePredicate = Callable[[Any], bool]


class CircuitState(IntEnum):
    """Circuit breaker states mapped to integer values for Prometheus gauges."""

    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


class FailureClassification(str, Enum):
    """Failure taxonomies defined in circuit breaker contracts."""

    TIMEOUT = "timeout"
    EXCEPTION = "exception"
    SLOW_CALL = "slow_call"
    CUSTOM = "custom_predicate"


@dataclass(slots=True)
class CircuitBreakerConfig:
    """Configuration parameters for a circuit breaker instance."""

    service: str
    failure_threshold: int = 5
    time_window_ms: int = 60000
    timeout_duration_ms: int = 30000
    success_threshold: int = 1
    slow_call_threshold_ms: Optional[int] = None
    failure_exceptions: tuple[type[BaseException], ...] = (Exception,)
    fallback: Optional[FallbackCallable] = None
    failure_predicate: Optional[FailurePredicate] = None
    alternate_service: Optional[str] = None  # Separate label for metrics clarity

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0:
            msg = "failure_threshold must be positive"
            raise ValueError(msg)
        if self.success_threshold <= 0:
            msg = "success_threshold must be positive"
            raise ValueError(msg)
        if self.timeout_duration_ms <= 0:
            msg = "timeout_duration_ms must be positive"
            raise ValueError(msg)
        if self.time_window_ms <= 0:
            msg = "time_window_ms must be positive"
            raise ValueError(msg)


class CircuitBreakerError(RuntimeError):
    """Base error type for circuit breaker failures."""


class CircuitBreakerOpenError(CircuitBreakerError):
    """Raised when a caller attempts to execute work while the circuit is OPEN."""

    def __init__(self, service: str, *, retry_after_ms: float, reason: str) -> None:
        self.service = service
        self.retry_after_ms = max(retry_after_ms, 0.0)
        self.reason = reason
        message = (
            f"Circuit breaker for service '{service}' is OPEN due to {reason}. "
            f"Retry after {self.retry_after_ms:.0f}ms."
        )
        super().__init__(message)


class FallbackUnavailableError(CircuitBreakerError):
    """Raised when the configured fallback strategy fails during invocation."""

    def __init__(self, service: str, strategy: str, original: BaseException) -> None:
        message = (
            f"Fallback strategy '{strategy}' for service '{service}' failed: {original}"
        )
        super().__init__(message)
        self.service = service
        self.strategy = strategy
        self.original = original


_METRICS = get_metrics()
_TRACER = get_tracer()

_STATE_GAUGE = _METRICS.gauge(
    "circuit_breaker_state",
    "Circuit breaker current state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    labelnames=("component", "service", "alternate_service"),
)

_TRANSITIONS = _METRICS.counter(
    "circuit_breaker_transitions_total",
    "Total circuit breaker state transitions",
    labelnames=("component", "service", "alternate_service", "from_state", "to_state"),
)

_CALLS = _METRICS.counter(
    "circuit_breaker_calls_total",
    "Circuit breaker calls by result",
    labelnames=("component", "service", "alternate_service", "result"),
)

_FAILURES = _METRICS.counter(
    "circuit_breaker_failures_total",
    "Circuit breaker failures by type",
    labelnames=("component", "service", "alternate_service", "failure_type"),
)

_FALLBACKS = _METRICS.counter(
    "circuit_breaker_fallbacks_total",
    "Circuit breaker fallback invocations",
    labelnames=("component", "service", "alternate_service", "fallback_strategy"),
)

_LATENCY = _METRICS.histogram(
    "circuit_breaker_latency_ms",
    "Circuit breaker call latency in milliseconds",
    labelnames=("component", "service", "alternate_service", "state"),
    buckets=(
        0.1,
        1.0,
        10.0,
        50.0,
        100.0,
        500.0,
        1000.0,
        5000.0,
        10000.0,
    ),
)


def _is_slow_call(latency_ms: float, threshold_ms: Optional[int]) -> bool:
    return threshold_ms is not None and latency_ms > float(threshold_ms)


async def _maybe_await(value: Awaitable[Any] | Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class CircuitBreaker:
    """Circuit breaker core implementation matching ADR-0009/0009a requirements."""

    __slots__ = (
        "_config",
        "_state",
        "_monotonic",
        "_lock",
        "_failure_timestamps",
        "_success_count",
        "_half_open_probe_active",
        "_opened_at_monotonic",
    )

    def __init__(
        self,
        config: CircuitBreakerConfig,
        *,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._state = CircuitState.CLOSED
        self._monotonic = monotonic or time.monotonic
        self._lock = asyncio.Lock()
        self._failure_timestamps: Deque[float] = deque()
        self._success_count = 0
        self._half_open_probe_active = False
        self._opened_at_monotonic: float | None = None

        _STATE_GAUGE.labels(
            component="k1.resilience",
            service=config.service,
            alternate_service=config.alternate_service or "",
        ).set(CircuitState.CLOSED.value)

    @property
    def service(self) -> str:
        return self._config.service

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return len(self._failure_timestamps)

    @property
    def success_count(self) -> int:
        return self._success_count

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    def retry_after_ms(self) -> float:
        """
        Return remaining OPEN timeout in milliseconds for HTTP Retry-After headers.

        Returns 0.0 if circuit is not OPEN or timeout has elapsed.
        Useful for populating HTTP 503 Retry-After headers when circuit is OPEN.

        Example:
            retry_ms = breaker.retry_after_ms()
            if retry_ms > 0:
                response.headers["Retry-After"] = str(int(retry_ms / 1000))

        Returns:
            Remaining timeout in milliseconds (0.0 if not OPEN or timeout elapsed)
        """
        return self._retry_after_ms(self._monotonic())

    async def update_config(self, new_config: CircuitBreakerConfig) -> None:
        """
        Update circuit breaker configuration without resetting state.

        Preserves:
        - Current circuit state (CLOSED/OPEN/HALF_OPEN)
        - Failure timestamps within the rolling window
        - Opened timestamp (for OPEN timeout calculation)
        - Success count (for HALF_OPEN probe tracking)

        Used by ConfigManager during hot-reload to apply new thresholds/timeouts
        without dropping failure history or resetting OPEN circuits.

        Args:
            new_config: New configuration to apply

        Raises:
            ValueError: If new_config has invalid parameters
        """
        # Validate new config (triggers __post_init__ checks)
        new_config.__post_init__()

        async with self._lock:
            # Preserve state across config update
            old_service = self._config.service
            self._config = new_config

            # If service name changed, log warning (metrics labels will change)
            if old_service != new_config.service:
                logger.warning(
                    "circuit_breaker_service_name_changed",
                    old_service=old_service,
                    new_service=new_config.service,
                    state=self._state.name,
                )

            logger.info(
                "circuit_breaker_config_updated",
                service=self.service,
                failure_threshold=new_config.failure_threshold,
                timeout_duration_ms=new_config.timeout_duration_ms,
                state=self._state.name,
            )

    async def call(
        self,
        operation: OperationCallable,
        *args: Any,
        cognitive_trace_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute ``operation`` guarded by the circuit breaker."""

        permission = await self._acquire_permission(cognitive_trace_id)
        if not permission.allowed:
            return await self._handle_rejection(permission, cognitive_trace_id)

        token: object | None = None
        if cognitive_trace_id:
            token = _TRACER.attach_cognitive_trace(cognitive_trace_id)

        start = self._monotonic()
        try:
            with _TRACER.span(
                "k1.resilience.circuit_breaker.call",
                attributes={
                    "service": self.service,
                    "state": permission.state_at_call.name,
                },
            ):
                result = await _maybe_await(operation(*args, **kwargs))
        except self._config.failure_exceptions as exc:
            latency_ms = (self._monotonic() - start) * 1000.0
            _LATENCY.labels(
                component="k1.resilience",
                service=self.service,
                alternate_service=self._config.alternate_service or "",
                state=permission.state_at_call.name,
            ).observe(latency_ms)
            await self._record_failure(
                failure_type=self._classify_failure(exc, latency_ms),
                trace_id=cognitive_trace_id,
                latency_ms=latency_ms,
            )
            raise
        finally:
            if token is not None:
                _TRACER.detach(token)

        latency_ms = (self._monotonic() - start) * 1000.0
        _LATENCY.labels(
            component="k1.resilience",
            service=self.service,
            alternate_service=self._config.alternate_service or "",
            state=permission.state_at_call.name,
        ).observe(latency_ms)

        if self._should_count_as_failure(result, latency_ms):
            await self._record_failure(
                failure_type=(
                    FailureClassification.SLOW_CALL
                    if _is_slow_call(latency_ms, self._config.slow_call_threshold_ms)
                    else FailureClassification.CUSTOM
                ),
                trace_id=cognitive_trace_id,
                latency_ms=latency_ms,
            )
            return result

        await self._record_success(trace_id=cognitive_trace_id)
        return result

    async def _acquire_permission(self, trace_id: str | None) -> _Permission:
        timeout_seconds = self._config.timeout_duration_ms / 1000.0
        now = self._monotonic()
        async with self._lock:
            self._maybe_transition_from_open(now, trace_id)

            state = self._state
            if state == CircuitState.OPEN:
                retry_after = self._retry_after_ms(now)
                self._record_rejection_locked(trace_id, "open")
                return _Permission(
                    allowed=False,
                    state_at_call=state,
                    retry_after_ms=retry_after,
                    reason="open",
                )

            if state == CircuitState.HALF_OPEN and self._half_open_probe_active:
                self._record_rejection_locked(trace_id, "half_open_probe_in_flight")
                return _Permission(
                    allowed=False,
                    state_at_call=state,
                    retry_after_ms=timeout_seconds * 1000.0,
                    reason="half_open_probe_in_flight",
                )

            if state == CircuitState.HALF_OPEN:
                self._half_open_probe_active = True

            return _Permission(
                allowed=True,
                state_at_call=state,
                retry_after_ms=0.0,
                reason="allowed",
            )

    async def _handle_rejection(
        self, permission: _Permission, trace_id: str | None
    ) -> Any:
        fallback = self._config.fallback
        if fallback is None:
            raise CircuitBreakerOpenError(
                self.service,
                retry_after_ms=permission.retry_after_ms,
                reason=permission.reason,
            )

        strategy = getattr(fallback, "__name__", fallback.__class__.__name__)
        try:
            result = await _maybe_await(fallback())
        except Exception as exc:  # pragma: no cover - fallback failure path
            logger.error(
                "circuit_breaker_fallback_failed",
                service=self.service,
                fallback_strategy=strategy,
                circuit_state=self._state.name,
                trace_id=trace_id,
            )
            raise FallbackUnavailableError(self.service, strategy, exc) from exc

        _FALLBACKS.labels(
            component="k1.resilience",
            service=self.service,
            alternate_service=self._config.alternate_service or "",
            fallback_strategy=strategy,
        ).inc()
        logger.warning(
            "circuit_breaker_fallback",
            service=self.service,
            fallback_strategy=strategy,
            circuit_state=self._state.name,
            trace_id=trace_id,
        )
        return result

    async def _record_success(self, trace_id: str | None) -> None:
        async with self._lock:
            _CALLS.labels(
                component="k1.resilience",
                service=self.service,
                alternate_service=self._config.alternate_service or "",
                result="success",
            ).inc()

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_probe_active = False
                if self._success_count >= self._config.success_threshold:
                    self._transition_to(CircuitState.CLOSED, trace_id)
                    self._failure_timestamps.clear()
                    self._success_count = 0
                else:
                    logger.info(
                        "circuit_breaker_half_open_probe_success",
                        service=self.service,
                        success_count=self._success_count,
                        success_threshold=self._config.success_threshold,
                        trace_id=trace_id,
                    )
            else:
                self._failure_timestamps.clear()
                self._success_count = 0

    async def _record_failure(
        self,
        *,
        failure_type: FailureClassification,
        trace_id: str | None,
        latency_ms: float,
    ) -> None:
        now = self._monotonic()
        window_seconds = self._config.time_window_ms / 1000.0

        async with self._lock:
            _CALLS.labels(
                component="k1.resilience",
                service=self.service,
                alternate_service=self._config.alternate_service or "",
                result="failure",
            ).inc()
            _FAILURES.labels(
                component="k1.resilience",
                service=self.service,
                alternate_service=self._config.alternate_service or "",
                failure_type=failure_type.value,
            ).inc()

            self._half_open_probe_active = False
            self._failure_timestamps.append(now)

            while self._failure_timestamps:
                oldest = self._failure_timestamps[0]
                if now - oldest <= window_seconds:
                    break
                self._failure_timestamps.popleft()

            failure_count = len(self._failure_timestamps)
            logger.warning(
                "circuit_breaker_failure",
                service=self.service,
                failure_type=failure_type.value,
                failure_count=failure_count,
                threshold=self._config.failure_threshold,
                latency_ms=latency_ms,
                trace_id=trace_id,
            )

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN, trace_id)
                self._failure_timestamps.clear()
                return

            if failure_count >= self._config.failure_threshold:
                self._transition_to(CircuitState.OPEN, trace_id)
                self._failure_timestamps.clear()

    def _maybe_transition_from_open(self, now: float, trace_id: str | None) -> None:
        if self._state != CircuitState.OPEN:
            return
        if self._opened_at_monotonic is None:
            return

        timeout_seconds = self._config.timeout_duration_ms / 1000.0
        if now - self._opened_at_monotonic >= timeout_seconds:
            self._transition_to(CircuitState.HALF_OPEN, trace_id)
            self._success_count = 0
            self._half_open_probe_active = False

    def _transition_to(self, new_state: CircuitState, trace_id: str | None) -> None:
        if new_state == self._state:
            return

        old_state = self._state
        self._state = new_state
        _STATE_GAUGE.labels(
            component="k1.resilience",
            service=self.service,
            alternate_service=self._config.alternate_service or "",
        ).set(new_state.value)
        _TRANSITIONS.labels(
            component="k1.resilience",
            service=self.service,
            alternate_service=self._config.alternate_service or "",
            from_state=old_state.name,
            to_state=new_state.name,
        ).inc()
        logger.info(
            "circuit_breaker_transition",
            service=self.service,
            from_state=old_state.name,
            to_state=new_state.name,
            trace_id=trace_id,
        )

        if new_state == CircuitState.OPEN:
            self._opened_at_monotonic = self._monotonic()
            logger.warning(
                "circuit_breaker_opened",
                service=self.service,
                failure_threshold=self._config.failure_threshold,
                timeout_duration_ms=self._config.timeout_duration_ms,
                trace_id=trace_id,
            )
        elif new_state == CircuitState.CLOSED:
            self._opened_at_monotonic = None
            self._success_count = 0
            logger.info(
                "circuit_breaker_closed",
                service=self.service,
                trace_id=trace_id,
            )
        elif new_state == CircuitState.HALF_OPEN:
            logger.info(
                "circuit_breaker_half_open",
                service=self.service,
                trace_id=trace_id,
            )

    def _record_rejection_locked(self, trace_id: str | None, reason: str) -> None:
        _CALLS.labels(
            component="k1.resilience",
            service=self.service,
            alternate_service=self._config.alternate_service or "",
            result="rejected",
        ).inc()
        logger.warning(
            "circuit_breaker_rejected",
            service=self.service,
            reason=reason,
            circuit_state=self._state.name,
            trace_id=trace_id,
        )

    def _should_count_as_failure(self, result: Any, latency_ms: float) -> bool:
        if _is_slow_call(latency_ms, self._config.slow_call_threshold_ms):
            return True
        predicate = self._config.failure_predicate
        if predicate is None:
            return False
        try:
            return predicate(result)
        except Exception:  # pragma: no cover - defensive guard
            logger.exception(
                "circuit_breaker_failure_predicate_error",
                service=self.service,
            )
            return False

    def _classify_failure(
        self, exc: BaseException, latency_ms: float
    ) -> FailureClassification:
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return FailureClassification.TIMEOUT
        if _is_slow_call(latency_ms, self._config.slow_call_threshold_ms):
            return FailureClassification.SLOW_CALL
        return FailureClassification.EXCEPTION

    def _retry_after_ms(self, now: float) -> float:
        if self._opened_at_monotonic is None:
            return float(self._config.timeout_duration_ms)
        elapsed = now - self._opened_at_monotonic
        remaining = (self._config.timeout_duration_ms / 1000.0) - elapsed
        return max(remaining, 0.0) * 1000.0


@dataclass(slots=True)
class _Permission:
    allowed: bool
    state_at_call: CircuitState
    retry_after_ms: float
    reason: str
