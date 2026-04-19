"""EventBusAdapter -- production event pub/sub adapter [F34].

Implements ``IEventPort`` (Planner port SS15.8) by wrapping
Fabric's ``IEventPort`` (5.1.2).

Adapter wiring (SS16.1.7, SS16.3):
    Planner IEventPort -> EventBusAdapter -> Fabric IEventPort

Design:
    - Identical interface between Planner and Fabric IEventPort (SS15.9)
    - emit() is synchronous, fire-and-forget, MUST NOT raise
    - subscribe() returns SubscriptionHandle for later unsubscription
    - unsubscribe() passthrough
    - Thin passthrough adapter (interface identity per SS15.9)

Import graph (Layer 2)
----------------------
k1.planner.adapters.event_bus_adapter
  -> k1.fabric.ports.event_port  (SubscriptionHandle)
  -> typing, logging
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from k1.fabric.ports.event_port import IEventPort, SubscriptionHandle

logger = logging.getLogger(__name__)


class EventBusAdapter:
    """Production Event Bus adapter (SS16.1.7).

    Wraps Fabric's ``IEventPort`` to implement the Planner's
    ``IEventPort``.  Because the two port interfaces are identical
    (SS15.9), this is a thin passthrough adapter.

    Fire-and-forget contract on emit:
        ``emit()`` catches exceptions and logs them.  It NEVER raises
        to the caller.

    Subscription lifecycle (SS23):
        - INIT phase:  subscribe to clarification/approval response topics
        - SHUTDOWN:    unsubscribe all handles
    """

    __slots__ = ("_bus",)

    def __init__(self, event_port: IEventPort) -> None:
        """Initialize EventBusAdapter.

        Args:
            event_port: Fabric ``IEventPort`` instance (5.1.2) with
                ``emit()``, ``subscribe()``, ``unsubscribe()`` methods.
        """
        self._bus = event_port

    # ------------------------------------------------------------------
    # IEventPort implementation
    # ------------------------------------------------------------------

    def emit(
        self,
        topic: str,
        payload: Any,
    ) -> None:
        """Emit an event to all subscribers of the given topic.

        Fire-and-forget: this method NEVER raises, even on bus failure.

        Args:
            topic: Event topic string.
            payload: Event payload (dataclass or dict).
        """
        try:
            self._bus.emit(topic, payload)
        except Exception:
            logger.exception(
                "EventBus emit failed, dropping event (fire-and-forget)",
                extra={"topic": topic},
            )

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Any], None],
    ) -> SubscriptionHandle:
        """Subscribe a handler to events on the given topic.

        Args:
            topic: Event topic to subscribe to.
            handler: Callable ``(topic: str, payload: Any) -> None``.

        Returns:
            ``SubscriptionHandle`` for later unsubscription.
        """
        return self._bus.subscribe(topic, handler)

    def unsubscribe(
        self,
        handle: SubscriptionHandle,
    ) -> bool:
        """Remove a subscription.

        Args:
            handle: The ``SubscriptionHandle`` returned by ``subscribe()``.

        Returns:
            ``True`` if the subscription was removed, ``False`` if the
            handle was not found.
        """
        return self._bus.unsubscribe(handle)


__all__ = ["EventBusAdapter"]
