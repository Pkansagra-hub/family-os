"""
k1.fabric.adapters.event_port_prod -- Production EventPortProdAdapter.

Dedicated production IEventPort that bridges Fabric events to IBus.

Design:
  - Wraps an IBus instance (typed as ``Any`` for loose coupling).
  - ``emit()`` serializes Dict payload → JSON bytes → Envelope → publish.
  - ``subscribe()`` wraps the handler to deserialize Envelope → Dict
    before calling the Fabric-level handler.
  - ``unsubscribe()`` translates SubscriptionHandle → IBus handle.
  - Thread-safe: delegates to IBus which is thread-safe.

Replaces LocalEventAdapter's dual production/test role:
  - LocalEventAdapter continues as test/in-process adapter.
  - This adapter is for production deployment with a real bus.

Consumers:
  - CapabilityRegistry, ModuleLoader, CircuitBreaker, HealthChecker,
    FabricDispatcher, etc. -- all Fabric subsystems that emit events.
  - Injected via FabricFactory.create_with_ports(event_port=...)

Structural subtyping:
  Satisfies IEventPort protocol without inheriting from it.

References:
  - IEventPort (5.1.2)
  - FabricBusAdapter (k1/bus/adapters/fabric_adapter.py) -- same
    serialization pattern, but this adapter lives in Fabric's layer
    and is exclusively an IEventPort (not IDeltaBusPort).
  - LocalEventAdapter (5.2.3) -- in-process counterpart

Exports:
  EventPortProdAdapter
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any, Callable, Dict

from k1.fabric.ports.event_port import SubscriptionHandle

logger = logging.getLogger(__name__)


class EventPortProdAdapter:
    """
    Production event port adapter for Fabric's IEventPort.

    Wraps an IBus instance and serializes Fabric Dict payloads to/from
    bus Envelope bytes.  Thread-safe.

    Implements ``IEventPort`` via structural subtyping:
      - emit(topic, payload) -> None
      - subscribe(topic, handler) -> SubscriptionHandle
      - unsubscribe(handle) -> bool
    """

    __slots__ = (
        "_bus",
        "_lock",
        "_subscriptions",
        "_emit_count",
        "_subscribe_count",
    )

    def __init__(self, bus: Any) -> None:
        """
        Initialize with a bus instance.

        Args:
            bus: An IBus-compatible object with ``publish(envelope)``,
                ``subscribe(pattern, handler)`` and
                ``unsubscribe(handle)`` methods.  Typed as ``Any``
                for loose coupling.
        """
        self._bus = bus
        self._lock = threading.RLock()
        # Map our SubscriptionHandle.subscription_id -> bus-level handle
        self._subscriptions: Dict[str, Any] = {}
        self._emit_count = 0
        self._subscribe_count = 0

    # ------------------------------------------------------------------
    # IEventPort: emit
    # ------------------------------------------------------------------

    def emit(self, topic: str, payload: Any) -> None:
        """
        Emit an event to all subscribers via the bus.

        Serializes the payload to JSON bytes and publishes as an Envelope.
        Fire-and-forget: never raises.

        Args:
            topic:   Event topic string.
            payload: Event payload (dict or dataclass with to_dict()).
                     Should contain ``cognitive_trace_id`` per FAB-09.
        """
        with self._lock:
            self._emit_count += 1

        # Normalize payload to dict
        if hasattr(payload, "to_dict"):
            payload_dict = payload.to_dict()
        elif isinstance(payload, dict):
            payload_dict = payload
        else:
            payload_dict = {"value": payload}

        try:
            raw = json.dumps(payload_dict, separators=(",", ":"), default=str).encode("utf-8")
        except (TypeError, ValueError):
            logger.warning(
                "EventPortProdAdapter: failed to serialize payload for " "topic=%s",
                topic,
                exc_info=True,
            )
            return

        try:
            from k1.bus.envelope.envelope import Envelope, Priority

            trace_id = ""
            if isinstance(payload_dict, dict):
                trace_id = str(payload_dict.get("cognitive_trace_id", ""))

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
                "EventPortProdAdapter: failed to publish to topic=%s",
                topic,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # IEventPort: subscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Any], None],
    ) -> SubscriptionHandle:
        """
        Subscribe a handler to events on the given topic.

        The handler receives ``(topic, payload_dict)`` — the adapter
        deserializes the bus Envelope bytes back to a Dict before
        calling the handler.

        Args:
            topic:   Topic pattern (exact or wildcard).
            handler: Callable ``(topic: str, payload: Any) -> None``.

        Returns:
            SubscriptionHandle for later unsubscription.
        """
        sub_id = str(uuid.uuid4())

        def _wrapper(envelope: Any) -> None:
            """Deserialize Envelope payload and invoke Fabric handler."""
            try:
                data = json.loads(envelope.payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                logger.warning(
                    "EventPortProdAdapter: failed to deserialize payload "
                    "for topic=%s -- handler skipped",
                    getattr(envelope, "topic", topic),
                )
                return
            try:
                handler(getattr(envelope, "topic", topic), data)
            except Exception:
                logger.exception(
                    "EventPortProdAdapter: handler error for topic=%s",
                    getattr(envelope, "topic", topic),
                )

        try:
            bus_handle = self._bus.subscribe(topic, _wrapper)
            with self._lock:
                self._subscriptions[sub_id] = bus_handle
                self._subscribe_count += 1
        except Exception:
            logger.warning(
                "EventPortProdAdapter: failed to subscribe to topic=%s",
                topic,
                exc_info=True,
            )

        return SubscriptionHandle(
            subscription_id=sub_id,
            topic=topic,
        )

    # ------------------------------------------------------------------
    # IEventPort: unsubscribe
    # ------------------------------------------------------------------

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """
        Remove a subscription.

        Translates the Fabric SubscriptionHandle to the bus-level
        handle and delegates to IBus.unsubscribe().

        Args:
            handle: The SubscriptionHandle returned by subscribe().

        Returns:
            True if the subscription was found and removed.
        """
        with self._lock:
            bus_handle = self._subscriptions.pop(handle.subscription_id, None)

        if bus_handle is None:
            return False

        try:
            return self._bus.unsubscribe(bus_handle)
        except Exception:
            logger.warning(
                "EventPortProdAdapter: failed to unsubscribe handle=%s",
                handle.subscription_id,
                exc_info=True,
            )
            return False

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def emit_count(self) -> int:
        """Number of emit() calls made."""
        with self._lock:
            return self._emit_count

    @property
    def subscribe_count(self) -> int:
        """Number of subscribe() calls made."""
        with self._lock:
            return self._subscribe_count

    @property
    def active_subscriptions(self) -> int:
        """Number of currently active subscriptions."""
        with self._lock:
            return len(self._subscriptions)

    @property
    def bus(self) -> Any:
        """Access the underlying bus instance."""
        return self._bus

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"EventPortProdAdapter(bus={self._bus!r}, "
                f"emits={self._emit_count}, "
                f"subs={len(self._subscriptions)})"
            )


__all__ = ["EventPortProdAdapter"]
