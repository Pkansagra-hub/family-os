"""M5.E2.I6 — selfmodel <-> bridge seam.

Per IMPLEMENTATION_PLAN_SELF_MODEL.md M5.E2.I6:

    Validate: submit_command('sync.delta', ...) round-trip with
    stub IBridgeClient; offline -> LocalOutbox -> online drain;
    SSE k0.sync.complete.v1 triggers refresh; signing path uses
    bridge.core.signing.Ed25519Signing.
    Acceptance: bridge integration green; outbox parity verified
    against real LocalOutbox SQLite.

Wires the real ``BridgeAmendmentSyncAdapter`` against:

* the real ``StubBridgeClient`` (records calls)
* the real ``Ed25519Signing`` (production crypto)
* the real ``LocalOutbox`` (SQLite-backed) for offline parity
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from bridge.core.signing import Ed25519Signing
from bridge.sync.local_outbox import LocalOutbox
from bridge.testing.stub_client import StubBridgeClient
from k1.selfmodel.adapters.bridge_amendment_sync import (
    AMENDMENT_DELTA_SCHEMA,
    TOPIC_BRIDGE_SYNC_DELTA,
    TOPIC_K0_SYNC_COMPLETE,
    BridgeAmendmentSyncAdapter,
)
from k1.selfmodel.contracts.constitution import (
    AmendmentProposal,
    AmendmentStatus,
)
from k1.selfmodel.contracts.privacy import PrivacyBand

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _signing() -> Ed25519Signing:
    """Real Ed25519 with a deterministic 32-byte seed for the test."""
    seed = b"\x42" * 32
    return Ed25519Signing(seed, key_id="did:device:test#1")


def _proposal(amendment_id: str = "amd-1") -> AmendmentProposal:
    return AmendmentProposal(
        amendment_id=amendment_id,
        parent_version="v0",
        proposed_by="member_1",
        body={"rule_x": "tighten"},
        status=AmendmentStatus.DRAFT,
        expires_at_ms=0,
    )


# =====================================================================
# submit_delta -> StubBridgeClient.submit_command round-trip
# =====================================================================
async def test_submit_delta_roundtrip_through_stub_bridge() -> None:
    bridge = StubBridgeClient()
    adapter = BridgeAmendmentSyncAdapter(bridge=bridge, signing=_signing())

    sig = await adapter.submit_delta(_proposal(), trace_id="t-1")

    # The stub recorded exactly one submit_command call on sync.delta.
    submit_calls = [c for c in bridge.calls if c[0] == "submit_command"]
    assert len(submit_calls) == 1
    method, args, kwargs = submit_calls[0]
    topic, body = args
    assert topic == TOPIC_BRIDGE_SYNC_DELTA
    assert kwargs["schema_uri"] == AMENDMENT_DELTA_SCHEMA
    assert kwargs["band"] == "GREEN"
    assert kwargs["trace_id"] == "t-1"
    # Signing fields populated by the adapter.
    assert body["amendment_id"] == "amd-1"
    assert body["signature"] == sig
    assert body["signing_key_id"] == "did:device:test#1"


async def test_signature_verifies_with_same_key() -> None:
    """Real Ed25519 signing/verify round-trip."""
    bridge = StubBridgeClient()
    signer = _signing()
    adapter = BridgeAmendmentSyncAdapter(bridge=bridge, signing=signer)

    sig = await adapter.submit_delta(_proposal())
    body = bridge.calls[0][1][1]
    # Re-canonicalise body without the signature/signing_key_id fields
    # (the adapter stamps both *after* signing).
    canonical = {k: v for k, v in body.items() if k not in ("signature", "signing_key_id")}
    canonical_bytes = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert signer.verify(canonical_bytes, sig)


# =====================================================================
# Offline -> LocalOutbox -> online drain (parity check)
# =====================================================================
def test_local_outbox_round_trip(tmp_path: Path) -> None:
    """When the bridge is offline, callers enqueue the canonical body
    into the real ``LocalOutbox``. On reconnect, ``list_pending`` must
    yield exactly what was enqueued."""
    db_path = tmp_path / "outbox.db"
    outbox = LocalOutbox(db_path)
    assert outbox.pending_count() == 0

    body = {
        "schema": AMENDMENT_DELTA_SCHEMA,
        "amendment_id": "amd-offline-1",
        "parent_version": "v0",
        "body": {"rule_x": "tighten"},
        "status": "DRAFT",
    }
    envelope_json = json.dumps(body, sort_keys=True, separators=(",", ":"))

    row_id = outbox.enqueue(envelope_json, TOPIC_BRIDGE_SYNC_DELTA, priority=2)
    assert row_id > 0
    assert outbox.pending_count() == 1

    pending = outbox.list_pending()
    assert len(pending) == 1
    entry = pending[0]
    assert entry.topic == TOPIC_BRIDGE_SYNC_DELTA
    assert entry.priority == 2
    assert entry.status == "PENDING"
    # Round-trip parity: what we read back equals what we enqueued.
    assert json.loads(entry.envelope_json) == body

    # Cleanly close the SQLite handle so tmp_path can be torn down.
    outbox.close()


def test_local_outbox_persists_across_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "outbox.db"

    outbox1 = LocalOutbox(db_path)
    outbox1.enqueue('{"a":1}', TOPIC_BRIDGE_SYNC_DELTA, priority=1)
    outbox1.close()

    outbox2 = LocalOutbox(db_path)
    assert outbox2.pending_count() == 1
    assert outbox2.list_pending()[0].envelope_json == '{"a":1}'
    outbox2.close()


# =====================================================================
# SSE k0.sync.complete.v1 -> refresh_fn
# =====================================================================
class _SSEEvent:
    def __init__(self, topic: str, cursor: str, data: dict, policy_stamp: str = "") -> None:
        self.topic = topic
        self.cursor = cursor
        self.data = data
        self.policy_stamp = policy_stamp


class _SSEStubBridge(StubBridgeClient):
    """StubBridgeClient with a scriptable SSE generator."""

    def __init__(self, events: list[_SSEEvent]) -> None:
        super().__init__()
        self._events = events

    async def subscribe(self, topics, *, cursor=None):  # type: ignore[override]
        self._record("subscribe", topics, cursor=cursor)
        events = list(self._events)
        # Drain into a one-shot async generator that closes after the
        # last event so the SSE loop's reconnect-with-backoff doesn't
        # spin forever inside the test.
        sentinel = self  # capture for closure

        async def gen():
            for e in events:
                yield e
            # Signal the loop to exit by raising CancelledError on the
            # next iteration's "wait forever" — we'll cancel the task
            # from the test.

        return gen()


async def test_sse_event_triggers_refresh_fn_and_ack() -> None:
    refresh_calls: list[tuple[str, dict]] = []

    async def refresh_fn(device_id: str, data: dict) -> None:
        refresh_calls.append((device_id, dict(data)))

    event = _SSEEvent(
        topic=TOPIC_K0_SYNC_COMPLETE,
        cursor="cursor-1",
        data={"device_id": "dev-A", "version": "v1"},
        policy_stamp="ps-1",
    )
    bridge = _SSEStubBridge([event])
    adapter = BridgeAmendmentSyncAdapter(
        bridge=bridge,
        signing=_signing(),
        refresh_fn=refresh_fn,
    )

    await adapter.start_sse()
    # Yield until refresh_fn fires (bounded wait — fail fast on regression).
    for _ in range(50):
        if refresh_calls:
            break
        await asyncio.sleep(0.01)
    await adapter.stop_sse()

    assert refresh_calls == [("dev-A", {"device_id": "dev-A", "version": "v1"})]
    # The adapter ack'd the cursor back to the bridge.
    ack_calls = [c for c in bridge.calls if c[0] == "ack"]
    assert ack_calls and ack_calls[0][1] == (TOPIC_K0_SYNC_COMPLETE, "cursor-1")


async def test_sse_ignores_unrelated_topics() -> None:
    refresh_calls: list[str] = []

    async def refresh_fn(device_id: str, data: dict) -> None:
        refresh_calls.append(device_id)

    event = _SSEEvent(
        topic="k0.something.else.v1",
        cursor="cur-x",
        data={"device_id": "dev-B"},
    )
    bridge = _SSEStubBridge([event])
    adapter = BridgeAmendmentSyncAdapter(
        bridge=bridge,
        signing=_signing(),
        refresh_fn=refresh_fn,
    )

    await adapter.start_sse()
    await asyncio.sleep(0.05)
    await adapter.stop_sse()

    assert refresh_calls == []
