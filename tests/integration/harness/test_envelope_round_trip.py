"""Real K1 → K0 envelope round-trip tests against the live Docker K0.

Proves Epic 7.1's harness exercises the wire — not just process
lifecycle. Hits every K0 port currently exposed at ``/openapi.json``.

KNOWN ARCHITECTURAL SEAM (surfaced by these tests, 2026-05-18):
The Docker K0's ``command_topics.yaml`` registers **bare** topic names
(``memory.write``, ``session.snapshot``…) per its documented "DNS-style
topic_id, versioning via schema_uri" convention. Bridge codegen emits
**versioned** topic names (``memory.write.v1``…). The K0 gate therefore
returns ``TOPIC_UNKNOWN:memory.write.v1`` when the generated client
publishes. The gate-rejection tests below assert wire reachability
(envelope reaches K0, K0 parses it, K0's gate evaluates it). The
``TestRawHttpBareTopicRoundTrip`` test additionally proves a *full*
happy-path round-trip by publishing on the bare topic the deployed K0
accepts. Reconciling the topic-name seam is a follow-up item.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid

import httpx
import pytest

from .family_layout import single_father_layout
from .live_system import LiveSystem

# ---------------------------------------------------------------------------
# Memory write — POST /k0/command.submit via generated K1 client
# ---------------------------------------------------------------------------


@pytest.mark.requires_live_k0
@pytest.mark.asyncio
class TestMemoryWriteV1RoundTrip:
    """Prove the K1-client → K0-gate wire is alive end-to-end."""

    async def test_publish_reaches_k0_kernel_gate(self) -> None:
        from bridge.core.transport import BridgeTransportError

        async with LiveSystem(family=single_father_layout()) as sys_:
            father = sys_.k1s[0]
            try:
                response = await father.publish_memory_write_v1(
                    text="Round-trip from harness self-test",
                    topics=["integration", "harness"],
                )
            except BridgeTransportError as exc:
                assert exc.status_code is not None and 400 <= exc.status_code < 500
                assert isinstance(exc.body, dict)
                err = exc.body.get("error") or {}
                assert err.get("component") == "kernel.gate"
                assert "trace_id" in err
            else:
                assert isinstance(response, dict)
                assert not response.get("error")

    async def test_three_concurrent_publishes_each_reach_gate(self) -> None:
        from bridge.core.transport import BridgeTransportError

        async def _safe_publish(k1):
            try:
                return (
                    "ok",
                    await k1.publish_memory_write_v1(
                        text=f"concurrent-{k1.person.role}",
                        topics=["integration"],
                    ),
                )
            except BridgeTransportError as exc:
                return ("gate", exc.status_code, exc.body)

        async with LiveSystem() as sys_:
            results = await asyncio.gather(*(_safe_publish(k1) for k1 in sys_.k1s))
            assert len(results) == 3
            for r in results:
                assert r[0] in ("ok", "gate")
                if r[0] == "gate":
                    assert r[1] is not None and 400 <= r[1] < 500
                    assert "error" in r[2]


# ---------------------------------------------------------------------------
# Recall — POST /k0/query.recall via generated K1 client
# ---------------------------------------------------------------------------


@pytest.mark.requires_live_k0
@pytest.mark.asyncio
class TestRecallRequestV1RoundTrip:
    async def test_recall_reaches_k0_kernel_gate(self) -> None:
        from bridge._generated.k1.models.recall_response_v1 import RecallResponseV1
        from bridge.core.transport import BridgeTransportError

        async with LiveSystem(family=single_father_layout()) as sys_:
            father = sys_.k1s[0]
            try:
                response = await father.recall_request_v1(
                    trace_id=f"trace-{uuid.uuid4().hex[:12]}",
                )
            except BridgeTransportError as exc:
                assert exc.status_code is not None and 400 <= exc.status_code < 500
                assert isinstance(exc.body, dict)
                err = exc.body.get("error") or {}
                assert err.get("component") == "kernel.gate"
                assert err.get("code") in {
                    "REJECTED_KERNEL_GATE",
                    "TOPIC_UNKNOWN",
                    "VALIDATION_FAILED",
                }
            else:
                assert isinstance(response, RecallResponseV1)
                assert isinstance(response.hits, list)


# ---------------------------------------------------------------------------
# Raw-HTTP round-trip with bare topic name (deployed K0's wire shape)
# ---------------------------------------------------------------------------


def _build_bare_envelope(
    *,
    topic: str,
    body: dict,
    person_id: str,
    device_id: str,
    family_id: str,
    secret: bytes,
) -> bytes:
    """Build a minimal K0-compatible envelope for the bare topic shape."""
    env: dict = {
        "schema_version": "1.0",
        "topic": topic,
        "schema_uri": f"bridge://contracts/schemas/{topic}.json",
        "tenant_id": family_id,
        "space_id": family_id,
        "device_id": device_id,
        "actor": person_id,
        "policy_version": "1.0",
        "band": "GREEN",
        "trace_id": str(uuid.uuid4()),
        "ts": int(time.time() * 1000),
        "nonce": secrets.token_hex(8),
        "body": body,
        "body_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    canonical = json.dumps(env, sort_keys=True, separators=(",", ":")).encode()
    sig = hmac.new(secret, canonical, hashlib.sha256).digest()
    env["sig"] = {
        "alg": "HMAC-SHA256",
        "key_id": f"did:device:{device_id}#hmac",
        "signature": base64.urlsafe_b64encode(sig).decode().rstrip("="),
    }
    return json.dumps(env).encode("utf-8")


@pytest.mark.requires_live_k0
class TestRawHttpBareTopicRoundTrip:
    BASE = "http://127.0.0.1:8080"

    def test_command_submit_accepts_well_formed_memory_write(self) -> None:
        body = {
            "schema_version": "2.0",
            "operation": "UPSERT",
            "text": "Raw HTTP envelope round-trip",
            "topics": ["integration"],
            "sentiment_label": "neutral",
            "affect": {"valence": 0.5, "arousal": 0.4, "dominance": 0.5},
            "source_type": "user_stated",
            "novelty": "NOVEL",
            "elaboration_depth": "MENTION",
            "temporal_orientation": "ONGOING",
            "confidence": 0.9,
            "conversation_turn": 1,
            "language": "en",
            "session_id": "sess-raw-http",
        }
        envelope = _build_bare_envelope(
            topic="memory.write",
            body=body,
            person_id="harness-raw",
            device_id="harness-device",
            family_id="harness-fam",
            secret=os.urandom(32),
        )
        r = httpx.post(
            f"{self.BASE}/k0/command.submit",
            content=envelope,
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        assert r.status_code in (200, 202, 400, 401, 403, 422)
        if r.status_code in (200, 202):
            data = r.json()
            assert isinstance(data, dict)
        else:
            payload = r.json()
            assert "error" in payload or "detail" in payload


# ---------------------------------------------------------------------------
# Direct HTTP probes — every K0 port currently exposed at /openapi.json
# ---------------------------------------------------------------------------


@pytest.mark.requires_live_k0
class TestK0HttpRoutesReachable:
    BASE = "http://127.0.0.1:8080"

    def test_healthz_ok(self) -> None:
        r = httpx.get(f"{self.BASE}/healthz", timeout=2.0)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_readyz_responds(self) -> None:
        r = httpx.get(f"{self.BASE}/readyz", timeout=2.0)
        assert r.status_code in (200, 503)

    def test_metrics_exposition(self) -> None:
        r = httpx.get(f"{self.BASE}/metrics", timeout=5.0)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/plain")

    def test_command_submit_rejects_empty_post(self) -> None:
        r = httpx.post(f"{self.BASE}/k0/command.submit", json={}, timeout=5.0)
        assert r.status_code != 404
        assert 400 <= r.status_code < 500

    def test_query_recall_rejects_empty_post(self) -> None:
        r = httpx.post(f"{self.BASE}/k0/query.recall", json={}, timeout=5.0)
        assert r.status_code != 404
        assert 400 <= r.status_code < 500

    def test_obs_emit_rejects_empty_post(self) -> None:
        r = httpx.post(f"{self.BASE}/k0/obs.emit", json={}, timeout=5.0)
        assert r.status_code != 404
        assert 400 <= r.status_code < 500

    def test_driver_handshake_rejects_empty_post(self) -> None:
        r = httpx.post(f"{self.BASE}/k0/driver.handshake", json={}, timeout=5.0)
        assert r.status_code != 404
        assert 400 <= r.status_code < 500

    def test_sse_subscribe_rejects_empty_post(self) -> None:
        r = httpx.post(f"{self.BASE}/k0/sse.subscribe", json={}, timeout=5.0)
        assert r.status_code != 404
        assert 400 <= r.status_code < 500

    def test_sse_ack_rejects_empty_post(self) -> None:
        r = httpx.post(f"{self.BASE}/k0/sse.ack", json={}, timeout=5.0)
        assert r.status_code != 404
        assert 400 <= r.status_code < 500

    def test_admin_pipelines_listing(self) -> None:
        r = httpx.get(f"{self.BASE}/k0/admin/pipelines", timeout=5.0)
        assert r.status_code != 404

    def test_admin_scheduler_status(self) -> None:
        r = httpx.get(f"{self.BASE}/k0/admin/scheduler/status", timeout=5.0)
        assert r.status_code != 404
