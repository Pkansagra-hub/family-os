"""Ward integration coverage for multi-key rotation verification telemetry."""

from __future__ import annotations

import sqlite3
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterator

from nacl.signing import SigningKey
from ward import fixture, test  # type: ignore[attr-defined]

from k0.automation.migrate import apply_migrations
from k0.gate import MinimalGate, SchemaRecord, SchemaRegistry
from k0.gate.minimal_gate import SIGNATURE_INVALID
from k0.obs import MetricsExporter, ObservabilityEmitter
from k0.security import canonical_envelope, canonical_json, hash_payload
from k0.security.crypto import encode_base64url
from k0.storage.provisioning import DeviceKey, ProvisionedDevice, ProvisioningLedger
from k0.uow.connection_pool import configure_pool, shutdown_pool

DEVICE_ID = "device-rotation"
TENANT_ID = "tenant-rotation"
SPACE_ID = "space-rotation"
SCHEMA_URI = "https://contracts.family-ai.dev/schemas/memory.snapshot.json"
SCHEMA_VERSION = "1.0.0"


def _sign_envelope(template: Dict[str, Any], signing_key: SigningKey) -> Dict[str, Any]:
    envelope = deepcopy(template)
    envelope.pop("sig", None)
    envelope.pop("idem_key", None)
    message = canonical_envelope(envelope)
    signature = signing_key.sign(message).signature
    envelope["sig"] = encode_base64url(signature)
    return envelope


@fixture
def rotation_env() -> Iterator[Dict[str, Any]]:
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "rotation.sqlite3"
        apply_migrations(db_path)
        configure_pool(db_path)

        try:
            ledger = ProvisioningLedger()
            registry = SchemaRegistry()
            metrics = MetricsExporter(namespace="k0_kernel")
            observability = ObservabilityEmitter()
            initial_ts = datetime(2025, 10, 1, tzinfo=timezone.utc)
            provisioned_ts = initial_ts.isoformat(timespec="seconds")
            activated_ts = (initial_ts + timedelta(minutes=5)).isoformat(
                timespec="seconds"
            )
            grace_expires_ts = (initial_ts + timedelta(hours=6)).isoformat(
                timespec="seconds"
            )

            primary_connection = sqlite3.connect(str(db_path))
            primary_connection.row_factory = sqlite3.Row  # type: ignore[assignment]

            device = ProvisionedDevice(
                device_id=DEVICE_ID,
                tenant_id=TENANT_ID,
                space_id=SPACE_ID,
                mls_group_id="mls-group-rotation",
                provisioned_ts=provisioned_ts,
            )

            active_signing_key = SigningKey.generate()
            rotating_signing_key = SigningKey.generate()

            active_key = DeviceKey(
                device_id=DEVICE_ID,
                key_version="v2",
                verify_key=encode_base64url(active_signing_key.verify_key.encode()),
                key_state="PENDING",
                registered_ts=provisioned_ts,
            )
            rotating_key = DeviceKey(
                device_id=DEVICE_ID,
                key_version="v1",
                verify_key=encode_base64url(
                    rotating_signing_key.verify_key.encode()
                ),
                key_state="ACTIVE",
                registered_ts=provisioned_ts,
                activated_ts=provisioned_ts,
            )

            # Persist provisioning bindings and initial keys
            ledger.register(device, connection=primary_connection)
            ledger.add_key(rotating_key, connection=primary_connection)
            ledger.add_key(active_key, connection=primary_connection)

            # Activate v2 and transition v1 → ROTATING
            stored_keys = ledger.get_keys(DEVICE_ID, connection=primary_connection)
            pending_v2 = next(k for k in stored_keys if k.key_version == "v2")
            for key in stored_keys:
                if key.key_state == "ACTIVE":
                    rotated = replace(
                        key,
                        key_state="ROTATING",
                        rotated_ts=activated_ts,
                        grace_expires_ts=grace_expires_ts,
                    )
                    ledger.add_key(rotated, connection=primary_connection)
            ledger.add_key(
                replace(
                    pending_v2,
                    key_state="ACTIVE",
                    activated_ts=activated_ts,
                ),
                connection=primary_connection,
            )

            registry.upsert(
                SchemaRecord(
                    uri=SCHEMA_URI,
                    version=SCHEMA_VERSION,
                    sha256="deadbeef" * 8,
                    status="ACTIVE",
                ),
                connection=primary_connection,
            )
            primary_connection.commit()
            primary_connection.close()

            body = {"memory": {"note": "rotation-validation"}}
            body_bytes = canonical_json(body).encode("utf-8")
            payload_hash = hash_payload(body_bytes)

            envelope_template: Dict[str, Any] = {
                "tenant_id": TENANT_ID,
                "space_id": SPACE_ID,
                "actor": DEVICE_ID,
                "device_id": DEVICE_ID,
                "schema_uri": SCHEMA_URI,
                "schema_version": SCHEMA_VERSION,
                "topic": "memory.snapshot.commit",
                "band": "GREEN",
                "policy_version": "2025-09-01",
                "ts": provisioned_ts,
                "payload_sha256": payload_hash,
            }

            gate = MinimalGate(
                registry=registry,
                provisioning=ledger,
                metrics=metrics,
                observability=observability,
            )

            yield {
                "db_path": db_path,
                "gate": gate,
                "metrics": metrics,
                "observability": observability,
                "ledger": ledger,
                "envelope_template": envelope_template,
                "body_bytes": body_bytes,
                "active_signing_key": active_signing_key,
                "rotating_signing_key": rotating_signing_key,
                "grace_expires_ts": grace_expires_ts,
            }
        finally:
            shutdown_pool()


@test("active and rotating keys verify successfully with telemetry emission")
def _(rotation_env: Any = rotation_env) -> None:
    gate: MinimalGate = rotation_env["gate"]
    metrics: MetricsExporter = rotation_env["metrics"]
    observability: ObservabilityEmitter = rotation_env["observability"]
    body_bytes: bytes = rotation_env["body_bytes"]
    envelope_template: Dict[str, Any] = rotation_env["envelope_template"]
    active_key: SigningKey = rotation_env["active_signing_key"]
    rotating_key: SigningKey = rotation_env["rotating_signing_key"]
    db_path: Path = rotation_env["db_path"]

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row  # type: ignore[assignment]
    try:
        active_envelope = _sign_envelope(envelope_template, active_key)
        outcome_active = gate.validate(active_envelope, body_bytes, connection=connection)
        assert outcome_active.accepted is True
        assert outcome_active.key_version == "v2"
        assert outcome_active.key_state == "ACTIVE"
        assert "idem_key" in active_envelope

        rotating_envelope = _sign_envelope(envelope_template, rotating_key)
        outcome_rotating = gate.validate(
            rotating_envelope, body_bytes, connection=connection
        )
        assert outcome_rotating.accepted is True
        assert outcome_rotating.key_version == "v1"
        assert outcome_rotating.key_state == "ROTATING"
    finally:
        connection.close()

    metrics_output = metrics.latest().decode("utf-8")
    assert "k0_kernel_k0_signature_verified_total" in metrics_output
    assert 'key_state="ACTIVE",key_version="v2"' in metrics_output
    assert 'key_state="ROTATING",key_version="v1"' in metrics_output

    events = observability.snapshot()
    assert any(
        event.get("event") == "signature_verification"
        and event.get("outcome") == "success"
        and event.get("key_state") == "ACTIVE"
        for event in events
    )
    assert any(
        event.get("event") == "signature_verification"
        and event.get("outcome") == "success"
        and event.get("key_state") == "ROTATING"
        for event in events
    )


@test("revoked key fails verification and increments failure counter")
def _(rotation_env: Any = rotation_env) -> None:
    gate: MinimalGate = rotation_env["gate"]
    metrics: MetricsExporter = rotation_env["metrics"]
    observability: ObservabilityEmitter = rotation_env["observability"]
    body_bytes: bytes = rotation_env["body_bytes"]
    envelope_template: Dict[str, Any] = rotation_env["envelope_template"]
    rotating_key: SigningKey = rotation_env["rotating_signing_key"]
    ledger: ProvisioningLedger = rotation_env["ledger"]
    db_path: Path = rotation_env["db_path"]

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row  # type: ignore[assignment]
    try:
        keys = ledger.get_keys(DEVICE_ID, connection=connection)
        rotating = next(k for k in keys if k.key_version == "v1")
        revoked = replace(
            rotating,
            key_state="REVOKED",
            revoked_ts=datetime(2025, 10, 1, 12, tzinfo=timezone.utc).isoformat(
                timespec="seconds"
            ),
            revocation_reason="test-revoked",
        )
        ledger.add_key(revoked, connection=connection)
        connection.commit()

        revoked_envelope = _sign_envelope(envelope_template, rotating_key)
        outcome = gate.validate(revoked_envelope, body_bytes, connection=connection)
    finally:
        connection.close()

    assert outcome.accepted is False
    assert outcome.reason == SIGNATURE_INVALID
    assert outcome.key_version is None

    metrics_output = metrics.latest().decode("utf-8")
    assert "k0_kernel_k0_signature_verification_failed_total" in metrics_output
    assert f'device_id="{DEVICE_ID}"' in metrics_output

    events = observability.snapshot()
    assert any(
        event.get("event") == "signature_verification"
        and event.get("outcome") == "failure"
        and event.get("reason") == SIGNATURE_INVALID
        for event in events
    )
