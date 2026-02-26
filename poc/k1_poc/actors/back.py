"""
poc.k1_poc.actors.back -- Back Handler (Epic 7.1-7.4).

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
  - Use poc.k1_poc.bus.builders for envelope construction

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
import time
from typing import Any

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus
from poc.k1_poc.bus.builders import (
    build_artifact_created,
    build_task_complete,
    build_task_failed,
    build_task_suspended,
    build_tool_completed,
    build_tool_started,
)
from poc.k1_poc.config import get_config
from poc.k1_poc.llm.ports import IConciergeModelPort
from poc.k1_poc.llm.types import ModelMessage
from poc.k1_poc.llm.validator import LLMOutputValidator
from poc.k1_poc.prompt.back_prompt import build_back_prompt
from poc.k1_poc.react.history import build_chat_history_for_back
from poc.k1_poc.react.loop import ReactResult, react_loop
from poc.k1_poc.tools.dispatcher import ToolDispatcher
from poc.k1_poc.tools.schemas_back import BACK_TIER_ALLOWLISTS, BACK_TOOL_SCHEMAS

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

    LOW tier gets only 3 tools: recall_memory, invoke_capability, submit_result.
    MEDIUM/HIGH get all 6.
    """
    allowed = set(BACK_TIER_ALLOWLISTS.get(tier, BACK_TIER_ALLOWLISTS["LOW"]))
    return [t for t in BACK_TOOL_SCHEMAS if t.name in allowed]


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


def _safe_get_section(ss: Any, name: str) -> Any:
    """Get a section from SessionStateManager, returning None on error."""
    try:
        return ss.get_section(name)
    except Exception:
        return None


def _read_ss_snapshot(ss: Any) -> dict[str, Any]:
    """Read selective SS snapshot for Back context.

    Back reads ONCE at task start. It does NOT re-read during ReAct iterations.

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

    def _to_prompt(section: Any) -> str:
        if section is None:
            return ""
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
        "beliefs_prompt": _to_prompt(beliefs),
        "referents": _get_referents(scoreboard),
        "task_state_prompt": _to_prompt(task_state),
        "task_artifacts_prompt": _to_prompt(task_artifacts),
        "safety_band": _get_safety_band(control),
        "history_entries": _get_history_entries(history),
        "persona_prefs": _get_persona_prefs(persona),
    }


# =========================================================================
# Envelope payload helper
# =========================================================================


def _parse_payload(envelope: Envelope) -> dict[str, Any]:
    """Safely parse JSON bytes payload from Envelope.

    Returns empty dict if payload is empty or invalid JSON.
    """
    if not envelope.payload:
        return {}
    try:
        return json.loads(envelope.payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


# =========================================================================
# Result emission helper (shared by back_handler and back_resume_handler)
# =========================================================================


def _emit_back_result(
    bus: IBus,
    envelope: Envelope,
    task_id: str,
    result: ReactResult,
) -> None:
    """Emit the appropriate bus event based on ReactResult status.

    Status mapping (V2 Section 16.4):
      complete         -> k1.orchestration.task.complete.v1
      suspended        -> k1.orchestration.task.suspended.v1
      cancelled        -> k1.orchestration.task.failed.v1
      budget_exhausted -> k1.orchestration.task.failed.v1
    """
    parent_id = envelope.envelope_id

    # Extract original task action from dispatch envelope for
    # downstream PRESENT mode scenario data
    original_task = _parse_payload(envelope)
    task_action = original_task.get("action", "")
    if not task_action:
        intents = original_task.get("intents")
        if isinstance(intents, list) and intents:
            task_action = intents[0].get("action", "")

    if result.status == "complete":
        data = result.data or {}
        env = build_task_complete(
            payload={
                "task_id": task_id,
                "action": task_action,
                "result_type": "complete",
                "final_answer": data.get("final_answer", ""),
                "results": data.get("results", []),
                "artifacts_created": data.get("artifacts_created", []),
            },
            parent_id=parent_id,
        )
        bus.publish(env)

    elif result.status == "suspended":
        data = result.data or {}
        env = build_task_suspended(
            payload={
                "task_id": task_id,
                "hil_type": data.get("hil_type", "clarification"),
                "question": data.get("question", ""),
                "options": data.get("options", []),
                "side_effects": data.get("side_effects", []),
                "timeout_s": get_config().actors.back.hitl_timeout_s,
            },
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
    model: IConciergeModelPort,
    ss: Any,
    bus: IBus,
    tool_dispatcher: ToolDispatcher,
    fsm_state: Any | None = None,
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
        fsm_state: FSMTurnState for cancellation checking. If None,
            cancellation is never triggered.

    Returns:
        ReactResult from the ReAct loop execution.
    """
    trace_id = envelope.cognitive_trace_id
    task = _parse_payload(envelope)
    task_id = task.get("task_id", "")
    tier = task.get("tier", "LOW")

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

    # 5. Build cancellation callback
    cancellation_check = _build_cancellation_check(fsm_state)

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

    # 7. Emit result to bus (Epic 7.3)
    _emit_back_result(bus, envelope, task_id, result)

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
    model: IConciergeModelPort,
    ss: Any,
    bus: IBus,
    tool_dispatcher: ToolDispatcher,
    fsm_state: Any | None = None,
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
        fsm_state: FSMTurnState with pending_context for the suspended task.

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

    # 1. Retrieve prior context from FSMTurnState
    pending = _get_pending_context(fsm_state, task_id)
    if not pending:
        env = build_task_failed(
            payload={
                "task_id": task_id,
                "reason": "no_pending_context",
                "error_code": "NO_PENDING_CONTEXT",
            },
            parent_id=envelope.envelope_id,
        )
        bus.publish(env)
        return ReactResult(status="cancelled", data={"reason": "no_pending_context"})

    original_task = pending.get("original_task", {})
    prior_messages = pending.get("prior_messages", [])
    tier = original_task.get("tier", "LOW")

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

    # 7. Build cancellation callback
    cancellation_check = _build_cancellation_check(fsm_state)

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
    _emit_back_result(bus, envelope, task_id, result)

    # 10. Clean up pending context
    _clear_pending_context(fsm_state, task_id)

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
) -> None:
    """Handle task cancellation by setting the FSM cancellation flag.

    When task.cancel.v1 arrives, sets fsm_state.cancellation_requested = True
    and records the task_id in fsm_state.cancelled_tasks. The ReAct loop
    checks cancellation_check() between iterations and exits cleanly.

    Args:
        envelope: The incoming bus Envelope (task.cancel).
        fsm_state: FSMTurnState for setting cancellation flag.
    """
    if fsm_state is None:
        logger.warning("back_cancel_handler: no fsm_state provided, cannot cancel")
        return

    payload = _parse_payload(envelope)
    task_id = payload.get("task_id", "")

    logger.info("back_cancel_handler: cancelling task_id=%s", task_id)

    # Set the cancellation flag (react_loop checks this between iterations)
    if hasattr(fsm_state, "cancellation_requested"):
        fsm_state.cancellation_requested = True
        logger.debug("back_cancel_handler: cancellation_requested flag set")

    # Record cancelled task_id
    if hasattr(fsm_state, "cancelled_tasks"):
        if isinstance(fsm_state.cancelled_tasks, set):
            fsm_state.cancelled_tasks.add(task_id)
            logger.debug("back_cancel_handler: task_id=%s added to cancelled_tasks set", task_id)


# =========================================================================
# store_pending_context -- Epic 7.4.2 (Suspend context storage)
# =========================================================================


def store_pending_context(
    fsm_state: Any,
    task_id: str,
    original_task: dict[str, Any],
    prior_messages: list[ModelMessage],
) -> None:
    """Store ReAct message history on suspend for later resume.

    Called when Back suspends (submit_result returns status="suspended").
    Stores original_task + prior_messages in fsm_state.pending_context
    for retrieval by back_resume_handler.

    Args:
        fsm_state: FSMTurnState with pending_context dict.
        task_id: ID of the suspended task.
        original_task: The full TaskDispatch payload.
        prior_messages: Complete ReAct message list before suspend.
    """
    if fsm_state is None:
        return

    if not hasattr(fsm_state, "pending_context"):
        return

    suspension_count = 0
    existing = fsm_state.pending_context.get(task_id)
    if existing:
        suspension_count = existing.get("suspension_count", 0)

    fsm_state.pending_context[task_id] = {
        "original_task": original_task,
        "prior_messages": prior_messages,
        "suspended_at": time.monotonic(),
        "suspension_count": suspension_count + 1,
    }


# =========================================================================
# Event subscription wiring -- Epic 7.2
# =========================================================================


def subscribe_back_events(
    bus: IBus,
    handler_fn: Any,
) -> list[Any]:
    """Subscribe to all Back-relevant bus topics.

    Wires up the Back handler to receive events from the bus.
    The 4 primary subscriptions per V2 Section 6.2:
      - k1.orchestration.task.dispatch.v1
      - k1.orchestration.task.cancel.v1
      - k1.orchestration.task.resume.v1
      - k1.orchestration.clarification.response.v1

    Args:
        bus: IBus instance.
        handler_fn: Callable[[Envelope], None] handler for each topic.

    Returns:
        List of SubscriptionHandle objects from bus.subscribe().
    """
    from poc.k1_poc.bus.topics import (
        TOPIC_CLARIFICATION_RESPONSE,
        TOPIC_TASK_CANCEL,
        TOPIC_TASK_DISPATCH,
        TOPIC_TASK_RESUME,
    )

    topics = [
        TOPIC_TASK_DISPATCH,
        TOPIC_TASK_CANCEL,
        TOPIC_TASK_RESUME,
        TOPIC_CLARIFICATION_RESPONSE,
    ]

    logger.info(
        "subscribe_back_events: wiring %d topics to back handler",
        len(topics),
    )
    handles = []
    for topic in topics:
        handle = bus.subscribe(topic, handler_fn)
        handles.append(handle)
        logger.debug("  subscribed back -> %s", topic)
    logger.info("subscribe_back_events: complete (%d handles)", len(handles))
    return handles


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


def _build_cancellation_check(fsm_state: Any) -> Any:
    """Build cancellation check callback from FSMTurnState.

    Returns an async callable that checks fsm_state.cancellation_requested.
    If no fsm_state, returns a lambda that always returns False.
    """
    if fsm_state is None:
        return _never_cancel

    async def _check() -> bool:
        return getattr(fsm_state, "cancellation_requested", False)

    return _check


async def _never_cancel() -> bool:
    """Always returns False -- no cancellation."""
    return False


def _get_pending_context(fsm_state: Any, task_id: str) -> dict[str, Any] | None:
    """Retrieve pending context for a suspended task from FSMTurnState."""
    if fsm_state is None:
        return None
    if not hasattr(fsm_state, "pending_context"):
        return None
    return fsm_state.pending_context.get(task_id)


def _clear_pending_context(fsm_state: Any, task_id: str) -> None:
    """Remove pending context after resume completes."""
    if fsm_state is None:
        return
    if not hasattr(fsm_state, "pending_context"):
        return
    fsm_state.pending_context.pop(task_id, None)
