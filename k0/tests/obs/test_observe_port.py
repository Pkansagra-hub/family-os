from __future__ import annotations

import json
import logging
from io import StringIO

from fastapi.testclient import TestClient
from ward import test  # type: ignore[attr-defined]

from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.obs.logging import configure_structured_logging
from k0.ports import observe


@test("obs.emit stores forwarded metrics snapshot and exposes it via /metrics")
def _() -> None:
    app = create_app(KernelSettings.default())

    payload = {
        "kind": "metrics",
        "body": {
            "snapshot": "k1_forwarded_metric 42\n",
            "captured_at": "2025-01-02T03:04:05Z",
            "source": "k1_bridge_tests",
        },
    }
    headers = {"X-Cognitive-Trace-Id": "trace-metrics-123"}

    with TestClient(app) as client:
        response = client.post("/k0/obs.emit", json=payload, headers=headers)
        assert response.status_code == 204

        rendered = app.state.forwarded_metrics.render()
        assert "k1_forwarded_metric 42" in rendered
        assert "trace_id=trace-metrics-123" in rendered
        assert "captured_at=2025-01-02T03:04:05Z" in rendered

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200
        body = metrics_response.text
        assert "# forwarded_metrics" in body
        assert "k1_forwarded_metric 42" in body


@test("obs.emit replays forwarded log entries through structured logging")
def _() -> None:
    stream = StringIO()
    configure_structured_logging(stream=stream, level="INFO", force=True)

    app = create_app(KernelSettings.default())

    payload = {
        "kind": "logs",
        "body": {
            "entries": [
                {
                    "event": "agent.forwarded",
                    "message": "Bridge log event",
                    "level": "INFO",
                    "cognitive_trace_id": "forwarded-trace",
                    "band": "GREEN",
                }
            ]
        },
    }

    original_logger = observe.logger
    observe.logger = logging.getLogger("k0.observe.test.forward")

    try:
        with TestClient(app) as client:
            response = client.post(
                "/k0/obs.emit",
                json=payload,
                headers={"X-Cognitive-Trace-Id": "trace-logs-001"},
            )
            assert response.status_code == 204
    finally:
        observe.logger = original_logger

    records = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    forwarded = next(record for record in records if record.get("message") == "agent.forwarded")
    context = forwarded.get("context", {})

    assert context.get("forwarded_message") == "Bridge log event"
    assert forwarded.get("cognitive_trace_id") == "forwarded-trace"
    assert context.get("forwarded") is True


@test("obs.emit accepts feedback envelopes")
def _() -> None:
    app = create_app(KernelSettings.default())

    payload = {
        "kind": "feedback",
        "body": {
            "feedback_id": "550e8400-e29b-41d4-a716-446655440000",
            "pipeline_id": "P02",
            "signal_class": "CORRECTION",
            "signal_subtype": "user_correction",
            "tenant_id": "tenant-tests",
            "space_id": "space-tests",
            "correlation": {"session_id": "sess-1", "event_ids": ["evt-1"]},
            "payload": {"extraction_quality": "good"},
        },
    }

    with TestClient(app) as client:
        response = client.post(
            "/k0/obs.emit",
            json=payload,
            headers={"X-Cognitive-Trace-Id": "trace-feedback-001"},
        )
        assert response.status_code == 204


@test("obs.emit rejects feedback envelopes missing tenant/space")
def _() -> None:
    app = create_app(KernelSettings.default())

    payload = {
        "kind": "feedback",
        "body": {
            "feedback_id": "550e8400-e29b-41d4-a716-446655440001",
            "pipeline_id": "P02",
            "signal_class": "CORRECTION",
            "signal_subtype": "user_correction",
            "correlation": {"session_id": "sess-1", "event_ids": ["evt-1"]},
            "payload": {"extraction_quality": "good"},
        },
    }

    with TestClient(app) as client:
        response = client.post(
            "/k0/obs.emit",
            json=payload,
            headers={"X-Cognitive-Trace-Id": "trace-feedback-002"},
        )
        assert response.status_code == 400
