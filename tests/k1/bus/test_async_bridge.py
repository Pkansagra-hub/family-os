"""
Tests for k1.bus.async_bridge -- AsyncBusBridge, AsyncMailboxBridge,
AsyncMailboxRouterBridge.

Coverage targets:
    - publish/subscribe/unsubscribe offloaded correctly
    - async handler shim bridges back to event-loop
    - AsyncMailboxBridge receive/pending
    - AsyncMailboxRouterBridge deliver/register/unregister/registered_actors
    - Protocol conformance (isinstance checks)
"""

from __future__ import annotations

import asyncio
from typing import Optional

import pytest

from k1.bus.async_bridge import AsyncBusBridge, AsyncMailboxBridge, AsyncMailboxRouterBridge
from k1.bus.envelope import Envelope
from k1.bus.ports.async_bus import IAsyncBus, IAsyncMailbox, IAsyncMailboxRouter
from k1.bus.ports.bus import BusHandler, SubscriptionHandle
from k1.bus.ports.mailbox import MailboxConfig

# ===================================================================
# Sync stubs that mimic IBus / IMailbox / IMailboxRouter
# ===================================================================


class StubBus:
    """Minimal IBus stub recording calls."""

    def __init__(self) -> None:
        self.published: list[Envelope] = []
        self._subs: dict[str, BusHandler] = {}
        self._next_id = 0

    def publish(self, envelope: Envelope) -> None:
        self.published.append(envelope)

    def subscribe(self, pattern: str, handler: BusHandler) -> SubscriptionHandle:
        self._next_id += 1
        sid = f"sub-{self._next_id}"
        self._subs[sid] = handler
        return SubscriptionHandle(subscription_id=sid, pattern=pattern)

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        return self._subs.pop(handle.subscription_id, None) is not None

    def dispatch(self, subscription_id: str, envelope: Envelope) -> None:
        """Test helper: invoke the registered handler directly."""
        handler = self._subs[subscription_id]
        handler(envelope)


class StubMailbox:
    """Minimal IMailbox stub."""

    def __init__(self) -> None:
        self._queue: list[Envelope] = []

    def receive(self, timeout_ms: int = 0) -> Optional[Envelope]:
        return self._queue.pop(0) if self._queue else None

    def pending(self) -> int:
        return len(self._queue)

    def enqueue(self, envelope: Envelope) -> None:
        self._queue.append(envelope)


class StubMailboxRouter:
    """Minimal IMailboxRouter stub."""

    def __init__(self) -> None:
        self._actors: dict[str, StubMailbox] = {}

    def deliver(self, actor_id: str, envelope: Envelope) -> None:
        self._actors[actor_id].enqueue(envelope)

    def register(self, actor_id: str, config: Optional[MailboxConfig] = None) -> StubMailbox:
        mb = StubMailbox()
        self._actors[actor_id] = mb
        return mb

    def unregister(self, actor_id: str) -> bool:
        return self._actors.pop(actor_id, None) is not None

    def registered_actors(self) -> list[str]:
        return list(self._actors.keys())


# ===================================================================
# AsyncBusBridge
# ===================================================================


class TestAsyncBusBridge:
    @pytest.mark.asyncio
    async def test_protocol_conformance(self) -> None:
        bridge = AsyncBusBridge(StubBus())
        assert isinstance(bridge, IAsyncBus)

    @pytest.mark.asyncio
    async def test_publish_offloads(self) -> None:
        stub = StubBus()
        bridge = AsyncBusBridge(stub)
        env = Envelope(topic="k1.test", payload=b"hello")
        await bridge.publish(env)
        assert len(stub.published) == 1
        assert stub.published[0].topic == "k1.test"

    @pytest.mark.asyncio
    async def test_subscribe_returns_handle(self) -> None:
        stub = StubBus()
        bridge = AsyncBusBridge(stub)

        async def my_handler(e: Envelope) -> None:
            pass

        handle = await bridge.subscribe("k1.test.*", my_handler)
        assert isinstance(handle, SubscriptionHandle)
        assert handle.pattern == "k1.test.*"

    @pytest.mark.asyncio
    async def test_unsubscribe_returns_bool(self) -> None:
        stub = StubBus()
        bridge = AsyncBusBridge(stub)

        async def my_handler(e: Envelope) -> None:
            pass

        handle = await bridge.subscribe("k1.test", my_handler)
        assert await bridge.unsubscribe(handle) is True
        # Second unsubscribe should return False
        assert await bridge.unsubscribe(handle) is False

    @pytest.mark.asyncio
    async def test_async_handler_called_via_shim(self) -> None:
        """
        Verify that when the sync bus dispatches, the async handler
        actually runs on the event-loop.
        """
        stub = StubBus()
        bridge = AsyncBusBridge(stub)

        received: list[Envelope] = []

        async def my_handler(e: Envelope) -> None:
            received.append(e)

        handle = await bridge.subscribe("k1.test", my_handler)

        # Simulate sync dispatch from bus thread
        env = Envelope(topic="k1.test", payload=b"shim-test")
        stub.dispatch(handle.subscription_id, env)

        # Give event-loop a tick to process the scheduled coroutine
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].payload == b"shim-test"


# ===================================================================
# AsyncMailboxBridge
# ===================================================================


class TestAsyncMailboxBridge:
    @pytest.mark.asyncio
    async def test_protocol_conformance(self) -> None:
        bridge = AsyncMailboxBridge(StubMailbox())
        assert isinstance(bridge, IAsyncMailbox)

    @pytest.mark.asyncio
    async def test_receive_empty(self) -> None:
        bridge = AsyncMailboxBridge(StubMailbox())
        result = await bridge.receive(timeout_ms=0)
        assert result is None

    @pytest.mark.asyncio
    async def test_receive_returns_envelope(self) -> None:
        stub = StubMailbox()
        env = Envelope(topic="k1.actor.msg", payload=b"payload")
        stub.enqueue(env)
        bridge = AsyncMailboxBridge(stub)
        result = await bridge.receive()
        assert result is not None
        assert result.topic == "k1.actor.msg"

    def test_pending_sync_passthrough(self) -> None:
        stub = StubMailbox()
        stub.enqueue(Envelope(topic="k1.test"))
        stub.enqueue(Envelope(topic="k1.test"))
        bridge = AsyncMailboxBridge(stub)
        assert bridge.pending() == 2


# ===================================================================
# AsyncMailboxRouterBridge
# ===================================================================


class TestAsyncMailboxRouterBridge:
    @pytest.mark.asyncio
    async def test_protocol_conformance(self) -> None:
        bridge = AsyncMailboxRouterBridge(StubMailboxRouter())
        assert isinstance(bridge, IAsyncMailboxRouter)

    @pytest.mark.asyncio
    async def test_register_returns_async_mailbox(self) -> None:
        bridge = AsyncMailboxRouterBridge(StubMailboxRouter())
        mb = await bridge.register("actor-1")
        assert isinstance(mb, AsyncMailboxBridge)
        assert isinstance(mb, IAsyncMailbox)

    @pytest.mark.asyncio
    async def test_deliver_routes_to_actor(self) -> None:
        stub_router = StubMailboxRouter()
        bridge = AsyncMailboxRouterBridge(stub_router)
        mb = await bridge.register("actor-1")
        env = Envelope(topic="k1.msg", payload=b"routed")
        await bridge.deliver("actor-1", env)
        result = await mb.receive()
        assert result is not None
        assert result.payload == b"routed"

    @pytest.mark.asyncio
    async def test_unregister(self) -> None:
        bridge = AsyncMailboxRouterBridge(StubMailboxRouter())
        await bridge.register("actor-1")
        assert await bridge.unregister("actor-1") is True
        assert await bridge.unregister("actor-1") is False

    def test_registered_actors_sync_passthrough(self) -> None:
        stub_router = StubMailboxRouter()
        stub_router.register("actor-a")
        stub_router.register("actor-b")
        bridge = AsyncMailboxRouterBridge(stub_router)
        actors = bridge.registered_actors()
        assert set(actors) == {"actor-a", "actor-b"}
        actors = bridge.registered_actors()
        assert set(actors) == {"actor-a", "actor-b"}
