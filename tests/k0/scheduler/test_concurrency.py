"""
Tests for SingleFlightGate concurrency controls.

Tests Issue 3.3.1: Single-Flight Pipeline Gate
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from k0.scheduler.concurrency import (
    OverlapPolicy,
    PendingRun,
    RunStats,
    SingleFlightGate,
    get_single_flight_gate,
    reset_single_flight_gate,
)


@pytest.fixture
def gate() -> SingleFlightGate:
    """Create a fresh SingleFlightGate for testing."""
    return SingleFlightGate()


class TestSingleFlightGate:
    """Tests for SingleFlightGate class."""

    @pytest.mark.asyncio
    async def test_try_acquire_succeeds_when_not_running(self, gate: SingleFlightGate) -> None:
        """Test that acquire succeeds when pipeline is not running."""
        result = await gate.try_acquire("P03", "trigger-1", "interval")
        assert result is True

    @pytest.mark.asyncio
    async def test_try_acquire_skip_interval_when_running(self, gate: SingleFlightGate) -> None:
        """Test that interval triggers are skipped when pipeline is running."""
        # First acquire
        await gate.try_acquire("P03", "trigger-1", "interval")
        gate.mark_running("P03", asyncio.create_task(asyncio.sleep(10)))

        # Second acquire should be skipped
        result = await gate.try_acquire("P03", "trigger-2", "interval")
        assert result is False

        # Check stats
        stats = gate.get_stats("P03")
        assert stats is not None
        assert stats.total_skipped == 1

    @pytest.mark.asyncio
    async def test_try_acquire_queue_threshold_when_running(self, gate: SingleFlightGate) -> None:
        """Test that threshold triggers are queued when pipeline is running."""
        # First acquire
        await gate.try_acquire("P03", "trigger-1", "threshold")
        gate.mark_running("P03", asyncio.create_task(asyncio.sleep(10)))

        # Second acquire should be queued
        result = await gate.try_acquire("P03", "trigger-2", "threshold")
        assert result is False

        # Check stats
        stats = gate.get_stats("P03")
        assert stats is not None
        assert stats.total_queued == 1

    @pytest.mark.asyncio
    async def test_try_acquire_queue_manual_when_running(self, gate: SingleFlightGate) -> None:
        """Test that manual triggers are queued when pipeline is running."""
        # First acquire
        await gate.try_acquire("P03", "trigger-1", "manual")
        gate.mark_running("P03", asyncio.create_task(asyncio.sleep(10)))

        # Second acquire should be queued
        result = await gate.try_acquire("P03", "trigger-2", "manual")
        assert result is False

        # Check stats
        stats = gate.get_stats("P03")
        assert stats is not None
        assert stats.total_queued == 1

    @pytest.mark.asyncio
    async def test_coalesce_replaces_pending(self, gate: SingleFlightGate) -> None:
        """Test that queued triggers are coalesced (max 1)."""
        # First acquire and mark running
        await gate.try_acquire("P03", "trigger-1", "threshold")
        gate.mark_running("P03", asyncio.create_task(asyncio.sleep(10)))

        # Queue first pending
        await gate.try_acquire("P03", "trigger-2", "threshold")

        # Queue second pending - should replace first
        await gate.try_acquire("P03", "trigger-3", "threshold")

        # Release and check pending
        pending = await gate.release("P03")
        assert pending is not None
        assert pending.trigger_id == "trigger-3"  # Latest trigger wins

    @pytest.mark.asyncio
    async def test_release_returns_pending(self, gate: SingleFlightGate) -> None:
        """Test that release returns the pending run."""
        # Acquire and mark running
        await gate.try_acquire("P03", "trigger-1", "threshold")
        gate.mark_running("P03", asyncio.create_task(asyncio.sleep(10)))

        # Queue a pending run
        await gate.try_acquire("P03", "trigger-2", "threshold")

        # Release should return pending
        pending = await gate.release("P03")
        assert pending is not None
        assert pending.trigger_id == "trigger-2"
        assert pending.trigger_type == "threshold"

    @pytest.mark.asyncio
    async def test_release_clears_running(self, gate: SingleFlightGate) -> None:
        """Test that release clears the running state."""
        # Acquire and mark running
        await gate.try_acquire("P03", "trigger-1", "interval")
        gate.mark_running("P03", asyncio.create_task(asyncio.sleep(10)))
        assert gate.is_running("P03") is True

        # Release
        await gate.release("P03")
        assert gate.is_running("P03") is False

    @pytest.mark.asyncio
    async def test_release_no_pending_returns_none(self, gate: SingleFlightGate) -> None:
        """Test that release returns None when no pending run."""
        # Acquire and mark running
        await gate.try_acquire("P03", "trigger-1", "interval")
        gate.mark_running("P03", asyncio.create_task(asyncio.sleep(10)))

        # Release without pending
        pending = await gate.release("P03")
        assert pending is None

    @pytest.mark.asyncio
    async def test_stats_tracks_runs_and_skips(self, gate: SingleFlightGate) -> None:
        """Test that stats correctly track runs and skips."""
        # Run once
        await gate.try_acquire("P03", "trigger-1", "interval")
        gate.mark_running("P03", asyncio.create_task(asyncio.sleep(0.01)))

        # Try to run again (skip)
        await gate.try_acquire("P03", "trigger-2", "interval")

        stats = gate.get_stats("P03")
        assert stats is not None
        assert stats.total_runs == 1
        assert stats.total_skipped == 1
        assert stats.last_run_at is not None
        assert stats.last_skip_at is not None

    @pytest.mark.asyncio
    async def test_multiple_pipelines_independent(self, gate: SingleFlightGate) -> None:
        """Test that different pipelines are tracked independently."""
        # Acquire P03
        await gate.try_acquire("P03", "trigger-1", "interval")
        gate.mark_running("P03", asyncio.create_task(asyncio.sleep(10)))

        # P08 should still be acquirable
        result = await gate.try_acquire("P08", "trigger-1", "interval")
        assert result is True

    def test_get_all_stats(self, gate: SingleFlightGate) -> None:
        """Test getting all pipeline stats."""
        # Add some stats
        gate._stats["P03"] = RunStats(total_runs=5)
        gate._stats["P08"] = RunStats(total_runs=3)

        all_stats = gate.get_all_stats()
        assert len(all_stats) == 2
        assert "P03" in all_stats
        assert "P08" in all_stats


class TestOverlapPolicy:
    """Tests for OverlapPolicy enum."""

    def test_skip_value(self) -> None:
        """Test SKIP policy value."""
        assert OverlapPolicy.SKIP.value == "skip"

    def test_queue_value(self) -> None:
        """Test QUEUE policy value."""
        assert OverlapPolicy.QUEUE.value == "queue"


class TestPendingRun:
    """Tests for PendingRun dataclass."""

    def test_pending_run_creation(self) -> None:
        """Test creating a PendingRun."""
        pending = PendingRun(trigger_id="test-trigger", trigger_type="threshold")
        assert pending.trigger_id == "test-trigger"
        assert pending.trigger_type == "threshold"
        assert pending.queued_at is not None

    def test_pending_run_has_timestamp(self) -> None:
        """Test that PendingRun has a timestamp."""
        before = datetime.now(timezone.utc)
        pending = PendingRun(trigger_id="test", trigger_type="manual")
        after = datetime.now(timezone.utc)

        assert before <= pending.queued_at <= after


class TestRunStats:
    """Tests for RunStats dataclass."""

    def test_run_stats_defaults(self) -> None:
        """Test RunStats default values."""
        stats = RunStats()
        assert stats.total_runs == 0
        assert stats.total_skipped == 0
        assert stats.total_queued == 0
        assert stats.last_run_at is None
        assert stats.last_skip_at is None


class TestGlobalGate:
    """Tests for global gate singleton."""

    def test_get_single_flight_gate_creates_singleton(self) -> None:
        """Test that get_single_flight_gate returns singleton."""
        reset_single_flight_gate()
        gate1 = get_single_flight_gate()
        gate2 = get_single_flight_gate()
        assert gate1 is gate2

    def test_reset_single_flight_gate_clears_singleton(self) -> None:
        """Test that reset clears the singleton."""
        gate1 = get_single_flight_gate()
        reset_single_flight_gate()
        gate2 = get_single_flight_gate()
        assert gate1 is not gate2
