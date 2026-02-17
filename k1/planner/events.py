"""Planner event topic constants and payload schemas [F06].

Central registry of all event topic strings and event payload dataclasses.
Prevents topic string duplication across services.

Design decisions
----------------
- Topic strings are module-level constants (no enum -- plain strings for
  direct use in IEventPort.publish() calls).
- Payload dataclasses are frozen=True (immutable after creation).
- CommittedPlan is the payload for TOPIC_PLAN_READY -- no wrapper needed.
- Response payloads (HILClarificationResponse, HILApprovalResponse) are
  owned by Concierge, not defined here.

Import graph (Layer 0 -- no internal deps)
------------------------------------------
k1.planner.events
  -> stdlib only (dataclasses, typing)

NEVER import from any service, port, or adapter module.

References
----------
- planner.md Section 26 (Delta Bus & Event Bus)
- planner.md Section 28 (Complete Event Catalog)
- planner.md Section 30.5.1 F06
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Topic constants (Section 28 -- Complete Event Catalog)
# ---------------------------------------------------------------------------

# Published by Planner
TOPIC_PLAN_READY = "k1.planner.plan.ready.v1"
TOPIC_PLAN_FAILED = "k1.planner.plan.failed.v1"
TOPIC_PLAN_CANCELLED = "k1.planner.plan.cancelled.v1"
TOPIC_MICRO_REPLAN_READY = "k1.planner.micro_replan.ready.v1"
TOPIC_DELTA = "k1.planner.delta.v1"
TOPIC_HIL_CLARIFICATION = "k1.hil.clarification.v1"
TOPIC_HIL_APPROVAL_REQ = "k1.hil.approval_request.v1"

# Subscribed by Planner
TOPIC_PLAN_REQUEST = "k1.planner.plan.request.v1"
TOPIC_PLAN_CANCEL = "k1.planner.plan.cancel.v1"
TOPIC_HIL_CLARIFICATION_RESP = "k1.hil.clarification_response.v1"
TOPIC_HIL_APPROVAL_RESP = "k1.hil.approval_response.v1"


# ---------------------------------------------------------------------------
# Event payload dataclasses (Section 28)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanFailedPayload:
    """Payload for TOPIC_PLAN_FAILED event.

    Emitted by PipelineController when a plan fails at any stage
    (unrecoverable after retry).
    """

    request_id: str
    stage: str
    error_code: str
    error_message: str
    tokens_used: int
    duration_ms: int
    trace_id: str
    partial_state: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("PlanFailedPayload.request_id must be non-empty")
        if not self.stage:
            raise ValueError("PlanFailedPayload.stage must be non-empty")
        if not self.error_code:
            raise ValueError("PlanFailedPayload.error_code must be non-empty")
        if not self.trace_id:
            raise ValueError("PlanFailedPayload.trace_id must be non-empty")


@dataclass(frozen=True)
class PlanCancelledPayload:
    """Payload for TOPIC_PLAN_CANCELLED event.

    Emitted by PipelineController when a plan is cancelled by Orchestrator
    via send_cancel().
    """

    request_id: str
    reason: str
    stage: str
    trace_id: str

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("PlanCancelledPayload.request_id must be non-empty")
        if not self.stage:
            raise ValueError("PlanCancelledPayload.stage must be non-empty")
        if not self.trace_id:
            raise ValueError("PlanCancelledPayload.trace_id must be non-empty")


@dataclass(frozen=True)
class HILClarificationPayload:
    """Payload for TOPIC_HIL_CLARIFICATION event (Section 12.2).

    Published by HILCoordinator during SKETCH when ambiguity is detected.
    Concierge subscribes and presents the question to the user.

    Response payloads are owned by Concierge (not defined here).
    """

    request_id: str
    question: str
    context: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("HILClarificationPayload.request_id must be non-empty")
        if not self.question:
            raise ValueError("HILClarificationPayload.question must be non-empty")
        if not self.trace_id:
            raise ValueError("HILClarificationPayload.trace_id must be non-empty")


@dataclass(frozen=True)
class HILApprovalRequestPayload:
    """Payload for TOPIC_HIL_APPROVAL_REQ event (Section 12.3).

    Published by HILCoordinator during VALIDATE for high-risk plans
    (steps with has_side_effects=true and safety_band_min above GREEN).

    Response payloads are owned by Concierge (not defined here).
    """

    request_id: str
    summary: str
    options: List[str] = field(default_factory=list)
    side_effects: List[str] = field(default_factory=list)
    safety_assessment: str = ""

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("HILApprovalRequestPayload.request_id must be non-empty")
        if not self.summary:
            raise ValueError("HILApprovalRequestPayload.summary must be non-empty")
        if not self.options:
            raise ValueError("HILApprovalRequestPayload.options must be non-empty")


__all__ = [
    # Topic constants -- published
    "TOPIC_PLAN_READY",
    "TOPIC_PLAN_FAILED",
    "TOPIC_PLAN_CANCELLED",
    "TOPIC_MICRO_REPLAN_READY",
    "TOPIC_DELTA",
    "TOPIC_HIL_CLARIFICATION",
    "TOPIC_HIL_APPROVAL_REQ",
    # Topic constants -- subscribed
    "TOPIC_PLAN_REQUEST",
    "TOPIC_PLAN_CANCEL",
    "TOPIC_HIL_CLARIFICATION_RESP",
    "TOPIC_HIL_APPROVAL_RESP",
    # Payload dataclasses
    "PlanFailedPayload",
    "PlanCancelledPayload",
    "HILClarificationPayload",
    "HILApprovalRequestPayload",
]
