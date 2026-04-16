"""
Tests for k1.bus.ports.async_bus -- IAsyncBus, IAsyncMailbox, IAsyncMailboxRouter protocols.

Coverage targets:
    - Protocol structural subtyping with @runtime_checkable
    - AsyncBusHandler type alias
    - Conforming and non-conforming class checks
"""

from typing import Optional

import pytest

from k1.bus.envelope import Envelope
from k1.bus.ports.async_bus import AsyncBusHandler, IAsyncBus, IAsyncMailbox, IAsyncMailboxRouter
from k1.bus.ports.bus import SubscriptionHandle
from k1.bus.ports.mailbox import MailboxConfig

# ===================================================================
# Conforming / Non-conforming stubs
# ===================================================================


class _ConformingAsyncBus:
    async def publish(self, envelope: Envelope) -> None:
        pass

    async def subscribe(self, pattern: str, handler: AsyncBusHandler) -> SubscriptionHandle:
        return SubscriptionHandle(subscription_id="test", pattern=pattern)

    async def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        return True


class _NonConformingAsyncBus:
    """Missing unsubscribe."""

    async def publish(self, envelope: Envelope) -> None:
        pass

    async def subscribe(self, pattern: str, handler: AsyncBusHandler) -> SubscriptionHandle:
        return SubscriptionHandle(subscription_id="test", pattern=pattern)


class _ConformingAsyncMailbox:
    async def receive(self, timeout_ms: int = 0) -> Optional[Envelope]:
        return None

    def pending(self) -> int:
        return 0


class _ConformingAsyncMailboxRouter:
    async def deliver(self, actor_id: str, envelope: Envelope) -> None:
        pass

    async def register(
        self, actor_id: str, config: Optional[MailboxConfig] = None
    ) -> _ConformingAsyncMailbox:
        return _ConformingAsyncMailbox()

    async def unregister(self, actor_id: str) -> bool:
        return True

    def registered_actors(self) -> list[str]:
        return []


# ===================================================================
# IAsyncBus Protocol
# ===================================================================


class TestIAsyncBusProtocol:
    def test_conforming_is_instance(self) -> None:
        bus = _ConformingAsyncBus()
        assert isinstance(bus, IAsyncBus)

    def test_non_conforming_is_not_instance(self) -> None:
        bus = _NonConformingAsyncBus()
        assert not isinstance(bus, IAsyncBus)

    @pytest.mark.asyncio
    async def test_publish_callable(self) -> None:
        bus = _ConformingAsyncBus()
        env = Envelope(topic="k1.test", payload=b"data")
        await bus.publish(env)

    @pytest.mark.asyncio
    async def test_subscribe_returns_handle(self) -> None:
        bus = _ConformingAsyncBus()

        async def handler(e: Envelope) -> None:
            pass

        handle = await bus.subscribe("k1.test.*", handler)
        assert isinstance(handle, SubscriptionHandle)

    @pytest.mark.asyncio
    async def test_unsubscribe_returns_bool(self) -> None:
        bus = _ConformingAsyncBus()
        handle = SubscriptionHandle(subscription_id="x", pattern="k1.test")
        result = await bus.unsubscribe(handle)
        assert result is True


# ===================================================================
# IAsyncMailbox Protocol
# ===================================================================


class TestIAsyncMailboxProtocol:
    def test_conforming_is_instance(self) -> None:
        mb = _ConformingAsyncMailbox()
        assert isinstance(mb, IAsyncMailbox)

    @pytest.mark.asyncio
    async def test_receive_returns_optional_envelope(self) -> None:
        mb = _ConformingAsyncMailbox()
        result = await mb.receive(timeout_ms=0)
        assert result is None

    def test_pending_returns_int(self) -> None:
        mb = _ConformingAsyncMailbox()
        assert mb.pending() == 0


# ===================================================================
# IAsyncMailboxRouter Protocol
# ===================================================================


class TestIAsyncMailboxRouterProtocol:
    def test_conforming_is_instance(self) -> None:
        router = _ConformingAsyncMailboxRouter()
        assert isinstance(router, IAsyncMailboxRouter)

    @pytest.mark.asyncio
    async def test_deliver_callable(self) -> None:
        router = _ConformingAsyncMailboxRouter()
        await router.deliver("actor-1", Envelope(topic="k1.test"))

    @pytest.mark.asyncio
    async def test_register_returns_mailbox(self) -> None:
        router = _ConformingAsyncMailboxRouter()
        mb = await router.register("actor-1")
        assert isinstance(mb, IAsyncMailbox)

    @pytest.mark.asyncio
    async def test_unregister_returns_bool(self) -> None:
        router = _ConformingAsyncMailboxRouter()
        result = await router.unregister("actor-1")
        assert result is True

    def test_registered_actors_returns_list(self) -> None:
        router = _ConformingAsyncMailboxRouter()
        assert router.registered_actors() == []
