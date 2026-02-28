"""
poc.k1_poc.events.registry -- event_type -> canonical class mapping.

M1 E1.1.6: Maps event_type strings to their canonical dataclass for
deserialization. This is separate from BUILDERS because event_type
(domain concept) != topic (transport concept).

Usage::

    from poc.k1_poc.events.registry import EVENT_TYPE_REGISTRY, resolve_event_type

    cls = resolve_event_type("task.completed")  # -> TaskCompleted
    event = cls.from_payload(payload_dict)
"""

from __future__ import annotations

from typing import Any

from poc.k1_poc.events.base import CanonicalEventMeta
from poc.k1_poc.events.conversation import (
    DeadLettered,
    IntentArbitrated,
    ResponseFinalDecided,
    UserInputReceived,
)
from poc.k1_poc.events.hitl import HILRequested, HILResolved, TaskResumed, TaskSuspended
from poc.k1_poc.events.mutation import TurnMutationSummary
from poc.k1_poc.events.pool import (
    BackPoolWorkerAcquiredEvent,
    BackPoolWorkerReleasedEvent,
    DependencyFailedEvent,
    TaskDeferredEvent,
    TaskLeasedEvent,
    TaskLeaseExpiredEvent,
    TaskLeaseRenewedEvent,
)
from poc.k1_poc.events.task import (
    TaskCancelled,
    TaskCompleted,
    TaskCreated,
    TaskFailed,
    TaskLeased,
    TaskProgressed,
)
from poc.k1_poc.events.weave import (
    WeaveCandidateArrived,
    WeaveDecisionMade,
    WeaveEmitted,
    WeaveMetricsEvent,
)

# All 16 canonical event types, keyed by event_type string.
EVENT_TYPE_REGISTRY: dict[str, type[CanonicalEventMeta]] = {
    # Conversation (3)
    "conversation.user_input.received": UserInputReceived,
    "conversation.intent.arbitrated": IntentArbitrated,
    "conversation.dead_lettered": DeadLettered,
    # M2 E2.5.4: Response-final decision audit trail
    "conversation.response_final.decided": ResponseFinalDecided,
    # Task lifecycle (6)
    "task.created": TaskCreated,
    "task.leased": TaskLeased,
    "task.progressed": TaskProgressed,
    "task.completed": TaskCompleted,
    "task.failed": TaskFailed,
    "task.cancelled": TaskCancelled,
    # HITL (4)
    "hil.requested": HILRequested,
    "hil.resolved": HILResolved,
    "task.suspended": TaskSuspended,
    "task.resumed": TaskResumed,
    # Weave (3)
    "conversation.weave.candidate": WeaveCandidateArrived,
    "conversation.weave.decided": WeaveDecisionMade,
    "conversation.weave.emitted": WeaveEmitted,
    # Weave metrics (1) -- M8 E8.5.1
    "metrics.weave.session": WeaveMetricsEvent,
    # Mutation audit (1) -- M4 E4.5.4
    "mutation.turn_summary": TurnMutationSummary,
    # BackPool / Lease lifecycle (7) -- M7 E7.5.1, E7.5.4
    "pool.worker.acquired": BackPoolWorkerAcquiredEvent,
    "pool.worker.released": BackPoolWorkerReleasedEvent,
    "pool.task.leased": TaskLeasedEvent,
    "pool.task.lease_expired": TaskLeaseExpiredEvent,
    "pool.task.lease_renewed": TaskLeaseRenewedEvent,
    "pool.task.deferred": TaskDeferredEvent,
    "pool.task.dependency_failed": DependencyFailedEvent,
}


def resolve_event_type(event_type: str) -> type[CanonicalEventMeta] | None:
    """Look up the canonical event class for a given event_type string.

    Args:
        event_type: The canonical event_type string (e.g. "task.completed").

    Returns:
        The canonical event class, or None if not registered.
    """
    return EVENT_TYPE_REGISTRY.get(event_type)


def deserialize_event(payload: dict[str, Any]) -> CanonicalEventMeta | None:
    """Deserialize a payload dict to a typed canonical event.

    Looks up the event_type field in the payload and dispatches to the
    appropriate from_payload() class method.

    Args:
        payload: Dict containing at least an "event_type" field.

    Returns:
        A typed CanonicalEventMeta subclass instance, or None if
        event_type is missing or unrecognized.
    """
    event_type = payload.get("event_type", "")
    cls = EVENT_TYPE_REGISTRY.get(event_type)
    if cls is None:
        return None
    return cls.from_payload(payload)


__all__ = [
    "EVENT_TYPE_REGISTRY",
    "resolve_event_type",
    "deserialize_event",
]
__all__ = [
    "EVENT_TYPE_REGISTRY",
    "resolve_event_type",
    "deserialize_event",
]
