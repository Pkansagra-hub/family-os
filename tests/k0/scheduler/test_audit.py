"""
Tests for SchedulerAuditor and audit events.

Tests Issue 3.3.4: Trigger Audit Logging
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from k0.scheduler.audit import (
    PipelineRunCompleteEvent,
    PipelineRunStartEvent,
    SchedulerAuditor,
    TriggerFiredEvent,
    TriggerQueuedEvent,
    TriggerSkippedEvent,
    get_scheduler_auditor,
    reset_scheduler_auditor,
)


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create a mock logger for testing."""
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def auditor(mock_logger: MagicMock) -> SchedulerAuditor:
    """Create an auditor with mock logger."""
    return SchedulerAuditor(logger=mock_logger)


class TestSchedulerAuditor:
    """Tests for SchedulerAuditor class."""

    def test_log_trigger_fired(self, auditor: SchedulerAuditor, mock_logger: MagicMock) -> None:
        """Test logging a trigger fired event."""
        auditor.log_trigger_fired(
            pipeline_id="P03",
            trigger_id="trigger-1",
            trigger_type="interval",
            execution_count=5,
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert call_args["event"] == "trigger.fired"
        assert call_args["pipeline_id"] == "P03"
        assert call_args["trigger_id"] == "trigger-1"
        assert call_args["trigger_type"] == "interval"
        assert call_args["execution_count"] == 5

    def test_log_trigger_skipped(self, auditor: SchedulerAuditor, mock_logger: MagicMock) -> None:
        """Test logging a trigger skipped event."""
        auditor.log_trigger_skipped(
            pipeline_id="P03",
            trigger_id="trigger-1",
            trigger_type="interval",
            reason="already_running",
        )

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        assert call_args["event"] == "trigger.skipped"
        assert call_args["pipeline_id"] == "P03"
        assert call_args["trigger_id"] == "trigger-1"
        assert call_args["reason"] == "already_running"

    def test_log_trigger_queued(self, auditor: SchedulerAuditor, mock_logger: MagicMock) -> None:
        """Test logging a trigger queued event."""
        auditor.log_trigger_queued(
            pipeline_id="P03",
            trigger_id="trigger-2",
            trigger_type="threshold",
            replaced_trigger_id="trigger-1",
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert call_args["event"] == "trigger.queued"
        assert call_args["pipeline_id"] == "P03"
        assert call_args["trigger_id"] == "trigger-2"
        assert call_args["replaced_trigger_id"] == "trigger-1"

    def test_log_pipeline_run_start(
        self, auditor: SchedulerAuditor, mock_logger: MagicMock
    ) -> None:
        """Test logging a pipeline run start event."""
        auditor.log_pipeline_run_start(
            pipeline_id="P03",
            trigger_id="trigger-1",
            trigger_type="threshold",
            run_number=10,
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert call_args["event"] == "pipeline.run.start"
        assert call_args["pipeline_id"] == "P03"
        assert call_args["run_number"] == 10

    def test_log_pipeline_run_complete_success(
        self, auditor: SchedulerAuditor, mock_logger: MagicMock
    ) -> None:
        """Test logging a successful pipeline run completion."""
        auditor.log_pipeline_run_complete(
            pipeline_id="P03",
            trigger_id="trigger-1",
            duration_ms=150.5,
            success=True,
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert call_args["event"] == "pipeline.run.complete"
        assert call_args["success"] is True
        assert call_args["duration_ms"] == 150.5
        assert call_args["error"] is None

    def test_log_pipeline_run_complete_error(
        self, auditor: SchedulerAuditor, mock_logger: MagicMock
    ) -> None:
        """Test logging a failed pipeline run completion."""
        auditor.log_pipeline_run_complete(
            pipeline_id="P03",
            trigger_id="trigger-1",
            duration_ms=50.0,
            success=False,
            error="Connection timeout",
        )

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args[0][0]
        assert call_args["event"] == "pipeline.run.complete"
        assert call_args["success"] is False
        assert call_args["error"] == "Connection timeout"

    def test_audit_event_has_timestamp(
        self, auditor: SchedulerAuditor, mock_logger: MagicMock
    ) -> None:
        """Test that audit events have timestamps."""
        auditor.log_trigger_fired(
            pipeline_id="P03",
            trigger_id="trigger-1",
            trigger_type="interval",
        )

        call_args = mock_logger.info.call_args[0][0]
        assert "timestamp" in call_args
        assert call_args["timestamp"] is not None
        # Should be ISO format
        assert "T" in call_args["timestamp"]


class TestAuditEvents:
    """Tests for audit event dataclasses."""

    def test_trigger_fired_event_fields(self) -> None:
        """Test TriggerFiredEvent has all required fields."""
        event = TriggerFiredEvent(
            event="trigger.fired",
            timestamp="2025-01-01T00:00:00Z",
            pipeline_id="P03",
            trigger_id="trigger-1",
            trigger_type="interval",
            execution_count=5,
        )
        assert event.event == "trigger.fired"
        assert event.pipeline_id == "P03"
        assert event.trigger_id == "trigger-1"
        assert event.trigger_type == "interval"
        assert event.execution_count == 5

    def test_trigger_skipped_event_fields(self) -> None:
        """Test TriggerSkippedEvent has all required fields."""
        event = TriggerSkippedEvent(
            event="trigger.skipped",
            timestamp="2025-01-01T00:00:00Z",
            pipeline_id="P03",
            trigger_id="trigger-1",
            trigger_type="interval",
            reason="already_running",
        )
        assert event.event == "trigger.skipped"
        assert event.reason == "already_running"

    def test_trigger_queued_event_fields(self) -> None:
        """Test TriggerQueuedEvent has all required fields."""
        event = TriggerQueuedEvent(
            event="trigger.queued",
            timestamp="2025-01-01T00:00:00Z",
            pipeline_id="P03",
            trigger_id="trigger-2",
            trigger_type="threshold",
            replaced_trigger_id="trigger-1",
        )
        assert event.event == "trigger.queued"
        assert event.replaced_trigger_id == "trigger-1"

    def test_pipeline_run_start_event_fields(self) -> None:
        """Test PipelineRunStartEvent has all required fields."""
        event = PipelineRunStartEvent(
            event="pipeline.run.start",
            timestamp="2025-01-01T00:00:00Z",
            pipeline_id="P03",
            trigger_id="trigger-1",
            trigger_type="threshold",
            run_number=10,
        )
        assert event.event == "pipeline.run.start"
        assert event.run_number == 10

    def test_pipeline_run_complete_event_fields(self) -> None:
        """Test PipelineRunCompleteEvent has all required fields."""
        event = PipelineRunCompleteEvent(
            event="pipeline.run.complete",
            timestamp="2025-01-01T00:00:00Z",
            pipeline_id="P03",
            trigger_id="trigger-1",
            duration_ms=150.5,
            success=True,
        )
        assert event.event == "pipeline.run.complete"
        assert event.duration_ms == 150.5
        assert event.success is True


class TestGlobalAuditor:
    """Tests for global auditor singleton."""

    def test_get_scheduler_auditor_creates_singleton(self) -> None:
        """Test that get_scheduler_auditor returns singleton."""
        reset_scheduler_auditor()
        auditor1 = get_scheduler_auditor()
        auditor2 = get_scheduler_auditor()
        assert auditor1 is auditor2

    def test_reset_scheduler_auditor_clears_singleton(self) -> None:
        """Test that reset clears the singleton."""
        auditor1 = get_scheduler_auditor()
        reset_scheduler_auditor()
        auditor2 = get_scheduler_auditor()
        assert auditor1 is not auditor2
