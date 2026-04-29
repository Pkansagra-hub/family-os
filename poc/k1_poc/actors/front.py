"""
poc.k1_poc.actors.front -- Front Handler (Epic 6.1-6.6).

The front_handler is the entry point invoked by the FSM when an event
targets the Front LLM. It:
  1. Resolves the PromptMode from FSM state + event + SS signals
  2. Computes the affect band from affective_now
  3. Extracts mode-specific scenario data from the envelope + SS
  4. Assembles the prompt via DynamicPromptBuilder
  5. Runs the ReAct loop
  6. Emits bus events (ack, task dispatch, final response)
  7. Separates cancel vs normal dispatches (6.5)
  8. Auto-emits task.resume after HITL_RESOLVE (6.4.4)

V2 Design Ref: Section 6.1, 8.7, 8.10 (Front Handler Wiring)

Bus API notes (actual Envelope implementation):
  - Envelope.payload is bytes (JSON serialized via builders)
  - Envelope.envelope_id is int (not 'id')
  - Envelope.cognitive_trace_id is str (not 'trace_id')
  - IBus.publish(envelope) -- not emit()
  - Use poc.k1_poc.bus.builders for envelope construction
"""

from __future__ import annotations

import json
import logging
from typing import Any

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus

# Shared actor utilities (M3 E3.5)
from poc.k1_poc.actors.shared import never_cancel as _never_cancel
from poc.k1_poc.actors.shared import parse_envelope_payload as _parse_payload
from poc.k1_poc.actors.shared import safe_get_section as _safe_get_section
from poc.k1_poc.bus.builders import (
    build_final_response,
    build_response_stream,
    build_task_cancel,
    build_task_dispatch,
    build_task_resume,
)
from poc.k1_poc.config import get_config
from poc.k1_poc.llm.hub_types import IModelHubPort
from poc.k1_poc.llm.types import ModelMessage
from poc.k1_poc.llm.validator import LLMOutputValidator
from poc.k1_poc.prompt.affect import compute_affect_band
from poc.k1_poc.prompt.builder import DynamicPromptBuilder
from poc.k1_poc.prompt.mode import PromptMode, determine_mode
from poc.k1_poc.react.loop import ReactResult, react_loop
from poc.k1_poc.task.complexity import ComplexityTier, budget_for_tier
from poc.k1_poc.tools.dispatcher import ToolDispatcher

logger = logging.getLogger(__name__)

# Reasoning-leak detection patterns.  Flash Lite (and other non-thinking
# models) sometimes prefix their response text with chain-of-thought
# reasoning that should never reach the user.  These patterns detect
# common prefixes so _strip_leaked_reasoning can remove them.
import re

_REASONING_PREFIXES = re.compile(
    r"^("
    # "The user is asking..." / "The user's request..."
    r"The (?:user|previous turn|current context)\b.+?"
    # "I will use the X tool..." / "I need to..."
    r"|I (?:will|need to|should|am going to)\b.+?"
    # "Based on the memory recall..." / "Based on the results..."
    r"|Based on\b.+?"
    # "To proceed,..." / "Therefore,..."
    r"|(?:To proceed|Therefore|However|First|Let me)\b.+?" r")"
    # Stop at a clear pivot to user-facing text
    r"(?=\n[A-Z]|\n\n)",
    re.DOTALL,
)


def _strip_leaked_reasoning(text: str) -> str:
    """Remove chain-of-thought reasoning leaked into the response text.

    Models without a dedicated thinking mode (e.g. gemini-2.5-flash-lite)
    sometimes prefix the user-facing response with internal reasoning.
    This function detects and strips such prefixes so only the clean
    user-facing message reaches the renderer.

    Heuristic: If the text contains two or more paragraph breaks, and
    the early paragraphs match reasoning patterns while the final
    paragraph(s) look like a direct user response, keep only the final
    part.  If unsure, returns the original text unchanged.
    """
    if not text or "\n" not in text:
        return text

    # Split into paragraphs (double-newline or single-newline blocks)
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) < 2:
        return text

    # Walk paragraphs from the end to find where user-facing text begins.
    # Reasoning paragraphs typically start with meta-language about the
    # user, tools, or the model's own process.
    reasoning_markers = (
        "The user",
        "The previous turn",
        "The current context",
        "I will use",
        "I need to",
        "I should",
        "I am going to",
        "Based on",
        "To proceed",
        "Therefore,",
        "However,",
        "First,",
        "Let me",
    )

    # Find the first paragraph that does NOT start with a reasoning marker
    # scanning from the end (most reliable: last paragraph is the response)
    first_clean = len(paragraphs)
    for i in range(len(paragraphs) - 1, -1, -1):
        p = paragraphs[i]
        is_reasoning = any(p.startswith(m) for m in reasoning_markers)
        if is_reasoning:
            break
        first_clean = i

    if first_clean == 0:
        # Nothing detected as reasoning -- return original
        return text
    if first_clean >= len(paragraphs):
        # Everything is reasoning? Return original to be safe
        return text

    clean = "\n\n".join(paragraphs[first_clean:])
    if clean:
        stripped_chars = len(text) - len(clean)
        if stripped_chars > 0:
            logger.info(
                "front_handler: stripped %d chars of leaked reasoning from response",
                stripped_chars,
            )
        return clean
    return text


# Patterns matching raw system/HIL blocks that LLMs sometimes pass through
# instead of rephrasing.  Covers:
#   [HIL Request] Type: ... Question: ... Options: ... Side effects: ...
#   Note: The generate_story task is suspended because ...
#   == WORKER NEEDS USER INPUT ==  (scenario template echoed verbatim)
_SYSTEM_BLOCK_RE = re.compile(
    r"(?:"
    # [HIL Request] block (may span multiple lines)
    r"\[HIL\s*Request\][^\n]*(?:\n(?:Type|Question|Options|Side\s*effects)[^\n]*)*" r"|"
    # Note about task suspension
    r"Note:\s*The\s+\S+\s+task\s+is\s+suspended\b[^\n]*" r"|"
    # Echoed scenario template header
    r"==\s*WORKER NEEDS USER INPUT\s*==[^\n]*" r")",
    re.IGNORECASE,
)


def _strip_leaked_system_blocks(text: str) -> str:
    """Remove raw HIL/system blocks that leaked into the response text.

    LLMs in HITL_RELAY mode sometimes pass through structured data from
    the scenario template instead of rephrasing it naturally.  This
    function strips those blocks so only conversational text remains.
    """
    if not text:
        return text
    cleaned = _SYSTEM_BLOCK_RE.sub("", text)
    # Collapse runs of blank lines left by removed blocks
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if cleaned != text.strip():
        removed = len(text) - len(cleaned)
        logger.info(
            "front_handler: stripped %d chars of leaked system blocks from response",
            removed,
        )
    return cleaned if cleaned else text


# =========================================================================
# _parse_routing_metadata -- M5 E5.3.3
# =========================================================================


def _parse_routing_metadata(envelope: Envelope) -> dict[str, Any] | None:
    """Extract routing_metadata from enriched envelope payload.

    M5 E5.3.2 enriches the envelope payload with an ``routing_metadata``
    key before delivering to Front.  This helper safely extracts it so
    ``determine_mode()`` can receive it as a kwarg.

    Returns:
        The routing_metadata dict if present, else None.
    """
    try:
        payload = _parse_payload(envelope)
        return payload.get("routing_metadata")
    except Exception:
        return None


# =========================================================================
# _extract_scenario_data -- V2 Section 16.3, ITEM #9
# =========================================================================


def _extract_scenario_data(
    mode: PromptMode,
    envelope: Envelope,
    ss: Any,
) -> dict[str, Any]:
    """Extract mode-specific payload data from envelope and SS.

    Each mode needs different payload fields to populate its scenario
    data template. Returns a dict consumed by DynamicPromptBuilder.

    Args:
        mode: The resolved PromptMode.
        envelope: The incoming bus Envelope (payload is bytes).
        ss: SessionStateManager instance (duck typed for section access).

    Returns:
        Dict with mode-specific keys for prompt injection.
    """
    payload = _parse_payload(envelope)

    if mode == PromptMode.PRESENT:
        return {
            "task_description": payload.get("action", ""),
            "task_result_summary": payload.get("final_answer", ""),
            "artifacts": payload.get("artifacts_created", []),
            "completed_before_cancel": payload.get("completed_before_cancel", False),
            "results": payload.get("results", []),
            "tool_history": payload.get("tool_history", []),
        }

    if mode == PromptMode.WEAVE:
        payload_results = payload.get("results")
        if isinstance(payload_results, list):
            pending = payload_results
        else:
            control = _safe_get_section(ss, "control")
            pending = getattr(control, "pending_results", None) or []

        payload_count = payload.get("count")
        result_count = payload_count if isinstance(payload_count, int) else len(pending)

        # M8 E8.5.5: Check if this is a digest payload
        if isinstance(payload_results, list) and len(payload_results) == 1:
            first = payload_results[0]
            if isinstance(first, dict) and first.get("is_digest"):
                narrative = _safe_get_section(ss, "narrative_active")
                thread_name = payload.get("current_thread", "")
                if not thread_name and narrative and hasattr(narrative, "get_active_thread_name"):
                    thread_name = narrative.get_active_thread_name() or ""
                # M8 E8.5.6: Emotional context for digest
                affect_dict = _get_affect_dict(ss)
                emotional_context = _build_emotional_context(affect_dict)
                return {
                    "result_count": first.get("digest_count", 0),
                    "results_summary": first.get("digest_summary", ""),
                    "current_thread": thread_name,
                    "urgency_label": "Summary -- present as a brief update",
                    "emotional_context": emotional_context,
                }

        payload_summary = payload.get("results_summary")
        if isinstance(payload_summary, str) and payload_summary:
            results_summary = payload_summary
        else:
            # FSMTurnState.enqueue_result wraps the task.complete payload
            # under a "result" key.  Unwrap it so we can read "action"
            # and "final_answer" regardless of nesting.
            summary_lines: list[str] = []
            for r in pending:
                inner = r.get("result", r) if isinstance(r, dict) else r
                action = inner.get("action", "") if isinstance(inner, dict) else ""
                final_answer = inner.get("final_answer", "") if isinstance(inner, dict) else ""
                summary_lines.append(f"- {action}: {final_answer}")

                # Include structured results data (e.g. web search results)
                # so Front can present actual names, URLs, snippets to user.
                inner_results = inner.get("results", []) if isinstance(inner, dict) else []
                if isinstance(inner_results, list):
                    for item in inner_results[:10]:
                        if isinstance(item, dict):
                            # Web search result: {title, url, snippet}
                            title = item.get("title") or item.get("name", "")
                            url = item.get("url") or item.get("href", "")
                            snippet = item.get("snippet") or item.get("body", "")
                            if title:
                                line = f"  * {title}"
                                if url:
                                    line += f" -- {url}"
                                if snippet:
                                    line += f"\n    {snippet[:120]}"
                                summary_lines.append(line)

            results_summary = "\n".join(summary_lines)

        narrative = _safe_get_section(ss, "narrative_active")
        thread_name = payload.get("current_thread", "")
        if not thread_name and narrative and hasattr(narrative, "get_active_thread_name"):
            thread_name = narrative.get_active_thread_name() or ""

        # M8 E8.5.6: Urgency label from result metadata
        has_critical = any(
            (r.get("result", r) if isinstance(r, dict) else {}).get("urgency")
            in ("critical", "urgent")
            for r in pending
            if isinstance(r, dict)
        )
        if has_critical:
            urgency_label = (
                "URGENT -- present the time-critical result(s) prominently. "
                "The user needs to know about this immediately."
            )
        elif result_count >= 3:
            urgency_label = (
                "Summary -- these are routine updates. " "Present as a brief, natural aside."
            )
        else:
            urgency_label = "Informational -- weave this result lightly into the conversation."

        # M8 E8.5.6: Emotional context from affective_now
        affect_dict = _get_affect_dict(ss)
        emotional_context = _build_emotional_context(affect_dict)

        return {
            "result_count": result_count,
            "results_summary": results_summary,
            "current_thread": thread_name,
            "urgency_label": urgency_label,
            "emotional_context": emotional_context,
        }

    if mode == PromptMode.HITL_RELAY:
        return {
            "hil_type": payload.get("hil_type", ""),
            "hil_question": payload.get("question", ""),
            "hil_options": payload.get("options", []),
            "hil_side_effects": payload.get("side_effects", []),
        }

    if mode == PromptMode.HITL_RESOLVE:
        task_state = _safe_get_section(ss, "task_state")
        suspended = {}
        if task_state and hasattr(task_state, "get_all"):
            tasks = task_state.get_all()
            suspended = next(
                (t for t in tasks if t.get("status") == "SUSPENDED"),
                {},
            )
        return {
            "suspended_task_summary": suspended.get("action", ""),
            "original_question": (suspended.get("pending_hil") or {}).get("question", ""),
            "user_answer": payload.get("text", ""),
        }

    if mode == PromptMode.ERROR:
        return {
            "task_description": payload.get("action", ""),
            "failure_reason": payload.get("reason", ""),
            "error_code": payload.get("error_code", ""),
            "partial_results": payload.get("partial_results", []),
            "retries_attempted": payload.get("retries_attempted", 0),
        }

    if mode == PromptMode.CANCEL:
        task_id = payload.get("task_id", "")
        task_state = _safe_get_section(ss, "task_state")
        task = {}
        if task_state and hasattr(task_state, "get_by_id"):
            task = task_state.get_by_id(task_id) or {}
        return {
            "task_id": task_id,
            "task_action": task.get("action", ""),
            "task_status": task.get("status", ""),
        }

    if mode == PromptMode.CLARIFY_ASK:
        clarifications = _safe_get_section(ss, "clarifications")
        top_gap: dict[str, Any] = {}
        if clarifications and hasattr(clarifications, "get_top_blocking"):
            top_gap = clarifications.get_top_blocking() or {}
        return {
            "gap_field": top_gap.get("field", ""),
            "previous_question": top_gap.get("question", ""),
        }

    # STANDARD / INTERRUPT: inject family context + preloaded memories
    # so the LLM knows WHO it's talking to and can be proactive.
    # M8 E8.5.4: Deferred weave results injected via async_results_context.
    if mode in (PromptMode.STANDARD, PromptMode.INTERRUPT):
        context = _extract_family_context(ss)
        # M8 E8.5.4: Read async_results_context from payload (set by controller
        # from deferred results, or empty string if none).
        context["async_results_context"] = payload.get("async_results_context", "")
        return context

    return {}


# =========================================================================
# _extract_family_context -- Inject family context for STANDARD/INTERRUPT
# =========================================================================


def _extract_family_context(ss: Any) -> dict[str, Any]:
    """Build family context dict from persona section.

    Renders persona (family members, preferences, rules) into structured
    text injected via SCENARIO_DATA_TEMPLATES[STANDARD].

    Memories are NOT injected here -- the LLM must call recall_memory()
    proactively to retrieve relevant context. This teaches the model to
    be genuinely proactive rather than passively reading pre-injected data.
    """
    lines_family: list[str] = []
    active_member = "unknown"

    # --- Persona / family profile ---
    persona = _safe_get_section(ss, "persona")
    if persona is not None:
        # Try preferences dict first (where coordinator stores family data)
        prefs = getattr(persona, "_preferences", {})
        family_data = prefs.get("family", None)
        active_member = prefs.get("active_member", "unknown")
        session_cfg = prefs.get("session", {})

        if family_data:
            lines_family.append(f"Family: {family_data.get('family_name', '?')}")
            lines_family.append(f"Location: {family_data.get('location', '?')}")
            lines_family.append(f"Timezone: {family_data.get('timezone', '?')}")

            members = family_data.get("members", [])
            for m in members:
                name = m.get("name", "?")
                relation = m.get("relation", "?")
                age = m.get("age", "?")
                occupation = m.get("occupation", "")
                occ_str = f", {occupation}" if occupation else ""
                line = f"  - {name} ({relation}, {age}{occ_str})"
                member_prefs = m.get("preferences", {})
                if member_prefs:
                    pref_parts = []
                    for k, v in member_prefs.items():
                        if isinstance(v, dict):
                            pref_parts.append(f"{k}: {v}")
                        else:
                            pref_parts.append(f"{k}={v}")
                    if pref_parts:
                        line += f" [{', '.join(pref_parts[:4])}]"
                lines_family.append(line)

            # Family-level rules
            if family_data.get("dietary_restrictions"):
                lines_family.append(f"Dietary: {', '.join(family_data['dietary_restrictions'])}")
            if family_data.get("dinner_dnd_window"):
                lines_family.append(
                    f"DND: {family_data['dinner_dnd_window']} (dinner, no interrupts)"
                )
            if family_data.get("grocery_store"):
                lines_family.append(
                    f"Grocery: {family_data['grocery_store']}, "
                    f"order by {family_data.get('grocery_deadline', '?')}, "
                    f"delivery {family_data.get('grocery_delivery_window', '?')}"
                )

        if session_cfg:
            tone = session_cfg.get("tone", "warm")
            formality = session_cfg.get("formality", "casual")
            verbosity = session_cfg.get("verbosity", "concise")
            lines_family.append(f"Session style: {tone}, {formality}, {verbosity}")

    family_block = "\n".join(lines_family) if lines_family else "(no family data loaded)"

    return {
        "active_member": active_member,
        "family_context": family_block,
    }


# =========================================================================
# _build_resolution -- HITL_RESOLVE resolution (Epic 6.4.4)
# =========================================================================


def _build_resolution(scenario_data: dict[str, Any]) -> dict[str, Any]:
    """Build a resolution dict from HITL_RESOLVE scenario data.

    For M06 POC: extract resolution from the user answer text.
    Full implementation in M09 uses structured output or tool calls
    to parse the user's natural language answer into a typed resolution.

    Args:
        scenario_data: Dict from _extract_scenario_data(HITL_RESOLVE, ...).

    Returns:
        Resolution dict with keys: selected_option, target, approval,
        additional_info.
    """
    return {
        "selected_option": None,
        "target": None,
        "approval": None,
        "additional_info": scenario_data.get("user_answer"),
    }


# =========================================================================
# SS access helpers
# =========================================================================


def _get_affect_dict(ss: Any) -> dict[str, Any]:
    """Get affect dict from affective_now section, with fallback."""
    section = _safe_get_section(ss, "affective_now")
    if section is None:
        return {}
    if hasattr(section, "to_dict"):
        return section.to_dict()
    return {}


def _build_emotional_context(affect_dict: dict[str, Any]) -> str:
    """M8 E8.5.6: Build emotional context string from affect state.

    Used by _extract_scenario_data WEAVE mode to populate the
    {emotional_context} placeholder in the WEAVE scenario template.
    """
    if not affect_dict:
        return (
            "User affect is neutral. Standard weave -- respond to their "
            "topic first, then naturally transition to the result."
        )

    valence = affect_dict.get("valence", 0.0)
    band = affect_dict.get("band", affect_dict.get("affect_band", ""))

    if band == "crisis" or valence < -0.5:
        return (
            "The user is in emotional distress. Be extremely gentle. "
            "Acknowledge their state before presenting any result. "
            "If the result is not safety-critical, consider deferring it entirely. "
            "Example: 'I know this is a really hard time...'"
        )
    if valence < -0.3:
        return (
            "The user's mood is negative (sad, frustrated, or stressed). "
            "Be sensitive. Acknowledge what they're going through before "
            "transitioning to the result. Frame results positively: "
            "'One less thing to worry about -- your hotel is confirmed.'"
        )
    if band == "positive" or valence > 0.3:
        return (
            "The user is in a positive mood. Match their energy. "
            "Present results enthusiastically: 'Great news -- everything went through!'"
        )
    return (
        "User affect is neutral. Standard weave -- respond to their "
        "topic first, then naturally transition to the result."
    )


def _get_clarification_state(ss: Any) -> dict[str, Any]:
    """Build clarification_state dict from clarifications section."""
    section = _safe_get_section(ss, "clarifications")
    if section is None:
        return {"open_gaps": 0, "blocking_gaps": 0, "depth": 0}
    result: dict[str, Any] = {"open_gaps": 0, "blocking_gaps": 0, "depth": 0}
    if hasattr(section, "open_count"):
        result["open_gaps"] = section.open_count()
    if hasattr(section, "blocking_count"):
        result["blocking_gaps"] = section.blocking_count()
    if hasattr(section, "max_depth"):
        result["depth"] = section.max_depth()
    return result


def _get_task_state_dict(ss: Any) -> dict[str, Any]:
    """Build task_state dict from task_state section."""
    section = _safe_get_section(ss, "task_state")
    if section is None:
        return {"tasks": []}
    if hasattr(section, "get_all"):
        return {"tasks": section.get_all()}
    return {"tasks": []}


def _get_fsm_state(ss: Any) -> str:
    """Get FSM flow_state from control section, default from config."""
    _default = get_config().actors.front.default_fsm_state
    control = _safe_get_section(ss, "control")
    if control is None:
        return _default
    if hasattr(control, "flow_state"):
        return control.flow_state or _default
    return _default


def _get_history_active(ss: Any) -> list[Any]:
    """Get history_active entries as TypedHistoryEntry list for build_chat_history.

    Prefers get_typed_entries() which decomposes Turn objects into
    TypedHistoryEntry (with .entry_type / .text) that build_chat_history expects.
    Falls back to .entries or .get_all() for non-section objects.
    """
    section = _safe_get_section(ss, "history_active")
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


def _extract_current_user_text(mode: PromptMode, envelope: Envelope) -> str:
    """Extract current-turn user text from envelope payload when present.

    History and current input are distinct: history_active provides prior
    turns; current user text is appended as the active turn for this call.
    """
    payload = _parse_payload(envelope)
    text = (payload.get("text") or "").strip()
    if not text:
        return ""

    if mode in {
        PromptMode.STANDARD,
        PromptMode.CLARIFY_RESOLVE,
        PromptMode.HITL_RESOLVE,
        PromptMode.INTERRUPT,
    }:
        return text
    return ""


# =========================================================================
# front_handler -- V2 Section 6.1 Front Handler Wiring
# =========================================================================


async def front_handler(
    envelope: Envelope,
    model: IModelHubPort,
    ss: Any,
    bus: IBus,
    tool_dispatcher: ToolDispatcher,
    all_tool_schemas: list[Any] | None = None,
    fsm_state: str | None = None,
    opp_pipeline: Any | None = None,
) -> ReactResult:
    """Front handler with mode-driven prompt assembly.

    Called by FSM when an event targets Front. Determines the cognitive mode,
    assembles the prompt, and runs the ReAct loop. Emits bus events for ack,
    task dispatch, and final response.

    Args:
        envelope: The incoming bus Envelope triggering this invocation.
        model: LLM adapter implementing IModelHubPort.
        ss: SessionStateManager instance (duck typed for section access).
        bus: IBus instance for publishing response events.
        tool_dispatcher: Front ToolDispatcher for tool execution.
        all_tool_schemas: Full FRONT_TOOL_SCHEMAS list. If None, builder
            produces empty tool list.
        fsm_state: Explicit FSM state override. If None, reads from
            ss.control.flow_state.
        opp_pipeline: OppPipeline instance for OPP-3/6/7 prompt enrichment.

    Returns:
        ReactResult from the ReAct loop execution.
    """
    trace_id = envelope.cognitive_trace_id

    # 0. Guard: skip observability-only topics that should never trigger
    #    an LLM call. These are informational events (turn lifecycle,
    #    tool lifecycle) that must not be processed as STANDARD mode.
    #    Processing them causes an infinite loop:
    #      front -> FINAL_RESPONSE -> turn.completed -> front -> ...
    _OBSERVABILITY_TOPICS = frozenset(
        {
            "k1.session.turn.started.v1",
            "k1.session.turn.completed.v1",
            "k1.orchestration.tool.started.v1",
            "k1.orchestration.tool.completed.v1",
            "k1.session.state.updated.v1",
        }
    )
    if envelope.topic in _OBSERVABILITY_TOPICS:
        logger.info(
            "front_handler: SKIP observability topic=%s envelope_id=%d (no LLM call)",
            envelope.topic,
            envelope.envelope_id,
        )
        return ReactResult(
            status="skipped",
            text="",
            dispatched_tasks=[],
        )

    # 1. Determine FSM state (explicit or from SS)
    resolved_fsm_state = fsm_state or _get_fsm_state(ss)

    # 2. Determine mode from FSM state + context
    affect_dict = _get_affect_dict(ss)
    clarification_state = _get_clarification_state(ss)
    task_state_dict = _get_task_state_dict(ss)

    mode = determine_mode(
        fsm_state=resolved_fsm_state,
        envelope_topic=envelope.topic,
        clarification_state=clarification_state,
        task_state=task_state_dict,
        affect=affect_dict,
        routing_metadata=_parse_routing_metadata(envelope),
    )

    logger.info(
        "front_handler: mode=%s fsm=%s topic=%s trace=%s",
        mode.value,
        resolved_fsm_state,
        envelope.topic,
        trace_id[:8] if trace_id else "",
    )

    # 3. Compute affect band
    affect_band = compute_affect_band(affect_dict)

    # 4. Get clarification depth (for CLARIFY_ASK mode)
    clarify_depth = 0
    if mode == PromptMode.CLARIFY_ASK:
        clarifications = _safe_get_section(ss, "clarifications")
        if clarifications and hasattr(clarifications, "get_top_blocking"):
            top_gap = clarifications.get_top_blocking()
            if top_gap:
                clarify_depth = top_gap.get("depth", 0)

    # 5. Extract domain from Phase 1 classification (V2 Section 6.1 step 3)
    control_section = _safe_get_section(ss, "control")
    domain: str | None = None
    if control_section and hasattr(control_section, "get_domains"):
        _dc = control_section.get_domains()
        _pd = getattr(_dc, "primary_domain", None) or ""
        if _pd and _pd != "general":
            domain = _pd

    # 5a. Extract affect confidence and tier for conditional tool inclusion
    _front_cfg = get_config().actors.front
    affect_confidence: float = affect_dict.get("confidence", _front_cfg.default_affect_confidence)
    tier: str = _front_cfg.default_tier
    if control_section and hasattr(control_section, "tier"):
        tier = control_section.tier or _front_cfg.default_tier

    # 6. Build scenario data
    scenario_data = _extract_scenario_data(mode, envelope, ss)

    # 7. Build chat history
    from poc.k1_poc.react.history import build_chat_history

    history_active = _get_history_active(ss)
    # History window from SS_READ_CONFIGS
    from poc.k1_poc.prompt.builder import SS_READ_CONFIGS

    ss_configs = SS_READ_CONFIGS.get(mode, [])
    history_window = next(
        (c.history_window for c in ss_configs if c.section == "history_active"),
        _front_cfg.history_window_fallback,
    )
    messages = build_chat_history(history_active, window=history_window)

    # 7b. Add current-turn user input as an explicit user message.
    #     This is NOT history; it's the active query for this invocation.
    current_user_text = _extract_current_user_text(mode, envelope)
    if current_user_text:
        if not messages or not (
            messages[-1].role == "user" and messages[-1].content == current_user_text
        ):
            messages.append(ModelMessage(role="user", content=current_user_text))
            logger.info(
                "front_handler: appended current user turn to messages: %s",
                current_user_text[:60],
            )

    # 8. Assemble prompt via mode-driven builder
    # OPP-6/OPP-7: Enrich prompt with episodic compression + dynamic identity
    opp_enrichment = None
    if opp_pipeline is not None:
        try:
            history_active = _get_history_active(ss)
            turns_for_opp = (
                [{"role": e.get("role", ""), "text": e.get("text", "")} for e in history_active]
                if history_active
                else []
            )
            opp_enrichment = opp_pipeline.on_pre_prompt_build(
                turns=turns_for_opp,
                affect_band=affect_band,
                active_domains=[domain] if domain else [],
            )
            if opp_enrichment.compressed_context:
                scenario_data["compressed_context"] = opp_enrichment.compressed_context
                logger.info(
                    "front_handler: OPP-6 compressed %d episodes, %d recent turns kept",
                    opp_enrichment.episodes_used,
                    opp_enrichment.recent_turns_kept,
                )
            if opp_enrichment.identity_block:
                scenario_data["identity_block"] = opp_enrichment.identity_block
                logger.info("front_handler: OPP-7 dynamic identity block injected")
        except Exception:
            logger.warning("front_handler: OPP prompt enrichment failed", exc_info=True)

    builder = DynamicPromptBuilder()
    context = builder.build(
        mode=mode,
        affect_band=affect_band,
        history_messages=messages,
        all_tool_schemas=all_tool_schemas or [],
        scenario_data=scenario_data,
        clarify_depth=clarify_depth,
        domain=domain,
        affect_confidence=affect_confidence,
        tier=tier,
        ss=ss,
    )

    # 9. Run ReAct loop (Section 7)
    # OPP-3: Apply affect hard caps to LLM params before invocation
    opp_llm_overrides = None
    if opp_pipeline is not None:
        try:
            opp_llm_overrides = opp_pipeline.on_pre_llm_call(
                affect_band=affect_band,
            )
            if opp_llm_overrides.max_response_tokens is not None:
                logger.info(
                    "front_handler: OPP-3 affect caps band=%s max_tokens=%d vocab=%s",
                    opp_llm_overrides.affect_band_applied,
                    opp_llm_overrides.max_response_tokens,
                    opp_llm_overrides.vocabulary_tier,
                )
        except Exception:
            logger.warning("front_handler: OPP-3 affect caps failed", exc_info=True)

    # Synthetic envelopes (e.g. weave batch) bypass the bus and are not
    # tracked by the timing chain's causal buffer.  Using their envelope_id
    # as parent_id for bus-published events (like response.final) causes the
    # timing chain to buffer those events indefinitely waiting for a parent
    # delivery that will never happen.  Fall back to the envelope's own
    # parent_id which DID go through the bus.
    from poc.k1_poc.bus.builders import SYNTHETIC_ID_START

    if envelope.envelope_id >= SYNTHETIC_ID_START:
        parent_id = envelope.parent_id
    else:
        parent_id = envelope.envelope_id

    logger.info(
        "front_handler: LLM INPUT  prompt_len=%d messages=%d tools=%d max_iter=%d affect=%s",
        len(context.system_prompt),
        len(context.messages),
        len(context.tools),
        context.max_iterations,
        context.affect_band,
    )
    logger.debug(
        "front_handler: LLM INPUT tools=%s",
        [t.name for t in context.tools],
    )

    # Build output validator with the FULL tool schema set (Epic 4.1).
    # Uses all_tool_schemas (not mode-filtered context.tools) so valid Front
    # tools aren't rejected -- validator catches truly hallucinated names.
    validator = LLMOutputValidator(all_tool_schemas) if all_tool_schemas else None

    # Stream callback: forward thinking/text chunks to bus (Epic 2.1)
    _stream_chunk_idx = 0

    async def _on_stream(chunk) -> None:
        """Forward streaming chunks to bus as k1.response.stream.v1."""
        nonlocal _stream_chunk_idx
        if chunk.chunk_type == "thought_delta" and chunk.thought_text:
            env = build_response_stream(
                payload={
                    "text": chunk.thought_text,
                    "chunk_type": "thinking",
                    "chunk_index": _stream_chunk_idx,
                    "is_final": False,
                    "trace_id": trace_id,
                },
                parent_id=parent_id,
            )
            bus.publish(env)
            _stream_chunk_idx += 1
        elif chunk.chunk_type == "text_delta" and chunk.text:
            env = build_response_stream(
                payload={
                    "text": chunk.text,
                    "chunk_type": "text",
                    "chunk_index": _stream_chunk_idx,
                    "is_final": False,
                    "trace_id": trace_id,
                },
                parent_id=parent_id,
            )
            bus.publish(env)
            _stream_chunk_idx += 1

    async def _on_text_response(text: str) -> None:
        """Emit k1.response.final.v1 on bus -- Epic 6.3.3."""
        logger.info(
            "front_handler._on_text_response: publishing FINAL text=%s parent_id=%d",
            text[:60],
            parent_id,
        )
        env = build_final_response(
            payload={"text": text, "trace_id": trace_id},
            parent_id=parent_id,
        )
        bus.publish(env)
        logger.info(
            "front_handler._on_text_response: FINAL published (envelope_id=%d)", env.envelope_id
        )

    result = await react_loop(
        actor="front",
        system_prompt=context.system_prompt,
        messages=context.messages,
        tools=context.tools,
        max_iterations=context.max_iterations,
        model=model,
        tool_dispatcher=tool_dispatcher,
        on_text_response=_on_text_response,
        cancellation_check=_never_cancel,
        trace_id=trace_id,
        scenario=mode.value,
        validator=validator,
        on_stream=_on_stream,
    )

    logger.info(
        "front_handler: LLM OUTPUT  status=%s text_len=%d dispatched=%d tool_calls=%d trace=%s",
        result.status,
        len(result.text) if result.text else 0,
        len(result.dispatched_tasks),
        len(result.tool_calls) if hasattr(result, "tool_calls") else 0,
        trace_id[:8] if trace_id else "",
    )
    if result.text:
        logger.debug(
            "front_handler: LLM OUTPUT text_preview=%s",
            result.text[:120],
        )

    # 10. Post-loop: emit bus events in correct FSM order.
    #
    #     The react_loop no longer fires on_text_response directly.
    #     Instead, front_handler controls emission order:
    #       a) Cancel dispatches (URGENT)
    #       b) Normal task dispatches (INTERACTIVE) -- FSM: DISPATCHING -> COMPANIONING
    #       c) Final response -- FSM: DISPATCHING -> LISTENING (or COMPANIONING -> ...)
    #
    #     This prevents the FSM from transitioning to LISTENING before
    #     task dispatches arrive, which caused IllegalTransitionError.

    cancel_dispatches: list[dict[str, Any]] = []
    normal_dispatches: list[dict[str, Any]] = []

    for task_spec in result.dispatched_tasks:
        intents = task_spec.get("intents", [])
        if intents and intents[0].get("action") == "cancel":
            cancel_dispatches.append(task_spec)
        else:
            normal_dispatches.append(task_spec)

    # 10a. Emit cancels first (URGENT priority via build_task_cancel)
    for cancel_spec in cancel_dispatches:
        cancel_intents = cancel_spec.get("intents", [{}])
        target_task_id = cancel_intents[0].get("target_task_id", "") if cancel_intents else ""
        emit_task_cancel(
            bus=bus,
            task_id=target_task_id,
            reason="User requested cancellation",
            parent_id=parent_id,
            trace_id=trace_id,
        )

    # 10b. Emit normal dispatches BEFORE response.final
    #       Include tier so FSM/Back can route correctly (Epic 6.1).
    for task_spec in normal_dispatches:
        canonical_tier = tier if tier in {"LOW", "MEDIUM", "HIGH"} else "LOW"
        tier_enum = ComplexityTier(canonical_tier)
        env = build_task_dispatch(
            payload={
                **task_spec,
                "tier": canonical_tier,
                "budget_hint": budget_for_tier(tier_enum),
                "trace_id": trace_id,
            },
            parent_id=parent_id,
        )
        bus.publish(env)

    # 10c. Emit response.final AFTER all dispatches (correct FSM ordering)
    #      For STANDARD/PRESENT modes, emit stream chunks first (Epic 4.2).
    if result.text:
        clean_text = _strip_leaked_reasoning(result.text)
        clean_text = _strip_leaked_system_blocks(clean_text)
        if mode in (PromptMode.STANDARD, PromptMode.PRESENT):
            await _emit_streaming_response(
                bus=bus,
                text=clean_text,
                trace_id=trace_id,
                parent_id=parent_id,
            )
        await _on_text_response(clean_text)

    # 11. Post-loop: auto-emit task.resume after HITL_RESOLVE (Epic 6.4.4)
    if mode == PromptMode.HITL_RESOLVE:
        task_state_section = _safe_get_section(ss, "task_state")
        suspended_task: dict[str, Any] = {}
        if task_state_section and hasattr(task_state_section, "get_all"):
            tasks = task_state_section.get_all()
            suspended_task = next(
                (t for t in tasks if t.get("status") == "SUSPENDED"),
                {},
            )
        suspended_task_id = suspended_task.get("task_id", "")
        if suspended_task_id:
            resolution = _build_resolution(scenario_data)
            emit_task_resume(
                bus=bus,
                task_id=suspended_task_id,
                user_answer=json.dumps(resolution),
                resolution=resolution,
                parent_id=parent_id,
                trace_id=trace_id,
            )

    logger.info(
        "front_handler complete: status=%s dispatched=%d cancel=%d trace=%s",
        result.status,
        len(normal_dispatches),
        len(cancel_dispatches),
        trace_id[:8] if trace_id else "",
    )

    return result


# =========================================================================
# Event subscription wiring -- Epic 6.2
# =========================================================================


def subscribe_front_events(
    bus: IBus,
    handler_fn: Any,
) -> list[Any]:
    """Subscribe to all Front-relevant bus topics.

    Wires up the Front handler to receive events from the bus.
    Returns a list of subscription handles for cleanup.

    Args:
        bus: IBus instance.
        handler_fn: Callable[[Envelope], None] handler for each topic.

    Returns:
        List of SubscriptionHandle objects from bus.subscribe().
    """
    from poc.k1_poc.bus.topics import FRONT_SUBSCRIPTIONS

    logger.info(
        "subscribe_front_events: wiring %d topics to front handler",
        len(FRONT_SUBSCRIPTIONS),
    )
    handles = []
    for topic in FRONT_SUBSCRIPTIONS:
        handle = bus.subscribe(topic, handler_fn)
        handles.append(handle)
        logger.debug("  subscribed front -> %s", topic)
    logger.info("subscribe_front_events: complete (%d handles)", len(handles))
    return handles


# =========================================================================
# Cancel and resume emission helpers -- Epic 6.3.4, 6.3.5
# =========================================================================


def emit_task_cancel(
    bus: IBus,
    task_id: str,
    reason: str,
    parent_id: int = 0,
    trace_id: str = "",
) -> Envelope:
    """Emit k1.orchestration.task.cancel.v1 on bus -- Epic 6.3.4.

    Args:
        bus: IBus instance.
        task_id: ID of task to cancel.
        reason: Cancellation reason string.
        parent_id: Parent envelope ID for causal chain.
        trace_id: Cognitive trace ID.

    Returns:
        The published Envelope.
    """
    env = build_task_cancel(
        payload={"task_id": task_id, "reason": reason, "trace_id": trace_id},
        parent_id=parent_id,
    )
    bus.publish(env)
    logger.info("emit_task_cancel: task_id=%s reason=%s", task_id, reason)
    return env


def emit_task_resume(
    bus: IBus,
    task_id: str,
    user_answer: str,
    resolution: dict[str, Any] | None = None,
    parent_id: int = 0,
    trace_id: str = "",
) -> Envelope:
    """Emit k1.orchestration.task.resume.v1 on bus -- Epic 6.3.5.

    Args:
        bus: IBus instance.
        task_id: ID of task to resume.
        user_answer: The user's answer to the HITL question.
        parent_id: Parent envelope ID for causal chain.
        trace_id: Cognitive trace ID.

    Returns:
        The published Envelope.
    """
    resolved_payload = resolution
    if resolved_payload is None:
        try:
            parsed = json.loads(user_answer)
            resolved_payload = (
                parsed if isinstance(parsed, dict) else {"additional_info": user_answer}
            )
        except (json.JSONDecodeError, TypeError):
            resolved_payload = {"additional_info": user_answer}

    env = build_task_resume(
        payload={
            "task_id": task_id,
            "resolution": resolved_payload,
            "answer": user_answer,
            "trace_id": trace_id,
        },
        parent_id=parent_id,
    )
    bus.publish(env)
    logger.info("emit_task_resume: task_id=%s answer_len=%d", task_id, len(user_answer))
    return env


# =========================================================================
# Internal helpers
# =========================================================================


async def _emit_streaming_response(
    bus: IBus,
    text: str,
    trace_id: str,
    parent_id: int,
) -> None:
    """Emit text as stream chunks before final response (Epic 4.2).

    Splits text into sentence-level chunks and emits each as a
    k1.response.stream.v1 event. The caller emits response.final
    after this function completes.

    Uses sentence boundaries (. ! ? followed by space) for natural
    chunking. Falls back to ~80-char word-boundary chunks for long
    sentences. This keeps bus traffic to 5-15 envelopes per response
    instead of 80-100 word-level envelopes.

    Args:
        bus: IBus instance.
        text: The full response text to stream.
        trace_id: Cognitive trace ID.
        parent_id: Parent envelope ID for causal chain.
    """
    import re

    # Split on sentence boundaries (keep the delimiter with the chunk)
    raw_chunks = re.split(r"(?<=[.!?])\s+", text)

    # Further split any chunk > 120 chars at word boundaries
    chunks: list[str] = []
    for raw in raw_chunks:
        if len(raw) <= 120:
            chunks.append(raw)
        else:
            # Split long chunk at word boundaries (~80 chars)
            words = raw.split(" ")
            current = ""
            for w in words:
                candidate = f"{current} {w}" if current else w
                if len(candidate) > 80 and current:
                    chunks.append(current)
                    current = w
                else:
                    current = candidate
            if current:
                chunks.append(current)

    for i, chunk_text in enumerate(chunks):
        env = build_response_stream(
            payload={
                "text": chunk_text,
                "chunk_index": i,
                "is_final": i == len(chunks) - 1,
                "trace_id": trace_id,
            },
            parent_id=parent_id,
        )
        bus.publish(env)
