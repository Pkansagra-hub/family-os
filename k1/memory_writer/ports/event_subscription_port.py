"""
k1.memory_writer.ports.event_subscription_port -- IEventSubscriptionPort protocol.

K1 Bus subscription for receiving turn completion events.

Memory Writer subscribes to exactly one topic:
  - turn.complete.v1 (from Concierge via K1 Bus)

This is the entry point for the MW pipeline. When a turn completes,
the TurnDispatcher receives the event and kicks off the 5-stage
extraction pipeline.

Production adapter: EventSubscriptionAdapter in adapters/event_subscription_adapter.py
Test adapter: In adapters/test_adapters.py

References:
  - Epic 1.9 (Event definitions)
  - k1/orchestrator/ports/event_subscription_port.py (pattern reference)
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine, Protocol, runtime_checkable

from k1.memory_writer.types import Subscription


@runtime_checkable
class IEventSubscriptionPort(Protocol):
    """
    K1 Bus subscription for event-driven pipeline triggering.

    MW subscribes to turn.complete.v1 to start extraction.
    MW also publishes observability events (filter decisions,
    extraction completions, batch submissions, errors, circuit state).
    """

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> Subscription:
        """
        Subscribe to a K1 Bus topic with an async handler.

        Args:
            topic: Event topic to subscribe to (e.g. "turn.complete.v1").
            handler: Async callable invoked when an event arrives.
                Signature: async def handler(payload: dict) -> None

        Returns:
            Subscription handle for later unsubscription.

        Raises:
            AdapterError: If subscription fails.
        """
        ...  # pragma: no cover

    async def unsubscribe(
        self,
        subscription_id: str,
    ) -> None:
        """
        Remove a subscription by its ID.

        Args:
            subscription_id: The ID from the Subscription object.

        Raises:
            AdapterError: If unsubscription fails.
        """
        ...  # pragma: no cover

    async def publish(
        self,
        topic: str,
        payload: dict,
    ) -> None:
        """
        Publish an observability event to the K1 Bus.

        Used by MW pipeline stages to emit telemetry events:
          - k1.mw.filter.decision.v1
          - k1.mw.extraction.complete.v1
          - k1.mw.batch.submitted.v1
          - k1.mw.pipeline.error.v1
          - k1.mw.circuit.open.v1

        Args:
            topic: Event topic to publish to.
            payload: Event payload dict.

        Raises:
            AdapterError: If publish fails (non-critical, log and continue).
        """
        ...  # pragma: no cover
