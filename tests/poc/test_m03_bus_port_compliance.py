"""
M3 E3.6 — Bus-port protocol compliance tests.

Validates:
    1. Factory-produced objects satisfy IBus / IMailboxRouter / IMailbox protocols
    2. Protocol methods work through protocol references (not concrete types)
    3. Middleware chain integrates correctly with bus
    4. Existing K1 bus behaviour is preserved
"""

from __future__ import annotations

import logging

import pytest

from k1.bus.envelope import Envelope, Priority
from k1.bus.middleware import Middleware, MiddlewareChain
from k1.bus.middleware.metrics import MetricsMiddleware
from k1.bus.middleware.topic_validation import TopicRegistry, TopicValidationMiddleware
from k1.bus.middleware.tracing import TracingMiddleware
from k1.bus.ports.bus import IBus
from k1.bus.ports.mailbox import IMailbox, IMailboxRouter
from poc.k1_poc.bus.setup import (
    _build_middleware_chain,
    create_poc_bus,
    create_poc_router,
    create_poc_session_adapter,
    register_poc_actors,
)
from poc.k1_poc.bus.topics import ALL_TOPICS
from poc.k1_poc.config import get_config, reset_config

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_cfg():
    """Ensure config is fresh for each test."""
    reset_config()
    yield
    reset_config()


@pytest.fixture()
def bus() -> IBus:
    return create_poc_bus(capture=True)


@pytest.fixture()
def router() -> IMailboxRouter:
    return create_poc_router()


# ═══════════════════════════════════════════════════════════════════════════
# E3.6.1 — Protocol isinstance compliance
# ═══════════════════════════════════════════════════════════════════════════


class TestProtocolCompliance:
    """Factory outputs satisfy @runtime_checkable K1 protocols."""

    def test_bus_is_ibus(self, bus: IBus):
        assert isinstance(bus, IBus)

    def test_router_is_imailboxrouter(self, router: IMailboxRouter):
        assert isinstance(router, IMailboxRouter)

    def test_front_mailbox_is_imailbox(self, router: IMailboxRouter):
        front, _back = register_poc_actors(router)
        assert isinstance(front, IMailbox)

    def test_back_mailbox_is_imailbox(self, router: IMailboxRouter):
        _front, back = register_poc_actors(router)
        assert isinstance(back, IMailbox)

    def test_session_adapter_returns_non_none(self, bus: IBus):
        adapter = create_poc_session_adapter(bus)
        assert adapter is not None


# ═══════════════════════════════════════════════════════════════════════════
# E3.6.1 — IBus protocol methods through protocol reference
# ═══════════════════════════════════════════════════════════════════════════


class TestIBusMethods:
    """All IBus protocol methods callable through protocol reference."""

    def test_publish(self, bus: IBus):
        env = Envelope(
            topic="k1.orchestration.task.dispatch.v1",
            payload=b"{}",
            priority=Priority.INTERACTIVE,
        )
        bus.publish(env)
        assert len(bus.captured) == 1

    def test_subscribe_and_unsubscribe(self, bus: IBus):
        received = []
        handle = bus.subscribe("k1.test.topic.v1", lambda e: received.append(e))
        assert handle is not None
        bus.unsubscribe(handle)

    def test_publish_calls_handler(self, bus: IBus):
        received = []
        bus.subscribe(
            "k1.orchestration.task.dispatch.v1",
            lambda e: received.append(e),
        )
        env = Envelope(
            topic="k1.orchestration.task.dispatch.v1",
            payload=b'{"test": true}',
            priority=Priority.INTERACTIVE,
        )
        bus.publish(env)
        assert len(received) == 1
        assert received[0].topic == "k1.orchestration.task.dispatch.v1"


# ═══════════════════════════════════════════════════════════════════════════
# E3.6.1 — IMailboxRouter protocol methods
# ═══════════════════════════════════════════════════════════════════════════


class TestIMailboxRouterMethods:
    """All IMailboxRouter protocol methods callable through protocol ref."""

    def test_register(self, router: IMailboxRouter):
        mailbox = router.register("test_actor")
        assert isinstance(mailbox, IMailbox)

    def test_unregister(self, router: IMailboxRouter):
        router.register("test_actor")
        router.unregister("test_actor")
        assert "test_actor" not in router.registered_actors()

    def test_registered_actors(self, router: IMailboxRouter):
        router.register("actor_a")
        router.register("actor_b")
        actors = router.registered_actors()
        assert "actor_a" in actors
        assert "actor_b" in actors

    def test_deliver(self, router: IMailboxRouter):
        mailbox = router.register("test_actor")
        env = Envelope(
            topic="k1.test.v1",
            payload=b"{}",
            priority=Priority.INTERACTIVE,
        )
        router.deliver("test_actor", env)
        result = mailbox.receive()
        assert result is not None
        assert result.topic == "k1.test.v1"


# ═══════════════════════════════════════════════════════════════════════════
# E3.6.1 — IMailbox protocol methods
# ═══════════════════════════════════════════════════════════════════════════


class TestIMailboxMethods:
    """All IMailbox protocol methods callable through protocol reference."""

    def test_receive_returns_none_when_empty(self, router: IMailboxRouter):
        mailbox = router.register("empty_actor")
        assert mailbox.receive() is None

    def test_pending_initially_zero(self, router: IMailboxRouter):
        mailbox = router.register("empty_actor")
        assert mailbox.pending() == 0

    def test_pending_increments_after_deliver(self, router: IMailboxRouter):
        mailbox = router.register("count_actor")
        env = Envelope(topic="k1.test.v1", payload=b"{}", priority=Priority.INTERACTIVE)
        router.deliver("count_actor", env)
        assert mailbox.pending() == 1

    def test_receive_decrements_pending(self, router: IMailboxRouter):
        mailbox = router.register("recv_actor")
        env = Envelope(topic="k1.test.v1", payload=b"{}", priority=Priority.INTERACTIVE)
        router.deliver("recv_actor", env)
        mailbox.receive()
        assert mailbox.pending() == 0


# ═══════════════════════════════════════════════════════════════════════════
# E3.6.2 — Middleware integration
# ═══════════════════════════════════════════════════════════════════════════


class TestMiddlewareIntegration:
    """Middleware chain processes envelopes correctly."""

    def test_topic_validation_known_topic_no_warning(self, caplog):
        """Known topic passes through without warning."""
        registry = TopicRegistry()
        registry.register("k1.orchestration.task.dispatch.v1")
        mw = TopicValidationMiddleware(registry)

        env = Envelope(
            topic="k1.orchestration.task.dispatch.v1",
            payload=b"{}",
            priority=Priority.INTERACTIVE,
        )
        result = mw.process(env)
        assert result is env
        assert mw.warning_count == 0

    def test_topic_validation_unknown_topic_warns(self, caplog):
        """Unknown topic produces warning but envelope is NOT dropped."""
        registry = TopicRegistry()
        mw = TopicValidationMiddleware(registry)

        env = Envelope(
            topic="k1.totally.unknown.v1",
            payload=b"{}",
            priority=Priority.INTERACTIVE,
        )
        with caplog.at_level(logging.WARNING):
            result = mw.process(env)
        assert result is env  # SOFT validation: never drops
        assert mw.warning_count == 1

    def test_topic_validation_never_drops(self):
        """TopicValidationMiddleware NEVER returns None."""
        registry = TopicRegistry()
        mw = TopicValidationMiddleware(registry)

        for i in range(10):
            env = Envelope(
                topic=f"k1.unknown.topic.{i}",
                payload=b"{}",
                priority=Priority.BACKGROUND,
            )
            result = mw.process(env)
            assert result is not None

    def test_middleware_chain_processes_all(self):
        """MiddlewareChain runs all middlewares in sequence."""
        registry = TopicRegistry()
        registry.register("k1.test.v1")
        chain = MiddlewareChain(
            [
                TopicValidationMiddleware(registry),
                TracingMiddleware(enabled=False),
                MetricsMiddleware(enabled=False),
            ]
        )
        env = Envelope(topic="k1.test.v1", payload=b"{}", priority=Priority.INTERACTIVE)
        result = chain.process(env)
        assert result is not None
        assert result.topic == "k1.test.v1"

    def test_tracing_noop_when_disabled(self):
        """TracingMiddleware is a no-op when disabled."""
        mw = TracingMiddleware(enabled=False)
        env = Envelope(topic="k1.test.v1", payload=b"{}", priority=Priority.INTERACTIVE)
        result = mw.process(env)
        assert result is env

    def test_metrics_noop_when_disabled(self):
        """MetricsMiddleware is a no-op when disabled."""
        mw = MetricsMiddleware(enabled=False)
        env = Envelope(topic="k1.test.v1", payload=b"{}", priority=Priority.INTERACTIVE)
        result = mw.process(env)
        assert result is env

    def test_tracing_satisfies_middleware_protocol(self):
        assert isinstance(TracingMiddleware(enabled=False), Middleware)

    def test_metrics_satisfies_middleware_protocol(self):
        assert isinstance(MetricsMiddleware(enabled=False), Middleware)

    def test_topic_validation_satisfies_middleware_protocol(self):
        registry = TopicRegistry()
        assert isinstance(TopicValidationMiddleware(registry), Middleware)


# ═══════════════════════════════════════════════════════════════════════════
# E3.6.2 — _build_middleware_chain config integration
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildMiddlewareChain:
    """_build_middleware_chain respects config flags."""

    def test_default_config_enables_topic_validation(self):
        """Default config has topic_validation_enabled=True."""
        cfg = get_config().bus
        chain = _build_middleware_chain(cfg)
        assert chain is not None
        assert len(chain._middlewares) == 1
        assert isinstance(chain._middlewares[0], TopicValidationMiddleware)

    def test_all_disabled_returns_none(self):
        cfg = get_config().bus
        cfg.topic_validation_enabled = False
        cfg.tracing_enabled = False
        cfg.metrics_enabled = False
        chain = _build_middleware_chain(cfg)
        assert chain is None

    def test_all_enabled(self):
        cfg = get_config().bus
        cfg.topic_validation_enabled = True
        cfg.tracing_enabled = True
        cfg.metrics_enabled = True
        chain = _build_middleware_chain(cfg)
        assert chain is not None
        assert len(chain._middlewares) == 3
        assert isinstance(chain._middlewares[0], TopicValidationMiddleware)
        assert isinstance(chain._middlewares[1], TracingMiddleware)
        assert isinstance(chain._middlewares[2], MetricsMiddleware)

    def test_topic_registry_has_all_topics(self):
        """Registry contains all POC topics."""
        cfg = get_config().bus
        chain = _build_middleware_chain(cfg)
        assert chain is not None
        mw = chain._middlewares[0]
        assert isinstance(mw, TopicValidationMiddleware)
        for topic in ALL_TOPICS:
            assert mw.registry.is_known(topic), f"Missing topic: {topic}"

    def test_topic_registry_has_dynamic_prefixes(self):
        """Registry covers k1.agent.* and k1.session.* dynamic topics."""
        cfg = get_config().bus
        chain = _build_middleware_chain(cfg)
        mw = chain._middlewares[0]
        assert mw.registry.is_known("k1.agent.some_agent.delta.v1")
        assert mw.registry.is_known("k1.session.some_event")


# ═══════════════════════════════════════════════════════════════════════════
# E3.6.2 — Bus with middleware end-to-end
# ═══════════════════════════════════════════════════════════════════════════


class TestBusWithMiddleware:
    """Bus + middleware chain works end-to-end."""

    def test_publish_known_topic_no_warning(self, bus: IBus, caplog):
        """Publishing a known topic through real bus produces no warning."""
        env = Envelope(
            topic="k1.orchestration.task.dispatch.v1",
            payload=b"{}",
            priority=Priority.INTERACTIVE,
        )
        with caplog.at_level(logging.WARNING, logger="k1.bus.middleware.topic_validation"):
            bus.publish(env)
        assert "Unknown topic" not in caplog.text

    def test_publish_unknown_topic_warns_but_delivers(self, bus: IBus, caplog):
        """Unknown topic warns but is still delivered."""
        received = []
        bus.subscribe("k1.rogue.topic.v1", lambda e: received.append(e))
        env = Envelope(
            topic="k1.rogue.topic.v1",
            payload=b"{}",
            priority=Priority.INTERACTIVE,
        )
        with caplog.at_level(logging.WARNING):
            bus.publish(env)
        assert len(received) == 1  # Delivered despite unknown
        assert "Unknown topic" in caplog.text

    def test_multiple_envelopes_all_delivered(self, bus: IBus):
        """Multiple envelopes through middleware all get captured."""
        for i in range(5):
            env = Envelope(
                topic="k1.orchestration.task.dispatch.v1",
                payload=f'{{"n": {i}}}'.encode(),
                priority=Priority.INTERACTIVE,
            )
            bus.publish(env)
        assert len(bus.captured) == 5


# ═══════════════════════════════════════════════════════════════════════════
# E3.6.3 — Regression: setup functions still work
# ═══════════════════════════════════════════════════════════════════════════


class TestSetupRegression:
    """E3.1 + E3.5 changes don't break setup functions."""

    def test_create_poc_bus_returns_ibus(self):
        bus = create_poc_bus()
        assert isinstance(bus, IBus)

    def test_create_poc_bus_capture_mode(self):
        bus = create_poc_bus(capture=True)
        env = Envelope(topic="k1.test.v1", payload=b"{}", priority=Priority.INTERACTIVE)
        bus.publish(env)
        assert len(bus.captured) == 1

    def test_create_poc_router_returns_imailboxrouter(self):
        router = create_poc_router()
        assert isinstance(router, IMailboxRouter)

    def test_register_poc_actors_returns_imailboxes(self):
        router = create_poc_router()
        front, back = register_poc_actors(router)
        assert isinstance(front, IMailbox)
        assert isinstance(back, IMailbox)

    def test_session_adapter_creation(self):
        bus = create_poc_bus()
        adapter = create_poc_session_adapter(bus)
        assert adapter is not None

    def test_full_boot_chain(self):
        """Full boot sequence: bus -> router -> adapter -> actors."""
        bus = create_poc_bus(capture=True)
        router = create_poc_router()
        adapter = create_poc_session_adapter(bus)
        front, back = register_poc_actors(router)
        assert isinstance(bus, IBus)
        assert isinstance(router, IMailboxRouter)
        assert isinstance(front, IMailbox)
        assert isinstance(back, IMailbox)
        assert adapter is not None


# ═══════════════════════════════════════════════════════════════════════════
# E3.6 — Re-export verification
# ═══════════════════════════════════════════════════════════════════════════


class TestReExports:
    """E3.2 re-exports in poc.k1_poc.bus are importable."""

    def test_ibus_importable(self):
        from poc.k1_poc.bus import IBus as IBus_  # noqa: F401

        assert IBus_ is IBus

    def test_imailbox_importable(self):
        from poc.k1_poc.bus import IMailbox as IMailbox_  # noqa: F401

        assert IMailbox_ is IMailbox

    def test_imailboxrouter_importable(self):
        from poc.k1_poc.bus import IMailboxRouter as IMailboxRouter_  # noqa: F401

        assert IMailboxRouter_ is IMailboxRouter

    def test_bushandler_importable(self):
        from poc.k1_poc.bus import BusHandler  # noqa: F401

    def test_subscriptionhandle_importable(self):
        from poc.k1_poc.bus import SubscriptionHandle  # noqa: F401

    def test_mailboxconfig_importable(self):
        from poc.k1_poc.bus import MailboxConfig  # noqa: F401
