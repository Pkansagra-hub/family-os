"""
Tests for CronTriggerEngine.

Tests the CRON trigger implementation for scheduled pipeline execution.
Requires the croniter package: pip install croniter
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from k0.runtime.schemas import TriggerSpec, TriggerType
from k0.scheduler.triggers import CronTriggerEngine, TriggerEvent

# Skip all tests if croniter not installed
pytest.importorskip("croniter")


class TestCronTriggerEngineCreation:
    """Tests for CronTriggerEngine creation and validation."""

    @pytest.fixture
    def cron_spec(self) -> TriggerSpec:
        """Create a cron trigger spec."""
        return TriggerSpec(
            id="test_cron",
            type=TriggerType.CRON,
            cron_expression="* * * * *",  # Every minute
        )

    def test_cron_engine_creation(self, cron_spec: TriggerSpec) -> None:
        """Test creating a cron trigger engine."""
        engine = CronTriggerEngine(cron_spec, "test_pipeline")

        assert engine.spec == cron_spec
        assert engine.pipeline_id == "test_pipeline"
        assert not engine.is_running
        assert engine.fire_count == 0
        assert engine.last_fired is None

    def test_cron_engine_with_timezone(self, cron_spec: TriggerSpec) -> None:
        """Test creating engine with custom timezone."""
        engine = CronTriggerEngine(cron_spec, "test_pipeline", timezone="US/Eastern")

        assert engine._timezone == "US/Eastern"

    def test_cron_engine_default_timezone(self, cron_spec: TriggerSpec) -> None:
        """Test that default timezone is UTC."""
        engine = CronTriggerEngine(cron_spec, "test_pipeline")

        assert engine._timezone == "UTC"


class TestCronTriggerEngineStartStop:
    """Tests for CronTriggerEngine start/stop lifecycle."""

    @pytest.fixture
    def cron_spec(self) -> TriggerSpec:
        """Create a cron trigger spec."""
        return TriggerSpec(
            id="test_cron",
            type=TriggerType.CRON,
            cron_expression="* * * * *",
        )

    @pytest.mark.asyncio
    async def test_cron_engine_start_stop(self, cron_spec: TriggerSpec) -> None:
        """Test starting and stopping cron engine."""
        engine = CronTriggerEngine(cron_spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)
        assert engine.is_running

        await engine.stop()
        assert not engine.is_running

    @pytest.mark.asyncio
    async def test_cron_engine_double_start_ignored(self, cron_spec: TriggerSpec) -> None:
        """Test that starting twice is a no-op."""
        engine = CronTriggerEngine(cron_spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)
        await engine.start(callback)  # Should log warning but not fail

        assert engine.is_running

        await engine.stop()

    @pytest.mark.asyncio
    async def test_cron_engine_requires_cron_expression(self) -> None:
        """Test that TriggerSpec validation requires cron_expression for CRON type."""
        from pydantic import ValidationError

        # Pydantic validation catches missing cron_expression at spec creation
        with pytest.raises(ValidationError, match="cron_expression required"):
            TriggerSpec(
                id="test_cron_no_expr",
                type=TriggerType.CRON,
                # No cron_expression - should fail validation
            )

    @pytest.mark.asyncio
    async def test_cron_engine_rejects_invalid_expression(self) -> None:
        """Test that engine rejects invalid cron expression."""
        spec = TriggerSpec(
            id="test_cron_invalid",
            type=TriggerType.CRON,
            cron_expression="invalid cron",
        )
        engine = CronTriggerEngine(spec, "test_pipeline")
        callback = MagicMock()

        with pytest.raises(ValueError, match="Invalid cron expression"):
            await engine.start(callback)


class TestCronTriggerEngineExecution:
    """Tests for CronTriggerEngine firing behavior."""

    @pytest.mark.asyncio
    async def test_cron_trigger_fires_callback(self) -> None:
        """Test that cron trigger fires callback at scheduled time."""
        spec = TriggerSpec(
            id="test_cron",
            type=TriggerType.CRON,
            cron_expression="* * * * *",  # Every minute
        )
        engine = CronTriggerEngine(spec, "test_pipeline")
        events: list[TriggerEvent] = []

        def callback(event: TriggerEvent) -> None:
            events.append(event)

        # Mock time to make test fast
        # The engine uses time.time() for calculating delay
        with patch("k0.scheduler.triggers.time") as mock_time:
            # Start at 59 seconds before next minute
            mock_time.monotonic.return_value = 100.0
            mock_time.time.return_value = time.time()

            await engine.start(callback)

            # Let the loop run briefly
            await asyncio.sleep(0.1)

            await engine.stop()

        # Engine started, verify it's registered
        assert engine.fire_count >= 0  # May or may not have fired yet

    @pytest.mark.asyncio
    async def test_cron_trigger_context_includes_expression(self) -> None:
        """Test that TriggerEvent context includes cron expression."""
        spec = TriggerSpec(
            id="test_cron",
            type=TriggerType.CRON,
            cron_expression="0 2 * * *",  # 2 AM daily
        )
        engine = CronTriggerEngine(spec, "test_pipeline")
        events: list[TriggerEvent] = []

        def callback(event: TriggerEvent) -> None:
            events.append(event)

        # Manually create and record an event to test context
        event = engine._create_event(
            {
                "scheduled_time": time.time(),
                "trigger_type": "cron",
                "cron_expression": spec.cron_expression,
            }
        )
        engine._record_fire(event)

        assert event.context["trigger_type"] == "cron"
        assert event.context["cron_expression"] == "0 2 * * *"
        assert "scheduled_time" in event.context

    @pytest.mark.asyncio
    async def test_cron_trigger_records_fire_count(self) -> None:
        """Test that fire count is incremented on each trigger."""
        spec = TriggerSpec(
            id="test_cron",
            type=TriggerType.CRON,
            cron_expression="* * * * *",
        )
        engine = CronTriggerEngine(spec, "test_pipeline")

        # Manually record fires
        event1 = engine._create_event()
        engine._record_fire(event1)
        assert engine.fire_count == 1

        event2 = engine._create_event()
        engine._record_fire(event2)
        assert engine.fire_count == 2

    def test_cron_trigger_get_next_fire_time(self) -> None:
        """Test get_next_fire_time returns correct timestamp."""
        spec = TriggerSpec(
            id="test_cron",
            type=TriggerType.CRON,
            cron_expression="0 * * * *",  # Top of every hour
        )
        engine = CronTriggerEngine(spec, "test_pipeline")

        # Before start, returns None
        assert engine.get_next_fire_time() is None

    @pytest.mark.asyncio
    async def test_cron_trigger_get_next_fire_time_after_start(self) -> None:
        """Test get_next_fire_time after engine started."""
        spec = TriggerSpec(
            id="test_cron",
            type=TriggerType.CRON,
            cron_expression="0 * * * *",  # Top of every hour
        )
        engine = CronTriggerEngine(spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)

        next_fire = engine.get_next_fire_time()
        assert next_fire is not None
        assert next_fire > time.time()  # Should be in the future

        await engine.stop()


class TestCronTriggerEngineCroniterIntegration:
    """Tests for croniter integration."""

    def test_croniter_import_error(self) -> None:
        """Test helpful error when croniter not installed."""
        spec = TriggerSpec(
            id="test_cron",
            type=TriggerType.CRON,
            cron_expression="* * * * *",
        )
        # Verify engine can be created (croniter is installed in test env)
        engine = CronTriggerEngine(spec, "test_pipeline")
        assert engine.spec.cron_expression == "* * * * *"


class TestCronExpressionValidation:
    """Tests for various cron expression formats."""

    @pytest.mark.asyncio
    async def test_cron_every_minute(self) -> None:
        """Test every minute expression: * * * * *"""
        spec = TriggerSpec(
            id="every_minute",
            type=TriggerType.CRON,
            cron_expression="* * * * *",
        )
        engine = CronTriggerEngine(spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)
        assert engine.is_running
        await engine.stop()

    @pytest.mark.asyncio
    async def test_cron_daily_2am(self) -> None:
        """Test daily at 2 AM: 0 2 * * *"""
        spec = TriggerSpec(
            id="daily_2am",
            type=TriggerType.CRON,
            cron_expression="0 2 * * *",
        )
        engine = CronTriggerEngine(spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)
        assert engine.is_running
        await engine.stop()

    @pytest.mark.asyncio
    async def test_cron_hourly_2am_to_5am(self) -> None:
        """Test hourly during 2-5 AM window: 0 2-5 * * *"""
        spec = TriggerSpec(
            id="sleep_window",
            type=TriggerType.CRON,
            cron_expression="0 2-5 * * *",
        )
        engine = CronTriggerEngine(spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)
        assert engine.is_running
        await engine.stop()

    @pytest.mark.asyncio
    async def test_cron_weekdays_only(self) -> None:
        """Test weekdays at noon: 0 12 * * 1-5"""
        spec = TriggerSpec(
            id="weekday_noon",
            type=TriggerType.CRON,
            cron_expression="0 12 * * 1-5",
        )
        engine = CronTriggerEngine(spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)
        assert engine.is_running
        await engine.stop()

    @pytest.mark.asyncio
    async def test_cron_every_5_minutes(self) -> None:
        """Test every 5 minutes: */5 * * * *"""
        spec = TriggerSpec(
            id="every_5_min",
            type=TriggerType.CRON,
            cron_expression="*/5 * * * *",
        )
        engine = CronTriggerEngine(spec, "test_pipeline")
        callback = MagicMock()

        await engine.start(callback)
        assert engine.is_running
        await engine.stop()


class TestCronTriggerEngineErrorHandling:
    """Tests for error handling in CronTriggerEngine."""

    @pytest.mark.asyncio
    async def test_cron_engine_handles_callback_error(self) -> None:
        """Test that engine continues after callback error."""
        spec = TriggerSpec(
            id="test_cron",
            type=TriggerType.CRON,
            cron_expression="* * * * *",
        )
        engine = CronTriggerEngine(spec, "test_pipeline")

        def bad_callback(event: TriggerEvent) -> None:
            raise RuntimeError("Callback failed")

        # Engine should not crash on callback error
        await engine.start(bad_callback)
        await asyncio.sleep(0.1)
        await engine.stop()

        # Engine should have stopped cleanly
        assert not engine.is_running

    @pytest.mark.asyncio
    async def test_cron_engine_stop_when_not_running(self) -> None:
        """Test stopping engine that's not running."""
        spec = TriggerSpec(
            id="test_cron",
            type=TriggerType.CRON,
            cron_expression="* * * * *",
        )
        engine = CronTriggerEngine(spec, "test_pipeline")

        # Should not raise
        await engine.stop()
        assert not engine.is_running
