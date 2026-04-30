"""k1.hil -- Unified Human-in-the-Loop service (E1).

This package is the SINGLE source of truth for HIL across:
  - planner SKETCH (clarification) and VALIDATE (approval)
  - concierge Back -> FSM (needs_human)
  - orchestrator ConstraintResolver (override)
  - fabric CapabilityFabric.execute (capability_gate)

E1 stands up the module skeleton WITHOUT wiring any production caller.
Wiring lands in E3 (fabric), E4 (concierge), E5 (planner), E6
(orchestrator), and E7 (kernel bootstrap).
"""

from __future__ import annotations

from k1.hil.config import HILConfig
from k1.hil.safety import SafetyBandPolicy, SafetyDecision
from k1.hil.service import HumanInTheLoopService
from k1.hil.topics import TOPIC_HIL_AUDIT, TOPIC_HIL_REQUEST, TOPIC_HIL_RESPONSE
from k1.hil.types import (
    ApprovalRequest,
    ApprovalResponse,
    CapabilityContractView,
    CapabilityGateRequest,
    ClarificationRequest,
    ClarificationResponse,
    GateDecision,
    GateOutcome,
    HILBlockedEvent,
    HILEnvelope,
    HILKind,
    HILRequestedEvent,
    HILResolvedEvent,
    HILResponseEnvelope,
    HILTimedOutEvent,
    NeedsHumanRequest,
    NeedsHumanResponse,
    OverrideRequest,
    OverrideResponse,
)

__all__ = [
    # config / policy
    "HILConfig",
    "SafetyBandPolicy",
    "SafetyDecision",
    # service
    "HumanInTheLoopService",
    # topics
    "TOPIC_HIL_AUDIT",
    "TOPIC_HIL_REQUEST",
    "TOPIC_HIL_RESPONSE",
    # discriminator
    "HILKind",
    # envelopes
    "HILEnvelope",
    "HILResponseEnvelope",
    # per-kind requests/responses
    "ClarificationRequest",
    "ClarificationResponse",
    "ApprovalRequest",
    "ApprovalResponse",
    "NeedsHumanRequest",
    "NeedsHumanResponse",
    "OverrideRequest",
    "OverrideResponse",
    "CapabilityGateRequest",
    "CapabilityContractView",
    "GateDecision",
    "GateOutcome",
    # ledger events
    "HILRequestedEvent",
    "HILResolvedEvent",
    "HILTimedOutEvent",
    "HILBlockedEvent",
]
