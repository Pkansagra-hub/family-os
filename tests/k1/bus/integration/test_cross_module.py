"""
Integration tests: cross-module communication through the K1 bus.

These tests prove that different modules can communicate through the bus
without knowing about each other's internals.  This is the "timing belt"
effect -- ONE bus instance connecting ALL components.

Scenarios:
    1. Fabric adapter emit -> raw IBus subscriber receives bytes -> decodes Dict
    2. Delta aggregation via trie wildcard subscription
    3. Mailbox point-to-point alongside pub/sub
    4. Full flow: mailbox dispatch -> bus publish -> trie fan-out -> adapter decode
    5. Causal chain ordering through the timing chain
    6. Session adapter emit -> raw bus subscriber -> session subscriber round-trip
    7. Multiple adapters on same bus (Fabric + Session coexistence)
    8. Middleware observability across adapter publishes
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from k1.bus.adapters.fabric_adapter import FabricBusAdapter
from k1.bus.adapters.session_adapter import SessionBusAdapter
from k1.bus.envelope import Envelope, Priority
from k1.bus.factory import BusFactory
from k1.bus.impl.local_bus import LocalBus
from k1.bus.impl.local_mailbox import LocalMailboxRouter
from k1.bus.ports.mailbox import MailboxConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus() -> LocalBus:
    """Capture-mode bus for integration tests (Python backend)."""
    return BusFactory.create_for_testing(backend="python")


@pytest.fixture
def fabric(bus: LocalBus) -> FabricBusAdapter:
    return FabricBusAdapter(bus)


@pytest.fixture
def session(bus: LocalBus) -> SessionBusAdapter:
    return SessionBusAdapter(bus)


@pytest.fixture
def router() -> LocalMailboxRouter:
    return BusFactory.create_mailbox_router()


# ---------------------------------------------------------------------------
# 1. Fabric adapter emit -> raw IBus subscriber receives bytes -> decode
# ---------------------------------------------------------------------------


class TestFabricToRawBus:
    """Fabric adapter publishes Dict; raw bus subscriber reads bytes."""

    def test_fabric_emit_raw_subscriber(self, bus: LocalBus, fabric: FabricBusAdapter) -> None:
        raw_envelopes: list[Envelope] = []
        bus.subscribe("k1.fabric.>", raw_envelopes.append)

        fabric.emit(
            "k1.fabric.capability.registered.v1",
            {"name": "search", "cognitive_trace_id": "trace-1"},
        )

        assert len(raw_envelopes) == 1
        env = raw_envelopes[0]
        assert env.topic == "k1.fabric.capability.registered.v1"
        assert env.cognitive_trace_id == "trace-1"

        # Raw subscriber can decode the bytes
        payload = json.loads(env.payload.decode("utf-8"))
        assert payload["name"] == "search"

    def test_fabric_delta_raw_subscriber(self, bus: LocalBus, fabric: FabricBusAdapter) -> None:
        """Delta events are also visible to raw IBus subscribers."""
        raw: list[Envelope] = []
        bus.subscribe("k1.agent.>", raw.append)

        fabric.emit_delta("agent-1", "plan_update", "plan", {"step": 3})

        assert len(raw) == 1
        data = json.loads(raw[0].payload.decode("utf-8"))
        assert data["agent_id"] == "agent-1"
        assert data["delta_type"] == "plan_update"


# ---------------------------------------------------------------------------
# 2. Delta aggregation via trie wildcard
# ---------------------------------------------------------------------------


class TestDeltaAggregation:
    """Multiple agents emit deltas; aggregator collects via wildcard."""

    def test_wildcard_delta_aggregation(self, bus: LocalBus, fabric: FabricBusAdapter) -> None:
        aggregated: list[Envelope] = []
        # Subscribe to all agent deltas via greedy wildcard
        bus.subscribe("k1.agent.>", aggregated.append)

        fabric.emit_delta("agent-1", "plan_update", "plan", {"v": 1})
        fabric.emit_delta("agent-2", "status_change", "state", {"v": 2})
        fabric.emit_delta("agent-3", "tool_result", "tools", {"v": 3})

        assert len(aggregated) == 3
        topics = [e.topic for e in aggregated]
        assert "k1.agent.agent-1.delta.v1" in topics
        assert "k1.agent.agent-2.delta.v1" in topics
        assert "k1.agent.agent-3.delta.v1" in topics

    def test_single_agent_filter(self, bus: LocalBus, fabric: FabricBusAdapter) -> None:
        """Subscribe to one agent's deltas only."""
        agent1_deltas: list[Envelope] = []
        bus.subscribe("k1.agent.agent-1.delta.v1", agent1_deltas.append)

        fabric.emit_delta("agent-1", "update", "plan", {})
        fabric.emit_delta("agent-2", "update", "plan", {})

        assert len(agent1_deltas) == 1


# ---------------------------------------------------------------------------
# 3. Mailbox point-to-point alongside pub/sub
# ---------------------------------------------------------------------------


class TestMailboxAlongsidePubSub:
    """Mailbox (point-to-point) and bus (pub/sub) work independently."""

    def test_mailbox_and_bus_coexist(self, bus: LocalBus, router: LocalMailboxRouter) -> None:
        # Set up mailbox for orchestrator
        mb = router.register("orchestrator", MailboxConfig(capacity=50))

        # Set up pub/sub subscriber
        pubsub_received: list[Envelope] = []
        bus.subscribe("k1.test", pubsub_received.append)

        # Publish to bus (pub/sub)
        bus.publish(Envelope(topic="k1.test", payload=b"bus-data"))

        # Deliver to mailbox (point-to-point)
        router.deliver(
            "orchestrator",
            Envelope(topic="k1.mailbox.test", payload=b"mailbox-data"),
        )

        # Both work independently
        assert len(pubsub_received) == 1
        assert pubsub_received[0].payload == b"bus-data"

        received = mb.receive(timeout_ms=100)
        assert received is not None
        assert received.payload == b"mailbox-data"

    def test_mailbox_priority_ordering(self, router: LocalMailboxRouter) -> None:
        """Mailbox delivers by priority (URGENT before BACKGROUND)."""
        mb = router.register("planner", MailboxConfig(capacity=50, priority_wfq=True))

        # Send in reverse priority order
        router.deliver(
            "planner",
            Envelope(topic="k1.bg", priority=Priority.BACKGROUND, payload=b"bg"),
        )
        router.deliver(
            "planner",
            Envelope(topic="k1.urgent", priority=Priority.URGENT, payload=b"urgent"),
        )

        # Receive should give URGENT first (WFQ)
        first = mb.receive(timeout_ms=100)
        second = mb.receive(timeout_ms=100)
        assert first is not None
        assert second is not None
        assert first.priority == Priority.URGENT
        assert second.priority == Priority.BACKGROUND


# ---------------------------------------------------------------------------
# 4. Full flow: adapter -> bus -> trie fan-out -> decode
# ---------------------------------------------------------------------------


class TestFullFlow:
    """End-to-end: Fabric emit -> bus -> multiple subscribers -> decode."""

    def test_fabric_to_orchestrator_pattern(self, bus: LocalBus, fabric: FabricBusAdapter) -> None:
        """
        Simulates: Fabric completes capability -> bus -> Orchestrator receives.
        """
        orchestrator_inbox: list[Dict[str, Any]] = []

        # Orchestrator subscribes to capability completions
        bus.subscribe(
            "k1.fabric.capability.>",
            lambda env: orchestrator_inbox.append(json.loads(env.payload.decode("utf-8"))),
        )

        # Fabric completes a capability
        fabric.emit(
            "k1.fabric.capability.completed.v1",
            {
                "capability": "search",
                "result": {"items": 3},
                "cognitive_trace_id": "trace-flow-1",
            },
        )

        assert len(orchestrator_inbox) == 1
        assert orchestrator_inbox[0]["capability"] == "search"
        assert orchestrator_inbox[0]["result"] == {"items": 3}

    def test_session_to_bus_to_subscriber(self, bus: LocalBus, session: SessionBusAdapter) -> None:
        """Session emits event -> bus -> raw subscriber receives."""
        raw_received: list[Envelope] = []
        # P6.9: sessionstate.* events now flatten to k1.sessionstate.*
        bus.subscribe("k1.sessionstate.>", raw_received.append)

        session.emit("sessionstate.mutation.approved", {"section": "plan"})

        assert len(raw_received) == 1
        data = json.loads(raw_received[0].payload.decode("utf-8"))
        assert data["payload"]["section"] == "plan"

    def test_fan_out_multiple_subscribers(self, bus: LocalBus, fabric: FabricBusAdapter) -> None:
        """One publish -> multiple subscribers each get the envelope."""
        orchestrator: list[Dict] = []
        logger_sub: list[Dict] = []
        metrics_sub: list[Dict] = []

        bus.subscribe(
            "k1.fabric.capability.>",
            lambda e: orchestrator.append(json.loads(e.payload.decode("utf-8"))),
        )
        bus.subscribe(
            "k1.fabric.>",
            lambda e: logger_sub.append(json.loads(e.payload.decode("utf-8"))),
        )
        bus.subscribe(
            "k1.fabric.capability.completed.v1",
            lambda e: metrics_sub.append(json.loads(e.payload.decode("utf-8"))),
        )

        fabric.emit("k1.fabric.capability.completed.v1", {"cap": "search"})

        assert len(orchestrator) == 1
        assert len(logger_sub) == 1
        assert len(metrics_sub) == 1


# ---------------------------------------------------------------------------
# 5. Causal chain ordering
# ---------------------------------------------------------------------------


class TestCausalChainIntegration:
    """Parent-child ordering with timing chain."""

    def test_causal_ordering_through_bus(self) -> None:
        """
        Parent published first is delivered immediately.
        Child (with parent_id) is also delivered immediately when parent exists.
        Uses separate topics to avoid sequence gap interactions.
        """
        bus = BusFactory.create_for_testing(ordered=True)
        delivered: list[int] = []

        # Use k1.capability.> — STRICT topic for ordering enforcement
        bus.subscribe("k1.capability.>", lambda e: delivered.append(e.envelope_id))

        # Step 1: Publish a root parent — parent_id=0, separate topic
        bus.publish(
            Envelope(
                topic="k1.capability.parent",
                payload=b"parent",
                parent_id=0,
            )
        )
        parent_id = bus.captured[-1].envelope_id
        # Root envelope -> delivered immediately
        assert len(delivered) == 1
        assert delivered[0] == parent_id

        # Step 2: Publish a child referencing the parent — different topic
        bus.publish(
            Envelope(
                topic="k1.capability.child",
                payload=b"child",
                parent_id=parent_id,
            )
        )
        # Parent already delivered -> child cascades immediately
        assert len(delivered) == 2


# ---------------------------------------------------------------------------
# 6. Session adapter round-trip through bus
# ---------------------------------------------------------------------------


class TestSessionRoundTrip:
    """Session adapter emit -> bus -> session subscriber receives."""

    def test_session_emit_subscribe_round_trip(self, session: SessionBusAdapter) -> None:
        received: list[Any] = []
        session.subscribe("sessionstate.mutation.approved", received.append)
        session.emit("sessionstate.mutation.approved", {"section": "plan", "approved": True})

        assert len(received) == 1
        assert received[0] == {"section": "plan", "approved": True}


# ---------------------------------------------------------------------------
# 7. Multiple adapters on same bus
# ---------------------------------------------------------------------------


class TestMultiAdapterCoexistence:
    """Fabric and Session adapters coexist on the same bus."""

    def test_fabric_and_session_isolated(
        self, bus: LocalBus, fabric: FabricBusAdapter, session: SessionBusAdapter
    ) -> None:
        fabric_received: list[tuple[str, Dict]] = []
        session_received: list[Any] = []

        fabric.subscribe("k1.fabric.>", lambda t, p: fabric_received.append((t, p)))
        session.subscribe("sessionstate.event", session_received.append)

        # Fabric event
        fabric.emit("k1.fabric.module.loaded.v1", {"module": "search"})
        # Session event
        session.emit("sessionstate.event", {"type": "update"})

        # Each adapter's subscribers see only their events
        assert len(fabric_received) == 1
        assert fabric_received[0][1]["module"] == "search"
        assert len(session_received) == 1
        assert session_received[0] == {"type": "update"}

    def test_all_events_visible_on_raw_bus(
        self, bus: LocalBus, fabric: FabricBusAdapter, session: SessionBusAdapter
    ) -> None:
        """Raw bus subscriber sees ALL events from all adapters."""
        all_envelopes: list[Envelope] = []
        bus.subscribe("k1.>", all_envelopes.append)

        fabric.emit("k1.fabric.test", {"src": "fabric"})
        session.emit("sessionstate.test", {"src": "session"})
        fabric.emit_delta("agent-1", "test", "sec", {"src": "delta"})

        assert len(all_envelopes) == 3
        topics = {e.topic for e in all_envelopes}
        assert "k1.fabric.test" in topics
        assert "k1.sessionstate.test" in topics
        assert "k1.agent.agent-1.delta.v1" in topics

    def test_bus_stats_count_all_adapter_events(
        self, bus: LocalBus, fabric: FabricBusAdapter, session: SessionBusAdapter
    ) -> None:
        fabric.emit("k1.fabric.test", {})
        session.emit("ss.test", {})
        fabric.emit_delta("a1", "t", "s", {})
        assert bus.stats.envelopes_published == 3


# ---------------------------------------------------------------------------
# 8. Middleware observability across adapters
# ---------------------------------------------------------------------------


class TestMiddlewareWithAdapters:
    """Middleware chain fires for adapter-originated publishes."""

    def test_middleware_sees_adapter_publishes(self) -> None:
        from k1.bus.middleware import MiddlewareChain

        class RecordingMiddleware:
            def __init__(self) -> None:
                self.seen: list[Envelope] = []

            def process(self, envelope: Envelope) -> Envelope | None:
                self.seen.append(envelope)
                return envelope

        recorder = RecordingMiddleware()
        chain = MiddlewareChain([recorder])
        bus = BusFactory.create_for_testing(middleware=chain, backend="python")
        fabric = FabricBusAdapter(bus)
        session = SessionBusAdapter(bus)

        fabric.emit("k1.fabric.test", {"data": 1})
        session.emit("ss.test", {"data": 2})

        assert len(recorder.seen) == 2
        assert recorder.seen[0].topic == "k1.fabric.test"
        assert recorder.seen[1].topic == "k1.session.ss.test"


# ---------------------------------------------------------------------------
# 9. Envelope ID monotonicity across adapters
# ---------------------------------------------------------------------------


class TestEnvelopeIdMonotonicity:
    """Envelope IDs are globally monotonic across all adapters."""

    def test_ids_increase_across_adapters(
        self, bus: LocalBus, fabric: FabricBusAdapter, session: SessionBusAdapter
    ) -> None:
        fabric.emit("k1.test.1", {})
        session.emit("test.2", {})
        fabric.emit_delta("a1", "t", "s", {})

        ids = [e.envelope_id for e in bus.captured]
        assert ids == sorted(ids)
        assert len(set(ids)) == 3  # All unique
