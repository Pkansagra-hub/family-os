from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from jsonschema import Draft7Validator, FormatChecker, ValidationError
from ward import test  # type: ignore[import]

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "k0" / "contracts" / "jsonschema"
FORMAT_CHECKER = FormatChecker()

SCHEMA_EXAMPLES: Dict[str, Any] = {
    "envelope.schema.json": {
        "cognitive_trace_id": "6d1f861e-6c30-4ba2-bc34-2dcaad4a0c89",
        "tenant_id": "tenant-main",
        "space_id": "space-main",
        "topic": "memory.delta",
        "schema_uri": "https://schemas.family.local/memory/delta.json",
        "schema_version": "1.0.0",
        "actor": "actor-1",
        "device_id": "device-123",
        "band": "GREEN",
        "policy_version": "2024.01",
        "ts": "2024-01-01T12:00:00Z",
        "sig": "base64sig==",
        "payload_sha256": "0" * 64,
        "idem_key": "idem-1",
        "body": {"event": "memory.write", "payload": {"value": 42}},
    },
    "error.schema.json": {
        "error": {
            "code": "QOS_BUDGET_EXHAUSTED",
            "component": "kernel.qos",
            "reason": "LIMIT_EXCEEDED",
            "trace_id": "8bdeb2da-e3d1-46f5-81c6-6b9639a923d3",
            "hint": "Increase latency budget",
            "budgets": {"fanout": 0, "top_k": 8},
            "details": {"cap": "fanout"},
        }
    },
    "infra.snapshot.event.json": {
        "type": "BEGIN",
        "watermark": 1024,
        "snapshot_id": "snapshot-20240101",
    },
    "offset.cursor.schema.json": {
        "subscriber_id": "client-123",
        "topic": "memory.delta",
        "space_id": "space-main",
        "tenant_id": "tenant-main",
        "offset": 128,
        "ts": "2024-01-02T12:00:00Z",
    },
    "pep.schema.json": {
        "band": "AMBER",
        "abac": {"tenant_id": "tenant-main", "roles": ["coordinator"]},
        "caps": {"fanout": {"limit": 12}, "throughput": {"pps": 200}},
        "decision": "ALLOW",
        "obligations": ["log-event"],
    },
    "query.recall.request.json": {
        "selectors": [{"kind": "episodic", "target": "memory"}],
        "space_id": "space-main",
        "fanout_hints": {"max_results": 25},
        "qos_hints": {"band": "GREEN"},
        "max_latency_ms": 250,
    },
    "query.recall.response.json": {
        "bundle": {"items": []},
        "trace": {"query_id": "abcd-1234"},
        "budgets": {"fanout": 1, "time_slice": 200, "policy": "baseline"},
    },
    "receipt.schema.json": {
        "receipt_id": "5eb83486-df9d-4d5a-912f-1a5da8c3a609",
        "idem_key": "idem-1",
        "wal_pos": 4096,
        "commit_ts": "2024-01-03T12:00:00Z",
        "payload_sha256": "f" * 64,
        "mls_group_id": "mls-group-01",
        "key_version": "v1",
        "device_sig": "device-sig",
        "obligations": ["notify-tenant"],
    },
    "sse.ack.request.json": {
        "subscriber_id": "client-123",
        "topic": "memory.delta",
        "space_id": "space-main",
        "tenant_id": "tenant-main",
        "offset": 512,
        "ack_ts": "2024-01-04T12:00:00Z",
    },
    "driver.handshake.request.json": {
        "alias": "st_vector",
        "transport": "http",
        "endpoint": "https://indexer.family.local/apply",
        "capabilities": ["apply"],
        "metadata": {"version": "1.0.0"},
    },
    "driver.handshake.response.json": {
        "session_id": "b5bbdc9d686f4c9e9a3cb652c0f80a98",
        "alias": "st_vector",
        "driver_module": "faiss",
        "transport": "http",
        "endpoint": "https://indexer.family.local/apply",
        "lease_seconds": 300,
        "issued_at": "2025-09-30T12:00:00Z",
        "expires_at": "2025-09-30T12:05:00Z",
        "capabilities": ["apply"],
        "metadata": {"version": "1.0.0"},
    },
}


def load_schema(schema_path: Path) -> Dict[str, Any]:
    return json.loads(schema_path.read_text())


@test("All JSON schemas pass Draft7 validation")
def schema_contracts_are_well_formed() -> None:
    for schema_path in sorted(SCHEMA_DIR.glob("*.json"), key=lambda path: path.name):
        schema = load_schema(schema_path)
        Draft7Validator.check_schema(schema)


@test("Example payloads satisfy JSON schemas")
def schema_examples_match() -> None:
    for schema_path in sorted(SCHEMA_DIR.glob("*.json"), key=lambda path: path.name):
        schema = load_schema(schema_path)
        example = SCHEMA_EXAMPLES.get(schema_path.name)
        assert example is not None, f"Missing example payload for {schema_path.name}"
        validator = Draft7Validator(schema, format_checker=FORMAT_CHECKER)
        try:
            validator.validate(example)  # type: ignore[arg-type]
        except ValidationError as exc:
            raise AssertionError(
                f"Example payload failed validation for {schema_path.name}: {exc.message}"
            ) from exc
