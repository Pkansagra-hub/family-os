"""M4.E3 — BridgeAmendmentSyncAdapter tests."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

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
from k1.selfmodel.contracts.privacy import BlackBandLeakError, PrivacyBand


# ---------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------
class FakeSigning:
    key_id = "test-key-1"

    def __init__(self) -> None:
        self.calls: list[bytes] = []

    def sign(self, payload: bytes) -> str:
        self.calls.append(payload)
        return f"sig_{len(payload)}"


class FakeBridge:
    def __init__(self, sse_events: list[Any] | None = None) -> None:
        self.submit_calls: list[dict[str, Any]] = []
        self.ack_calls: list[tuple[str, str]] = []
        self._sse_events = list(sse_events or [])

    async def submit_command(self, topic, body, *, schema_uri, band, trace_id=None):
        self.submit_calls.append(
            {
                "topic": topic,
                "body": body,
                "schema_uri": schema_uri,
                "band": band,
                "trace_id": trace_id,
            }
        )

    def subscribe(self, topics, *, cursor=None):
        events = list(self._sse_events)

        async def gen():
            for e in events:
                yield e
            # Block forever after to mimic open SSE stream.
            await asyncio.Event().wait()

        return gen()

    async def ack(self, topic: str, cursor: str) -> None:
        self.ack_calls.append((topic, cursor))


class FakeBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish_simple(self, topic, body):
        self.published.append((topic, body))


class FakeEvent:
    def __init__(self, topic, cursor, data, policy_stamp="ps-1"):
        self.topic = topic
        self.cursor = cursor
        self.data = data
        self.policy_stamp = policy_stamp


def _proposal(**overrides) -> AmendmentProposal:
    base = dict(
        amendment_id="amd_1",
        parent_version="v0",
        proposed_by="member_1",
        body={"rule_x": "tighten"},
        status=AmendmentStatus.DRAFT,
        expires_at_ms=0,
    )
    base.update(overrides)
    return AmendmentProposal(**base)


# ---------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------
def test_constructor_requires_bridge() -> None:
    with pytest.raises(ValueError):
        BridgeAmendmentSyncAdapter(bridge=None, signing=FakeSigning())


def test_constructor_requires_signing() -> None:
    with pytest.raises(ValueError):
        BridgeAmendmentSyncAdapter(bridge=FakeBridge(), signing=None)


# ---------------------------------------------------------------------
# submit_delta — happy path
# ---------------------------------------------------------------------
async def test_submit_delta_signs_and_submits() -> None:
    bridge = FakeBridge()
    signing = FakeSigning()
    adapter = BridgeAmendmentSyncAdapter(bridge=bridge, signing=signing)

    sig = await adapter.submit_delta(_proposal(), trace_id="t1")

    assert sig.startswith("sig_")
    assert len(bridge.submit_calls) == 1
    call = bridge.submit_calls[0]
    assert call["topic"] == TOPIC_BRIDGE_SYNC_DELTA
    assert call["schema_uri"] == AMENDMENT_DELTA_SCHEMA
    assert call["band"] == "GREEN"
    assert call["trace_id"] == "t1"
    body = call["body"]
    assert body["amendment_id"] == "amd_1"
    assert body["signature"] == sig
    assert body["signing_key_id"] == "test-key-1"


async def test_submit_delta_canonical_json_is_deterministic() -> None:
    signing = FakeSigning()
    adapter1 = BridgeAmendmentSyncAdapter(bridge=FakeBridge(), signing=signing)
    adapter2 = BridgeAmendmentSyncAdapter(bridge=FakeBridge(), signing=FakeSigning())

    await adapter1.submit_delta(_proposal())
    await adapter2.submit_delta(_proposal())

    # Both adapters signed the exact same canonical bytes.
    assert signing.calls and adapter2._signing.calls  # type: ignore[attr-defined]
    assert signing.calls[0] == adapter2._signing.calls[0]  # type: ignore[attr-defined]
    # And those bytes parse to a dict containing our amendment.
    parsed = json.loads(signing.calls[0])
    assert parsed["amendment_id"] == "amd_1"


async def test_submit_delta_rejects_none_proposal() -> None:
    adapter = BridgeAmendmentSyncAdapter(bridge=FakeBridge(), signing=FakeSigning())
    with pytest.raises(ValueError):
        await adapter.submit_delta(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# submit_delta — E3 invariant
# ---------------------------------------------------------------------
async def test_submit_delta_with_black_band_raises_before_submit() -> None:
    bridge = FakeBridge()
    adapter = BridgeAmendmentSyncAdapter(bridge=bridge, signing=FakeSigning())
    with pytest.raises(BlackBandLeakError):
        await adapter.submit_delta(_proposal(), band=PrivacyBand.BLACK)
    # Bridge must not have been touched.
    assert bridge.submit_calls == []


# ---------------------------------------------------------------------
# SSE handler
# ---------------------------------------------------------------------
async def test_sse_event_refreshes_publishes_and_acks() -> None:
    refresh_calls: list[tuple[str, dict[str, Any]]] = []

    async def refresh(device_id, data):
        refresh_calls.append((device_id, data))

    event = FakeEvent(
        topic=TOPIC_K0_SYNC_COMPLETE,
        cursor="cur-1",
        data={"device_id": "dev-A", "constitution_version": "v1"},
    )
    bus = FakeBus()
    bridge = FakeBridge(sse_events=[event])
    adapter = BridgeAmendmentSyncAdapter(
        bridge=bridge, signing=FakeSigning(), local_bus=bus, refresh_fn=refresh
    )

    await adapter.start_sse()
    # Allow the SSE loop to consume the event.
    for _ in range(50):
        if refresh_calls and bridge.ack_calls:
            break
        await asyncio.sleep(0.01)
    await adapter.stop_sse()

    assert refresh_calls == [("dev-A", {"device_id": "dev-A", "constitution_version": "v1"})]
    assert bridge.ack_calls == [(TOPIC_K0_SYNC_COMPLETE, "cur-1")]
    assert bus.published and bus.published[0][1]["device_id"] == "dev-A"


async def test_sse_ignores_unrelated_topic() -> None:
    refresh_calls: list[Any] = []

    async def refresh(device_id, data):
        refresh_calls.append((device_id, data))

    bridge = FakeBridge(sse_events=[FakeEvent("some.other.topic", "cur-x", {})])
    adapter = BridgeAmendmentSyncAdapter(bridge=bridge, signing=FakeSigning(), refresh_fn=refresh)
    await adapter.start_sse()
    await asyncio.sleep(0.05)
    await adapter.stop_sse()
    assert refresh_calls == []
    assert bridge.ack_calls == []


async def test_start_sse_is_idempotent() -> None:
    bridge = FakeBridge()
    adapter = BridgeAmendmentSyncAdapter(bridge=bridge, signing=FakeSigning())
    await adapter.start_sse()
    task1 = adapter._sse_task  # type: ignore[attr-defined]
    await adapter.start_sse()
    task2 = adapter._sse_task  # type: ignore[attr-defined]
    assert task1 is task2
    await adapter.stop_sse()


async def test_stop_sse_without_start_is_safe() -> None:
    adapter = BridgeAmendmentSyncAdapter(bridge=FakeBridge(), signing=FakeSigning())
    await adapter.stop_sse()  # must not raise


async def test_refresh_fn_exception_is_logged_not_raised(caplog) -> None:
    async def bad_refresh(device_id, data):
        raise RuntimeError("refresh boom")

    bridge = FakeBridge(sse_events=[FakeEvent(TOPIC_K0_SYNC_COMPLETE, "cur-1", {"device_id": "X"})])
    adapter = BridgeAmendmentSyncAdapter(
        bridge=bridge, signing=FakeSigning(), refresh_fn=bad_refresh
    )
    await adapter.start_sse()
    for _ in range(50):
        if bridge.ack_calls:
            break
        await asyncio.sleep(0.01)
    await adapter.stop_sse()
    # Even though refresh failed, we still acked.
    assert bridge.ack_calls == [(TOPIC_K0_SYNC_COMPLETE, "cur-1")]


# ---------------------------------------------------------------------
# Coverage: SSE loop reconnect, ack failure, alternate bus shapes
# ---------------------------------------------------------------------
class FakeBridgeAsyncSubscribe:
    """Bridge whose subscribe() is a coroutine returning the iterator."""

    def __init__(self, events):
        self._events = list(events)
        self.ack_calls: list[tuple[str, str]] = []

    async def subscribe(self, topics, *, cursor=None):
        events = list(self._events)

        async def gen():
            for e in events:
                yield e
            await asyncio.Event().wait()

        return gen()

    async def ack(self, topic, cursor):
        raise RuntimeError("ack down")


async def test_sse_subscribe_coroutine_form_and_ack_failure(caplog) -> None:
    event = FakeEvent(TOPIC_K0_SYNC_COMPLETE, "cur-7", {"device_id": "Y"})
    bridge = FakeBridgeAsyncSubscribe([event])
    refreshed: list[Any] = []

    async def refresh(d, data):
        refreshed.append((d, data))

    adapter = BridgeAmendmentSyncAdapter(bridge=bridge, signing=FakeSigning(), refresh_fn=refresh)
    await adapter.start_sse()
    for _ in range(50):
        if refreshed:
            break
        await asyncio.sleep(0.01)
    await adapter.stop_sse()
    assert refreshed == [("Y", {"device_id": "Y"})]


class FakeBusPublishSync:
    """Bus with only sync ``publish`` (no publish_simple)."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic, body):
        self.published.append((topic, body))


async def test_local_bus_publish_fallback_path() -> None:
    event = FakeEvent(TOPIC_K0_SYNC_COMPLETE, "cur-9", {"device_id": "Z"})
    bus = FakeBusPublishSync()
    bridge = FakeBridge(sse_events=[event])
    adapter = BridgeAmendmentSyncAdapter(bridge=bridge, signing=FakeSigning(), local_bus=bus)
    await adapter.start_sse()
    for _ in range(50):
        if bus.published:
            break
        await asyncio.sleep(0.01)
    await adapter.stop_sse()
    assert bus.published and bus.published[0][1]["device_id"] == "Z"


class FakeBridgeReconnect:
    """Subscribe raises once, then yields normally (exercises backoff)."""

    def __init__(self, events):
        self._events = list(events)
        self._attempts = 0
        self.ack_calls: list[tuple[str, str]] = []

    def subscribe(self, topics, *, cursor=None):
        self._attempts += 1
        if self._attempts == 1:
            raise RuntimeError("first attempt fails")
        events = list(self._events)

        async def gen():
            for e in events:
                yield e
            await asyncio.Event().wait()

        return gen()

    async def ack(self, topic, cursor):
        self.ack_calls.append((topic, cursor))


async def test_sse_loop_backs_off_then_reconnects(monkeypatch) -> None:
    # Make sleep instant so the test doesn't actually wait.
    real_sleep = asyncio.sleep

    async def fast_sleep(_d):
        await real_sleep(0)

    monkeypatch.setattr("k1.selfmodel.adapters.bridge_amendment_sync.asyncio.sleep", fast_sleep)
    bridge = FakeBridgeReconnect([FakeEvent(TOPIC_K0_SYNC_COMPLETE, "cur-r", {"device_id": "R"})])
    refreshed: list[Any] = []

    async def refresh(d, data):
        refreshed.append(d)

    adapter = BridgeAmendmentSyncAdapter(bridge=bridge, signing=FakeSigning(), refresh_fn=refresh)
    await adapter.start_sse()
    for _ in range(100):
        if refreshed:
            break
        await real_sleep(0.01)
    await adapter.stop_sse()
    assert refreshed == ["R"]
    assert bridge._attempts >= 2


class FakeBusBoom:
    async def publish_simple(self, topic, body):
        raise RuntimeError("bus down")


async def test_local_bus_publish_failure_is_swallowed() -> None:
    event = FakeEvent(TOPIC_K0_SYNC_COMPLETE, "cur-b", {"device_id": "B"})
    bridge = FakeBridge(sse_events=[event])
    adapter = BridgeAmendmentSyncAdapter(
        bridge=bridge, signing=FakeSigning(), local_bus=FakeBusBoom()
    )
    await adapter.start_sse()
    for _ in range(50):
        if bridge.ack_calls:
            break
        await asyncio.sleep(0.01)
    await adapter.stop_sse()
    # We still acked even though publish raised.
    assert bridge.ack_calls == [(TOPIC_K0_SYNC_COMPLETE, "cur-b")]


class FakeBridgeStreamEndsCleanly:
    """SSE stream that returns immediately, forcing the reconnect path."""

    def __init__(self):
        self._calls = 0

    def subscribe(self, topics, *, cursor=None):
        self._calls += 1

        async def gen():
            if False:  # never yields
                yield None
            return

        return gen()

    async def ack(self, topic, cursor):
        pass


async def test_sse_clean_stream_end_triggers_reconnect(monkeypatch) -> None:
    real_sleep = asyncio.sleep

    async def fast_sleep(_d):
        await real_sleep(0)

    monkeypatch.setattr("k1.selfmodel.adapters.bridge_amendment_sync.asyncio.sleep", fast_sleep)
    bridge = FakeBridgeStreamEndsCleanly()
    adapter = BridgeAmendmentSyncAdapter(bridge=bridge, signing=FakeSigning())
    await adapter.start_sse()
    for _ in range(100):
        if bridge._calls >= 2:
            break
        await real_sleep(0.005)
    await adapter.stop_sse()
    assert bridge._calls >= 2
