"""
Tests for FabricAuditor.

Issue 2.1.6: Fabric Audit Logging

Coverage:
- Audit event dataclasses
- FabricAuditor logging methods
- Latency calculation
- Structured event format
"""

from __future__ import annotations

import logging
import time
from typing import Any

import pytest

from k0.fabric.audit import (
    AuditEvent,
    FabricAuditor,
    FabricInvokeComplete,
    FabricInvokeError,
    FabricInvokeStart,
    FabricInvokeTimeout,
    get_fabric_auditor,
    reset_fabric_auditor,
)


@pytest.fixture(autouse=True)
def reset_auditor():
    """Reset global auditor before and after each test."""
    reset_fabric_auditor()
    yield
    reset_fabric_auditor()


class TestAuditEventDataclasses:
    """Tests for audit event dataclasses."""

    def test_audit_event_base_structure(self) -> None:
        """AuditEvent has required fields."""
        event = AuditEvent(
            event="test.event",
            timestamp="2025-12-14T10:00:00Z",
            trace_id="trace-123",
            correlation_id="req-456",
        )

        assert event.event == "test.event"
        assert event.timestamp == "2025-12-14T10:00:00Z"
        assert event.trace_id == "trace-123"
        assert event.correlation_id == "req-456"

    def test_fabric_invoke_start_structure(self) -> None:
        """FabricInvokeStart has capability and caller_id."""
        event = FabricInvokeStart(
            event="fabric.invoke.start",
            timestamp="2025-12-14T10:00:00Z",
            trace_id="trace-123",
            correlation_id="req-456",
            capability="score_salience",
            caller_id="P02_WRITE",
        )

        assert event.capability == "score_salience"
        assert event.caller_id == "P02_WRITE"

    def test_fabric_invoke_complete_structure(self) -> None:
        """FabricInvokeComplete has latency and success."""
        event = FabricInvokeComplete(
            event="fabric.invoke.complete",
            timestamp="2025-12-14T10:00:00Z",
            trace_id="trace-123",
            correlation_id="req-456",
            capability="score_salience",
            provider_id="salience.scorer",
            caller_id="P02_WRITE",
            latency_ms=15.5,
            success=True,
        )

        assert event.latency_ms == 15.5
        assert event.success is True

    def test_fabric_invoke_error_structure(self) -> None:
        """FabricInvokeError has error details."""
        event = FabricInvokeError(
            event="fabric.invoke.error",
            timestamp="2025-12-14T10:00:00Z",
            trace_id="trace-123",
            correlation_id="req-456",
            capability="score_salience",
            provider_id="salience.scorer",
            caller_id="P02_WRITE",
            error_type="ValueError",
            error_msg="Invalid input",
            latency_ms=5.0,
            success=False,
        )

        assert event.error_type == "ValueError"
        assert event.error_msg == "Invalid input"
        assert event.success is False

    def test_fabric_invoke_timeout_structure(self) -> None:
        """FabricInvokeTimeout has timeout details."""
        event = FabricInvokeTimeout(
            event="fabric.invoke.timeout",
            timestamp="2025-12-14T10:00:00Z",
            trace_id="trace-123",
            correlation_id="req-456",
            capability="score_salience",
            provider_id="salience.scorer",
            caller_id="P02_WRITE",
            timeout_ms=100.0,
            elapsed_ms=105.5,
            success=False,
        )

        assert event.timeout_ms == 100.0
        assert event.elapsed_ms == 105.5

    def test_events_are_frozen(self) -> None:
        """Audit events are immutable (frozen dataclass)."""
        event = FabricInvokeStart(
            event="fabric.invoke.start",
            timestamp="2025-12-14T10:00:00Z",
            trace_id="trace-123",
            correlation_id="req-456",
            capability="test",
            caller_id="caller",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            event.capability = "modified"  # type: ignore


class TestFabricAuditor:
    """Tests for FabricAuditor class."""

    def test_log_invoke_start_returns_start_time(self) -> None:
        """log_invoke_start returns monotonic start time."""
        auditor = FabricAuditor()

        before = time.monotonic()
        start_time = auditor.log_invoke_start(
            capability="test_cap",
            caller_id="P02",
            trace_id="trace-123",
            correlation_id="req-456",
        )
        after = time.monotonic()

        assert before <= start_time <= after

    def test_log_invoke_complete_logs_event(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_invoke_complete logs structured event."""
        auditor = FabricAuditor()

        with caplog.at_level(logging.INFO, logger="k0.fabric.audit"):
            start_time = time.monotonic()
            auditor.log_invoke_complete(
                capability="score_salience",
                provider_id="salience.scorer",
                caller_id="P02_WRITE",
                start_time=start_time,
                trace_id="trace-123",
                correlation_id="req-456",
            )

        # Should have logged something
        assert len(caplog.records) >= 1

    def test_log_invoke_error_logs_at_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_invoke_error logs at WARNING level."""
        auditor = FabricAuditor()

        with caplog.at_level(logging.WARNING, logger="k0.fabric.audit"):
            start_time = time.monotonic()
            error = ValueError("Test error")
            auditor.log_invoke_error(
                capability="score_salience",
                provider_id="salience.scorer",
                caller_id="P02_WRITE",
                error=error,
                start_time=start_time,
                trace_id="trace-123",
                correlation_id="req-456",
            )

        # Should have logged at warning level
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_log_invoke_timeout_logs_at_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_invoke_timeout logs at WARNING level."""
        auditor = FabricAuditor()

        with caplog.at_level(logging.WARNING, logger="k0.fabric.audit"):
            start_time = time.monotonic()
            auditor.log_invoke_timeout(
                capability="score_salience",
                provider_id="salience.scorer",
                caller_id="P02_WRITE",
                timeout_ms=100.0,
                start_time=start_time,
                trace_id="trace-123",
                correlation_id="req-456",
            )

        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_latency_calculated_correctly(self) -> None:
        """Latency is calculated from monotonic time difference."""
        auditor = FabricAuditor()
        logged_events: list[dict[str, Any]] = []

        # Create a custom logger to capture the event
        class CapturingHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                if hasattr(record, "msg") and isinstance(record.msg, dict):
                    logged_events.append(record.msg)

        custom_logger = logging.getLogger("test.audit")
        custom_logger.addHandler(CapturingHandler())
        custom_logger.setLevel(logging.DEBUG)

        auditor_with_custom = FabricAuditor(logger=custom_logger)

        start_time = time.monotonic()
        # Simulate some delay
        time.sleep(0.01)  # 10ms

        auditor_with_custom.log_invoke_complete(
            capability="test",
            provider_id="provider",
            caller_id="caller",
            start_time=start_time,
            trace_id=None,
            correlation_id=None,
        )

        # Check latency is approximately correct (>= 10ms)
        assert len(logged_events) == 1
        assert logged_events[0]["latency_ms"] >= 10.0


class TestFabricAuditorContextPolicy:
    """Tests for context policy audit logging."""

    def test_log_context_policy_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_context_policy logs at DEBUG level."""
        auditor = FabricAuditor()

        with caplog.at_level(logging.DEBUG, logger="k0.fabric.audit"):
            auditor.log_context_policy(
                capability="score_salience",
                provider_id="salience.scorer",
                policy="inherit",
                caller_caps_count=5,
                effective_caps_count=3,
                trace_id="trace-123",
                correlation_id="req-456",
            )

        assert any(r.levelno == logging.DEBUG for r in caplog.records)


class TestGlobalAuditor:
    """Tests for global auditor singleton."""

    def test_get_auditor_returns_same_instance(self) -> None:
        """get_fabric_auditor returns same instance."""
        auditor1 = get_fabric_auditor()
        auditor2 = get_fabric_auditor()

        assert auditor1 is auditor2

    def test_reset_clears_auditor(self) -> None:
        """reset_fabric_auditor clears singleton."""
        auditor1 = get_fabric_auditor()
        reset_fabric_auditor()
        auditor2 = get_fabric_auditor()

        assert auditor1 is not auditor2


class TestCustomLogger:
    """Tests for custom logger injection."""

    def test_auditor_accepts_custom_logger(self) -> None:
        """FabricAuditor can use custom logger."""
        custom_logger = logging.getLogger("custom.audit.logger")
        auditor = FabricAuditor(logger=custom_logger)

        assert auditor._logger is custom_logger

    def test_auditor_defaults_to_fabric_audit_logger(self) -> None:
        """FabricAuditor defaults to k0.fabric.audit logger."""
        auditor = FabricAuditor()

        assert auditor._logger.name == "k0.fabric.audit"
