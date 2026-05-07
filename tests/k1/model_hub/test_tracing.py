"""Tests for k1.model_hub.tracing -- structured logging [9.1.2]."""

from __future__ import annotations

import json
import logging

import pytest

from k1.model_hub.tracing import (
    ALL_PHASES,
    PHASE_BUDGET_REJECTED,
    PHASE_CACHE_HIT,
    PHASE_DISPATCH_OK,
    PHASE_REQUEST_RECEIVED,
    PHASE_RESPONSE_SENT,
    PHASE_VALIDATE_FAILED,
    build_trace_log,
    emit_trace_log,
    redact_messages,
    safe_labels,
)

# ===========================================================================
# build_trace_log
# ===========================================================================


class TestBuildTraceLog:
    """Structured log payload construction."""

    def test_minimal_payload(self) -> None:
        """Minimal call produces required fields."""
        p = build_trace_log(phase=PHASE_REQUEST_RECEIVED)
        assert p["phase"] == "request.received"
        assert p["component"] == "model_hub"
        assert "timestamp" in p
        assert p["level"] == "INFO"

    def test_all_fields(self) -> None:
        """All optional fields included when provided."""
        p = build_trace_log(
            level=logging.WARNING,
            phase=PHASE_DISPATCH_OK,
            trace_id="t-1",
            request_id="r-1",
            consumer_id="test",
            capability="CHAT",
            model_id="gpt-4",
            provider_id="openai",
            duration_ms=42.5,
            success=True,
            extra={"attempts": 2},
        )
        assert p["trace_id"] == "t-1"
        assert p["request_id"] == "r-1"
        assert p["consumer_id"] == "test"
        assert p["capability"] == "CHAT"
        assert p["model_id"] == "gpt-4"
        assert p["provider_id"] == "openai"
        assert p["duration_ms"] == 42.5
        assert p["success"] is True
        assert p["extra"] == {"attempts": 2}
        assert p["level"] == "WARNING"

    def test_absent_fields_omitted(self) -> None:
        """Fields not provided are absent from payload."""
        p = build_trace_log(phase=PHASE_CACHE_HIT)
        assert "trace_id" not in p
        assert "model_id" not in p
        assert "duration_ms" not in p
        assert "success" not in p

    def test_duration_rounded(self) -> None:
        """Duration is rounded to 2 decimal places."""
        p = build_trace_log(phase=PHASE_DISPATCH_OK, duration_ms=1.23456)
        assert p["duration_ms"] == 1.23

    def test_timestamp_is_iso(self) -> None:
        """Timestamp is ISO 8601 format."""
        p = build_trace_log(phase=PHASE_REQUEST_RECEIVED)
        assert "T" in p["timestamp"]  # ISO format marker

    def test_success_false(self) -> None:
        """Success=False is preserved."""
        p = build_trace_log(phase=PHASE_VALIDATE_FAILED, success=False)
        assert p["success"] is False

    def test_serializable_to_json(self) -> None:
        """Payload can be serialized to JSON."""
        p = build_trace_log(
            phase=PHASE_REQUEST_RECEIVED,
            trace_id="t-1",
            extra={"count": 5},
        )
        s = json.dumps(p)
        assert isinstance(s, str)
        parsed = json.loads(s)
        assert parsed["trace_id"] == "t-1"


# ===========================================================================
# emit_trace_log
# ===========================================================================


class TestEmitTraceLog:
    """Structured log emission."""

    def test_returns_payload(self) -> None:
        """emit_trace_log returns the built payload."""
        p = emit_trace_log(phase=PHASE_RESPONSE_SENT, trace_id="t-emit")
        assert p["phase"] == "response.sent"
        assert p["trace_id"] == "t-emit"

    def test_logs_to_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        """emit_trace_log writes to k1.model_hub logger."""
        with caplog.at_level(logging.INFO, logger="k1.model_hub"):
            emit_trace_log(phase=PHASE_REQUEST_RECEIVED, trace_id="t-log")
        assert any("request.received" in record.message for record in caplog.records)

    def test_warning_level(self, caplog: pytest.LogCaptureFixture) -> None:
        """emit_trace_log respects level parameter."""
        with caplog.at_level(logging.WARNING, logger="k1.model_hub"):
            emit_trace_log(
                level=logging.WARNING,
                phase=PHASE_BUDGET_REJECTED,
                trace_id="t-warn",
            )
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_emitted_payload_is_valid_json(self, caplog: pytest.LogCaptureFixture) -> None:
        """Emitted message is valid JSON."""
        with caplog.at_level(logging.INFO, logger="k1.model_hub"):
            emit_trace_log(phase=PHASE_DISPATCH_OK, trace_id="t-json")
        for record in caplog.records:
            if "dispatch.ok" in record.message:
                parsed = json.loads(record.message)
                assert parsed["phase"] == "dispatch.ok"
                break
        else:
            pytest.fail("Expected log record not found")


# ===========================================================================
# Privacy: redact_messages
# ===========================================================================


class TestRedactMessages:
    """Privacy enforcement for message content."""

    def test_content_redacted(self) -> None:
        """Message content replaced with <REDACTED>."""
        msgs = [{"role": "user", "content": "My secret prompt"}]
        safe = redact_messages(msgs)
        assert safe[0]["content"] == "<REDACTED>"
        assert safe[0]["role"] == "user"

    def test_multiple_messages(self) -> None:
        """All messages redacted."""
        msgs = [
            {"role": "system", "content": "You are an AI"},
            {"role": "user", "content": "Tell me secrets"},
            {"role": "assistant", "content": "I can help"},
        ]
        safe = redact_messages(msgs)
        assert len(safe) == 3
        assert all(m["content"] == "<REDACTED>" for m in safe)

    def test_empty_messages(self) -> None:
        """Empty list returns empty list."""
        assert redact_messages([]) == []

    def test_missing_role(self) -> None:
        """Missing role defaults to 'unknown'."""
        msgs = [{"content": "test"}]
        safe = redact_messages(msgs)
        assert safe[0]["role"] == "unknown"


# ===========================================================================
# Privacy: safe_labels
# ===========================================================================


class TestSafeLabels:
    """Secret redaction in label dicts."""

    def test_normal_labels_preserved(self) -> None:
        """Non-secret labels are preserved."""
        labels = {"provider": "openai", "model": "gpt-4"}
        safe = safe_labels(labels)
        assert safe == {"provider": "openai", "model": "gpt-4"}

    def test_api_key_redacted(self) -> None:
        """api_key values are redacted."""
        labels = {"api_key": "sk-abc123", "provider": "openai"}
        safe = safe_labels(labels)
        assert safe["api_key"] == "<REDACTED>"
        assert safe["provider"] == "openai"

    def test_multiple_secret_keys(self) -> None:
        """All secret-like keys are redacted."""
        labels = {
            "key": "abc",
            "token": "xyz",
            "secret": "123",
            "password": "hunter2",
            "credential": "cred-val",
            "provider": "safe",
        }
        safe = safe_labels(labels)
        assert safe["key"] == "<REDACTED>"
        assert safe["token"] == "<REDACTED>"
        assert safe["secret"] == "<REDACTED>"
        assert safe["password"] == "<REDACTED>"
        assert safe["credential"] == "<REDACTED>"
        assert safe["provider"] == "safe"

    def test_case_insensitive(self) -> None:
        """Secret detection is case-insensitive."""
        labels = {"API_KEY": "sk-abc", "Token": "xyz"}
        safe = safe_labels(labels)
        assert safe["API_KEY"] == "<REDACTED>"
        assert safe["Token"] == "<REDACTED>"

    def test_empty_labels(self) -> None:
        """Empty dict returns empty dict."""
        assert safe_labels({}) == {}


# ===========================================================================
# Phase constants
# ===========================================================================


class TestPhaseConstants:
    """Verify phase constant completeness."""

    def test_all_phases_count(self) -> None:
        """ALL_PHASES contains 34 phases."""
        assert len(ALL_PHASES) == 34

    def test_all_phases_unique(self) -> None:
        """No duplicate phase names."""
        assert len(set(ALL_PHASES)) == len(ALL_PHASES)

    def test_all_phases_are_strings(self) -> None:
        """All phases are non-empty strings."""
        assert all(isinstance(p, str) and len(p) > 0 for p in ALL_PHASES)

    def test_pipeline_phases_present(self) -> None:
        """Core pipeline phases exist."""
        expected = [
            "request.received",
            "validate.ok",
            "budget.check",
            "route.start",
            "select.model",
            "cache.hit",
            "normalize.request",
            "dispatch.start",
            "dispatch.ok",
            "response.sent",
        ]
        for phase in expected:
            assert phase in ALL_PHASES

    def test_lifecycle_phases_present(self) -> None:
        """Lifecycle phases exist."""
        expected = [
            "lifecycle.init",
            "lifecycle.health_check",
            "lifecycle.ready",
            "lifecycle.degraded",
            "lifecycle.shutdown",
        ]
        for phase in expected:
            assert phase in ALL_PHASES

    def test_circuit_phases_present(self) -> None:
        """Circuit breaker phases exist."""
        assert "circuit.open" in ALL_PHASES
        assert "circuit.close" in ALL_PHASES
