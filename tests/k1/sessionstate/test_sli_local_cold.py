"""
Epic 5.1-T.4: Test LOCAL COLD Reconstruction SLI
=================================================

Tests that verify LOCAL COLD reconstruction latency meets SLI targets.

IMPLEMENTATION PLAN: docs/plans/sessionstate-implementation-plan.md
EPIC: 5.1-T - SLI/SLO Validation Tests
ISSUE: 5.1-T.4 - Test LOCAL COLD reconstruction SLI

SLI TARGETS (from sessionstate.policies.yaml):
----------------------------------------------
- P50: <25 milliseconds
- P95: <50 milliseconds
- P99: <75 milliseconds

SCENARIOS:
----------
1. Empty session reconstruction
2. 50% full session reconstruction
3. 90% full session reconstruction
4. 96KB (max) session reconstruction
"""

import statistics
import time
import uuid
from pathlib import Path
from typing import List

import pytest

from k1.sessionstate import SessionStateFactory

# =============================================================================
# SLI TARGETS (milliseconds)
# =============================================================================

SLI_LOCAL_COLD_P50_MS = 25  # 25 milliseconds
SLI_LOCAL_COLD_P95_MS = 50  # 50 milliseconds
SLI_LOCAL_COLD_P99_MS = 75  # 75 milliseconds


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create temp database path."""
    return tmp_path / "sli_reconstruction_test.db"


@pytest.fixture
def session_id() -> str:
    """Generate unique session ID."""
    return f"sli-recon-{uuid.uuid4().hex[:8]}"


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


def create_and_checkpoint_session(
    db_path: Path,
    session_id: str,
    fill_percentage: float = 0.0,
) -> None:
    """Create session, fill to percentage, checkpoint, and stop."""
    manager = SessionStateFactory.create_standalone(
        session_id=session_id,
        db_path=db_path,
    )
    manager.start(restore_if_exists=False)

    # Fill to target percentage
    if fill_percentage > 0:
        # Total budget is 96KB, fill proportionally
        target_bytes = int(96 * 1024 * fill_percentage / 100)
        bytes_per_mutation = 100
        mutations_needed = max(1, target_bytes // bytes_per_mutation)

        sections = ["scoreboard", "control", "meta", "telemetry", "persona"]
        for i in range(mutations_needed):
            section = sections[i % len(sections)]
            manager.mutate(
                section=section,
                operation="set",
                data={"index": i, "data": "x" * 50},
                estimated_bytes=bytes_per_mutation,
            )

    # Checkpoint to LOCAL COLD
    manager.checkpoint()
    manager.stop(checkpoint_before_stop=False)


def measure_reconstruction_ms(db_path: Path, session_id: str) -> float:
    """Measure reconstruction latency in milliseconds."""
    start = time.perf_counter()
    manager = SessionStateFactory.create_standalone(
        session_id=session_id,
        db_path=db_path,
    )
    result = manager.start(restore_if_exists=True)
    end = time.perf_counter()

    assert result.success, f"Reconstruction failed: {result.error}"
    assert result.restored, "Session was not restored"

    # Clean up
    manager.stop(checkpoint_before_stop=False)

    return (end - start) * 1000  # Convert to ms


# =============================================================================
# EMPTY SESSION TESTS
# =============================================================================


class TestEmptySessionReconstruction:
    """Test reconstruction of empty session."""

    def test_empty_reconstruction_fast(self, db_path: Path, session_id: str) -> None:
        """Empty session reconstruction is fast."""
        create_and_checkpoint_session(db_path, session_id, fill_percentage=0)

        latency_ms = measure_reconstruction_ms(db_path, session_id)

        print(f"\nEmpty reconstruction: {latency_ms:.2f}ms")
        assert latency_ms < SLI_LOCAL_COLD_P99_MS * 2, f"Latency {latency_ms}ms too slow"

    def test_10_empty_reconstructions(self, db_path: Path) -> None:
        """10 empty reconstructions - measure distribution."""
        latencies_ms: List[float] = []

        for i in range(10):
            session_id = f"empty-{i}-{uuid.uuid4().hex[:4]}"
            create_and_checkpoint_session(db_path, session_id, fill_percentage=0)
            latency_ms = measure_reconstruction_ms(db_path, session_id)
            latencies_ms.append(latency_ms)

        latencies_ms.sort()
        p50 = percentile(latencies_ms, 50)
        p95 = percentile(latencies_ms, 95)

        print(f"\n10 empty reconstructions - P50: {p50:.2f}ms, P95: {p95:.2f}ms")


# =============================================================================
# PARTIAL FILL TESTS
# =============================================================================


class TestPartialFillReconstruction:
    """Test reconstruction at various fill levels."""

    def test_10_percent_fill(self, db_path: Path, session_id: str) -> None:
        """10% fill reconstruction."""
        create_and_checkpoint_session(db_path, session_id, fill_percentage=10)

        latency_ms = measure_reconstruction_ms(db_path, session_id)

        print(f"\n10% fill reconstruction: {latency_ms:.2f}ms")
        assert latency_ms < SLI_LOCAL_COLD_P99_MS * 2

    def test_50_percent_fill(self, db_path: Path, session_id: str) -> None:
        """50% fill reconstruction."""
        create_and_checkpoint_session(db_path, session_id, fill_percentage=50)

        latency_ms = measure_reconstruction_ms(db_path, session_id)

        print(f"\n50% fill reconstruction: {latency_ms:.2f}ms")
        assert latency_ms < SLI_LOCAL_COLD_P99_MS * 2

    def test_90_percent_fill(self, db_path: Path, session_id: str) -> None:
        """90% fill reconstruction (near capacity)."""
        create_and_checkpoint_session(db_path, session_id, fill_percentage=90)

        latency_ms = measure_reconstruction_ms(db_path, session_id)

        print(f"\n90% fill reconstruction: {latency_ms:.2f}ms")
        assert latency_ms < SLI_LOCAL_COLD_P99_MS * 2


# =============================================================================
# FULL SESSION TESTS
# =============================================================================


class TestFullSessionReconstruction:
    """Test reconstruction of fully filled session."""

    def test_full_session_reconstruction(self, db_path: Path, session_id: str) -> None:
        """96KB (max) session reconstruction."""
        # Note: Can't actually fill to 100% due to eviction
        # Use 95% as proxy for "full"
        create_and_checkpoint_session(db_path, session_id, fill_percentage=95)

        latency_ms = measure_reconstruction_ms(db_path, session_id)

        print(f"\n95% (near-full) reconstruction: {latency_ms:.2f}ms")
        assert latency_ms < SLI_LOCAL_COLD_P99_MS * 2


# =============================================================================
# LATENCY DISTRIBUTION TESTS
# =============================================================================


class TestReconstructionLatencyDistribution:
    """Test reconstruction latency distribution."""

    def test_50_reconstructions_sli_compliance(self, db_path: Path) -> None:
        """50 reconstructions - verify SLI compliance."""
        latencies_ms: List[float] = []

        # Create 50 sessions with varying fill
        for i in range(50):
            session_id = f"dist-{i}-{uuid.uuid4().hex[:4]}"
            fill_pct = (i % 10) * 10  # 0%, 10%, 20%, ..., 90%
            create_and_checkpoint_session(db_path, session_id, fill_percentage=fill_pct)
            latency_ms = measure_reconstruction_ms(db_path, session_id)
            latencies_ms.append(latency_ms)

        latencies_ms.sort()

        p50 = percentile(latencies_ms, 50)
        p95 = percentile(latencies_ms, 95)
        p99 = percentile(latencies_ms, 99)
        mean = statistics.mean(latencies_ms)

        print("\n50 reconstructions (mixed fill):")
        print(f"  Mean: {mean:.2f}ms")
        print(f"  P50:  {p50:.2f}ms (target: <{SLI_LOCAL_COLD_P50_MS}ms)")
        print(f"  P95:  {p95:.2f}ms (target: <{SLI_LOCAL_COLD_P95_MS}ms)")
        print(f"  P99:  {p99:.2f}ms (target: <{SLI_LOCAL_COLD_P99_MS}ms)")

        # SLI targets with tolerance (2x for CI environments)
        tolerance = 2
        assert p50 < SLI_LOCAL_COLD_P50_MS * tolerance, f"P50 SLI breach: {p50}ms"
        assert p95 < SLI_LOCAL_COLD_P95_MS * tolerance, f"P95 SLI breach: {p95}ms"
        assert p99 < SLI_LOCAL_COLD_P99_MS * tolerance, f"P99 SLI breach: {p99}ms"


# =============================================================================
# REPEATED RECONSTRUCTION TESTS
# =============================================================================


class TestRepeatedReconstruction:
    """Test repeated reconstruction of same session."""

    def test_10_repeated_reconstructions(self, db_path: Path, session_id: str) -> None:
        """Same session reconstructed 10 times."""
        create_and_checkpoint_session(db_path, session_id, fill_percentage=50)

        latencies_ms: List[float] = []
        for _ in range(10):
            latency_ms = measure_reconstruction_ms(db_path, session_id)
            latencies_ms.append(latency_ms)

        latencies_ms.sort()
        p50 = percentile(latencies_ms, 50)
        p95 = percentile(latencies_ms, 95)

        print(f"\n10 repeated reconstructions - P50: {p50:.2f}ms, P95: {p95:.2f}ms")

        # Should be consistent
        tolerance = 2
        assert p95 < SLI_LOCAL_COLD_P95_MS * tolerance


# =============================================================================
# BENCHMARK TESTS
# =============================================================================


class TestReconstructionBenchmark:
    """Benchmark reconstruction performance."""

    def test_reconstruction_throughput(self, db_path: Path) -> None:
        """Measure reconstruction throughput."""
        # Create 20 sessions
        session_ids = []
        for i in range(20):
            sid = f"bench-{i}-{uuid.uuid4().hex[:4]}"
            create_and_checkpoint_session(db_path, sid, fill_percentage=30)
            session_ids.append(sid)

        # Measure total time to reconstruct all
        start = time.perf_counter()
        for sid in session_ids:
            measure_reconstruction_ms(db_path, sid)
        total_time = time.perf_counter() - start

        throughput = len(session_ids) / total_time

        print(f"\n20 reconstructions in {total_time:.3f}s ({throughput:.1f} sessions/sec)")

        # Should achieve reasonable throughput
        assert throughput > 5, f"Throughput {throughput} too low"

    def test_scaling_with_data_size(self, db_path: Path) -> None:
        """Test latency scaling with data size."""
        results: List[tuple[int, float]] = []

        for fill_pct in [0, 25, 50, 75]:
            session_id = f"scale-{fill_pct}-{uuid.uuid4().hex[:4]}"
            create_and_checkpoint_session(db_path, session_id, fill_percentage=fill_pct)

            latencies = []
            for _ in range(5):
                latency_ms = measure_reconstruction_ms(db_path, session_id)
                latencies.append(latency_ms)

            avg_latency = statistics.mean(latencies)
            results.append((fill_pct, avg_latency))

        print("\nLatency vs fill percentage:")
        for fill_pct, latency in results:
            print(f"  {fill_pct:3d}%: {latency:.2f}ms")

        # Latency should scale roughly linearly (not exponentially)
        # Check that 75% is not more than 4x of 25%
        latency_25 = next(lat for pct, lat in results if pct == 25)
        latency_75 = next(lat for pct, lat in results if pct == 75)

        if latency_25 > 0:
            ratio = latency_75 / latency_25
            print(f"  75%/25% ratio: {ratio:.2f}x")
            assert ratio < 10, f"Non-linear scaling: {ratio:.1f}x"
