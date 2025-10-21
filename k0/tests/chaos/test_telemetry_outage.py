"""Ward tests for telemetry outage chaos injection (Issue 9.1.4 Phase 3)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from ward import test

from k0.chaos.toggles import should_drop_telemetry
from k0.kernel.config import ChaosSettings
from k0.obs.metrics import MetricsExporter
from tests.chaos.fixtures import (
    chaos_enabled_config,
    high_failure_config,
    metric_value,
    metrics_exporter,
)


@test("chaos toggle: should_drop_telemetry returns probabilistic decisions")
def _(config: ChaosSettings = chaos_enabled_config) -> None:
    decisions = [should_drop_telemetry(config) for _ in range(1000)]

    drop_count = sum(1 for drop in decisions if drop)
    # outage_rate=0.05 means 5% drops, expect 30-70 drops out of 1000
    assert 30 <= drop_count <= 70, f"Expected ~50 drops, got {drop_count}"


@test("chaos toggle: high outage rate produces frequent drops")
def _(config: ChaosSettings = high_failure_config) -> None:
    decisions = [should_drop_telemetry(config) for _ in range(200)]

    drop_count = sum(1 for drop in decisions if drop)
    # outage_rate=0.5 means 50% drops, expect 80-120 drops out of 200
    assert 80 <= drop_count <= 120, f"Expected ~100 drops, got {drop_count}"


@test("chaos toggle: disabled config never drops telemetry")
def _() -> None:
    config = ChaosSettings(enabled=False, telemetry_outage_rate=0.0)
    decisions = [should_drop_telemetry(config) for _ in range(100)]

    drop_count = sum(1 for drop in decisions if drop)
    assert drop_count == 0, "Expected zero drops with chaos disabled"


@test("telemetry: partial metric emission with outage simulation")
def _(
    config: ChaosSettings = chaos_enabled_config,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    # Simulate metric emission with chaos drops
    counter = exporter.counter(
        "test_chaos_telemetry_counter",
        "Test counter for chaos validation",
    )

    emitted = 0
    dropped = 0

    for _ in range(500):
        if should_drop_telemetry(config):
            dropped += 1
        else:
            counter.inc()
            emitted += 1

    # Verify some metrics captured (not 100% drop)
    current_value = metric_value(
        exporter, "k0_kernel_test_chaos_telemetry_counter_total"
    )
    assert current_value is not None
    assert current_value == emitted
    assert emitted > 0, "Expected at least some metrics emitted"

    # With outage_rate=0.05, expect ~25 drops out of 500
    assert 10 <= dropped <= 50, f"Expected ~25 drops, got {dropped}"


@test("hypothesis: telemetry drops occur at configured probability")
def _() -> None:
    @settings(max_examples=40, deadline=300)
    @given(
        outage_rate=st.floats(min_value=0.0, max_value=1.0),
        seed=st.integers(min_value=1, max_value=999999),
    )
    def runner(outage_rate: float, seed: int) -> None:
        config = ChaosSettings(
            enabled=True,
            telemetry_outage_rate=outage_rate,
            random_seed=seed,
        )

        decisions = [should_drop_telemetry(config) for _ in range(200)]
        drop_count = sum(1 for drop in decisions if drop)

        # Allow 20% margin for randomness
        expected = outage_rate * 200
        lower = max(0, expected - 40)
        upper = min(200, expected + 40)

        assert (
            lower <= drop_count <= upper
        ), f"outage_rate={outage_rate}, expected {expected}±40, got {drop_count}"

    runner()
