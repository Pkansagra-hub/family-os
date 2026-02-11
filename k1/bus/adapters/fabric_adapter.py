"""
k1.bus.adapters.fabric_adapter -- FabricBusAdapter.

Bridges Fabric's IEventPort(Dict) and IDeltaBusPort interfaces to IBus(bytes).

Serialization (V1): JSON -- Dict <-> bytes round-trip via json.dumps/loads.
Future V2: FlatBuffers zero-copy.

The adapter satisfies BOTH Fabric port protocols simultaneously:
    - IEventPort:    emit(topic, Dict), subscribe(topic, handler(topic, Dict))
    - IDeltaBusPort: emit_delta(agent_id, delta_type, section, data)

Delta topics follow the pattern: ``k1.agent.{agent_id}.delta.v1``

Usage::

    from k1.bus.adapters import FabricBusAdapter
    from k1.bus.factory import BusFactory

    bus = BusFactory.create_local()
    adapter = FabricBusAdapter(bus)

    # Use as IEventPort
    adapter.emit("k1.fabric.capability.registered.v1", {"name": "search"})

    # Use as IDeltaBusPort
    adapter.emit_delta("agent-1", "plan_update", "plan", {"step": 3})

    # Subscribe (handler receives deserialized Dict)
    handle = adapter.subscribe("k1.fabric.*", my_handler)
    adapter.unsubscribe(handle)

Exports:
    FabricBusAdapter
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict

from k1.bus.envelope import Envelope, Priority
from k1.bus.impl.local_bus import LocalBus
from k1.bus.ports.bus import SubscriptionHandle

# Fabric port types -- import for isinstance checks in tests.
# We use structural subtyping so these imports are optional at runtime.
from k1.fabric.ports.delta_bus import DeltaPayload
from k1.fabric.ports.event_port import SubscriptionHandle as FabricSubscriptionHandle

logger = logging.getLogger(__name__)


def _serialize_payload(payload: Dict[str, Any]) -> bytes:
    """Serialize a Dict payload to bytes (V1: JSON)."""
    return json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")


def _deserialize_payload(raw: bytes) -> Dict[str, Any]:
    """Deserialize bytes back to a Dict payload (V1: JSON)."""
    return json.loads(raw.decode("utf-8"))


class FabricBusAdapter:
    """
    Adapts IBus(bytes) <-> Fabric IEventPort(Dict) + IDeltaBusPort.

    Satisfies Fabric's IEventPort Protocol (structural subtyping):
        emit(topic, payload: Dict) -> None
        subscribe(topic, handler: (str, Dict) -> None) -> SubscriptionHandle
        unsubscribe(handle) -> bool

    Satisfies Fabric's IDeltaBusPort Protocol (structural subtyping):
        emit_delta(agent_id, delta_type, section, data: Dict) -> None

    Serialization:
        Dict -> json.dumps -> bytes on publish
        bytes -> json.loads -> Dict on subscribe callback

    Thread-safe: delegates to LocalBus which is thread-safe.
    """

    __slots__ = ("_bus",)

    def __init__(self, bus: LocalBus) -> None:
        """
        Create a FabricBusAdapter.

        Args:
            bus: The underlying IBus implementation to delegate to.
        """
        self._bus = bus

    # ------------------------------------------------------------------
    # IEventPort: emit
    # ------------------------------------------------------------------

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        Emit an event to all subscribers of the given topic.

        Serializes the Dict payload to bytes and publishes to the bus.
        Fire-and-forget: never raises even if no subscribers exist.

        Args:
            topic:   Event topic string.
            payload: Event payload dict.  Should contain ``cognitive_trace_id``
                     per FAB-09.
        """
        raw = _serialize_payload(payload)
        trace_id = payload.get("cognitive_trace_id", "")
        self._bus.publish(
            Envelope(
                topic=topic,
                payload=raw,
                cognitive_trace_id=str(trace_id) if trace_id else "",
                priority=Priority.INTERACTIVE,
            )
        )

    # ------------------------------------------------------------------
    # IEventPort: subscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> FabricSubscriptionHandle:
        """
        Subscribe a handler to events on the given topic.

        The handler is called with ``(topic, payload_dict)`` -- the adapter
        deserializes the bus bytes back to a Dict.

        Args:
            topic:   Topic pattern (exact or wildcard via trie).
            handler: Callable ``(topic: str, payload: Dict) -> None``.

        Returns:
            FabricSubscriptionHandle compatible with Fabric's IEventPort.
        """

        def _wrapper(env: Envelope) -> None:
            try:
                data = _deserialize_payload(env.payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning(
                    "FabricBusAdapter: failed to deserialize payload for "
                    "topic=%s envelope_id=%d -- handler skipped",
                    env.topic,
                    env.envelope_id,
                )
                return
            try:
                handler(env.topic, data)
            except Exception:
                logger.exception(
                    "FabricBusAdapter: handler error for topic=%s",
                    env.topic,
                )

        bus_handle = self._bus.subscribe(topic, _wrapper)
        return FabricSubscriptionHandle(
            subscription_id=bus_handle.subscription_id,
            topic=bus_handle.pattern,
        )

    # ------------------------------------------------------------------
    # IEventPort: unsubscribe
    # ------------------------------------------------------------------

    def unsubscribe(self, handle: FabricSubscriptionHandle) -> bool:
        """
        Remove a subscription.

        Args:
            handle: The FabricSubscriptionHandle returned by subscribe().

        Returns:
            True if the subscription was found and removed.
        """
        bus_handle = SubscriptionHandle(
            subscription_id=handle.subscription_id,
            pattern=handle.topic,
        )
        return self._bus.unsubscribe(bus_handle)

    # ------------------------------------------------------------------
    # IDeltaBusPort: emit_delta
    # ------------------------------------------------------------------

    def emit_delta(
        self,
        agent_id: str,
        delta_type: str,
        section: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Emit a delta event from an agent.

        Publishes to topic ``k1.agent.{agent_id}.delta.v1`` with the
        delta payload serialized as JSON bytes.

        Args:
            agent_id:   The agent that produced the delta.
            delta_type: Type of state change (e.g. "plan_update").
            section:    Which section of agent state changed.
            data:       Arbitrary payload describing the change.
        """
        topic = f"k1.agent.{agent_id}.delta.v1"
        payload = DeltaPayload(
            agent_id=agent_id,
            delta_type=delta_type,
            section=section,
            data=data,
        )
        raw = _serialize_payload(payload.to_dict())
        self._bus.publish(
            Envelope(
                topic=topic,
                payload=raw,
                priority=Priority.REALTIME,
            )
        )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def bus(self) -> LocalBus:
        """Access the underlying bus instance."""
        return self._bus

    def __repr__(self) -> str:
        return f"FabricBusAdapter(bus={self._bus!r})"


__all__ = ["FabricBusAdapter"]
