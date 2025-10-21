"""Ward regression suite for the minimal gate envelope validation pipeline."""

import base64
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Tuple, cast

from nacl.signing import SigningKey
from ward import fixture, test  # type: ignore[attr-defined]

from k0.gate import MinimalGate, SchemaRecord, SchemaRegistry
from k0.gate.minimal_gate import (
    CANONICALIZATION_ERROR,
    DEVICE_NOT_PROVISIONED,
    IDEM_KEY_INVALID,
    IDEM_KEY_MISMATCH,
    LIMIT_EXCEEDED,
    MISSING_BINDINGS,
    PAYLOAD_HASH_MISMATCH,
    PAYLOAD_HASH_MISSING,
    SCHEMA_BLOCKED,
    SCHEMA_NOT_ACTIVE,
    SCHEMA_SUNSET,
    SIGNATURE_INVALID,
    SIGNATURE_MISSING,
    SPACE_MISMATCH,
)
from k0.idem import derive_idem_key
from k0.security import canonical_envelope, canonical_json, hash_payload
from k0.storage.provisioning import DeviceKey, ProvisionedDevice, ProvisioningLedger

EXAMPLES_DIR = (
    Path(__file__).resolve().parents[2] / "contracts" / "jsonschema" / "examples"
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def remove_payload_hash(envelope: Dict[str, Any]) -> None:
    envelope.pop("payload_sha256", None)


def remove_signature(envelope: Dict[str, Any]) -> None:
    envelope.pop("sig", None)


class StubSchemaRegistry(SchemaRegistry):
    def __init__(self, records: Dict[Tuple[str, str], SchemaRecord]) -> None:
        super().__init__()
        self._records = records

    def get(
        self,
        uri: str,
        version: str,
        *,
        connection: object | None = None,
    ) -> SchemaRecord:
        del connection
        try:
            return self._records[(uri, version)]
        except KeyError as exc:
            raise KeyError(uri) from exc


class StubProvisioningLedger(ProvisioningLedger):
    def __init__(
        self, record: ProvisionedDevice | None, key: DeviceKey | None = None
    ) -> None:
        super().__init__(cache_size=16)
        self._record = record
        self._key = key

    def lookup(
        self,
        tenant_id: str,
        space_id: str,
        device_id: str,
        *,
        connection: object | None = None,
    ) -> ProvisionedDevice | None:
        if self._record is None:
            return None
        if self._record.device_id != device_id:
            return None
        return self._record

    def get_keys(
        self,
        device: ProvisionedDevice,
        *,
        states: list[str] | None = None,
        connection: object | None = None,
    ) -> list[DeviceKey]:
        if self._key is None:
            return []
        if states is not None and self._key.key_state not in states:
            return []
        return [self._key]


@fixture
def example_envelope() -> tuple[Dict[str, Any], bytes]:
    path = EXAMPLES_DIR / "envelope.snapshot.json"
    data = json.loads(path.read_text())
    body_bytes = canonical_json(data["body"]).encode("utf-8")
    envelope: Dict[str, Any] = {
        key: value for key, value in data.items() if key != "body"
    }
    envelope["payload_sha256"] = hash_payload(body_bytes)
    envelope.pop("idem_key", None)
    envelope.pop("sig", None)
    return envelope, body_bytes


@fixture
def gate_context(example_envelope: Any = example_envelope) -> Dict[str, Any]:
    base_envelope, body = cast(tuple[Dict[str, Any], bytes], example_envelope)
    signing_key = SigningKey.generate()
    verify_key_b64 = _b64url(bytes(signing_key.verify_key))
    device_record = ProvisionedDevice(
        device_id=str(base_envelope["device_id"]),
        tenant_id=str(base_envelope["tenant_id"]),
        space_id=str(base_envelope["space_id"]),
        mls_group_id="mls-group-1",
        provisioned_ts="2025-09-28T12:00:00Z",
    )
    # Create device key separate from provisioned device (post Issue 8.2.1 refactor)
    device_key = DeviceKey(
        device_id=str(base_envelope["device_id"]),
        key_version="v1",
        verify_key=verify_key_b64,
        key_state="ACTIVE",
        registered_ts="2025-09-28T11:00:00Z",
        activated_ts="2025-09-28T12:00:00Z",
    )
    schema_key = (
        str(base_envelope["schema_uri"]),
        str(base_envelope["schema_version"]),
    )
    return {
        "base_envelope": deepcopy(base_envelope),
        "body": body,
        "signing_key": signing_key,
        "device_record": device_record,
        "device_key": device_key,
        "schema_key": schema_key,
    }


def signed_envelope(
    context: Dict[str, Any],
    mutate: Callable[[Dict[str, Any]], None] | None = None,
) -> Dict[str, Any]:
    envelope: Dict[str, Any] = deepcopy(context["base_envelope"])
    if mutate is not None:
        mutate(envelope)
    envelope.pop("sig", None)
    signature = context["signing_key"].sign(canonical_envelope(envelope)).signature
    envelope["sig"] = _b64url(signature)
    return envelope


_UNSPECIFIED = object()


def make_gate(
    context: Dict[str, Any],
    *,
    registry_records: Dict[Tuple[str, str], SchemaRecord] | None = None,
    device_record: ProvisionedDevice | None | object = _UNSPECIFIED,
    device_key: DeviceKey | None | object = _UNSPECIFIED,
    max_envelope_bytes: int | None = None,
    max_body_bytes: int | None = None,
) -> MinimalGate:
    if registry_records is None:
        uri, version = context["schema_key"]
        registry_records = {
            (uri, version): SchemaRecord(
                uri=uri,
                version=version,
                sha256="deadbeef" * 8,
                status="ACTIVE",
            )
        }
    if device_record is _UNSPECIFIED:
        provisioned = cast(ProvisionedDevice, context["device_record"])
    else:
        provisioned = cast(ProvisionedDevice | None, device_record)
    if device_key is _UNSPECIFIED:
        key = cast(DeviceKey, context.get("device_key"))
    else:
        key = cast(DeviceKey | None, device_key)
    provisioning = StubProvisioningLedger(provisioned, key)
    registry = StubSchemaRegistry(registry_records)
    kwargs: Dict[str, int] = {}
    if max_envelope_bytes is not None:
        kwargs["max_envelope_bytes"] = max_envelope_bytes
    if max_body_bytes is not None:
        kwargs["max_body_bytes"] = max_body_bytes
    return MinimalGate(provisioning=provisioning, registry=registry, **kwargs)


@test("minimal gate accepts canonical example envelope")
def _(gate_context: Any = gate_context) -> None:
    gate = make_gate(gate_context)
    envelope = signed_envelope(gate_context)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is True
    assert outcome.reason is None
    expected = derive_idem_key(
        envelope, payload_hash=hash_payload(gate_context["body"])
    )
    assert outcome.idem_key == expected
    assert envelope["idem_key"] == expected


@test("envelope size limit is enforced")
def _(gate_context: Any = gate_context) -> None:
    envelope = signed_envelope(gate_context)
    size_limit = len(canonical_json(envelope).encode("utf-8")) - 1
    gate = make_gate(gate_context, max_envelope_bytes=size_limit)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == f"{LIMIT_EXCEEDED}:envelope"


@test("body size limit is enforced")
def _(gate_context: Any = gate_context) -> None:
    envelope = signed_envelope(gate_context)
    limit = len(gate_context["body"]) - 1
    gate = make_gate(gate_context, max_body_bytes=limit)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == f"{LIMIT_EXCEEDED}:body"


@test("unknown schemas are rejected")
def _(gate_context: Any = gate_context) -> None:
    envelope = signed_envelope(gate_context)
    empty_registry: Dict[Tuple[str, str], SchemaRecord] = {}
    gate = make_gate(gate_context, registry_records=empty_registry)
    uri, version = gate_context["schema_key"]
    outcome = gate.validate(envelope, gate_context["body"])
    expected = f"{SCHEMA_NOT_ACTIVE}:{uri}@{version}"
    assert outcome.accepted is False
    assert outcome.reason == expected


@test("blocked schemas are denied")
def _(gate_context: Any = gate_context) -> None:
    uri, version = gate_context["schema_key"]
    registry = {
        (uri, version): SchemaRecord(
            uri=uri,
            version=version,
            sha256="deadbeef" * 8,
            status="BLOCKED",
        )
    }
    envelope = signed_envelope(gate_context)
    gate = make_gate(gate_context, registry_records=registry)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == f"{SCHEMA_BLOCKED}:{uri}@{version}"


@test("deprecated schemas map to sunset reason")
def _(gate_context: Any = gate_context) -> None:
    uri, version = gate_context["schema_key"]
    registry = {
        (uri, version): SchemaRecord(
            uri=uri,
            version=version,
            sha256="deadbeef" * 8,
            status="DEPRECATED",
        )
    }
    envelope = signed_envelope(gate_context)
    gate = make_gate(gate_context, registry_records=registry)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == f"{SCHEMA_SUNSET}:{uri}@{version}"


@test("payload hash mismatch is detected")
def _(gate_context: Any = gate_context) -> None:
    envelope = signed_envelope(
        gate_context,
        mutate=lambda env: env.__setitem__("payload_sha256", "0" * 64),
    )
    gate = make_gate(gate_context)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == PAYLOAD_HASH_MISMATCH


@test("missing payload hash when body present is rejected")
def _(gate_context: Any = gate_context) -> None:
    envelope = signed_envelope(gate_context, mutate=remove_payload_hash)
    gate = make_gate(gate_context)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == PAYLOAD_HASH_MISSING


@test("payload hash provided without body fails")
def _(gate_context: Any = gate_context) -> None:
    envelope = signed_envelope(gate_context)
    gate = make_gate(gate_context)
    outcome = gate.validate(envelope, None)
    assert outcome.accepted is False
    assert outcome.reason == PAYLOAD_HASH_MISMATCH


@test("signature failures are surfaced")
def _(gate_context: Any = gate_context) -> None:
    envelope = signed_envelope(gate_context)
    envelope["sig"] = _b64url(b"\x00" * 64)
    gate = make_gate(gate_context)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == SIGNATURE_INVALID


@test("mismatched client-provided idem key is rejected")
def _(gate_context: Dict[str, Any] = gate_context) -> None:
    def _override_idem_key(env: Dict[str, Any]) -> None:
        env["idem_key"] = "0" * 64

    envelope = signed_envelope(gate_context, mutate=_override_idem_key)
    gate = make_gate(gate_context)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == IDEM_KEY_MISMATCH


@test("invalid client idem key format is rejected")
def _(gate_context: Dict[str, Any] = gate_context) -> None:
    def _bad_idem_key(env: Dict[str, Any]) -> None:
        env["idem_key"] = "bad-key"

    envelope = signed_envelope(gate_context, mutate=_bad_idem_key)
    gate = make_gate(gate_context)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == IDEM_KEY_INVALID


@test("missing signature is rejected")
def _(gate_context: Any = gate_context) -> None:
    envelope = signed_envelope(gate_context)
    remove_signature(envelope)
    gate = make_gate(gate_context)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == SIGNATURE_MISSING


@test("missing actor bindings are detected")
def _(gate_context: Any = gate_context) -> None:
    def _clear_device(env: Dict[str, Any]) -> None:
        env["device_id"] = ""

    envelope = signed_envelope(gate_context, mutate=_clear_device)
    gate = make_gate(gate_context)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == f"{MISSING_BINDINGS}:device_id"


@test("non-provisioned devices are rejected")
def _(gate_context: Any = gate_context) -> None:
    envelope = signed_envelope(gate_context)
    gate = make_gate(gate_context, device_record=None)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == DEVICE_NOT_PROVISIONED


@test("space mismatches are surfaced")
def _(gate_context: Any = gate_context) -> None:
    base = gate_context["device_record"]
    mismatched = ProvisionedDevice(
        device_id=base.device_id,
        tenant_id=base.tenant_id,
        space_id="other-space",
        mls_group_id=base.mls_group_id,
        provisioned_ts=base.provisioned_ts,
    )
    envelope = signed_envelope(gate_context)
    gate = make_gate(gate_context, device_record=mismatched)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == SPACE_MISMATCH


@test("blank verify keys are rejected")
def _(gate_context: Any = gate_context) -> None:
    base_key = gate_context["device_key"]
    blank_key = DeviceKey(
        device_id=base_key.device_id,
        key_version=base_key.key_version,
        verify_key="   ",
        key_state=base_key.key_state,
        registered_ts=base_key.registered_ts,
        activated_ts=base_key.activated_ts,
    )
    envelope = signed_envelope(gate_context)
    gate = make_gate(gate_context, device_key=blank_key)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    # Blank keys cause signature verification to fail (ValueError from VerifyKey)
    assert outcome.reason == SIGNATURE_INVALID


@test("non-serialisable envelopes trigger canonicalisation errors")
def _(gate_context: Any = gate_context) -> None:
    envelope = signed_envelope(gate_context)
    envelope["extra"] = object()
    gate = make_gate(gate_context)
    outcome = gate.validate(envelope, gate_context["body"])
    assert outcome.accepted is False
    assert outcome.reason == CANONICALIZATION_ERROR
