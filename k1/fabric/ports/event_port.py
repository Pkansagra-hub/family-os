"""
k1.fabric.ports.event_port -- IEventPort port (5.1.2).

Event emission and subscription for all Fabric events.

Design:
  - All Fabric events are emitted through this port.
  - FAB-09: every event payload MUST carry ``cognitive_trace_id``.
  - Supports both fire-and-forget emission and subscription callbacks.
  - SubscriptionHandle: opaque handle returned by subscribe(), used
    for unsubscription.

Event topics emitted by Fabric subsystems:
  - ``k1.fabric.capability.registered.v1``       (Registry 2.2.2)
  - ``k1.fabric.capability.unregistered.v1``      (Registry 2.2.2)
  - ``k1.fabric.module.loaded.v1``                (ModuleLoader 2.3.2)
  - ``k1.fabric.circuit.state.changed.v1``        (CircuitBreaker 3.4.1)
  - ``k1.fabric.provider.health.changed.v1``      (HealthChecker 3.6.1)
  - ``k1.fabric.output.validation.failed.v1``     (ValidationFallback 3.5.4)
  - ``k1.fabric.pressure.warning.v1``             (FabricDispatcher 4.4.1)
  - ``k1.fabric.pressure.shedding.v1``            (FabricDispatcher 4.4.1)
  - ``k1.agent.{agent_id}.delta.v1``              (DeltaEmitter 4.3.4)

Consumers:
  - CapabilityRegistry (2.2.2) -- emit on register/unregister
  - ModuleLoader (2.3.2) -- emit on module loaded
  - CircuitBreaker (3.4.1) -- emit on state transition
  - HealthChecker (3.6.1) -- emit on health state change
  - OutputValidation fallback (3.5.4) -- emit on rejection
  - FabricDispatcher (4.4.1) -- emit on backpressure transition
  - FabricMailbox backpressure (4.4.2)

Production adapter: K1 EventBus adapter (5.2.3)
Test adapter: LocalEventAdapter with capture mode (5.2.3)

References:
  - FAB-09 (cognitive_trace_id on all events)
  - SessionState IEventPort pattern (reuse)

Exports:
  IEventPort
  SubscriptionHandle
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubscriptionHandle:
    """
    Opaque handle for event subscription management.

    Returned by ``IEventPort.subscribe()``.  Pass to
    ``IEventPort.unsubscribe()`` to remove the subscription.

    Attributes:
        subscription_id: Unique identifier for this subscription.
        topic: The topic this subscription is listening to.
    """

    subscription_id: str = ""
    topic: str = ""


# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IEventPort(Protocol):
    """
    Event emission and subscription port for the Capability Fabric.

    This is the canonical port interface (5.1.2).  Any object with
    matching method signatures satisfies this protocol (structural
    subtyping via ``typing.Protocol``).

    FAB-09 enforcement:
      Every event payload SHOULD contain a ``cognitive_trace_id`` key.
      The port itself does not enforce this -- it is the caller's
      responsibility to include it.  Test adapters can verify this
      in capture mode.

    Thread safety:
      Implementations MUST support concurrent calls to ``emit()``
      from multiple threads/tasks.  ``subscribe()`` and ``unsubscribe()``
      need not be concurrent-safe with ``emit()`` but MUST be safe
      with each other.

    Handler semantics:
      - Handlers are called synchronously during ``emit()``.
      - Handlers MUST NOT raise exceptions (emit must not fail).
      - If a handler raises, the implementation SHOULD catch and log,
        then continue calling remaining handlers.
    """

    def emit(
        self,
        topic: str,
        payload: Any,
    ) -> None:
        """
        Emit an event to all subscribers of the given topic.

        Fire-and-forget: this method MUST NOT raise even if no
        subscribers exist or a handler fails.

        Args:
            topic: Event topic string (e.g. ``"k1.fabric.capability.registered.v1"``).
            payload: Event payload (dataclass or dict).  Should contain
                ``cognitive_trace_id`` per FAB-09.
        """
        ...  # pragma: no cover

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Any], None],
    ) -> SubscriptionHandle:
        """
        Subscribe a handler to events on the given topic.

        The handler is called with ``(topic, payload)`` each time
        an event matching the topic is emitted.

        Args:
            topic: Event topic to subscribe to.
            handler: Callable ``(topic: str, payload: dict) -> None``.

        Returns:
            SubscriptionHandle for later unsubscription.
        """
        ...  # pragma: no cover

    def unsubscribe(
        self,
        handle: SubscriptionHandle,
    ) -> bool:
        """
        Remove a subscription.

        Args:
            handle: The SubscriptionHandle returned by ``subscribe()``.

        Returns:
            True if the subscription was found and removed,
            False if it was already removed or never existed.
        """
        ...  # pragma: no cover
