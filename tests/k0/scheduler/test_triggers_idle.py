"""
Tests for IdleTriggerEngine.

Tests the IDLE trigger implementation for idle-based pipeline execution.
Requires ActivityTracker infrastructure.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from k0.runtime.schemas import TriggerSpec, TriggerType
from k0.scheduler.activity import ActivityTracker
from k0.scheduler.triggers import IdleTriggerEngine, TriggerEvent, create_trigger_engine


class TestIdleTriggerEngineCreation:
    """Tests for IdleTriggerEngine creation and validation."""

    @pytest.fixture
    def idle_spec(self) -> TriggerSpec:
        """Create an idle trigger spec."""
        return TriggerSpec(
            id="test_idle",
            type=TriggerType.IDLE,
            idle_seconds=5,
        )

    @pytest.fixture
    def activity_tracker(self) -> ActivityTracker:
        """Create an activity tracker for testing."""
        return ActivityTracker(check_interval=0.05)

    def test_idle_engine_creation(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test creating an idle trigger engine."""
        engine = IdleTriggerEngine(idle_spec, "test_pipeline", activity_tracker)

        assert engine.spec == idle_spec
        assert engine.pipeline_id == "test_pipeline"
        assert not engine.is_running
        assert engine.fire_count == 0
        assert engine.last_fired is None

    def test_idle_engine_with_syscalls(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test creating engine with syscalls for pending count."""
        mock_syscalls = MagicMock()
        engine = IdleTriggerEngine(
            idle_spec,
            "test_pipeline",
            activity_tracker,
            syscalls=mock_syscalls,
        )

        assert engine._syscalls is mock_syscalls


class TestIdleTriggerEngineStartStop:
    """Tests for IdleTriggerEngine start/stop lifecycle."""

    @pytest.fixture
    def idle_spec(self) -> TriggerSpec:
        """Create an idle trigger spec."""
        return TriggerSpec(
            id="test_idle",
            type=TriggerType.IDLE,
            idle_seconds=1,  # Minimum valid value
        )

    @pytest.fixture
    async def activity_tracker(self) -> ActivityTracker:
        """Create and start an activity tracker with fast check interval."""
        tracker = ActivityTracker(check_interval=0.01)
        await tracker.start()
        yield tracker
        await tracker.stop()

    @pytest.mark.asyncio
    async def test_idle_engine_start_stop(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test starting and stopping idle engine."""
        engine = IdleTriggerEngine(idle_spec, "test_pipeline", activity_tracker)
        callback = MagicMock()

        await engine.start(callback)
        assert engine.is_running
        assert activity_tracker.listener_count == 1

        await engine.stop()
        assert not engine.is_running
        assert activity_tracker.listener_count == 0

    @pytest.mark.asyncio
    async def test_idle_engine_double_start_ignored(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test that starting twice is a no-op."""
        engine = IdleTriggerEngine(idle_spec, "test_pipeline", activity_tracker)
        callback = MagicMock()

        await engine.start(callback)
        await engine.start(callback)  # Should log warning but not fail

        assert engine.is_running
        assert activity_tracker.listener_count == 1

        await engine.stop()

    @pytest.mark.asyncio
    async def test_idle_engine_requires_idle_seconds(self) -> None:
        """Test that TriggerSpec validation requires idle_seconds for IDLE type."""
        from pydantic import ValidationError

        # Pydantic validation catches missing idle_seconds at spec creation
        with pytest.raises(ValidationError, match="idle_seconds required"):
            TriggerSpec(
                id="test_idle_no_seconds",
                type=TriggerType.IDLE,
                # No idle_seconds - should fail validation
            )


class TestIdleTriggerEngineExecution:
    """Tests for IdleTriggerEngine firing behavior."""

    @pytest.fixture
    def idle_spec(self) -> TriggerSpec:
        """Create an idle trigger spec with short threshold."""
        return TriggerSpec(
            id="test_idle",
            type=TriggerType.IDLE,
            idle_seconds=1,  # Minimum valid value
        )

    @pytest.fixture
    async def activity_tracker(self) -> ActivityTracker:
        """Create and start an activity tracker with fast check interval."""
        tracker = ActivityTracker(check_interval=0.01)
        await tracker.start()
        yield tracker
        await tracker.stop()

    @pytest.mark.asyncio
    async def test_idle_trigger_fires_callback(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test that idle trigger fires callback when idle threshold met."""
        import time

        engine = IdleTriggerEngine(idle_spec, "test_pipeline", activity_tracker)
        events: list[TriggerEvent] = []

        def callback(event: TriggerEvent) -> None:
            events.append(event)

        await engine.start(callback)

        # Manipulate _last_activity to simulate being idle for threshold time
        activity_tracker._last_activity = time.monotonic() - 2.0  # 2 seconds ago

        # Wait for check loop to detect and fire
        await asyncio.sleep(0.1)

        await engine.stop()

        # Should have fired at least once
        assert len(events) >= 1
        assert engine.fire_count >= 1

    @pytest.mark.asyncio
    async def test_idle_trigger_context_includes_idle_seconds(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test that TriggerEvent context includes idle_seconds."""
        import time

        engine = IdleTriggerEngine(idle_spec, "test_pipeline", activity_tracker)
        events: list[TriggerEvent] = []

        def callback(event: TriggerEvent) -> None:
            events.append(event)

        await engine.start(callback)

        # Simulate idle for threshold time
        activity_tracker._last_activity = time.monotonic() - 2.0
        await asyncio.sleep(0.1)
        await engine.stop()

        assert len(events) >= 1
        event = events[0]
        assert event.context["trigger_type"] == "idle"
        assert "idle_seconds" in event.context
        assert event.context["idle_seconds"] >= 1.0  # Threshold is 1 second

    @pytest.mark.asyncio
    async def test_idle_trigger_resets_on_activity(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test that idle trigger can fire again after activity."""
        import time

        engine = IdleTriggerEngine(idle_spec, "test_pipeline", activity_tracker)
        events: list[TriggerEvent] = []

        def callback(event: TriggerEvent) -> None:
            events.append(event)

        await engine.start(callback)

        # Simulate idle to trigger first fire
        activity_tracker._last_activity = time.monotonic() - 2.0
        await asyncio.sleep(0.1)
        first_count = len(events)
        assert first_count >= 1

        # Record activity (resets the timer)
        activity_tracker.record_activity()

        # Simulate idle again for second fire
        activity_tracker._last_activity = time.monotonic() - 2.0
        await asyncio.sleep(0.1)

        await engine.stop()

        # Should have fired again
        assert len(events) > first_count

    @pytest.mark.asyncio
    async def test_idle_trigger_records_fire_count(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test that fire count is incremented on each trigger."""
        import time

        engine = IdleTriggerEngine(idle_spec, "test_pipeline", activity_tracker)
        callback = MagicMock()

        await engine.start(callback)

        # Simulate idle to trigger first fire
        activity_tracker._last_activity = time.monotonic() - 2.0
        await asyncio.sleep(0.1)

        first_count = engine.fire_count
        assert first_count >= 1

        # Record activity (resets timer and fired flag)
        activity_tracker.record_activity()

        # Simulate idle again for second fire
        activity_tracker._last_activity = time.monotonic() - 2.0
        await asyncio.sleep(0.1)

        await engine.stop()

        assert engine.fire_count > first_count


class TestIdleTriggerEngineMinPending:
    """Tests for min_pending condition."""

    @pytest.fixture
    def idle_spec_with_pending(self) -> TriggerSpec:
        """Create an idle trigger spec with min_pending."""
        return TriggerSpec(
            id="test_idle_pending",
            type=TriggerType.IDLE,
            idle_seconds=1,  # Minimum valid value
            min_pending=10,
            table="st_vec",
            condition="status = 'pending'",
        )

    @pytest.fixture
    async def activity_tracker(self) -> ActivityTracker:
        """Create and start an activity tracker with fast check interval."""
        tracker = ActivityTracker(check_interval=0.01)
        await tracker.start()
        yield tracker
        await tracker.stop()

    @pytest.mark.asyncio
    async def test_idle_trigger_with_min_pending_no_syscalls(
        self,
        idle_spec_with_pending: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test idle trigger with min_pending but no syscalls returns 0."""
        import time

        engine = IdleTriggerEngine(
            idle_spec_with_pending,
            "test_pipeline",
            activity_tracker,
            syscalls=None,
        )
        callback = MagicMock()

        await engine.start(callback)

        # Simulate idle for threshold time
        activity_tracker._last_activity = time.monotonic() - 2.0
        await asyncio.sleep(0.1)
        await engine.stop()

        # Without syscalls, pending count is 0, which is < min_pending (10)
        # So trigger should NOT fire
        callback.assert_not_called()


class TestIdleTriggerEngineFactory:
    """Tests for create_trigger_engine with IDLE type."""

    @pytest.fixture
    def idle_spec(self) -> TriggerSpec:
        """Create an idle trigger spec."""
        return TriggerSpec(
            id="test_idle",
            type=TriggerType.IDLE,
            idle_seconds=300,
        )

    @pytest.fixture
    def activity_tracker(self) -> ActivityTracker:
        """Create an activity tracker."""
        return ActivityTracker()

    def test_create_idle_engine(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test creating IDLE engine via factory."""
        engine = create_trigger_engine(
            idle_spec,
            "pipeline",
            activity_tracker=activity_tracker,
        )

        assert isinstance(engine, IdleTriggerEngine)
        assert engine.spec == idle_spec

    def test_create_idle_engine_requires_activity_tracker(
        self,
        idle_spec: TriggerSpec,
    ) -> None:
        """Test that factory raises if activity_tracker missing."""
        with pytest.raises(ValueError, match="requires activity_tracker"):
            create_trigger_engine(idle_spec, "pipeline", activity_tracker=None)

    def test_create_idle_engine_with_syscalls(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test creating IDLE engine with syscalls."""
        mock_syscalls = MagicMock()
        engine = create_trigger_engine(
            idle_spec,
            "pipeline",
            syscalls=mock_syscalls,
            activity_tracker=activity_tracker,
        )

        assert isinstance(engine, IdleTriggerEngine)
        assert engine._syscalls is mock_syscalls


class TestIdleTriggerEngineErrorHandling:
    """Tests for error handling in IdleTriggerEngine."""

    @pytest.fixture
    def idle_spec(self) -> TriggerSpec:
        """Create an idle trigger spec."""
        return TriggerSpec(
            id="test_idle",
            type=TriggerType.IDLE,
            idle_seconds=1,  # Minimum valid value
        )

    @pytest.fixture
    async def activity_tracker(self) -> ActivityTracker:
        """Create and start an activity tracker with fast check interval."""
        tracker = ActivityTracker(check_interval=0.01)
        await tracker.start()
        yield tracker
        await tracker.stop()

    @pytest.mark.asyncio
    async def test_idle_engine_stop_when_not_running(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test stopping engine that's not running."""
        engine = IdleTriggerEngine(idle_spec, "test_pipeline", activity_tracker)

        # Should not raise
        await engine.stop()
        assert not engine.is_running

    @pytest.mark.asyncio
    async def test_idle_engine_handles_callback_error(
        self,
        idle_spec: TriggerSpec,
        activity_tracker: ActivityTracker,
    ) -> None:
        """Test that engine continues after callback error."""
        import time

        def bad_callback(event: TriggerEvent) -> None:
            raise RuntimeError("Callback failed")

        engine = IdleTriggerEngine(idle_spec, "test_pipeline", activity_tracker)

        # Engine should not crash on callback error (handled by ActivityTracker)
        await engine.start(bad_callback)

        # Simulate idle for threshold time
        activity_tracker._last_activity = time.monotonic() - 2.0
        await asyncio.sleep(0.1)
        await engine.stop()

        # Engine should have stopped cleanly
        assert not engine.is_running
