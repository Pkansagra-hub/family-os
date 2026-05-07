"""
C1 Issue 3.3 — Output adapter behavioural tests.

Covers TestOutputAdapter + BusOutputAdapter behaviour.
"""

from __future__ import annotations

import asyncio

from k1.bus.envelope import Envelope, Priority


def _make_envelope(topic: str = "k1.test.v1", payload: bytes = b'{"text":"hi"}') -> Envelope:
    return Envelope(topic=topic, priority=Priority.INTERACTIVE, payload=payload)


# ===================================================================
# TestOutputAdapter
# ===================================================================


class TestOutputAdapterBehaviour:
    def test_send_captures_envelope(self) -> None:
        from k1.concierge.adapters.test_output import TestOutputAdapter

        adapter = TestOutputAdapter()
        env = _make_envelope()
        asyncio.get_event_loop().run_until_complete(adapter.send(env))
        assert len(adapter.sent) == 1
        assert adapter.sent[0] is env

    def test_get_sent_no_filter(self) -> None:
        from k1.concierge.adapters.test_output import TestOutputAdapter

        adapter = TestOutputAdapter()
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope("t1")))
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope("t2")))
        assert len(adapter.get_sent()) == 2

    def test_get_sent_with_topic_filter(self) -> None:
        from k1.concierge.adapters.test_output import TestOutputAdapter

        adapter = TestOutputAdapter()
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope("t1")))
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope("t2")))
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope("t1")))
        assert len(adapter.get_sent("t1")) == 2
        assert len(adapter.get_sent("t2")) == 1

    def test_last_returns_most_recent(self) -> None:
        from k1.concierge.adapters.test_output import TestOutputAdapter

        adapter = TestOutputAdapter()
        e1 = _make_envelope(payload=b'{"n":1}')
        e2 = _make_envelope(payload=b'{"n":2}')
        asyncio.get_event_loop().run_until_complete(adapter.send(e1))
        asyncio.get_event_loop().run_until_complete(adapter.send(e2))
        assert adapter.last() is e2

    def test_last_empty(self) -> None:
        from k1.concierge.adapters.test_output import TestOutputAdapter

        adapter = TestOutputAdapter()
        assert adapter.last() is None

    def test_clear_resets(self) -> None:
        from k1.concierge.adapters.test_output import TestOutputAdapter

        adapter = TestOutputAdapter()
        asyncio.get_event_loop().run_until_complete(adapter.send(_make_envelope()))
        adapter.clear()
        assert len(adapter.sent) == 0


# ===================================================================
# BusOutputAdapter (production)
# ===================================================================


class TestBusOutputAdapterBehaviour:
    def test_satisfies_ioutputport(self) -> None:
        from k1.bus.factory import BusFactory
        from k1.concierge.adapters.bus_output import BusOutputAdapter

        bus = BusFactory.create_local()
        from k1.concierge.ports import IOutputPort

        adapter = BusOutputAdapter(bus)
        assert isinstance(adapter, IOutputPort)
