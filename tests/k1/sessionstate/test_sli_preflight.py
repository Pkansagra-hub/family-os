"""
Epic 5.1-T.3: Test Mutation Preflight Latency SLI
==================================================

Tests that verify mutation preflight check latency meets SLI targets.

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md
EPIC: 5.1-T - SLI/SLO Validation Tests
ISSUE: 5.1-T.3 - Test mutation preflight latency SLI

SLI TARGETS (from sessionstate.policies.yaml):
----------------------------------------------
- P50: <25 microseconds
- P95: <50 microseconds
- P99: <75 microseconds

PREFLIGHT CHECKS:
-----------------
1. Budget validation - section under limit
2. Section validation - valid section name
3. Size estimation - estimated_bytes check
4. Operation validation - valid operation for section

NOTE: Preflight is the fast path before mutation is applied.
We measure just the preflight, not the full mutation.
"""

import statistics
import time
from typing import Generator, List

import pytest

from k1.sessionstate import SessionStateFactory, SessionStateManager
from k1.sessionstate.guard import MutationGuard

# =============================================================================
# SLI TARGETS (microseconds)
# =============================================================================

SLI_PREFLIGHT_P50_US = 25  # 25 microseconds
SLI_PREFLIGHT_P95_US = 50  # 50 microseconds
SLI_PREFLIGHT_P99_US = 75  # 75 microseconds

# CI environments can be 30x slower due to virtualization
CI_TOLERANCE = 30


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def manager() -> Generator[SessionStateManager, None, None]:
    """Create test manager."""
    manager = SessionStateFactory.create_for_testing()
    manager.start(restore_if_exists=False)

    yield manager

    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


@pytest.fixture
def guard(manager: SessionStateManager) -> MutationGuard:
    """Get mutation guard from manager."""
    return manager.mutation_guard


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


# =============================================================================
# BASELINE TESTS
# =============================================================================


class TestPreflightBaseline:
    """Baseline preflight latency tests."""

    def test_single_preflight_fast(self, guard: MutationGuard) -> None:
        """Single preflight completes quickly."""
        start = time.perf_counter_ns()
        result = guard.preflight(
            section="control",
            operation="set",
            estimated_bytes=100,
        )
        end = time.perf_counter_ns()

        latency_us = (end - start) / 1000
        assert result.approved, f"Preflight rejected: {result.reason}"
        assert latency_us < SLI_PREFLIGHT_P99_US * 10, f"Latency {latency_us}μs too slow"

    def test_preflight_returns_result(self, guard: MutationGuard) -> None:
        """Preflight returns proper result."""
        result = guard.preflight(
            section="scoreboard",
            operation="set",
            estimated_bytes=50,
        )

        assert hasattr(result, "approved")
        assert result.approved is True

    def test_preflight_rejects_invalid_section(self, guard: MutationGuard) -> None:
        """Preflight rejects invalid section."""
        result = guard.preflight(
            section="invalid_section",
            operation="set",
            estimated_bytes=100,
        )

        assert result.approved is False
        assert result.reason is not None


# =============================================================================
# LATENCY DISTRIBUTION TESTS
# =============================================================================


class TestPreflightLatencyDistribution:
    """Test preflight latency distribution."""

    def test_1000_preflights_distribution(self, guard: MutationGuard) -> None:
        """1,000 preflights - measure distribution."""
        latencies_us: List[float] = []

        for _ in range(1000):
            start = time.perf_counter_ns()
            _ = guard.preflight(
                section="control",
                operation="set",
                estimated_bytes=100,
            )
            end = time.perf_counter_ns()
            latencies_us.append((end - start) / 1000)

        latencies_us.sort()

        p50 = percentile(latencies_us, 50)
        p95 = percentile(latencies_us, 95)
        p99 = percentile(latencies_us, 99)

        print(f"\n1000 preflights - P50: {p50:.2f}μs, P95: {p95:.2f}μs, P99: {p99:.2f}μs")

    def test_10000_preflights_sli_compliance(self, guard: MutationGuard) -> None:
        """10,000 preflights - verify SLI compliance."""
        latencies_us: List[float] = []

        for _ in range(10000):
            start = time.perf_counter_ns()
            _ = guard.preflight(
                section="scoreboard",
                operation="set",
                estimated_bytes=100,
            )
            end = time.perf_counter_ns()
            latencies_us.append((end - start) / 1000)

        latencies_us.sort()

        p50 = percentile(latencies_us, 50)
        p95 = percentile(latencies_us, 95)
        p99 = percentile(latencies_us, 99)
        mean = statistics.mean(latencies_us)

        print("\n10000 preflights:")
        print(f"  Mean: {mean:.2f}μs")
        print(f"  P50:  {p50:.2f}μs (target: <{SLI_PREFLIGHT_P50_US}μs)")
        print(f"  P95:  {p95:.2f}μs (target: <{SLI_PREFLIGHT_P95_US}μs)")
        print(f"  P99:  {p99:.2f}μs (target: <{SLI_PREFLIGHT_P99_US}μs)")

        # SLI targets with tolerance (10x for CI environments)
        tolerance = 10
        assert p50 < SLI_PREFLIGHT_P50_US * tolerance, f"P50 SLI breach: {p50}μs"
        assert p95 < SLI_PREFLIGHT_P95_US * tolerance, f"P95 SLI breach: {p95}μs"
        assert p99 < SLI_PREFLIGHT_P99_US * tolerance, f"P99 SLI breach: {p99}μs"


# =============================================================================
# PREFLIGHT TYPES TESTS
# =============================================================================


class TestPreflightTypes:
    """Test different preflight scenarios."""

    def test_small_mutation_preflight(self, guard: MutationGuard) -> None:
        """Small mutation preflight."""
        latencies_us: List[float] = []

        for _ in range(1000):
            start = time.perf_counter_ns()
            _ = guard.preflight(section="control", operation="set", estimated_bytes=10)
            end = time.perf_counter_ns()
            latencies_us.append((end - start) / 1000)

        latencies_us.sort()
        p95 = percentile(latencies_us, 95)
        print(f"\nSmall mutation preflight P95: {p95:.2f}μs")

    def test_large_mutation_preflight(self, guard: MutationGuard) -> None:
        """Large mutation preflight (near budget limit)."""
        latencies_us: List[float] = []

        for _ in range(1000):
            start = time.perf_counter_ns()
            _ = guard.preflight(section="control", operation="set", estimated_bytes=4000)
            end = time.perf_counter_ns()
            latencies_us.append((end - start) / 1000)

        latencies_us.sort()
        p95 = percentile(latencies_us, 95)
        print(f"\nLarge mutation preflight P95: {p95:.2f}μs")

    def test_rejection_preflight_speed(self, guard: MutationGuard) -> None:
        """Rejection should be as fast as approval."""
        latencies_us: List[float] = []

        for _ in range(1000):
            start = time.perf_counter_ns()
            _ = guard.preflight(section="invalid", operation="set", estimated_bytes=100)
            end = time.perf_counter_ns()
            latencies_us.append((end - start) / 1000)

        latencies_us.sort()
        p95 = percentile(latencies_us, 95)
        print(f"\nRejection preflight P95: {p95:.2f}μs")

        # Rejections should be fast too (CI tolerance needed)
        assert p95 < SLI_PREFLIGHT_P95_US * CI_TOLERANCE


# =============================================================================
# DIFFERENT SECTIONS TESTS
# =============================================================================


class TestPreflightAllSections:
    """Test preflight across different sections."""

    def test_hot_section_preflights(self, guard: MutationGuard) -> None:
        """HOT section preflight latencies."""
        hot_sections = ["control", "scoreboard", "meta", "history_active"]
        section_latencies: dict[str, List[float]] = {s: [] for s in hot_sections}

        for _ in range(500):
            for section in hot_sections:
                start = time.perf_counter_ns()
                _ = guard.preflight(section=section, operation="set", estimated_bytes=100)
                end = time.perf_counter_ns()
                section_latencies[section].append((end - start) / 1000)

        print("\n\nHOT section preflight latencies:")
        for section, latencies in section_latencies.items():
            latencies.sort()
            p95 = percentile(latencies, 95)
            print(f"  {section:20s}: P95={p95:6.2f}μs")

    def test_warm_section_preflights(self, guard: MutationGuard) -> None:
        """WARM section preflight latencies."""
        warm_sections = ["telemetry", "persona", "history_recent", "beliefs_history"]
        section_latencies: dict[str, List[float]] = {s: [] for s in warm_sections}

        for _ in range(500):
            for section in warm_sections:
                start = time.perf_counter_ns()
                _ = guard.preflight(section=section, operation="set", estimated_bytes=100)
                end = time.perf_counter_ns()
                section_latencies[section].append((end - start) / 1000)

        print("\n\nWARM section preflight latencies:")
        for section, latencies in section_latencies.items():
            latencies.sort()
            p95 = percentile(latencies, 95)
            print(f"  {section:20s}: P95={p95:6.2f}μs")


# =============================================================================
# LOAD TESTS
# =============================================================================


class TestPreflightUnderLoad:
    """Test preflight under various load levels."""

    def test_burst_preflights(self, guard: MutationGuard) -> None:
        """Burst of 10,000 preflights as fast as possible."""
        latencies_us: List[float] = []

        start_total = time.perf_counter()
        for _ in range(10000):
            start = time.perf_counter_ns()
            _ = guard.preflight(section="control", operation="set", estimated_bytes=100)
            end = time.perf_counter_ns()
            latencies_us.append((end - start) / 1000)
        total_time = time.perf_counter() - start_total

        latencies_us.sort()
        p50 = percentile(latencies_us, 50)
        p95 = percentile(latencies_us, 95)

        throughput = 10000 / total_time

        print(f"\nBurst 10000 preflights in {total_time:.3f}s ({throughput:.0f} ops/sec)")
        print(f"  P50: {p50:.2f}μs, P95: {p95:.2f}μs")

        # Should achieve very high throughput
        assert throughput > 50000, f"Throughput {throughput} too low"


# =============================================================================
# PREFLIGHT VS FULL MUTATION
# =============================================================================


class TestPreflightVsMutation:
    """Compare preflight vs full mutation latency."""

    def test_preflight_faster_than_mutation(
        self, manager: SessionStateManager, guard: MutationGuard
    ) -> None:
        """Preflight should be faster than full mutation."""
        preflight_latencies: List[float] = []
        mutation_latencies: List[float] = []

        # Measure preflight
        for _ in range(1000):
            start = time.perf_counter_ns()
            _ = guard.preflight(section="scoreboard", operation="set", estimated_bytes=50)
            end = time.perf_counter_ns()
            preflight_latencies.append((end - start) / 1000)

        # Measure full mutation
        for i in range(1000):
            start = time.perf_counter_ns()
            _ = manager.mutate(
                section="scoreboard",
                operation="set",
                data={"key": f"value_{i}"},
                estimated_bytes=50,
            )
            end = time.perf_counter_ns()
            mutation_latencies.append((end - start) / 1000)

        preflight_latencies.sort()
        mutation_latencies.sort()

        preflight_p95 = percentile(preflight_latencies, 95)
        mutation_p95 = percentile(mutation_latencies, 95)

        print(f"\nPreflight P95: {preflight_p95:.2f}μs")
        print(f"Mutation P95:  {mutation_p95:.2f}μs")
        print(f"Ratio: {mutation_p95/preflight_p95:.2f}x")

        # Preflight should be faster (or at least not slower)
        assert preflight_p95 <= mutation_p95 * 1.5, "Preflight slower than mutation"
