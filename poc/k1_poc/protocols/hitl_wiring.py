"""
poc.k1_poc.protocols.hitl_wiring -- Cross-layer HITL wiring helpers.

V2 Design Ref: Section 9.1 (HITL Closed Cycle -- steps 7-8, resume)
V2 Design Ref: Section 9.4 (Front HITL_RELAY / HITL_RESOLVE modes)
V2 Design Ref: Section 9.7 (Complete Event Traces, resume context)
V2 Design Ref: Section 8.9 (Task Resume Payload)
V2 Design Ref: Section 6.1 (Prompt Mode Config: tools, iterations, SS reads)

Epics 13.7 + 13.8 + 13.9: Cross-layer wiring between prompt, FSM, and
protocol layers for HITL flows.

This module provides:

    ResumeContext:           Structured context for Back resume after HITL
    build_resume_context:    Assemble resume context from response + state
    HILModeConfig:           Complete config snapshot for a HITL mode
    get_hitl_relay_config:   Full HITL_RELAY mode configuration
    get_hitl_resolve_config: Full HITL_RESOLVE mode configuration
    validate_hitl_wiring:    Cross-layer consistency checks

Epic 13.8.3 -- Back Resume from Saved ReAct History:
    When Back receives task.resume.v1, it needs structured context to
    continue from where it left off.  build_resume_context() assembles
    this from the HILResponse, TaskStateEntry, and saved ReAct history.

    Resume instruction (V2 Section 8.9):
        "You previously suspended this task for {hil_type}. The user
        has provided their answer. Resume from where you left off.
        Do NOT re-execute tools that already succeeded."

INVARIANTS (V2 Section 9.10):
    2. Every HITL shape (clarification/approval/selection) follows the
       same closed cycle.
    7. ReAct history is preserved across suspension for zero-waste resume.
    9. No heuristic flags (anti-spin, force_text_only) in HITL flows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from poc.k1_poc.prompt.builder import SS_READ_CONFIGS, SSReadConfig
from poc.k1_poc.prompt.mode import (
    CRISIS_ITERATIONS_TABLE,
    MAX_ITERATIONS_TABLE,
    TOOL_ALLOWLIST,
    PromptMode,
)
from poc.k1_poc.prompt.sections import ANTI_PATTERN_KEYS, MODE_EXAMPLES, MODE_SECTIONS

logger = logging.getLogger(__name__)

# =========================================================================
# Resume context type strings (V2 Section 8.9)
# =========================================================================

RESUME_INSTRUCTIONS: dict[str, str] = {
    "clarification": (
        "You previously suspended this task because a required parameter "
        "was missing. The user has provided the missing information in the "
        "resolution field. Resume from where you left off. Do NOT re-execute "
        "tools that already succeeded. Use findings_so_far as your starting state."
    ),
    "approval": (
        "You previously suspended this task for user approval. The user has "
        "responded (approved, modified, or cancelled). "
        "If approved: execute invoke_capability with merged_params. "
        "If modified: use the updated params. "
        "If cancelled: call submit_result(complete) with cancelled status. "
        "IMPORTANT: Do NOT call discover_capabilities again -- the capability "
        "was already found before suspension (check findings_so_far for the "
        "capability name). Do NOT re-execute any tool that already succeeded. "
        "Resume from where you left off."
    ),
    "selection": (
        "You previously suspended this task because multiple results were found "
        "and the user needed to choose. The user has made their selection. "
        "Resume with the selected option. Do NOT re-execute the discovery search. "
        "Do NOT call discover_capabilities again."
    ),
}


@dataclass
class ResumeContext:
    """Structured context for Back resume after HITL resolution.

    V2 Design Ref: Section 8.9 (Task Resume Payload)
    V2 Design Ref: Section 9.7 (Resume context assembly)

    When Back receives task.resume.v1, it uses this context to continue
    from the exact point where it suspended. The ReAct message history
    is replayed so Back does not repeat work.

    Attributes:
        task_id:               The task being resumed.
        hil_type:              The type of HITL that was resolved.
        original_task:         Original dispatch spec from FSMTurnState.
        findings_so_far:       ReAct message history before suspension.
        tool_history:          Subset of findings: only tool call entries.
        last_iteration:        Iteration count where the loop suspended.
        resolution:            User's structured answer.
        resume_instruction:    Natural language instruction for Back.
        remaining_budget:      Iterations remaining in the ReAct budget.
        merged_params:         Params with user modifications applied
                              (approval/selection flows only).
    """

    task_id: str
    hil_type: str = "clarification"
    original_task: dict[str, Any] = field(default_factory=dict)
    findings_so_far: list[dict[str, Any]] = field(default_factory=list)
    tool_history: list[dict[str, Any]] = field(default_factory=list)
    last_iteration: int = 0
    resolution: dict[str, Any] = field(default_factory=dict)
    resume_instruction: str = ""
    remaining_budget: int = 0
    merged_params: dict[str, Any] = field(default_factory=dict)

    @property
    def has_findings(self) -> bool:
        """Whether any prior findings exist for resume."""
        return len(self.findings_so_far) > 0

    @property
    def tool_count(self) -> int:
        """Number of tools already executed before suspension."""
        return len(self.tool_history)

    def to_back_context(self) -> dict[str, Any]:
        """Serialize to the dict format Back expects.

        V2 Design Ref: Section 8.9 (BackContext_TaskResume)
        """
        ctx: dict[str, Any] = {
            "task_id": self.task_id,
            "hil_type": self.hil_type,
            "original_task": self.original_task,
            "findings_so_far": self.findings_so_far,
            "tool_history": self.tool_history,
            "last_iteration": self.last_iteration,
            "resolution": self.resolution,
            "instruction": self.resume_instruction,
            "remaining_budget": self.remaining_budget,
        }
        if self.merged_params:
            ctx["merged_params"] = self.merged_params
        return ctx


def build_resume_context(
    task_id: str,
    hil_type: str,
    resolution: dict[str, Any],
    findings_so_far: list[dict[str, Any]] | None = None,
    original_task: dict[str, Any] | None = None,
    last_iteration: int = 0,
    total_budget: int = 10,
    merged_params: dict[str, Any] | None = None,
) -> ResumeContext:
    """Assemble structured resume context for Back after HITL resolution.

    V2 Design Ref: Section 8.9 (Resume Context Assembly)
    V2 Design Ref: Section 9.7 (Event traces -- resume step)

    Called by the FSM when task.resume.v1 is about to be dispatched to Back.
    Extracts tool history from findings_so_far and computes remaining budget.

    Args:
        task_id:           The suspended task being resumed.
        hil_type:          One of: clarification, approval, selection.
        resolution:        User's structured answer from HILResponse.
        findings_so_far:   ReAct message history before suspension.
        original_task:     Original dispatch spec.
        last_iteration:    Iteration where loop suspended.
        total_budget:      Total ReAct iteration budget.
        merged_params:     Params with user modifications (approval/selection).

    Returns:
        ResumeContext ready for Back consumption.
    """
    findings = findings_so_far or []
    task_spec = original_task or {}

    # Extract tool-call entries from findings history
    tool_calls = [
        entry
        for entry in findings
        if entry.get("role") == "tool" or entry.get("type") == "tool_call"
    ]

    # Compute remaining budget
    remaining = max(1, total_budget - last_iteration)

    # Get type-specific resume instruction
    instruction = RESUME_INSTRUCTIONS.get(hil_type, RESUME_INSTRUCTIONS["clarification"])

    ctx = ResumeContext(
        task_id=task_id,
        hil_type=hil_type,
        original_task=task_spec,
        findings_so_far=findings,
        tool_history=tool_calls,
        last_iteration=last_iteration,
        resolution=resolution,
        resume_instruction=instruction,
        remaining_budget=remaining,
        merged_params=merged_params or {},
    )

    logger.info(
        "Built resume context [task=%s, type=%s, findings=%d, tools=%d, remaining=%d]",
        task_id,
        hil_type,
        len(findings),
        len(tool_calls),
        remaining,
    )

    return ctx


# =========================================================================
# HILModeConfig -- Complete snapshot of a HITL mode's configuration
# =========================================================================


@dataclass
class HILModeConfig:
    """Complete configuration snapshot for a HITL prompt mode.

    V2 Design Ref: Section 6.1 (Prompt Mode Config Matrix)

    Captures all cross-layer configuration for a single HITL mode:
    tools, iterations, prompt sections, SS reads, anti-patterns, examples.
    Used for validation and E2E wiring verification.

    Attributes:
        mode:                 The PromptMode.
        tool_allowlist:       Tools available in this mode.
        max_iterations:       Normal iteration budget.
        crisis_iterations:    Crisis-adjusted iteration budget.
        prompt_sections:      Ordered prompt section keys.
        anti_pattern_key:     Anti-pattern section key (if any).
        ss_read_configs:      SS section read configurations.
        has_examples:         Whether mode-specific examples exist.
    """

    mode: PromptMode
    tool_allowlist: list[str]
    max_iterations: int
    crisis_iterations: int
    prompt_sections: list[str]
    anti_pattern_key: str
    ss_read_configs: list[SSReadConfig]
    has_examples: bool


def get_hitl_relay_config() -> HILModeConfig:
    """Return the complete HITL_RELAY mode configuration.

    V2 Design Ref: Section 6.1 (HITL_RELAY column)
    V2 Design Ref: Section 9.4 (Front HITL_RELAY behavior)

    HITL_RELAY is pure text-only mode:
        - 0 tools (empty allowlist)
        - 1 iteration (translate structured HITL -> natural language)
        - Minimal prompt sections (IDENTITY + EMOTIONAL_CALIB + SAFETY_HITL)
        - 4 SS sections read (affective_now, control, persona, task_state)
        - ANTI_PATTERNS_HITL anti-pattern set
    """
    mode = PromptMode.HITL_RELAY
    return HILModeConfig(
        mode=mode,
        tool_allowlist=list(TOOL_ALLOWLIST[mode]),
        max_iterations=MAX_ITERATIONS_TABLE[mode],
        crisis_iterations=CRISIS_ITERATIONS_TABLE[mode],
        prompt_sections=list(MODE_SECTIONS[mode]),
        anti_pattern_key=ANTI_PATTERN_KEYS.get(mode, ""),
        ss_read_configs=list(SS_READ_CONFIGS[mode]),
        has_examples=mode in MODE_EXAMPLES and bool(MODE_EXAMPLES[mode]),
    )


def get_hitl_resolve_config() -> HILModeConfig:
    """Return the complete HITL_RESOLVE mode configuration.

    V2 Design Ref: Section 6.1 (HITL_RESOLVE column)
    V2 Design Ref: Section 9.4 (Front HITL_RESOLVE behavior)

    HITL_RESOLVE is a short cognitive mode:
        - 1 tool (update_beliefs)
        - 3 iterations (normal) / 2 iterations (crisis)
        - 5 prompt sections (IDENTITY + REACT_RHYTHM_REDUCED + ...)
        - 7 SS sections read (beliefs, scoreboard, affect, control, history, persona, task)
        - ANTI_PATTERNS_HITL anti-pattern set
    """
    mode = PromptMode.HITL_RESOLVE
    return HILModeConfig(
        mode=mode,
        tool_allowlist=list(TOOL_ALLOWLIST[mode]),
        max_iterations=MAX_ITERATIONS_TABLE[mode],
        crisis_iterations=CRISIS_ITERATIONS_TABLE[mode],
        prompt_sections=list(MODE_SECTIONS[mode]),
        anti_pattern_key=ANTI_PATTERN_KEYS.get(mode, ""),
        ss_read_configs=list(SS_READ_CONFIGS[mode]),
        has_examples=mode in MODE_EXAMPLES and bool(MODE_EXAMPLES[mode]),
    )


# =========================================================================
# Cross-layer wiring validation
# =========================================================================


def validate_hitl_wiring() -> list[str]:
    """Validate cross-layer HITL wiring consistency.

    V2 Design Ref: Section 9.10 (HITL Invariants)
    V2 Design Ref: Section 6.1 (Prompt Mode Config Matrix)

    Checks that all layers (prompt, FSM, protocol) are correctly wired
    for HITL flows. Returns a list of issues found (empty = all good).

    Checks performed:
        1. HITL_RELAY has empty tool allowlist (0 tools, pure text)
        2. HITL_RESOLVE has exactly [update_beliefs]
        3. Both HITL modes have ANTI_PATTERNS_HITL
        4. HITL_RELAY has max_iterations=1 (single translation pass)
        5. HITL_RESOLVE has max_iterations=3 (short cognitive turn)
        6. Both modes have in-context examples
        7. HITL_RELAY has SAFETY_HITL in prompt sections
        8. HITL_RESOLVE has STATE_INTERP_TASK in prompt sections
        9. HITL_RELAY reads task_state (needs pending_hil context)
        10. HITL_RESOLVE reads history_active (needs prior conversation)
        11. HITL_RELAY crisis iterations = 1 (no reduction possible)
        12. HITL_RESOLVE crisis iterations = 2 (reduced from 3)
        13. Both modes have IDENTITY section (first section)
        14. Both modes have EMOTIONAL_CALIB (affect-aware tone)

    Returns:
        List of issue strings. Empty list means all wiring is correct.
    """
    issues: list[str] = []

    # ---- HITL_RELAY checks ----
    relay_tools = TOOL_ALLOWLIST[PromptMode.HITL_RELAY]
    if relay_tools:
        issues.append(f"HITL_RELAY tool allowlist should be empty, got {relay_tools}")

    if MAX_ITERATIONS_TABLE[PromptMode.HITL_RELAY] != 1:
        issues.append(
            f"HITL_RELAY max_iterations should be 1, "
            f"got {MAX_ITERATIONS_TABLE[PromptMode.HITL_RELAY]}"
        )

    if CRISIS_ITERATIONS_TABLE[PromptMode.HITL_RELAY] != 1:
        issues.append(
            f"HITL_RELAY crisis_iterations should be 1, "
            f"got {CRISIS_ITERATIONS_TABLE[PromptMode.HITL_RELAY]}"
        )

    relay_sections = MODE_SECTIONS[PromptMode.HITL_RELAY]
    if "SAFETY_HITL" not in relay_sections:
        issues.append("HITL_RELAY missing SAFETY_HITL in prompt sections")
    if "IDENTITY" not in relay_sections:
        issues.append("HITL_RELAY missing IDENTITY in prompt sections")
    if "EMOTIONAL_CALIB" not in relay_sections:
        issues.append("HITL_RELAY missing EMOTIONAL_CALIB in prompt sections")

    relay_ss = {cfg.section for cfg in SS_READ_CONFIGS[PromptMode.HITL_RELAY]}
    if "task_state" not in relay_ss:
        issues.append("HITL_RELAY missing task_state in SS read configs")
    if "affective_now" not in relay_ss:
        issues.append("HITL_RELAY missing affective_now in SS read configs")

    # ---- HITL_RESOLVE checks ----
    resolve_tools = TOOL_ALLOWLIST[PromptMode.HITL_RESOLVE]
    expected_tools = {"update_beliefs"}
    if set(resolve_tools) != expected_tools:
        issues.append(
            f"HITL_RESOLVE tool allowlist should be {expected_tools}, " f"got {set(resolve_tools)}"
        )

    if MAX_ITERATIONS_TABLE[PromptMode.HITL_RESOLVE] != 3:
        issues.append(
            f"HITL_RESOLVE max_iterations should be 3, "
            f"got {MAX_ITERATIONS_TABLE[PromptMode.HITL_RESOLVE]}"
        )

    if CRISIS_ITERATIONS_TABLE[PromptMode.HITL_RESOLVE] != 2:
        issues.append(
            f"HITL_RESOLVE crisis_iterations should be 2, "
            f"got {CRISIS_ITERATIONS_TABLE[PromptMode.HITL_RESOLVE]}"
        )

    resolve_sections = MODE_SECTIONS[PromptMode.HITL_RESOLVE]
    if "STATE_INTERP_TASK" not in resolve_sections:
        issues.append("HITL_RESOLVE missing STATE_INTERP_TASK in prompt sections")
    if "IDENTITY" not in resolve_sections:
        issues.append("HITL_RESOLVE missing IDENTITY in prompt sections")
    if "EMOTIONAL_CALIB" not in resolve_sections:
        issues.append("HITL_RESOLVE missing EMOTIONAL_CALIB in prompt sections")
    if "SAFETY_HITL" not in resolve_sections:
        issues.append("HITL_RESOLVE missing SAFETY_HITL in prompt sections")

    resolve_ss = {cfg.section for cfg in SS_READ_CONFIGS[PromptMode.HITL_RESOLVE]}
    if "history_active" not in resolve_ss:
        issues.append("HITL_RESOLVE missing history_active in SS read configs")
    if "task_state" not in resolve_ss:
        issues.append("HITL_RESOLVE missing task_state in SS read configs")
    if "beliefs_active" not in resolve_ss:
        issues.append("HITL_RESOLVE missing beliefs_active in SS read configs")

    # ---- Shared checks ----
    for mode in (PromptMode.HITL_RELAY, PromptMode.HITL_RESOLVE):
        ap_key = ANTI_PATTERN_KEYS.get(mode)
        if ap_key != "ANTI_PATTERNS_HITL":
            issues.append(
                f"{mode.name} anti-pattern key should be 'ANTI_PATTERNS_HITL', " f"got '{ap_key}'"
            )

        if mode not in MODE_EXAMPLES or not MODE_EXAMPLES[mode]:
            issues.append(f"{mode.name} missing in-context examples")

    # ---- Resume instruction checks ----
    for hil_type in ("clarification", "approval", "selection"):
        if hil_type not in RESUME_INSTRUCTIONS:
            issues.append(f"Missing resume instruction for hil_type='{hil_type}'")

    return issues
