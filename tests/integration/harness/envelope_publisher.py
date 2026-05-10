"""Standalone envelope publisher for harness tests.

Mirrors :meth:`tests.integration.harness.k1_handle.K1Handle.publish_memory_write_v1_native`
but without requiring a spawned K1 process. Used by Epic 7.2 partition
isolation tests that need to publish from *ad-hoc* provisioned devices
bound to specific ``(tenant_id, space_id)`` pairs (one device per
scope-band space — the K0 ``minimal_gate`` enforces
``SPACE_TENANT_MISMATCH`` against the device's provisioned binding).

Wire shape mirrors the K0 deploy reference scripts at
``k0/deploy/scripts/events/family_life_events.py`` exactly: bare
``memory.write`` topic, ``sig_alg="Ed25519SHA512"``,
``sig_kid="{device_id}#1"``, no client-supplied ``idem_key``, signature
over ``canonical_envelope(envelope)`` after ``envelope_sha256`` is set.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from nacl.signing import SigningKey

from k0.security import (
    canonical_envelope,
    canonical_json,
    compute_envelope_sha256,
    hash_payload,
)
from k0.security.crypto import encode_base64url


async def publish_memory_write_native(
    *,
    k0_base_url: str,
    tenant_id: str,
    space_id: str,
    device_id: str,
    actor: str,
    signing_seed: bytes,
    text: str,
    topics: list[str] | None = None,
    band: str = "GREEN",
    schema_uri: str = "schema://k0/topics/memory_write.body.json",
    schema_version: str = "2.2",
    policy_version: str = "2025-09-28",
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build, sign, and submit a ``memory.write`` envelope over HTTP.

    Returns ``{"http_status": int, "body": dict, "envelope_sha256": str,
    "cognitive_trace_id": str}``.
    """
    body: dict[str, Any] = {
        "schema_version": "2.2",
        "operation": "UPSERT",
        "text": text,
        "topics": topics or ["integration"],
        "sentiment_label": "neutral",
        "affect": {"valence": 0.5, "arousal": 0.4, "dominance": 0.5},
        "source_type": "user_stated",
        "novelty": "NOVEL",
        "elaboration_depth": "MENTION",
        "temporal_orientation": "ONGOING",
        "confidence": 0.9,
        "conversation_turn": 1,
        "language": "en",
        "session_id": f"sess-{actor}",
    }
    if extra_body:
        body.update(extra_body)

    body_bytes = canonical_json(body).encode("utf-8")
    payload_sha256 = hash_payload(body_bytes)

    envelope: dict[str, Any] = {
        "cognitive_trace_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "space_id": space_id,
        "topic": "memory.write",
        "schema_uri": schema_uri,
        "schema_version": schema_version,
        "actor": actor,
        "device_id": device_id,
        "band": band,
        "policy_version": policy_version,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "payload_sha256": payload_sha256,
        "sig_alg": "Ed25519SHA512",
        "sig_kid": f"{device_id}#1",
        "body": body,
        "policy": {"abac": {"roles": ["guest"]}},
    }
    envelope["envelope_sha256"] = compute_envelope_sha256(envelope)
    signing_key = SigningKey(signing_seed)
    envelope["sig"] = encode_base64url(signing_key.sign(canonical_envelope(envelope)).signature)

    url = f"{k0_base_url.rstrip('/')}/k0/command.submit"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            content=json.dumps(envelope).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
    try:
        data = response.json()
    except Exception:  # noqa: BLE001
        data = {"raw_text": response.text}
    return {
        "http_status": response.status_code,
        "body": data,
        "envelope_sha256": envelope["envelope_sha256"],
        "cognitive_trace_id": envelope["cognitive_trace_id"],
    }
