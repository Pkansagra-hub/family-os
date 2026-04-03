"""
k1.concierge.adapters.null_event_subscription -- Null IEventSubscriptionPort for startup tier.

Shared Orchestrator needs IEventSubscriptionPort at construction.
At startup tier, no events need routing — this null adapter absorbs
emit() calls and returns dummy handles from subscribe().

Used by: Shared OrchestratorService at startup tier.

Protocol: k1.orchestrator.ports.event_subscription_port.IEventSubscriptionPort
Gap: SIM-GAP-51
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from k1.fabric.ports.event_port import SubscriptionHandle


class NullEventSubscriptionAdapter:
    """Null IEventSubscriptionPort — absorbs all events, routes nothing.

    Satisfies IEventSubscriptionPort structurally. Used by shared
    Orchestrator at startup tier when no event consumers exist.
    """

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> SubscriptionHandle:
        return SubscriptionHandle(subscription_id="null", topic=topic)

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        return False  # Nothing to remove

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        pass  # Silent drop
