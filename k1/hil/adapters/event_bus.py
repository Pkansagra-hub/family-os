"""KernelHILEventAdapter — bridges K1 sync IBus to HIL-local IEventPort.

The HIL service expects an event port with:

    async def publish(self, topic: str, payload: dict[str, Any]) -> None
    def subscribe(self, topic: str, handler: EventHandler) -> SubscriptionHandle
    def unsubscribe(self, handle: SubscriptionHandle) -> None

where EventHandler is `async (topic, payload_dict) -> None`.

K1's IBus (LocalBus) is sync and traffics in `Envelope(topic, payload: bytes)`
with sync handlers. This adapter:

  - Serialises dict payloads to JSON bytes on publish().
  - Wraps sync bus handlers so they decode the envelope back to a dict and
    schedule the user-supplied async handler on the loop captured at
    subscribe() time.

Thread safety: delegates to IBus, which is thread-safe. Subscription handles
are opaque tuples `(topic, sync_wrapper, bus_handle)` — the adapter resolves
the bus handle on unsubscribe().
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

EventHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class KernelHILEventAdapter:
    """Adapt a K1 IBus to the HIL service's IEventPort Protocol."""

    __slots__ = ("_bus", "_lock", "_loop")

    def __init__(self, bus: Any, *, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Initialise.

        Args:
            bus: A K1 IBus-compatible object with ``publish(envelope)``,
                ``subscribe(topic, handler)`` and ``unsubscribe(handle)``.
            loop: The event loop on which async handlers should be
                scheduled. If ``None``, the running loop at subscribe()
                time is used.
        """
        self._bus = bus
        self._lock = threading.RLock()
        self._loop = loop

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish a dict payload to ``topic``. Best-effort; never raises."""
        try:
            from k1.bus.envelope.envelope import Envelope, Priority
        except Exception:  # pragma: no cover - import guard
            logger.warning("KernelHILEventAdapter: bus envelope import failed", exc_info=True)
            return

        try:
            raw = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
        except (TypeError, ValueError):
            logger.warning(
                "KernelHILEventAdapter: failed to serialise payload for topic=%s",
                topic,
                exc_info=True,
            )
            return

        trace_id = str(payload.get("trace_id", "")) if isinstance(payload, dict) else ""
        try:
            self._bus.publish(
                Envelope(
                    topic=topic,
                    payload=raw,
                    cognitive_trace_id=trace_id,
                    priority=Priority.INTERACTIVE,
                )
            )
        except Exception:
            logger.warning(
                "KernelHILEventAdapter: bus.publish failed topic=%s",
                topic,
                exc_info=True,
            )

    def subscribe(self, topic: str, handler: EventHandler) -> Any:
        """Subscribe ``handler`` to ``topic``.

        Returns an opaque handle accepted by ``unsubscribe()``.
        """
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop yet — defer capture to first delivery.
                loop = None

        def _sync_wrapper(envelope: Any) -> None:
            try:
                data = json.loads(envelope.payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                logger.warning(
                    "KernelHILEventAdapter: failed to deserialise payload topic=%s",
                    getattr(envelope, "topic", topic),
                )
                return
            target_loop = loop
            if target_loop is None:
                try:
                    target_loop = asyncio.get_event_loop()
                except RuntimeError:
                    logger.warning(
                        "KernelHILEventAdapter: no event loop for HIL handler topic=%s",
                        getattr(envelope, "topic", topic),
                    )
                    return
            try:
                asyncio.run_coroutine_threadsafe(
                    handler(getattr(envelope, "topic", topic), data),
                    target_loop,
                )
            except Exception:
                logger.exception(
                    "KernelHILEventAdapter: failed to schedule handler topic=%s",
                    getattr(envelope, "topic", topic),
                )

        with self._lock:
            bus_handle = self._bus.subscribe(topic, _sync_wrapper)
        # The handle the HIL service stores is opaque to it; we keep the
        # bus handle inside the tuple so unsubscribe() can pass it back.
        return (topic, _sync_wrapper, bus_handle)

    def unsubscribe(self, handle: Any) -> None:
        """Remove a previously registered subscription. Idempotent."""
        if handle is None:
            return
        try:
            _topic, _wrapper, bus_handle = handle
        except (TypeError, ValueError):
            logger.warning("KernelHILEventAdapter: malformed unsubscribe handle")
            return
        try:
            self._bus.unsubscribe(bus_handle)
        except Exception:
            logger.warning(
                "KernelHILEventAdapter: bus.unsubscribe failed",
                exc_info=True,
            )


__all__ = ["KernelHILEventAdapter"]
