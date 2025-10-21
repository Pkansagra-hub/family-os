from __future__ import annotations

from typing import Any, Dict

from fastapi import Request
from ward import test  # type: ignore[attr-defined]

from k0.kernel.admission import consume_admission_records, record_admission_decision
from k0.policy.pep_syscall import Obligation, PolicyDecision
from k0.storage.receipts import Receipt


def _build_request() -> Request:
    scope: Dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "headers": [],
        "path": "/admission",
        "raw_path": b"/admission",
        "query_string": b"",
        "root_path": "",
        "scheme": "http",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    async def _receive() -> dict[str, Any]:
        return {"type": "http.request"}

    return Request(scope, receive=_receive)


@test("admission records capture decision context and clear after consumption")
def _() -> None:
    request = _build_request()
    obligation = Obligation(name="AUDIT_TRAIL", details={"channel": "primary"})
    decision = PolicyDecision(admit=True, obligations=(obligation,))
    envelope = {
        "tenant_id": "tenant-alpha",
        "space_id": "space-omega",
        "band": "GREEN",
        "topic": "memory.topic",
    }
    receipt = Receipt(
        receipt_id="rct-123",
        idem_key="idem-123",
        wal_pos=42,
        commit_ts="2025-01-01T00:00:00Z",
        tenant_id="tenant-alpha",
        space_id="space-omega",
        device_id="device-42",
        mls_group_id="group-7",
        key_version="v1",
        device_sig="sig-abc",
    )

    record_admission_decision(
        request,
        decision=decision,
        envelope=envelope,
        receipt=receipt,
        port="command",
    )

    envelope["tenant_id"] = "mutated"  # ensure a defensive copy was stored

    records = consume_admission_records(request)
    assert len(records) == 1
    record = records[0]
    assert record.decision is decision
    assert record.envelope["tenant_id"] == "tenant-alpha"
    assert record.envelope["space_id"] == "space-omega"
    assert record.envelope["band"] == "GREEN"
    assert record.receipt is receipt
    assert record.port == "command"

    assert consume_admission_records(request) == []
    assert consume_admission_records(request) == []
    assert consume_admission_records(request) == []
    assert consume_admission_records(request) == []
    assert consume_admission_records(request) == []
    assert consume_admission_records(request) == []
