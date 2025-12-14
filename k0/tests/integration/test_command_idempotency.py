"""Integration coverage for command port idempotency handling."""

from __future__ import annotations

import gc
import sqlite3
import uuid
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator

from fastapi.testclient import TestClient
from nacl.signing import SigningKey  # type: ignore[import]
from ward import test  # type: ignore[attr-defined]

from k0.automation.migrate import apply_migrations
from k0.gate.schema_registry import SchemaRecord, SchemaRegistry
from k0.idem import IdempotencyLedger, LedgerEntry, derive_idem_key
from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.kernel.dependencies import database_session
from k0.security import canonical_envelope
from k0.security.crypto import encode_base64url
from k0.storage.provisioning import DeviceKey, ProvisionedDevice, ProvisioningLedger

BASE_ENVELOPE: dict[str, Any] = {
    "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
    "tenant_id": "tenant-alpha",
    "space_id": "space-omega",
    "topic": "memory.snapshot.commit",
    "schema_uri": "https://contracts.family-ai.dev/schemas/memory.snapshot.json",
    "schema_version": "1.0.0",
    "actor": "device-123",
    "device_id": "device-123",
    "band": "GREEN",
    "policy_version": "2025-09-01",
    "ts": "2025-09-28T12:00:00Z",
    "sig": "placeholder-signature",
    "payload_sha256": None,
    # V1 required fields (ADR-K001)
    "sig_alg": "ED25519",
    "sig_kid": "did:device:device-123#1",
    "envelope_sha256": "0" * 64,  # Will be computed by gate
}

SIGNING_KEY = SigningKey(bytes(range(32)))
VERIFY_KEY_B64 = encode_base64url(SIGNING_KEY.verify_key.encode())
SCHEMA_SHA = sha256(
    f"{BASE_ENVELOPE['schema_uri']}@{BASE_ENVELOPE['schema_version']}".encode("utf-8")
).hexdigest()


def cleanup_sqlite_artifacts(db_path: Path) -> None:
    """Best-effort cleanup for SQLite database files on Windows."""

    artifacts_suffixes = ("", "-wal", "-shm")
    remaining: list[Path] = []

    for _ in range(10):
        if db_path.exists():
            try:
                with sqlite3.connect(str(db_path), timeout=0) as connection:
                    connection.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    connection.execute("PRAGMA journal_mode=DELETE;")
            except sqlite3.OperationalError:
                pass

        gc.collect()

        remaining.clear()
        for suffix in artifacts_suffixes:
            artifact = db_path.with_name(f"{db_path.name}{suffix}")
            if not artifact.exists():
                continue
            try:
                artifact.unlink()
            except PermissionError:
                remaining.append(artifact)

        if not remaining:
            return

    # Residual locks are tolerated; TemporaryDirectory cleanup ignores errors.
    return


@test("duplicate idem key produces 409 with telemetry emission")
def _() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "kernel.db"
        apply_migrations(db_path)

        primary_connection = sqlite3.connect(str(db_path), check_same_thread=False)
        primary_connection.row_factory = sqlite3.Row  # type: ignore[assignment]

        provisioning = ProvisioningLedger()
        device = ProvisionedDevice(
            device_id=str(BASE_ENVELOPE["device_id"]),
            tenant_id=str(BASE_ENVELOPE["tenant_id"]),
            space_id=str(BASE_ENVELOPE["space_id"]),
            mls_group_id="mls-group-id",
            provisioned_ts="2025-09-28T12:00:00Z",
        )
        device_key = DeviceKey(
            device_id=str(BASE_ENVELOPE["device_id"]),
            key_version="1",
            verify_key=VERIFY_KEY_B64,
            key_state="ACTIVE",
            registered_ts="2025-09-28T12:00:00Z",
            activated_ts="2025-09-28T12:00:00Z",
        )
        provisioning.register(device, connection=primary_connection)
        provisioning.add_key(device_key, connection=primary_connection)
        primary_connection.commit()

        registry = SchemaRegistry()
        registry.upsert(
            SchemaRecord(
                uri=str(BASE_ENVELOPE["schema_uri"]),
                version=str(BASE_ENVELOPE["schema_version"]),
                sha256=SCHEMA_SHA,
                status="ACTIVE",
            ),
            connection=primary_connection,
        )
        primary_connection.commit()

        ledger = IdempotencyLedger()
        envelope = dict(BASE_ENVELOPE)
        if envelope.get("payload_sha256") is None:
            envelope.pop("payload_sha256", None)
        idem_key = derive_idem_key(envelope, payload_hash=envelope.get("payload_sha256"))
        envelope["idem_key"] = idem_key
        message = canonical_envelope(envelope)
        signature = SIGNING_KEY.sign(message).signature
        envelope["sig"] = encode_base64url(signature)

        entry = LedgerEntry(
            idem_key=idem_key,
            receipt_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            first_seen_ts="2025-09-28T12:05:00Z",
            state="COMMITTED",
            expiry_ts=None,
        )

        ledger.upsert(entry, connection=primary_connection)
        primary_connection.commit()

        settings = KernelSettings.load(overrides={"database": {"path": str(db_path)}})
        app = create_app(settings=settings)

        def _connection_override() -> Iterator[sqlite3.Connection]:
            try:
                yield primary_connection
            finally:
                pass

        app.dependency_overrides[database_session] = _connection_override
        with TestClient(app) as client:
            response = client.post("/k0/command.submit", json=envelope)
            assert response.status_code == 409
            payload = response.json()
            assert payload["receipt_id"] == entry.receipt_id
            assert payload["commit_ts"] == entry.first_seen_ts
            assert payload["idem_key"] == idem_key
            response.close()

            metrics_output = app.state.metrics_exporter.latest().decode("utf-8")
            assert "command_idempotency_duplicates_total" in metrics_output

            events = app.state.observability_emitter.snapshot()
            assert events
            # Find the command_idem_duplicate event (not necessarily last due to HTTP metrics)
            idem_duplicate_events = [
                e for e in events if e.get("event") == "command_idem_duplicate"
            ]
            assert idem_duplicate_events, "Expected command_idem_duplicate event"
            assert idem_duplicate_events[-1]["idem_key"] == idem_key

            new_envelope = dict(envelope)
            new_envelope["tenant_id"] = "tenant-beta"
            if new_envelope.get("payload_sha256") is None:
                new_envelope.pop("payload_sha256", None)
            new_idem_key = derive_idem_key(
                new_envelope, payload_hash=new_envelope.get("payload_sha256")
            )
            new_envelope["idem_key"] = new_idem_key
            new_message = canonical_envelope(new_envelope)
            new_signature = SIGNING_KEY.sign(new_message).signature
            new_envelope["sig"] = encode_base64url(new_signature)
            fresh_response = client.post("/k0/command.submit", json=new_envelope)
            assert fresh_response.status_code == 400
            fresh_payload = fresh_response.json()
            assert fresh_payload["error"]["code"] == "REJECTED_KERNEL_GATE"
            assert fresh_payload["error"]["reason"] == "SPACE_TENANT_MISMATCH"
            assert fresh_payload["error"]["component"] == "kernel.gate"
            uuid.UUID(fresh_payload["error"]["trace_id"])
            fresh_response.close()

        app.dependency_overrides.pop(database_session, None)
        client = None
        app = None
        try:
            primary_connection.rollback()
        except sqlite3.ProgrammingError:
            pass
        primary_connection.close()
        gc.collect()
        cleanup_sqlite_artifacts(db_path)
