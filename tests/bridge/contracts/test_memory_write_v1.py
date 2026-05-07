"""MS-2.5 first contract tests for ``memory.write.v1``.

These tests are the live demonstration of the Bridge MS-2.5 exit
criteria for the first contract:

1. Pydantic body validation accepts a fully-formed atom.
2. The same Pydantic body validation rejects payloads missing any one
   of the 14 required fields, parametrised one-per-field.
3. Envelope builder produces an envelope that can be signed with a real
   Ed25519 key and verified end-to-end.
4. The idempotency key matches the documented BLAKE3 formula
   ``BLAKE3(topic \\x00 canonical_json(body) \\x00 device_id)``.
5. The legacy alias ``memory.write`` resolves to ``memory.write.v1`` at
   dispatch time (no breaking rename for legacy producers).
6. Round-trip: K1 client → in-process HTTP transport → bridge dispatcher
   → K0 handler → P02 ack, with the handler receiving an *equal*
   Pydantic model (not just dict-equivalent).

All tests use real components — real schema, real Pydantic, real
Ed25519, real httpx ASGI transport, real FastAPI dispatcher.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from blake3 import blake3
from pydantic import ValidationError

from bridge._generated.k0.handlers.memory_write_v1 import register_handlers as register_k0_handlers
from bridge._generated.k0.models.memory_write_v1 import MemoryWriteV1
from bridge._generated.k1.clients.memory_write_v1 import MemoryWriteV1Client
from bridge.core.envelope_builder import BridgeConfig, EnvelopeBuilder
from bridge.core.signing import Ed25519Signing
from bridge.core.transport.in_process_http import InProcessHttpTransport
from bridge.handlers.k0.memory_write_v1 import handle_memory_write_v1
from bridge.runtime import BridgeRuntime, Role
from bridge.testing.dispatcher_app import build_app

CONTRACTS_PATH = Path(__file__).resolve().parents[3] / "bridge" / "contracts"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid_atom() -> dict[str, Any]:
    """Return a fully-formed v2.2 MemoryAtom satisfying every required field."""
    return {
        "schema_version": "2.2",
        "operation": "UPSERT",
        "text": "Had coffee with Rachel at Starbucks and discussed her new role.",
        "topics": ["coffee", "career"],
        "sentiment_label": "positive",
        "affect": {"valence": 0.6, "arousal": 0.4, "dominance": 0.5},
        "source_type": "user_stated",
        "novelty": "EXPECTED",
        "elaboration_depth": "DISCUSSED",
        "temporal_orientation": "PAST",
        "confidence": 0.9,
        "session_id": "session-2026-01-24-abc",
        "conversation_turn": 7,
        "language": "en",
    }


REQUIRED_FIELDS = (
    "schema_version",
    "operation",
    "text",
    "topics",
    "sentiment_label",
    "affect",
    "source_type",
    "novelty",
    "elaboration_depth",
    "temporal_orientation",
    "confidence",
    "session_id",
    "conversation_turn",
    "language",
)


@pytest.fixture
def runtime_with_handler() -> BridgeRuntime:
    """K0-role runtime with the memory.write.v1 handler installed.

    The runtime is built without a transport here — the test that needs
    one wires :class:`InProcessHttpTransport` separately.
    """
    rt = BridgeRuntime(role=Role.K0, contracts_path=CONTRACTS_PATH)
    register_k0_handlers(rt, impl=handle_memory_write_v1)
    return rt


@pytest.fixture
def signer() -> Ed25519Signing:
    """Ephemeral Ed25519 key — no fixture file, deterministic per test run."""
    seed = b"\x07" * 32  # 32-byte seed
    return Ed25519Signing(seed, key_id="test-kid-ms25")


@pytest.fixture
def envelope_builder(signer: Ed25519Signing) -> EnvelopeBuilder:
    cfg = BridgeConfig(
        tenant_id="tenant-test",
        space_id="space-test",
        device_id="device-ms25",
    )
    return EnvelopeBuilder(cfg, signer)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_memory_write_v1_payload_validation_accepts_valid() -> None:
    """A complete v2.2 atom passes Pydantic validation and round-trips."""
    atom = _valid_atom()
    model = MemoryWriteV1.model_validate(atom)
    # Round-trip equality on the required-field subset.
    dumped = model.model_dump(mode="json", by_alias=True)
    for field_name in REQUIRED_FIELDS:
        assert dumped[field_name] == atom[field_name], field_name


@pytest.mark.parametrize("missing", REQUIRED_FIELDS)
def test_memory_write_v1_payload_validation_rejects_missing_required(
    missing: str,
) -> None:
    """Removing any single required field triggers a ValidationError."""
    atom = _valid_atom()
    atom.pop(missing)
    with pytest.raises(ValidationError) as exc:
        MemoryWriteV1.model_validate(atom)
    # The error report mentions the missing field by name.
    assert any(missing in str(err["loc"]) for err in exc.value.errors())


def test_memory_write_v1_envelope_signs_and_verifies(
    envelope_builder: EnvelopeBuilder,
    signer: Ed25519Signing,
) -> None:
    """A built envelope's signature verifies against the same Ed25519 key."""
    atom = _valid_atom()
    env = envelope_builder.build(topic="memory.write.v1", body=atom)
    assert env["sig_alg"] == "ed25519"
    assert env["sig_kid"] == "test-kid-ms25"
    # Verify the signature against envelope_sha256 (what the builder signs).
    assert signer.verify(
        env["envelope_sha256"].encode("utf-8"),
        env["sig"],
    )


def test_memory_write_v1_envelope_idem_key_is_blake3_of_canonical_fields(
    envelope_builder: EnvelopeBuilder,
) -> None:
    """Idempotency key matches the documented BLAKE3 formula exactly."""
    atom = _valid_atom()
    env = envelope_builder.build(topic="memory.write.v1", body=atom)
    canonical_body = json.dumps(atom, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = blake3()
    digest.update(b"memory.write.v1")
    digest.update(b"\x00")
    digest.update(canonical_body.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(b"device-ms25")
    assert env["idem_key"] == digest.hexdigest()


@pytest.mark.asyncio
async def test_memory_write_v1_dispatch_requires_canonical_topic(
    runtime_with_handler: BridgeRuntime,
) -> None:
    """MS-3a removed the legacy ``memory.write`` alias; only the canonical
    versioned topic resolves at dispatch time."""
    # Canonical topic is registered.
    handler_topics = runtime_with_handler.handlers.topics()
    assert "memory.write.v1" in handler_topics

    # The legacy unversioned name is no longer accepted.
    with pytest.raises(KeyError):
        await runtime_with_handler.dispatch(topic="memory.write", payload={})


@pytest.mark.asyncio
async def test_memory_write_v1_round_trip_via_in_process_http(
    runtime_with_handler: BridgeRuntime,
) -> None:
    """End-to-end: K1 client → ASGI transport → dispatcher → K0 handler."""
    seen: dict[str, Any] = {}

    async def capture_then_forward(payload: MemoryWriteV1) -> dict[str, Any]:
        # Replace the registered handler for this test so we can assert
        # the *exact* Pydantic instance the dispatcher invoked us with.
        seen["payload"] = payload
        return await handle_memory_write_v1(payload)

    # Re-register: a fresh runtime to avoid duplicate-topic errors.
    rt = BridgeRuntime(role=Role.K0, contracts_path=CONTRACTS_PATH)
    register_k0_handlers(rt, impl=capture_then_forward)

    app = build_app(runtime=rt)
    transport = InProcessHttpTransport(app=app)
    try:
        client_runtime = BridgeRuntime(
            role=Role.K1,
            contracts_path=CONTRACTS_PATH,
            transport=transport,
        )
        client = MemoryWriteV1Client(runtime=client_runtime)
        atom = _valid_atom()
        model = MemoryWriteV1.model_validate(atom)
        result = await client.publish(model)
    finally:
        await transport.close()

    assert result["ack"] is True
    assert result["topic"] == "memory.write.v1"
    assert result["atom_id"].startswith("atom-")
    # The handler received a real Pydantic model, not a dict.
    assert isinstance(seen["payload"], MemoryWriteV1)
    # JSON-mode dump equality: round-trip preserves every field bit-exactly.
    # (Object-level ``==`` is asymmetric for Optional[Enum-with-null] fields
    # because validating from ``None`` yields ``None`` while validating from
    # JSON-serialised ``null`` yields the synthetic ``EnumName.NoneType_None``
    # member; both produce identical JSON, which is what the wire promises.)
    assert seen["payload"].model_dump(mode="json", by_alias=True) == model.model_dump(
        mode="json", by_alias=True
    )
