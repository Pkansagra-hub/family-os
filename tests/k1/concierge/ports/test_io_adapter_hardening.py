"""
E-1.2 I-1.2.1 — I/O adapter hardening tests.

Extends existing BusInputAdapter / BusOutputAdapter tests with full
behavioural coverage: FIFO ordering, close/unsubscribe, has_buffered
lifecycle, subscriber integration, topic preservation, multiple sends.
"""

from __future__ import annotations

import asyncio

from k1.bus.envelope import Envelope, Priority
from k1.bus.factory import BusFactory
from k1.concierge.adapters.bus_input import BusInputAdapter
from k1.concierge.adapters.bus_output import BusOutputAdapter
from k1.concierge.bus.builders import build_user_input
from k1.concierge.bus.topics import TOPIC_USER_INPUT
from k1.concierge.ports import IInputPort, IOutputPort


def _make_envelope(topic: str = "k1.test.v1", payload: bytes = b'{"text":"hi"}') -> Envelope:
    return Envelope(topic=topic, priority=Priority.INTERACTIVE, payload=payload)


# ===================================================================
# BusInputAdapter — production I/O input
# ===================================================================


class TestBusInputAdapterProtocol:
    """BusInputAdapter satisfies IInputPort Protocol."""

    def test_satisfies_iinputport(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        assert isinstance(adapter, IInputPort)
        adapter.close()


class TestBusInputAdapterReceive:
    """receive() pulls envelopes from bus subscription."""

    def test_receives_single_envelope(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        env = build_user_input({"text": "hello", "device_id": "d1"})
        bus.publish(env)
        result = asyncio.run(adapter.receive())
        assert result.topic == TOPIC_USER_INPUT
        adapter.close()

    def test_fifo_ordering_preserved(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        e1 = build_user_input({"text": "first", "device_id": "d1"})
        e2 = build_user_input({"text": "second", "device_id": "d1"})
        bus.publish(e1)
        bus.publish(e2)

        async def _recv_two():
            return await adapter.receive(), await adapter.receive()

        r1, r2 = asyncio.run(_recv_two())
        assert r1.payload == e1.payload
        assert r2.payload == e2.payload
        adapter.close()

    def test_receives_only_user_input_topic(self) -> None:
        """Non-TOPIC_USER_INPUT publishes are NOT buffered."""
        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        other = _make_envelope(topic="k1.response.final.v1")
        bus.publish(other)
        assert adapter.has_buffered() is False
        adapter.close()


class TestBusInputAdapterHasBuffered:
    """has_buffered() tracks queue state correctly."""

    def test_empty_on_creation(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        assert adapter.has_buffered() is False
        adapter.close()

    def test_true_after_publish(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        env = build_user_input({"text": "hi", "device_id": "d1"})
        bus.publish(env)
        assert adapter.has_buffered() is True
        adapter.close()

    def test_false_after_consume(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        env = build_user_input({"text": "hi", "device_id": "d1"})
        bus.publish(env)
        asyncio.run(adapter.receive())
        assert adapter.has_buffered() is False
        adapter.close()


class TestBusInputAdapterClose:
    """close() unsubscribes from bus."""

    def test_close_unsubscribes(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        adapter.close()
        # After close, publishing should NOT buffer
        env = build_user_input({"text": "after close", "device_id": "d1"})
        bus.publish(env)
        assert adapter.has_buffered() is False

    def test_close_idempotent(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        adapter.close()
        adapter.close()  # No error on second close

    def test_handle_none_after_close(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusInputAdapter(bus)
        adapter.close()
        assert adapter._handle is None


# ===================================================================
# BusOutputAdapter — production I/O output
# ===================================================================


class TestBusOutputAdapterProtocol:
    """BusOutputAdapter satisfies IOutputPort Protocol."""

    def test_satisfies_ioutputport(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusOutputAdapter(bus)
        assert isinstance(adapter, IOutputPort)


class TestBusOutputAdapterSend:
    """send() publishes envelopes to bus for subscribers."""

    def test_send_publishes_to_bus(self) -> None:
        """A bus subscriber receives the envelope sent through the adapter."""
        bus = BusFactory.create_local()
        adapter = BusOutputAdapter(bus)
        received: list[Envelope] = []
        bus.subscribe("k1.response.final.v1", lambda e: received.append(e))
        env = _make_envelope(topic="k1.response.final.v1")
        asyncio.run(adapter.send(env))
        assert len(received) == 1
        assert received[0].payload == env.payload

    def test_send_preserves_topic(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusOutputAdapter(bus)
        received: list[Envelope] = []
        bus.subscribe("k1.response.stream.v1", lambda e: received.append(e))
        env = _make_envelope(topic="k1.response.stream.v1", payload=b'{"chunk":"data"}')
        asyncio.run(adapter.send(env))
        assert received[0].topic == "k1.response.stream.v1"

    def test_send_multiple_envelopes(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusOutputAdapter(bus)
        received: list[Envelope] = []
        bus.subscribe("k1.test.v1", lambda e: received.append(e))
        for i in range(5):
            env = _make_envelope(payload=f'{{"n":{i}}}'.encode())
            asyncio.run(adapter.send(env))
        assert len(received) == 5

    def test_send_preserves_payload(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusOutputAdapter(bus)
        received: list[Envelope] = []
        bus.subscribe("k1.test.v1", lambda e: received.append(e))
        payload = b'{"response":"hello world"}'
        env = _make_envelope(payload=payload)
        asyncio.run(adapter.send(env))
        assert received[0].payload == payload

    def test_send_preserves_priority(self) -> None:
        bus = BusFactory.create_local()
        adapter = BusOutputAdapter(bus)
        received: list[Envelope] = []
        bus.subscribe("k1.test.v1", lambda e: received.append(e))
        env = Envelope(topic="k1.test.v1", priority=Priority.URGENT, payload=b"{}")
        asyncio.run(adapter.send(env))
        assert received[0].priority == Priority.URGENT
