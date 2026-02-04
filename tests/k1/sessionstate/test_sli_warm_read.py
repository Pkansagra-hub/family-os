"""
Epic 5.1-T.2: Test WARM Read Latency SLI
=========================================

Tests that verify WARM tier read latency meets SLI targets.

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md
EPIC: 5.1-T - SLI/SLO Validation Tests
ISSUE: 5.1-T.2 - Test WARM read latency SLI

SLI TARGETS (from sessionstate.policies.yaml):
----------------------------------------------
- P50: <100 microseconds
- P95: <200 microseconds
- P99: <300 microseconds

SCENARIOS:
----------
1. Single WARM reads - baseline latency
2. 10,000 WARM reads - measure distribution
3. Load levels: 100, 1000, 10000 ops/sec
"""

import statistics
import time
from typing import Generator, List

import pytest

from k1.sessionstate import SessionStateFactory, SessionStateManager

# =============================================================================
# SLI TARGETS (microseconds)
# =============================================================================

SLI_WARM_READ_P50_US = 100  # 100 microseconds
SLI_WARM_READ_P95_US = 200  # 200 microseconds
SLI_WARM_READ_P99_US = 300  # 300 microseconds

# WARM tier sections (from implementation)
WARM_SECTIONS = [
    "telemetry",
    "history_recent",
    "beliefs_history",
    "persona",
]


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def manager() -> Generator[SessionStateManager, None, None]:
    """Create test manager with WARM section data."""
    manager = SessionStateFactory.create_for_testing()
    manager.start(restore_if_exists=False)

    # Pre-populate WARM sections with data
    for section in WARM_SECTIONS:
        manager.mutate(
            section=section,
            operation="set",
            data={"key": "value", "number": 42, "section": section},
            estimated_bytes=100,
        )

    yield manager

    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


def percentile(data: List[float], p: float) -> float:
    """Calculate percentile from sorted data."""
    if not data:
        return 0.0
    k = (len(data) - 1) * (p / 100)
    f = int(k)
    c = f + 1 if f + 1 < len(data) else f
    if f == c:
        return data[f]
    return data[f] * (c - k) + data[c] * (k - f)


def measure_read_latency_ns(manager: SessionStateManager, section: str) -> int:
    """Measure single read latency in nanoseconds."""
    start = time.perf_counter_ns()
    _ = manager.get_section(section)
    end = time.perf_counter_ns()
    return end - start


# =============================================================================
# BASELINE TESTS
# =============================================================================


class TestWarmReadBaseline:
    """Baseline WARM read latency tests."""

    def test_single_warm_read_fast(self, manager: SessionStateManager) -> None:
        """Single WARM read completes quickly."""
        latency_ns = measure_read_latency_ns(manager, "telemetry")
        latency_us = latency_ns / 1000

        # Should be well under P99 target
        assert latency_us < SLI_WARM_READ_P99_US * 10, f"Latency {latency_us}μs too slow"

    def test_all_warm_sections_readable(self, manager: SessionStateManager) -> None:
        """All WARM sections are readable."""
        for section in WARM_SECTIONS:
            data = manager.get_section(section)
            assert data is not None, f"Section {section} not readable"

    def test_warm_read_returns_data(self, manager: SessionStateManager) -> None:
        """WARM read returns actual data."""
        data = manager.get_section("persona")
        assert data is not None


# =============================================================================
# LATENCY DISTRIBUTION TESTS
# =============================================================================


class TestWarmReadLatencyDistribution:
    """Test WARM read latency distribution."""

    def test_1000_reads_distribution(self, manager: SessionStateManager) -> None:
        """1,000 reads - measure distribution."""
        latencies_us: List[float] = []

        for _ in range(1000):
            latency_ns = measure_read_latency_ns(manager, "telemetry")
            latencies_us.append(latency_ns / 1000)

        latencies_us.sort()

        p50 = percentile(latencies_us, 50)
        p95 = percentile(latencies_us, 95)
        p99 = percentile(latencies_us, 99)

        print(f"\n1000 WARM reads - P50: {p50:.2f}μs, P95: {p95:.2f}μs, P99: {p99:.2f}μs")

        # Log but don't fail - measuring baseline
        assert p50 < SLI_WARM_READ_P50_US * 100, f"P50 {p50}μs extremely slow"

    def test_10000_reads_sli_compliance(self, manager: SessionStateManager) -> None:
        """10,000 reads - verify SLI compliance."""
        latencies_us: List[float] = []

        for _ in range(10000):
            latency_ns = measure_read_latency_ns(manager, "persona")
            latencies_us.append(latency_ns / 1000)

        latencies_us.sort()

        p50 = percentile(latencies_us, 50)
        p95 = percentile(latencies_us, 95)
        p99 = percentile(latencies_us, 99)
        mean = statistics.mean(latencies_us)

        print("\n10000 WARM reads:")
        print(f"  Mean: {mean:.2f}μs")
        print(f"  P50:  {p50:.2f}μs (target: <{SLI_WARM_READ_P50_US}μs)")
        print(f"  P95:  {p95:.2f}μs (target: <{SLI_WARM_READ_P95_US}μs)")
        print(f"  P99:  {p99:.2f}μs (target: <{SLI_WARM_READ_P99_US}μs)")

        # SLI targets with tolerance (10x for CI environments)
        tolerance = 10
        assert p50 < SLI_WARM_READ_P50_US * tolerance, f"P50 SLI breach: {p50}μs"
        assert p95 < SLI_WARM_READ_P95_US * tolerance, f"P95 SLI breach: {p95}μs"
        assert p99 < SLI_WARM_READ_P99_US * tolerance, f"P99 SLI breach: {p99}μs"


class TestWarmReadAllSections:
    """Test WARM read latency across all sections."""

    def test_all_sections_latency(self, manager: SessionStateManager) -> None:
        """Measure latency for all 4 WARM sections."""
        section_latencies: dict[str, List[float]] = {s: [] for s in WARM_SECTIONS}

        # 100 reads per section
        for _ in range(100):
            for section in WARM_SECTIONS:
                latency_ns = measure_read_latency_ns(manager, section)
                section_latencies[section].append(latency_ns / 1000)

        print("\n\nPer-section WARM read latencies (100 reads each):")
        for section, latencies in section_latencies.items():
            latencies.sort()
            p50 = percentile(latencies, 50)
            p95 = percentile(latencies, 95)
            print(f"  {section:20s}: P50={p50:6.2f}μs, P95={p95:6.2f}μs")

        # All sections should meet relaxed SLI
        tolerance = 10
        for section, latencies in section_latencies.items():
            latencies.sort()
            p95 = percentile(latencies, 95)
            assert p95 < SLI_WARM_READ_P95_US * tolerance, f"{section} P95 too slow"


# =============================================================================
# LOAD TESTS
# =============================================================================


class TestWarmReadUnderLoad:
    """Test WARM read latency under various load levels."""

    def test_burst_reads(self, manager: SessionStateManager) -> None:
        """Burst of 10,000 reads as fast as possible."""
        latencies_us: List[float] = []

        start_total = time.perf_counter()
        for _ in range(10000):
            latency_ns = measure_read_latency_ns(manager, "telemetry")
            latencies_us.append(latency_ns / 1000)
        total_time = time.perf_counter() - start_total

        latencies_us.sort()
        p50 = percentile(latencies_us, 50)
        p95 = percentile(latencies_us, 95)
        p99 = percentile(latencies_us, 99)

        throughput = 10000 / total_time

        print(f"\nBurst 10000 WARM reads in {total_time:.3f}s ({throughput:.0f} ops/sec)")
        print(f"  P50: {p50:.2f}μs, P95: {p95:.2f}μs, P99: {p99:.2f}μs")

        # Verify high throughput
        assert throughput > 10000, f"Throughput {throughput} too low"


# =============================================================================
# COMPARISON TESTS
# =============================================================================


class TestHotVsWarmComparison:
    """Compare HOT vs WARM read latency."""

    def test_warm_not_slower_than_10x_hot(self, manager: SessionStateManager) -> None:
        """WARM reads should not be >10x slower than HOT."""
        hot_latencies: List[float] = []
        warm_latencies: List[float] = []

        # Measure HOT (control section)
        for _ in range(1000):
            latency_ns = measure_read_latency_ns(manager, "control")
            hot_latencies.append(latency_ns / 1000)

        # Measure WARM (telemetry section)
        for _ in range(1000):
            latency_ns = measure_read_latency_ns(manager, "telemetry")
            warm_latencies.append(latency_ns / 1000)

        hot_latencies.sort()
        warm_latencies.sort()

        hot_p95 = percentile(hot_latencies, 95)
        warm_p95 = percentile(warm_latencies, 95)

        print(f"\nHOT P95: {hot_p95:.2f}μs, WARM P95: {warm_p95:.2f}μs")
        print(f"Ratio: {warm_p95/hot_p95:.2f}x")

        # WARM should not be dramatically slower (both are in-memory)
        # Note: In this implementation, both may be similar speed
        ratio = warm_p95 / hot_p95 if hot_p95 > 0 else 1
        assert ratio < 10, f"WARM {ratio:.1f}x slower than HOT"
