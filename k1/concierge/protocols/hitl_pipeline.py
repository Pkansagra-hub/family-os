"""
k1.concierge.protocols.hitl_pipeline -- End-to-end HITL pipeline orchestration.

V2 Design Ref: Section 9.2.2 (Approval shape -- side-effect detection, consent, execute)
V2 Design Ref: Section 9.2.3 (Selection shape -- multiple results, user chooses)
V2 Design Ref: Section 9.3 (Safety Band Escalation Table)
V2 Design Ref: Section 9.4 (Front HITL_RELAY / HITL_RESOLVE modes)
V2 Design Ref: Section 9.7 (Complete Event Traces for all 3 flows)
V2 Design Ref: Section 9.8 (Defense-in-Depth FSM Enforcement L2)

Epics 13.4 + 13.5: Approval and Selection flow pipelines.

This module provides end-to-end pipeline helpers that wire together:
    - Safety band detection and escalation
    - Side-effect detection from capability contracts
    - HILCoordinator orchestration
    - Approval modification merge logic
    - Selection resolution to concrete params

These sit between the actors (Back/Front) and the HILCoordinator.
The actors call pipeline functions; the pipelines call HILCoordinator.

INVARIANTS (V2 Section 9.10):
    1. No side-effect capability executes without user approval.
    8. Approval modifications are applied BEFORE execution, not after.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from k1.concierge.protocols.hitl import HILResponse, SafetyBand
from k1.concierge.protocols.hitl_flow import (
    parse_approval_resolution,
    parse_selection_resolution,
)

logger = logging.getLogger(__name__)


# =========================================================================
# Epic 13.4 -- Approval Pipeline
# =========================================================================


def detect_approval_required(
    capability_contract: dict[str, Any],
) -> bool:
    """Detect whether a capability requires approval before execution.

    V2 Design Ref: Section 9.2.2 (Approval trigger)
    V2 Design Ref: Section 9.3 (Safety Band Escalation Table)

    The rule is absolute:
        has_side_effects == true -> approval required
        safety_band == AMBER    -> approval required
        safety_band == RED      -> execution blocked entirely

    Args:
        capability_contract: Capability metadata from Fabric registry.
            Expected keys: has_side_effects, safety_band, name.

    Returns:
        True if user approval is required before execution.
    """
    has_side_effects = capability_contract.get("has_side_effects", False)
    safety_band_str = capability_contract.get("safety_band", "GREEN")

    try:
        band = SafetyBand(safety_band_str)
    except ValueError:
        band = SafetyBand.AMBER  # Unknown -> err on the side of caution

    # RED: always blocked (caller should handle separately)
    if band == SafetyBand.RED:
        return True

    # has_side_effects=true: always requires approval
    if has_side_effects:
        return True

    # AMBER without side_effects: unusual, but approval required
    if band == SafetyBand.AMBER:
        logger.debug(
            "detect_approval_required  capability=%s band=AMBER -> True",
            capability_contract.get("name", "?"),
        )
        return True

    # GREEN without side_effects: safe
    logger.debug(
        "detect_approval_required  capability=%s band=%s side_effects=%s -> False",
        capability_contract.get("name", "?"),
        band.value,
        has_side_effects,
    )
    return False


def apply_approval_modifications(
    original_params: dict[str, Any],
    modifications: dict[str, Any],
) -> dict[str, Any]:
    """Apply user's modifications to task params before resuming Back.

    V2 Design Ref: Section 9.2.2 (Approval resolution shapes)
    V2 Design Ref: Section 9.10, Invariant 8

    Invariant 8: Modifications are applied BEFORE execution, not after.

    Example (V2 Section 9.2.2):
        User: "Go ahead but use the Amex"
        Original: {payment_method: "visa_4242", hotel: "Vineyard Inn"}
        Modifications: {payment_method: "amex"}
        Result: {payment_method: "amex", hotel: "Vineyard Inn"}

    Modifications are applied as a shallow merge. Original params are
    NOT mutated; a new dict is returned.

    Args:
        original_params: The params Back intended to use.
        modifications:   User's requested changes.

    Returns:
        Merged params dict (shallow copy with modifications applied).
    """
    merged = {**original_params, **modifications}
    if modifications:
        logger.info(
            "Applied approval modifications: %s (changed %d param(s))",
            list(modifications.keys()),
            len(modifications),
        )
    return merged


@dataclass
class ApprovalResult:
    """Result of processing an approval response.

    V2 Design Ref: Section 9.2.2 (Approval resolution shapes)

    Captures the user's decision and the merged params ready for
    Back to use when resuming execution.

    Attributes:
        decision:         The user's decision: approve, modify, cancel.
        merged_params:    Params with modifications applied (for approve/modify).
        modifications:    The modifications the user requested (empty for approve/cancel).
        raw_user_text:    Original user text for audit trail.
        should_execute:   Whether Back should invoke_capability.
        should_re_present: Whether to re-present for approval (modify decision).
    """

    decision: str
    merged_params: dict[str, Any]
    modifications: dict[str, Any] = field(default_factory=dict)
    raw_user_text: str = ""
    should_execute: bool = False
    should_re_present: bool = False


def process_approval_response(
    response: HILResponse,
    original_params: dict[str, Any],
) -> ApprovalResult:
    """Process a user's approval response into an actionable result.

    V2 Design Ref: Section 9.2.2 (Approval resolution shapes)

    Decision table:
        approve:            Execute with original (or modified) params.
        approve + mods:     Execute with merged params.
        modify + mods:      Re-present for approval with modified params.
        cancel:             Do NOT execute. Task cancelled.

    Args:
        response:        The HILResponse from the user.
        original_params: The params Back intended to use.

    Returns:
        ApprovalResult with execution directive.
    """
    parsed = parse_approval_resolution(response.resolution)
    decision = parsed.get("decision", "approve")
    modifications = parsed.get("modifications", {})
    merged = apply_approval_modifications(original_params, modifications)

    if decision == "cancel":
        logger.info("Task %s: approval cancelled by user", response.task_id)
        return ApprovalResult(
            decision="cancel",
            merged_params=original_params,
            modifications={},
            raw_user_text=response.raw_user_text,
            should_execute=False,
            should_re_present=False,
        )

    if decision == "modify":
        logger.info(
            "Task %s: approval modified, re-present required [mods=%s]",
            response.task_id,
            list(modifications.keys()),
        )
        return ApprovalResult(
            decision="modify",
            merged_params=merged,
            modifications=modifications,
            raw_user_text=response.raw_user_text,
            should_execute=False,
            should_re_present=True,
        )

    # approve (with or without modifications)
    if modifications:
        logger.info(
            "Task %s: approved with modifications [mods=%s]",
            response.task_id,
            list(modifications.keys()),
        )
    else:
        logger.info("Task %s: approved without modifications", response.task_id)

    return ApprovalResult(
        decision="approve",
        merged_params=merged,
        modifications=modifications,
        raw_user_text=response.raw_user_text,
        should_execute=True,
        should_re_present=False,
    )


# =========================================================================
# Epic 13.5 -- Selection Pipeline
# =========================================================================


@dataclass
class SelectionResult:
    """Result of processing a selection response.

    V2 Design Ref: Section 9.2.3 (Selection resolution)

    Captures the user's selection and the concrete params for
    Back to use when resuming execution.

    Attributes:
        selected_option:   The option index the user chose.
        selected_options:  Multiple selected options (multi-select).
        target:            Resolved label/name of the selected option.
        selected_data:     Full data dict of the selected option.
        raw_user_text:     Original user text for audit trail.
    """

    selected_option: int | None = None
    selected_options: list[int] | None = None
    target: str = ""
    selected_data: dict[str, Any] = field(default_factory=dict)
    raw_user_text: str = ""

    @property
    def is_multi_select(self) -> bool:
        """Whether the user selected multiple options."""
        return self.selected_options is not None and len(self.selected_options) > 1

    @property
    def is_valid(self) -> bool:
        """Whether a selection was actually made."""
        return self.selected_option is not None or bool(self.selected_options)


def resolve_selection_to_params(
    response: HILResponse,
    available_options: list[dict[str, Any]],
    param_name: str = "target",
) -> SelectionResult:
    """Resolve a selection response into concrete params for Back.

    V2 Design Ref: Section 9.2.3 (Selection resolution)
    V2 Design Ref: Section 9.7, Flow 3 (Selection event trace)

    Maps the user's selection (option index or text) back to the
    original result data that Back returned from discovery.

    Example:
        User: "The one in Sonoma"
        Front resolves: {selected_option: 2}
        Available options: [{id:1, label:"Napa"}, {id:2, label:"Sonoma"}]
        Result: selected_data = {id:2, label:"Sonoma"}, target="Sonoma"

    Args:
        response:          The HILResponse from the user.
        available_options:  The original options presented (from HILRequest).
        param_name:         The param key to populate with the selection.

    Returns:
        SelectionResult with resolved data.
    """
    parsed = parse_selection_resolution(response.resolution, available_options)

    # Multi-select case
    if "selected_options" in parsed:
        indices = parsed["selected_options"]
        selected_data_list = []
        for idx in indices:
            for opt in available_options:
                if opt.get("id") == idx:
                    selected_data_list.append(opt)
                    break
        return SelectionResult(
            selected_options=indices,
            target=", ".join(
                opt.get("label", opt.get("name", f"option-{opt.get('id')}"))
                for opt in selected_data_list
            ),
            selected_data={
                param_name: selected_data_list,
                "selected_count": len(selected_data_list),
            },
            raw_user_text=response.raw_user_text,
        )

    # Single-select case
    selected_id = parsed.get("selected_option")
    target = parsed.get("target", "")
    selected_data: dict[str, Any] = {}

    if selected_id is not None:
        for opt in available_options:
            if opt.get("id") == selected_id:
                selected_data = dict(opt)
                if not target:
                    target = opt.get("label", opt.get("name", ""))
                break

    if selected_data:
        logger.info(
            "Selection resolved: option %d -> %s",
            selected_id,
            target,
        )
    else:
        logger.warning(
            "Selection option %s not found in available options",
            selected_id,
        )

    return SelectionResult(
        selected_option=selected_id,
        target=target,
        selected_data=selected_data,
        raw_user_text=response.raw_user_text,
    )


def build_resume_params_from_selection(
    selection: SelectionResult,
    original_params: dict[str, Any],
    param_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build resume params by merging selection into original params.

    V2 Design Ref: Section 9.7, Flow 3 (Back resumes with selection)

    Example:
        original_params: {intent: "book_hotel", location: "Napa Valley"}
        selection.selected_data: {id: 2, label: "Vineyard Inn, Sonoma",
                                   price: 185}
        param_mapping: {"label": "hotel", "price": "price_per_night"}
        Result: {intent: "book_hotel", location: "Napa Valley",
                 hotel: "Vineyard Inn, Sonoma", price_per_night: 185}

    Args:
        selection:       The resolved SelectionResult.
        original_params: Back's original params (pre-selection).
        param_mapping:   Maps selected_data keys to param keys.
                        If None, selected_data is merged directly.

    Returns:
        Merged params dict for Back resume.
    """
    merged = dict(original_params)

    if param_mapping:
        for source_key, target_key in param_mapping.items():
            if source_key in selection.selected_data:
                merged[target_key] = selection.selected_data[source_key]
    else:
        # Direct merge (exclude internal "id" key)
        for k, v in selection.selected_data.items():
            if k != "id":
                merged[k] = v

    # Always set target if available
    if selection.target:
        merged["_selected_target"] = selection.target

    return merged
