"""IEventPort -- Planner event pub/sub protocol [F18].

The event port is the only **bidirectional** port on the Planner.  It
publishes plan lifecycle events and subscribes to inbound control events
and HIL responses.

Design decisions (SS15.8, SS15.9)
---------------------------------
- Identical interface to the Fabric's ``IEventPort`` (SS5.1.2, SS15.9).
- ``emit()`` is synchronous, fire-and-forget, MUST NOT raise.
- ``subscribe()`` returns ``SubscriptionHandle`` for later unsubscription.
- Handlers are called synchronously during ``emit()``.
- Handlers MUST NOT raise exceptions.

Published topics (SS28)
-----------------------
- k1.planner.plan.ready.v1
- k1.planner.plan.failed.v1
- k1.planner.plan.cancelled.v1
- k1.planner.micro_replan.ready.v1
- k1.hil.clarification.v1
- k1.hil.approval_request.v1

Subscribed topics (SS28)
-------------------------
- k1.hil.clarification_response.v1
- k1.hil.approval_response.v1
(plan.request and plan.cancel are handled via mailbox path in V1)

Subscription lifecycle (SS23)
-----------------------------
INIT phase:  subscribe(clarification_response), subscribe(approval_response)
SHUTDOWN phase: unsubscribe(both handles)

Callers
-------
- PlannerAgent (subscribe at INIT, unsubscribe at SHUTDOWN)
- CommitService (emit plan.ready)
- PipelineController (emit plan.failed, plan.cancelled)
- HILCoordinator (emit/subscribe HIL events)

Adapter: EventBusAdapter [F34] wraps K1 Event Bus

Import graph (Layer 1)
----------------------
k1.planner.ports.event_port
  -> k1.fabric.ports.event_port  (SubscriptionHandle)
  -> typing
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from k1.fabric.ports.event_port import SubscriptionHandle


@runtime_checkable
class IEventPort(Protocol):
    """Bidirectional event pub/sub port.

    This is a structural protocol (``typing.Protocol``).  Any object with
    matching method signatures satisfies it via structural subtyping.

    Interface is identical to the Fabric's ``IEventPort`` (SS15.9).

    Handler semantics
    -----------------
    - Handlers are called synchronously during ``emit()``.
    - Handlers MUST NOT raise exceptions.
    - If a handler raises, the implementation SHOULD catch and log,
      then continue calling remaining handlers.
    """

    def emit(
        self,
        topic: str,
        payload: Any,
    ) -> None:
        """Emit an event to all subscribers of the given topic.

        Fire-and-forget: this method MUST NOT raise even if no
        subscribers exist or a handler fails.

        Args:
            topic: Event topic string (e.g.
                ``"k1.planner.plan.ready.v1"``).
            payload: Event payload (dataclass or dict).  Should contain
                ``cognitive_trace_id`` per FAB-09.
        """
        ...  # pragma: no cover

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Any], None],
    ) -> SubscriptionHandle:
        """Subscribe a handler to events on the given topic.

        The handler is called with ``(topic, payload)`` each time an
        event matching the topic is emitted.

        Args:
            topic: Event topic to subscribe to.
            handler: Callable ``(topic: str, payload: dict) -> None``.

        Returns:
            ``SubscriptionHandle`` for later unsubscription.
        """
        ...  # pragma: no cover

    def unsubscribe(
        self,
        handle: SubscriptionHandle,
    ) -> bool:
        """Remove a subscription.

        Args:
            handle: The ``SubscriptionHandle`` returned by
                ``subscribe()``.

        Returns:
            ``True`` if the subscription was found and removed,
            ``False`` if it was already removed or never existed.
        """
        ...  # pragma: no cover


__all__ = ["IEventPort"]
