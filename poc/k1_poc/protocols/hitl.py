"""
poc.k1_poc.protocols.hitl -- HITL request/response types and safety band.

V2 Design Ref: Section 9.1 (HITL Closed Cycle)
V2 Design Ref: Section 9.2 (Three HITL Shapes: clarification, approval, selection)
V2 Design Ref: Section 9.3 (Safety Band Escalation Table)
V2 Design Ref: Section 9.5 (Suspension Rules and Limits)
V2 Design Ref: Section 9.10 (HITL Invariants)

Epic 13.1: HILRequest, HILResponse, SafetyBand, escalate_safety_band.

HILRequest is the structured payload emitted by Back when it needs
human input.  Three shapes exist:

    clarification: Missing or ambiguous parameters.
                   Default timeout: 60s.
    approval:      Side-effect actions requiring user consent.
                   Default timeout: 120s.
    selection:     Multiple results, user must choose.
                   Default timeout: 90s.

HILResponse is the structured resolution emitted by Front after the
user answers.  It carries the user's decision and parsed resolution.

SafetyBand controls execution gating:
    GREEN:  Execute directly (no side effects).
    AMBER:  Approval required (side effects present).
    RED:    Execution blocked (financial/medical/legal).

Safety band escalation (V2 Section 9.3):
    GREEN + side_effects -> AMBER (auto-escalate)
    AMBER + any          -> AMBER (no change)
    RED + any            -> RED   (always block)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from poc.k1_poc.config import get_config
from poc.k1_poc.protocols.suspension import MAX_SUSPENSIONS_PER_TASK


class SafetyBand(str, Enum):
    """Execution safety classification for capabilities.

    V2 Design Ref: Section 9.3 (Safety Band Escalation Table)

    GREEN: Safe to execute without approval (no side effects).
    AMBER: Requires user approval before execution (side effects present).
    RED:   Execution blocked entirely. Refer to supervisor.
    """

    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


# HITL timeouts: authoritative values live in config/defaults.yaml
# (protocols.hil_timeouts) in SECONDS.  Use _get_hil_timeouts() to access.
# No module-level fallback dict -- config is the single source of truth.
# (V3 E0.2.1: removed HIL_TIMEOUTS constant, unified to seconds)


def _get_hil_timeouts() -> dict[str, float]:
    """Return HITL timeouts from central config (seconds).

    V3 E0.2.1: Returns float seconds (was int milliseconds).
    """
    return get_config().protocols.hil_timeouts


# Valid HITL types
VALID_HIL_TYPES: frozenset[str] = frozenset({"clarification", "approval", "selection"})


def escalate_safety_band(
    band: SafetyBand,
    has_side_effects: bool = False,
) -> SafetyBand:
    """Apply safety band escalation rules.

    V2 Design Ref: Section 9.3 (Safety Band Escalation Table)

    Escalation logic:
        1. RED -> always RED (never execute)
        2. GREEN + side_effects -> AMBER (auto-escalate)
        3. AMBER -> AMBER (no change)
        4. GREEN + no side_effects -> GREEN (safe)

    Args:
        band: Current safety band from capability contract.
        has_side_effects: Whether the capability has side effects.

    Returns:
        The effective safety band after escalation.
    """
    if band == SafetyBand.RED:
        return SafetyBand.RED
    if has_side_effects:
        return SafetyBand.AMBER
    return band


@dataclass
class HILRequest:
    """Structured HITL request emitted by Back when it needs human input.

    V2 Design Ref: Section 9.1 (HITL Closed Cycle, step 1-2)
    V2 Design Ref: Section 9.2 (Three shapes)
    V2 Design Ref: Section 9.5 (pending_hil persistence)

    The Back LLM calls submit_result(needs_human) which creates this
    request.  The FSM stores it in TaskStateEntry.pending_hil for
    crash recovery.  Front reads it in HITL_RELAY mode.

    Three shapes:
        clarification: question + context (missing params)
        approval:      question + options + side_effects
        selection:     question + options (multiple results)

    Attributes:
        task_id:         The task being suspended.
        hil_type:        One of: clarification, approval, selection.
        question:        The question for the user.
        options:         Structured options (approval/selection).
        context:         Additional context (capability, params_so_far).
        side_effects:    Explicit side effects for approval type.
        safety_band:     Effective safety band after escalation.
        timeout_ms:      Timeout for user response (type-specific default).
        max_rounds:      Max HITL rounds allowed per task (default 2).
        created_at_ns:   Monotonic timestamp when request was created.
    """

    task_id: str
    hil_type: str
    question: str
    options: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    side_effects: list[str] = field(default_factory=list)
    safety_band: SafetyBand = SafetyBand.GREEN
    timeout_ms: int = 0
    max_rounds: int = MAX_SUSPENSIONS_PER_TASK
    created_at_ns: int = field(default_factory=time.monotonic_ns)

    def __post_init__(self) -> None:
        """Validate hil_type and apply default timeout if not set."""
        if self.hil_type not in VALID_HIL_TYPES:
            raise ValueError(
                f"Invalid hil_type '{self.hil_type}'. " f"Must be one of: {sorted(VALID_HIL_TYPES)}"
            )
        if self.timeout_ms <= 0:
            self.timeout_ms = HIL_TIMEOUTS.get(self.hil_type, 60_000)

    @property
    def timeout_seconds(self) -> float:
        """Timeout in seconds."""
        return self.timeout_ms / 1000.0

    def to_payload(self) -> dict[str, Any]:
        """Serialize to bus envelope payload.

        V2 Design Ref: Section 9.5 (pending_hil persistence format)
        """
        return {
            "task_id": self.task_id,
            "hil_type": self.hil_type,
            "question": self.question,
            "options": self.options,
            "context": self.context,
            "side_effects": self.side_effects,
            "safety_band": self.safety_band.value,
            "timeout_ms": self.timeout_ms,
            "max_rounds": self.max_rounds,
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> HILRequest:
        """Deserialize from bus envelope payload."""
        band = data.get("safety_band", "GREEN")
        if isinstance(band, str):
            band = SafetyBand(band)
        return cls(
            task_id=data["task_id"],
            hil_type=data["hil_type"],
            question=data["question"],
            options=data.get("options", []),
            context=data.get("context", {}),
            side_effects=data.get("side_effects", []),
            safety_band=band,
            timeout_ms=data.get("timeout_ms", 0),
            max_rounds=data.get("max_rounds", MAX_SUSPENSIONS_PER_TASK),
        )

    def to_persistence(self) -> dict[str, Any]:
        """Serialize for TaskStateEntry.pending_hil crash recovery.

        V2 Design Ref: Section 9.5 (pending_hil format)
        V2 Design Ref: Section 9.6 (Crash Recovery Protocol)

        Includes suspended_at_ms for timeout checking on recovery.
        """
        payload = self.to_payload()
        payload["suspended_at_ms"] = int(self.created_at_ns / 1_000_000)
        return payload


@dataclass
class HILResponse:
    """Structured HITL response from Front after user answers.

    V2 Design Ref: Section 9.4 (HITL_RESOLVE mode)
    V2 Design Ref: Section 9.2 (Resolution parsing by hil_type)

    Resolution formats by hil_type:
        clarification: {answer: str, resolved_params: {param: value, ...}}
        approval:      {decision: "approve"|"modify"|"cancel",
                        modifications: {param: value, ...}}
        selection:     {selected_option: int, target: str}

    Attributes:
        task_id:        The suspended task.
        decision:       High-level decision (approve/modify/cancel/answered).
        resolution:     Structured resolution payload (type-specific).
        raw_user_text:  Original user text for audit trail.
    """

    task_id: str
    decision: str = "answered"
    resolution: dict[str, Any] = field(default_factory=dict)
    raw_user_text: str = ""

    def to_payload(self) -> dict[str, Any]:
        """Serialize to bus envelope payload."""
        return {
            "task_id": self.task_id,
            "decision": self.decision,
            "resolution": self.resolution,
            "raw_user_text": self.raw_user_text,
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> HILResponse:
        """Deserialize from bus envelope payload."""
        return cls(
            task_id=data["task_id"],
            decision=data.get("decision", "answered"),
            resolution=data.get("resolution", {}),
            raw_user_text=data.get("raw_user_text", ""),
        )
