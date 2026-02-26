"""
tests.poc.test_m01_e2e -- End-to-end bus wiring and boot validation.

Tests:
    - boot() returns all 5 components with correct types
    - Pub/sub delivery through the real bus
    - Mailbox actor registration and delivery
    - SessionBusAdapter event mapping
    - Causal chain ordering (parent_id enforcement via TimingChain)
    - WFQ priority scheduling in mailboxes
    - Capture mode records envelopes
"""

from __future__ import annotations

import json

from k1.bus.adapters.session_adapter import SessionBusAdapter
from k1.bus.envelope import Envelope, Priority
from k1.bus.impl.local_bus import LocalBus
from k1.bus.impl.local_mailbox import LocalMailbox, LocalMailboxRouter
from poc.k1_poc.bus.builders import build_task_dispatch, build_user_input
from poc.k1_poc.bus.setup import ACTOR_BACK, ACTOR_FRONT
from poc.k1_poc.bus.topics import TOPIC_TASK_DISPATCH, TOPIC_USER_INPUT
from poc.k1_poc.main import boot


class TestBoot:
    """Verify boot() returns correct infrastructure."""

    def test_boot_returns_all_keys(self) -> None:
        infra = boot(capture=True)
        assert set(infra.keys()) == {"bus", "router", "adapter", "front_mailbox", "back_mailbox"}

    def test_boot_bus_type(self) -> None:
        infra = boot(capture=True)
        assert isinstance(infra["bus"], LocalBus)

    def test_boot_router_type(self) -> None:
        infra = boot()
        assert isinstance(infra["router"], LocalMailboxRouter)

    def test_boot_adapter_type(self) -> None:
        infra = boot()
        assert isinstance(infra["adapter"], SessionBusAdapter)

    def test_boot_mailbox_types(self) -> None:
        infra = boot()
        assert isinstance(infra["front_mailbox"], LocalMailbox)
        assert isinstance(infra["back_mailbox"], LocalMailbox)

    def test_boot_actors_registered(self) -> None:
        infra = boot()
        actors = infra["router"].registered_actors()
        assert ACTOR_FRONT in actors
        assert ACTOR_BACK in actors

    def test_boot_adapter_connected(self) -> None:
        infra = boot()
        assert infra["adapter"].is_connected is True


class TestPubSubDelivery:
    """Verify publish/subscribe works through the real bus."""

    def test_subscriber_receives_envelope(self) -> None:
        infra = boot(capture=True)
        bus = infra["bus"]
        received = []

        bus.subscribe(TOPIC_USER_INPUT, lambda env: received.append(env))
        env = build_user_input({"text": "hello"})
        bus.publish(env)

        assert len(received) == 1
        assert received[0].topic == TOPIC_USER_INPUT
        data = json.loads(received[0].payload)
        assert data["text"] == "hello"

    def test_capture_records_envelopes(self) -> None:
        infra = boot(capture=True)
        bus = infra["bus"]

        bus.publish(build_user_input({"text": "a"}))
        bus.publish(build_user_input({"text": "b"}))

        assert len(bus.captured) == 2

    def test_multiple_subscribers_same_topic(self) -> None:
        infra = boot(capture=True)
        bus = infra["bus"]
        r1, r2 = [], []

        bus.subscribe(TOPIC_USER_INPUT, lambda env: r1.append(env))
        bus.subscribe(TOPIC_USER_INPUT, lambda env: r2.append(env))
        bus.publish(build_user_input({"text": "fan-out"}))

        assert len(r1) == 1
        assert len(r2) == 1

    def test_no_crosstalk_between_topics(self) -> None:
        infra = boot(capture=True)
        bus = infra["bus"]
        received = []

        bus.subscribe(TOPIC_TASK_DISPATCH, lambda env: received.append(env))
        bus.publish(build_user_input({"text": "hello"}))

        assert len(received) == 0


class TestMailboxDelivery:
    """Verify mailbox point-to-point delivery."""

    def test_deliver_to_front(self) -> None:
        infra = boot()
        router = infra["router"]
        front = infra["front_mailbox"]

        env = Envelope(topic="k1.test.msg", priority=Priority.INTERACTIVE, payload=b"hello")
        router.deliver(ACTOR_FRONT, env)

        received = front.receive(timeout_ms=1000)
        assert received is not None
        assert received.payload == b"hello"

    def test_deliver_to_back(self) -> None:
        infra = boot()
        router = infra["router"]
        back = infra["back_mailbox"]

        env = Envelope(topic="k1.test.msg", priority=Priority.INTERACTIVE, payload=b"world")
        router.deliver(ACTOR_BACK, env)

        received = back.receive(timeout_ms=1000)
        assert received is not None
        assert received.payload == b"world"


class TestSessionAdapter:
    """Verify SessionBusAdapter maps events to bus topics."""

    def test_emit_maps_to_bus_topic(self) -> None:
        infra = boot(capture=True)
        bus = infra["bus"]
        adapter = infra["adapter"]
        received = []

        bus.subscribe("k1.session.sessionstate.mutation.approved", lambda env: received.append(env))
        adapter.emit("sessionstate.mutation.approved", {"section": "plan"})

        assert len(received) == 1
        data = json.loads(received[0].payload)
        assert data["payload"]["section"] == "plan"

    def test_subscribe_receives_events(self) -> None:
        infra = boot(capture=True)
        adapter = infra["adapter"]
        received = []

        adapter.subscribe("sessionstate.eviction.triggered", lambda p: received.append(p))
        adapter.emit("sessionstate.eviction.triggered", {"reason": "ttl"})

        assert len(received) == 1
        assert received[0]["reason"] == "ttl"


class TestCausalChain:
    """Verify causal ordering via parent_id through the TimingChain."""

    def test_parent_child_ordering(self) -> None:
        """Child (parent_id=X) is delivered after parent (envelope_id=X)."""
        infra = boot(capture=True)
        bus = infra["bus"]
        delivered = []

        bus.subscribe(TOPIC_USER_INPUT, lambda env: delivered.append(("input", env.envelope_id)))
        bus.subscribe(
            TOPIC_TASK_DISPATCH, lambda env: delivered.append(("dispatch", env.envelope_id))
        )

        # Publish parent first (user input)
        parent = build_user_input({"text": "go"})
        bus.publish(parent)

        # The parent gets stamped with an envelope_id by the bus
        parent_id = bus.captured[0].envelope_id

        # Now publish child with parent_id pointing to the parent
        child = build_task_dispatch({"task": "search"}, parent_id=parent_id)
        bus.publish(child)

        # Both should be delivered, parent first
        assert len(delivered) == 2
        assert delivered[0][0] == "input"
        assert delivered[1][0] == "dispatch"

    def test_root_envelope_has_parent_zero(self) -> None:
        env = build_user_input({"text": "root"})
        assert env.parent_id == 0


class TestWFQPriority:
    """Verify WFQ mailbox schedules URGENT before BACKGROUND."""

    def test_urgent_before_background(self) -> None:
        infra = boot()
        router = infra["router"]
        front = infra["front_mailbox"]

        # Deliver BACKGROUND first, then URGENT
        bg = Envelope(topic="k1.test.bg", priority=Priority.BACKGROUND, payload=b"bg")
        urg = Envelope(topic="k1.test.urg", priority=Priority.URGENT, payload=b"urg")

        router.deliver(ACTOR_FRONT, bg)
        router.deliver(ACTOR_FRONT, urg)

        # With WFQ, URGENT should come out first despite being delivered second
        first = front.receive(timeout_ms=1000)
        second = front.receive(timeout_ms=1000)

        assert first.priority == Priority.URGENT
        assert second.priority == Priority.BACKGROUND
