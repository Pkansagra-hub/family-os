"""
poc.k1_poc.protocols.hitl_flow -- HITL flow helpers for clarification,
approval, and selection patterns.

V2 Design Ref: Section 9.2 (Three HITL Shapes)
V2 Design Ref: Section 9.4 (Front LLM Behavior -- HITL_RELAY / HITL_RESOLVE)
V2 Design Ref: Section 9.7 (Complete Event Traces for all 3 flows)

Epic 13.3: Clarification flow helpers and HITL flow utilities.

This module provides:

    HILFlowType:           Enum matching the three HITL shapes.
    ClarificationContext:  Structured missing-param context for Back.
    ApprovalContext:       Structured side-effect context for Back.
    SelectionContext:      Structured multi-result context for Back.
    build_hitl_request:    Factory function to build HILRequest from flow context.
    parse_hitl_resolution: Parse user's natural language into structured resolution.

These are the protocol-layer helpers that sit between:
    - Back's submit_result(needs_human) call (Section 9.2)
    - HILCoordinator's handle_needs_human() (Section 9.1)
    - Front's HITL_RELAY/HITL_RESOLVE modes (Section 9.4)

The actual LLM prompting and actor-level handling lives in M06/M07 (actors).
This module handles the structured data transformations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from poc.k1_poc.protocols.hitl import HILRequest, SafetyBand, escalate_safety_band


class HILFlowType(str, Enum):
    """The three HITL flow shapes.

    V2 Design Ref: Section 9.2 (Three HITL Shapes)

    CLARIFICATION: Missing or ambiguous parameters (Section 9.2.1).
    APPROVAL:      Side-effect actions requiring consent (Section 9.2.2).
    SELECTION:     Multiple results requiring user choice (Section 9.2.3).
    """

    CLARIFICATION = "clarification"
    APPROVAL = "approval"
    SELECTION = "selection"


@dataclass
class ClarificationContext:
    """Structured context for a clarification HITL request.

    V2 Design Ref: Section 9.2.1 (Clarification shape)

    Built when Back detects missing required parameters that cannot
    be inferred from reference_context or beliefs_summary.

    Attributes:
        capability:      The capability being invoked.
        missing_params:  List of missing required parameter names.
        available_params: Parameters already resolved.
        attempted_sources: Where Back looked for the params.
    """

    capability: str
    missing_params: list[str]
    available_params: dict[str, Any] = field(default_factory=dict)
    attempted_sources: list[str] = field(default_factory=list)

    def to_context(self) -> dict[str, Any]:
        """Convert to HILRequest.context dict."""
        return {
            "capability": self.capability,
            "missing_params": self.missing_params,
            "available_params": self.available_params,
            "attempted_sources": self.attempted_sources,
        }

    def build_question(self) -> str:
        """Build a structured question from missing params.

        Returns a question string that Front will translate to
        natural language via HITL_RELAY mode.
        """
        if len(self.missing_params) == 1:
            return f"What {self.missing_params[0]} should I use?"
        params = ", ".join(self.missing_params)
        return f"I need the following to proceed: {params}"


@dataclass
class ApprovalContext:
    """Structured context for an approval HITL request.

    V2 Design Ref: Section 9.2.2 (Approval shape)

    Built when Back is about to execute a capability with
    has_side_effects=true.

    Attributes:
        capability:      The capability requesting approval.
        action_summary:  Human-readable summary of what will happen.
        side_effects:    Explicit list of consequences.
        params:          Parameters that will be used.
        safety_band:     Safety band from capability contract.
    """

    capability: str
    action_summary: str
    side_effects: list[str]
    params: dict[str, Any] = field(default_factory=dict)
    safety_band: SafetyBand = SafetyBand.AMBER

    def to_context(self) -> dict[str, Any]:
        """Convert to HILRequest.context dict."""
        return {
            "capability": self.capability,
            "action_summary": self.action_summary,
            "params": self.params,
        }

    @property
    def default_options(self) -> list[dict[str, Any]]:
        """Standard approval options: approve, modify, cancel."""
        return [
            {"label": "approve", "description": "Proceed with action"},
            {"label": "modify", "description": "Change parameters first"},
            {"label": "cancel", "description": "Cancel the action"},
        ]


@dataclass
class SelectionContext:
    """Structured context for a selection HITL request.

    V2 Design Ref: Section 9.2.3 (Selection shape)

    Built when Back's discovery returned multiple results that
    require user preference.

    Attributes:
        capability:      The discovery capability that returned results.
        results:         The result set to choose from.
        selection_reason: Why Back cannot pick (subjective, preference-driven).
        findings_so_far: Preserved for resume (Back skips re-search).
    """

    capability: str
    results: list[dict[str, Any]]
    selection_reason: str = "Multiple matches found"
    findings_so_far: list[dict[str, Any]] = field(default_factory=list)

    def to_context(self) -> dict[str, Any]:
        """Convert to HILRequest.context dict."""
        return {
            "capability": self.capability,
            "selection_reason": self.selection_reason,
            "result_count": len(self.results),
        }

    def to_options(self) -> list[dict[str, Any]]:
        """Convert results to HILRequest.options format."""
        options: list[dict[str, Any]] = []
        for i, result in enumerate(self.results, start=1):
            option: dict[str, Any] = {"id": i}
            option.update(result)
            options.append(option)
        return options


# =========================================================================
# Factory: build HILRequest from flow context
# =========================================================================


def build_clarification_request(
    task_id: str,
    context: ClarificationContext,
    question: str | None = None,
    safety_band: SafetyBand = SafetyBand.GREEN,
) -> HILRequest:
    """Build an HILRequest for a clarification flow.

    V2 Design Ref: Section 9.2.1

    Args:
        task_id:      The task being suspended.
        context:      ClarificationContext with missing params.
        question:     Custom question (defaults to auto-generated).
        safety_band:  Safety band from capability contract.

    Returns:
        HILRequest with hil_type="clarification".
    """
    return HILRequest(
        task_id=task_id,
        hil_type="clarification",
        question=question or context.build_question(),
        context=context.to_context(),
        safety_band=safety_band,
    )


def build_approval_request(
    task_id: str,
    context: ApprovalContext,
    question: str | None = None,
) -> HILRequest:
    """Build an HILRequest for an approval flow.

    V2 Design Ref: Section 9.2.2

    Safety band is always at least AMBER for approval (auto-escalated).

    Args:
        task_id:  The task being suspended.
        context:  ApprovalContext with side effects.
        question: Custom question (defaults to action_summary).

    Returns:
        HILRequest with hil_type="approval".
    """
    effective_band = escalate_safety_band(context.safety_band, has_side_effects=True)
    return HILRequest(
        task_id=task_id,
        hil_type="approval",
        question=question or context.action_summary,
        options=context.default_options,
        context=context.to_context(),
        side_effects=context.side_effects,
        safety_band=effective_band,
    )


def build_selection_request(
    task_id: str,
    context: SelectionContext,
    question: str | None = None,
    safety_band: SafetyBand = SafetyBand.GREEN,
) -> HILRequest:
    """Build an HILRequest for a selection flow.

    V2 Design Ref: Section 9.2.3

    Args:
        task_id:      The task being suspended.
        context:      SelectionContext with results.
        question:     Custom question (defaults to selection_reason).
        safety_band:  Safety band from capability contract.

    Returns:
        HILRequest with hil_type="selection".
    """
    return HILRequest(
        task_id=task_id,
        hil_type="selection",
        question=question or context.selection_reason,
        options=context.to_options(),
        context=context.to_context(),
        safety_band=safety_band,
    )


# =========================================================================
# Resolution parsers (structured output from Front HITL_RESOLVE)
# =========================================================================


def parse_clarification_resolution(
    raw_resolution: dict[str, Any],
) -> dict[str, Any]:
    """Parse a clarification resolution into resolved_params.

    V2 Design Ref: Section 9.4 (HITL_RESOLVE resolution parsing)

    Input examples:
        {"check_in_date": "2026-06-15", "nights": 2}
        {"answer": "June 15th for 2 nights", "resolved_params": {...}}

    Returns:
        Normalized resolution with "resolved_params" key.
    """
    if "resolved_params" in raw_resolution:
        return raw_resolution
    # The entire dict IS the resolved params
    return {
        "answer": raw_resolution.get("answer", ""),
        "resolved_params": {k: v for k, v in raw_resolution.items() if k != "answer"},
    }


def parse_approval_resolution(
    raw_resolution: dict[str, Any],
) -> dict[str, Any]:
    """Parse an approval resolution into decision + modifications.

    V2 Design Ref: Section 9.2.2 (Approval resolution shapes)
    V2 Design Ref: Section 9.4 (HITL_RESOLVE resolution parsing)

    Input examples:
        {"decision": "approve"}
        {"decision": "approve", "modifications": {"payment_method": "amex"}}
        {"decision": "cancel"}
        {"decision": "modify", "modifications": {"nights": 3}}

    Returns:
        Normalized resolution with "decision" and optional "modifications".
    """
    decision = raw_resolution.get("decision", "approve")
    result: dict[str, Any] = {"decision": decision}
    if "modifications" in raw_resolution:
        result["modifications"] = raw_resolution["modifications"]
    return result


def parse_selection_resolution(
    raw_resolution: dict[str, Any],
    available_options: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse a selection resolution into selected_option.

    V2 Design Ref: Section 9.2.3 (Selection resolution)
    V2 Design Ref: Section 9.4 (HITL_RESOLVE resolution parsing)

    Input examples:
        {"selected_option": 2, "target": "Vineyard Inn, Sonoma"}
        {"selected_options": [1, 2]}

    Returns:
        Normalized resolution with "selected_option" or "selected_options".
    """
    result: dict[str, Any] = {}

    if "selected_option" in raw_resolution:
        result["selected_option"] = raw_resolution["selected_option"]
        if "target" in raw_resolution:
            result["target"] = raw_resolution["target"]
        # Resolve target from options if available
        elif available_options:
            idx = raw_resolution["selected_option"]
            for opt in available_options:
                if opt.get("id") == idx:
                    result["target"] = opt.get("label", opt.get("name", ""))
                    break

    elif "selected_options" in raw_resolution:
        result["selected_options"] = raw_resolution["selected_options"]

    return result
