"""Component tests for Layer 5 circuit breaker (ADR-0009 series).

Validates the finite state machine, fail-fast behaviour, fallback handling, and
observability integration defined in:
- ADR-0009  – Circuit Breaker Pattern
- ADR-0009a – Circuit Breaker FSM Implementation
- ADR-0009c – Circuit Breaker Metrics & Observability
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, cast

from prometheus_client import REGISTRY
from ward import fixture, raises, test  # type: ignore[attr-defined]

from k1.l5_infrastructure.observability import get_tracer
from k1.l5_infrastructure.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    FailureClassification,
)


class _FakeClock:
    __slots__ = ("value",)

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def monotonic(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@fixture
async def fake_clock_fixture() -> AsyncGenerator[_FakeClock, None]:
    yield _FakeClock()


@fixture
async def circuit_breaker_fixture(
    fake_clock_dep: Any = fake_clock_fixture,
) -> AsyncGenerator[CircuitBreaker, None]:
    fake_clock = cast(_FakeClock, fake_clock_dep)
    config = CircuitBreakerConfig(
        service="resilience_test",
        failure_threshold=3,
        time_window_ms=60000,
        timeout_duration_ms=30000,
        success_threshold=1,
        slow_call_threshold_ms=200,
    )
    yield CircuitBreaker(config, monotonic=fake_clock.monotonic)


async def _failure_operation() -> None:
    raise TimeoutError("service unavailable")


@test("circuit breaker transitions CLOSED → OPEN after failures within window")
async def _(breaker: Any = circuit_breaker_fixture) -> None:
    circuit_breaker = cast(CircuitBreaker, breaker)
    for _ in range(3):
        with raises(TimeoutError):
            await circuit_breaker.call(_failure_operation)

    assert circuit_breaker.state is CircuitState.OPEN
    assert circuit_breaker.failure_count == 0  # cleared on OPEN transition


@test("open circuit rejects calls and raises CircuitBreakerOpenError without fallback")
async def _(
    breaker: Any = circuit_breaker_fixture, fake_clock: Any = fake_clock_fixture
) -> None:
    circuit_breaker = cast(CircuitBreaker, breaker)
    fake_clock_inst = cast(_FakeClock, fake_clock)
    for _ in range(3):
        with raises(TimeoutError):
            await circuit_breaker.call(_failure_operation)

    rejection_metric = (
        REGISTRY.get_sample_value(
            "k1_intelligence_circuit_breaker_calls_total",
            {
                "component": "k1.resilience",
                "service": "resilience_test",
                "alternate_service": "",
                "result": "rejected",
            },
        )
        or 0.0
    )

    with raises(CircuitBreakerOpenError) as exc_info:
        await circuit_breaker.call(lambda: None)

    err = exc_info.raised
    assert err.retry_after_ms >= 0.0
    assert "Circuit breaker" in str(err)

    updated = (
        REGISTRY.get_sample_value(
            "k1_intelligence_circuit_breaker_calls_total",
            {
                "component": "k1.resilience",
                "service": "resilience_test",
                "alternate_service": "",
                "result": "rejected",
            },
        )
        or 0.0
    )
    assert updated == rejection_metric + 1.0

    fake_clock_inst.advance(31.0)  # allow transition to HALF_OPEN
    result = await circuit_breaker.call(lambda: "probe-success")
    assert result == "probe-success"
    assert circuit_breaker.state is CircuitState.CLOSED


@test("half-open state allows a single probe and rejects concurrent requests")
async def _(
    breaker: Any = circuit_breaker_fixture, fake_clock: Any = fake_clock_fixture
) -> None:
    """Test that only one probe executes in HALF_OPEN, second is rejected (Fix validation)."""
    circuit_breaker = cast(CircuitBreaker, breaker)
    clock = cast(_FakeClock, fake_clock)

    for _ in range(3):
        with raises(TimeoutError):
            await circuit_breaker.call(_failure_operation)

    clock.advance(30.1)

    ready = asyncio.Event()
    proceed = asyncio.Event()

    async def probe() -> str:
        ready.set()
        await proceed.wait()
        return "ok"

    async def second() -> None:
        await ready.wait()
        with raises(CircuitBreakerOpenError) as exc_info:
            await circuit_breaker.call(lambda: "second")

        # Verify rejection reason is half_open_probe_in_flight
        err = exc_info.raised
        assert (
            "half_open_probe_in_flight" in err.reason or "probe" in err.reason.lower()
        ), f"Expected half_open probe rejection, got: {err.reason}"

    first_task = asyncio.create_task(circuit_breaker.call(probe))
    second_task = asyncio.create_task(second())

    await ready.wait()
    proceed.set()

    result = await first_task
    await second_task

    assert result == "ok"
    assert circuit_breaker.state is CircuitState.CLOSED


@test("slow successful calls are classified as failures")
async def _(
    breaker: Any = circuit_breaker_fixture, fake_clock: Any = fake_clock_fixture
) -> None:
    circuit_breaker = cast(CircuitBreaker, breaker)
    clock = cast(_FakeClock, fake_clock)

    async def slow_success() -> str:
        clock.advance(0.25)
        return "slow"

    await circuit_breaker.call(slow_success)
    failure_total = REGISTRY.get_sample_value(
        "k1_intelligence_circuit_breaker_failures_total",
        {
            "component": "k1.resilience",
            "service": "resilience_test",
            "alternate_service": "",
            "failure_type": FailureClassification.SLOW_CALL.value,
        },
    )
    assert failure_total and failure_total >= 1.0


@test("cognitive trace IDs propagate through circuit breaker execution")
async def _(
    breaker: Any = circuit_breaker_fixture, fake_clock: Any = fake_clock_fixture
) -> None:
    circuit_breaker = cast(CircuitBreaker, breaker)
    clock = cast(_FakeClock, fake_clock)
    tracer = get_tracer()
    observed: list[str | None] = []

    async def traced_operation() -> str:
        observed.append(tracer.current_cognitive_trace_id())
        clock.advance(0.01)
        return "observed"

    result = await circuit_breaker.call(
        traced_operation,
        cognitive_trace_id="trace-abc123",
    )

    assert result == "observed"
    assert observed == ["trace-abc123"]
    assert tracer.current_cognitive_trace_id() is None
