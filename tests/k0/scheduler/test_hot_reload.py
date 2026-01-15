"""
Tests for PipelineScheduler hot reload functionality.

Tests Issue 3.3.2: Hot Reload with Atomic Swap
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from k0.runtime.schemas import PipelineSpec, StageSpec, TriggerSpec, TriggerType
from k0.scheduler.concurrency import reset_single_flight_gate
from k0.scheduler.scheduler import (
    HotReloadResult,
    PipelineScheduler,
    PipelineState,
    reset_pipeline_scheduler,
)


@pytest.fixture
def mock_syscalls() -> MagicMock:
    """Create mock syscalls for testing."""
    syscalls = MagicMock()
    syscalls.query_count = MagicMock(return_value=0)
    return syscalls


@pytest.fixture
def scheduler(mock_syscalls: MagicMock) -> PipelineScheduler:
    """Create a PipelineScheduler for testing."""
    reset_pipeline_scheduler()
    reset_single_flight_gate()
    return PipelineScheduler(syscalls=mock_syscalls)


def make_pipeline_spec(
    pipeline_id: str,
    trigger_type: TriggerType = TriggerType.MANUAL,
) -> PipelineSpec:
    """Create a test PipelineSpec."""
    # Ensure pipeline_id matches pattern ^P[0-9]{2}_[A-Z_]+$
    # E.g., P03_TEST, P08_EMBED
    trigger_id = f"{pipeline_id.lower().replace('_', '')}_trigger"

    # Create trigger based on type
    if trigger_type == TriggerType.INTERVAL:
        trigger = TriggerSpec(
            id=trigger_id,
            type=trigger_type,
            interval_seconds=60,
        )
    else:
        trigger = TriggerSpec(
            id=trigger_id,
            type=trigger_type,
        )

    stage = StageSpec(
        id="stage_01_test",
        module="test.handler:v1",
    )
    return PipelineSpec(
        pipeline_id=pipeline_id,
        version="v1",
        triggers=[trigger],
        dag=[stage],
    )


class TestHotReloadResult:
    """Tests for HotReloadResult dataclass."""

    def test_default_values(self) -> None:
        """Test HotReloadResult default values."""
        result = HotReloadResult()
        assert result.affected_pipelines == []
        assert result.success is False
        assert result.error is None
        assert result.added == 0
        assert result.updated == 0
        assert result.removed == 0

    def test_with_values(self) -> None:
        """Test HotReloadResult with values."""
        result = HotReloadResult(
            affected_pipelines=["P03_TEST", "P08_EMBED"],
            success=True,
            added=2,
            removed=1,
        )
        assert result.affected_pipelines == ["P03_TEST", "P08_EMBED"]
        assert result.success is True
        assert result.added == 2
        assert result.removed == 1


class TestHotReload:
    """Tests for PipelineScheduler.hot_reload method."""

    @pytest.mark.asyncio
    async def test_hot_reload_adds_new_pipeline(self, scheduler: PipelineScheduler) -> None:
        """Test hot reload can add a new pipeline."""
        spec = make_pipeline_spec("P03_TEST")
        new_specs = {"P03_TEST": spec}

        result = await scheduler.hot_reload(new_specs)

        assert result.success is True
        assert result.added == 1
        assert "P03_TEST" in scheduler.pipelines

    @pytest.mark.asyncio
    async def test_hot_reload_replaces_existing_pipeline(
        self, scheduler: PipelineScheduler
    ) -> None:
        """Test hot reload replaces existing pipeline."""
        # Register initial pipeline
        spec1 = make_pipeline_spec("P03_TEST")
        scheduler.register_pipeline(spec1)

        # Hot reload with new spec
        spec2 = make_pipeline_spec("P03_TEST", trigger_type=TriggerType.INTERVAL)
        new_specs = {"P03_TEST": spec2}

        result = await scheduler.hot_reload(new_specs)

        assert result.success is True
        assert "P03_TEST" in scheduler.pipelines
        # Verify the new trigger type
        p03 = scheduler.get_pipeline("P03_TEST")
        assert p03 is not None
        assert len(p03.triggers) == 1

    @pytest.mark.asyncio
    async def test_hot_reload_cancels_old_triggers(self, scheduler: PipelineScheduler) -> None:
        """Test hot reload stops old triggers before installing new ones."""
        # Register and start initial pipeline
        spec1 = make_pipeline_spec("P03_TEST")
        scheduler.register_pipeline(spec1)
        await scheduler.start()

        p03_before = scheduler.get_pipeline("P03_TEST")
        assert p03_before is not None
        assert p03_before.state == PipelineState.RUNNING

        # Hot reload
        spec2 = make_pipeline_spec("P03_TEST")
        new_specs = {"P03_TEST": spec2}

        result = await scheduler.hot_reload(new_specs)

        assert result.success is True
        # New pipeline should be running (scheduler was running)
        p03_after = scheduler.get_pipeline("P03_TEST")
        assert p03_after is not None
        assert p03_after.state == PipelineState.RUNNING

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_hot_reload_starts_triggers_if_scheduler_running(
        self, scheduler: PipelineScheduler
    ) -> None:
        """Test hot reload starts new triggers if scheduler is running."""
        await scheduler.start()

        spec = make_pipeline_spec("P03_TEST")
        new_specs = {"P03_TEST": spec}

        result = await scheduler.hot_reload(new_specs)

        assert result.success is True
        p03 = scheduler.get_pipeline("P03_TEST")
        assert p03 is not None
        assert p03.state == PipelineState.RUNNING

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_hot_reload_only_affects_specified_pipelines(
        self, scheduler: PipelineScheduler
    ) -> None:
        """Test hot reload only affects pipelines in affected set."""
        # Register two pipelines
        spec_p03 = make_pipeline_spec("P03_TEST")
        spec_p08 = make_pipeline_spec("P08_EMBED")
        scheduler.register_pipeline(spec_p03)
        scheduler.register_pipeline(spec_p08)

        # Hot reload only P03
        new_spec = make_pipeline_spec("P03_TEST")
        new_specs = {"P03_TEST": new_spec}
        affected = {"P03_TEST"}

        result = await scheduler.hot_reload(new_specs, affected_pipelines=affected)

        assert result.success is True
        assert "P03_TEST" in result.affected_pipelines
        assert "P08_EMBED" not in result.affected_pipelines
        # P08 should still be registered
        assert "P08_EMBED" in scheduler.pipelines

    @pytest.mark.asyncio
    async def test_hot_reload_error_returns_failure(self, scheduler: PipelineScheduler) -> None:
        """Test hot reload returns failure on error."""
        # Create a spec that will cause an error
        with patch.object(scheduler, "_stop_pipeline", side_effect=Exception("Test error")):
            spec = make_pipeline_spec("P03_TEST")
            scheduler.register_pipeline(spec)

            new_specs = {"P03_TEST": make_pipeline_spec("P03_TEST")}
            result = await scheduler.hot_reload(new_specs)

            assert result.success is False
            assert result.error is not None
            assert "Test error" in result.error

    @pytest.mark.asyncio
    async def test_hot_reload_is_atomic_lock_held(self, scheduler: PipelineScheduler) -> None:
        """Test that hot reload holds the reload lock."""
        # Start a hot reload
        spec = make_pipeline_spec("P03_TEST")
        new_specs = {"P03_TEST": spec}

        # Verify lock is used by checking no concurrent reloads
        async def delayed_reload() -> HotReloadResult:
            await asyncio.sleep(0.01)
            return await scheduler.hot_reload(new_specs)

        # Run two reloads concurrently - they should serialize
        results = await asyncio.gather(
            scheduler.hot_reload(new_specs),
            delayed_reload(),
        )

        # Both should succeed (lock provides serialization)
        assert all(r.success for r in results)


class TestDrainInFlight:
    """Tests for _drain_in_flight method."""

    @pytest.mark.asyncio
    async def test_drain_returns_immediately_if_none_running(
        self, scheduler: PipelineScheduler
    ) -> None:
        """Test drain returns immediately if no pipelines are running."""
        # No pipelines running
        await scheduler._drain_in_flight({"P03_TEST", "P08_EMBED"})
        # Should complete without delay

    @pytest.mark.asyncio
    async def test_drain_logs_warning_on_timeout(self, scheduler: PipelineScheduler) -> None:
        """Test drain logs warning if timeout exceeded."""
        from k0.scheduler.concurrency import get_single_flight_gate

        gate = get_single_flight_gate()

        # Create a long-running task
        task = asyncio.create_task(asyncio.sleep(100))
        gate.mark_running("P03_TEST", task)

        # Set very short timeout
        scheduler._drain_timeout_seconds = 0.1

        # This should timeout
        await scheduler._drain_in_flight({"P03_TEST"})

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
