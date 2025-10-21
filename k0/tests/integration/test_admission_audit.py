from __future__ import annotations

from typing import Any, Dict, List, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from ward import test  # type: ignore[attr-defined]

from k0.kernel.admission import record_admission_decision
from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.policy.pep_syscall import Obligation, PolicyDecision
from k0.storage.receipts import Receipt


class RecordingReceiptStore:
    def __init__(self) -> None:
        self.saved: List[Receipt] = []

    def save(self, receipt: Receipt, *, connection: object | None = None) -> None:
        self.saved.append(receipt)


class RecordingObservabilityEmitter:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, event: Dict[str, Any]) -> None:
        self.events.append(dict(event))


class RecordingMetricsExporter:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, float, Dict[str, str]]] = []

    def emit(self, metric_name: str, value: float = 1.0, **labels: str) -> None:
        self.calls.append((metric_name, value, dict(labels)))


@test("admission middleware persists receipts and emits telemetry signals")
def _() -> None:
    settings = KernelSettings.load(overrides={"telemetry": {"otlp_endpoint": None}})
    app = create_app(settings=settings)

    receipt_store = RecordingReceiptStore()
    observability_emitter = RecordingObservabilityEmitter()
    metrics_exporter = RecordingMetricsExporter()
    app.state.receipt_store = receipt_store
    app.state.observability_emitter = observability_emitter
    app.state.metrics_exporter = metrics_exporter

    @app.get("/admit")
    async def admit_endpoint(request: Request) -> JSONResponse:
        obligation = Obligation(name="AUDIT_TRAIL", details={"channel": "primary"})
        decision = PolicyDecision(admit=True, obligations=(obligation,))
        envelope: Dict[str, Any] = {
            "tenant_id": "tenant-alpha",
            "space_id": "space-omega",
            "band": "GREEN",
            "topic": "memory.topic",
        }
        receipt = Receipt(
            receipt_id="receipt-001",
            idem_key="idem-001",
            wal_pos=77,
            commit_ts="2025-06-01T12:00:00Z",
            tenant_id="tenant-alpha",
            space_id="space-omega",
            device_id="device-42",
            mls_group_id="mls-7",
            key_version="v1",
            device_sig="sig-abc",
        )
        record_admission_decision(
            request,
            decision=decision,
            envelope=envelope,
            receipt=receipt,
            port="observe",
        )
        envelope["tenant_id"] = (
            "mutated"  # ensure defensive copy for middleware processing
        )
        return JSONResponse({"status": "ok"})

    _ = admit_endpoint

    client = TestClient(app)
    response = client.get("/admit", headers={"X-Cognitive-Trace-Id": "trace-fixed"})
    assert response.status_code == 200

    assert len(receipt_store.saved) == 1
    saved_receipt = receipt_store.saved[0]
    assert saved_receipt.receipt_id == "receipt-001"

    assert len(observability_emitter.events) == 1
    event = observability_emitter.events[0]
    assert event["trace_id"] == "trace-fixed"
    assert event["decision"] == "allow"
    assert event["obligations"] == ["AUDIT_TRAIL"]
    assert event["obligation_details"] == [{"channel": "primary"}]
    assert event["tenant_id"] == "tenant-alpha"
    assert event["space_id"] == "space-omega"
    assert event["band"] == "GREEN"
    assert event["receipt_id"] == "receipt-001"
    assert event["wal_pos"] == 77
    assert "error" not in event

    assert len(metrics_exporter.calls) == 1
    metric_name, value, labels = metrics_exporter.calls[0]
    assert metric_name == "admission_decisions_total"
    assert value == 1.0
    assert labels == {"decision": "allow", "port": "observe"}


@test("admission middleware captures errors when downstream handlers fail")
def _() -> None:
    settings = KernelSettings.load(overrides={"telemetry": {"otlp_endpoint": None}})
    app = create_app(settings=settings)

    receipt_store = RecordingReceiptStore()
    observability_emitter = RecordingObservabilityEmitter()
    metrics_exporter = RecordingMetricsExporter()
    app.state.receipt_store = receipt_store
    app.state.observability_emitter = observability_emitter
    app.state.metrics_exporter = metrics_exporter

    @app.get("/deny")
    async def deny_endpoint(request: Request) -> JSONResponse:
        decision = PolicyDecision(
            admit=False, obligations=(), deny_reason="ROLE_FORBIDDEN"
        )
        envelope: Dict[str, Any] = {
            "tenant_id": "tenant-beta",
            "space_id": "space-beta",
            "band": "AMBER",
        }
        record_admission_decision(
            request,
            decision=decision,
            envelope=envelope,
            receipt=None,
            port="command",
        )
        raise RuntimeError("boom")

    _ = deny_endpoint

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/deny")
    assert response.status_code == 500

    assert receipt_store.saved == []
    assert len(observability_emitter.events) == 1
    event = observability_emitter.events[0]
    assert event["decision"] == "deny"
    assert event["deny_reason"] == "ROLE_FORBIDDEN"
    assert event["obligations"] == []
    assert "receipt_id" not in event
    assert event["port"] == "command"
    assert event["error"] == "RuntimeError"
    trace_id = event["trace_id"]
    assert len(trace_id) == 32
    int(trace_id, 16)

    assert len(metrics_exporter.calls) == 1
    metric_name, value, labels = metrics_exporter.calls[0]
    assert metric_name == "admission_decisions_total"
    assert value == 1.0
    assert labels == {"decision": "deny", "port": "command"}
