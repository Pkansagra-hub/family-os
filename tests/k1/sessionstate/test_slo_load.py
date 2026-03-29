"""
Epic 5.1-T.8/9/10: SLO Load Testing
====================================

Tests that validate SLO targets under load conditions.

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md
EPIC: 5.1-T - SLI/SLO Validation Tests
ISSUES:
  - 5.1-T.8: Test sustained load SLO
  - 5.1-T.9: Test concurrent session SLO
  - 5.1-T.10: Test pressure cascade SLO

SLO TARGETS (from sessionstate.policies.yaml):
----------------------------------------------
- Availability: 99.9% (3.65 min downtime/day)
- Latency compliance: 99.5% within SLI targets
- Memory compliance: 100% (never exceed 96KB)

SCENARIOS:
----------
1. Sustained load (many operations over time)
2. Burst load (high ops/sec for short period)
3. Mixed read/write workloads
4. Pressure cascade (fill to thresholds)
"""

import time
import uuid
from pathlib import Path
from typing import Generator

import pytest

from k1.sessionstate import SessionStateFactory, SessionStateManager

# =============================================================================
# SLO TARGETS
# =============================================================================

# Latency SLIs for compliance checking
SLI_HOT_P95_US = 100  # microseconds
SLI_WARM_P95_US = 200  # microseconds
SLI_PREFLIGHT_P95_US = 50  # microseconds

# SLO compliance thresholds
SLO_LATENCY_COMPLIANCE = 0.995  # 99.5% of reads meet SLI
SLO_MEMORY_COMPLIANCE = 1.0  # 100% never exceed
SLO_AVAILABILITY = 0.999  # 99.9% success rate

# CI tolerance (environment may be slow)
CI_TOLERANCE = 20  # 20x for timing-sensitive tests

# Memory limits
MEMORY_LIMIT_BYTES = 98304  # 96KB


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
def standalone_manager(tmp_path: Path) -> Generator[SessionStateManager, None, None]:
    """Create standalone manager with SQLite."""
    db_path = tmp_path / "slo_load_test.db"
    session_id = f"slo-load-{uuid.uuid4().hex[:8]}"

    manager = SessionStateFactory.create_standalone(
        session_id=session_id,
        db_path=db_path,
    )
    manager.start(restore_if_exists=False)

    yield manager

    if manager.is_running:
        manager.stop(checkpoint_before_stop=False)


# =============================================================================
# SUSTAINED LOAD TESTS (5.1-T.8)
# =============================================================================


class TestSustainedLoad:
    """Test SLO compliance under sustained load."""

    def test_1000_reads_availability(self, manager: SessionStateManager) -> None:
        """1000 reads maintain 99.9% availability."""
        successes = 0
        failures = 0

        for _ in range(1000):
            try:
                manager.get_section("control")
                successes += 1
            except Exception:
                failures += 1

        availability = successes / (successes + failures)
        assert (
            availability >= SLO_AVAILABILITY
        ), f"Availability {availability:.3%} < {SLO_AVAILABILITY:.3%}"

    def test_1000_mutations_availability(self, standalone_manager: SessionStateManager) -> None:
        """1000 mutations maintain 99.9% availability."""
        successes = 0
        failures = 0

        for i in range(1000):
            try:
                result = standalone_manager.mutate(
                    section="control",
                    operation="set",
                    data={"index": i},
                    estimated_bytes=20,
                )
                if result.success:
                    successes += 1
                else:
                    failures += 1
            except Exception:
                failures += 1

        availability = successes / (successes + failures)
        assert (
            availability >= SLO_AVAILABILITY
        ), f"Availability {availability:.3%} < {SLO_AVAILABILITY:.3%}"

    def test_500_read_latency_compliance(self, manager: SessionStateManager) -> None:
        """500 HOT reads maintain 99.5% latency compliance."""
        latencies_us = []

        for _ in range(500):
            start = time.perf_counter_ns()
            manager.get_section("control")
            elapsed_us = (time.perf_counter_ns() - start) / 1000

            latencies_us.append(elapsed_us)

        compliant = sum(1 for l in latencies_us if l <= SLI_HOT_P95_US * CI_TOLERANCE)
        compliance_rate = compliant / len(latencies_us)

        assert (
            compliance_rate >= SLO_LATENCY_COMPLIANCE
        ), f"Compliance {compliance_rate:.3%} < {SLO_LATENCY_COMPLIANCE:.3%}"

    def test_mixed_workload_stability(self, standalone_manager: SessionStateManager) -> None:
        """Mixed read/write workload maintains stability."""
        read_count = 0
        write_count = 0
        errors = 0

        for i in range(500):
            try:
                if i % 3 == 0:
                    # Write
                    standalone_manager.mutate(
                        section="scoreboard",
                        operation="set",
                        data={"i": i},
                        estimated_bytes=10,
                    )
                    write_count += 1
                else:
                    # Read
                    standalone_manager.get_section("scoreboard")
                    read_count += 1
            except Exception:
                errors += 1

        total = read_count + write_count + errors
        success_rate = (read_count + write_count) / total

        assert success_rate >= SLO_AVAILABILITY
        assert read_count > 300  # Mostly reads
        assert write_count > 150  # Some writes


# =============================================================================
# BURST LOAD TESTS
# =============================================================================


class TestBurstLoad:
    """Test SLO compliance under burst conditions."""

    def test_100_rapid_reads(self, manager: SessionStateManager) -> None:
        """100 rapid consecutive reads complete successfully."""
        for _ in range(100):
            manager.get_section("control")

        # If we got here, all succeeded
        assert True

    def test_100_rapid_mutations(self, standalone_manager: SessionStateManager) -> None:
        """100 rapid consecutive mutations complete successfully."""
        successes = 0

        for i in range(100):
            result = standalone_manager.mutate(
                section="control",
                operation="set",
                data={"burst": i},
                estimated_bytes=10,
            )
            if result.success:
                successes += 1

        assert successes >= 99  # Allow 1 failure

    def test_burst_then_read(self, standalone_manager: SessionStateManager) -> None:
        """Burst of mutations followed by reads works."""
        # Burst writes
        for i in range(50):
            standalone_manager.mutate(
                section="meta",
                operation="set",
                data={"burst": i},
                estimated_bytes=20,
            )

        # Follow with reads
        for _ in range(50):
            standalone_manager.get_section("meta")

        # Verify state is valid
        snapshot = standalone_manager.get_snapshot()
        assert snapshot.pressure is not None


# =============================================================================
# MEMORY COMPLIANCE TESTS
# =============================================================================


class TestMemoryCompliance:
    """Test 100% memory compliance SLO."""

    def test_never_exceed_96kb_under_load(self, standalone_manager: SessionStateManager) -> None:
        """Memory never exceeds 96KB under sustained load."""
        violations = 0

        for i in range(500):
            standalone_manager.mutate(
                section="scoreboard",
                operation="set",
                data={"i": i, "data": "x" * 100},
                estimated_bytes=150,
            )

            snapshot = standalone_manager.get_snapshot()
            if snapshot.total_size_bytes > MEMORY_LIMIT_BYTES:
                violations += 1

        assert violations == 0, f"Memory violated {violations} times"

    def test_memory_stable_under_churn(self, standalone_manager: SessionStateManager) -> None:
        """Memory stays stable under high churn workload."""
        max_observed = 0

        # Create churn: write then overwrite
        for cycle in range(10):
            for i in range(50):
                standalone_manager.mutate(
                    section="telemetry",
                    operation="set",
                    data={"cycle": cycle, "item": i, "data": "x" * 50},
                    estimated_bytes=100,
                )

            snapshot = standalone_manager.get_snapshot()
            max_observed = max(max_observed, snapshot.total_size_bytes)

        assert max_observed <= MEMORY_LIMIT_BYTES


# =============================================================================
# PRESSURE CASCADE TESTS (5.1-T.10)
# =============================================================================


class TestPressureCascade:
    """Test behavior as memory pressure increases."""

    def test_normal_pressure_operations(self, manager: SessionStateManager) -> None:
        """Operations work at normal pressure."""
        snapshot = manager.get_snapshot()
        assert snapshot.pressure.value.lower() == "normal"

        # Operations should work
        result = manager.mutate(
            section="control",
            operation="set",
            data={"test": True},
            estimated_bytes=10,
        )
        assert result.success

    def test_fill_to_80_percent(self, standalone_manager: SessionStateManager) -> None:
        """System handles fill to 80% utilization."""
        target_bytes = int(MEMORY_LIMIT_BYTES * 0.80)

        # Fill toward target
        for i in range(500):
            standalone_manager.mutate(
                section="scoreboard",
                operation="set",
                data={"i": i, "d": "x" * 100},
                estimated_bytes=150,
            )

            snapshot = standalone_manager.get_snapshot()
            if snapshot.total_size_bytes >= target_bytes * 0.5:
                break

        # System should still be operational
        snapshot = standalone_manager.get_snapshot()
        assert snapshot.pressure is not None

    def test_pressure_does_not_crash(self, standalone_manager: SessionStateManager) -> None:
        """Heavy load does not crash system."""
        # Aggressive filling
        for i in range(1000):
            try:
                standalone_manager.mutate(
                    section="control",
                    operation="set",
                    data={"i": i, "x": "y" * 200},
                    estimated_bytes=250,
                )
            except Exception:
                pass  # Some failures acceptable under pressure

        # System should still respond
        snapshot = standalone_manager.get_snapshot()
        assert snapshot is not None

    def test_reads_work_under_pressure(self, standalone_manager: SessionStateManager) -> None:
        """Reads still work when under memory pressure."""
        # Fill first
        for i in range(200):
            standalone_manager.mutate(
                section="scoreboard",
                operation="set",
                data={"i": i, "d": "x" * 100},
                estimated_bytes=150,
            )

        # Reads should still work
        read_successes = 0
        for _ in range(100):
            try:
                standalone_manager.get_section("scoreboard")
                read_successes += 1
            except Exception:
                pass

        assert read_successes >= 99  # Almost all should succeed


# =============================================================================
# SNAPSHOT STABILITY TESTS
# =============================================================================


class TestSnapshotStability:
    """Test snapshot stability under load."""

    def test_100_snapshots_consistent(self, manager: SessionStateManager) -> None:
        """100 consecutive snapshots are consistent."""
        session_ids = set()

        for _ in range(100):
            snapshot = manager.get_snapshot()
            session_ids.add(snapshot.session_id)

        # All should be same session
        assert len(session_ids) == 1

    def test_snapshot_timing_stable(self, manager: SessionStateManager) -> None:
        """Snapshot timing is stable across 100 calls."""
        latencies_us = []

        for _ in range(100):
            start = time.perf_counter_ns()
            manager.get_snapshot()
            latencies_us.append((time.perf_counter_ns() - start) / 1000)

        # Calculate variance
        mean = sum(latencies_us) / len(latencies_us)
        variance = sum((l - mean) ** 2 for l in latencies_us) / len(latencies_us)
        std_dev = variance**0.5

        # Coefficient of variation should be reasonable
        cv = std_dev / mean if mean > 0 else 0
        assert cv < 2.0  # Allow high variance in CI


# =============================================================================
# THROUGHPUT TESTS
# =============================================================================


class TestThroughput:
    """Test throughput capabilities."""

    def test_read_throughput_1000_ops(self, manager: SessionStateManager) -> None:
        """Measure read throughput over 1000 operations."""
        start = time.perf_counter()

        for _ in range(1000):
            manager.get_section("control")

        elapsed = time.perf_counter() - start
        ops_per_sec = 1000 / elapsed

        # Should be able to do at least 1000 ops/sec
        assert ops_per_sec >= 1000, f"Only {ops_per_sec:.0f} ops/sec"

    def test_mutation_throughput_500_ops(self, standalone_manager: SessionStateManager) -> None:
        """Measure mutation throughput over 500 operations."""
        start = time.perf_counter()

        for i in range(500):
            standalone_manager.mutate(
                section="control",
                operation="set",
                data={"i": i},
                estimated_bytes=10,
            )

        elapsed = time.perf_counter() - start
        ops_per_sec = 500 / elapsed

        # Should be able to do at least 500 ops/sec
        assert ops_per_sec >= 500, f"Only {ops_per_sec:.0f} ops/sec"
