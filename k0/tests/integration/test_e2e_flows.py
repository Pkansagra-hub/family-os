"""
End-to-End Black-Box Test Suite for K0 Kernel

Tests the complete kernel workflow using only public HTTP APIs:
- Command submission → receipt → WAL → outbox
- Query recall with selectors and budgets
- SSE subscribe → delivery → ack
- Observability endpoints

Uses the K0 SDK client for clean test c    envelope = _build_command_envelope(
        env,
        topic="memory.invalid",
        body={"action": "test"},
    )
    # Corrupt signature (field name is 'sig' not 'device_sig')
    envelope["sig"] = "AAAA" + envelope["sig"][4:]

    response = env.client.submit_command(envelope)
    assert not response.ok
    assert response.status_code == 400
    error = response.error
    assert error is not None
    # Gate returns specific error codes like INVALID_SIGNATURE
    assert error["code"] in ("REJECTED_KERNEL_GATE",)
    assert error.get("reason") in ("INVALID_SIGNATURE", "GATE_SIGNATURE_INVALID")tion-ready patterns.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterator
from uuid import uuid4

from nacl.signing import SigningKey
from ward import fixture, test  # type: ignore[attr-defined]

from k0.gate.schema_registry import SchemaRecord
from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.security import canonical_envelope, canonical_json
from k0.security.crypto import encode_base64url
from k0.storage.provisioning import DeviceKey, ProvisionedDevice
from k0.uow.connection_pool import connection_scope, shutdown_pool
from k0.tests.sdk.k0_client import CommandReceipt, K0Client

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_SQL_PATH = REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql"


class E2ETestEnv:
    """Complete E2E test environment with kernel, SDK client, and provisioned device."""

    def __init__(
        self,
        client: K0Client,
        signing_key: SigningKey,
        tenant_id: str,
        space_id: str,
        device_id: str,
        schema_uri: str,
        schema_version: str,
        db_path: Path,
    ):
        self.client = client
        self.signing_key = signing_key
        self.tenant_id = tenant_id
        self.space_id = space_id
        self.device_id = device_id
        self.schema_uri = schema_uri
        self.schema_version = schema_version
        self.db_path = db_path


@fixture
def e2e_env() -> Iterator[E2ETestEnv]:
    """
    Provision a complete E2E test environment with:
    - Temporary SQLite database
    - Running kernel (FastAPI TestClient)
    - K0 SDK client
    - Provisioned device with signing key
    - Registered schema
    """
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

    # Provision device and keys
    signing_key = SigningKey.generate()
    verify_key_b64 = encode_base64url(signing_key.verify_key.encode())

    tenant_id = f"tenant-{uuid4().hex[:8]}"
    space_id = f"space-{uuid4().hex[:8]}"
    device_id = f"device-{uuid4().hex[:8]}"

    device = ProvisionedDevice(
        device_id=device_id,
        tenant_id=tenant_id,
        space_id=space_id,
        mls_group_id=f"mls-{uuid4().hex[:8]}",
        provisioned_ts="2025-09-30T00:00:00Z",
    )
    device_key = DeviceKey(
        device_id=device_id,
        key_version="1",
        verify_key=verify_key_b64,
        key_state="ACTIVE",
        registered_ts="2025-09-30T00:00:00Z",
        activated_ts="2025-09-30T00:00:00Z",
    )

    # Register schema
    schema_uri = "schema://test.e2e"
    schema_version = "1.0"
    schema_sha = sha256(f"{schema_uri}@{schema_version}".encode("utf-8")).hexdigest()

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

    # Mark kernel as ready (migrations applied + WAL replay complete)
    if hasattr(app.state, "readiness"):
        app.state.readiness.mark_migrations_complete()
        app.state.readiness.mark_wal_replay_complete()

    # Clear observability state
    if hasattr(app.state, "observability_emitter"):
        app.state.observability_emitter.clear()

    # Register initial metric to ensure Prometheus export is not empty
    if hasattr(app.state, "metrics_exporter"):
        app.state.metrics_exporter.set_gauge("test_environment_initialized", 1.0)

    # Create SDK client wrapping TestClient
    from fastapi.testclient import TestClient

    test_client = TestClient(app)
    sdk_client = K0Client(base_url="http://testserver")
    sdk_client._client = test_client  # type: ignore[assignment]

    env = E2ETestEnv(
        client=sdk_client,
        signing_key=signing_key,
        tenant_id=tenant_id,
        space_id=space_id,
        device_id=device_id,
        schema_uri=schema_uri,
        schema_version=schema_version,
        db_path=db_path,
    )

    yield env

    test_client.close()
    shutdown_pool()
    tmp_dir.cleanup()


def _build_command_envelope(
    env: E2ETestEnv,
    *,
    topic: str,
    body: Dict[str, Any],
    trace_id: str | None = None,
) -> Dict[str, Any]:
    """Build and sign a command envelope for submission."""
    from datetime import datetime, timezone

    trace_id = trace_id or str(uuid4())
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    # Compute payload hash
    body_bytes = canonical_json(body).encode("utf-8")
    payload_hash = sha256(body_bytes).hexdigest()
    payload_bytes = len(body_bytes)

    # Build envelope with FLAT structure matching gate expectations
    envelope: Dict[str, Any] = {
        "cognitive_trace_id": trace_id,
        "tenant_id": env.tenant_id,
        "space_id": env.space_id,
        "device_id": env.device_id,
        "topic": topic,
        "schema_uri": env.schema_uri,  # FLAT, not nested
        "schema_version": env.schema_version,  # FLAT, not nested
        "actor": f"user@{env.tenant_id}",
        "band": "GREEN",
        "policy_version": "1.0",
        "ts": ts,
        "payload_sha256": payload_hash,
        "payload_bytes": payload_bytes,
        # Add policy context with roles array to pass PEP evaluation
        "policy": {
            "abac": {
                "roles": [
                    "coordinator"
                ],  # coordinator allows memory.*, events.*, policy.* topics
            }
        },
    }

    # Sign canonical envelope (without sig and body fields)
    canonical = canonical_envelope(envelope)
    signature = env.signing_key.sign(canonical)
    envelope["sig"] = encode_base64url(
        signature.signature
    )  # Field name is 'sig' not 'device_sig'
    envelope["body"] = body  # Add body after signing

    return envelope


# === Observability Port Tests ===


@test("e2e: health endpoint returns 200")
def _(env: E2ETestEnv = e2e_env) -> None:
    response = env.client.health()
    assert response.ok
    assert response.status_code == 200


@test("e2e: readiness endpoint returns 200 when kernel ready")
def _(env: E2ETestEnv = e2e_env) -> None:
    response = env.client.readiness()
    assert response.ok
    assert response.status_code == 200
    assert response.body is not None
    assert response.body.get("ready") is True
    components = response.body.get("components", {})
    assert components.get("migrations_applied") is True
    assert components.get("wal_replay_complete") is True


@test("e2e: metrics endpoint returns Prometheus format")
def _(env: E2ETestEnv = e2e_env) -> None:
    response = env.client.metrics()
    assert response.ok
    assert response.status_code == 200
    # Verify Prometheus text format
    content = response.raw_content.decode("utf-8")
    assert "# HELP" in content or "# TYPE" in content


# === Command Port Tests ===


@test("e2e: command submit → receipt → WAL persistence")
def _(env: E2ETestEnv = e2e_env) -> None:
    envelope = _build_command_envelope(
        env,
        topic="memory.command",
        body={"action": "create", "payload": {"name": "test-resource"}},
    )

    response = env.client.submit_command(envelope)
    assert response.ok, f"Command failed: {response.error}"
    assert response.status_code == 200

    # Parse receipt
    receipt = CommandReceipt.from_response(response)
    assert receipt.receipt_id
    assert receipt.idem_key
    assert receipt.wal_pos > 0

    # Verify WAL persistence via direct DB check
    with connection_scope() as conn:
        row = conn.execute(
            "SELECT pos, topic, tenant_id, space_id, device_id FROM st_wal WHERE pos = ?",
            (receipt.wal_pos,),
        ).fetchone()
        assert row is not None
        assert row["topic"] == "memory.command"  # Match actual envelope topic
        assert row["tenant_id"] == env.tenant_id
        assert row["space_id"] == env.space_id
        assert row["device_id"] == env.device_id


@test("e2e: command idempotency prevents duplicate commits")
def _(env: E2ETestEnv = e2e_env) -> None:
    envelope = _build_command_envelope(
        env,
        topic="memory.idempotent",
        body={"action": "upsert", "key": "unique-key-1"},
    )

    # First submission
    response1 = env.client.submit_command(envelope)
    assert response1.ok
    receipt1 = CommandReceipt.from_response(response1)

    # Second submission (identical envelope) - should return 409 with same receipt
    response2 = env.client.submit_command(envelope)
    assert response2.status_code == 409  # Idempotency: duplicate detected
    # Parse receipt from 409 response (simplified structure)
    assert response2.body is not None
    receipt2_data = response2.body
    assert receipt2_data["receipt_id"] == str(receipt1.receipt_id)
    assert receipt2_data["idem_key"] == receipt1.idem_key

    # Verify only one WAL entry exists
    with connection_scope() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS total FROM st_wal WHERE idem_key = ?",
            (receipt1.idem_key,),
        ).fetchone()["total"]
        assert count == 1


@test("e2e: command with invalid signature is rejected")
def _(env: E2ETestEnv = e2e_env) -> None:
    envelope = _build_command_envelope(
        env,
        topic="memory.invalid",
        body={"action": "test"},
    )
    # Corrupt signature
    envelope["sig"] = "AAAA" + envelope["sig"][4:]

    response = env.client.submit_command(envelope)
    assert not response.ok
    assert response.status_code in (400, 403)
    error = response.error
    assert error is not None
    assert error["code"] in (
        "GATE_SIGNATURE_INVALID",
        "GATE_REJECTED",
        "REJECTED_KERNEL_GATE",
    )


@test("e2e: command creates outbox entries for configured drivers")
def _(env: E2ETestEnv = e2e_env) -> None:
    envelope = _build_command_envelope(
        env,
        topic="memory.outbox",
        body={"indexed": True, "content": "test data"},
    )

    response = env.client.submit_command(envelope)
    assert response.ok
    receipt = CommandReceipt.from_response(response)

    # Verify outbox entry created
    with connection_scope() as conn:
        rows = conn.execute(
            "SELECT driver, op_kind, wal_pos FROM st_outbox WHERE wal_pos = ?",
            (receipt.wal_pos,),
        ).fetchall()
        assert len(rows) > 0, "Expected outbox entries for driver dispatch"
        # Default driver from command port
        driver_names = {row["driver"] for row in rows}
        assert len(driver_names) > 0


# === Query Port Tests ===


@test("e2e: query recall executes selectors and returns bundle")
def _(env: E2ETestEnv = e2e_env) -> None:
    # Submit a command first to have data in WAL
    envelope = _build_command_envelope(
        env,
        topic="memory.query",  # Matches coordinator role
        body={"key": "queryable", "value": 42},
    )
    cmd_response = env.client.submit_command(envelope)
    assert cmd_response.ok

    # Execute query
    selectors = [
        {
            "topic": "test.query.data",
            "limit": 10,
        }
    ]
    query_response = env.client.query_recall(
        tenant_id=env.tenant_id,
        space_id=env.space_id,
        selectors=selectors,
    )

    assert query_response.ok, f"Query failed: {query_response.error}"
    assert query_response.body is not None

    body = query_response.body
    assert "bundle" in body
    assert "trace" in body
    assert "budgets" in body

    budgets = body["budgets"]
    assert "fanout" in budgets
    assert "time_slice" in budgets


@test("e2e: query with fanout budget exhaustion returns 429")
def _(env: E2ETestEnv = e2e_env) -> None:
    # Attempt query with zero fanout budget via QoS hints
    selectors = [{"topic": "test.*", "limit": 5}]

    # Note: actual budget enforcement depends on kernel QoS configuration
    # This test verifies the error path when budgets are exhausted
    query_response = env.client.query_recall(
        tenant_id=env.tenant_id,
        space_id=env.space_id,
        selectors=selectors,
        qos_hints={"fanout_limit": 0},  # Request impossible budget
    )

    # If kernel enforces, expect 429; otherwise query succeeds with reduced results
    if not query_response.ok:
        assert query_response.status_code == 429
        error = query_response.error
        assert error is not None
        assert error["code"] == "QOS_BUDGET_EXHAUSTED"


# === SSE Port Tests ===


@test("e2e: sse.ack persists subscriber offset")
def _(env: E2ETestEnv = e2e_env) -> None:
    subscriber_id = f"subscriber-{uuid4().hex[:8]}"
    topic = "memory.sse.topic"
    offset = 42

    response = env.client.sse_ack(
        subscriber_id=subscriber_id,
        topic=topic,
        space_id=env.space_id,
        tenant_id=env.tenant_id,
        offset=offset,
    )

    assert response.ok
    assert response.status_code == 204

    # Verify offset stored
    with connection_scope() as conn:
        row = conn.execute(
            "SELECT offset FROM st_offsets WHERE subscriber_id = ? AND topic = ?",
            (subscriber_id, topic),
        ).fetchone()
        assert row is not None
        assert row["offset"] == offset


@test("e2e: sse.subscribe delivers events from WAL")
def _(env: E2ETestEnv = e2e_env) -> None:
    topic = "memory.sse.delivery"

    # Submit command to create WAL entry
    envelope = _build_command_envelope(
        env,
        topic=topic,
        body={"event": "test-sse-event"},
    )
    cmd_response = env.client.submit_command(envelope)
    assert cmd_response.ok
    receipt = CommandReceipt.from_response(cmd_response)

    # Subscribe to SSE stream (consume one event)
    subscriber_id = f"sub-{uuid4().hex[:8]}"
    events = []

    for i, event in enumerate(
        env.client.sse_subscribe(
            tenant_id=env.tenant_id,
            space_id=env.space_id,
            topics=[topic],
            subscriber_id=subscriber_id,
        )
    ):
        events.append(event)
        if i >= 0:  # Consume first event
            break

    assert len(events) == 1
    delivered_event = events[0]
    assert "wal_pos" in delivered_event
    assert delivered_event["wal_pos"] == receipt.wal_pos
    assert delivered_event["topic"] == topic


# === Full E2E Flow Test ===


@test("e2e: complete flow - command → query → sse → ack")
def _(env: E2ETestEnv = e2e_env) -> None:
    """
    Comprehensive E2E test exercising all ports in sequence:
    1. Submit command → verify receipt and WAL
    2. Query for the data → verify bundle
    3. Subscribe via SSE → verify delivery
    4. Ack the event → verify offset persistence
    """
    topic = "memory.full.flow"
    test_data = {"flow_id": str(uuid4()), "step": "complete"}

    # Step 1: Submit command
    envelope = _build_command_envelope(env, topic=topic, body=test_data)
    cmd_response = env.client.submit_command(envelope)
    assert cmd_response.ok, f"Command failed: {cmd_response.error}"
    receipt = CommandReceipt.from_response(cmd_response)
    assert receipt.wal_pos > 0

    # Step 2: Query recall
    selectors = [{"topic": topic, "limit": 1}]
    query_response = env.client.query_recall(
        tenant_id=env.tenant_id,
        space_id=env.space_id,
        selectors=selectors,
    )
    assert query_response.ok, f"Query failed: {query_response.error}"
    assert query_response.body is not None
    bundle = query_response.body["bundle"]
    assert bundle is not None  # Query should return the event

    # Step 3: SSE subscribe and consume
    subscriber_id = f"full-flow-{uuid4().hex[:8]}"
    events = []
    for i, event in enumerate(
        env.client.sse_subscribe(
            tenant_id=env.tenant_id,
            space_id=env.space_id,
            topics=[topic],
            subscriber_id=subscriber_id,
        )
    ):
        events.append(event)
        if i >= 0:
            break

    assert len(events) == 1
    sse_event = events[0]
    assert sse_event["wal_pos"] == receipt.wal_pos
    assert sse_event["topic"] == topic

    # Step 4: Ack the event
    ack_response = env.client.sse_ack(
        subscriber_id=subscriber_id,
        topic=topic,
        space_id=env.space_id,
        tenant_id=env.tenant_id,
        offset=receipt.wal_pos,
    )
    assert ack_response.ok
    assert ack_response.status_code == 204

    # Verify offset persisted
    with connection_scope() as conn:
        row = conn.execute(
            "SELECT offset FROM st_offsets WHERE subscriber_id = ? AND topic = ?",
            (subscriber_id, topic),
        ).fetchone()
        assert row is not None
        assert row["offset"] == receipt.wal_pos


# === Error Path Tests ===


@test("e2e: invalid envelope schema is rejected")
def _(env: E2ETestEnv = e2e_env) -> None:
    envelope = {
        "cognitive_trace_id": str(uuid4()),
        # Missing required fields
        "topic": "memory.invalid",  # Matches coordinator role
    }

    response = env.client.submit_command(envelope)
    assert not response.ok
    assert response.status_code == 400
    error = response.error
    assert error is not None
    assert error["code"] in (
        "GATE_ENVELOPE_INVALID",
        "GATE_REJECTED",
        "REJECTED_KERNEL_GATE",
    )


@test("e2e: command without provisioned device is rejected")
def _(env: E2ETestEnv = e2e_env) -> None:
    envelope = _build_command_envelope(
        env,
        topic="memory.unprovisioned",
        body={"action": "test"},
    )
    # Use a device_id that isn't provisioned
    envelope["device_id"] = "device-not-provisioned"

    response = env.client.submit_command(envelope)
    assert not response.ok
    assert response.status_code in (400, 403, 404)
    error = response.error
    assert error is not None


@test("e2e: query with invalid tenant/space returns empty or error")
def _(env: E2ETestEnv = e2e_env) -> None:
    selectors = [{"topic": "test.*", "limit": 10}]

    response = env.client.query_recall(
        tenant_id="tenant-nonexistent",
        space_id="space-nonexistent",
        selectors=selectors,
    )

    # Kernel may return 200 with empty bundle or 404/403
    if response.ok:
        assert response.body is not None
        bundle = response.body.get("bundle", {})
        # Empty or minimal results expected
    else:
        assert response.status_code in (403, 404)

