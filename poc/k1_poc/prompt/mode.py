"""
poc.k1_poc.prompt.mode -- PromptMode enum and mode resolution.

Implements V2 Section 4 FSM-driven prompt assembly mode selection.
Each PromptMode determines which tools, SS sections, prompt sections,
examples, and iteration limits are injected into the Front LLM context.

The determine_mode() function resolves FSM state + event topic + SS signals
to exactly one PromptMode. No ambiguity -- every combination resolves to
exactly one mode. Priority order (first match wins):

    1. Explicit FSM state mappings
    2. FSM state + event topic combinations
    3. Event-topic-driven mappings
    4. SS-signal-driven fallbacks
    5. Default: STANDARD
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

from poc.k1_poc.config import get_config


class PromptMode(Enum):
    """Cognitive mode for Front LLM prompt assembly.

    Each mode selects a specific subset of tools, SS sections,
    prompt sections, examples, and modulation rules.

    Values:
        STANDARD:        Normal user input, full cognitive processing
        CLARIFY_ASK:     Front detected ambiguity, asking user
        CLARIFY_RESOLVE: User answered a clarification question
        HITL_RELAY:      Back suspended, present question to user
        HITL_RESOLVE:    User answered HITL question
        PRESENT:         Delivering task results
        WEAVE:           Presenting async results mid-conversation
        CANCEL:          Confirming/handling cancellation
        INTERRUPT:       New user input while task in progress
        ERROR:           Task failed, explaining gracefully
    """

    STANDARD = "standard"
    CLARIFY_ASK = "clarify_ask"
    CLARIFY_RESOLVE = "clarify_resolve"
    HITL_RELAY = "hitl_relay"
    HITL_RESOLVE = "hitl_resolve"
    PRESENT = "present"
    WEAVE = "weave"
    CANCEL = "cancel"
    INTERRUPT = "interrupt"
    ERROR = "error"


# =========================================================================
# Tool allowlist per mode (V2 Section 16.3)
# =========================================================================

TOOL_ALLOWLIST: dict[PromptMode, list[str]] = {
    PromptMode.STANDARD: [
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "update_narrative",
        "recall_memory",
        "summarize_context",
        "dispatch_task",
        # refine_affect and promote_belief added conditionally at build time
    ],
    PromptMode.CLARIFY_ASK: [
        "update_clarifications",
        "recall_memory",
    ],
    PromptMode.CLARIFY_RESOLVE: [
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "promote_belief",
        "recall_memory",
        "dispatch_task",
    ],
    PromptMode.HITL_RELAY: [],  # Pure text-only
    PromptMode.HITL_RESOLVE: [
        "update_beliefs",
    ],
    PromptMode.PRESENT: [
        "update_beliefs",
        "update_narrative",
    ],
    PromptMode.WEAVE: [
        "update_beliefs",
        "update_narrative",
        # V3 E0.1.2: update_scoreboard added so salience scoring is updated
        # when async results are woven into conversation in the same turn.
        "update_scoreboard",
    ],
    PromptMode.CANCEL: [
        "update_beliefs",
        "update_narrative",
    ],
    PromptMode.INTERRUPT: [
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "update_narrative",
        "refine_affect",
        "promote_belief",
        "recall_memory",
        "summarize_context",
        "dispatch_task",
    ],
    PromptMode.ERROR: [
        "update_narrative",
    ],
}


def get_tool_allowlist(
    mode: PromptMode,
    affect_confidence: float = 1.0,
    tier: str = "LOW",
) -> list[str]:
    """Return the tool allowlist for a mode with conditional inclusions.

    V2 Design Doc Section 6.1 (Conditional Tool Inclusion, ITEM #11):
      - refine_affect: added when affect_confidence < 0.6 (Phase 1 uncertain)
      - promote_belief: added when tier != "LOW" (MEDIUM/HIGH complexity)

    STANDARD mode has 8 base tools, up to 10 with conditionals.
    INTERRUPT always has all 10 (conditionals are already in the base list).

    Args:
        mode: The current PromptMode.
        affect_confidence: Phase 1 affect confidence (0.0-1.0).
        tier: Task complexity tier ("LOW", "MEDIUM", "HIGH").

    Returns:
        List of tool names available for this mode.
    """
    base = list(TOOL_ALLOWLIST[mode])

    # HITL_RELAY is strictly text-only -- no conditional tools.
    # Adding tools here wastes the tight 2-iteration budget and
    # causes degenerate empty responses.
    if mode == PromptMode.HITL_RELAY:
        return base

    # Conditional: refine_affect when Phase 1 affect is uncertain
    threshold = get_config().prompt.affect_confidence_threshold
    if affect_confidence < threshold and "refine_affect" not in base:
        base.append("refine_affect")

    # Conditional: promote_belief for non-LOW tier tasks
    if tier != "LOW" and "promote_belief" not in base:
        base.append("promote_belief")

    return base


# =========================================================================
# Max iterations per mode (V2 Section 16.3)
# =========================================================================

MAX_ITERATIONS_TABLE: dict[PromptMode, int] = {
    PromptMode.STANDARD: 6,
    PromptMode.CLARIFY_ASK: 3,
    PromptMode.CLARIFY_RESOLVE: 5,
    PromptMode.HITL_RELAY: 2,
    PromptMode.HITL_RESOLVE: 3,
    PromptMode.PRESENT: 3,
    PromptMode.WEAVE: 3,
    PromptMode.CANCEL: 3,
    PromptMode.INTERRUPT: 6,
    PromptMode.ERROR: 2,
}

CRISIS_ITERATIONS_TABLE: dict[PromptMode, int] = {
    PromptMode.STANDARD: 4,
    PromptMode.CLARIFY_ASK: 2,
    PromptMode.CLARIFY_RESOLVE: 4,
    PromptMode.HITL_RELAY: 2,
    PromptMode.HITL_RESOLVE: 2,
    PromptMode.PRESENT: 2,
    PromptMode.WEAVE: 2,
    PromptMode.CANCEL: 2,
    PromptMode.INTERRUPT: 4,
    PromptMode.ERROR: 2,
}


def get_max_iterations(mode: PromptMode, affect_band: str = "neutral") -> int:
    """Return the iteration budget for a mode, adjusted for crisis affect.

    V2 Design Doc Section 6.1: When the user is in crisis
    (valence < -0.5, arousal > 0.7), faster response is more important
    than thorough cognitive processing. The crisis table reduces
    iterations by 1-2 to force earlier response.

    This is the standalone version of DynamicPromptBuilder._get_max_iterations().

    Args:
        mode: The current PromptMode.
        affect_band: The computed affect band string.
            "crisis" triggers the CRISIS_ITERATIONS_TABLE.
            All other bands use MAX_ITERATIONS_TABLE.

    Returns:
        Integer iteration budget. Always >= 1.
    """
    cfg = get_config().prompt
    mode_key = mode.name  # e.g. "STANDARD"
    if affect_band == "crisis":
        return cfg.crisis_iterations.get(mode_key, CRISIS_ITERATIONS_TABLE[mode])
    return cfg.max_iterations.get(mode_key, MAX_ITERATIONS_TABLE[mode])


# =========================================================================
# Topic constants (imported from bus.topics -- single source of truth)
# V3 E0.1.4: replaced inline string literals with canonical imports.
# =========================================================================

from poc.k1_poc.bus.topics import TOPIC_TASK_COMPLETE as _TOPIC_TASK_COMPLETE  # noqa: E402
from poc.k1_poc.bus.topics import TOPIC_TASK_FAILED as _TOPIC_TASK_FAILED  # noqa: E402
from poc.k1_poc.bus.topics import TOPIC_TASK_SUSPENDED as _TOPIC_TASK_SUSPENDED  # noqa: E402
from poc.k1_poc.bus.topics import TOPIC_USER_INPUT as _TOPIC_USER_INPUT  # noqa: E402
from poc.k1_poc.bus.topics import TOPIC_WEAVE_BATCH as _TOPIC_WEAVE_BATCH  # noqa: E402

# =========================================================================
# determine_mode() -- Mode Resolution (V2 Section 4, 16.3)
# =========================================================================


def determine_mode(
    fsm_state: str,
    envelope_topic: str,
    clarification_state: dict[str, Any] | None = None,
    task_state: dict[str, Any] | None = None,
    affect: dict[str, Any] | None = None,
    routing_metadata: dict[str, Any] | None = None,
) -> PromptMode:
    """Resolve FSM state + event topic + SS signals to a single PromptMode.

    Priority order (first match wins):
        1. Explicit FSM state mappings
        2. FSM state + event topic combinations
        3. Event-topic-driven mappings
        4. SS-signal-driven fallbacks
        5. Default: STANDARD

    Args:
        fsm_state: Current FSM state string (e.g. "CANCELLING", "DISPATCHING").
        envelope_topic: The topic string from the incoming Envelope.
        clarification_state: Dict with keys:
            open_gaps (int), blocking_gaps (int), depth (int).
        task_state: Dict with key "tasks" (list of task dicts with "status" field).
        affect: Dict with "valence" and "arousal" floats.
        routing_metadata: Arbiter routing metadata from M5 E5.3.3.
            Currently passed through for future mode refinement (M8+).
            Contains arbiter_reason, domain overlap, entity overlap, etc.

    Returns:
        PromptMode: The resolved prompt mode. Guaranteed to be exactly one.
    """
    clarification_state = clarification_state or {}
    task_state = task_state or {}

    # 1. Explicit FSM state mappings
    if fsm_state == "CANCELLING":
        logger.info(
            "determine_mode  fsm=%s topic=%s -> CANCEL (explicit state)",
            fsm_state,
            envelope_topic,
        )
        return PromptMode.CANCEL
    if fsm_state == "INTERRUPT_HANDLING":
        logger.info(
            "determine_mode  fsm=%s topic=%s -> INTERRUPT (explicit state)",
            fsm_state,
            envelope_topic,
        )
        return PromptMode.INTERRUPT

    # 1b. Detect interrupt via routing_metadata (INTERRUPT_HANDLING is transient,
    #     FSM has already moved to DISPATCHING by the time Front reads SS)
    if routing_metadata and routing_metadata.get("interrupt_origin"):
        logger.info(
            "determine_mode  routing_metadata.interrupt_origin -> INTERRUPT",
        )
        return PromptMode.INTERRUPT

    # 2. FSM state + event topic combinations
    if fsm_state == "CLARIFYING_USER":
        if envelope_topic == _TOPIC_USER_INPUT:
            logger.info(
                "determine_mode  fsm=%s topic=%s -> CLARIFY_RESOLVE",
                fsm_state,
                envelope_topic,
            )
            return PromptMode.CLARIFY_RESOLVE
        logger.info(
            "determine_mode  fsm=%s topic=%s -> CLARIFY_ASK",
            fsm_state,
            envelope_topic,
        )
        return PromptMode.CLARIFY_ASK

    if fsm_state == "CLARIFYING_WORKER":
        if envelope_topic == _TOPIC_USER_INPUT:
            logger.info(
                "determine_mode  fsm=%s topic=%s -> HITL_RESOLVE",
                fsm_state,
                envelope_topic,
            )
            return PromptMode.HITL_RESOLVE
        logger.info(
            "determine_mode  fsm=%s topic=%s -> HITL_RELAY",
            fsm_state,
            envelope_topic,
        )
        return PromptMode.HITL_RELAY

    # 3. Event-topic-driven mappings
    if envelope_topic == _TOPIC_TASK_COMPLETE:
        logger.info("determine_mode  topic=%s -> PRESENT", envelope_topic)
        return PromptMode.PRESENT
    if envelope_topic == _TOPIC_TASK_FAILED:
        logger.info("determine_mode  topic=%s -> ERROR", envelope_topic)
        return PromptMode.ERROR
    if envelope_topic == _TOPIC_WEAVE_BATCH:
        logger.info("determine_mode  topic=%s -> WEAVE", envelope_topic)
        return PromptMode.WEAVE
    if envelope_topic == _TOPIC_TASK_SUSPENDED:
        logger.info("determine_mode  topic=%s -> HITL_RELAY", envelope_topic)
        return PromptMode.HITL_RELAY

    # 4. SS-signal-driven fallbacks (only for user input)
    if envelope_topic == _TOPIC_USER_INPUT:
        tasks = task_state.get("tasks", [])
        suspended = [t for t in tasks if t.status == "SUSPENDED"]
        if suspended:
            logger.info(
                "determine_mode  topic=user_input suspended_tasks=%d -> HITL_RESOLVE",
                len(suspended),
            )
            return PromptMode.HITL_RESOLVE
        if clarification_state.get("blocking_gaps", 0) > 0:
            logger.info(
                "determine_mode  topic=user_input blocking_gaps=%d -> CLARIFY_RESOLVE",
                clarification_state["blocking_gaps"],
            )
            return PromptMode.CLARIFY_RESOLVE

    # 5. Default
    logger.info(
        "determine_mode  fsm=%s topic=%s -> STANDARD (default)",
        fsm_state,
        envelope_topic,
    )
    return PromptMode.STANDARD
