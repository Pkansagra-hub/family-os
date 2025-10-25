"""Component tests for Layer 5 retry policy (ADR-0008b).

Validates exponential backoff, failure classification, idempotency rules, and
observability integration for the retry policy defined in:
- ADR-0008  – Saga Pattern (forward recovery)
- ADR-0008b – Retry Policy Parameters & Contracts
- ADR-0024  – Performance Budgets (<5ms decision)
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, cast

from prometheus_client import REGISTRY
from ward import fixture, raises, test  # type: ignore[attr-defined]

from k1.l5_infrastructure.resilience.retry_policy import (
    FailureType,
    RetryAbortedError,
    RetryAttemptsExceeded,
    RetryPolicy,
    RetryPolicyConfig,
)


class _FakeClock:
    __slots__ = ("value",)

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def monotonic(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _FakeSleeper:
    __slots__ = ("clock", "calls")

    def __init__(self, clock: _FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, delay_seconds: float) -> None:
        self.calls.append(delay_seconds)
        self.clock.advance(delay_seconds)


@fixture
async def fake_clock() -> AsyncGenerator[_FakeClock, None]:
    yield _FakeClock()


@fixture
async def fake_sleeper(
    clock_dep: Any = fake_clock,
) -> AsyncGenerator[_FakeSleeper, None]:
    clock = cast(_FakeClock, clock_dep)
    yield _FakeSleeper(clock)


@fixture
async def retry_policy(
    clock_dep: Any = fake_clock,
    sleeper_dep: Any = fake_sleeper,
) -> AsyncGenerator[RetryPolicy, None]:
    clock = cast(_FakeClock, clock_dep)
    sleeper = cast(_FakeSleeper, sleeper_dep)
    config = RetryPolicyConfig(
        name="component_test",
        jitter_percent=0.0,
        max_retries=5,
        base_delay_ms=100.0,
        max_delay_ms=1600.0,
    )
    policy = RetryPolicy(
        config=config,
        random_seed=42,
        sleep=sleeper.__call__,
        time_source=clock.monotonic,
    )
    yield policy


async def _get_metric(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(f"k1_intelligence_{name}", labels)
    return float(value or 0.0)


@test("retry policy retries transient failures with exponential backoff")
async def _(
    policy_dep: Any = retry_policy,
    sleeper_dep: Any = fake_sleeper,
) -> None:
    policy = cast(RetryPolicy, policy_dep)
    sleeper = cast(_FakeSleeper, sleeper_dep)

    attempts = 0

    async def transient_operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("service unavailable")
        return "ok"

    before_failures = await _get_metric(
        "retry_attempts_total",
        {
            "policy": "component_test",
            "classification": FailureType.TRANSIENT.value,
            "result": "failure",
        },
    )

    before_success = await _get_metric(
        "retry_outcomes_total",
        {"policy": "component_test", "outcome": "success"},
    )

    result = await policy.execute(
        transient_operation,
        idempotent=True,
        description="transient",
        cognitive_trace_id="trace-transient",
    )

    assert result == "ok"
    assert attempts == 3
    assert sleeper.calls == [0.1, 0.2]

    after_failures = await _get_metric(
        "retry_attempts_total",
        {
            "policy": "component_test",
            "classification": FailureType.TRANSIENT.value,
            "result": "failure",
        },
    )

    after_success = await _get_metric(
        "retry_outcomes_total",
        {"policy": "component_test", "outcome": "success"},
    )

    assert after_failures == before_failures + 2.0
    assert after_success == before_success + 1.0


@test("retry policy aborts ambiguous failure for non-idempotent operation")
async def _(policy_dep: Any = retry_policy) -> None:
    policy = cast(RetryPolicy, policy_dep)

    async def ambiguous_failure() -> None:
        raise RuntimeError("ambiguous")

    before_aborted = await _get_metric(
        "retry_outcomes_total",
        {"policy": "component_test", "outcome": "aborted"},
    )

    with raises(RetryAbortedError) as exc_info:
        await policy.execute(
            ambiguous_failure,
            idempotent=False,
            description="payment-transfer",
        )

    err = exc_info.raised
    assert err.description == "payment-transfer"
    assert err.classification is FailureType.AMBIGUOUS

    after_aborted = await _get_metric(
        "retry_outcomes_total",
        {"policy": "component_test", "outcome": "aborted"},
    )

    assert after_aborted == before_aborted + 1.0


@test("retry policy stops after max retries for repeated transient failures")
async def _(policy_dep: Any = retry_policy) -> None:
    policy = cast(RetryPolicy, policy_dep)

    async def always_timeout() -> None:
        raise TimeoutError("five failures")

    with raises(RetryAttemptsExceeded):
        await policy.execute(
            always_timeout,
            idempotent=True,
            description="timeout-loop",
        )


@test("retry policy respects open circuit breakers")
async def _(policy_dep: Any = retry_policy) -> None:
    policy = cast(RetryPolicy, policy_dep)
    executed = False

    async def never_called() -> None:
        nonlocal executed
        executed = True

    class _Breaker:
        __slots__ = ("is_open",)

        def __init__(self) -> None:
            self.is_open = True

    breaker = _Breaker()

    before_circuit = await _get_metric(
        "retry_outcomes_total",
        {"policy": "component_test", "outcome": "circuit_open"},
    )

    with raises(RetryAbortedError) as exc_info:
        await policy.execute(
            never_called,
            idempotent=True,
            description="circuit-open",
            circuit_breaker=breaker,
        )

    err = exc_info.raised
    assert err.description == "circuit-open"
    assert err.classification is FailureType.TRANSIENT
    assert executed is False

    after_circuit = await _get_metric(
        "retry_outcomes_total",
        {"policy": "component_test", "outcome": "circuit_open"},
    )

    assert after_circuit == before_circuit + 1.0
