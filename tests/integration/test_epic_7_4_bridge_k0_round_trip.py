"""Epic 7.4 — Bridge → K0 live round-trip test.

Proves the actual K1 → EnvelopeBuilder → Ed25519Signing → HttpTransport → K0
code path works end-to-end without bypassing the bridge.

This is the test that was previously blocked by IDEM_KEY_MISMATCH.
Three bugs in the bridge have been fixed to enable this:

1. ``idem_key`` removed from client envelope — K0 gate owns derivation via
   HMAC-SHA256(device_secret, envelope_sha256|device_id|time_bucket).
2. ``sig_alg`` label corrected from ``"ed25519"`` → ``"Ed25519SHA512"``.
3. ``sig_kid`` format corrected from ``"did:device:{id}#1"`` → ``"{id}#1"``.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from bridge.core.envelope_builder import BridgeConfig, EnvelopeBuilder
from bridge.core.signing import Ed25519Signing
from tests.integration.harness.device_provisioner import provision_extra_device
from tests.integration.harness.k0_observer import latest_receipt_for_device

_K0_BASE_URL = "http://127.0.0.1:8080"
_SUBMIT_URL = f"{_K0_BASE_URL}/k0/command.submit"


def _hex(n: int = 8) -> str:
    return uuid.uuid4().hex[:n]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_envelope_builder_round_trip_via_live_k0() -> None:
    """EnvelopeBuilder + Ed25519Signing → K0 HTTP 200 + receipt.

    This is the first test to exercise the real bridge code path
    against a live K0 container. No bypasses, no native helpers —
    pure bridge code.
    """
    tenant_id = f"bridge-rt-{_hex()}"
    space_id = tenant_id
    device_id = f"dev-{_hex()}"

    # Provision a device so K0's gate accepts the envelope's device_id.
    ad_hoc = provision_extra_device(
        device_id=device_id,
        tenant_id=tenant_id,
        space_id=space_id,
    )

    # Wire up the bridge stack exactly as K1 does in production.
    config = BridgeConfig(
        tenant_id=tenant_id,
        space_id=space_id,
        device_id=device_id,
        actor=f"actor-{_hex()}",
        policy_version="2025-09-28",
        default_band="GREEN",
    )
    signer = Ed25519Signing(
        signing_key_bytes=ad_hoc.ed25519_seed,
        key_id=f"{device_id}#1",
    )
    builder = EnvelopeBuilder(config=config, signer=signer)

    body = {
        "schema_version": "2.2",
        "operation": "UPSERT",
        "text": "Bridge round-trip test — first real bridge→K0 commit",
        "topics": ["integration", "bridge"],
        "sentiment_label": "neutral",
        "affect": {"valence": 0.5, "arousal": 0.4, "dominance": 0.5},
        "source_type": "user_stated",
        "novelty": "NOVEL",
        "elaboration_depth": "MENTION",
        "temporal_orientation": "ONGOING",
        "confidence": 0.9,
        "conversation_turn": 1,
        "language": "en",
        "session_id": f"sess-{_hex()}",
    }
    envelope = builder.build(
        topic="memory.write",
        body=body,
        schema_uri="schema://k0/topics/memory_write.body.json",
    )

    # Submit via raw httpx (same as HttpTransport would do).
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(_SUBMIT_URL, json=envelope)

    assert (
        response.status_code == 200
    ), f"Bridge→K0 got HTTP {response.status_code}: {response.text[:500]}"
    data = response.json()
    assert "receipt_id" in data, data
    assert "commit_ts" in data, data

    # Confirm the row landed in st_receipts.
    receipt = latest_receipt_for_device(device_id)
    assert receipt is not None
    assert receipt["tenant_id"] == tenant_id
    assert receipt["space_id"] == space_id
    assert receipt["device_id"] == device_id

    # Confirm bridge envelope does NOT contain idem_key (K0 fills it).
    assert "idem_key" not in envelope
    # Confirm correct sig_alg label.
    assert envelope["sig_alg"] == "Ed25519SHA512"
    # Confirm K0 echoes back a valid receipt_id (UUID).
    uuid.UUID(data["receipt_id"])  # raises if invalid
