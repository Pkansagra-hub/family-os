"""
AsyncBusBridge -- async wrappers for the sync K1 bus primitives.

Issue 2.0.1 – Pre-requisite: give async callers (Fabric, Orchestrator,
Planner, ModelHub) a non-blocking interface to the threaded LocalBus,
LocalMailbox, and LocalMailboxRouter.

Strategy
--------
*  **Write / blocking calls** are offloaded via ``asyncio.to_thread`` so the
   event-loop is never blocked by the underlying ``threading.Lock`` in the
   sync bus implementation.

*  **Lock-free reads** (``pending``, ``registered_actors``) are direct
   pass-throughs — no need for a thread hop.

*  **Handler bridging**: The sync bus dispatches on its own thread via
   ``BusHandler = Callable[[Envelope], None]``.  When an *async* handler
   is registered through ``AsyncBusBridge.subscribe``, we wrap it in a
   thin sync shim that schedules the coroutine onto the caller's event-loop
   via ``asyncio.run_coroutine_threadsafe``.

Classes
-------
- :class:`AsyncBusBridge`          wraps ``IBus``
- :class:`AsyncMailboxBridge`      wraps ``IMailbox``
- :class:`AsyncMailboxRouterBridge` wraps ``IMailboxRouter``
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from k1.bus.envelope import Envelope
from k1.bus.ports.async_bus import AsyncBusHandler
from k1.bus.ports.bus import BusHandler, IBus, SubscriptionHandle
from k1.bus.ports.mailbox import IMailbox, IMailboxRouter, MailboxConfig

logger = logging.getLogger(__name__)


# ===================================================================
# AsyncBusBridge
# ===================================================================


class AsyncBusBridge:
    """
    Async facade over a sync :class:`IBus` implementation.

    Implements the :class:`IAsyncBus` protocol.

    Parameters
    ----------
    sync_bus : IBus
        The underlying synchronous bus (e.g. ``LocalBus``).
    loop : asyncio.AbstractEventLoop | None
        Event-loop used to schedule async handler callbacks.
        Defaults to the running loop at construction time.
    """

    __slots__ = ("_sync", "_loop", "_async_handler_errors")

    def __init__(
        self,
        sync_bus: IBus,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._sync = sync_bus
        self._loop = loop or asyncio.get_running_loop()
        # P6.1 (I-16): track async handler exceptions surfaced via
        # ``Future.add_done_callback`` so callers can observe failures
        # that would otherwise be silently swallowed.
        self._async_handler_errors: int = 0

    @property
    def async_handler_errors(self) -> int:
        """Cumulative count of exceptions raised by async handlers (P6.1 / I-16)."""
        return self._async_handler_errors

    # -- IAsyncBus ---------------------------------------------------------

    async def publish(self, envelope: Envelope) -> None:
        """Offload publish to a worker thread (acquires bus lock)."""
        await asyncio.to_thread(self._sync.publish, envelope)

    async def subscribe(
        self,
        pattern: str,
        handler: AsyncBusHandler,
    ) -> SubscriptionHandle:
        """
        Subscribe with an *async* handler.

        The handler coroutine is scheduled onto *self._loop* from the
        bus dispatch thread via ``run_coroutine_threadsafe``.
        """
        sync_shim = self._wrap_async_handler(handler)
        return await asyncio.to_thread(self._sync.subscribe, pattern, sync_shim)

    async def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """Offload unsubscribe to a worker thread."""
        return await asyncio.to_thread(self._sync.unsubscribe, handle)

    # -- internal ----------------------------------------------------------

    def _wrap_async_handler(self, handler: AsyncBusHandler) -> BusHandler:
        """
        Return a sync callable that schedules *handler* on the event-loop.

        The sync bus dispatches handlers on its own thread; this shim
        bridges back to async-land without blocking the dispatch thread.

        P6.1 (I-16): the scheduled ``Future`` is observed via
        ``add_done_callback`` so exceptions raised by the async handler are
        logged and counted instead of being silently swallowed.
        """
        loop = self._loop
        bridge = self  # capture for the done callback

        def _on_done(fut: "asyncio.Future[None]", env: Envelope) -> None:
            try:
                exc = fut.exception()
            except asyncio.CancelledError:
                logger.warning(
                    "Async bus handler cancelled for topic=%s envelope_id=%s",
                    env.topic,
                    env.envelope_id,
                )
                bridge._async_handler_errors += 1
                return
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "Failed to inspect async handler future for topic=%s envelope_id=%s",
                    env.topic,
                    env.envelope_id,
                )
                bridge._async_handler_errors += 1
                return
            if exc is not None:
                logger.error(
                    "Async bus handler raised %s for topic=%s envelope_id=%s: %s",
                    type(exc).__name__,
                    env.topic,
                    env.envelope_id,
                    exc,
                    exc_info=exc,
                )
                bridge._async_handler_errors += 1

        def _sync_shim(envelope: Envelope) -> None:
            fut = asyncio.run_coroutine_threadsafe(handler(envelope), loop)
            fut.add_done_callback(lambda f, env=envelope: _on_done(f, env))

        return _sync_shim


# ===================================================================
# AsyncMailboxBridge
# ===================================================================


class AsyncMailboxBridge:
    """
    Async facade over a sync :class:`IMailbox`.

    Implements the :class:`IAsyncMailbox` protocol.

    Parameters
    ----------
    sync_mailbox : IMailbox
        Underlying synchronous mailbox.
    """

    __slots__ = ("_sync",)

    def __init__(self, sync_mailbox: IMailbox) -> None:
        self._sync = sync_mailbox

    # -- IAsyncMailbox -----------------------------------------------------

    async def receive(self, timeout_ms: int = 0) -> Optional[Envelope]:
        """
        Offload blocking receive to a worker thread.

        ``IMailbox.receive`` can block for up to *timeout_ms*; offloading
        keeps the event-loop responsive.
        """
        return await asyncio.to_thread(self._sync.receive, timeout_ms)

    def pending(self) -> int:
        """Lock-free — direct passthrough, no thread hop needed."""
        return self._sync.pending()


# ===================================================================
# AsyncMailboxRouterBridge
# ===================================================================


class AsyncMailboxRouterBridge:
    """
    Async facade over a sync :class:`IMailboxRouter`.

    Implements the :class:`IAsyncMailboxRouter` protocol.

    Parameters
    ----------
    sync_router : IMailboxRouter
        Underlying synchronous mailbox router.
    """

    __slots__ = ("_sync",)

    def __init__(self, sync_router: IMailboxRouter) -> None:
        self._sync = sync_router

    # -- IAsyncMailboxRouter -----------------------------------------------

    async def deliver(self, actor_id: str, envelope: Envelope) -> None:
        """Offload deliver (may raise BackpressureError) to a worker thread."""
        await asyncio.to_thread(self._sync.deliver, actor_id, envelope)

    async def register(
        self,
        actor_id: str,
        config: Optional[MailboxConfig] = None,
    ) -> AsyncMailboxBridge:
        """
        Register an actor and return an :class:`AsyncMailboxBridge`.

        The underlying sync router creates a ``LocalMailbox``; we wrap it
        in an async view before returning.
        """
        sync_mailbox = await asyncio.to_thread(self._sync.register, actor_id, config)
        return AsyncMailboxBridge(sync_mailbox)

    async def unregister(self, actor_id: str) -> bool:
        """Offload unregister to a worker thread."""
        return await asyncio.to_thread(self._sync.unregister, actor_id)

    def registered_actors(self) -> list[str]:
        """Lock-free — direct passthrough."""
        return self._sync.registered_actors()


__all__ = [
    "AsyncBusBridge",
    "AsyncMailboxBridge",
    "AsyncMailboxRouterBridge",
]
