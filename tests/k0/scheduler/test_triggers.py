"""
Tests for k0/scheduler/triggers.py

Tests TriggerEngine base class and concrete implementations:
- IntervalTriggerEngine
- ThresholdTriggerEngine
- ManualTriggerEngine
- create_trigger_engine factory
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.runtime.schemas import TriggerSpec, TriggerType
from k0.scheduler.triggers import (
    CronTriggerEngine,
    IntervalTriggerEngine,
    ManualTriggerEngine,
    ThresholdTriggerEngine,
    TriggerEvent,
    create_trigger_engine,
)

# ============================================================
# TriggerEvent Tests
# ============================================================


class TestTriggerEvent:
    """Tests for TriggerEvent dataclass."""

    def test_trigger_event_creation(self) -> None:
        """Test creating a trigger event."""
        event = TriggerEvent(
            trigger_id="test_trigger",
            pipeline_id="test_pipeline",
            fired_at=100.0,
            context={"count": 50},
        )

        assert event.trigger_id == "test_trigger"
        assert event.pipeline_id == "test_pipeline"
        assert event.fired_at == 100.0
        assert event.context == {"count": 50}

    def test_trigger_event_default_context(self) -> None:
        """Test trigger event with default empty context."""
        event = TriggerEvent(
            trigger_id="test",
            pipeline_id="test",
            fired_at=0.0,
        )

        assert event.context == {}

    def test_trigger_event_is_frozen(self) -> None:
        """Test that trigger event is immutable."""
        event = TriggerEvent(
            trigger_id="test",
            pipeline_id="test",
            fired_at=0.0,
        )

        with pytest.raises(AttributeError):
            event.trigger_id = "new-id"  # type: ignore


# ============================================================
# IntervalTriggerEngine Tests
# ============================================================


class TestIntervalTriggerEngine:
    """Tests for IntervalTriggerEngine."""

    @pytest.fixture
    def interval_spec(self) -> TriggerSpec:
        """Create an interval trigger spec with short interval for testing."""
        return TriggerSpec(
            id="test_interval",
            type=TriggerType.INTERVAL,
            interval_seconds=1,  # Minimum 1 second (integer required)
        )

    def test_interval_engine_creation(self, interval_spec: TriggerSpec) -> None:
        """Test creating an interval trigger engine."""
        engine = IntervalTriggerEngine(interval_spec, "test_pipeline")

        assert engine.spec == interval_spec
        assert engine.pipeline_id == "test_pipeline"
        assert not engine.is_running
        assert engine.fire_count == 0
        assert engine.last_fired is None

    @pytest.mark.asyncio
    async def test_interval_engine_start_stop(self, interval_spec: TriggerSpec) -> None:
        """Test starting and stopping interval engine."""
        engine = IntervalTriggerEngine(interval_spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)
        assert engine.is_running

        await engine.stop()
        assert not engine.is_running

    @pytest.mark.asyncio
    async def test_interval_engine_fires_callback(self, interval_spec: TriggerSpec) -> None:
        """Test that interval engine fires callback after interval."""
        engine = IntervalTriggerEngine(interval_spec, "test_pipeline")
        events: list[TriggerEvent] = []

        def callback(event: TriggerEvent) -> None:
            events.append(event)

        await engine.start(callback)

        # Wait for at least one fire (interval is 1 second)
        await asyncio.sleep(1.2)

        await engine.stop()

        # Should have fired at least once
        assert len(events) >= 1
        assert engine.fire_count >= 1

        # Verify event contents
        event = events[0]
        assert event.trigger_id == "test_interval"
        assert event.pipeline_id == "test_pipeline"
        assert event.fired_at > 0

    @pytest.mark.asyncio
    async def test_interval_engine_double_start_ignored(self, interval_spec: TriggerSpec) -> None:
        """Test that starting twice is a no-op."""
        engine = IntervalTriggerEngine(interval_spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)
        await engine.start(callback)  # Second start should be ignored

        assert engine.is_running

        await engine.stop()


# ============================================================
# ThresholdTriggerEngine Tests
# ============================================================


class TestThresholdTriggerEngine:
    """Tests for ThresholdTriggerEngine."""

    @pytest.fixture
    def threshold_spec(self) -> TriggerSpec:
        """Create a threshold trigger spec."""
        return TriggerSpec(
            id="test_threshold",
            type=TriggerType.THRESHOLD,
            table="st_vec",
            condition="status = 'READY'",
            threshold_count=10,
            check_interval_seconds=1,  # 100ms for fast testing
        )

    @pytest.fixture
    def mock_syscalls(self) -> MagicMock:
        """Create mock syscalls with query_count."""
        syscalls = MagicMock()
        syscalls.query_count = AsyncMock(return_value=0)
        return syscalls

    def test_threshold_engine_creation(
        self,
        threshold_spec: TriggerSpec,
        mock_syscalls: MagicMock,
    ) -> None:
        """Test creating a threshold trigger engine."""
        engine = ThresholdTriggerEngine(threshold_spec, "test_pipeline", mock_syscalls)

        assert engine.spec == threshold_spec
        assert engine.pipeline_id == "test_pipeline"
        assert not engine.is_running

    @pytest.mark.asyncio
    async def test_threshold_engine_start_stop(
        self,
        threshold_spec: TriggerSpec,
        mock_syscalls: MagicMock,
    ) -> None:
        """Test starting and stopping threshold engine."""
        engine = ThresholdTriggerEngine(threshold_spec, "test_pipeline", mock_syscalls)
        callback = MagicMock()

        await engine.start(callback)
        assert engine.is_running

        await engine.stop()
        assert not engine.is_running

    @pytest.mark.asyncio
    async def test_threshold_engine_fires_when_exceeded(
        self,
        threshold_spec: TriggerSpec,
        mock_syscalls: MagicMock,
    ) -> None:
        """Test that threshold engine fires when count exceeds threshold."""
        # Set count above threshold
        mock_syscalls.query_count = AsyncMock(return_value=15)

        engine = ThresholdTriggerEngine(threshold_spec, "test_pipeline", mock_syscalls)
        events: list[TriggerEvent] = []

        def callback(event: TriggerEvent) -> None:
            events.append(event)

        await engine.start(callback)
        await asyncio.sleep(1.2)  # Wait for at least one check
        await engine.stop()

        # Should have fired
        assert len(events) >= 1
        assert engine.fire_count >= 1

        # Verify context contains count info
        event = events[0]
        assert event.context["count"] == 15
        assert event.context["threshold"] == 10

    @pytest.mark.asyncio
    async def test_threshold_engine_no_fire_below_threshold(
        self,
        threshold_spec: TriggerSpec,
        mock_syscalls: MagicMock,
    ) -> None:
        """Test that threshold engine doesn't fire below threshold."""
        # Set count below threshold
        mock_syscalls.query_count = AsyncMock(return_value=5)

        engine = ThresholdTriggerEngine(threshold_spec, "test_pipeline", mock_syscalls)
        callback = MagicMock()

        await engine.start(callback)
        await asyncio.sleep(1.2)
        await engine.stop()

        # Should not have fired
        callback.assert_not_called()
        assert engine.fire_count == 0


# ============================================================
# ManualTriggerEngine Tests
# ============================================================


class TestManualTriggerEngine:
    """Tests for ManualTriggerEngine."""

    @pytest.fixture
    def manual_spec(self) -> TriggerSpec:
        """Create a manual trigger spec."""
        return TriggerSpec(
            id="test_manual",
            type=TriggerType.MANUAL,
        )

    def test_manual_engine_creation(self, manual_spec: TriggerSpec) -> None:
        """Test creating a manual trigger engine."""
        engine = ManualTriggerEngine(manual_spec, "test_pipeline")

        assert engine.spec == manual_spec
        assert engine.pipeline_id == "test_pipeline"
        assert not engine.is_running

    @pytest.mark.asyncio
    async def test_manual_engine_start_stop(self, manual_spec: TriggerSpec) -> None:
        """Test starting and stopping manual engine."""
        engine = ManualTriggerEngine(manual_spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)
        assert engine.is_running

        await engine.stop()
        assert not engine.is_running

    @pytest.mark.asyncio
    async def test_manual_engine_fire(self, manual_spec: TriggerSpec) -> None:
        """Test manually firing the trigger."""
        engine = ManualTriggerEngine(manual_spec, "test_pipeline")
        events: list[TriggerEvent] = []

        def callback(event: TriggerEvent) -> None:
            events.append(event)

        await engine.start(callback)

        # Manually fire
        result = engine.fire()

        assert result is True
        assert len(events) == 1
        assert engine.fire_count == 1

        event = events[0]
        assert event.trigger_id == "test_manual"
        assert event.pipeline_id == "test_pipeline"

        await engine.stop()

    @pytest.mark.asyncio
    async def test_manual_engine_fire_when_stopped(self, manual_spec: TriggerSpec) -> None:
        """Test that fire returns False when not running."""
        engine = ManualTriggerEngine(manual_spec, "test_pipeline")

        # Not started - should fail
        result = engine.fire()
        assert result is False
        assert engine.fire_count == 0

    @pytest.mark.asyncio
    async def test_manual_engine_multiple_fires(self, manual_spec: TriggerSpec) -> None:
        """Test firing multiple times."""
        engine = ManualTriggerEngine(manual_spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)

        engine.fire()
        engine.fire()
        engine.fire()

        assert engine.fire_count == 3
        assert callback.call_count == 3

        await engine.stop()


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateTriggerEngine:
    """Tests for create_trigger_engine factory."""

    @pytest.fixture
    def mock_syscalls(self) -> MagicMock:
        """Create mock syscalls."""
        syscalls = MagicMock()
        syscalls.query_count = AsyncMock()
        return syscalls

    def test_create_interval_engine(self) -> None:
        """Test creating interval engine via factory."""
        spec = TriggerSpec(
            id="interval",
            type=TriggerType.INTERVAL,
            interval_seconds=60,
        )

        engine = create_trigger_engine(spec, "pipeline")

        assert isinstance(engine, IntervalTriggerEngine)
        assert engine.spec == spec

    def test_create_threshold_engine(self, mock_syscalls: MagicMock) -> None:
        """Test creating threshold engine via factory."""
        spec = TriggerSpec(
            id="threshold",
            type=TriggerType.THRESHOLD,
            table="st_vec",
            threshold_count=50,
        )

        engine = create_trigger_engine(spec, "pipeline", mock_syscalls)

        assert isinstance(engine, ThresholdTriggerEngine)

    def test_create_threshold_engine_requires_syscalls(self) -> None:
        """Test that threshold engine requires syscalls."""
        spec = TriggerSpec(
            id="threshold",
            type=TriggerType.THRESHOLD,
            table="st_vec",
            threshold_count=50,
        )

        with pytest.raises(ValueError, match="requires syscalls"):
            create_trigger_engine(spec, "pipeline", syscalls=None)

    def test_create_manual_engine(self) -> None:
        """Test creating manual engine via factory."""
        spec = TriggerSpec(
            id="manual",
            type=TriggerType.MANUAL,
        )

        engine = create_trigger_engine(spec, "pipeline")

        assert isinstance(engine, ManualTriggerEngine)

    def test_create_cron_engine(self) -> None:
        """Test creating CRON engine via factory."""
        spec = TriggerSpec(
            id="cron_test",
            type=TriggerType.CRON,
            cron_expression="0 * * * *",
        )

        engine = create_trigger_engine(spec, "pipeline")

        assert isinstance(engine, CronTriggerEngine)
        assert engine.spec == spec

    def test_create_idle_engine_requires_activity_tracker(self) -> None:
        """Test that IDLE trigger requires activity_tracker parameter."""
        spec = TriggerSpec(
            id="idle_test",
            type=TriggerType.IDLE,
            idle_seconds=300,  # Required for IDLE type
        )

        with pytest.raises(ValueError, match="requires activity_tracker"):
            create_trigger_engine(spec, "pipeline")


# ============================================================
# TriggerEngine Base Tests
# ============================================================


class TestTriggerEngineBase:
    """Tests for TriggerEngine base class behavior."""

    @pytest.fixture
    def spec(self) -> TriggerSpec:
        """Create a basic spec."""
        return TriggerSpec(
            id="base_test",
            type=TriggerType.MANUAL,
        )

    def test_engine_initial_state(self, spec: TriggerSpec) -> None:
        """Test initial state of trigger engine."""
        engine = ManualTriggerEngine(spec, "test_pipeline")

        assert engine.is_running is False
        assert engine.last_fired is None
        assert engine.fire_count == 0

    def test_create_event(self, spec: TriggerSpec) -> None:
        """Test _create_event method."""
        engine = ManualTriggerEngine(spec, "test_pipeline")
        event = engine._create_event({"key": "value"})

        assert event.trigger_id == "base_test"
        assert event.pipeline_id == "test_pipeline"
        assert event.fired_at > 0
        assert event.context == {"key": "value"}

    def test_record_fire(self, spec: TriggerSpec) -> None:
        """Test _record_fire method."""
        engine = ManualTriggerEngine(spec, "test_pipeline")
        event = engine._create_event()

        engine._record_fire(event)

        assert engine.last_fired == event.fired_at
        assert engine.fire_count == 1

        # Fire again
        event2 = engine._create_event()
        engine._record_fire(event2)

        assert engine.last_fired == event2.fired_at
        assert engine.fire_count == 2
