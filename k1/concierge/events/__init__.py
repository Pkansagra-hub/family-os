"""
k1.concierge.events -- V3 canonical event schemas.

M1 E1.1: Defines the 16 canonical event types used across the K1 POC.
Every event extends CanonicalEventMeta with domain-specific fields.

Submodules:
    base         -- CanonicalEventMeta and validation utilities
    conversation -- UserInputReceived, IntentArbitrated, DeadLettered
    task         -- TaskCreated, TaskLeased, TaskProgressed, TaskCompleted, TaskFailed, TaskCancelled
    hitl         -- HILRequested, HILResolved, TaskSuspended, TaskResumed
    weave        -- WeaveCandidateArrived, WeaveDecisionMade, WeaveEmitted
    registry     -- event_type -> class mapping for deserialization
    validator    -- runtime schema validation and causation chain checks
"""

from k1.concierge.events.base import CanonicalEventMeta, validate_canonical_metadata  # noqa: F401
from k1.concierge.events.validator import (  # noqa: F401
    EVENT_SCHEMA_REGISTRY,
    validate_event,
    validate_event_chain,
)

__all__ = [
    "CanonicalEventMeta",
    "validate_canonical_metadata",
    "EVENT_SCHEMA_REGISTRY",
    "validate_event",
    "validate_event_chain",
]
