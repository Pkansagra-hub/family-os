"""
C1 Issue 3.2 — Input adapter behavioural tests.

Covers TestInputAdapter + BusInputAdapter behaviour.
"""

from __future__ import annotations

import asyncio

from k1.bus.envelope import Envelope, Priority


def _make_envelope(topic: str = "k1.test.v1", payload: bytes = b'{"text":"hi"}') -> Envelope:
    return Envelope(topic=topic, priority=Priority.INTERACTIVE, payload=payload)


# ===================================================================
# TestInputAdapter
# ===================================================================


class TestInputAdapterBehaviour:
    def test_receive_returns_injected_envelope(self) -> None:
        from k1.concierge.adapters.test_input import TestInputAdapter

        adapter = TestInputAdapter()
        env = _make_envelope()
        adapter.inject(env)
        result = asyncio.run(adapter.receive())
        assert result is env

    def test_has_buffered_empty(self) -> None:
        from k1.concierge.adapters.test_input import TestInputAdapter

        adapter = TestInputAdapter()
        assert adapter.has_buffered() is False

    def test_has_buffered_after_inject(self) -> None:
        from k1.concierge.adapters.test_input import TestInputAdapter

        adapter = TestInputAdapter()
        adapter.inject(_make_envelope())
        assert adapter.has_buffered() is True

    def test_inject_text_creates_envelope(self) -> None:
        from k1.concierge.adapters.test_input import TestInputAdapter

        adapter = TestInputAdapter()
        adapter.inject_text("hello world")
        assert adapter.has_buffered() is True
        env = asyncio.run(adapter.receive())
        assert env.topic == "k1.session.user.input.v1"

    def test_fifo_ordering(self) -> None:
        from k1.concierge.adapters.test_input import TestInputAdapter

        adapter = TestInputAdapter()
        e1 = _make_envelope(payload=b'{"n":1}')
        e2 = _make_envelope(payload=b'{"n":2}')
        adapter.inject(e1)
        adapter.inject(e2)

        async def _recv_two():
            return await adapter.receive(), await adapter.receive()

        r1, r2 = asyncio.run(_recv_two())
        assert r1 is e1
        assert r2 is e2


# ===================================================================
# BusInputAdapter (production)
# ===================================================================


class TestBusInputAdapterBehaviour:
    def test_receives_published_envelope(self) -> None:
        from k1.bus.factory import BusFactory
        from k1.concierge.adapters.bus_input import BusInputAdapter
        from k1.concierge.bus.builders import build_user_input

        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        env = build_user_input({"text": "hello", "device_id": "test"})
        bus.publish(env)
        assert adapter.has_buffered() is True
        result = asyncio.run(adapter.receive())
        assert result.topic == "k1.session.user.input.v1"
        adapter.close()
