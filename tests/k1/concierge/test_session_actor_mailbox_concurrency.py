"""GAP-HIL-012 -- ConciergeRuntime must run independent Front/Back mailbox
consumers so a blocking Back handler cannot stall Front delivery.

Regression for the historical deadlock where a single ``_mailbox_consumer``
served both mailboxes round-robin and an awaiting Back actor (e.g. a HIL
wait) held the coroutine, starving Front of its envelopes.
"""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress
from types import SimpleNamespace

import pytest

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.bus.topics import TOPIC_HIL_REQUEST, TOPIC_TASK_DISPATCH
from k1.concierge.session import ConciergeRuntime


class _Mailbox:
    def __init__(self) -> None:
        self._items: deque[Envelope] = deque()

    def push(self, envelope: Envelope) -> None:
        self._items.append(envelope)

    def receive(self, timeout_ms: int = 0) -> Envelope | None:  # noqa: ARG002
        if not self._items:
            return None
        return self._items.popleft()


def _env(topic: str, envelope_id: int) -> Envelope:
    return Envelope(
        topic=topic,
        priority=Priority.INTERACTIVE,
        envelope_id=envelope_id,
        payload=b"{}",
        payload_format=PayloadFormat.JSON,
    )


def _make_runtime(front_mailbox: _Mailbox, back_mailbox: _Mailbox) -> ConciergeRuntime:
    return ConciergeRuntime(
        bus=SimpleNamespace(),
        router=SimpleNamespace(),
        front_mailbox=front_mailbox,
        back_mailbox=back_mailbox,
        fsm=SimpleNamespace(state=SimpleNamespace(name="COMPANIONING"), _opp_pipeline=None),
        model=SimpleNamespace(),
        session_state=SimpleNamespace(),
        front_dispatcher=SimpleNamespace(),
        back_dispatcher=SimpleNamespace(),
        front_subscriptions=[],
    )


@pytest.mark.asyncio
async def test_split_consumers_run_independently(monkeypatch) -> None:
    """Front consumer must deliver while Back consumer is blocked on HIL."""
    front_mailbox = _Mailbox()
    back_mailbox = _Mailbox()
    back_started = asyncio.Event()
    release_back = asyncio.Event()
    front_seen = asyncio.Event()

    async def fake_back_handler(**_kwargs):
        back_started.set()
        await release_back.wait()

    async def fake_front_handler(**_kwargs):
        front_seen.set()

    monkeypatch.setattr("k1.concierge.actors.back.route_back_envelope", fake_back_handler)
    monkeypatch.setattr("k1.concierge.actors.front.front_handler", fake_front_handler)

    runtime = _make_runtime(front_mailbox, back_mailbox)

    # Use the split consumers directly to assert the new wiring shape.
    front_task = asyncio.create_task(runtime._front_consumer())
    back_task = asyncio.create_task(runtime._back_consumer())
    try:
        back_mailbox.push(_env(TOPIC_TASK_DISPATCH, 1))
        await asyncio.wait_for(back_started.wait(), timeout=1.0)

        # Back coroutine is now suspended in await release_back.wait().
        # Front must still drain its mailbox.
        front_mailbox.push(_env(TOPIC_HIL_REQUEST, 2))
        await asyncio.wait_for(front_seen.wait(), timeout=1.0)
    finally:
        release_back.set()
        front_task.cancel()
        back_task.cancel()
        with suppress(asyncio.CancelledError):
            await front_task
        with suppress(asyncio.CancelledError):
            await back_task


@pytest.mark.asyncio
async def test_start_creates_both_consumer_tasks(monkeypatch) -> None:
    """ConciergeRuntime.start() must spawn distinct Front and Back tasks."""
    front_mailbox = _Mailbox()
    back_mailbox = _Mailbox()

    async def _noop(**_kwargs):
        return None

    monkeypatch.setattr("k1.concierge.actors.back.route_back_envelope", _noop)
    monkeypatch.setattr("k1.concierge.actors.front.front_handler", _noop)

    runtime = _make_runtime(front_mailbox, back_mailbox)
    await runtime.start()
    try:
        assert runtime._front_consumer_task is not None
        assert runtime._back_consumer_task is not None
        assert runtime._front_consumer_task is not runtime._back_consumer_task
        assert not runtime._front_consumer_task.done()
        assert not runtime._back_consumer_task.done()
    finally:
        await runtime.stop()

    assert runtime._front_consumer_task.done()
    assert runtime._back_consumer_task.done()
