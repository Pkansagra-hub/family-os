from __future__ import annotations

from hashlib import sha256
from typing import Any

from nacl.encoding import URLSafeBase64Encoder  # type: ignore[import]
from nacl.signing import SigningKey  # type: ignore[import]
from ward import test  # type: ignore[attr-defined]

from k0.gate.minimal_gate import (
    DEVICE_NOT_PROVISIONED,
    MISSING_BINDINGS,
    PAYLOAD_HASH_MISMATCH,
    PAYLOAD_HASH_MISSING,
    SIGNATURE_INVALID,
    SIGNATURE_MISSING,
    SPACE_MISMATCH,
    MinimalGate,
)
from k0.gate.schema_registry import SchemaRecord, SchemaRegistry
from k0.security import canonical_envelope, hash_payload
from k0.storage.provisioning import DeviceKey, ProvisionedDevice, ProvisioningLedger
from k0.uow.connection_pool import connection_scope
from tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]

SIGNING_KEY = SigningKey(bytes(range(32)))
VERIFY_KEY_B64 = SIGNING_KEY.verify_key.encode(URLSafeBase64Encoder).decode("ascii")
SCHEMA_URI = "schema://memory.delta"
SCHEMA_VERSION = "1.0.0"
SCHEMA_SHA = sha256(f"{SCHEMA_URI}@{SCHEMA_VERSION}".encode("utf-8")).hexdigest()
TOPIC = "memory.delta"
ACTOR = "device-actor"


def _register_device(ledger: ProvisioningLedger) -> None:
    device = ProvisionedDevice(
        device_id="device-A",
        tenant_id="tenant-A",
        space_id="space-A",
        mls_group_id="mls-1",
        provisioned_ts="2025-09-28T12:00:00Z",
    )
    device_key = DeviceKey(
        device_id="device-A",
        key_version="v1",
        verify_key=VERIFY_KEY_B64,
        key_state="ACTIVE",
        registered_ts="2025-09-28T12:00:00Z",
        activated_ts="2025-09-28T12:00:00Z",
    )
    ledger.register(device)
    ledger.add_key(device_key)


def _seed_registry() -> SchemaRegistry:
    registry = SchemaRegistry()
    registry.upsert(
        SchemaRecord(
            uri=SCHEMA_URI,
            version=SCHEMA_VERSION,
            sha256=SCHEMA_SHA,
            status="ACTIVE",
        )
    )
    return registry


def _build_gate(*, provisioning: ProvisioningLedger | None = None) -> MinimalGate:
    registry = _seed_registry()
    return MinimalGate(provisioning=provisioning, registry=registry)


def _signed_envelope(body: bytes, **overrides: object) -> dict[str, object]:
    envelope: dict[str, object] = {
        "tenant_id": "tenant-A",
        "space_id": "space-A",
        "device_id": "device-A",
        "actor": ACTOR,
        "topic": TOPIC,
        "schema_uri": SCHEMA_URI,
        "schema_version": SCHEMA_VERSION,
        "payload_sha256": hash_payload(body),
    }
    envelope.update(overrides)
    message = canonical_envelope(envelope)
    signature = SIGNING_KEY.sign(message).signature
    envelope["sig"] = URLSafeBase64Encoder.encode(signature).decode("ascii")
    return envelope


@test("minimal gate accepts envelopes with provisioned bindings")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    ledger = ProvisioningLedger()
    _register_device(ledger)

    gate = _build_gate(provisioning=ledger)
    body = b"payload"
    envelope = _signed_envelope(body)

    outcome = gate.validate(envelope, body=body)
    assert outcome.accepted is True
    assert outcome.reason is None


@test("minimal gate rejects unprovisioned devices")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    gate = _build_gate()
    envelope: dict[str, object] = {
        "tenant_id": "tenant-A",
        "space_id": "space-A",
        "device_id": "device-Z",
        "actor": ACTOR,
        "topic": TOPIC,
        "schema_uri": SCHEMA_URI,
        "schema_version": SCHEMA_VERSION,
    }

    outcome = gate.validate(envelope)
    assert outcome.accepted is False
    assert outcome.reason == DEVICE_NOT_PROVISIONED


@test("minimal gate detects tenant/space mismatches")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    ledger = ProvisioningLedger()
    device = ProvisionedDevice(
        device_id="device-B",
        tenant_id="tenant-A",
        space_id="space-A",
        mls_group_id="mls-2",
        provisioned_ts="2025-09-28T12:30:00Z",
    )
    device_key = DeviceKey(
        device_id="device-B",
        key_version="v1",
        verify_key=VERIFY_KEY_B64,
        key_state="ACTIVE",
        registered_ts="2025-09-28T12:30:00Z",
        activated_ts="2025-09-28T12:30:00Z",
    )
    ledger.register(device)
    ledger.add_key(device_key)

    gate = _build_gate(provisioning=ledger)
    envelope: dict[str, object] = {
        "tenant_id": "tenant-A",
        "space_id": "space-B",
        "device_id": "device-B",
        "actor": ACTOR,
        "topic": TOPIC,
        "schema_uri": SCHEMA_URI,
        "schema_version": SCHEMA_VERSION,
    }

    outcome = gate.validate(envelope)
    assert outcome.accepted is False
    assert outcome.reason == SPACE_MISMATCH


@test("minimal gate reports missing binding fields")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    gate = _build_gate()
    envelope: dict[str, object] = {
        "tenant_id": "tenant-A",
        "space_id": " ",
        "actor": ACTOR,
        "topic": TOPIC,
        "schema_uri": SCHEMA_URI,
        "schema_version": SCHEMA_VERSION,
    }

    outcome = gate.validate(envelope)
    assert outcome.accepted is False
    assert outcome.reason is not None
    assert outcome.reason.startswith(MISSING_BINDINGS)


@test("minimal gate rejects envelopes missing payload hash when body present")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    ledger = ProvisioningLedger()
    _register_device(ledger)
    gate = _build_gate(provisioning=ledger)

    body = b"payload"
    envelope: dict[str, object] = {
        "tenant_id": "tenant-A",
        "space_id": "space-A",
        "device_id": "device-A",
        "actor": ACTOR,
        "topic": TOPIC,
        "schema_uri": SCHEMA_URI,
        "schema_version": SCHEMA_VERSION,
        "sig": "ignored",
    }

    outcome = gate.validate(envelope, body=body)
    assert outcome.accepted is False
    assert outcome.reason == PAYLOAD_HASH_MISSING


@test("minimal gate rejects payload hash mismatches")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    ledger = ProvisioningLedger()
    _register_device(ledger)
    gate = _build_gate(provisioning=ledger)

    body = b"payload"
    envelope = _signed_envelope(body)
    envelope["payload_sha256"] = "0" * 64

    outcome = gate.validate(envelope, body=body)
    assert outcome.accepted is False
    assert outcome.reason == PAYLOAD_HASH_MISMATCH


@test("minimal gate rejects envelopes without signatures")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    ledger = ProvisioningLedger()
    _register_device(ledger)
    gate = _build_gate(provisioning=ledger)

    body = b"payload"
    envelope = _signed_envelope(body)
    envelope.pop("sig")

    outcome = gate.validate(envelope, body=body)
    assert outcome.accepted is False
    assert outcome.reason == SIGNATURE_MISSING


@test("minimal gate rejects envelopes with invalid signatures")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    ledger = ProvisioningLedger()
    _register_device(ledger)
    gate = _build_gate(provisioning=ledger)

    body = b"payload"
    envelope = _signed_envelope(body)
    signature = str(envelope["sig"])
    envelope["sig"] = signature[::-1]

    outcome = gate.validate(envelope, body=body)
    assert outcome.accepted is False
    assert outcome.reason == SIGNATURE_INVALID


@test("minimal gate rejects envelopes when verify key missing from provisioning record")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    ledger = ProvisioningLedger()
    with connection_scope() as connection:
        # Insert device binding
        connection.execute(
            (
                "INSERT INTO st_devices (device_id, tenant_id, space_id, mls_group_id, provisioned_ts) "
                "VALUES (?, ?, ?, ?, ?)"
            ),
            (
                "device-A",
                "tenant-A",
                "space-A",
                "mls-1",
                "2025-09-28T12:00:00Z",
            ),
        )
        # Insert key with blank verify_key to test error handling
        connection.execute(
            (
                "INSERT INTO st_device_keys (device_id, key_version, verify_key, key_state, registered_ts, activated_ts) "
                "VALUES (?, ?, ?, ?, ?, ?)"
            ),
            (
                "device-A",
                "v1",
                "  ",  # Invalid/blank key
                "ACTIVE",
                "2025-09-28T12:00:00Z",
                "2025-09-28T12:00:00Z",
            ),
        )
        connection.commit()

    gate = _build_gate(provisioning=ledger)
    body = b"payload"
    envelope = _signed_envelope(body)

    outcome = gate.validate(envelope, body=body)
    assert outcome.accepted is False
    # With separate key table, blank verify_key results in signature verification failure
    # rather than a specific "missing key" error
    assert outcome.reason == SIGNATURE_INVALID
