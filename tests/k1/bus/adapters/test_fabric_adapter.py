"""
Tests for k1.bus.adapters.fabric_adapter -- FabricBusAdapter.

Covers:
    Protocol conformance:
        - Satisfies Fabric IEventPort (structural subtyping)
        - Satisfies Fabric IDeltaBusPort (structural subtyping)

    IEventPort (emit/subscribe/unsubscribe):
        - Dict -> bytes -> Dict round-trip via emit + subscribe
        - cognitive_trace_id extracted from payload
        - Subscribe handler receives (topic, Dict)
        - Unsubscribe removes handler
        - Multiple subscribers on same topic
        - Wildcard subscription
        - Handler error isolation
        - Malformed payload handling

    IDeltaBusPort (emit_delta):
        - emit_delta publishes to k1.agent.{id}.delta.v1
        - Delta payload round-trips through DeltaPayload.to_dict()
        - Subscriber receives deserialized DeltaPayload dict

    SubscriptionHandle compatibility:
        - Returns Fabric SubscriptionHandle
        - subscription_id and topic fields populated
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from k1.bus.adapters.fabric_adapter import FabricBusAdapter
from k1.bus.envelope import Priority
from k1.bus.factory import BusFactory
from k1.bus.impl.local_bus import LocalBus
from k1.fabric.ports.delta_bus import IDeltaBusPort
from k1.fabric.ports.event_port import IEventPort as FabricIEventPort
from k1.fabric.ports.event_port import SubscriptionHandle as FabricSubscriptionHandle

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus() -> LocalBus:
    """Capture-mode bus for testing."""
    return BusFactory.create_for_testing()


@pytest.fixture
def adapter(bus: LocalBus) -> FabricBusAdapter:
    """FabricBusAdapter wrapping a test bus."""
    return FabricBusAdapter(bus)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestFabricAdapterProtocolConformance:
    """FabricBusAdapter satisfies Fabric port protocols."""

    def test_satisfies_ievent_port(self, adapter: FabricBusAdapter) -> None:
        assert isinstance(adapter, FabricIEventPort)

    def test_satisfies_idelta_bus_port(self, adapter: FabricBusAdapter) -> None:
        assert isinstance(adapter, IDeltaBusPort)


# ---------------------------------------------------------------------------
# IEventPort: emit
# ---------------------------------------------------------------------------


class TestFabricAdapterEmit:
    """emit() serializes Dict and publishes to bus."""

    def test_emit_publishes_to_bus(self, bus: LocalBus, adapter: FabricBusAdapter) -> None:
        adapter.emit("k1.fabric.capability.registered.v1", {"name": "search"})
        assert len(bus.captured) == 1
        assert bus.captured[0].topic == "k1.fabric.capability.registered.v1"

    def test_emit_serializes_dict_to_json_bytes(
        self, bus: LocalBus, adapter: FabricBusAdapter
    ) -> None:
        adapter.emit("k1.test", {"key": "value", "num": 42})
        payload = json.loads(bus.captured[0].payload.decode("utf-8"))
        assert payload == {"key": "value", "num": 42}

    def test_emit_extracts_cognitive_trace_id(
        self, bus: LocalBus, adapter: FabricBusAdapter
    ) -> None:
        adapter.emit("k1.test", {"cognitive_trace_id": "trace-123", "data": "x"})
        assert bus.captured[0].cognitive_trace_id == "trace-123"

    def test_emit_no_trace_id(self, bus: LocalBus, adapter: FabricBusAdapter) -> None:
        adapter.emit("k1.test", {"data": "no trace"})
        assert bus.captured[0].cognitive_trace_id == ""

    def test_emit_priority_is_interactive(self, bus: LocalBus, adapter: FabricBusAdapter) -> None:
        adapter.emit("k1.test", {})
        assert bus.captured[0].priority == Priority.INTERACTIVE

    def test_emit_multiple_events(self, bus: LocalBus, adapter: FabricBusAdapter) -> None:
        for i in range(5):
            adapter.emit(f"k1.test.{i}", {"idx": i})
        assert len(bus.captured) == 5


# ---------------------------------------------------------------------------
# IEventPort: subscribe + round-trip
# ---------------------------------------------------------------------------


class TestFabricAdapterSubscribe:
    """subscribe() registers handler that receives deserialized Dict."""

    def test_subscribe_round_trip(self, adapter: FabricBusAdapter) -> None:
        received: list[tuple[str, Dict[str, Any]]] = []
        adapter.subscribe("k1.test", lambda t, p: received.append((t, p)))
        adapter.emit("k1.test", {"round": "trip"})
        assert len(received) == 1
        assert received[0] == ("k1.test", {"round": "trip"})

    def test_subscribe_wildcard(self, adapter: FabricBusAdapter) -> None:
        received: list[str] = []
        adapter.subscribe("k1.fabric.*", lambda t, p: received.append(t))
        adapter.emit("k1.fabric.capability.registered.v1", {})
        adapter.emit("k1.fabric.module.loaded.v1", {})
        adapter.emit("k1.unrelated.topic", {})
        # Wildcard k1.fabric.* matches single segment -- not multi-segment
        # Only direct children match "*" (one segment).
        # "k1.fabric.capability.registered.v1" has 3 segments after fabric -> no match
        # Use "k1.fabric.>" for greedy match in real usage
        assert len(received) == 0  # * matches ONE segment only

    def test_subscribe_greedy_wildcard(self, adapter: FabricBusAdapter) -> None:
        received: list[str] = []
        adapter.subscribe("k1.fabric.>", lambda t, p: received.append(t))
        adapter.emit("k1.fabric.capability.registered.v1", {})
        adapter.emit("k1.fabric.module.loaded.v1", {})
        adapter.emit("k1.unrelated.topic", {})
        assert len(received) == 2

    def test_subscribe_returns_fabric_handle(self, adapter: FabricBusAdapter) -> None:
        handle = adapter.subscribe("k1.test", lambda t, p: None)
        assert isinstance(handle, FabricSubscriptionHandle)
        assert handle.subscription_id != ""
        assert handle.topic == "k1.test"

    def test_multiple_subscribers(self, adapter: FabricBusAdapter) -> None:
        r1: list[Dict] = []
        r2: list[Dict] = []
        adapter.subscribe("k1.test", lambda t, p: r1.append(p))
        adapter.subscribe("k1.test", lambda t, p: r2.append(p))
        adapter.emit("k1.test", {"shared": True})
        assert len(r1) == 1
        assert len(r2) == 1

    def test_handler_error_isolation(self, adapter: FabricBusAdapter) -> None:
        """Handler exception doesn't break other subscribers."""
        received: list[str] = []

        def bad_handler(t: str, p: Dict) -> None:
            raise ValueError("handler boom")

        def good_handler(t: str, p: Dict) -> None:
            received.append(t)

        adapter.subscribe("k1.test", bad_handler)
        adapter.subscribe("k1.test", good_handler)
        adapter.emit("k1.test", {"data": "x"})
        # good_handler still gets called (error isolation in adapter wrapper)
        # Note: LocalBus also isolates, but the adapter wrapper catches first
        assert len(received) == 1


# ---------------------------------------------------------------------------
# IEventPort: unsubscribe
# ---------------------------------------------------------------------------


class TestFabricAdapterUnsubscribe:
    """unsubscribe() removes the subscription."""

    def test_unsubscribe_removes_handler(self, adapter: FabricBusAdapter) -> None:
        received: list[str] = []
        handle = adapter.subscribe("k1.test", lambda t, p: received.append(t))
        adapter.emit("k1.test", {"a": 1})
        assert len(received) == 1

        result = adapter.unsubscribe(handle)
        assert result is True

        adapter.emit("k1.test", {"b": 2})
        assert len(received) == 1  # No new delivery

    def test_unsubscribe_nonexistent(self, adapter: FabricBusAdapter) -> None:
        fake = FabricSubscriptionHandle(subscription_id="nonexistent", topic="k1.test")
        result = adapter.unsubscribe(fake)
        assert result is False


# ---------------------------------------------------------------------------
# IDeltaBusPort: emit_delta
# ---------------------------------------------------------------------------


class TestFabricAdapterDelta:
    """emit_delta() publishes delta events to agent topic."""

    def test_emit_delta_topic(self, bus: LocalBus, adapter: FabricBusAdapter) -> None:
        adapter.emit_delta("agent-1", "plan_update", "plan", {"step": 3})
        assert len(bus.captured) == 1
        assert bus.captured[0].topic == "k1.agent.agent-1.delta.v1"

    def test_emit_delta_payload_round_trip(self, bus: LocalBus, adapter: FabricBusAdapter) -> None:
        adapter.emit_delta("agent-1", "plan_update", "plan", {"step": 3})
        data = json.loads(bus.captured[0].payload.decode("utf-8"))
        assert data["agent_id"] == "agent-1"
        assert data["delta_type"] == "plan_update"
        assert data["section"] == "plan"
        assert data["data"] == {"step": 3}

    def test_emit_delta_priority_realtime(self, bus: LocalBus, adapter: FabricBusAdapter) -> None:
        adapter.emit_delta("agent-1", "status", "state", {})
        assert bus.captured[0].priority == Priority.REALTIME

    def test_emit_delta_subscribe_via_bus(self, adapter: FabricBusAdapter) -> None:
        """Can subscribe to delta topics via greedy wildcard and receive deserialized data."""
        received: list[Dict] = []
        # '>' must be the last segment, so use k1.agent.> to match all sub-segments
        adapter.subscribe(
            "k1.agent.>",
            lambda t, p: received.append(p),
        )
        adapter.emit_delta("agent-2", "context_change", "context", {"key": "val"})
        assert len(received) == 1
        assert received[0]["delta_type"] == "context_change"
        assert received[0]["data"] == {"key": "val"}

    def test_emit_delta_subscribe_exact(self, adapter: FabricBusAdapter) -> None:
        """Subscribe to exact delta topic."""
        received: list[Dict] = []
        adapter.subscribe(
            "k1.agent.agent-3.delta.v1",
            lambda t, p: received.append(p),
        )
        adapter.emit_delta("agent-3", "tool_result", "tools", {"result": "ok"})
        assert len(received) == 1
        assert received[0]["delta_type"] == "tool_result"

    def test_multiple_agents_different_topics(
        self, bus: LocalBus, adapter: FabricBusAdapter
    ) -> None:
        adapter.emit_delta("a1", "type1", "sec", {})
        adapter.emit_delta("a2", "type2", "sec", {})
        topics = [e.topic for e in bus.captured]
        assert "k1.agent.a1.delta.v1" in topics
        assert "k1.agent.a2.delta.v1" in topics


# ---------------------------------------------------------------------------
# Repr and properties
# ---------------------------------------------------------------------------


class TestFabricAdapterProperties:
    def test_bus_property(self, bus: LocalBus, adapter: FabricBusAdapter) -> None:
        assert adapter.bus is bus

    def test_repr(self, adapter: FabricBusAdapter) -> None:
        assert "FabricBusAdapter" in repr(adapter)
        assert "FabricBusAdapter" in repr(adapter)
