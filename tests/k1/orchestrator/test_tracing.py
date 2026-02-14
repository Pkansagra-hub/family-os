from __future__ import annotations

import json
import logging
from uuid import UUID

from k1.orchestrator.tracing import build_trace_log, trace_phase


def test_build_trace_log_includes_required_fields() -> None:
    payload = build_trace_log(
        level=logging.INFO,
        phase="dispatch_high",
        trace_id="trace-1",
        request_id="req-1",
        tier="HIGH",
        step_id="s1",
        wave=2,
        duration_ms=12.5,
        success=True,
    )

    assert payload["component"] == "orchestrator.dispatch_high"
    assert payload["trace_id"] == "trace-1"
    assert payload["request_id"] == "req-1"
    assert payload["tier"] == "HIGH"
    assert payload["step_id"] == "s1"
    assert payload["wave"] == 2
    assert payload["duration_ms"] == 12.5
    assert payload["success"] is True
    assert "timestamp" in payload


def test_build_trace_log_generates_uuid_when_missing_trace() -> None:
    payload = build_trace_log(
        level=logging.INFO,
        phase="route",
        trace_id="",
    )
    UUID(payload["trace_id"])


def test_trace_phase_emits_json_message(caplog) -> None:
    logger = logging.getLogger("tests.orchestrator.tracing")
    caplog.set_level(logging.INFO, logger=logger.name)

    trace_phase(
        logger,
        "aggregate",
        trace_id="trace-agg",
        request_id="req-agg",
        tier="MEDIUM",
        success=True,
    )

    assert caplog.records
    msg = caplog.records[-1].message
    data = json.loads(msg)
    assert data["component"] == "orchestrator.aggregate"
    assert data["trace_id"] == "trace-agg"
    assert data["request_id"] == "req-agg"
    assert data["tier"] == "MEDIUM"
    assert data["success"] is True
