"""Layer 5 Resilience — Retry Policy (ADR-0008b).

This module implements the exponential backoff retry policy defined in
ADR-0008b (Forward Recovery vs Backward Recovery) and the associated
contracts under ``k1/contracts/error_recovery/saga/forward_vs_backward_recovery``.

The retry policy provides:

* Failure classification into TRANSIENT, PERMANENT, or AMBIGUOUS categories
  (ADR-0008b §1) with extensible rules for HTTP/network errors.
* Exponential backoff with 20% jitter and a 10s budget envelope (ADR-0008b §3).
* Optional circuit breaker awareness to avoid retry storms when the breaker is
  open (ADR-0009/0009a).
* Idempotency safeguards for ambiguous failures when the operation is not
  idempotent (ADR-0008a).
* Structured observability via Prometheus metrics, OpenTelemetry spans, and
  structured logging (<5ms decision budget per ADR-0024).

The default retry configuration matches the canonical values documented in the
contracts:

``max_retries = 5`` → delays: 100ms, 200ms, 400ms, 800ms, 1600ms
``jitter = ±20%``  → prevents thundering herd behaviour
``retry_budget = 10_000ms`` → total time spent retrying per operation

Threading Model:
    All retry policy APIs are async and require an event loop. The policy uses
    asyncio.sleep() for delays and must be called from within an async context.
    Do not use threading.Thread or multiprocessing; K1 follows the async/await
    concurrency model exclusively.

    Example:
        >>> policy = RetryPolicy()
        >>> result = await policy.execute(operation, idempotent=True)  # ✓ Correct
        >>> # policy.execute(operation, idempotent=True)  # ✗ Wrong: missing await

    For background tasks, use asyncio.create_task() instead of threads.

Usage example:

.. code-block:: python

        policy = RetryPolicy()

        async def unreliable_call() -> str:
                response = await http_client.get("https://api.example.com/data")
                response.raise_for_status()
                return response.text

        result = await policy.execute(
                unreliable_call,
                idempotent=True,
                cognitive_trace_id="trace-123",
                description="fetch-data",
        )

The implementation is intentionally dependency-light and does not assume a
particular HTTP client; classification is driven by error attributes instead of
concrete exception types to preserve flexibility across components.
"""

from __future__ import annotations

import asyncio
import inspect
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Sequence, TypeVar

from k1.l5_infrastructure.observability import get_metrics, get_tracer

try:  # pragma: no cover - structlog may be optional in slim test environments
    import structlog  # type: ignore

    logger = structlog.get_logger(__name__)  # type: ignore
except ImportError:  # pragma: no cover - fallback shim
    import logging

    class _StructLogShim:
        """Minimal shim replicating structlog's API with stdlib logging."""

        def __init__(self, base: logging.Logger) -> None:
            self._base = base

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
    "FailureType",
    "FailureClassifier",
    "RetryPolicyConfig",
    "RetryAttemptInfo",
    "RetryPolicy",
    "RetryError",
    "RetryBudgetExceeded",
    "RetryAttemptsExceeded",
    "RetryAbortedError",
]


T = TypeVar("T")


class FailureType(str, Enum):
    """Failure classifications defined by ADR-0008b."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    AMBIGUOUS = "ambiguous"


@dataclass(slots=True)
class RetryPolicyConfig:
    """Configuration values for :class:`RetryPolicy`.

    The defaults match the canonical contract values. ``max_retries`` represents
    the number of *retries* after the initial attempt (i.e. 5 → up to 6 total
    attempts). ``jitter_percent`` is expressed as a fractional value (0.2 == 20%).
    """

    name: str = "default"
    max_retries: int = 5
    base_delay_ms: float = 100.0
    max_delay_ms: float = 1600.0
    jitter_percent: float = 0.20
    retry_budget_ms: float = 10_000.0
    respect_circuit_breaker: bool = True
    allowed_transient: Sequence[type[BaseException]] = (
        TimeoutError,
        asyncio.TimeoutError,
        ConnectionError,
    )
    allowed_permanent: Sequence[type[BaseException]] = (
        ValueError,
        PermissionError,
    )

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            msg = "max_retries must be non-negative"
            raise ValueError(msg)
        if self.base_delay_ms <= 0:
            msg = "base_delay_ms must be positive"
            raise ValueError(msg)
        if self.max_delay_ms < self.base_delay_ms:
            msg = "max_delay_ms must be >= base_delay_ms"
            raise ValueError(msg)
        if not (0.0 <= self.jitter_percent <= 1.0):
            msg = "jitter_percent must be between 0.0 and 1.0"
            raise ValueError(msg)
        if self.retry_budget_ms <= 0:
            msg = "retry_budget_ms must be positive"
            raise ValueError(msg)


@dataclass(slots=True)
class RetryAttemptInfo:
    """Metadata about an individual retry attempt."""

    attempt_number: int
    classification: FailureType
    delay_ms: float
    total_elapsed_ms: float
    exception: BaseException


class FailureClassifier:
    """Classifies exceptions into retry categories.

    The classifier relies on a combination of explicit exception type mappings
    and well-known attributes (``status``, ``status_code``, ``phase``) so that it
    works with multiple HTTP client libraries without taking a hard dependency.
    """

    #: HTTP status codes classified as transient, permanent, or ambiguous.
    _TRANSIENT_STATUS = {429, 503, 504, 599}
    _PERMANENT_STATUS = {400, 401, 403, 404, 405, 422}
    _AMBIGUOUS_STATUS = {500, 502}

    def __init__(
        self,
        *,
        config: RetryPolicyConfig,
        custom_rules: Optional[dict[type[BaseException], FailureType]] = None,
    ) -> None:
        self._config = config
        self._custom_rules = custom_rules or {}

    def classify(self, error: BaseException) -> FailureType:
        """Classify ``error`` into a :class:`FailureType`."""

        error_type = type(error)

        if error_type in self._custom_rules:
            return self._custom_rules[error_type]

        if isinstance(error, tuple(self._config.allowed_transient)):
            phase = getattr(error, "phase", None)
            if phase == "after_send":
                return FailureType.AMBIGUOUS
            return FailureType.TRANSIENT

        if isinstance(error, tuple(self._config.allowed_permanent)):
            return FailureType.PERMANENT

        status = self._extract_status(error)
        if status is not None:
            if status in self._TRANSIENT_STATUS:
                return FailureType.TRANSIENT
            if status in self._PERMANENT_STATUS:
                return FailureType.PERMANENT
            if status in self._AMBIGUOUS_STATUS:
                return FailureType.AMBIGUOUS

        if isinstance(error, OSError):
            return FailureType.TRANSIENT

        return FailureType.AMBIGUOUS

    @staticmethod
    def _extract_status(error: BaseException) -> Optional[int]:
        """Best-effort extraction of HTTP status code from ``error``."""

        for attribute in ("status", "status_code", "response"):
            value = getattr(error, attribute, None)
            if isinstance(value, int):
                return value
            if value is not None:
                maybe_status = getattr(value, "status", None)
                if isinstance(maybe_status, int):
                    return maybe_status
                maybe_status = getattr(value, "status_code", None)
                if isinstance(maybe_status, int):
                    return maybe_status
        return None


class RetryError(RuntimeError):
    """Base error for retry policy failures."""


class RetryBudgetExceeded(RetryError):
    """Raised when the cumulative retry delay exceeds the configured budget."""

    def __init__(self, *, description: str, budget_ms: float) -> None:
        super().__init__(
            f"Retry budget exceeded for '{description}' after {budget_ms:.0f}ms"
        )
        self.description = description
        self.budget_ms = budget_ms


class RetryAttemptsExceeded(RetryError):
    """Raised when all retry attempts are exhausted without success."""

    def __init__(self, *, description: str, attempts: int) -> None:
        super().__init__(
            f"Maximum retry attempts ({attempts}) exceeded for '{description}'"
        )
        self.description = description
        self.attempts = attempts


class RetryAbortedError(RetryError):
    """Raised when retrying would violate idempotency guarantees."""

    def __init__(self, *, description: str, classification: FailureType) -> None:
        super().__init__(
            f"Retry aborted for '{description}' due to {classification.value} failure"
        )
        self.description = description
        self.classification = classification


_METRICS = get_metrics()
_TRACER = get_tracer()

_ATTEMPTS_COUNTER = _METRICS.counter(
    "retry_attempts_total",
    "Retry attempts executed",
    labelnames=("component", "policy", "classification", "result"),
)

_OUTCOME_COUNTER = _METRICS.counter(
    "retry_outcomes_total",
    "Retry policy outcomes",
    labelnames=("component", "policy", "outcome"),
)

_DELAY_HISTOGRAM = _METRICS.histogram(
    "retry_delay_ms",
    "Delay applied between retry attempts",
    labelnames=("component", "policy"),
    buckets=(10, 50, 100, 200, 400, 800, 1600, 3200, 6400),
)

_EXECUTION_HISTOGRAM = _METRICS.histogram(
    "retry_execution_ms",
    "Total execution time guarded by the retry policy",
    labelnames=("component", "policy", "outcome"),
    buckets=(
        10,
        50,
        100,
        250,
        500,
        1000,
        2000,
        5000,
        10000,
        20000,
    ),
)


class RetryPolicy:
    """Exponential backoff retry policy compliant with ADR-0008b.

    Parameters
    ----------
    config:
            Policy configuration. Defaults to :class:`RetryPolicyConfig` using
            canonical contract values.
    classifier:
            Failure classifier. If omitted, a classifier will be constructed from the
            provided ``config``.
    random_seed:
            Optional seed for deterministic jitter (useful for tests).
    sleep:
            Awaitable used to suspend between retries. Defaults to ``asyncio.sleep``
            but can be replaced with a deterministic fake in tests (no ``time.sleep``
            allowed per testing guidelines).
    time_source:
            Callable returning monotonic timestamps for latency calculations.
    """

    def __init__(
        self,
        *,
        config: Optional[RetryPolicyConfig] = None,
        classifier: Optional[FailureClassifier] = None,
        random_seed: Optional[int] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config or RetryPolicyConfig()
        self._classifier = classifier or FailureClassifier(config=self._config)
        self._sleep = sleep
        self._time_source = time_source
        self._rng = random.Random(random_seed)

    async def execute(
        self,
        operation: Callable[[], Awaitable[T] | T],
        *,
        idempotent: bool,
        cognitive_trace_id: Optional[str] = None,
        description: str = "operation",
        on_retry: Optional[Callable[[RetryAttemptInfo], Awaitable[None] | None]] = None,
        circuit_breaker: Optional[Any] = None,
    ) -> T:
        """Execute ``operation`` with retry protection.

        Parameters
        ----------
        operation:
                Callable that performs the work. It may be synchronous or async.
        idempotent:
                Indicates whether retrying the operation is safe when classification is
                AMBIGUOUS (ADR-0008b §1.3). Non-idempotent operations abort on
                ambiguous failures.
        cognitive_trace_id:
                Trace identifier to propagate through observability stack.
        description:
                Human-readable description used in logs/metrics.
        on_retry:
                Optional callback invoked before each retry with attempt metadata.
        circuit_breaker:
                Optional circuit breaker instance. If provided and configured to be
                respected, retries will stop when the breaker is OPEN.
        """

        policy_name = self._config.name
        start = self._time_source()
        token: Optional[object] = None

        if cognitive_trace_id:
            token = _TRACER.attach_cognitive_trace(cognitive_trace_id)

        try:
            attempt = 0
            total_delay_ms = 0.0

            while True:
                # Circuit breaker guard (fail-fast) before attempting work.
                if (
                    circuit_breaker is not None
                    and self._config.respect_circuit_breaker
                    and getattr(circuit_breaker, "is_open", False)
                ):
                    self._record_outcome(
                        outcome="circuit_open",
                        policy_name=policy_name,
                        start=start,
                        description=description,
                        trace_id=cognitive_trace_id,
                    )
                    logger.warning(
                        "retry_circuit_breaker_open",
                        policy=policy_name,
                        description=description,
                        trace_id=cognitive_trace_id,
                    )

                    # Fix 5: Invoke circuit breaker fallback if configured
                    fallback = getattr(circuit_breaker, "fallback", None)
                    if fallback is not None and callable(fallback):
                        logger.info(
                            "retry_invoking_circuit_breaker_fallback",
                            policy=policy_name,
                            description=description,
                            trace_id=cognitive_trace_id,
                        )
                        try:
                            fallback_result = await _maybe_await(fallback())
                            return fallback_result  # type: ignore[return-value]
                        except Exception as fallback_err:
                            logger.error(
                                "retry_circuit_breaker_fallback_failed",
                                policy=policy_name,
                                description=description,
                                error=str(fallback_err),
                                trace_id=cognitive_trace_id,
                            )
                            # Fall through to raise RetryAbortedError

                    raise RetryAbortedError(
                        description=description,
                        classification=FailureType.TRANSIENT,
                    )

                try:
                    with _TRACER.span(
                        "k1.resilience.retry.attempt",
                        attributes={
                            "policy": policy_name,
                            "attempt": attempt,
                            "description": description,
                        },
                    ):
                        result = await _maybe_await(operation())
                except BaseException as exc:  # noqa: BLE001 - propagate classification
                    classification = self._classifier.classify(exc)

                    # Record metrics for the failed attempt.
                    _ATTEMPTS_COUNTER.labels(
                        component="k1.resilience",
                        policy=policy_name,
                        classification=classification.value,
                        result="failure",
                    ).inc()

                    outcome = await self._handle_failure(
                        attempt=attempt,
                        classification=classification,
                        exception=exc,
                        total_delay_ms=total_delay_ms,
                        idempotent=idempotent,
                        description=description,
                        policy_name=policy_name,
                        on_retry=on_retry,
                        start=start,
                        cognitive_trace_id=cognitive_trace_id,
                    )

                    if outcome is None:
                        raise  # Permanent or aborted: propagate exception

                    delay_ms = outcome.delay_ms
                    total_delay_ms = outcome.total_elapsed_ms

                    _DELAY_HISTOGRAM.labels(
                        component="k1.resilience", policy=policy_name
                    ).observe(delay_ms)

                    await self._sleep(delay_ms / 1000.0)
                    attempt += 1
                    continue

                # Success path: record metrics and return.
                elapsed_ms = (self._time_source() - start) * 1000.0
                _ATTEMPTS_COUNTER.labels(
                    component="k1.resilience",
                    policy=policy_name,
                    classification="none",
                    result="success",
                ).inc()
                _OUTCOME_COUNTER.labels(
                    component="k1.resilience", policy=policy_name, outcome="success"
                ).inc()
                _EXECUTION_HISTOGRAM.labels(
                    component="k1.resilience", policy=policy_name, outcome="success"
                ).observe(elapsed_ms)

                logger.info(
                    "retry_success",
                    policy=policy_name,
                    description=description,
                    attempts=attempt + 1,
                    elapsed_ms=round(elapsed_ms, 2),
                    trace_id=cognitive_trace_id,
                )
                return result
        finally:
            if token is not None:
                _TRACER.detach(token)

    async def _handle_failure(
        self,
        *,
        attempt: int,
        classification: FailureType,
        exception: BaseException,
        total_delay_ms: float,
        idempotent: bool,
        description: str,
        policy_name: str,
        on_retry: Optional[Callable[[RetryAttemptInfo], Awaitable[None] | None]],
        start: float,
        cognitive_trace_id: Optional[str],
    ) -> Optional[RetryAttemptInfo]:
        """Process a failed attempt and decide whether to retry."""

        config = self._config

        if classification is FailureType.PERMANENT:
            self._record_outcome(
                outcome="permanent_failure",
                policy_name=policy_name,
                start=start,
                description=description,
                trace_id=cognitive_trace_id,
            )
            logger.error(
                "retry_permanent_failure",
                policy=policy_name,
                description=description,
                attempt=attempt,
                error=str(exception),
                trace_id=cognitive_trace_id,
            )
            raise exception

        if classification is FailureType.AMBIGUOUS and not idempotent:
            self._record_outcome(
                outcome="aborted",
                policy_name=policy_name,
                start=start,
                description=description,
                trace_id=cognitive_trace_id,
            )
            raise RetryAbortedError(
                description=description,
                classification=classification,
            ) from exception

        if attempt >= config.max_retries:
            self._record_outcome(
                outcome="attempts_exhausted",
                policy_name=policy_name,
                start=start,
                description=description,
                trace_id=cognitive_trace_id,
            )
            raise RetryAttemptsExceeded(
                description=description,
                attempts=config.max_retries,
            ) from exception

        delay_ms = min(config.base_delay_ms * (2**attempt), config.max_delay_ms)
        jitter_fraction = config.jitter_percent
        if jitter_fraction:
            jitter = self._rng.uniform(-jitter_fraction, jitter_fraction)
            delay_ms *= 1.0 + jitter

        total_elapsed_ms = total_delay_ms + delay_ms

        if total_elapsed_ms > config.retry_budget_ms:
            self._record_outcome(
                outcome="budget_exhausted",
                policy_name=policy_name,
                start=start,
                description=description,
                trace_id=cognitive_trace_id,
            )
            raise RetryBudgetExceeded(
                description=description,
                budget_ms=config.retry_budget_ms,
            ) from exception

        attempt_info = RetryAttemptInfo(
            attempt_number=attempt + 1,
            classification=classification,
            delay_ms=delay_ms,
            total_elapsed_ms=total_elapsed_ms,
            exception=exception,
        )

        logger.warning(
            "retry_scheduling",
            policy=policy_name,
            description=description,
            attempt=attempt + 1,
            classification=classification.value,
            delay_ms=round(delay_ms, 2),
            total_delay_ms=round(total_elapsed_ms, 2),
            trace_id=cognitive_trace_id,
        )

        if on_retry is not None:
            maybe_awaitable = on_retry(attempt_info)
            if inspect.isawaitable(maybe_awaitable):  # pragma: no branch
                await maybe_awaitable  # type: ignore[arg-type]

        return attempt_info

    def _record_outcome(
        self,
        *,
        outcome: str,
        policy_name: str,
        start: float,
        description: str,
        trace_id: Optional[str],
    ) -> None:
        elapsed_ms = (self._time_source() - start) * 1000.0
        _OUTCOME_COUNTER.labels(
            component="k1.resilience", policy=policy_name, outcome=outcome
        ).inc()
        _EXECUTION_HISTOGRAM.labels(
            component="k1.resilience", policy=policy_name, outcome=outcome
        ).observe(elapsed_ms)
        logger.error(
            "retry_outcome",
            policy=policy_name,
            description=description,
            outcome=outcome,
            elapsed_ms=round(elapsed_ms, 2),
            trace_id=trace_id,
        )

    async def execute_idempotent(
        self,
        operation: Callable[[], Awaitable[T] | T],
        *,
        cognitive_trace_id: Optional[str] = None,
        description: str = "operation",
        on_retry: Optional[Callable[[RetryAttemptInfo], Awaitable[None] | None]] = None,
        circuit_breaker: Optional[Any] = None,
    ) -> T:
        """Convenience wrapper for executing idempotent operations with retry protection.

        This is a shorthand for ``execute(..., idempotent=True)`` to simplify
        common read operations, queries, and other safe-to-retry work.

        Parameters
        ----------
        operation:
                Callable that performs the work. It may be synchronous or async.
        cognitive_trace_id:
                Trace identifier to propagate through observability stack.
        description:
                Human-readable description used in logs/metrics.
        on_retry:
                Optional callback invoked before each retry with attempt metadata.
        circuit_breaker:
                Optional circuit breaker instance. If provided and configured to be
                respected, retries will stop when the breaker is OPEN.

        Returns
        -------
        T
                The result of the operation.

        Raises
        ------
        RetryBudgetExceeded
                When the retry budget is exhausted.
        RetryAbortedError
                When the circuit breaker is OPEN (if configured).

        Examples
        --------
        >>> policy = RetryPolicy()
        >>> result = await policy.execute_idempotent(
        ...     lambda: fetch_user_data(user_id),
        ...     description="fetch_user_data",
        ...     cognitive_trace_id=trace_id,
        ... )
        """
        return await self.execute(
            operation,
            idempotent=True,
            cognitive_trace_id=cognitive_trace_id,
            description=description,
            on_retry=on_retry,
            circuit_breaker=circuit_breaker,
        )


async def _maybe_await(value: Awaitable[T] | T) -> T:
    """Await ``value`` if necessary."""

    if inspect.isawaitable(value):
        return await value  # type: ignore[arg-type]
    return value  # type: ignore[return-value]
