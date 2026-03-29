"""
V2-M9 Integration + Factory Switch tests.

Epic 9.1: Factory upgrade -- backend parameter ("auto"/"rust"/"python")
    M9-001: BusFactory.create_local() with Rust backend
    M9-002: BusFactory.create_for_testing() with Rust backend
    M9-003: BusFactory.create_local(backend=...) explicit selection
    M9-004: BusFactory.create_mailbox_router() with Rust backend

Epic 9.2: Full integration validation
    M9-005: V1 tests against Rust backend (covered by parity tests)
    M9-006: V1 tests against Python fallback
    M9-007: Cross-module: FabricBusAdapter + RustBus
    M9-008: Cross-module: SessionBusAdapter + RustBus
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
from k1.bus.ports.mailbox import MailboxConfig, UnknownActorError

# --- Conditional imports ---

try:
    import k1_bus_core

    HAS_RUST = True
except ImportError:
    HAS_RUST = False

try:
    from k1.bus.impl.rust_bus_adapter import RustBusAdapter
except ImportError:
    RustBusAdapter = None  # type: ignore[assignment,misc]

try:
    from k1.bus.impl.rust_mailbox_adapter import RustMailboxAdapter, RustMailboxRouterAdapter
except ImportError:
    RustMailboxRouterAdapter = None  # type: ignore[assignment,misc]
    RustMailboxAdapter = None  # type: ignore[assignment,misc]

requires_rust = pytest.mark.skipif(not HAS_RUST, reason="k1_bus_core not installed")


# ===================================================================
#  Epic 9.1 -- Factory Upgrade
# ===================================================================


class TestFactoryBackendParameter:
    """M9-003: backend= parameter validation and resolution."""

    def test_invalid_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid backend"):
            BusFactory.create_local(backend="turbo")

    def test_python_backend_returns_local_bus(self) -> None:
        bus = BusFactory.create_local(backend="python")
        assert isinstance(bus, LocalBus)

    @requires_rust
    def test_rust_backend_returns_rust_adapter(self) -> None:
        bus = BusFactory.create_local(backend="rust")
        assert isinstance(bus, RustBusAdapter)

    @requires_rust
    def test_auto_backend_returns_rust_when_available(self) -> None:
        bus = BusFactory.create_local(backend="auto")
        assert isinstance(bus, RustBusAdapter)

    def test_auto_backend_returns_python_when_no_rust(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import k1.bus.factory as factory_mod

        monkeypatch.setattr(factory_mod, "_RUST_AVAILABLE", False)
        bus = BusFactory.create_local(backend="auto")
        assert isinstance(bus, LocalBus)

    def test_rust_backend_raises_when_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import k1.bus.factory as factory_mod

        monkeypatch.setattr(factory_mod, "_RUST_AVAILABLE", False)
        with pytest.raises(ImportError, match="Rust backend requested"):
            BusFactory.create_local(backend="rust")


class TestFactoryCreateLocal:
    """M9-001: BusFactory.create_local() with Rust backend."""

    @requires_rust
    def test_create_local_rust_capture_off(self) -> None:
        bus = BusFactory.create_local(backend="rust", capture=False)
        assert isinstance(bus, RustBusAdapter)
        assert bus.captured == []

    @requires_rust
    def test_create_local_rust_capture_on(self) -> None:
        bus = BusFactory.create_local(backend="rust", capture=True)
        bus.publish(Envelope(topic="k1.test", payload=b"data"))
        assert len(bus.captured) == 1
        assert bus.captured[0].topic == "k1.test"

    @requires_rust
    def test_create_local_timing_chain_forces_python(self) -> None:
        """TimingChain is Python-only; factory should fall back."""
        from k1.bus.timing.defaults import default_timing_config
        from k1.bus.timing.timing_chain import TimingChain

        chain = TimingChain(config=default_timing_config(), timeout_ms=5000)
        bus = BusFactory.create_local(backend="rust", timing_chain=chain)
        # Should fall back to Python because of timing_chain
        assert isinstance(bus, LocalBus)

    def test_create_local_python_basic(self) -> None:
        bus = BusFactory.create_local(backend="python", capture=True)
        assert isinstance(bus, LocalBus)
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert len(bus.captured) == 1

    def test_backward_compat_no_backend_param(self) -> None:
        """Calling without backend= still works (defaults to auto)."""
        bus = BusFactory.create_local()
        assert bus is not None
        bus.publish(Envelope(topic="k1.compat", payload=b"ok"))


class TestFactoryCreateForTesting:
    """M9-002: BusFactory.create_for_testing() with Rust backend."""

    @requires_rust
    def test_testing_rust_capture_enabled(self) -> None:
        bus = BusFactory.create_for_testing(backend="rust")
        assert isinstance(bus, RustBusAdapter)
        bus.publish(Envelope(topic="k1.test", payload=b"data"))
        assert len(bus.captured) == 1

    def test_testing_python_capture_enabled(self) -> None:
        bus = BusFactory.create_for_testing(backend="python")
        assert isinstance(bus, LocalBus)
        bus.publish(Envelope(topic="k1.test", payload=b"data"))
        assert len(bus.captured) == 1

    def test_testing_ordered_forces_python(self) -> None:
        """ordered=True requires TimingChain which is Python-only."""
        bus = BusFactory.create_for_testing(ordered=True, backend="rust")
        # ordered forces Python implementation
        assert isinstance(bus, LocalBus)

    def test_testing_backward_compat(self) -> None:
        bus = BusFactory.create_for_testing()
        assert bus is not None
        bus.publish(Envelope(topic="k1.test", payload=b"ok"))
        assert len(bus.captured) == 1


class TestFactoryCreateLocalOrdered:
    """M9-003: create_local_ordered defaults to Python."""

    def test_ordered_default_is_python(self) -> None:
        bus = BusFactory.create_local_ordered()
        assert isinstance(bus, LocalBus)

    def test_ordered_rust_raises(self) -> None:
        with pytest.raises(ValueError, match="TimingChain.*not supported"):
            BusFactory.create_local_ordered(backend="rust")

    def test_ordered_python_explicit(self) -> None:
        bus = BusFactory.create_local_ordered(backend="python")
        assert isinstance(bus, LocalBus)


class TestFactoryCreateMailboxRouter:
    """M9-004: BusFactory.create_mailbox_router() with Rust backend."""

    def test_python_backend(self) -> None:
        router = BusFactory.create_mailbox_router(backend="python")
        assert isinstance(router, LocalMailboxRouter)

    @requires_rust
    def test_rust_backend(self) -> None:
        router = BusFactory.create_mailbox_router(backend="rust")
        assert isinstance(router, RustMailboxRouterAdapter)

    @requires_rust
    def test_auto_backend_returns_rust(self) -> None:
        router = BusFactory.create_mailbox_router(backend="auto")
        assert isinstance(router, RustMailboxRouterAdapter)

    def test_backward_compat(self) -> None:
        """Calling without backend= still works."""
        router = BusFactory.create_mailbox_router()
        assert router is not None


# ===================================================================
#  Epic 9.2 -- Full Integration Validation
# ===================================================================

# --- Parametrized bus fixture: run integration tests on both backends ---


@pytest.fixture(params=["python", "rust"] if HAS_RUST else ["python"])
def backend_bus(request: pytest.FixtureRequest) -> Any:
    """Capture-mode bus for each backend."""
    bus = BusFactory.create_for_testing(backend=request.param)
    yield bus
    if not bus.closed:
        bus.close()


@pytest.fixture(params=["python", "rust"] if HAS_RUST else ["python"])
def backend_router(request: pytest.FixtureRequest) -> Any:
    """Mailbox router for each backend."""
    router = BusFactory.create_mailbox_router(backend=request.param)
    yield router
    if not router.closed:
        router.close()


# ===================================================================
#  M9-005/006: V1 behavioral tests against both backends
# ===================================================================


class TestBusBasicBehavior:
    """Core bus behavior verified on both Rust and Python backends."""

    def test_publish_and_capture(self, backend_bus: Any) -> None:
        backend_bus.publish(Envelope(topic="k1.test", payload=b"hello"))
        assert len(backend_bus.captured) == 1
        assert backend_bus.captured[0].topic == "k1.test"
        assert backend_bus.captured[0].payload == b"hello"

    def test_subscribe_and_receive(self, backend_bus: Any) -> None:
        received: list[Envelope] = []
        backend_bus.subscribe("k1.test", received.append)
        backend_bus.publish(Envelope(topic="k1.test", payload=b"data"))
        assert len(received) == 1
        assert received[0].payload == b"data"

    def test_wildcard_subscribe(self, backend_bus: Any) -> None:
        received: list[Envelope] = []
        backend_bus.subscribe("k1.test.>", received.append)
        backend_bus.publish(Envelope(topic="k1.test.alpha", payload=b"a"))
        backend_bus.publish(Envelope(topic="k1.test.beta", payload=b"b"))
        backend_bus.publish(Envelope(topic="k1.other", payload=b"x"))
        assert len(received) == 2

    def test_unsubscribe(self, backend_bus: Any) -> None:
        received: list[Envelope] = []
        handle = backend_bus.subscribe("k1.test", received.append)
        backend_bus.publish(Envelope(topic="k1.test", payload=b"1"))
        assert len(received) == 1

        result = backend_bus.unsubscribe(handle)
        assert result is True

        backend_bus.publish(Envelope(topic="k1.test", payload=b"2"))
        assert len(received) == 1  # No new deliveries

    def test_stats_after_publish(self, backend_bus: Any) -> None:
        backend_bus.subscribe("k1.test", lambda e: None)
        backend_bus.publish(Envelope(topic="k1.test", payload=b"x"))
        stats = backend_bus.stats
        assert stats.envelopes_published >= 1
        assert stats.envelopes_delivered >= 1

    def test_close_prevents_publish(self, backend_bus: Any) -> None:
        backend_bus.close()
        assert backend_bus.closed is True
        # Publish after close is a no-op (no exception)
        backend_bus.publish(Envelope(topic="k1.test", payload=b"after"))

    def test_subscription_count(self, backend_bus: Any) -> None:
        assert backend_bus.subscription_count == 0
        h1 = backend_bus.subscribe("k1.a", lambda e: None)
        h2 = backend_bus.subscribe("k1.b", lambda e: None)
        assert backend_bus.subscription_count == 2
        backend_bus.unsubscribe(h1)
        assert backend_bus.subscription_count == 1

    def test_multiple_subscribers_same_topic(self, backend_bus: Any) -> None:
        r1: list[Envelope] = []
        r2: list[Envelope] = []
        backend_bus.subscribe("k1.test", r1.append)
        backend_bus.subscribe("k1.test", r2.append)
        backend_bus.publish(Envelope(topic="k1.test", payload=b"data"))
        assert len(r1) == 1
        assert len(r2) == 1

    def test_envelope_id_stamped(self, backend_bus: Any) -> None:
        backend_bus.publish(Envelope(topic="k1.test", payload=b"data"))
        env = backend_bus.captured[0]
        assert env.envelope_id > 0
        assert env.sequence > 0

    def test_envelope_priority_preserved(self, backend_bus: Any) -> None:
        backend_bus.publish(Envelope(topic="k1.test", priority=Priority.URGENT, payload=b"u"))
        assert backend_bus.captured[0].priority == Priority.URGENT

    def test_error_in_handler_isolated(self, backend_bus: Any) -> None:
        """Handler error doesn't crash the bus."""
        good_received: list[Envelope] = []

        def bad_handler(e: Envelope) -> None:
            raise RuntimeError("boom")

        backend_bus.subscribe("k1.test", bad_handler)
        backend_bus.subscribe("k1.test", good_received.append)
        backend_bus.publish(Envelope(topic="k1.test", payload=b"data"))
        assert len(good_received) == 1
        assert backend_bus.stats.handler_errors >= 1


class TestMailboxBasicBehavior:
    """Mailbox behavior verified on both backends."""

    def test_register_deliver_receive(self, backend_router: Any) -> None:
        mb = backend_router.register("actor-1", MailboxConfig(capacity=10))
        backend_router.deliver("actor-1", Envelope(topic="k1.test", payload=b"hello"))
        env = mb.receive(timeout_ms=100)
        assert env is not None
        assert env.topic == "k1.test"
        assert env.payload == b"hello"

    def test_unregister(self, backend_router: Any) -> None:
        backend_router.register("actor-1")
        assert backend_router.actor_count == 1
        result = backend_router.unregister("actor-1")
        assert result is True
        assert backend_router.actor_count == 0

    def test_deliver_unknown_actor_raises(self, backend_router: Any) -> None:
        with pytest.raises((UnknownActorError, ValueError)):
            backend_router.deliver("ghost", Envelope(topic="k1.test", payload=b"data"))

    def test_close_router(self, backend_router: Any) -> None:
        backend_router.register("actor-1")
        backend_router.close()
        assert backend_router.closed is True

    def test_registered_actors(self, backend_router: Any) -> None:
        backend_router.register("actor-a")
        backend_router.register("actor-b")
        actors = backend_router.registered_actors()
        assert set(actors) == {"actor-a", "actor-b"}

    def test_mailbox_pending(self, backend_router: Any) -> None:
        mb = backend_router.register("actor-1", MailboxConfig(capacity=10))
        backend_router.deliver("actor-1", Envelope(topic="k1.test", payload=b"1"))
        backend_router.deliver("actor-1", Envelope(topic="k1.test", payload=b"2"))
        assert mb.pending() == 2
        mb.receive(timeout_ms=0)
        assert mb.pending() == 1

    def test_mailbox_for(self, backend_router: Any) -> None:
        backend_router.register("actor-1")
        mb = backend_router.mailbox_for("actor-1")
        assert mb is not None
        assert backend_router.mailbox_for("nonexistent") is None


# ===================================================================
#  M9-007: Cross-module -- FabricBusAdapter + Rust bus
# ===================================================================


@requires_rust
class TestFabricAdapterRustBus:
    """FabricBusAdapter works with RustBusAdapter."""

    @pytest.fixture
    def rust_bus(self) -> Any:
        bus = BusFactory.create_for_testing(backend="rust")
        yield bus
        if not bus.closed:
            bus.close()

    @pytest.fixture
    def fabric(self, rust_bus: Any) -> FabricBusAdapter:
        return FabricBusAdapter(rust_bus)

    def test_fabric_emit_raw_subscriber(self, rust_bus: Any, fabric: FabricBusAdapter) -> None:
        raw: list[Envelope] = []
        rust_bus.subscribe("k1.fabric.>", raw.append)
        fabric.emit("k1.fabric.module.loaded.v1", {"module": "search"})

        assert len(raw) == 1
        data = json.loads(raw[0].payload.decode("utf-8"))
        assert data["module"] == "search"

    def test_fabric_emit_delta(self, rust_bus: Any, fabric: FabricBusAdapter) -> None:
        raw: list[Envelope] = []
        rust_bus.subscribe("k1.agent.>", raw.append)
        fabric.emit_delta("agent-1", "plan_update", "plan", {"step": 3})

        assert len(raw) == 1
        data = json.loads(raw[0].payload.decode("utf-8"))
        assert data["agent_id"] == "agent-1"
        assert data["delta_type"] == "plan_update"

    def test_fabric_subscribe_round_trip(self, fabric: FabricBusAdapter) -> None:
        received: list[tuple[str, Dict]] = []
        fabric.subscribe("k1.fabric.>", lambda t, p: received.append((t, p)))
        fabric.emit("k1.fabric.test", {"data": 42})

        assert len(received) == 1
        assert received[0][0] == "k1.fabric.test"
        assert received[0][1]["data"] == 42

    def test_fabric_unsubscribe(self, fabric: FabricBusAdapter) -> None:
        received: list[tuple[str, Dict]] = []
        handle = fabric.subscribe("k1.fabric.>", lambda t, p: received.append((t, p)))
        fabric.emit("k1.fabric.test", {"v": 1})
        assert len(received) == 1

        fabric.unsubscribe(handle)
        fabric.emit("k1.fabric.test", {"v": 2})
        assert len(received) == 1  # No more deliveries

    def test_rust_bus_captures_fabric_events(self, rust_bus: Any, fabric: FabricBusAdapter) -> None:
        fabric.emit("k1.fabric.test", {"x": 1})
        assert len(rust_bus.captured) == 1

    def test_fabric_stats(self, rust_bus: Any, fabric: FabricBusAdapter) -> None:
        fabric.emit("k1.fabric.a", {})
        fabric.emit("k1.fabric.b", {})
        assert rust_bus.stats.envelopes_published == 2


# ===================================================================
#  M9-008: Cross-module -- SessionBusAdapter + Rust bus
# ===================================================================


@requires_rust
class TestSessionAdapterRustBus:
    """SessionBusAdapter works with RustBusAdapter."""

    @pytest.fixture
    def rust_bus(self) -> Any:
        bus = BusFactory.create_for_testing(backend="rust")
        yield bus
        if not bus.closed:
            bus.close()

    @pytest.fixture
    def session(self, rust_bus: Any) -> SessionBusAdapter:
        return SessionBusAdapter(rust_bus)

    def test_session_emit_raw_subscriber(self, rust_bus: Any, session: SessionBusAdapter) -> None:
        raw: list[Envelope] = []
        rust_bus.subscribe("k1.session.>", raw.append)
        session.emit("sessionstate.mutation.approved", {"section": "plan"})

        assert len(raw) == 1
        data = json.loads(raw[0].payload.decode("utf-8"))
        assert data["payload"]["section"] == "plan"

    def test_session_subscribe_round_trip(self, session: SessionBusAdapter) -> None:
        received: list[Any] = []
        session.subscribe("sessionstate.test", received.append)
        session.emit("sessionstate.test", {"key": "value"})

        assert len(received) == 1
        assert received[0] == {"key": "value"}

    def test_session_unsubscribe(self, session: SessionBusAdapter) -> None:
        received: list[Any] = []
        sub_id = session.subscribe("sessionstate.test", received.append)
        session.emit("sessionstate.test", {"v": 1})
        assert len(received) == 1

        session.unsubscribe(sub_id)
        session.emit("sessionstate.test", {"v": 2})
        assert len(received) == 1

    def test_session_is_connected(self, session: SessionBusAdapter) -> None:
        assert session.is_connected is True

    def test_session_emit_batch(self, rust_bus: Any, session: SessionBusAdapter) -> None:
        raw: list[Envelope] = []
        rust_bus.subscribe("k1.session.>", raw.append)
        session.emit_batch(
            [
                ("sessionstate.a", {"v": 1}),
                ("sessionstate.b", {"v": 2}),
            ]
        )
        assert len(raw) == 2

    def test_rust_bus_captures_session_events(
        self, rust_bus: Any, session: SessionBusAdapter
    ) -> None:
        session.emit("sessionstate.test", {"x": 1})
        assert len(rust_bus.captured) == 1

    def test_session_stats(self, rust_bus: Any, session: SessionBusAdapter) -> None:
        session.emit("ss.a", {})
        session.emit("ss.b", {})
        assert rust_bus.stats.envelopes_published == 2


# ===================================================================
#  Multi-adapter coexistence on Rust bus
# ===================================================================


@requires_rust
class TestMultiAdapterRustBus:
    """Fabric + Session on same RustBusAdapter (coexistence)."""

    @pytest.fixture
    def rust_bus(self) -> Any:
        bus = BusFactory.create_for_testing(backend="rust")
        yield bus
        if not bus.closed:
            bus.close()

    @pytest.fixture
    def fabric(self, rust_bus: Any) -> FabricBusAdapter:
        return FabricBusAdapter(rust_bus)

    @pytest.fixture
    def session(self, rust_bus: Any) -> SessionBusAdapter:
        return SessionBusAdapter(rust_bus)

    def test_adapters_isolated(
        self,
        fabric: FabricBusAdapter,
        session: SessionBusAdapter,
    ) -> None:
        fabric_received: list[tuple[str, Dict]] = []
        session_received: list[Any] = []

        fabric.subscribe("k1.fabric.>", lambda t, p: fabric_received.append((t, p)))
        session.subscribe("sessionstate.event", session_received.append)

        fabric.emit("k1.fabric.module.loaded.v1", {"module": "search"})
        session.emit("sessionstate.event", {"type": "update"})

        assert len(fabric_received) == 1
        assert fabric_received[0][1]["module"] == "search"
        assert len(session_received) == 1
        assert session_received[0] == {"type": "update"}

    def test_all_events_on_raw_bus(
        self,
        rust_bus: Any,
        fabric: FabricBusAdapter,
        session: SessionBusAdapter,
    ) -> None:
        all_envs: list[Envelope] = []
        rust_bus.subscribe("k1.>", all_envs.append)

        fabric.emit("k1.fabric.test", {"src": "fabric"})
        session.emit("sessionstate.test", {"src": "session"})
        fabric.emit_delta("agent-1", "test", "sec", {"src": "delta"})

        # Rust bus also emits k1.bus.subscription.created on subscribe,
        # so filter to application topics only
        app_topics = {e.topic for e in all_envs if not e.topic.startswith("k1.bus.")}
        assert "k1.fabric.test" in app_topics
        assert "k1.session.sessionstate.test" in app_topics
        assert "k1.agent.agent-1.delta.v1" in app_topics
        assert len(app_topics) == 3

    def test_bus_stats_count_all(
        self,
        rust_bus: Any,
        fabric: FabricBusAdapter,
        session: SessionBusAdapter,
    ) -> None:
        fabric.emit("k1.fabric.test", {})
        session.emit("ss.test", {})
        fabric.emit_delta("a1", "t", "s", {})
        assert rust_bus.stats.envelopes_published == 3

    def test_envelope_ids_monotonic(
        self,
        rust_bus: Any,
        fabric: FabricBusAdapter,
        session: SessionBusAdapter,
    ) -> None:
        fabric.emit("k1.test.1", {})
        session.emit("test.2", {})
        fabric.emit_delta("a1", "t", "s", {})

        ids = [e.envelope_id for e in rust_bus.captured]
        assert ids == sorted(ids)
        assert len(set(ids)) == 3


# ===================================================================
#  Rust bus adapter -- direct API surface tests
# ===================================================================


@requires_rust
class TestRustBusAdapterAPI:
    """Direct tests on RustBusAdapter API surface."""

    def test_drain(self) -> None:
        bus = RustBusAdapter(capture=True)
        bus.publish(Envelope(topic="k1.test", payload=b"a"))
        bus.publish(Envelope(topic="k1.test", payload=b"b"))
        drained = bus.drain()
        assert len(drained) == 2
        assert all(isinstance(e, Envelope) for e in drained)

    def test_topic_sequence(self) -> None:
        bus = RustBusAdapter(capture=True)
        bus.publish(Envelope(topic="k1.test", payload=b"a"))
        bus.publish(Envelope(topic="k1.test", payload=b"b"))
        seq = bus.topic_sequence("k1.test")
        assert seq >= 2

    def test_last_envelope_id(self) -> None:
        bus = RustBusAdapter(capture=True)
        bus.publish(Envelope(topic="k1.a", payload=b"a"))
        bus.publish(Envelope(topic="k1.b", payload=b"b"))
        assert bus.last_envelope_id >= 2

    def test_handler_circuits(self) -> None:
        bus = RustBusAdapter(capture=True)
        circuits = bus.handler_circuits()
        assert isinstance(circuits, dict)

    def test_closed_initially_false(self) -> None:
        bus = RustBusAdapter(capture=True)
        assert bus.closed is False

    def test_stats_dataclass(self) -> None:
        from k1.bus.impl.local_bus import BusStats

        bus = RustBusAdapter(capture=True)
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        stats = bus.stats
        assert isinstance(stats, BusStats)
        assert stats.envelopes_published == 1


# ===================================================================
#  Rust mailbox adapter -- direct API surface tests
# ===================================================================


@requires_rust
class TestRustMailboxAdapterAPI:
    """Direct tests on RustMailboxRouterAdapter API surface."""

    @pytest.fixture
    def router(self) -> RustMailboxRouterAdapter:
        r = RustMailboxRouterAdapter()
        yield r
        if not r.closed:
            r.close()

    def test_register_and_deliver(self, router: RustMailboxRouterAdapter) -> None:
        mb = router.register("actor-1", MailboxConfig(capacity=10))
        assert isinstance(mb, RustMailboxAdapter)

        router.deliver("actor-1", Envelope(topic="k1.test", payload=b"hello"))
        env = mb.receive(timeout_ms=100)
        assert env is not None
        assert isinstance(env, Envelope)
        assert env.payload == b"hello"

    def test_unregister(self, router: RustMailboxRouterAdapter) -> None:
        router.register("actor-1")
        assert router.actor_count == 1
        assert router.unregister("actor-1") is True
        assert router.actor_count == 0

    def test_registered_actors(self, router: RustMailboxRouterAdapter) -> None:
        router.register("a")
        router.register("b")
        assert set(router.registered_actors()) == {"a", "b"}

    def test_deliver_unknown_raises(self, router: RustMailboxRouterAdapter) -> None:
        with pytest.raises((UnknownActorError, ValueError)):
            router.deliver("ghost", Envelope(topic="k1.test", payload=b"x"))

    def test_stats_snapshot(self, router: RustMailboxRouterAdapter) -> None:
        router.register("actor-1", MailboxConfig(capacity=10))
        router.deliver("actor-1", Envelope(topic="k1.test", payload=b"x"))
        snap = router.stats_snapshot()
        assert isinstance(snap, dict)

    def test_mailbox_for_existing(self, router: RustMailboxRouterAdapter) -> None:
        router.register("actor-1")
        mb = router.mailbox_for("actor-1")
        assert mb is not None

    def test_mailbox_for_nonexistent(self, router: RustMailboxRouterAdapter) -> None:
        assert router.mailbox_for("ghost") is None

    def test_close_router(self, router: RustMailboxRouterAdapter) -> None:
        router.register("actor-1")
        router.close()
        assert router.closed is True

    def test_mailbox_pending_and_counts(self, router: RustMailboxRouterAdapter) -> None:
        mb = router.register("actor-1", MailboxConfig(capacity=50))
        router.deliver("actor-1", Envelope(topic="k1.test", payload=b"1"))
        router.deliver("actor-1", Envelope(topic="k1.test", payload=b"2"))
        assert mb.pending() == 2
        assert mb.delivered_count == 2

        mb.receive(timeout_ms=0)
        assert mb.pending() == 1
        assert mb.received_count == 1

    def test_mailbox_capacity(self, router: RustMailboxRouterAdapter) -> None:
        mb = router.register("actor-1", MailboxConfig(capacity=42))
        assert mb.capacity == 42

    def test_mailbox_close(self, router: RustMailboxRouterAdapter) -> None:
        mb = router.register("actor-1")
        assert mb.closed is False
        mb.close()
        assert mb.closed is True

    def test_priority_ordering(self, router: RustMailboxRouterAdapter) -> None:
        """WFQ mailbox serves URGENT before BACKGROUND."""
        mb = router.register("planner", MailboxConfig(capacity=50, priority_wfq=True))

        router.deliver(
            "planner",
            Envelope(topic="k1.bg", priority=Priority.BACKGROUND, payload=b"bg"),
        )
        router.deliver(
            "planner",
            Envelope(topic="k1.urgent", priority=Priority.URGENT, payload=b"urgent"),
        )

        first = mb.receive(timeout_ms=100)
        second = mb.receive(timeout_ms=100)
        assert first is not None
        assert second is not None
        assert first.priority == Priority.URGENT
        assert second.priority == Priority.BACKGROUND


# ===================================================================
#  Backward compatibility -- existing factory patterns unchanged
# ===================================================================


class TestBackwardCompatibility:
    """All pre-M9 factory call patterns still work without modification."""

    def test_create_local_default(self) -> None:
        bus = BusFactory.create_local()
        bus.publish(Envelope(topic="k1.test", payload=b"ok"))

    def test_create_local_with_capture(self) -> None:
        bus = BusFactory.create_local(capture=True)
        bus.publish(Envelope(topic="k1.test", payload=b"ok"))
        assert len(bus.captured) == 1

    def test_create_for_testing_default(self) -> None:
        bus = BusFactory.create_for_testing()
        bus.publish(Envelope(topic="k1.test", payload=b"ok"))
        assert len(bus.captured) == 1

    def test_create_for_testing_ordered(self) -> None:
        bus = BusFactory.create_for_testing(ordered=True)
        bus.publish(Envelope(topic="k1.test", payload=b"ok"))
        assert len(bus.captured) == 1

    def test_create_local_ordered_default(self) -> None:
        bus = BusFactory.create_local_ordered()
        bus.publish(Envelope(topic="k1.test", payload=b"ok"))

    def test_create_mailbox_router_default(self) -> None:
        router = BusFactory.create_mailbox_router()
        mb = router.register("actor-1")
        assert router.actor_count == 1
        router.close()
