"""
Tests for k1.bus.adapters.session_adapter -- SessionBusAdapter.

Covers:
    Protocol conformance:
        - isinstance(adapter, IEventPort) -- ABC check

    IEventPort (emit/subscribe/unsubscribe):
        - event_type -> topic prefix mapping (k1.session.{event_type})
        - Topic stripping in handler (receives payload only, no topic)
        - Any payload round-trip via JSON serialization
        - is_connected always True (in-process bus)
        - subscribe returns str subscription_id
        - unsubscribe takes str, returns bool
        - emit_batch inherited default works

    Edge cases:
        - Closed bus -> is_connected False
        - Multiple subscriptions
        - Handler error isolation
        - Unsubscribe nonexistent returns False
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from k1.bus.adapters.session_adapter import SessionBusAdapter
from k1.bus.envelope import Priority
from k1.bus.factory import BusFactory
from k1.bus.impl.local_bus import LocalBus
from k1.sessionstate.ports.events import IEventPort

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus() -> LocalBus:
    """Capture-mode bus for testing."""
    return BusFactory.create_for_testing()


@pytest.fixture
def adapter(bus: LocalBus) -> SessionBusAdapter:
    """SessionBusAdapter wrapping a test bus."""
    return SessionBusAdapter(bus)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestSessionAdapterProtocol:
    """SessionBusAdapter is a proper IEventPort (ABC)."""

    def test_isinstance_ievent_port(self, adapter: SessionBusAdapter) -> None:
        assert isinstance(adapter, IEventPort)


# ---------------------------------------------------------------------------
# IEventPort: is_connected
# ---------------------------------------------------------------------------


class TestSessionAdapterConnected:
    """is_connected reflects bus state."""

    def test_connected_when_bus_open(self, adapter: SessionBusAdapter) -> None:
        assert adapter.is_connected is True

    def test_not_connected_when_bus_closed(self, bus: LocalBus, adapter: SessionBusAdapter) -> None:
        bus.close()
        assert adapter.is_connected is False


# ---------------------------------------------------------------------------
# IEventPort: emit
# ---------------------------------------------------------------------------


class TestSessionAdapterEmit:
    """emit() maps event_type to bus topic with prefix."""

    def test_emit_maps_topic(self, bus: LocalBus, adapter: SessionBusAdapter) -> None:
        adapter.emit("sessionstate.mutation.approved", {"section": "plan"})
        assert len(bus.captured) == 1
        assert bus.captured[0].topic == "k1.sessionstate.mutation.approved"

    def test_emit_serializes_payload(self, bus: LocalBus, adapter: SessionBusAdapter) -> None:
        adapter.emit("test.event", {"key": "value"})
        data = json.loads(bus.captured[0].payload.decode("utf-8"))
        assert data == {"payload": {"key": "value"}}

    def test_emit_string_payload(self, bus: LocalBus, adapter: SessionBusAdapter) -> None:
        adapter.emit("test.event", "simple-string")
        data = json.loads(bus.captured[0].payload.decode("utf-8"))
        assert data["payload"] == "simple-string"

    def test_emit_priority_interactive(self, bus: LocalBus, adapter: SessionBusAdapter) -> None:
        adapter.emit("test.event", {})
        assert bus.captured[0].priority == Priority.INTERACTIVE

    def test_emit_multiple(self, bus: LocalBus, adapter: SessionBusAdapter) -> None:
        for i in range(3):
            adapter.emit(f"event.{i}", {"idx": i})
        assert len(bus.captured) == 3


# ---------------------------------------------------------------------------
# IEventPort: subscribe + round-trip
# ---------------------------------------------------------------------------


class TestSessionAdapterSubscribe:
    """subscribe() maps event_type and strips topic from handler."""

    def test_subscribe_round_trip(self, adapter: SessionBusAdapter) -> None:
        received: list[Any] = []
        adapter.subscribe("test.event", received.append)
        adapter.emit("test.event", {"round": "trip"})
        assert len(received) == 1
        assert received[0] == {"round": "trip"}

    def test_handler_receives_payload_only(self, adapter: SessionBusAdapter) -> None:
        """Handler receives unwrapped payload, not (topic, payload)."""
        received: list[Any] = []
        adapter.subscribe("test.event", received.append)
        adapter.emit("test.event", "just-a-string")
        assert received[0] == "just-a-string"

    def test_subscribe_returns_str(self, adapter: SessionBusAdapter) -> None:
        sub_id = adapter.subscribe("test.event", lambda p: None)
        assert isinstance(sub_id, str)
        assert len(sub_id) > 0

    def test_multiple_subscribers(self, adapter: SessionBusAdapter) -> None:
        r1: list[Any] = []
        r2: list[Any] = []
        adapter.subscribe("test.event", r1.append)
        adapter.subscribe("test.event", r2.append)
        adapter.emit("test.event", "data")
        assert len(r1) == 1
        assert len(r2) == 1

    def test_different_event_types_isolated(self, adapter: SessionBusAdapter) -> None:
        r1: list[Any] = []
        r2: list[Any] = []
        adapter.subscribe("event.a", r1.append)
        adapter.subscribe("event.b", r2.append)
        adapter.emit("event.a", "only-a")
        assert len(r1) == 1
        assert len(r2) == 0

    def test_handler_error_isolation(self, adapter: SessionBusAdapter) -> None:
        received: list[Any] = []

        def bad(p: Any) -> None:
            raise RuntimeError("boom")

        def good(p: Any) -> None:
            received.append(p)

        adapter.subscribe("test.event", bad)
        adapter.subscribe("test.event", good)
        adapter.emit("test.event", "data")
        assert len(received) == 1


# ---------------------------------------------------------------------------
# IEventPort: unsubscribe
# ---------------------------------------------------------------------------


class TestSessionAdapterUnsubscribe:
    """unsubscribe() removes subscription by ID."""

    def test_unsubscribe_removes_handler(self, adapter: SessionBusAdapter) -> None:
        received: list[Any] = []
        sub_id = adapter.subscribe("test.event", received.append)
        adapter.emit("test.event", "first")
        assert len(received) == 1

        result = adapter.unsubscribe(sub_id)
        assert result is True

        adapter.emit("test.event", "second")
        assert len(received) == 1  # No new delivery

    def test_unsubscribe_nonexistent(self, adapter: SessionBusAdapter) -> None:
        result = adapter.unsubscribe("no-such-id")
        assert result is False

    def test_double_unsubscribe(self, adapter: SessionBusAdapter) -> None:
        sub_id = adapter.subscribe("test.event", lambda p: None)
        assert adapter.unsubscribe(sub_id) is True
        assert adapter.unsubscribe(sub_id) is False


# ---------------------------------------------------------------------------
# IEventPort: emit_batch
# ---------------------------------------------------------------------------


class TestSessionAdapterBatch:
    """emit_batch() inherited from ABC default calls emit() per event."""

    def test_emit_batch(self, bus: LocalBus, adapter: SessionBusAdapter) -> None:
        events = [
            ("event.a", {"idx": 0}),
            ("event.b", {"idx": 1}),
            ("event.c", {"idx": 2}),
        ]
        adapter.emit_batch(events)
        assert len(bus.captured) == 3
        topics = [e.topic for e in bus.captured]
        assert "k1.session.event.a" in topics
        assert "k1.session.event.b" in topics
        assert "k1.session.event.c" in topics


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestSessionAdapterProperties:
    def test_bus_property(self, bus: LocalBus, adapter: SessionBusAdapter) -> None:
        assert adapter.bus is bus

    def test_active_subscriptions(self, adapter: SessionBusAdapter) -> None:
        assert adapter.active_subscriptions == 0
        adapter.subscribe("test.a", lambda p: None)
        adapter.subscribe("test.b", lambda p: None)
        assert adapter.active_subscriptions == 2

    def test_repr(self, adapter: SessionBusAdapter) -> None:
        r = repr(adapter)
        assert "SessionBusAdapter" in r
        assert "connected=True" in r
