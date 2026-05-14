"""
k1.concierge.actors.back -- Back Handler (Epic 7.1-7.4).

The back_handler is the entry point invoked by the FSM when a task.dispatch
event targets the Back LLM. It:
  1. Reads selective SS snapshot (beliefs, task_state, artifacts, safety, persona)
  2. Builds Back system prompt via build_back_prompt (static identity + dynamic task)
  3. Assembles messages: 5-entry history + task JSON as "user" message
  4. Runs the ReAct loop with tier-based budget and cancellation callback
  5. Emits result events (task.complete, task.failed, task.suspended)
  6. Emits observability events (tool.started, tool.completed) per tool call
  7. Handles task.cancel by setting cancellation flag
  8. Handles task.resume by replaying prior ReAct history + resolution

V2 Design Ref: Section 6.2, 8.7-8.9, 16.4 (Back Handler Wiring)

Bus API notes (actual Envelope implementation):
  - Envelope.payload is bytes (JSON serialized via builders)
  - Envelope.envelope_id is int (not 'id')
  - Envelope.cognitive_trace_id is str (not 'trace_id')
  - IBus.publish(envelope) -- not emit()
  - Use k1.concierge.bus.builders for envelope construction

Identity contract (V2 Section 4.2):
  The Back is the executor. Precise, tool-focused, no personality.
  It NEVER talks to the user directly. It NEVER streams text to the
  output channel. It only consumes and produces structured JSON payloads.
  Back NEVER writes SessionState directly -- all mutations flow as
  structured deltas via the K1 Bus.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus

# Shared actor utilities (M3 E3.5)
from k1.concierge.actors.shared import never_cancel as _never_cancel
from k1.concierge.actors.shared import parse_envelope_payload as _parse_payload
from k1.concierge.actors.shared import safe_get_section as _safe_get_section
from k1.concierge.bus.builders import (
    build_artifact_created,
    build_task_complete,
    build_task_failed,
    build_task_suspended,
    build_tool_completed,
    build_tool_started,
)
from k1.concierge.config import get_config
from k1.concierge.llm.types import ModelMessage
from k1.concierge.llm.validator import LLMOutputValidator
from k1.concierge.prompt.back_prompt import build_back_prompt
from k1.concierge.protocols.cancellation import CancellationToken, CancelReason
from k1.concierge.protocols.suspension import SuspensionResolutionNotFound
from k1.concierge.react.history import build_chat_history_for_back
from k1.concierge.react.loop import ReactResult, react_loop
from k1.concierge.tools.dispatcher import ToolDispatcher, create_back_dispatcher
from k1.concierge.tools.schemas_back import BACK_TIER_ALLOWLISTS, BACK_TOOL_SCHEMAS
from k1.model_hub.ports import IModelHubPort

logger = logging.getLogger(__name__)

# Compatibility export -- max ReAct iterations per tier
# (mirrors config default: BackActorConfig.max_iterations)
BACK_MAX_ITERATIONS: dict[str, int] = {"LOW": 4, "MEDIUM": 8, "HIGH": 12}


# =========================================================================
# Budget / tier helpers
# =========================================================================


def _budget_to_iterations(budget_hint: int) -> int:
    """Map budget_hint from TaskDispatch to max_iterations for react_loop.

    Budget values from V2 Section 26.6:
      LOW tier:    budget_hint ~2-4  -> max_iterations = budget_hint
      MEDIUM tier: budget_hint ~5-8  -> max_iterations = budget_hint
      HIGH tier:   budget_hint ~8-12 -> max_iterations = budget_hint
    The budget_hint IS the max tool calls including submit_result.
    Floor value loaded from config.
    """
    return max(budget_hint, get_config().actors.back.budget_floor)


def _filter_back_tools(tier: str) -> list[Any]:
    """Return Back tool schemas filtered by tier allowlist.

    P3.4b: tier may be 'simple', 'plan', or any legacy alias (LOW/MEDIUM/HIGH).
    """
    allowed = set(BACK_TIER_ALLOWLISTS.get(tier, ["submit_result"]))
    return [t for t in BACK_TOOL_SCHEMAS if t.name in allowed]


# =========================================================================
# P3.4c: Per-task back dispatcher tier rebind
# =========================================================================


def _resolve_back_tier_bucket(task_tier: str) -> str:
    """Map a task tier (legacy or canonical) to its back-dispatcher bucket."""
    upper = str(task_tier).upper()
    if upper in ("MEDIUM", "HIGH"):
        return "plan"
    return "simple"


def _maybe_rebind_back_dispatcher(
    tool_dispatcher: ToolDispatcher,
    task_tier: str,
    bus: IBus,
) -> ToolDispatcher:
    """Return an equal-or-upgraded back ToolDispatcher for the given task tier.

    Per-task rebind: avoids a global tool_tier config by spinning up a fresh
    dispatcher when the task requires the larger 'plan' allowlist.
    """
    desired_bucket = _resolve_back_tier_bucket(task_tier)
    if tool_dispatcher.tier == desired_bucket:
        return tool_dispatcher
    logger.info(
        "back_handler: rebinding dispatcher tier %s -> %s for task tier %s",
        tool_dispatcher.tier,
        desired_bucket,
        task_tier,
    )
    return create_back_dispatcher(
        tier=desired_bucket,
        ctx=tool_dispatcher.ctx,
        bus=bus,
    )


# =========================================================================
# Observability helpers (Epic 7.3.1, 7.3.2)
# =========================================================================


def _summarize_args(args: dict[str, Any], max_len: int | None = None) -> str:
    """Summarize tool call arguments for observability.

    Masks sensitive fields (loaded from config).
    Truncates to max_len characters (default from config).
    """
    _cfg = get_config().actors.back
    if max_len is None:
        max_len = _cfg.summarize_args_max_len
    safe = {}
    sensitive_keys = set(_cfg.sensitive_keys)
    for k, v in args.items():
        if k in sensitive_keys:
            safe[k] = "***"
        else:
            safe[k] = v
    text = json.dumps(safe, separators=(",", ":"), default=str)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _summarize_result(result: dict[str, Any], max_len: int | None = None) -> str:
    """Summarize tool result for observability. Truncates to max_len (default from config)."""
    if max_len is None:
        max_len = get_config().actors.back.summarize_result_max_len
    text = json.dumps(result, separators=(",", ":"), default=str)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _extract_tool_history(result: ReactResult) -> list[dict[str, Any]]:
    """Extract a summary of tool calls from the ReactResult dispatched_tasks."""
    return result.dispatched_tasks


def _status_to_error_code(status: str) -> str:
    """Map result status to error_code string."""
    mapping = {
        "cancelled": "CANCELLED",
        "budget_exhausted": "BUDGET_EXHAUSTED",
        "tool_error": "TOOL_ERROR",
    }
    return mapping.get(status, "UNKNOWN")


# =========================================================================
# SS snapshot helpers (V2 Section 25.4.1)
# =========================================================================


def _read_ss_snapshot(ss: Any) -> dict[str, Any]:
    """Read selective SS snapshot for Back context.

    Back reads ONCE at task start. It does NOT re-read during ReAct iterations.

    M4 E4.5.6: Uses SECTION_RENDERERS from prompt.builder for task_state,
    task_artifacts, and beliefs_active to ensure consistent formatting
    between Front prompt assembly and Back context reads.

    Sections read:
      beliefs_active   -- User facts, constraints, preferences
      scoreboard       -- Referent resolution (pronouns)
      task_state       -- Dependency info, active tasks
      task_artifacts   -- What has been done (avoid re-doing)
      control          -- Safety band only
      history_active   -- 5 recent entries
      persona          -- Payment, dietary, accessibility

    Sections NOT read:
      affective_now    -- Back has no personality
      clarifications   -- Front's concern
      narrative_active -- Thread tracking is Front's job
      meta             -- Irrelevant to task execution
    """
    beliefs = _safe_get_section(ss, "beliefs_active")
    scoreboard = _safe_get_section(ss, "scoreboard")
    task_state = _safe_get_section(ss, "task_state")
    task_artifacts = _safe_get_section(ss, "task_artifacts")
    control = _safe_get_section(ss, "control")
    history = _safe_get_section(ss, "history_active")
    persona = _safe_get_section(ss, "persona")

    def _render_via_renderer(section: Any, section_name: str) -> str:
        """Render section using SECTION_RENDERERS (full mode) for consistency.

        Falls back to section.to_prompt() if no renderer is registered.
        """
        if section is None:
            return ""
        try:
            from k1.concierge.prompt.builder import SECTION_RENDERERS, SSReadConfig

            renderers = SECTION_RENDERERS.get(section_name)
            if renderers is not None:
                full_fn = renderers[0]
                cfg = SSReadConfig(section=section_name, read_mode="full")
                text = full_fn(section, cfg)
                if text:
                    return text
        except Exception:
            pass
        # Fallback: direct to_prompt
        if hasattr(section, "to_prompt"):
            return section.to_prompt()
        return ""

    def _get_referents(section: Any) -> dict[str, Any]:
        if section is None:
            return {}
        if hasattr(section, "get_referents"):
            return section.get_referents()
        return {}

    def _get_safety_band(section: Any) -> str:
        _default = get_config().actors.back.default_safety_band
        if section is None:
            return _default
        if hasattr(section, "safety"):
            band = getattr(section.safety, "band", None)
            return band if band else _default
        if hasattr(section, "flow_state"):
            return _default
        return _default

    def _get_persona_prefs(section: Any) -> dict[str, Any]:
        if section is None:
            return {}
        result = {}
        for key in ("payment_method", "dietary", "accessibility"):
            if hasattr(section, "get"):
                result[key] = section.get(key)
            elif hasattr(section, key):
                result[key] = getattr(section, key, None)
        return result

    def _get_history_entries(section: Any) -> list[Any]:
        if section is None:
            return []
        # Preferred: decompose Turn objects into TypedHistoryEntry
        if hasattr(section, "get_typed_entries"):
            return section.get_typed_entries()
        if hasattr(section, "entries"):
            return section.entries
        if hasattr(section, "get_all"):
            return section.get_all()
        return []

    return {
        "beliefs_prompt": _render_via_renderer(beliefs, "beliefs_active"),
        "referents": _get_referents(scoreboard),
        "task_state_prompt": _render_via_renderer(task_state, "task_state"),
        "task_artifacts_prompt": _render_via_renderer(task_artifacts, "task_artifacts"),
        "safety_band": _get_safety_band(control),
        "history_entries": _get_history_entries(history),
        "persona_prefs": _get_persona_prefs(persona),
    }


# =========================================================================
# Envelope payload helper
# =========================================================================


# =========================================================================
# Message serialization helpers (M3 E3.3.4)
# =========================================================================


def _serialize_messages(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    """Serialize ModelMessage list to JSON-safe dicts for resume context.

    M3 E3.3.4: When Back suspends, the react history is serialized
    and included in the task.suspended payload so the FSM can store
    it via SuspensionManager.store_context and deliver it back on
    resume via the enriched envelope.
    """
    result = []
    for m in messages:
        entry: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_call_id:
            entry["tool_call_id"] = m.tool_call_id
        if m.name:
            entry["name"] = m.name
        if m.tool_calls:
            entry["tool_calls"] = [
                {"name": tc.name, "arguments": tc.arguments} for tc in m.tool_calls
            ]
        result.append(entry)
    return result


def _deserialize_messages(data: list[dict]) -> list[ModelMessage]:
    """Reconstruct ModelMessage list from serialized dicts.

    M3 E3.3.2: Used by back_resume_handler to reconstruct the prior
    message history from the envelope-carried resume_context.
    """
    return [
        ModelMessage(
            role=d.get("role", "user"),
            content=d.get("content", ""),
            tool_call_id=d.get("tool_call_id"),
            name=d.get("name"),
        )
        for d in data
    ]


# =========================================================================
# Result emission helper (shared by back_handler and back_resume_handler)
# =========================================================================


def _emit_back_result(
    bus: IBus,
    envelope: Envelope,
    task_id: str,
    result: ReactResult,
    react_history: list[ModelMessage] | None = None,
    original_task: dict[str, Any] | None = None,
    tool_call_summaries: list[dict[str, Any]] | None = None,
) -> None:
    """Emit the appropriate bus event based on ReactResult status.

    Status mapping (V2 Section 16.4):
      complete         -> k1.orchestration.task.complete.v1
      suspended        -> k1.orchestration.task.suspended.v1
      cancelled        -> k1.orchestration.task.failed.v1
      budget_exhausted -> k1.orchestration.task.failed.v1

    M3 E3.3.4: When status is 'suspended', react_history and
    original_task are included in the payload so the FSM can store
    them via SuspensionManager and deliver them back on resume.
    """
    parent_id = envelope.envelope_id

    # Extract original task action from dispatch envelope for
    # downstream PRESENT mode scenario data
    envelope_task = _parse_payload(envelope)
    task_action = envelope_task.get("action", "")
    if not task_action:
        intents = envelope_task.get("intents")
        if isinstance(intents, list) and intents:
            task_action = intents[0].get("action", "")

    if result.status == "complete":
        data = result.data or {}
        complete_payload: dict[str, Any] = {
            "task_id": task_id,
            "action": task_action,
            "result_type": "complete",
            "final_answer": data.get("final_answer", ""),
            "results": data.get("results", []),
            "artifacts_created": data.get("artifacts_created", []),
        }
        if tool_call_summaries:
            complete_payload["tool_call_summaries"] = tool_call_summaries
        env = build_task_complete(
            payload=complete_payload,
            parent_id=parent_id,
        )
        bus.publish(env)

    elif result.status == "suspended":
        data = result.data or {}
        suspended_payload: dict[str, Any] = {
            "task_id": task_id,
            "hil_type": data.get("hil_type", "clarification"),
            "question": data.get("question", ""),
            "options": data.get("options", []),
            "side_effects": data.get("side_effects", []),
            "timeout_s": get_config().actors.back.hitl_timeout_s,
        }
        # M3 E3.3.4: Include react history and original task so FSM
        # can store them via SuspensionManager and deliver on resume.
        if react_history is not None:
            suspended_payload["react_history"] = _serialize_messages(react_history)
        if original_task is not None:
            suspended_payload["original_task"] = original_task
        env = build_task_suspended(
            payload=suspended_payload,
            parent_id=parent_id,
        )
        bus.publish(env)

    elif result.status in ("cancelled", "budget_exhausted"):
        data = result.data if result.data else {}
        env = build_task_failed(
            payload={
                "task_id": task_id,
                "reason": result.status,
                "error_code": _status_to_error_code(result.status),
                "partial_results": data.get("partial_results") if data else None,
            },
            parent_id=parent_id,
        )
        bus.publish(env)


# =========================================================================
# back_handler -- V2 Section 6.2 Back Handler Wiring (Epic 7.1)
# =========================================================================


async def back_handler(
    envelope: Envelope,
    model: IModelHubPort,
    ss: Any,
    bus: IBus,
    tool_dispatcher: ToolDispatcher,
    fsm_state: Any | None = None,
    cancel_token: CancellationToken | None = None,
) -> ReactResult:
    """Back handler: ReAct agent for task execution.

    Called by FSM when a task.dispatch arrives. Builds task-focused
    context and runs the ReAct loop with tier-based budget. Back is
    a pure executor: no personality, no user-facing text, JSON-only.

    SS READ CONTRACT (V3 E0.1.6):
      - Snapshot-at-start: SS is read ONCE via _read_ss_snapshot() at
        the beginning of this handler.  The snapshot is immutable for
        the duration of the ReAct loop.
      - No mid-loop re-reads: Back MUST NOT access the live SS manager
        during ReAct iterations.  The dispatch snapshot is the contract.
      - Re-read on resume: When a suspended task is resumed, the resume
        handler (back_resume_handler) re-reads SS at resume time to
        capture any state changes that occurred during suspension.
      - The ``ss`` parameter is passed in but should only be used for
        the initial snapshot call.  A future enhancement may replace it
        with a read-only proxy to enforce this at runtime.

    4-step flow (V2 Section 16.4):
      1. Build system prompt with task context + SS snapshot
      2. Build messages: 5-entry history + task JSON as "user" message
      3. Run ReAct loop with Back-specific tools and termination
      4. Emit result to bus

    Args:
        envelope: The incoming bus Envelope (task.dispatch).
        model: LLM adapter implementing IConciergeModelPort.
        ss: SessionStateManager instance (duck typed for section access).
        bus: IBus instance for publishing response events.
        tool_dispatcher: Back ToolDispatcher for tool execution.
        fsm_state: FSM controller for token extraction (legacy fallback).
        cancel_token: Per-task CancellationToken (M3 E3.2.5). If None,
            extracted from fsm_state.cancel_handler.get_token(task_id).

    Returns:
        ReactResult from the ReAct loop execution.
    """
    trace_id = envelope.cognitive_trace_id
    task = _parse_payload(envelope)
    task_id = task.get("task_id", "")
    tier = task.get("tier", "LOW")
    # P3.4c: Per-task tier rebind for the back dispatcher.
    tool_dispatcher = _maybe_rebind_back_dispatcher(tool_dispatcher, tier, bus)

    logger.info(
        "back_handler: task_id=%s tier=%s trace=%s",
        task_id,
        tier,
        trace_id[:8] if trace_id else "",
    )

    # 1. Read SS snapshot ONCE at task start
    snapshot = _read_ss_snapshot(ss)
    logger.info(
        "back_handler: SS snapshot  beliefs_len=%d referents=%d safety=%s history=%d",
        len(snapshot["beliefs_prompt"]),
        len(snapshot["referents"]),
        snapshot["safety_band"],
        len(snapshot["history_entries"]),
    )

    # 2. Build system prompt with task context + SS snapshot
    _back_cfg = get_config().actors.back
    max_iterations = _back_cfg.max_iterations.get(tier, _back_cfg.max_iterations["LOW"])
    budget_hint = task.get("budget_hint")
    if budget_hint is not None:
        max_iterations = _budget_to_iterations(budget_hint)

    system_prompt = build_back_prompt(
        task=task,
        beliefs=snapshot["beliefs_prompt"],
        referents=snapshot["referents"],
        task_state=snapshot["task_state_prompt"],
        task_artifacts=snapshot["task_artifacts_prompt"],
        safety_band=snapshot["safety_band"],
        persona_prefs=snapshot["persona_prefs"],
        max_tool_calls=max_iterations,
    )

    # 3. Build messages: last N entries + task as "user" message
    messages = build_chat_history_for_back(
        snapshot["history_entries"], window=_back_cfg.history_window
    )
    messages.append(
        ModelMessage(
            role="user",
            content=json.dumps(task, indent=2),
        )
    )

    # 4. Select tools by tier
    tools = _filter_back_tools(tier)

    # M5 E5.5.4: Register messages list with controller for inter-iteration
    # injection (modify-inflight).  The controller's RunningTaskHandle stores
    # a reference to this SAME list object so _handle_arbiter_modify() can
    # append a synthetic PARAMETER_UPDATE message between iterations.
    if fsm_state and hasattr(fsm_state, "register_running_task_messages"):
        fsm_state.register_running_task_messages(task_id, messages)

    logger.info(
        "back_handler: LLM INPUT  prompt_len=%d messages=%d tools=%d max_iter=%d tier=%s",
        len(system_prompt),
        len(messages),
        len(tools),
        max_iterations,
        tier,
    )
    logger.debug(
        "back_handler: LLM INPUT tools=%s",
        [t.name for t in tools],
    )

    # Build output validator with tier-filtered tools (Epic 4.1)
    validator = LLMOutputValidator(tools) if tools else None

    # 5. Build cancellation callback (M3 E3.2.3: per-task token)
    if cancel_token is None:
        cancel_token = _extract_cancel_token(fsm_state, task_id)
    cancellation_check = _build_cancellation_check(
        cancel_token=cancel_token,
        fsm_state=fsm_state,
    )

    # 6. Run ReAct loop (V2 Section 7, ITEM #14, ITEM #19)
    result = await react_loop(
        actor="back",
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        max_iterations=max_iterations,
        model=model,
        tool_dispatcher=tool_dispatcher,
        on_text_response=_noop_text,
        cancellation_check=cancellation_check,
        trace_id=trace_id,
        scenario="task_execution",
        validator=validator,
    )

    # 6b. needs_human → task.suspended (no in-process bypass).
    # When react_loop returns status="suspended" (Back called
    # submit_result(needs_human, ...)), _emit_back_result below publishes
    # TOPIC_TASK_SUSPENDED. The FSM transitions COMPANIONING →
    # CLARIFYING_WORKER, Front runs in HITL_RELAY mode to translate the
    # structured request to natural-language prose, the user replies via
    # ordinary chat, and Front (HITL_RESOLVE) emits TOPIC_TASK_RESUME
    # which back_resume_handler picks up to continue the ReAct loop.
    # This preserves the Front-owns-user-channel invariant (see
    # _scan_temp/04_actors.md and _scan_temp/11_diagram.md §8.3).

    # 7. Emit result to bus (Epic 7.3)
    # M3 E3.3.4: Pass react history + original task for suspended payloads
    # Phase P: Extract tool call summaries for MW persistence
    call_summaries = [s.to_dict() for s in tool_dispatcher.get_call_summaries()]
    _emit_back_result(
        bus,
        envelope,
        task_id,
        result,
        react_history=messages,
        original_task=task,
        tool_call_summaries=call_summaries,
    )

    logger.info(
        "back_handler: LLM OUTPUT  status=%s text_len=%d tool_calls=%d trace=%s",
        result.status,
        len(result.text) if result.text else 0,
        len(result.tool_calls) if hasattr(result, "tool_calls") else 0,
        trace_id[:8] if trace_id else "",
    )
    if result.data:
        logger.debug(
            "back_handler: LLM OUTPUT data_keys=%s",
            list(result.data.keys()),
        )

    logger.info(
        "back_handler complete: task_id=%s status=%s trace=%s",
        task_id,
        result.status,
        trace_id[:8] if trace_id else "",
    )

    return result


# =========================================================================
# back_resume_handler -- Epic 7.4.1 (Task Resume)
# =========================================================================


async def back_resume_handler(
    envelope: Envelope,
    model: IModelHubPort,
    ss: Any,
    bus: IBus,
    tool_dispatcher: ToolDispatcher,
    fsm_state: Any | None = None,
    cancel_token: CancellationToken | None = None,
) -> ReactResult:
    """Resume a suspended Back task with user's resolution.

    SS READ CONTRACT (V3 E0.1.6):
      - Re-read on resume: SS is re-read at resume time via
        _read_ss_snapshot() to capture state changes that occurred
        during the suspension period (e.g., new beliefs, updated
        scoreboard from Front interactions while task was suspended).
      - The fresh snapshot replaces the original dispatch snapshot
        for the remainder of the ReAct loop.

    Flow (V2 Section 6.6 + 25.4.2):
      1. Retrieve original task + prior ReAct messages from fsm_state
      2. Re-read SS (may have changed during suspension)
      3. Build system prompt (same as original dispatch)
      4. Hydrate resolution into messages
      5. Calculate remaining budget
      6. Continue ReAct loop
      7. Emit result + clean up pending context

    Args:
        envelope: The incoming bus Envelope (task.resume or clarification.response).
        model: LLM adapter implementing IConciergeModelPort.
        ss: SessionStateManager instance.
        bus: IBus instance for publishing response events.
        tool_dispatcher: Back ToolDispatcher for tool execution.
        fsm_state: FSM controller for token extraction (legacy fallback).
        cancel_token: Per-task CancellationToken (M3 E3.2.5). If None,
            extracted from fsm_state.cancel_handler.get_token(task_id).

    Returns:
        ReactResult from the resumed ReAct loop execution.
    """
    trace_id = envelope.cognitive_trace_id
    payload = _parse_payload(envelope)
    task_id = payload.get("task_id", "")
    resolution = payload.get("resolution", {})
    resume_context = payload.get("resume_context", {})

    # If this is a clarification.response, map to resolution structure
    if not resolution and payload.get("response"):
        resolution = {"additional_info": payload["response"]}
    if not resolution and payload.get("answer"):
        resolution = {"additional_info": payload["answer"]}

    logger.info(
        "back_resume_handler: task_id=%s trace=%s",
        task_id,
        trace_id[:8] if trace_id else "",
    )

    # 1. Retrieve prior context
    # M3 E3.3.1 + 3.3.2 + M6 E6.2 (C08): SuspensionManager is the single
    # resume-context owner.  FSM enriches the resume envelope's payload
    # via SuspensionManager.pop_context.  If the payload lacks
    # ``resume_context`` (or ``resume_context`` lacks the required keys),
    # there is no recovery path here -- raise SuspensionResolutionNotFound
    # so the caller can re-emit the original HITL question to Front.
    original_task: dict[str, Any] = {}
    prior_messages: list[ModelMessage] = []

    if resume_context and (
        resume_context.get("original_task") or resume_context.get("react_history")
    ):
        original_task = resume_context.get("original_task", {})
        raw_history = resume_context.get("react_history", [])
        if isinstance(raw_history, list) and raw_history:
            prior_messages = _deserialize_messages(raw_history)
        logger.info(
            "back_resume_handler: using envelope-carried resume_context "
            "original_task_keys=%s prior_msgs=%d",
            list(original_task.keys())[:5] if original_task else [],
            len(prior_messages),
        )
    else:
        logger.warning(
            "back_resume_handler: no resume_context for task_id=%s "
            "-- raising SuspensionResolutionNotFound",
            task_id,
        )
        # Emit task_failed with the canonical error_code so observers
        # see a clean failure trail, then raise so the FSM can re-emit
        # the HITL question.
        env = build_task_failed(
            payload={
                "task_id": task_id,
                "reason": "suspension_resolution_not_found",
                "error_code": "SUSPENSION_RESOLUTION_NOT_FOUND",
            },
            parent_id=envelope.envelope_id,
        )
        bus.publish(env)
        raise SuspensionResolutionNotFound(task_id)

    tier = original_task.get("tier", "LOW")
    # P3.4c: Per-task tier rebind for the back dispatcher.
    tool_dispatcher = _maybe_rebind_back_dispatcher(tool_dispatcher, tier, bus)

    # 2. Re-read SS at resume time (may have changed during suspension)
    snapshot = _read_ss_snapshot(ss)
    logger.info(
        "back_resume_handler: SS re-read  beliefs_len=%d safety=%s prior_msgs=%d",
        len(snapshot["beliefs_prompt"]),
        snapshot["safety_band"],
        len(prior_messages),
    )

    # 3. Build system prompt (same as original dispatch, fresh SS)
    _back_cfg = get_config().actors.back
    original_budget = _back_cfg.max_iterations.get(tier, _back_cfg.max_iterations["LOW"])
    budget_hint = original_task.get("budget_hint")
    if budget_hint is not None:
        original_budget = _budget_to_iterations(budget_hint)

    system_prompt = build_back_prompt(
        task=original_task,
        beliefs=snapshot["beliefs_prompt"],
        referents=snapshot["referents"],
        task_state=snapshot["task_state_prompt"],
        task_artifacts=snapshot["task_artifacts_prompt"],
        safety_band=snapshot["safety_band"],
        persona_prefs=snapshot["persona_prefs"],
        max_tool_calls=original_budget,
    )

    # 4. Hydrate resolution into messages (copy to avoid mutation)
    messages = list(prior_messages)

    # Use structured resume instruction from ResumeContext when available
    # (built by FSM via build_resume_context in hitl_wiring.py)
    if resume_context and resume_context.get("instruction"):
        hil_type = resume_context.get("hil_type", "clarification")
        resume_instruction = (
            f"{resume_context['instruction']}\n" f"Resolution: {json.dumps(resolution, indent=2)}"
        )
        logger.info("back_resume_handler: using ResumeContext instruction hil_type=%s", hil_type)
    else:
        resume_instruction = (
            "The user has provided their answer to your question.\n"
            f"Resolution: {json.dumps(resolution, indent=2)}\n"
            "Resume from where you left off. Do NOT re-execute tools "
            "that already succeeded. Use your prior findings as starting state."
        )

    messages.append(
        ModelMessage(
            role="user",
            content=resume_instruction,
        )
    )

    # 5. Calculate remaining budget
    tools_already_called = len([m for m in prior_messages if m.role == "tool"])
    remaining_budget = max(original_budget - tools_already_called, 2)

    # 6. Select tools by tier
    tools = _filter_back_tools(tier)

    # Build output validator for resume (Epic 4.1)
    resume_validator = LLMOutputValidator(tools) if tools else None

    # 7. Build cancellation callback (M3 E3.2.3: per-task token)
    if cancel_token is None:
        cancel_token = _extract_cancel_token(fsm_state, task_id)
    cancellation_check = _build_cancellation_check(
        cancel_token=cancel_token,
        fsm_state=fsm_state,
    )

    # 8. Continue ReAct loop
    result = await react_loop(
        actor="back",
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        max_iterations=remaining_budget,
        model=model,
        tool_dispatcher=tool_dispatcher,
        on_text_response=_noop_text,
        cancellation_check=cancellation_check,
        trace_id=trace_id,
        scenario="task_resume",
        validator=resume_validator,
    )

    # 9. Emit result (same as back_handler)
    # M3 E3.3.4: Pass react history + original task for re-suspension
    # Phase P: Extract tool call summaries for MW persistence
    resume_call_summaries = [s.to_dict() for s in tool_dispatcher.get_call_summaries()]
    _emit_back_result(
        bus,
        envelope,
        task_id,
        result,
        react_history=messages,
        original_task=original_task,
        tool_call_summaries=resume_call_summaries,
    )

    # 10. M6 E6.2 (C07): legacy _clear_pending_context call removed --
    # SuspensionManager.cleanup_task is now the single owner.

    logger.info(
        "back_resume_handler complete: task_id=%s status=%s trace=%s",
        task_id,
        result.status,
        trace_id[:8] if trace_id else "",
    )

    return result


# =========================================================================
# back_cancel_handler -- Epic 7.4.3 (Cancellation)
# =========================================================================


def back_cancel_handler(
    envelope: Envelope,
    fsm_state: Any | None = None,
    cancel_token: CancellationToken | None = None,
) -> None:
    """Handle task cancellation via CancellationToken.

    M3 E3.2.4: Uses per-task CancellationToken.cancel() instead of
    setting raw fsm_state.cancellation_requested boolean. The ReAct loop
    checks the token's is_cancelled property between iterations.

    Falls back to legacy fsm_state attribute mutation if no token
    is available (backward compatibility).

    Args:
        envelope: The incoming bus Envelope (task.cancel).
        fsm_state: FSM controller for token extraction (legacy fallback).
        cancel_token: Per-task CancellationToken (M3 E3.2.5). If None,
            extracted from fsm_state.cancel_handler.get_token(task_id).
    """
    payload = _parse_payload(envelope)
    task_id = payload.get("task_id", "")

    logger.info("back_cancel_handler: cancelling task_id=%s", task_id)

    # M3 E3.2.4: Extract token if not provided
    if cancel_token is None:
        cancel_token = _extract_cancel_token(fsm_state, task_id)

    if cancel_token is not None:
        # Per-task cancellation via CancellationToken API
        if not cancel_token.is_cancelled:
            cancel_token.cancel(CancelReason.USER_REQUESTED)
            logger.info(
                "back_cancel_handler: token.cancel() called for task_id=%s",
                task_id,
            )
        else:
            logger.debug(
                "back_cancel_handler: token already cancelled for task_id=%s",
                task_id,
            )
        return

    # Legacy fallback: raw boolean on fsm_state
    if fsm_state is None:
        logger.warning(
            "back_cancel_handler: no fsm_state or token, cannot cancel task_id=%s", task_id
        )
        return

    if hasattr(fsm_state, "cancellation_requested"):
        fsm_state.cancellation_requested = True
        logger.debug("back_cancel_handler: legacy cancellation_requested flag set")

    if hasattr(fsm_state, "cancelled_tasks"):
        if isinstance(fsm_state.cancelled_tasks, set):
            fsm_state.cancelled_tasks.add(task_id)
            logger.debug(
                "back_cancel_handler: task_id=%s added to cancelled_tasks set (legacy)", task_id
            )


# =========================================================================
# route_back_envelope -- M3 E3.1.1 (Back Mailbox Topic Router)
# =========================================================================


async def route_back_envelope(
    envelope: Envelope,
    model: IConciergeModelPort,
    ss: Any,
    bus: IBus,
    tool_dispatcher: ToolDispatcher,
    fsm_state: Any | None = None,
    cancel_token: CancellationToken | None = None,
) -> ReactResult | None:
    """Central topic-based dispatcher for all back-bound envelopes.

    Routes an incoming Envelope to the correct back handler based on
    envelope.topic, replacing the previous pattern where callers had
    to select the handler themselves.

    M3 E3.2.5: Extracts per-task CancellationToken from the FSM's
    CancellationHandler and passes it to each handler.

    M7 E7.3.3: Accepts cancel_token from TaskLease (passed by
    coordinator via BackTopicRouter). If provided, this takes
    priority over the FSM-extracted token.

    Topic routing table:
      - task.dispatch.v1       -> back_handler
      - task.resume.v1         -> back_resume_handler
      - task.cancel.v1         -> back_cancel_handler  (sync, returns None)
      - clarification.response -> back_resume_handler

    Args:
        envelope: Incoming bus Envelope with .topic set.
        model: LLM port for ReAct execution.
        ss: SessionState snapshot.
        bus: IBus for event emission.
        tool_dispatcher: ToolDispatcher for ReAct tool calls.
        fsm_state: FSM controller for CancellationToken extraction.

    Returns:
        ReactResult from the handler, or None for cancel/unknown topics.
    """
    from k1.concierge.bus.topics import (
        TOPIC_CLARIFICATION_RESPONSE,
        TOPIC_TASK_CANCEL,
        TOPIC_TASK_DISPATCH,
        TOPIC_TASK_RESUME,
    )

    topic = getattr(envelope, "topic", None) or ""

    # M7 E7.3.3: Prefer cancel_token from TaskLease (passed by coordinator)
    # Fall back to FSM-extracted token (M3 E3.2.5)
    payload = _parse_payload(envelope)
    task_id = payload.get("task_id", "")
    if cancel_token is None:
        cancel_token = _extract_cancel_token(fsm_state, task_id)

    if topic == TOPIC_TASK_DISPATCH:
        logger.info("route_back_envelope: dispatching to back_handler topic=%s", topic)
        return await back_handler(
            envelope=envelope,
            model=model,
            ss=ss,
            bus=bus,
            tool_dispatcher=tool_dispatcher,
            fsm_state=fsm_state,
            cancel_token=cancel_token,
        )

    if topic == TOPIC_TASK_RESUME:
        logger.info("route_back_envelope: dispatching to back_resume_handler topic=%s", topic)
        return await back_resume_handler(
            envelope=envelope,
            model=model,
            ss=ss,
            bus=bus,
            tool_dispatcher=tool_dispatcher,
            fsm_state=fsm_state,
            cancel_token=cancel_token,
        )

    if topic == TOPIC_CLARIFICATION_RESPONSE:
        logger.info(
            "route_back_envelope: dispatching to back_resume_handler (clarification) topic=%s",
            topic,
        )
        return await back_resume_handler(
            envelope=envelope,
            model=model,
            ss=ss,
            bus=bus,
            tool_dispatcher=tool_dispatcher,
            fsm_state=fsm_state,
            cancel_token=cancel_token,
        )

    if topic == TOPIC_TASK_CANCEL:
        logger.info("route_back_envelope: dispatching to back_cancel_handler topic=%s", topic)
        back_cancel_handler(
            envelope=envelope,
            fsm_state=fsm_state,
            cancel_token=cancel_token,
        )
        return None

    # M3 E3.7.1: Publish dead-letter for unknown back topics instead of
    # silently dropping.  This makes unroutable envelopes observable via
    # the standard dead-letter consumer.
    from k1.concierge.bus.builders import build_dead_letter

    dl_payload = {
        "reason": "unknown_back_topic",
        "original_topic": topic,
        "envelope_id": getattr(envelope, "envelope_id", None),
        "task_id": task_id,
    }
    bus.publish(
        build_dead_letter(payload=dl_payload, parent_id=getattr(envelope, "envelope_id", 0))
    )
    logger.warning(
        "route_back_envelope: unknown topic=%r, envelope_id=%s -- dead-lettered",
        topic,
        getattr(envelope, "envelope_id", "?"),
    )
    return None


# =========================================================================
# Observability emission helpers -- Epic 7.3.1, 7.3.2
# =========================================================================


def emit_tool_started(
    bus: IBus,
    task_id: str,
    tool_name: str,
    args: dict[str, Any],
    parent_id: int = 0,
) -> Envelope:
    """Emit k1.tool.started.v1 on bus -- Epic 7.3.1.

    Args:
        bus: IBus instance.
        task_id: ID of the executing task.
        tool_name: Name of the tool being called.
        args: Tool call arguments (summarized for observability).
        parent_id: Parent envelope ID for causal chain.

    Returns:
        The published Envelope.
    """
    env = build_tool_started(
        payload={
            "task_id": task_id,
            "tool_name": tool_name,
            "args_summary": _summarize_args(args),
        },
        parent_id=parent_id,
    )
    bus.publish(env)
    logger.info("emit_tool_started: task_id=%s tool=%s", task_id, tool_name)
    return env


def emit_tool_completed(
    bus: IBus,
    task_id: str,
    tool_name: str,
    result: dict[str, Any],
    duration_ms: int,
    success: bool,
    parent_id: int = 0,
) -> Envelope:
    """Emit k1.tool.completed.v1 on bus -- Epic 7.3.2.

    Args:
        bus: IBus instance.
        task_id: ID of the executing task.
        tool_name: Name of the completed tool.
        result: Tool result dict (summarized for observability).
        duration_ms: Wall-clock execution time in milliseconds.
        success: Whether the tool call succeeded.
        parent_id: Parent envelope ID for causal chain.

    Returns:
        The published Envelope.
    """
    env = build_tool_completed(
        payload={
            "task_id": task_id,
            "tool_name": tool_name,
            "result_summary": _summarize_result(result),
            "duration_ms": duration_ms,
            "success": success,
        },
        parent_id=parent_id,
    )
    bus.publish(env)
    logger.info(
        "emit_tool_completed: task_id=%s tool=%s duration_ms=%d success=%s",
        task_id,
        tool_name,
        duration_ms,
        success,
    )
    return env


def emit_artifact_created(
    bus: IBus,
    task_id: str,
    artifact_type: str,
    data: dict[str, Any],
    parent_id: int = 0,
) -> Envelope:
    """Emit k1.session.artifact.created.v1 on bus -- Epic 7.3.6.

    Args:
        bus: IBus instance.
        task_id: ID of the task that created the artifact.
        artifact_type: Type of artifact (booking, appointment, document, etc.).
        data: Artifact-specific data.
        parent_id: Parent envelope ID for causal chain.

    Returns:
        The published Envelope.
    """
    env = build_artifact_created(
        payload={
            "task_id": task_id,
            "artifact_type": artifact_type,
            "data": data,
        },
        parent_id=parent_id,
    )
    bus.publish(env)
    logger.info("emit_artifact_created: task_id=%s type=%s", task_id, artifact_type)
    return env


# =========================================================================
# Internal helpers
# =========================================================================


async def _noop_text(text: str) -> None:
    """Back never emits text to user -- no-op callback."""
    pass


def _extract_cancel_token(
    fsm_state: Any,
    task_id: str,
) -> CancellationToken | None:
    """Extract a per-task CancellationToken from the FSM controller.

    M3 E3.2.2: The FSM's CancellationHandler creates a CancellationToken
    per dispatched task (via register_task). This helper retrieves it
    so Back handlers can use per-task cancellation instead of the old
    global boolean.

    Lookup chain:
      1. fsm_state.cancel_handler.get_token(task_id)  -- ConciergeController
      2. fsm_state._cancel_handler.get_token(task_id)  -- direct attribute
      3. None (fallback)

    Args:
        fsm_state: The FSM controller (or any object with cancel_handler).
        task_id: The task to look up.

    Returns:
        CancellationToken if found, else None.
    """
    if fsm_state is None or not task_id:
        return None

    # Try public property first (ConciergeController.cancel_handler)
    handler = getattr(fsm_state, "cancel_handler", None)
    if handler is None:
        # Try private attribute (direct access)
        handler = getattr(fsm_state, "_cancel_handler", None)
    if handler is not None and hasattr(handler, "get_token"):
        token = handler.get_token(task_id)
        if token is not None:
            logger.debug(
                "_extract_cancel_token: found token for task_id=%s cancelled=%s",
                task_id,
                token.is_cancelled,
            )
            return token

    logger.debug(
        "_extract_cancel_token: no token for task_id=%s (fsm_type=%s)",
        task_id,
        type(fsm_state).__name__,
    )
    return None


def _build_cancellation_check(
    cancel_token: CancellationToken | None = None,
    fsm_state: Any = None,
) -> Any:
    """Build cancellation check callback from CancellationToken.

    M3 E3.2.3: Uses per-task CancellationToken.is_cancelled instead of
    the old global fsm_state.cancellation_requested boolean.

    M6 E6.2.3: Cancellation callback is mandatory for Back dispatch.
    Without it, HITL timeout cannot cancel a resumed Back loop between
    iterations. A warning is emitted if no token is available.

    Falls back to fsm_state.cancellation_requested for backward compat
    if no token is provided.

    Args:
        cancel_token: Per-task CancellationToken (preferred, M3 E3.2).
        fsm_state: Legacy FSMTurnState (fallback only).

    Returns:
        An async callable that returns True if cancellation is requested.
    """
    if cancel_token is not None:

        async def _check_token() -> bool:
            return cancel_token.is_cancelled

        return _check_token

    # Legacy fallback: raw boolean on fsm_state
    if fsm_state is not None:

        async def _check_legacy() -> bool:
            return getattr(fsm_state, "cancellation_requested", False)

        return _check_legacy

    # M6 E6.2.3: No cancel token = no way to stop a resumed Back loop
    # between iterations on HITL timeout. Log a warning.
    logger.warning(
        "_build_cancellation_check: no CancellationToken or fsm_state "
        "provided — Back loop will not be interruptible by HITL timeout"
    )
    return _never_cancel
