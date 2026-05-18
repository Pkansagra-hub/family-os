"""
k1.concierge.task.tools -- dispatch_task Front control tool.

V2 Design Ref: Section 6.1 (dispatch_task tool schema)
V2 Design Ref: Section 8.3 (single intent dispatch)
V2 Design Ref: Section 8.4 (bundled intents)
V2 Design Ref: Section 8.5 (chained tasks with depends_on)

Called by the Front LLM when the user's intent requires Back execution.
This is a SEQUENTIAL tool (Section 16.8.1): it depends on cognitive
state (beliefs, scoreboard) being up to date before dispatch.

The tool:
    1. Receives structured intents from the LLM
    2. Classifies as SINGLE / BUNDLED / CHAINED
    3. Builds TaskDispatch(es)
    4. Publishes to k1.orchestration.task.dispatch.v1 via publish_fn
    5. Returns observation dict to the LLM

Design doc Section 6.1 shows the return value as:
    {queued: true, task_id: "task-XXX"}
But for multi-dispatch (chained), we return all task IDs plus
classification metadata for the ReAct observation.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from k1.concierge.task.classifier import (
    IntentClassification,
    build_dispatches,
    classify_intents,
)
from k1.concierge.task.complexity import ComplexityTier
from k1.concierge.task.dispatch import TaskDispatch
from k1.concierge.task.intent import TaskIntent

logger = logging.getLogger(__name__)


async def dispatch_task(
    intents_raw: list[dict[str, Any]],
    tier: str = "MEDIUM",
    reference_context: dict[str, str] | None = None,
    urgency: str = "normal",
    depends_on: str | None = None,
    context_snapshot: dict[str, Any] | None = None,
    safety_band: str = "GREEN",
    publish_fn: Callable[[TaskDispatch], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Front tool: dispatch task(s) to Back for execution.

    Called from the ReAct loop when the LLM selects dispatch_task.
    The LLM provides structured intents extracted from user input.

    The design doc (Section 6.1) defines urgency and reference_context
    at the dispatch level (not per-intent).  Per-intent urgency is set
    to the dispatch-level value unless the intent already specifies one.

    Args:
        intents_raw:       List of intent dicts from LLM tool call.
                           Each has "action", "params", optional "domain".
        tier:              Complexity tier string: "LOW", "MEDIUM", "HIGH".
                           Case-insensitive.
        reference_context: Front-resolved pronoun and reference mappings.
                           E.g. {"the hotel": "Vineyard Inn"}.
        urgency:           Dispatch-level urgency: "normal"/"urgent"/"background".
        depends_on:        Task ID this dispatch depends on (for chained via
                           multiple dispatch_task calls). None = independent.
        context_snapshot:  Relevant SessionState sections at dispatch time.
        safety_band:       Safety band: GREEN/AMBER/RED.
        publish_fn:        Async callback to publish TaskDispatch to bus.
                           Injected by the tool registry / FSM.

    Returns:
        Observation dict for the ReAct loop:
        {
            "dispatched": [...task_ids...],
            "classification": "single" | "bundled" | "chained",
            "count": N,
        }
    """
    # Parse intents from LLM output
    # Apply dispatch-level urgency to intents that don't specify their own
    intents: list[TaskIntent] = []
    for raw in intents_raw:
        if "urgency" not in raw:
            raw = {**raw, "urgency": urgency}
        intents.append(TaskIntent.from_dict(raw))

    complexity = ComplexityTier(tier.upper())

    # Classify and build dispatches
    classification = classify_intents(intents)

    # If depends_on is provided at dispatch level (chained via multiple
    # dispatch_task calls per design doc Example 3), we override classification
    if depends_on is not None:
        classification = IntentClassification.CHAINED

    dispatches = build_dispatches(
        intents=intents,
        classification=classification,
        tier=complexity,
        reference_context=reference_context,
        safety_band=safety_band,
        context_snapshot=context_snapshot,
    )

    # For explicit depends_on (multi-call chaining), wire the first dispatch
    if depends_on is not None and dispatches:
        # Rebuild the first dispatch with the external depends_on
        first = dispatches[0]
        dispatches[0] = TaskDispatch(
            intents=first.intents,
            tier=first.tier,
            task_id=first.task_id,
            budget_hint=first.budget_hint,
            reference_context=first.reference_context,
            safety_band=first.safety_band,
            depends_on=depends_on,
            context_snapshot=first.context_snapshot,
        )

    # Publish each dispatch to the bus
    task_ids: list[str] = []
    for dispatch in dispatches:
        if publish_fn is not None:
            await publish_fn(dispatch)
        task_ids.append(dispatch.task_id)
        logger.info(
            "dispatch_task: published %s (classification=%s, intents=%d, depends_on=%s)",
            dispatch.task_id,
            classification.value,
            len(dispatch.intents),
            dispatch.depends_on,
        )

    return {
        "dispatched": task_ids,
        "classification": classification.value,
        "count": len(dispatches),
    }


# =========================================================================
# Tool schema for LLM system prompt injection (V2 Section 6.1)
# =========================================================================

DISPATCH_TASK_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "dispatch_task",
        "description": (
            "Dispatch a task to the background worker for execution. Use when the user "
            "wants something DONE (search, book, create, schedule, send, draft, etc.). "
            "Do NOT call for pure conversation, emotional support, or clarification. "
            "The FSM intercepts this tool call and emits k1.orchestration.task.dispatch.v1 "
            "on the bus. The tool itself returns immediately with dispatched status. "
            "For multi-intent messages, call dispatch_task ONCE with multiple intents "
            "in the intents array. For chained tasks, call dispatch_task multiple times "
            "with depends_on set to the previous task_id."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "intents": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "What to do (natural language or capability name)",
                            },
                            "params": {
                                "type": "object",
                                "description": (
                                    "Structured parameters extracted from conversation and beliefs"
                                ),
                            },
                            "domain": {
                                "type": "string",
                                "description": (
                                    "Domain hint: travel, health, productivity, finance, "
                                    "creative, shopping, family, etc."
                                ),
                            },
                        },
                        "required": ["action"],
                    },
                    "minItems": 1,
                    "description": (
                        "One or more intents to execute. Independent intents are bundled. "
                        "Sequential intents use depends_on."
                    ),
                },
                "urgency": {
                    "type": "string",
                    "enum": ["normal", "urgent", "background"],
                    "default": "normal",
                },
                "reference_context": {
                    "type": "object",
                    "description": (
                        "Resolved references for the Back worker. Front resolves pronouns and "
                        "references using its history view and passes resolved values here. "
                        "E.g. {'the hotel': 'Vineyard Inn', 'it': 'restaurant search'}."
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "depends_on": {
                    "type": "string",
                    "description": (
                        "Task ID this dispatch depends on (for chained tasks). "
                        "Omit for independent tasks."
                    ),
                },
            },
            "required": ["intents"],
        },
    },
}
