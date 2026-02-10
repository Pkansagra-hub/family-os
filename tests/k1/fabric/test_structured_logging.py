"""
Tests for Fabric Structured Logging
==================================

EPIC: 7.3 Tracing & Logging
ISSUE: 7.3.2

Tests:
1. LogEventType enum values
2. StructuredLogRecord serialization
3. FabricJsonFormatter output
4. FabricLogger phase methods
5. Trace ID propagation in logs
"""

import io
import json
import logging
from datetime import datetime

import pytest

from k1.fabric.logging import (
    FabricJsonFormatter,
    FabricLogger,
    LogEventType,
    StructuredLogRecord,
    configure_logger,
    get_default_logger,
)


@pytest.fixture
def log_stream():
    """Provide a StringIO stream for capturing log output."""
    return io.StringIO()


@pytest.fixture
def logger(log_stream):
    """Provide a FabricLogger with captured output."""
    import uuid

    logger_name = f"test.fabric.{uuid.uuid4().hex[:8]}"
    flogger = FabricLogger(
        name=logger_name,
        level=logging.DEBUG,
        stream=log_stream,
        use_json_format=True,
    )
    flogger._logger.propagate = False
    return flogger


class TestLogEventType:
    """Test LogEventType enum values."""

    def test_event_types_exist(self):
        assert LogEventType.RESOLVE.value == "resolve"
        assert LogEventType.POLICY_CHECK.value == "policy_check"
        assert LogEventType.CONTEXT_BUILD.value == "context_build"
        assert LogEventType.EXECUTE.value == "execute"
        assert LogEventType.RESULT_RETURN.value == "result_return"

    def test_total_event_count(self):
        assert len(LogEventType) == 5


class TestStructuredLogRecord:
    """Test StructuredLogRecord serialization."""

    def test_defaults(self):
        record = StructuredLogRecord(event="resolve")
        assert record.event == "resolve"
        assert record.level == "INFO"
        assert record.module == "fabric"
        assert record.timestamp_iso

    def test_to_dict_flattens_context(self):
        record = StructuredLogRecord(
            event="execute",
            context={"extra": "value"},
        )
        data = record.to_dict()
        assert data["extra"] == "value"

    def test_to_json_valid(self):
        record = StructuredLogRecord(
            event="result_return",
            trace_id="trace-123",
            request_id="req-456",
            context={"key": "value"},
        )
        parsed = json.loads(record.to_json())
        assert parsed["event"] == "result_return"
        assert parsed["trace_id"] == "trace-123"
        assert parsed["request_id"] == "req-456"
        assert parsed["key"] == "value"

    def test_timestamp_iso(self):
        record = StructuredLogRecord(event="resolve")
        parsed = datetime.fromisoformat(record.timestamp_iso.replace("Z", "+00:00"))
        assert parsed is not None


class TestFabricJsonFormatter:
    """Test JSON formatter output."""

    def test_format_valid_json(self):
        formatter = FabricJsonFormatter()
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
        assert parsed["module"] == "fabric"

    def test_format_structured_fields(self):
        formatter = FabricJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Structured",
            args=(),
            exc_info=None,
        )
        record.structured = {
            "event": "execute",
            "component": "fabric.execute",
            "trace_id": "trace-xyz",
            "request_id": "req-abc",
            "capability_name": "tool.execute.sample",
            "provider_id": "provider-1",
            "duration_ms": 12.5,
            "success": True,
            "context": {"extra": "value"},
        }
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["event"] == "execute"
        assert parsed["trace_id"] == "trace-xyz"
        assert parsed["request_id"] == "req-abc"
        assert parsed["capability_name"] == "tool.execute.sample"
        assert parsed["provider_id"] == "provider-1"
        assert parsed["duration_ms"] == 12.5
        assert parsed["success"] is True
        assert parsed["extra"] == "value"


class TestFabricLogger:
    """Test FabricLogger phase methods."""

    def test_resolve_log(self, logger, log_stream):
        logger.resolve(
            trace_id="trace-1",
            request_id="req-1",
            capability_name="tool.execute.sample",
            duration_ms=5.0,
            success=True,
        )
        parsed = json.loads(log_stream.getvalue().strip())
        assert parsed["event"] == "resolve"
        assert parsed["trace_id"] == "trace-1"
        assert parsed["request_id"] == "req-1"
        assert parsed["duration_ms"] == 5.0
        assert parsed["success"] is True

    def test_execute_log_failure(self, logger, log_stream):
        logger.execute(
            trace_id="trace-2",
            request_id="req-2",
            capability_name="tool.execute.sample",
            provider_id="provider-1",
            duration_ms=12.0,
            success=False,
        )
        parsed = json.loads(log_stream.getvalue().strip())
        assert parsed["event"] == "execute"
        assert parsed["provider_id"] == "provider-1"
        assert parsed["success"] is False

    def test_result_return_includes_trace_id(self, logger, log_stream):
        logger.result_return(
            trace_id="cognitive-trace-abc",
            request_id="req-3",
            capability_name="tool.execute.sample",
            duration_ms=20.0,
            success=True,
        )
        parsed = json.loads(log_stream.getvalue().strip())
        assert parsed["trace_id"] == "cognitive-trace-abc"


class TestModuleFunctions:
    """Test module-level convenience functions."""

    def test_get_default_logger_singleton(self):
        logger1 = get_default_logger()
        logger2 = get_default_logger()
        assert logger1 is logger2

    def test_configure_logger(self, log_stream):
        logger = configure_logger(level=logging.WARNING, stream=log_stream, use_json_format=True)
        assert isinstance(logger, FabricLogger)
