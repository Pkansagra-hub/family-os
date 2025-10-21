from __future__ import annotations

import json
import uuid
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, Iterator, cast

from fastapi.testclient import TestClient
from nacl.signing import SigningKey
from ward import fixture, test  # type: ignore[attr-defined]

from k0.gate.schema_registry import SchemaRecord
from k0.idem import derive_idem_key
from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.kernel.dependencies import qos_context_dependency
from k0.outbox import compute_fingerprint
from k0.ports.command import DEFAULT_OUTBOX_DRIVER, DEFAULT_OUTBOX_OPERATION
from k0.qos import QoSContext, Scheduler, SchedulerProfile
from k0.security import canonical_envelope, canonical_json, hash_payload
from k0.security.crypto import encode_base64url
from k0.storage.provisioning import DeviceKey, ProvisionedDevice
from k0.uow.connection_pool import connection_scope, shutdown_pool

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_SQL_PATH = REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql"


class CommandTestEnv(SimpleNamespace):
    client: TestClient
    signing_key: SigningKey
    schema_uri: str
    schema_version: str
    tenant_id: str
    space_id: str
    device_id: str
    app: Any


@fixture
def command_env() -> Iterator[CommandTestEnv]:
    tmp_dir = TemporaryDirectory()
    db_path = Path(tmp_dir.name) / "kernel.sqlite3"

    settings = KernelSettings.load(
        overrides={
            "database": {"path": str(db_path)},
            "telemetry": {"otlp_endpoint": None},
        }
    )
    app = create_app(settings=settings)

    storage_sql = STORAGE_SQL_PATH.read_text(encoding="utf-8")
    with connection_scope() as conn:
        conn.executescript(storage_sql)
        conn.commit()

    schema_uri = "schema://memory.delta"
    schema_version = "1.0"
    schema_sha = sha256(f"{schema_uri}@{schema_version}".encode("utf-8")).hexdigest()

    signing_key = SigningKey.generate()
    verify_key_b64 = encode_base64url(signing_key.verify_key.encode())
    device = ProvisionedDevice(
        device_id="device-test-1",
        tenant_id="tenant-alpha",
        space_id="space-main",
        mls_group_id="mls-group-1",
        provisioned_ts="2025-07-01T00:00:00Z",
    )
    device_key = DeviceKey(
        device_id="device-test-1",
        key_version="1",
        verify_key=verify_key_b64,
        key_state="ACTIVE",
        registered_ts="2025-07-01T00:00:00Z",
        activated_ts="2025-07-01T00:00:00Z",
    )

    with connection_scope() as conn:
        app.state.provisioning_ledger.register(device, connection=conn)
        app.state.provisioning_ledger.add_key(device_key, connection=conn)
        app.state.schema_registry.upsert(
            SchemaRecord(
                uri=schema_uri,
                version=schema_version,
                sha256=schema_sha,
                status="ACTIVE",
            ),
            connection=conn,
        )
        conn.commit()

    app.state.observability_emitter.clear()

    with TestClient(app) as client:
        yield CommandTestEnv(
            client=client,
            signing_key=signing_key,
            schema_uri=schema_uri,
            schema_version=schema_version,
            tenant_id=device.tenant_id,
            space_id=device.space_id,
            device_id=device.device_id,
            app=app,
        )

    shutdown_pool()
    tmp_dir.cleanup()


def _build_envelope(
    env: CommandTestEnv,
    *,
    trace_id: str | None = None,
) -> tuple[dict[str, Any], bytes, str]:
    trace_uuid = uuid.UUID(trace_id) if trace_id is not None else uuid.uuid4()
    trace = str(trace_uuid)
    body: dict[str, Any] = {
        "operation": "UPSERT",
        "payload": {"value": 42},
    }
    body_json = canonical_json(body)
    body_bytes = body_json.encode("utf-8")
    payload_hash = hash_payload(body_bytes)
    assert payload_hash is not None

    envelope: dict[str, Any] = {
        "cognitive_trace_id": trace,
        "tenant_id": env.tenant_id,
        "space_id": env.space_id,
        "topic": "memory.delta",
        "schema_uri": env.schema_uri,
        "schema_version": env.schema_version,
        "actor": "actor-123",
        "device_id": env.device_id,
        "band": "GREEN",
        "policy_version": "2025-09-28",
        "ts": "2025-08-01T12:00:00Z",
        "payload_sha256": payload_hash,
        "policy": {
            "abac": {
                "roles": ["coordinator"],
            }
        },
    }

    message = canonical_envelope(envelope)
    signature = encode_base64url(env.signing_key.sign(message).signature)
    request_payload = dict(envelope)
    request_payload["sig"] = signature
    request_payload["body"] = body
    return request_payload, body_bytes, payload_hash


@test("command.submit commits WAL, receipt, outbox, and idempotency ledger entries")
def _(command_env_obj: Any = command_env) -> None:
    env = cast(CommandTestEnv, command_env_obj)
    envelope, body_bytes, payload_hash = _build_envelope(env)
    expected_idem_key = derive_idem_key(envelope, payload_hash=payload_hash)

    response = env.client.post("/k0/command.submit", json=envelope)
    assert response.status_code == 200
    payload = response.json()

    assert uuid.UUID(payload["receipt_id"])  # validates format
    assert payload["idem_key"] == expected_idem_key
    offsets_raw = payload["offsets"]
    assert isinstance(offsets_raw, dict)
    offsets = cast(dict[str, int], offsets_raw)
    assert set(offsets.keys()) == {"memory.delta"}
    wal_pos = offsets["memory.delta"]
    assert isinstance(wal_pos, int)

    commit_ts = payload["commit_ts"]

    with connection_scope() as conn:
        wal_rows = conn.execute("SELECT * FROM st_wal").fetchall()
        assert len(wal_rows) == 1
        wal_row = wal_rows[0]
        assert wal_row["pos"] == wal_pos
        assert wal_row["tenant_id"] == env.tenant_id
        assert wal_row["space_id"] == env.space_id
        assert wal_row["payload_sha256"] == payload_hash
        assert wal_row["body"] == body_bytes
        stored_envelope = json.loads(wal_row["envelope_json"])
        assert stored_envelope["idem_key"] == expected_idem_key

        outbox_rows = conn.execute("SELECT * FROM st_outbox").fetchall()
        assert len(outbox_rows) == 1
        outbox_row = outbox_rows[0]
        assert outbox_row["wal_pos"] == wal_pos
        outbox_payload_bytes = outbox_row["payload"]
        assert outbox_row["fingerprint"] == compute_fingerprint(
            DEFAULT_OUTBOX_DRIVER,
            DEFAULT_OUTBOX_OPERATION,
            outbox_payload_bytes,
        )
        outbox_payload = json.loads(outbox_payload_bytes.decode("utf-8"))
        assert outbox_payload["wal_pos"] == wal_pos
        assert outbox_payload["idem_key"] == expected_idem_key

        receipts_rows = conn.execute("SELECT * FROM st_receipts").fetchall()
        assert len(receipts_rows) == 1
        receipt_row = receipts_rows[0]
        assert receipt_row["receipt_id"] == payload["receipt_id"]
        assert receipt_row["idem_key"] == expected_idem_key

        ledger_rows = conn.execute("SELECT * FROM idem_ledger").fetchall()
        assert len(ledger_rows) == 1
        ledger_row = ledger_rows[0]
        assert ledger_row["idem_key"] == expected_idem_key
        assert ledger_row["receipt_id"] == payload["receipt_id"]
        assert ledger_row["first_seen_ts"] == commit_ts

    events = env.app.state.observability_emitter.snapshot()
    assert any(
        event.get("event") == "receipt_issued"
        and event.get("idem_key") == expected_idem_key
        for event in events
    )

    metrics_text = env.app.state.metrics_exporter.latest().decode("utf-8")
    assert 'k0_kernel_receipt_issue_total{outcome="success"} 1.0' in metrics_text
    assert (
        'k0_kernel_admission_decisions_total{decision="allow",port="command"} 1.0'
        in metrics_text
    )

    registry = env.app.state.metrics_exporter.registry
    latency_count = registry.get_sample_value(
        "k0_kernel_http_request_latency_seconds_count",
        {
            "route": "/k0/command.submit",
            "method": "POST",
            "operation": "command",
        },
    )
    assert latency_count == 1.0
    availability_counter = registry.get_sample_value(
        "k0_kernel_http_requests_total",
        {
            "route": "/k0/command.submit",
            "method": "POST",
            "status": "200",
            "outcome": "success",
            "operation": "command",
        },
    )
    assert availability_counter == 1.0


@test("command.submit rejects duplicate idem keys with 409 conflict")
def _(command_env_obj: Any = command_env) -> None:
    env = cast(CommandTestEnv, command_env_obj)
    trace = "01234567-89ab-cdef-0123-456789abcdef"
    envelope_first, _, payload_hash = _build_envelope(env, trace_id=trace)
    expected_idem_key = derive_idem_key(envelope_first, payload_hash=payload_hash)

    response_initial = env.client.post("/k0/command.submit", json=envelope_first)
    assert response_initial.status_code == 200
    initial_payload = response_initial.json()

    env.app.state.observability_emitter.clear()

    envelope_second, _, _ = _build_envelope(env, trace_id=trace)
    response_duplicate = env.client.post("/k0/command.submit", json=envelope_second)
    assert response_duplicate.status_code == 409
    duplicate_payload = response_duplicate.json()

    assert duplicate_payload["idem_key"] == expected_idem_key
    assert duplicate_payload["receipt_id"] == initial_payload["receipt_id"]

    with connection_scope() as conn:
        wal_count = conn.execute("SELECT COUNT(*) AS cnt FROM st_wal").fetchone()["cnt"]
        assert wal_count == 1

    events = env.app.state.observability_emitter.snapshot()
    assert any(
        event.get("event") == "command_idem_duplicate"
        and event.get("idem_key") == expected_idem_key
        for event in events
    )

    metrics_text = env.app.state.metrics_exporter.latest().decode("utf-8")
    assert (
        'k0_kernel_command_idempotency_duplicates_total{port="command",state="COMMITTED"} 1.0'
        in metrics_text
    )

    registry = env.app.state.metrics_exporter.registry
    success_counter = registry.get_sample_value(
        "k0_kernel_http_requests_total",
        {
            "route": "/k0/command.submit",
            "method": "POST",
            "status": "200",
            "outcome": "success",
            "operation": "command",
        },
    )
    assert success_counter == 1.0
    duplicate_counter = registry.get_sample_value(
        "k0_kernel_http_requests_total",
        {
            "route": "/k0/command.submit",
            "method": "POST",
            "status": "409",
            "outcome": "error",
            "operation": "command",
        },
    )
    assert duplicate_counter == 1.0
    latency_count = registry.get_sample_value(
        "k0_kernel_http_request_latency_seconds_count",
        {
            "route": "/k0/command.submit",
            "method": "POST",
            "operation": "command",
        },
    )
    assert latency_count == 2.0


@test("command.submit returns 429 when fanout budget is exhausted")
def _(command_env_obj: Any = command_env) -> None:
    env = cast(CommandTestEnv, command_env_obj)
    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration test profile",
            port_limits={"command": 8},
            default_port_limit=8,
        )
    )

    def qos_override() -> QoSContext:
        return QoSContext(scheduler=scheduler, fanout_budget=1, top_k_budget=4)

    env.app.state.observability_emitter.clear()
    env.app.dependency_overrides[qos_context_dependency] = qos_override

    try:
        envelope, _, _ = _build_envelope(env)
        policy = dict(envelope["policy"])
        policy["caps"] = {"fanout": {"requested": 3}}
        envelope["policy"] = policy
        base_envelope = {
            key: value for key, value in envelope.items() if key not in {"sig", "body"}
        }
        message = canonical_envelope(base_envelope)
        envelope["sig"] = encode_base64url(env.signing_key.sign(message).signature)

        response = env.client.post("/k0/command.submit", json=envelope)
        assert response.status_code == 429
        payload = response.json()
        error = payload["error"]
        assert error["code"] == "QOS_BUDGET_EXHAUSTED"
        assert error["component"] == "kernel.qos"
        assert error["details"]["cap"] == "fanout"
        assert error["budgets"]["fanout"] == 1
        uuid.UUID(error["trace_id"])

        metrics_text = env.app.state.metrics_exporter.latest().decode("utf-8")
        assert (
            'k0_kernel_qos_budget_exhausted_total{band="GREEN",cap="fanout",port="command"}'
            in metrics_text
        )

        registry = env.app.state.metrics_exporter.registry
        qos_counter = registry.get_sample_value(
            "k0_kernel_http_requests_total",
            {
                "route": "/k0/command.submit",
                "method": "POST",
                "status": "429",
                "outcome": "error",
                "operation": "command",
            },
        )
        assert qos_counter == 1.0

        events = env.app.state.observability_emitter.snapshot()
        assert any(
            event.get("event") == "command_qos_budget_exhausted"
            and event.get("cap") == "fanout"
            for event in events
        )
    finally:
        env.app.dependency_overrides.pop(qos_context_dependency, None)


@test("command.submit surfaces scheduler capacity pressure with 429")
def _(command_env_obj: Any = command_env) -> None:
    env = cast(CommandTestEnv, command_env_obj)
    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration test profile",
            port_limits={"command": 1},
            default_port_limit=1,
        )
    )

    def qos_override() -> QoSContext:
        return QoSContext(scheduler=scheduler, fanout_budget=2, top_k_budget=4)

    env.app.state.observability_emitter.clear()
    env.app.dependency_overrides[qos_context_dependency] = qos_override

    try:
        envelope, _, _ = _build_envelope(env)
        policy = dict(envelope["policy"])
        policy["caps"] = {"fanout": {"requested": 2}}
        envelope["policy"] = policy
        base_envelope = {
            key: value for key, value in envelope.items() if key not in {"sig", "body"}
        }
        message = canonical_envelope(base_envelope)
        envelope["sig"] = encode_base64url(env.signing_key.sign(message).signature)

        response = env.client.post("/k0/command.submit", json=envelope)
        assert response.status_code == 429
        payload = response.json()
        error = payload["error"]
        assert error["component"] == "kernel.qos"
        assert error["details"]["cap"] == "scheduler"
        assert error["budgets"]["fanout"] == 2
        assert error["reason"] == "SCHEDULER_CAPACITY_EXHAUSTED"
        uuid.UUID(error["trace_id"])

        metrics_text = env.app.state.metrics_exporter.latest().decode("utf-8")
        assert (
            'k0_kernel_qos_budget_exhausted_total{band="GREEN",cap="scheduler",port="command"}'
            in metrics_text
        )

        registry = env.app.state.metrics_exporter.registry
        qos_counter = registry.get_sample_value(
            "k0_kernel_http_requests_total",
            {
                "route": "/k0/command.submit",
                "method": "POST",
                "status": "429",
                "outcome": "error",
                "operation": "command",
            },
        )
        assert qos_counter == 1.0

        events = env.app.state.observability_emitter.snapshot()
        assert any(
            event.get("event") == "command_qos_budget_exhausted"
            and event.get("cap") == "scheduler"
            for event in events
        )
    finally:
        env.app.dependency_overrides.pop(qos_context_dependency, None)
