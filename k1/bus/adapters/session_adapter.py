"""
k1.bus.adapters.session_adapter -- SessionBusAdapter.

Bridges SessionState's IEventPort(ABC) interface to IBus(bytes).

SessionState's IEventPort differs from Fabric's:
    - It's an ABC (not Protocol) -- requires isinstance compatibility
    - emit(event_type, payload: Any) -- no topic arg, uses event_type
    - subscribe(event_type, handler(payload: Any)) -> str  (returns str, not handle)
    - unsubscribe(subscription_id: str) -> bool  (takes str, not handle)
    - has is_connected property
    - has emit_batch method

Topic mapping:
    event_type "sessionstate.mutation.approved"
    -> bus topic "k1.sessionstate.mutation.approved"  (P6.9: flattened)
    event_type "lifecycle.started"
    -> bus topic "k1.session.lifecycle.started"      (legacy fallback)

Serialization (V1): JSON wraps payload as {"payload": <value>}.

Usage::

    from k1.bus.adapters import SessionBusAdapter
    from k1.bus.factory import BusFactory

    bus = BusFactory.create_local()
    adapter = SessionBusAdapter(bus)

    # Use as IEventPort (ABC)
    adapter.emit("sessionstate.mutation.approved", {"section": "plan"})

    # Subscribe
    sub_id = adapter.subscribe("sessionstate.mutation.approved", my_handler)
    adapter.unsubscribe(sub_id)

Exports:
    SessionBusAdapter
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from k1.bus.envelope import Envelope, Priority
from k1.bus.impl.local_bus import LocalBus
from k1.bus.ports.bus import SubscriptionHandle
from k1.sessionstate.ports.events import IEventPort

logger = logging.getLogger(__name__)

# Topic prefix for session state events on the bus
_SESSION_PREFIX = "k1.session."

# Event-type prefixes that already carry their own first segment.
# For these we map directly to ``k1.<event_type>`` instead of double-nesting
# under ``k1.session.<event_type>``.
#
# Phase 6 / P6.9: ``sessionstate.*`` events used to map to
# ``k1.session.sessionstate.*`` (4 segments after k1, double-nested).  The
# adapter now flattens them to ``k1.sessionstate.*`` so the wire topic
# matches the namespace convention and the timing rule for the
# ``k1.sessionstate`` prefix applies.  Caller-facing event_type strings are
# unchanged.
_FLATTEN_PREFIXES = ("sessionstate.",)


def _map_topic(event_type: str) -> str:
    """Map an IEventPort event_type to a bus topic string.

    See ``_FLATTEN_PREFIXES`` for the flattening rule (P6.9).
    """
    for prefix in _FLATTEN_PREFIXES:
        if event_type.startswith(prefix):
            return f"k1.{event_type}"
    return f"{_SESSION_PREFIX}{event_type}"


def _serialize_payload(payload: Any) -> bytes:
    """Serialize any payload to bytes (V1: JSON wrapper)."""
    return json.dumps({"payload": payload}, separators=(",", ":"), default=str).encode("utf-8")


def _deserialize_payload(raw: bytes) -> Any:
    """Deserialize bytes back to the original payload (V1: JSON wrapper)."""
    data = json.loads(raw.decode("utf-8"))
    return data.get("payload", data)


class SessionBusAdapter(IEventPort):
    """
    Adapts IBus(bytes) <-> SessionState IEventPort(Any).

    Extends SessionState's IEventPort ABC so isinstance() checks pass.

    Key differences from Fabric adapter:
        1. Maps event_type -> topic with prefix "k1.session."
        2. Handler receives payload only (no topic arg)
        3. subscribe() returns str (not SubscriptionHandle)
        4. unsubscribe() takes str (not SubscriptionHandle)
        5. is_connected always True for in-process bus

    Serialization:
        Any -> json.dumps({"payload": value}) -> bytes on emit
        bytes -> json.loads -> unwrap "payload" key on callback

    Thread-safe: delegates to LocalBus which is thread-safe.
    """

    __slots__ = ("_bus", "_subscriptions")

    def __init__(self, bus: LocalBus) -> None:
        """
        Create a SessionBusAdapter.

        Args:
            bus: The underlying IBus implementation to delegate to.
        """
        self._bus = bus
        # Track bus handles by subscription_id for unsubscribe
        self._subscriptions: dict[str, SubscriptionHandle] = {}

    # ------------------------------------------------------------------
    # IEventPort: is_connected
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """
        Check if event bus is connected.

        Always True for in-process LocalBus.
        """
        return not self._bus.closed

    # ------------------------------------------------------------------
    # IEventPort: emit
    # ------------------------------------------------------------------

    def emit(self, event_type: str, payload: Any) -> None:
        """
        Emit an event.

        Maps event_type to bus topic with prefix "k1.session.".
        Serializes payload as JSON bytes.

        Fire-and-forget: never raises.

        Args:
            event_type: Event type string (e.g. "sessionstate.mutation.approved").
            payload:    Event payload (any serializable value).
        """
        topic = _map_topic(event_type)
        raw = _serialize_payload(payload)
        self._bus.publish(
            Envelope(
                topic=topic,
                payload=raw,
                priority=Priority.INTERACTIVE,
            )
        )

    # ------------------------------------------------------------------
    # IEventPort: subscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Any], None],
    ) -> str:
        """
        Subscribe to an event type.

        Maps event_type to bus topic with prefix "k1.session.".
        Handler receives deserialized payload only (no topic).

        Args:
            event_type: Event type to subscribe to.
            handler:    Callback ``(payload: Any) -> None``.

        Returns:
            Subscription ID string (for unsubscribe).
        """
        topic = _map_topic(event_type)

        def _wrapper(env: Envelope) -> None:
            try:
                data = _deserialize_payload(env.payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning(
                    "SessionBusAdapter: failed to deserialize payload for "
                    "topic=%s envelope_id=%d -- handler skipped",
                    env.topic,
                    env.envelope_id,
                )
                return
            try:
                handler(data)
            except Exception:
                logger.exception(
                    "SessionBusAdapter: handler error for event_type=%s",
                    event_type,
                )

        bus_handle = self._bus.subscribe(topic, _wrapper)
        self._subscriptions[bus_handle.subscription_id] = bus_handle
        return bus_handle.subscription_id

    # ------------------------------------------------------------------
    # IEventPort: unsubscribe
    # ------------------------------------------------------------------

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from an event.

        Args:
            subscription_id: ID returned from subscribe().

        Returns:
            True if unsubscribed, False if not found.
        """
        handle = self._subscriptions.pop(subscription_id, None)
        if handle is None:
            return False
        return self._bus.unsubscribe(handle)

    # ------------------------------------------------------------------
    # IEventPort: emit_batch (inherited default calls emit() per event)
    # ------------------------------------------------------------------

    # emit_batch is inherited from IEventPort ABC default implementation.
    # It calls self.emit() for each (event_type, payload) tuple.

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def bus(self) -> LocalBus:
        """Access the underlying bus instance."""
        return self._bus

    @property
    def active_subscriptions(self) -> int:
        """Number of active subscriptions through this adapter."""
        return len(self._subscriptions)

    def __repr__(self) -> str:
        return (
            f"SessionBusAdapter(connected={self.is_connected}, "
            f"subscriptions={len(self._subscriptions)})"
        )


__all__ = ["SessionBusAdapter"]
