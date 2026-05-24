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


@pytest.mark.asyncio
async def test_back_hil_wait_does_not_block_front_mailbox(monkeypatch) -> None:
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

    runtime = ConciergeRuntime(
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

    consumer = asyncio.create_task(runtime._mailbox_consumer())
    try:
        back_mailbox.push(_env(TOPIC_TASK_DISPATCH, 1))
        await asyncio.wait_for(back_started.wait(), timeout=1.0)

        front_mailbox.push(_env(TOPIC_HIL_REQUEST, 2))
        await asyncio.wait_for(front_seen.wait(), timeout=1.0)
    finally:
        release_back.set()
        consumer.cancel()
        with suppress(asyncio.CancelledError):
            await consumer
