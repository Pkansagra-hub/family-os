"""
Tests for SessionState Structured Logging
==========================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 5.3 Tracing & Logging
ISSUE: 5.3.2

Tests:
1. StructuredLogRecord - serialization and fields
2. SessionStateJsonFormatter - format output
3. SessionStateLogger - all 15 log event types
4. JSON output validation - proper structure
5. Trace ID propagation - cognitive_trace_id in all logs
"""

import io
import json
import logging
from datetime import datetime

import pytest

from k1.sessionstate.logging import (
    LogEventType,
    SessionStateJsonFormatter,
    SessionStateLogger,
    StructuredLogRecord,
    configure_logger,
    get_default_logger,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def log_stream():
    """Provide a StringIO stream for capturing log output."""
    return io.StringIO()


@pytest.fixture
def logger(log_stream):
    """Provide a SessionStateLogger with captured output."""
    # Create logger with unique name to avoid conflicts
    import uuid

    logger_name = f"test.sessionstate.{uuid.uuid4().hex[:8]}"
    slogger = SessionStateLogger(
        name=logger_name,
        level=logging.DEBUG,
        stream=log_stream,
        use_json_format=True,
    )
    # Prevent propagation to root logger
    slogger._logger.propagate = False
    return slogger


@pytest.fixture
def text_logger(log_stream):
    """Provide a SessionStateLogger with text format output."""
    import uuid

    logger_name = f"test.sessionstate.text.{uuid.uuid4().hex[:8]}"
    slogger = SessionStateLogger(
        name=logger_name,
        level=logging.DEBUG,
        stream=log_stream,
        use_json_format=False,
    )
    # Prevent propagation to root logger
    slogger._logger.propagate = False
    return slogger


# =============================================================================
# TEST: LogEventType Enum
# =============================================================================


class TestLogEventType:
    """Test LogEventType enum values."""

    def test_mutation_events_exist(self):
        """All mutation event types should exist."""
        assert LogEventType.MUTATION_REQUESTED.value == "mutation.requested"
        assert LogEventType.MUTATION_APPROVED.value == "mutation.approved"
        assert LogEventType.MUTATION_REJECTED.value == "mutation.rejected"

    def test_eviction_events_exist(self):
        """All eviction event types should exist."""
        assert LogEventType.EVICTION_TRIGGERED.value == "eviction.triggered"
        assert LogEventType.EVICTION_COMPLETED.value == "eviction.completed"

    def test_emergency_events_exist(self):
        """All emergency event types should exist."""
        assert LogEventType.EMERGENCY_ACTIVATED.value == "emergency.activated"
        assert LogEventType.EMERGENCY_RESOLVED.value == "emergency.resolved"

    def test_reconstruction_events_exist(self):
        """All reconstruction event types should exist."""
        assert LogEventType.RECONSTRUCTION_STARTED.value == "reconstruction.started"
        assert LogEventType.RECONSTRUCTION_COMPLETED.value == "reconstruction.completed"

    def test_lifecycle_events_exist(self):
        """All lifecycle event types should exist."""
        assert LogEventType.LIFECYCLE_STARTED.value == "lifecycle.started"
        assert LogEventType.LIFECYCLE_STOPPED.value == "lifecycle.stopped"

    def test_checkpoint_events_exist(self):
        """All checkpoint event types should exist."""
        assert LogEventType.CHECKPOINT_CREATED.value == "checkpoint.created"
        assert LogEventType.CHECKPOINT_RESTORED.value == "checkpoint.restored"

    def test_migration_events_exist(self):
        """All migration event types should exist."""
        assert LogEventType.MIGRATION_STARTED.value == "migration.started"
        assert LogEventType.MIGRATION_COMPLETED.value == "migration.completed"

    def test_pressure_events_exist(self):
        """Pressure event type should exist."""
        assert LogEventType.PRESSURE_CHANGED.value == "pressure.changed"

    def test_total_event_count(self):
        """Should have 16 event types total."""
        assert len(LogEventType) == 16


# =============================================================================
# TEST: StructuredLogRecord
# =============================================================================


class TestStructuredLogRecord:
    """Test StructuredLogRecord dataclass."""

    def test_default_values(self):
        """Default values should be set correctly."""
        record = StructuredLogRecord(event="test.event")
        assert record.event == "test.event"
        assert record.level == "INFO"
        assert record.session_id == ""
        assert record.trace_id == ""
        assert record.module == "sessionstate"
        assert record.timestamp_iso  # Should have a value
        assert record.context == {}

    def test_to_dict_includes_standard_fields(self):
        """to_dict should include all standard fields."""
        record = StructuredLogRecord(
            event="mutation.approved",
            level="INFO",
            session_id="sess-123",
            trace_id="trace-456",
        )
        d = record.to_dict()
        assert d["event"] == "mutation.approved"
        assert d["level"] == "INFO"
        assert d["session_id"] == "sess-123"
        assert d["trace_id"] == "trace-456"
        assert d["module"] == "sessionstate"
        assert "timestamp_iso" in d

    def test_to_dict_flattens_context(self):
        """Context fields should be flattened into top-level."""
        record = StructuredLogRecord(
            event="mutation.approved",
            context={"section": "beliefs_active", "bytes_delta": 256},
        )
        d = record.to_dict()
        assert d["section"] == "beliefs_active"
        assert d["bytes_delta"] == 256

    def test_to_json_returns_valid_json(self):
        """to_json should return valid JSON string."""
        record = StructuredLogRecord(
            event="test.event",
            session_id="sess-123",
            trace_id="trace-456",
            context={"key": "value"},
        )
        json_str = record.to_json()
        parsed = json.loads(json_str)
        assert parsed["event"] == "test.event"
        assert parsed["key"] == "value"

    def test_timestamp_is_iso_format(self):
        """Timestamp should be ISO 8601 format."""
        record = StructuredLogRecord(event="test.event")
        # Should be parseable as ISO datetime
        parsed = datetime.fromisoformat(record.timestamp_iso.replace("Z", "+00:00"))
        assert parsed is not None


# =============================================================================
# TEST: SessionStateJsonFormatter
# =============================================================================


class TestSessionStateJsonFormatter:
    """Test JSON formatter for Python logging."""

    def test_format_produces_valid_json(self):
        """Formatter should produce valid JSON."""
        formatter = SessionStateJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "Test message"
        assert parsed["level"] == "INFO"
        assert parsed["module"] == "sessionstate"

    def test_format_includes_structured_fields(self):
        """Formatter should extract structured fields from extra."""
        formatter = SessionStateJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.structured = {
            "event": "mutation.approved",
            "session_id": "sess-123",
            "trace_id": "trace-456",
            "context": {"section": "beliefs_active"},
        }
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["event"] == "mutation.approved"
        assert parsed["session_id"] == "sess-123"
        assert parsed["trace_id"] == "trace-456"
        assert parsed["section"] == "beliefs_active"

    def test_format_includes_exception(self):
        """Formatter should include exception info if present."""
        formatter = SessionStateJsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error occurred",
                args=(),
                exc_info=exc_info,
            )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]


# =============================================================================
# TEST: SessionStateLogger - Mutation Events
# =============================================================================


class TestSessionStateLoggerMutation:
    """Test mutation logging methods."""

    def test_mutation_requested(self, logger, log_stream):
        """mutation_requested should log correct fields."""
        logger.mutation_requested(
            session_id="sess-123",
            trace_id="trace-456",
            section="beliefs_active",
            operation="append",
            estimated_bytes=256,
            writer_id="concierge",
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "mutation.requested"
        assert parsed["session_id"] == "sess-123"
        assert parsed["trace_id"] == "trace-456"
        assert parsed["section"] == "beliefs_active"
        assert parsed["operation"] == "append"
        assert parsed["estimated_bytes"] == 256
        assert parsed["writer_id"] == "concierge"
        assert parsed["level"] == "DEBUG"

    def test_mutation_approved(self, logger, log_stream):
        """mutation_approved should log correct fields."""
        logger.mutation_approved(
            session_id="sess-123",
            trace_id="trace-456",
            section="beliefs_active",
            operation="append",
            bytes_delta=256,
            new_size_bytes=1024,
            tier_utilization_pct=25.5,
            total_utilization_pct=15.0,
            pressure="normal",
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "mutation.approved"
        assert parsed["level"] == "INFO"
        assert parsed["bytes_delta"] == 256
        assert parsed["new_size_bytes"] == 1024
        assert parsed["tier_utilization_pct"] == 25.5
        assert parsed["pressure"] == "normal"

    def test_mutation_rejected(self, logger, log_stream):
        """mutation_rejected should log correct fields."""
        logger.mutation_rejected(
            session_id="sess-123",
            trace_id="trace-456",
            section="beliefs_active",
            operation="append",
            reason="section_budget_exceeded",
            available_bytes=128,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "mutation.rejected"
        assert parsed["level"] == "WARNING"
        assert parsed["reason"] == "section_budget_exceeded"
        assert parsed["available_bytes"] == 128


# =============================================================================
# TEST: SessionStateLogger - Eviction Events
# =============================================================================


class TestSessionStateLoggerEviction:
    """Test eviction logging methods."""

    def test_eviction_triggered(self, logger, log_stream):
        """eviction_triggered should log correct fields."""
        logger.eviction_triggered(
            session_id="sess-123",
            trace_id="trace-456",
            tier="warm",
            target_bytes=4096,
            pressure="critical",
            candidates=["telemetry", "beliefs_history"],
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "eviction.triggered"
        assert parsed["level"] == "INFO"
        assert parsed["tier"] == "warm"
        assert parsed["target_bytes"] == 4096
        assert parsed["pressure"] == "critical"
        assert parsed["candidates"] == ["telemetry", "beliefs_history"]

    def test_eviction_completed(self, logger, log_stream):
        """eviction_completed should log correct fields."""
        logger.eviction_completed(
            session_id="sess-123",
            trace_id="trace-456",
            tier="warm",
            sections_evicted=["telemetry"],
            bytes_freed=2048,
            bytes_archived=2000,
            new_pressure="normal",
            duration_ms=15.5,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "eviction.completed"
        assert parsed["bytes_freed"] == 2048
        assert parsed["bytes_archived"] == 2000
        assert parsed["duration_ms"] == 15.5


# =============================================================================
# TEST: SessionStateLogger - Emergency Events
# =============================================================================


class TestSessionStateLoggerEmergency:
    """Test emergency logging methods."""

    def test_emergency_activated_warning(self, logger, log_stream):
        """emergency_activated at warning level should use WARNING."""
        logger.emergency_activated(
            session_id="sess-123",
            trace_id="trace-456",
            level="warning",
            total_size_bytes=88000,
            utilization_pct=91.7,
            writes_blocked=False,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "emergency.activated"
        assert parsed["level"] == "WARNING"
        assert parsed["emergency_level"] == "warning"
        assert parsed["utilization_pct"] == 91.7
        assert parsed["writes_blocked"] is False

    def test_emergency_activated_critical(self, logger, log_stream):
        """emergency_activated at critical level should use ERROR."""
        logger.emergency_activated(
            session_id="sess-123",
            trace_id="trace-456",
            level="critical",
            total_size_bytes=95000,
            utilization_pct=97.0,
            writes_blocked=True,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "emergency.activated"
        assert parsed["level"] == "ERROR"
        assert parsed["emergency_level"] == "critical"
        assert parsed["writes_blocked"] is True

    def test_emergency_resolved(self, logger, log_stream):
        """emergency_resolved should log correct fields."""
        logger.emergency_resolved(
            session_id="sess-123",
            trace_id="trace-456",
            previous_level="critical",
            resolution_method="eviction",
            new_utilization_pct=75.0,
            duration_ms=500.0,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "emergency.resolved"
        assert parsed["previous_level"] == "critical"
        assert parsed["resolution_method"] == "eviction"


# =============================================================================
# TEST: SessionStateLogger - Reconstruction Events
# =============================================================================


class TestSessionStateLoggerReconstruction:
    """Test reconstruction logging methods."""

    def test_reconstruction_started(self, logger, log_stream):
        """reconstruction_started should log correct fields."""
        logger.reconstruction_started(
            session_id="sess-123",
            trace_id="trace-456",
            source="local_cold",
            sections_requested=["control", "beliefs_active", "meta"],
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "reconstruction.started"
        assert parsed["source"] == "local_cold"
        assert "control" in parsed["sections_requested"]

    def test_reconstruction_completed(self, logger, log_stream):
        """reconstruction_completed should log correct fields."""
        logger.reconstruction_completed(
            session_id="sess-123",
            trace_id="trace-456",
            source="local_cold",
            sections_restored=["control", "beliefs_active"],
            duration_ms=25.0,
            bytes_loaded=8192,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "reconstruction.completed"
        assert parsed["duration_ms"] == 25.0
        assert parsed["bytes_loaded"] == 8192


# =============================================================================
# TEST: SessionStateLogger - Lifecycle Events
# =============================================================================


class TestSessionStateLoggerLifecycle:
    """Test lifecycle logging methods."""

    def test_lifecycle_started(self, logger, log_stream):
        """lifecycle_started should log correct fields."""
        logger.lifecycle_started(
            session_id="sess-123",
            trace_id="trace-456",
            hot_sections=8,
            warm_sections=4,
            total_size_bytes=45000,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "lifecycle.started"
        assert parsed["hot_sections"] == 8
        assert parsed["warm_sections"] == 4
        assert parsed["total_size_bytes"] == 45000

    def test_lifecycle_stopped(self, logger, log_stream):
        """lifecycle_stopped should log correct fields."""
        logger.lifecycle_stopped(
            session_id="sess-123",
            trace_id="trace-456",
            duration_ms=60000.0,
            mutation_count=150,
            final_size_bytes=52000,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "lifecycle.stopped"
        assert parsed["duration_ms"] == 60000.0
        assert parsed["mutation_count"] == 150


# =============================================================================
# TEST: SessionStateLogger - Checkpoint Events
# =============================================================================


class TestSessionStateLoggerCheckpoint:
    """Test checkpoint logging methods."""

    def test_checkpoint_created(self, logger, log_stream):
        """checkpoint_created should log correct fields."""
        logger.checkpoint_created(
            session_id="sess-123",
            trace_id="trace-456",
            checkpoint_id="ckpt-789",
            sections_saved=12,
            bytes_saved=48000,
            duration_ms=18.5,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "checkpoint.created"
        assert parsed["checkpoint_id"] == "ckpt-789"
        assert parsed["sections_saved"] == 12
        assert parsed["bytes_saved"] == 48000

    def test_checkpoint_restored(self, logger, log_stream):
        """checkpoint_restored should log correct fields."""
        logger.checkpoint_restored(
            session_id="sess-123",
            trace_id="trace-456",
            checkpoint_id="ckpt-789",
            sections_restored=12,
            bytes_loaded=48000,
            duration_ms=22.0,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "checkpoint.restored"
        assert parsed["checkpoint_id"] == "ckpt-789"


# =============================================================================
# TEST: SessionStateLogger - Migration Events
# =============================================================================


class TestSessionStateLoggerMigration:
    """Test migration logging methods."""

    def test_migration_started(self, logger, log_stream):
        """migration_started should log correct fields."""
        logger.migration_started(
            session_id="sess-123",
            trace_id="trace-456",
            direction="hot_to_warm",
            sections=["beliefs_active"],
            bytes_to_migrate=2048,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "migration.started"
        assert parsed["direction"] == "hot_to_warm"
        assert parsed["sections"] == ["beliefs_active"]

    def test_migration_completed(self, logger, log_stream):
        """migration_completed should log correct fields."""
        logger.migration_completed(
            session_id="sess-123",
            trace_id="trace-456",
            direction="hot_to_warm",
            sections_migrated=["beliefs_active"],
            bytes_migrated=2048,
            duration_ms=5.0,
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "migration.completed"
        assert parsed["bytes_migrated"] == 2048


# =============================================================================
# TEST: SessionStateLogger - Pressure Events
# =============================================================================


class TestSessionStateLoggerPressure:
    """Test pressure logging methods."""

    def test_pressure_changed_to_normal(self, logger, log_stream):
        """pressure_changed to normal should use INFO."""
        logger.pressure_changed(
            session_id="sess-123",
            trace_id="trace-456",
            previous_level="elevated",
            new_level="normal",
            utilization_pct=75.0,
            tier="total",
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["event"] == "pressure.changed"
        assert parsed["level"] == "INFO"
        assert parsed["previous_level"] == "elevated"
        assert parsed["new_level"] == "normal"

    def test_pressure_changed_to_critical(self, logger, log_stream):
        """pressure_changed to critical should use WARNING."""
        logger.pressure_changed(
            session_id="sess-123",
            trace_id="trace-456",
            previous_level="normal",
            new_level="critical",
            utilization_pct=92.0,
            tier="warm",
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["level"] == "WARNING"
        assert parsed["tier"] == "warm"

    def test_pressure_changed_to_emergency(self, logger, log_stream):
        """pressure_changed to emergency should use ERROR."""
        logger.pressure_changed(
            session_id="sess-123",
            trace_id="trace-456",
            previous_level="critical",
            new_level="emergency",
            utilization_pct=96.0,
            tier="total",
        )
        output = log_stream.getvalue()
        parsed = json.loads(output.strip())
        assert parsed["level"] == "ERROR"


# =============================================================================
# TEST: Trace ID Propagation
# =============================================================================


class TestTraceIdPropagation:
    """Test that cognitive_trace_id is included in all log events."""

    def test_trace_id_in_mutation_events(self, logger, log_stream):
        """Trace ID should be in mutation events."""
        logger.mutation_approved(
            session_id="sess-123",
            trace_id="cognitive-trace-abc",
            section="control",
            operation="set",
            bytes_delta=100,
            new_size_bytes=100,
        )
        parsed = json.loads(log_stream.getvalue().strip())
        assert parsed["trace_id"] == "cognitive-trace-abc"

    def test_trace_id_in_eviction_events(self, logger, log_stream):
        """Trace ID should be in eviction events."""
        logger.eviction_triggered(
            session_id="sess-123",
            trace_id="cognitive-trace-xyz",
            tier="warm",
            target_bytes=1000,
            pressure="critical",
            candidates=["telemetry"],
        )
        parsed = json.loads(log_stream.getvalue().strip())
        assert parsed["trace_id"] == "cognitive-trace-xyz"

    def test_trace_id_in_lifecycle_events(self, logger, log_stream):
        """Trace ID should be in lifecycle events."""
        logger.lifecycle_started(
            session_id="sess-123",
            trace_id="cognitive-trace-start",
            hot_sections=8,
            warm_sections=4,
            total_size_bytes=50000,
        )
        parsed = json.loads(log_stream.getvalue().strip())
        assert parsed["trace_id"] == "cognitive-trace-start"

    def test_empty_trace_id_allowed(self, logger, log_stream):
        """Empty trace ID should be allowed."""
        logger.mutation_approved(
            session_id="sess-123",
            trace_id="",
            section="control",
            operation="set",
            bytes_delta=100,
            new_size_bytes=100,
        )
        parsed = json.loads(log_stream.getvalue().strip())
        assert parsed["trace_id"] == ""


# =============================================================================
# TEST: Module-Level Functions
# =============================================================================


class TestModuleFunctions:
    """Test module-level convenience functions."""

    def test_get_default_logger_returns_singleton(self):
        """get_default_logger should return the same instance."""
        logger1 = get_default_logger()
        logger2 = get_default_logger()
        assert logger1 is logger2

    def test_configure_logger_creates_new_instance(self, log_stream):
        """configure_logger should create a new configured instance."""
        logger = configure_logger(
            level=logging.WARNING,
            stream=log_stream,
            use_json_format=True,
        )
        assert isinstance(logger, SessionStateLogger)


# =============================================================================
# TEST: Text Format Logger
# =============================================================================


class TestTextFormatLogger:
    """Test non-JSON text format logging."""

    def test_text_format_produces_readable_output(self, text_logger, log_stream):
        """Text format should produce human-readable output."""
        text_logger.mutation_approved(
            session_id="sess-123",
            trace_id="trace-456",
            section="beliefs_active",
            operation="append",
            bytes_delta=256,
            new_size_bytes=1024,
        )
        output = log_stream.getvalue()
        # Text format should NOT be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(output)
        # But should contain relevant info
        assert "Mutation approved" in output
