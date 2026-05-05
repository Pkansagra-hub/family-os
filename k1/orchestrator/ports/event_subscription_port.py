"""
k1.orchestrator.ports.event_subscription_port -- IEventSubscriptionPort port (1.4.7).

Synchronous event bus port for subscribing to and emitting events.

Design:
  - Method signatures aligned with Fabric's IEventPort
    (k1/fabric/ports/event_port.py) which is the established K1
    event bus interface.
  - Reuses SubscriptionHandle type from Fabric.
  - All methods SYNC (Fabric's IEventPort is synchronous).
  - Handlers are sync: ``Callable[[str, Dict[str, Any]], None]``.
    If Orchestrator needs async processing, handler should enqueue
    to mailbox (sync) and async processing happens in mailbox loop.
  - Supports topic wildcards (e.g. ``k1.capability.*``).
  - Reconnection: exponential backoff 1s..30s, re-subscribe all
    topics on reconnect, at-most-once delivery.

Required subscriptions (registered at startup by OrchestratorFactory):
  - k1.planner.plan.ready.v1      -> route to mailbox as CommittedPlan
  - k1.planner.plan.failed.v1     -> route to mailbox as PlanFailedEvent
  - k1.planner.plan.cancelled.v1  -> route to mailbox as PlanCancelledEvent
  - k1.fabric.contract.updated.v1 -> route to GapDetector
  - k1.fabric.agent.tool_call.v1  -> route to ExecutionMonitor
  - k1.fabric.agent.llm_call.v1   -> route to ExecutionMonitor
  - k1.orchestration.workflow.trigger_due.v1 -> route to WorkflowScheduler
  - k1.capability.completed.v1    -> route to StepRunner
  - k1.capability.failed.v1       -> route to StepRunner

Consumers:
  - OrchestratorFactory (6.2.1) -- registers all required subscriptions
  - OrchestratorService.init() (6.2.2) -- startup subscription wiring
  - OrchestratorService.shutdown() (6.2.3) -- unsubscribe all

Production adapter: EventSubscriptionAdapter (6.1.7) in adapters/event_subscription_adapter.py
Test adapter: TestEventAdapter (6.1.14) in adapters/test_event_adapter.py

References:
  - k1/fabric/ports/event_port.py (IEventPort pattern)
  - ORCH-009 (trace_id on all events)

Exports:
  IEventSubscriptionPort
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Protocol, runtime_checkable

from k1.fabric.ports.event_port import SubscriptionHandle

# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IEventSubscriptionPort(Protocol):
    """
    Synchronous event bus port for the Orchestrator.

    Mirrors Fabric's IEventPort interface for consistency across
    K1 modules. Provides event subscription, unsubscription, and
    emission.

    Handler semantics:
      - Handlers are called synchronously during emit().
      - Handlers MUST NOT raise exceptions (emit must not fail).
      - Handler signature: ``Callable[[str, Dict[str, Any]], None]``
        receiving ``(topic, payload)``.
      - For async processing, handlers should enqueue to the mailbox
        (sync) and let the mailbox loop handle async work.

    Thread safety:
      Implementations MUST support concurrent emit() calls.
      subscribe()/unsubscribe() MUST be safe with each other.
    """

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> SubscriptionHandle:
        """
        Subscribe a handler to events on the given topic.

        Supports wildcard patterns (e.g. ``"k1.capability.*"``
        matches all capability lifecycle events).

        Args:
            topic: Event topic or pattern to subscribe to.
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
            handle: The SubscriptionHandle returned by subscribe().

        Returns:
            True if the subscription was found and removed,
            False if it was already removed or never existed.
        """
        ...  # pragma: no cover

    def emit(
        self,
        topic: str,
        payload: Dict[str, Any],
    ) -> None:
        """
        Publish an event to all subscribers of the given topic.

        Fire-and-forget: this method MUST NOT raise even if no
        subscribers exist or a handler fails. Used for internal
        re-routing (e.g. routing received plan events back to
        mailbox).

        Args:
            topic: Event topic string.
            payload: Event payload dict. Should contain
                ``cognitive_trace_id`` per ORCH-09.
        """
        ...  # pragma: no cover
