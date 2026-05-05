"""Policy request / verdict dataclasses + canonical decision matrix.

Implements the freshness × risk matrix from the whiteboard
(``docs/whiteboard/whiteboard_k1_user_selfmodel_and_tools.md`` §"Mapping
risk class × freshness state → default verdict").

| Risk \\ State        | fresh | stale                  | offline_local_only       | conflict_pending |
| ------------------- | ----- | ---------------------- | ------------------------ | ---------------- |
| low                 | ALLOW | ALLOW (capsule stale)  | ALLOW (queue writeback)  | ALLOW            |
| medium              | ALLOW | REQUIRE_CONFIRMATION   | REQUIRE_CONFIRMATION + Q | DENY (affected)  |
| high                | RC    | DEFER_OFFLINE          | DEFER_OFFLINE            | DENY             |
| safety_sensitive    | RC    | DEFER_OFFLINE (E:ALLOW)| DEFER_OFFLINE (E only)   | DENY             |

(``E`` = emergency override produces ``ALLOW`` with ``audit_required=True``.)
The constitution may *tighten* any cell but never loosen
``safety_sensitive`` cells.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Mapping

__all__ = [
    "FreshnessState",
    "PolicyDecision",
    "RiskClass",
    "ReasonCode",
    "PolicyRequest",
    "PolicyVerdict",
    "DEFAULT_DECISION_MATRIX",
    "decision_for",
]


class FreshnessState(str, Enum):
    """Projection freshness as seen by the gate."""

    FRESH = "fresh"
    STALE = "stale"
    OFFLINE_LOCAL_ONLY = "offline_local_only"
    CONFLICT_PENDING = "conflict_pending"


class PolicyDecision(str, Enum):
    """The five verdicts the gate can return."""

    ALLOW = "ALLOW"
    ALLOW_WITH_CAUTION = "ALLOW_WITH_CAUTION"  # M14.E1.I3
    DENY = "DENY"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    REQUIRE_IDENTITY = "REQUIRE_IDENTITY"
    DEFER_OFFLINE = "DEFER_OFFLINE"


class RiskClass(str, Enum):
    """Tool risk classification (declared per tool; default ``LOW``)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SAFETY_SENSITIVE = "safety_sensitive"


class ReasonCode(str, Enum):
    """Stable reason codes attached to verdicts."""

    OK = "ok"
    CAPABILITY_NOT_GRANTED = "capability_not_granted"
    NEEDS_CONFIRMATION = "needs_confirmation"
    IDENTITY_TIER_TOO_LOW = "identity_tier_too_low"
    PROJECTION_STALE = "projection_stale"
    OFFLINE_ONLY = "offline_only"
    BLACK_BAND = "black_band"
    CONSTITUTION_CONFLICT = "constitution_conflict"
    EMERGENCY_OVERRIDE = "emergency_override"
    UNKNOWN_TOOL = "unknown_tool"
    SOFT_WARN = "soft_warn"  # M14.E1.I3


@dataclass(frozen=True)
class PolicyRequest:
    """Inputs the policy evaluator needs to issue a verdict."""

    actor_id: str
    tool_name: str
    risk_class: RiskClass = RiskClass.LOW
    arguments: dict[str, object] = field(default_factory=dict)
    trace_id: str = ""
    emergency: bool = False  # set by caller for safety_sensitive overrides
    affected_member_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, object]:
        d = asdict(self)
        d["risk_class"] = self.risk_class.value
        d["affected_member_ids"] = list(self.affected_member_ids)
        return d


@dataclass(frozen=True)
class PolicyVerdict:
    """Result of evaluating a ``PolicyRequest`` against a SituationFrame."""

    decision: PolicyDecision
    reason: ReasonCode = ReasonCode.OK
    detail: str = ""
    requires_tier: int = 0  # only meaningful when decision == REQUIRE_IDENTITY
    pending_id: str = ""  # populated by the gate when escalation issued
    audit_required: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            "decision": self.decision.value,
            "reason": self.reason.value,
            "detail": self.detail,
            "requires_tier": self.requires_tier,
            "pending_id": self.pending_id,
            "audit_required": self.audit_required,
        }


# ---------------------------------------------------------------------
# Canonical matrix
# ---------------------------------------------------------------------
DEFAULT_DECISION_MATRIX: Mapping[
    RiskClass, Mapping[FreshnessState, tuple[PolicyDecision, ReasonCode]]
] = {
    RiskClass.LOW: {
        FreshnessState.FRESH: (PolicyDecision.ALLOW, ReasonCode.OK),
        FreshnessState.STALE: (PolicyDecision.ALLOW, ReasonCode.PROJECTION_STALE),
        FreshnessState.OFFLINE_LOCAL_ONLY: (PolicyDecision.ALLOW, ReasonCode.OFFLINE_ONLY),
        FreshnessState.CONFLICT_PENDING: (PolicyDecision.ALLOW, ReasonCode.CONSTITUTION_CONFLICT),
    },
    RiskClass.MEDIUM: {
        FreshnessState.FRESH: (PolicyDecision.ALLOW, ReasonCode.OK),
        FreshnessState.STALE: (PolicyDecision.REQUIRE_CONFIRMATION, ReasonCode.PROJECTION_STALE),
        FreshnessState.OFFLINE_LOCAL_ONLY: (
            PolicyDecision.REQUIRE_CONFIRMATION,
            ReasonCode.OFFLINE_ONLY,
        ),
        FreshnessState.CONFLICT_PENDING: (PolicyDecision.DENY, ReasonCode.CONSTITUTION_CONFLICT),
    },
    RiskClass.HIGH: {
        FreshnessState.FRESH: (PolicyDecision.REQUIRE_CONFIRMATION, ReasonCode.NEEDS_CONFIRMATION),
        FreshnessState.STALE: (PolicyDecision.DEFER_OFFLINE, ReasonCode.PROJECTION_STALE),
        FreshnessState.OFFLINE_LOCAL_ONLY: (PolicyDecision.DEFER_OFFLINE, ReasonCode.OFFLINE_ONLY),
        FreshnessState.CONFLICT_PENDING: (PolicyDecision.DENY, ReasonCode.CONSTITUTION_CONFLICT),
    },
    RiskClass.SAFETY_SENSITIVE: {
        FreshnessState.FRESH: (PolicyDecision.REQUIRE_CONFIRMATION, ReasonCode.NEEDS_CONFIRMATION),
        FreshnessState.STALE: (PolicyDecision.DEFER_OFFLINE, ReasonCode.PROJECTION_STALE),
        FreshnessState.OFFLINE_LOCAL_ONLY: (PolicyDecision.DEFER_OFFLINE, ReasonCode.OFFLINE_ONLY),
        FreshnessState.CONFLICT_PENDING: (PolicyDecision.DENY, ReasonCode.CONSTITUTION_CONFLICT),
    },
}


def decision_for(risk: RiskClass, state: FreshnessState) -> tuple[PolicyDecision, ReasonCode]:
    """Look up the matrix cell. Defaults to most-restrictive on bad input."""
    row = DEFAULT_DECISION_MATRIX.get(risk)
    if row is None:
        return (PolicyDecision.DENY, ReasonCode.UNKNOWN_TOOL)
    cell = row.get(state)
    if cell is None:
        return (PolicyDecision.DENY, ReasonCode.PROJECTION_STALE)
    return cell
