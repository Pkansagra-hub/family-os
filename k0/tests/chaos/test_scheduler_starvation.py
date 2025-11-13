"""Ward tests for scheduler capacity chaos injection (Issue 9.1.4 Phase 3)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from ward import raises, test

from k0.chaos.toggles import apply_scheduler_starvation
from k0.kernel.config import ChaosSettings
from k0.obs.metrics import MetricsExporter
from k0.qos.scheduler import Scheduler, SchedulerCapacityError, SchedulerProfile
from k0.tests.chaos.fixtures import (
    base_scheduler_profile,
    chaos_enabled_config,
    high_failure_config,
    metric_value,
    metrics_exporter,
)


@test("chaos toggle: apply_scheduler_starvation reduces port limits")
def _(
    profile: SchedulerProfile = base_scheduler_profile,
    config: ChaosSettings = chaos_enabled_config,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    starved = apply_scheduler_starvation(profile, config, exporter)

    # multiplier=0.3 means 30% capacity
    assert starved.port_limits["command"] == int(10 * 0.3)  # 3
    assert starved.port_limits["query"] == int(5 * 0.3)  # 1
    assert starved.port_limits["sse"] == max(1, int(3 * 0.3))  # 0 rounds to minimum 1

    # Telemetry emitted
    throttled = metric_value(exporter, "k0_kernel_scheduler_throttled_multiplier")
    assert throttled == 0.3


@test("scheduler: reduced capacity causes early SchedulerCapacityError")
def _(
    profile: SchedulerProfile = base_scheduler_profile,
    config: ChaosSettings = chaos_enabled_config,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    starved_profile = apply_scheduler_starvation(profile, config, exporter)
    scheduler = Scheduler(starved_profile)

    # Original limit: 10, starved: 3
    tokens = []
    for i in range(3):
        token = scheduler.acquire(band="GREEN", port="command", cost=1)
        tokens.append(token)

    # 4th acquisition should fail
    with raises(SchedulerCapacityError):
        scheduler.acquire(band="GREEN", port="command", cost=1)

    # Release tokens
    for token in tokens:
        token.release()


@test("scheduler: chaos disabled maintains full capacity")
def _(
    profile: SchedulerProfile = base_scheduler_profile,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    config = ChaosSettings(enabled=False)
    normal_profile = apply_scheduler_starvation(profile, config, exporter)

    # Should return original profile unchanged
    assert normal_profile.port_limits["command"] == 10
    assert normal_profile.port_limits["query"] == 5


@test("scheduler: high starvation allows only minimal capacity")
def _(
    profile: SchedulerProfile = base_scheduler_profile,
    config: ChaosSettings = high_failure_config,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    # multiplier=0.1 means 10% capacity
    starved = apply_scheduler_starvation(profile, config, exporter)

    assert starved.port_limits["command"] == 1  # 10 * 0.1 = 1
    assert starved.port_limits["query"] == 1  # 5 * 0.1 = 0.5 → min 1
    assert starved.port_limits["sse"] == 1  # 3 * 0.1 = 0.3 → min 1


@test("scheduler: queue recovery after token release")
def _(
    profile: SchedulerProfile = base_scheduler_profile,
    config: ChaosSettings = chaos_enabled_config,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    starved_profile = apply_scheduler_starvation(profile, config, exporter)
    scheduler = Scheduler(starved_profile)

    # Fill capacity (3 tokens)
    tokens = [scheduler.acquire(band="GREEN", port="command", cost=1) for _ in range(3)]

    # Verify capacity exhausted
    with raises(SchedulerCapacityError):
        scheduler.acquire(band="GREEN", port="command", cost=1)

    # Release first token
    tokens[0].release()

    # Should now be able to acquire again
    new_token = scheduler.acquire(band="GREEN", port="command", cost=1)
    new_token.release()

    # Cleanup
    for token in tokens[1:]:
        token.release()


@test("scheduler: telemetry reflects throttled state")
def _(
    profile: SchedulerProfile = base_scheduler_profile,
    config: ChaosSettings = chaos_enabled_config,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    apply_scheduler_starvation(profile, config, exporter)

    throttled = metric_value(exporter, "k0_kernel_scheduler_throttled_multiplier")
    assert throttled == config.scheduler_starvation_multiplier


@test("hypothesis: scheduler respects varied starvation multipliers")
def _(
    profile: SchedulerProfile = base_scheduler_profile,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    @settings(max_examples=40, deadline=300)
    @given(
        multiplier=st.floats(min_value=0.1, max_value=1.0),
        acquisitions=st.integers(min_value=1, max_value=15),
    )
    def runner(multiplier: float, acquisitions: int) -> None:
        config = ChaosSettings(
            enabled=True,
            scheduler_starvation_multiplier=multiplier,
        )

        starved_profile = apply_scheduler_starvation(profile, config, exporter)
        scheduler = Scheduler(starved_profile)

        expected_limit = max(1, int(10 * multiplier))
        tokens = []

        for i in range(min(acquisitions, expected_limit)):
            token = scheduler.acquire(band="GREEN", port="command", cost=1)
            tokens.append(token)

        # Verify capacity exhausted
        if acquisitions > expected_limit:
            with raises(SchedulerCapacityError):
                scheduler.acquire(band="GREEN", port="command", cost=1)

        # Cleanup
        for token in tokens:
            token.release()

        assert scheduler.active_tokens("command") == 0

    runner()

