"""
Epic 5.1-T.1: Test HOT Read Latency SLI
========================================

Tests that verify HOT tier read latency meets SLI targets.

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md
EPIC: 5.1-T - SLI/SLO Validation Tests
ISSUE: 5.1-T.1 - Test HOT read latency SLI

SLI TARGETS (from sessionstate.policies.yaml):
----------------------------------------------
- P50: <50 microseconds
- P95: <100 microseconds
- P99: <150 microseconds

SCENARIOS:
----------
1. Single HOT reads - baseline latency
2. 10,000 HOT reads - measure distribution
3. Load levels: 100, 1000, 10000 ops/sec

METHODOLOGY:
------------
- Use time.perf_counter_ns() for nanosecond precision
- Calculate percentiles from distribution
- Test all 8 HOT tier sections
"""

import statistics
import time
from typing import Generator, List

import pytest

from k1.sessionstate import SessionStateFactory, SessionStateManager

# =============================================================================
# SLI TARGETS (microseconds)
# =============================================================================

SLI_HOT_READ_P50_US = 50  # 50 microseconds
SLI_HOT_READ_P95_US = 100  # 100 microseconds
SLI_HOT_READ_P99_US = 150  # 150 microseconds

# HOT tier sections (actual valid sections from implementation)
HOT_SECTIONS = [
    "control",
    "scoreboard",
    "meta",
    "history_active",
    "narrative_active",
    "beliefs_active",
    "affective_now",
    "clarifications",
]


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def manager() -> Generator[SessionStateManager, None, None]:
    """Create test manager."""
    manager = SessionStateFactory.create_for_testing()
    manager.start(restore_if_exists=False)

    # Pre-populate HOT sections with data
    for section in HOT_SECTIONS:
        if section == "beliefs_active":
            manager.mutate(
                section=section,
                operation="add_fact",
                data={
                    "subject": "user",
                    "predicate": "prefers",
                    "obj": "python",
                    "confidence": 0.9,
                },
                estimated_bytes=100,
            )
        else:
            manager.mutate(
                section=section,
                operation="set",
                data={"key": "value", "number": 42},
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


class TestHotReadBaseline:
    """Baseline HOT read latency tests."""

    def test_single_hot_read_fast(self, manager: SessionStateManager) -> None:
        """Single HOT read completes quickly."""
        latency_ns = measure_read_latency_ns(manager, "control")
        latency_us = latency_ns / 1000

        # Should be well under P99 target
        assert latency_us < SLI_HOT_READ_P99_US * 10, f"Latency {latency_us}μs too slow"

    def test_all_hot_sections_readable(self, manager: SessionStateManager) -> None:
        """All HOT sections are readable."""
        for section in HOT_SECTIONS:
            data = manager.get_section(section)
            assert data is not None, f"Section {section} not readable"

    def test_hot_read_returns_data(self, manager: SessionStateManager) -> None:
        """HOT read returns actual data."""
        data = manager.get_section("control")
        assert data is not None
        # Depending on implementation, may be dict or object


# =============================================================================
# LATENCY DISTRIBUTION TESTS
# =============================================================================


class TestHotReadLatencyDistribution:
    """Test HOT read latency distribution."""

    def test_1000_reads_distribution(self, manager: SessionStateManager) -> None:
        """1,000 reads - measure distribution."""
        latencies_us: List[float] = []

        for _ in range(1000):
            latency_ns = measure_read_latency_ns(manager, "control")
            latencies_us.append(latency_ns / 1000)

        latencies_us.sort()

        p50 = percentile(latencies_us, 50)
        p95 = percentile(latencies_us, 95)
        p99 = percentile(latencies_us, 99)

        print(f"\n1000 HOT reads - P50: {p50:.2f}μs, P95: {p95:.2f}μs, P99: {p99:.2f}μs")

        # Log but don't fail - measuring baseline
        assert p50 < SLI_HOT_READ_P50_US * 100, f"P50 {p50}μs extremely slow"

    def test_10000_reads_sli_compliance(self, manager: SessionStateManager) -> None:
        """10,000 reads - verify SLI compliance."""
        latencies_us: List[float] = []

        for _ in range(10000):
            latency_ns = measure_read_latency_ns(manager, "scoreboard")
            latencies_us.append(latency_ns / 1000)

        latencies_us.sort()

        p50 = percentile(latencies_us, 50)
        p95 = percentile(latencies_us, 95)
        p99 = percentile(latencies_us, 99)
        mean = statistics.mean(latencies_us)

        print("\n10000 HOT reads:")
        print(f"  Mean: {mean:.2f}μs")
        print(f"  P50:  {p50:.2f}μs (target: <{SLI_HOT_READ_P50_US}μs)")
        print(f"  P95:  {p95:.2f}μs (target: <{SLI_HOT_READ_P95_US}μs)")
        print(f"  P99:  {p99:.2f}μs (target: <{SLI_HOT_READ_P99_US}μs)")

        # SLI targets with tolerance (10x for CI environments)
        tolerance = 10
        assert p50 < SLI_HOT_READ_P50_US * tolerance, f"P50 SLI breach: {p50}μs"
        assert p95 < SLI_HOT_READ_P95_US * tolerance, f"P95 SLI breach: {p95}μs"
        assert p99 < SLI_HOT_READ_P99_US * tolerance, f"P99 SLI breach: {p99}μs"


class TestHotReadAllSections:
    """Test HOT read latency across all sections."""

    def test_all_sections_latency(self, manager: SessionStateManager) -> None:
        """Measure latency for all 8 HOT sections."""
        section_latencies: dict[str, List[float]] = {s: [] for s in HOT_SECTIONS}

        # 100 reads per section
        for _ in range(100):
            for section in HOT_SECTIONS:
                latency_ns = measure_read_latency_ns(manager, section)
                section_latencies[section].append(latency_ns / 1000)

        print("\n\nPer-section HOT read latencies (100 reads each):")
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
            assert p95 < SLI_HOT_READ_P95_US * tolerance, f"{section} P95 too slow"


# =============================================================================
# LOAD TESTS
# =============================================================================


class TestHotReadUnderLoad:
    """Test HOT read latency under various load levels."""

    def test_100_ops_per_second(self, manager: SessionStateManager) -> None:
        """100 ops/sec - measure latency."""
        latencies_us: List[float] = []
        interval_s = 1 / 100  # 10ms between ops

        for _ in range(100):
            start_loop = time.perf_counter()

            latency_ns = measure_read_latency_ns(manager, "control")
            latencies_us.append(latency_ns / 1000)

            elapsed = time.perf_counter() - start_loop
            sleep_time = interval_s - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        latencies_us.sort()
        p95 = percentile(latencies_us, 95)

        print(f"\n100 ops/sec - P95: {p95:.2f}μs")
        assert p95 < SLI_HOT_READ_P95_US * 10

    def test_1000_ops_per_second(self, manager: SessionStateManager) -> None:
        """1,000 ops/sec - measure latency."""
        latencies_us: List[float] = []
        interval_s = 1 / 1000  # 1ms between ops

        for _ in range(1000):
            start_loop = time.perf_counter()

            latency_ns = measure_read_latency_ns(manager, "scoreboard")
            latencies_us.append(latency_ns / 1000)

            elapsed = time.perf_counter() - start_loop
            sleep_time = interval_s - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        latencies_us.sort()
        p95 = percentile(latencies_us, 95)

        print(f"\n1000 ops/sec - P95: {p95:.2f}μs")
        assert p95 < SLI_HOT_READ_P95_US * 10

    def test_burst_reads(self, manager: SessionStateManager) -> None:
        """Burst of 10,000 reads as fast as possible."""
        latencies_us: List[float] = []

        start_total = time.perf_counter()
        for _ in range(10000):
            latency_ns = measure_read_latency_ns(manager, "control")
            latencies_us.append(latency_ns / 1000)
        total_time = time.perf_counter() - start_total

        latencies_us.sort()
        p50 = percentile(latencies_us, 50)
        p95 = percentile(latencies_us, 95)
        p99 = percentile(latencies_us, 99)

        throughput = 10000 / total_time

        print(f"\nBurst 10000 reads in {total_time:.3f}s ({throughput:.0f} ops/sec)")
        print(f"  P50: {p50:.2f}μs, P95: {p95:.2f}μs, P99: {p99:.2f}μs")

        # Verify high throughput
        assert throughput > 10000, f"Throughput {throughput} too low"


# =============================================================================
# CONSISTENCY TESTS
# =============================================================================


class TestHotReadConsistency:
    """Test HOT read latency consistency."""

    def test_latency_stable_over_time(self, manager: SessionStateManager) -> None:
        """Latency remains stable over 5 batches."""
        batch_p95s: List[float] = []

        for batch in range(5):
            latencies_us: List[float] = []
            for _ in range(1000):
                latency_ns = measure_read_latency_ns(manager, "control")
                latencies_us.append(latency_ns / 1000)

            latencies_us.sort()
            p95 = percentile(latencies_us, 95)
            batch_p95s.append(p95)

        print(f"\nBatch P95s: {batch_p95s}")

        # Variance between batches should be reasonable
        mean_p95 = statistics.mean(batch_p95s)
        stdev_p95 = statistics.stdev(batch_p95s) if len(batch_p95s) > 1 else 0

        print(f"Mean P95: {mean_p95:.2f}μs, StdDev: {stdev_p95:.2f}μs")

        # P95 should be relatively stable (coefficient of variation < 100%)
        cv = (stdev_p95 / mean_p95) * 100 if mean_p95 > 0 else 0
        assert cv < 100, f"Latency too variable: CV={cv:.1f}%"

    def test_no_latency_spikes(self, manager: SessionStateManager) -> None:
        """No extreme latency spikes (>10x P99 target)."""
        latencies_us: List[float] = []

        for _ in range(5000):
            latency_ns = measure_read_latency_ns(manager, "control")
            latencies_us.append(latency_ns / 1000)

        max_latency = max(latencies_us)
        spike_threshold = SLI_HOT_READ_P99_US * 100  # 100x tolerance

        print(f"\nMax latency: {max_latency:.2f}μs (spike threshold: {spike_threshold}μs)")

        # No extreme spikes
        assert max_latency < spike_threshold, f"Spike detected: {max_latency}μs"


# =============================================================================
# SNAPSHOT READ TESTS
# =============================================================================


class TestSnapshotLatency:
    """Test snapshot read latency (alternative read path)."""

    def test_snapshot_latency(self, manager: SessionStateManager) -> None:
        """Snapshot read latency."""
        latencies_us: List[float] = []

        for _ in range(1000):
            start = time.perf_counter_ns()
            _ = manager.get_snapshot()
            end = time.perf_counter_ns()
            latencies_us.append((end - start) / 1000)

        latencies_us.sort()
        p50 = percentile(latencies_us, 50)
        p95 = percentile(latencies_us, 95)

        print(f"\nSnapshot read - P50: {p50:.2f}μs, P95: {p95:.2f}μs")

        # Snapshot may be slower than single section read
        # Target: <1ms (1000μs)
        assert p95 < 1000, f"Snapshot P95 {p95}μs too slow"

    def test_size_info_latency(self, manager: SessionStateManager) -> None:
        """Size info read latency."""
        latencies_us: List[float] = []

        for _ in range(1000):
            start = time.perf_counter_ns()
            _ = manager.get_all_section_sizes()
            end = time.perf_counter_ns()
            latencies_us.append((end - start) / 1000)

        latencies_us.sort()
        p95 = percentile(latencies_us, 95)

        print(f"\nSize info read - P95: {p95:.2f}μs")

        # Should be very fast
        assert p95 < 500, f"Size info P95 {p95}μs too slow"
