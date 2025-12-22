"""
Tests for k0/scheduler/scheduler.py

Tests PipelineScheduler class functionality:
- Pipeline registration
- Trigger coordination
- Manual trigger firing
- Start/stop lifecycle
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.runtime.schemas import TriggerSpec, TriggerType
from k0.scheduler.scheduler import PipelineScheduler, PipelineState, ScheduledPipeline
from k0.scheduler.triggers import ManualTriggerEngine, TriggerEvent

# ============================================================
# ScheduledPipeline Tests
# ============================================================


class TestScheduledPipeline:
    """Tests for ScheduledPipeline dataclass."""

    @pytest.fixture
    def mock_spec(self) -> MagicMock:
        """Create a mock pipeline spec."""
        spec = MagicMock()
        spec.pipeline_id = "test_pipeline"
        spec.triggers = []
        return spec

    def test_scheduled_pipeline_creation(self, mock_spec: MagicMock) -> None:
        """Test creating a ScheduledPipeline."""
        scheduled = ScheduledPipeline(
            pipeline_id="test_pipeline",
            spec=mock_spec,
        )

        assert scheduled.pipeline_id == "test_pipeline"
        assert scheduled.spec == mock_spec
        assert scheduled.triggers == []
        assert scheduled.state == PipelineState.REGISTERED
        assert scheduled.execution_count == 0
        assert scheduled.last_execution is None


class TestPipelineState:
    """Tests for PipelineState enum."""

    def test_all_states_exist(self) -> None:
        """Test that all expected states exist."""
        assert PipelineState.REGISTERED.value == "registered"
        assert PipelineState.STARTING.value == "starting"
        assert PipelineState.RUNNING.value == "running"
        assert PipelineState.STOPPING.value == "stopping"
        assert PipelineState.STOPPED.value == "stopped"
        assert PipelineState.ERROR.value == "error"


# ============================================================
# PipelineScheduler Tests
# ============================================================


class TestPipelineScheduler:
    """Tests for PipelineScheduler class."""

    @pytest.fixture
    def mock_syscalls(self) -> MagicMock:
        """Create mock syscalls."""
        syscalls = MagicMock()
        syscalls.query_count = AsyncMock(return_value=0)
        return syscalls

    @pytest.fixture
    def mock_executor(self) -> MagicMock:
        """Create mock pipeline executor."""
        return MagicMock()

    @pytest.fixture
    def mock_pipeline_spec(self) -> MagicMock:
        """Create mock pipeline spec with manual trigger."""
        spec = MagicMock()
        spec.pipeline_id = "test_pipeline"
        spec.triggers = [
            TriggerSpec(
                id="manual_trigger",
                type=TriggerType.MANUAL,
            ),
        ]
        return spec

    @pytest.fixture
    def mock_interval_pipeline_spec(self) -> MagicMock:
        """Create mock pipeline spec with interval trigger."""
        spec = MagicMock()
        spec.pipeline_id = "interval_pipeline"
        spec.triggers = [
            TriggerSpec(
                id="interval_trigger",
                type=TriggerType.INTERVAL,
                interval_seconds=1,  # Short for testing
            ),
        ]
        return spec

    def test_scheduler_creation(self, mock_syscalls: MagicMock) -> None:
        """Test creating a PipelineScheduler."""
        scheduler = PipelineScheduler(mock_syscalls)

        assert scheduler.pipelines == {}
        assert not scheduler.is_running

    def test_register_pipeline(
        self,
        mock_syscalls: MagicMock,
        mock_pipeline_spec: MagicMock,
    ) -> None:
        """Test registering a pipeline."""
        scheduler = PipelineScheduler(mock_syscalls)

        scheduled = scheduler.register_pipeline(mock_pipeline_spec)

        assert scheduled.pipeline_id == "test_pipeline"
        assert scheduled.state == PipelineState.REGISTERED
        assert len(scheduled.triggers) == 1
        assert isinstance(scheduled.triggers[0], ManualTriggerEngine)

        # Verify in registry
        assert "test_pipeline" in scheduler.pipelines

    def test_register_pipeline_duplicate_raises(
        self,
        mock_syscalls: MagicMock,
        mock_pipeline_spec: MagicMock,
    ) -> None:
        """Test that registering duplicate pipeline raises error."""
        scheduler = PipelineScheduler(mock_syscalls)

        scheduler.register_pipeline(mock_pipeline_spec)

        with pytest.raises(ValueError, match="already registered"):
            scheduler.register_pipeline(mock_pipeline_spec)

    def test_unregister_pipeline(
        self,
        mock_syscalls: MagicMock,
        mock_pipeline_spec: MagicMock,
    ) -> None:
        """Test unregistering a pipeline."""
        scheduler = PipelineScheduler(mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)

        result = scheduler.unregister_pipeline("test_pipeline")

        assert result is True
        assert "test_pipeline" not in scheduler.pipelines

    def test_unregister_pipeline_not_found(self, mock_syscalls: MagicMock) -> None:
        """Test unregistering non-existent pipeline returns False."""
        scheduler = PipelineScheduler(mock_syscalls)

        result = scheduler.unregister_pipeline("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_start_stop_scheduler(
        self,
        mock_syscalls: MagicMock,
        mock_pipeline_spec: MagicMock,
    ) -> None:
        """Test starting and stopping scheduler."""
        scheduler = PipelineScheduler(mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)

        await scheduler.start()

        assert scheduler.is_running
        scheduled = scheduler.get_pipeline("test_pipeline")
        assert scheduled is not None
        assert scheduled.state == PipelineState.RUNNING

        await scheduler.stop()

        assert not scheduler.is_running
        assert scheduled.state == PipelineState.STOPPED

    @pytest.mark.asyncio
    async def test_start_twice_ignored(
        self,
        mock_syscalls: MagicMock,
        mock_pipeline_spec: MagicMock,
    ) -> None:
        """Test that starting twice is a no-op."""
        scheduler = PipelineScheduler(mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)

        await scheduler.start()
        await scheduler.start()  # Should be ignored

        assert scheduler.is_running

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_fire_manual_trigger(
        self,
        mock_syscalls: MagicMock,
        mock_executor: MagicMock,
        mock_pipeline_spec: MagicMock,
    ) -> None:
        """Test firing a manual trigger."""
        scheduler = PipelineScheduler(mock_syscalls, mock_executor)
        scheduler.register_pipeline(mock_pipeline_spec)

        await scheduler.start()

        result = scheduler.fire_manual_trigger("test_pipeline", "manual_trigger")

        assert result is True
        mock_executor.assert_called_once()

        # Check executor was called with correct arguments
        call_args = mock_executor.call_args
        scheduled, event = call_args[0]
        assert scheduled.pipeline_id == "test_pipeline"
        assert isinstance(event, TriggerEvent)
        assert event.trigger_id == "manual_trigger"

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_fire_manual_trigger_pipeline_not_found(
        self,
        mock_syscalls: MagicMock,
    ) -> None:
        """Test firing trigger on non-existent pipeline returns False."""
        scheduler = PipelineScheduler(mock_syscalls)

        result = scheduler.fire_manual_trigger("nonexistent", "trigger")

        assert result is False

    @pytest.mark.asyncio
    async def test_fire_manual_trigger_wrong_type(
        self,
        mock_syscalls: MagicMock,
        mock_interval_pipeline_spec: MagicMock,
    ) -> None:
        """Test firing manual trigger on non-manual trigger returns False."""
        scheduler = PipelineScheduler(mock_syscalls)
        scheduler.register_pipeline(mock_interval_pipeline_spec)

        await scheduler.start()

        result = scheduler.fire_manual_trigger("interval_pipeline", "interval_trigger")

        assert result is False

        await scheduler.stop()

    def test_get_pipeline(
        self,
        mock_syscalls: MagicMock,
        mock_pipeline_spec: MagicMock,
    ) -> None:
        """Test getting a pipeline by ID."""
        scheduler = PipelineScheduler(mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)

        scheduled = scheduler.get_pipeline("test_pipeline")

        assert scheduled is not None
        assert scheduled.pipeline_id == "test_pipeline"

    def test_get_pipeline_not_found(self, mock_syscalls: MagicMock) -> None:
        """Test getting non-existent pipeline returns None."""
        scheduler = PipelineScheduler(mock_syscalls)

        scheduled = scheduler.get_pipeline("nonexistent")

        assert scheduled is None

    @pytest.mark.asyncio
    async def test_get_trigger_stats(
        self,
        mock_syscalls: MagicMock,
        mock_pipeline_spec: MagicMock,
    ) -> None:
        """Test getting trigger statistics."""
        scheduler = PipelineScheduler(mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)

        await scheduler.start()

        stats = scheduler.get_trigger_stats()

        assert "manual_trigger" in stats
        trigger_stat = stats["manual_trigger"]
        assert trigger_stat["pipeline_id"] == "test_pipeline"
        assert trigger_stat["type"] == "manual"
        assert trigger_stat["is_running"] is True
        assert trigger_stat["fire_count"] == 0

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_get_trigger_stats_by_pipeline(
        self,
        mock_syscalls: MagicMock,
        mock_pipeline_spec: MagicMock,
        mock_interval_pipeline_spec: MagicMock,
    ) -> None:
        """Test getting trigger stats filtered by pipeline."""
        scheduler = PipelineScheduler(mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)
        scheduler.register_pipeline(mock_interval_pipeline_spec)

        await scheduler.start()

        # Get all stats
        all_stats = scheduler.get_trigger_stats()
        assert len(all_stats) == 2

        # Filter by pipeline
        filtered_stats = scheduler.get_trigger_stats("test_pipeline")
        assert len(filtered_stats) == 1
        assert "manual_trigger" in filtered_stats

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_execution_count_increments(
        self,
        mock_syscalls: MagicMock,
        mock_pipeline_spec: MagicMock,
    ) -> None:
        """Test that execution count increments on trigger fire."""
        scheduler = PipelineScheduler(mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)

        await scheduler.start()

        scheduled = scheduler.get_pipeline("test_pipeline")
        assert scheduled is not None
        assert scheduled.execution_count == 0

        scheduler.fire_manual_trigger("test_pipeline", "manual_trigger")
        assert scheduled.execution_count == 1

        scheduler.fire_manual_trigger("test_pipeline", "manual_trigger")
        assert scheduled.execution_count == 2

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_interval_trigger_fires_automatically(
        self,
        mock_syscalls: MagicMock,
        mock_executor: MagicMock,
        mock_interval_pipeline_spec: MagicMock,
    ) -> None:
        """Test that interval triggers fire automatically."""
        scheduler = PipelineScheduler(mock_syscalls, mock_executor)
        scheduler.register_pipeline(mock_interval_pipeline_spec)

        await scheduler.start()

        # Wait for at least one interval fire
        await asyncio.sleep(1.2)

        await scheduler.stop()

        # Should have been called at least once
        assert mock_executor.call_count >= 1

        scheduled = scheduler.get_pipeline("interval_pipeline")
        assert scheduled is not None
        assert scheduled.execution_count >= 1


# ============================================================
# Integration-style Tests
# ============================================================


class TestSchedulerIntegration:
    """Integration tests for scheduler with multiple pipelines."""

    @pytest.fixture
    def mock_syscalls(self) -> MagicMock:
        """Create mock syscalls."""
        syscalls = MagicMock()
        syscalls.query_count = AsyncMock(return_value=100)  # Above threshold
        return syscalls

    @pytest.fixture
    def threshold_pipeline_spec(self) -> MagicMock:
        """Create mock pipeline spec with threshold trigger."""
        spec = MagicMock()
        spec.pipeline_id = "threshold_pipeline"
        spec.triggers = [
            TriggerSpec(
                id="threshold_trigger",
                type=TriggerType.THRESHOLD,
                table="st_vec",
                condition="status = 'READY'",
                threshold_count=50,
                check_interval_seconds=1,
            ),
        ]
        return spec

    @pytest.mark.asyncio
    async def test_threshold_trigger_fires_on_threshold(
        self,
        mock_syscalls: MagicMock,
        threshold_pipeline_spec: MagicMock,
    ) -> None:
        """Test threshold trigger fires when count exceeds threshold."""
        mock_executor = MagicMock()
        scheduler = PipelineScheduler(mock_syscalls, mock_executor)
        scheduler.register_pipeline(threshold_pipeline_spec)

        await scheduler.start()

        # Wait for threshold check
        await asyncio.sleep(1.2)

        await scheduler.stop()

        # Should have fired (count=100 > threshold=50)
        assert mock_executor.call_count >= 1

        # Verify context contains threshold info
        call_args = mock_executor.call_args
        _, event = call_args[0]
        assert event.context["count"] == 100
        assert event.context["threshold"] == 50

    @pytest.mark.asyncio
    async def test_multiple_pipelines(
        self,
        mock_syscalls: MagicMock,
    ) -> None:
        """Test scheduler with multiple pipelines."""
        spec1 = MagicMock()
        spec1.pipeline_id = "pipeline_1"
        spec1.triggers = [
            TriggerSpec(id="manual_1", type=TriggerType.MANUAL),
        ]

        spec2 = MagicMock()
        spec2.pipeline_id = "pipeline_2"
        spec2.triggers = [
            TriggerSpec(id="manual_2", type=TriggerType.MANUAL),
        ]

        scheduler = PipelineScheduler(mock_syscalls)
        scheduler.register_pipeline(spec1)
        scheduler.register_pipeline(spec2)

        await scheduler.start()

        assert len(scheduler.pipelines) == 2
        assert scheduler.get_pipeline("pipeline_1") is not None
        assert scheduler.get_pipeline("pipeline_2") is not None

        # Fire both
        scheduler.fire_manual_trigger("pipeline_1", "manual_1")
        scheduler.fire_manual_trigger("pipeline_2", "manual_2")

        p1 = scheduler.get_pipeline("pipeline_1")
        p2 = scheduler.get_pipeline("pipeline_2")

        assert p1 is not None and p1.execution_count == 1
        assert p2 is not None and p2.execution_count == 1

        await scheduler.stop()
