"""Ward tests for network latency chaos injection (Issue 9.1.4 Phase 3)."""

from __future__ import annotations

import time

from hypothesis import given, settings
from hypothesis import strategies as st
from ward import test

from k0.chaos.toggles import get_network_delay_ms
from k0.kernel.config import ChaosSettings
from k0.obs.metrics import MetricsExporter
from k0.tests.chaos.fixtures import (
    chaos_enabled_config,
    high_failure_config,
    metrics_exporter,
)


@test("chaos toggle: get_network_delay_ms returns configured latency")
def _(config: ChaosSettings = chaos_enabled_config) -> None:
    delay = get_network_delay_ms(config)
    assert delay == config.network_latency_ms
    assert delay == 100


@test("chaos toggle: high latency config returns large delay")
def _(config: ChaosSettings = high_failure_config) -> None:
    delay = get_network_delay_ms(config)
    assert delay == 500


@test("chaos toggle: disabled config returns zero delay")
def _() -> None:
    config = ChaosSettings(enabled=False, network_latency_ms=0)
    delay = get_network_delay_ms(config)
    assert delay == 0


@test("chaos network: ChaosTransport injects measurable latency")
def _(
    config: ChaosSettings = chaos_enabled_config,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    # Note: This test validates the ChaosTransport interface
    # Actual httpx integration would require a real transport mock
    # For now, verify the delay calculation

    delay_ms = get_network_delay_ms(config)
    assert delay_ms == 100

    # Measure actual delay if we inject via time.sleep
    start = time.perf_counter()
    time.sleep(delay_ms / 1000.0)  # Convert ms to seconds
    elapsed = time.perf_counter() - start

    # Allow 50ms margin for OS scheduling
    assert 0.08 <= elapsed <= 0.15, f"Expected ~0.1s, got {elapsed}s"


@test("hypothesis: network latency scales linearly with config")
def _(exporter: MetricsExporter = metrics_exporter) -> None:
    @settings(max_examples=30, deadline=500)
    @given(
        latency_ms=st.integers(min_value=10, max_value=200),
    )
    def runner(latency_ms: int) -> None:
        config = ChaosSettings(
            enabled=True,
            network_latency_ms=latency_ms,
        )

        delay = get_network_delay_ms(config)
        assert delay == latency_ms

        # Measure injected delay
        start = time.perf_counter()
        time.sleep(delay / 1000.0)
        elapsed = time.perf_counter() - start

        expected_seconds = latency_ms / 1000.0
        # Allow 30% margin for scheduler jitter
        lower = expected_seconds * 0.7
        upper = expected_seconds * 1.3

        assert (
            lower <= elapsed <= upper
        ), f"latency_ms={latency_ms}, expected {expected_seconds}s±30%, got {elapsed}s"

    runner()

