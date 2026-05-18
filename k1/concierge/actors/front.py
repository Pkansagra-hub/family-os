"""
k1.concierge.actors.front -- Front Handler (Epic 6.1-6.6).

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
  - Use k1.concierge.bus.builders for envelope construction
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus

# Shared actor utilities (M3 E3.5)
from k1.concierge.actors.frames import (
    BackResultFrame,
    HILResolutionFrame,
    WeavePresentationFrame,
    affect_dict_from_session,
    build_emotional_context,
)
from k1.concierge.actors.shared import never_cancel as _never_cancel
from k1.concierge.actors.shared import parse_envelope_payload as _parse_payload
from k1.concierge.actors.shared import safe_get_section as _safe_get_section
from k1.concierge.bus.builders import (
    build_final_response,
    build_hil_response,
    build_response_stream,
    build_task_cancel,
    build_task_dispatch,
    build_task_resume,
)
from k1.concierge.bus.topics import TOPIC_PROACTIVE_FILL
from k1.concierge.config import get_config
from k1.concierge.llm.types import ModelMessage
from k1.concierge.llm.validator import LLMOutputValidator
from k1.concierge.prompt.affect import compute_affect_band
from k1.concierge.prompt.builder import DynamicPromptBuilder
from k1.concierge.prompt.mode import PromptMode, determine_mode
from k1.concierge.react.loop import ReactResult, react_loop
from k1.concierge.task.complexity import ComplexityTier, budget_for_tier
from k1.concierge.tools.dispatcher import ToolDispatcher
from k1.model_hub.ports import IModelHubPort

logger = logging.getLogger(__name__)

_PROMPT_DUMP_DIR = Path(__file__).resolve().parents[3] / "data" / "prompt_dumps"


def _correlate_envelope(env: Envelope, source: Envelope, trace_id: str) -> Envelope:
    """Copy source correlation headers onto a Front-emitted envelope."""
    return replace(
        env,
        cognitive_trace_id=trace_id or source.cognitive_trace_id,
        session_id=source.session_id,
        request_id=source.request_id,
    )


def _bind_tool_context(tool_dispatcher: ToolDispatcher, *, trace_id: str, session_id: str) -> None:
    """Bind Front tool calls to the current envelope correlation scope."""
    ctx = getattr(tool_dispatcher, "ctx", None)
    if ctx is None:
        return
    ctx.cognitive_trace_id = trace_id or getattr(ctx, "cognitive_trace_id", "") or uuid.uuid4().hex
    ctx.session_id = session_id or getattr(ctx, "session_id", "")


# Detect common reasoning prefixes so they never leak to the user.
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


def _write_runtime_prompt_dump(
    *,
    envelope: Envelope,
    mode: PromptMode,
    context: Any,
    domain: str | None,
    tier: str,
    clarify_depth: int,
    trace_id: str,
) -> None:
    """Persist the exact Front prompt payload for postmortem debugging."""
    try:
        _PROMPT_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp_ms = int(time.time() * 1000)
        payload = {
            "timestamp_ms": timestamp_ms,
            "topic": envelope.topic,
            "envelope_id": envelope.envelope_id,
            "parent_id": envelope.parent_id,
            "trace_id": trace_id,
            "mode": mode.value,
            "domain": domain,
            "tier": tier,
            "clarify_depth": clarify_depth,
            "affect_band": context.affect_band,
            "max_iterations": context.max_iterations,
            "tool_names": [t.name for t in context.tools],
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                }
                for m in context.messages
            ],
            "system_prompt": context.system_prompt,
        }
        stem = f"front_prompt_env{envelope.envelope_id}_{timestamp_ms}"
        stamped_path = _PROMPT_DUMP_DIR / f"{stem}.json"
        latest_path = _PROMPT_DUMP_DIR / "front_prompt_latest.json"
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        stamped_path.write_text(serialized, encoding="utf-8")
        latest_path.write_text(serialized, encoding="utf-8")
        logger.info(
            "front_handler: prompt dump written envelope_id=%d file=%s latest=%s",
            envelope.envelope_id,
            stamped_path,
            latest_path,
        )
    except Exception:
        logger.warning("front_handler: prompt dump write failed", exc_info=True)


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


def _build_dispatch_ack(dispatches: list[dict[str, Any]]) -> str:
    """Return a deterministic in-progress acknowledgement for dispatched work."""
    if len(dispatches) > 1:
        return "I'm working on those now."
    return "I'm working on that now."


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


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_BACK_FRAME_JSON_RE = re.compile(
    r"\{[^{}]*(?:\"task_id\"|\"final_answer\"|\"result_type\"|"
    r"\"tool_call_summaries\")[\s\S]*?\}",
    re.IGNORECASE,
)
_TOOL_TRACE_LINE_RE = re.compile(
    r"(?im)^\s*(?:tool(?:_call| call|_history|_call_summaries)|iteration|scratchpad)\s*[:=].*$"
)


def _strip_leaked_back_frame(text: str) -> str:
    """Remove Back-internal frames, traces, and thinking blocks from final text."""
    if not text:
        return text
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _BACK_FRAME_JSON_RE.sub("", cleaned)
    cleaned = _TOOL_TRACE_LINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if cleaned != text.strip():
        logger.info(
            "front_handler: stripped %d chars of leaked Back frame/trace text",
            len(text) - len(cleaned),
        )
    return cleaned


_INTERNAL_FAILURE_MARKERS: tuple[str, ...] = (
    "tool invocation",
    "tool budget",
    "discover or invoke",
    "necessary capabilities",
    "validationerror",
    "traceback",
    "api error",
    "provider_error",
    "writecontext",
    "worker",
    "backend",
    "system failed",
)


def _looks_internal_failure_text(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _INTERNAL_FAILURE_MARKERS)


def _user_safe_failure_text(action: str = "") -> str:
    target = (action or "that task").strip() or "that task"
    return f"I couldn't finish {target}. Want me to try again?"


def _sanitize_result_summary(text: str) -> str:
    if not text or not _looks_internal_failure_text(text):
        return text
    return _user_safe_failure_text()


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
        if envelope.topic == TOPIC_PROACTIVE_FILL:
            message = str(payload.get("message") or payload.get("text") or "").strip()
            style = str(payload.get("style") or "informational")
            show_progress = bool(payload.get("show_progress", False))
            task_description = str(payload.get("action") or payload.get("task") or "status update")
            facts = [f"Fill candidate: {message}", f"Style: {style}"]
            if show_progress:
                facts.append("Show progress indicator: yes")
            return {
                "task_description": task_description,
                "task_result_summary": message,
                "task_facts": "\n".join(facts),
                "task_artifacts": "",
                "task_confidence": "high",
                "task_blockers": [],
                "suggested_next_action": "continue waiting for the background task",
                "semantic_guidance": "",
                "artifacts": [],
                "completed_before_cancel": False,
                "results": [],
                "tool_history": [],
                "proactive_fill_message": message,
                "proactive_fill_style": style,
                "proactive_fill_show_progress": show_progress,
            }
        frame_payload = payload.get("frame") if isinstance(payload.get("frame"), dict) else None
        frame = BackResultFrame.from_dict(frame_payload or payload)
        task_summary = frame.summary_text() if frame_payload else payload.get("final_answer", "")
        return {
            "task_description": payload.get("action", ""),
            "task_result_summary": task_summary,
            "task_facts": "\n".join(frame.fact_lines()),
            "task_artifacts": "\n".join(frame.artifact_lines()),
            "task_confidence": frame.confidence if frame.confidence is not None else "unknown",
            "task_blockers": frame.blockers,
            "suggested_next_action": frame.suggested_next_action,
            "semantic_guidance": frame.semantic_guidance_text(),
            "artifacts": frame.artifacts if frame_payload else payload.get("artifacts_created", []),
            "completed_before_cancel": payload.get("completed_before_cancel", False),
            "results": frame.facts if frame_payload else payload.get("results", []),
            "tool_history": (
                frame.tool_call_summaries
                if frame_payload
                else payload.get("tool_history", payload.get("tool_call_summaries", []))
            ),
        }

    if mode == PromptMode.WEAVE:
        frame = WeavePresentationFrame.from_payload_and_pending(payload, None, ss)
        data = frame.to_scenario_dict()
        data["results_summary"] = _sanitize_result_summary(str(data.get("results_summary") or ""))
        return data

    if mode == PromptMode.HITL_RELAY:
        # E1.M2.1: support new HILEnvelope shape; fall back to legacy
        # top-level keys if envelope not present.
        from k1.concierge.actors.front_hil_envelope import unwrap_hil_request_payload

        flat = unwrap_hil_request_payload(payload)
        return {
            "hil_type": flat.get("hil_type", ""),
            "hil_question": flat.get("question", ""),
            "hil_options": flat.get("options", []),
            "hil_side_effects": flat.get("side_effects", []),
            "_hil_envelope": flat.get("_hil_envelope"),
        }

    if mode == PromptMode.HITL_RESOLVE:
        from k1.concierge.actors.front_hil_envelope import (
            is_legacy_bridge_envelope,
            unwrap_hil_request_payload,
        )

        task_state = _safe_get_section(ss, "task_state")
        suspended = {}
        if task_state and hasattr(task_state, "get_all"):
            tasks = task_state.get_all()
            suspended = next(
                (t for t in tasks if _task_has_status(t, "SUSPENDED")),
                {},
            )
        pending_hil = _task_pending_hil_payload(suspended)
        incoming_envelope = pending_hil.get("envelope") or pending_hil.get("compat_hil_envelope")
        flat_hil = (
            unwrap_hil_request_payload(incoming_envelope)
            if isinstance(incoming_envelope, dict)
            else {}
        )
        inner_payload = (
            incoming_envelope.get("payload", {}) if isinstance(incoming_envelope, dict) else {}
        )
        legacy_bridge = bool(
            pending_hil.get("legacy_bridge") or is_legacy_bridge_envelope(incoming_envelope)
        )
        return {
            "suspended_task_summary": _task_field(suspended, "action", ""),
            "original_question": flat_hil.get("question") or pending_hil.get("question", ""),
            "user_answer": payload.get("text", ""),
            "_hil_envelope": incoming_envelope,
            "hil_type": (
                str(incoming_envelope.get("kind", ""))
                if isinstance(incoming_envelope, dict)
                else str(pending_hil.get("hil_type", ""))
            ),
            "hil_options": flat_hil.get("options")
            or pending_hil.get("options")
            or inner_payload.get("options")
            or inner_payload.get("proposed_alternatives")
            or [],
            "hil_side_effects": flat_hil.get("side_effects")
            or pending_hil.get("side_effects")
            or inner_payload.get("side_effects")
            or [],
            "pending_hil_id": (
                str(incoming_envelope.get("hil_request_id", ""))
                if isinstance(incoming_envelope, dict)
                else str(
                    pending_hil.get("pending_hil_id") or pending_hil.get("hil_request_id") or ""
                )
            ),
            "legacy_bridge": legacy_bridge,
            "task_id": _task_field(suspended, "task_id", ""),
        }

    if mode == PromptMode.ERROR:
        task_id = payload.get("task_id", "")
        task_state = _safe_get_section(ss, "task_state")
        task: Any = {}
        if task_id and task_state and hasattr(task_state, "get_by_id"):
            task = task_state.get_by_id(task_id) or {}
        task_description = payload.get("action") or _task_field(task, "action", "")
        return {
            "task_id": task_id,
            "task_description": task_description,
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

    M1: parse the user's answer into the resolution shape expected by
    front_hil_envelope.build_hil_response_envelope_dict while keeping
    legacy task.resume payloads backward-compatible.

    Args:
        scenario_data: Dict from _extract_scenario_data(HITL_RESOLVE, ...).

    Returns:
        Resolution dict with keys: selected_option, target, approval,
        additional_info.
    """
    return _build_resolution_frame(scenario_data).to_resolution_dict()


def _build_resolution_frame(scenario_data: dict[str, Any]) -> HILResolutionFrame:
    """Build a typed HIL resolution frame from HITL_RESOLVE scenario data."""
    from k1.concierge.protocols.hitl_flow import (
        parse_approval_resolution,
        parse_selection_resolution,
    )

    raw_answer = str(scenario_data.get("user_answer") or "")
    hil_type = _scenario_hil_kind(scenario_data)
    options = scenario_data.get("hil_options") or []
    task_id = str(scenario_data.get("task_id", "") or "")
    pending_hil_id = str(scenario_data.get("pending_hil_id", "") or "")
    legacy_bridge = bool(scenario_data.get("legacy_bridge", False))

    if hil_type == "approval":
        decision = _approval_decision_from_text(raw_answer)
        normalized = {"decision": decision}
        if decision == "modify":
            normalized["modifications"] = {"raw_user_text": raw_answer}
        parsed = parse_approval_resolution(normalized)
        approval = (
            True
            if parsed["decision"] == "approve"
            else False if parsed["decision"] == "reject" else None
        )
        return HILResolutionFrame(
            task_id=task_id,
            hil_request_id=pending_hil_id,
            kind=hil_type,
            raw_user_text=raw_answer,
            selected_option=parsed["decision"],
            approval=approval,
            additional_info=raw_answer,
            modifications=parsed.get("modifications"),
            legacy_bridge=legacy_bridge,
        )

    if hil_type == "capability_gate":
        decision = _approval_decision_from_text(raw_answer)
        approval = (
            True if decision == "approve" else False if decision in {"reject", "cancel"} else None
        )
        return HILResolutionFrame(
            task_id=task_id,
            hil_request_id=pending_hil_id,
            kind=hil_type,
            raw_user_text=raw_answer,
            selected_option=decision,
            approval=approval,
            additional_info=raw_answer,
            legacy_bridge=legacy_bridge,
        )

    if hil_type == "needs_human":
        matched = _match_hil_option(raw_answer, options)
        if matched is not None:
            selected = (
                matched.get("id")
                or matched.get("value")
                or matched.get("label")
                or matched.get("name")
            )
            parsed = parse_selection_resolution(
                {"selected_option": selected, "target": matched},
                options,
            )
            return HILResolutionFrame(
                task_id=task_id,
                hil_request_id=pending_hil_id,
                kind=hil_type,
                raw_user_text=raw_answer,
                selected_option=parsed.get("selected_option", selected),
                target=parsed.get("target", matched),
                additional_info=raw_answer,
                legacy_bridge=legacy_bridge,
            )
        return HILResolutionFrame(
            task_id=task_id,
            hil_request_id=pending_hil_id,
            kind=hil_type,
            raw_user_text=raw_answer,
            selected_option="answered",
            additional_info=raw_answer,
            legacy_bridge=legacy_bridge,
        )

    if hil_type == "override":
        matched = _match_hil_option(raw_answer, options)
        decision = _approval_decision_from_text(raw_answer)
        choice = (
            "fallback"
            if matched is not None
            else "abort" if decision in {"reject", "cancel"} else "override"
        )
        return HILResolutionFrame(
            task_id=task_id,
            hil_request_id=pending_hil_id,
            kind=hil_type,
            raw_user_text=raw_answer,
            selected_option=choice,
            target=matched,
            additional_info=raw_answer,
            legacy_bridge=legacy_bridge,
        )

    return HILResolutionFrame(
        task_id=task_id,
        hil_request_id=pending_hil_id,
        kind=hil_type or "clarification",
        raw_user_text=raw_answer,
        additional_info=raw_answer,
        legacy_bridge=legacy_bridge,
    )


def _scenario_hil_kind(scenario_data: dict[str, Any]) -> str:
    envelope = scenario_data.get("_hil_envelope")
    if isinstance(envelope, dict) and envelope.get("kind"):
        return str(envelope.get("kind") or "").lower()
    return str(scenario_data.get("hil_type") or "clarification").lower()


def _approval_decision_from_text(text: str) -> str:
    lowered = text.strip().lower().rstrip(".")
    if any(token in lowered for token in ("modify", "change", "adjust", "with ")):
        return "modify"
    if any(token in lowered for token in ("cancel", "abort", "stop")):
        return "cancel"
    if any(token in lowered for token in ("reject", "deny", "block", "no", "nope")):
        return "reject"
    if any(
        token in lowered
        for token in ("approve", "yes", "ok", "okay", "allow", "proceed", "go ahead", "sure")
    ):
        return "approve"
    return "approve" if lowered in {"y", "yeah", "yep"} else "cancel"


def _match_hil_option(answer: str, options: Any) -> dict[str, Any] | None:
    if not isinstance(options, list):
        return None
    lowered = answer.lower()
    for opt in options:
        if not isinstance(opt, dict):
            continue
        candidates = [
            opt.get("id"),
            opt.get("value"),
            opt.get("label"),
            opt.get("name"),
            opt.get("description"),
        ]
        if any(str(candidate).lower() in lowered for candidate in candidates if candidate):
            return opt
    return None


# =========================================================================
# SS access helpers
# =========================================================================


def _get_affect_dict(ss: Any) -> dict[str, Any]:
    """Get affect dict from affective_now section, with fallback."""
    return affect_dict_from_session(ss)


def _build_emotional_context(affect_dict: dict[str, Any]) -> str:
    """M8 E8.5.6: Build emotional context string from affect state.

    Used by _extract_scenario_data WEAVE mode to populate the
    {emotional_context} placeholder in the WEAVE scenario template.
    """
    return build_emotional_context(affect_dict)


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


def _task_field(task: Any, key: str, default: Any = None) -> Any:
    if isinstance(task, dict):
        return task.get(key, default)
    return getattr(task, key, default)


# Terminal task statuses -- task_state.py L74-89 contract.
_TASK_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


def _has_inflight_tasks(task_state_dict: dict[str, Any]) -> bool:
    """True when at least one task is NOT in a terminal status.

    M6.E3.I1 forwards this to OppPipeline.on_pre_prompt_build so that
    DynamicIdentityContext can select the EXECUTOR role for the active
    user when Back is busy.
    """
    for task in task_state_dict.get("tasks", []) or []:
        status = str(_task_field(task, "status", "") or "").lower()
        if status and status not in _TASK_TERMINAL_STATUSES:
            return True
    return False


def _history_entries_to_opp_turns(history_active: Any) -> list[dict[str, Any]]:
    """M6.E1.I3 thin wrapper -- delegates to the single owner module.

    See :mod:`k1.concierge.compression.turn_shape` for the canonical
    conversion. Kept here as a private alias so existing call sites in
    this file (and any future tests that import the private name) keep
    a stable surface.
    """
    from k1.concierge.compression.turn_shape import history_entries_to_opp_turns

    return history_entries_to_opp_turns(history_active)


def _derive_active_user(ss: Any) -> tuple[str, str]:
    """Return (active_user_id, active_user_name) from persona; empty fallbacks."""
    persona = _safe_get_section(ss, "persona")
    if persona is None:
        return ("", "")
    prefs = getattr(persona, "_preferences", {}) or {}
    active_member = str(prefs.get("active_member", "") or "")
    # No separate id field exists in persona -- reuse the display name as id.
    return (active_member, active_member)


def _task_has_status(task: Any, status: str) -> bool:
    return str(_task_field(task, "status", "")).upper() == status.upper()


def _task_pending_hil_payload(task: Any) -> dict[str, Any]:
    pending_hil_data = _task_field(task, "pending_hil_data")
    if isinstance(pending_hil_data, dict):
        return pending_hil_data
    pending_hil = _task_field(task, "pending_hil")
    if isinstance(pending_hil, dict):
        return pending_hil
    return {}


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


def _build_event_turn_text(mode: PromptMode, scenario_data: dict[str, Any]) -> str:
    """Build an explicit user turn for event-driven Front invocations.

    Event modes such as ERROR/PRESENT/WEAVE are triggered by bus events,
    not by a fresh user message. If the scenario exists only in the system
    prompt, some models can stop with no text because the chat transcript has
    no active turn to answer. This short message makes the event actionable
    while policy/details remain in the system prompt.
    """
    if mode == PromptMode.ERROR:
        task = str(scenario_data.get("task_description") or "that task")
        partial = scenario_data.get("partial_results") or []
        partial_hint = (
            "Mention the partial results that did succeed."
            if partial
            else "There are no partial results to present."
        )
        return (
            "A background task just failed. Tell the user in one concise, natural "
            f"message that {task} did not go through. Offer to try again or take "
            f"another path. {partial_hint} Do not expose internal reasons, error "
            "codes, stack traces, or system names."
        )

    if mode == PromptMode.PRESENT:
        if scenario_data.get("proactive_fill_message"):
            return (
                "A brief proactive status fill is ready. Use the fill facts as context, "
                "phrase it naturally in Front's voice, and do not expose internal payload fields."
            )
        task = str(scenario_data.get("task_description") or "the completed task")
        return (
            f"A user-relevant result is ready for {task}. Lead with what is now true "
            "or done, mention the concrete time/place/confirmation details, and "
            "preserve any semantic guidance or authority boundary in the scenario. "
            "Sound like you handled it, not like you are reading an operations log."
        )

    if mode == PromptMode.WEAVE:
        return (
            "Async results are ready. Answer the current conversation first, then "
            "bring in the concrete result summary naturally. Preserve any semantic "
            "guidance or authority boundary, and do not invent facts."
        )

    if mode == PromptMode.HITL_RELAY:
        question = str(scenario_data.get("hil_question") or "the worker's question")
        return (
            "A background task needs the user's input. Ask this question naturally "
            f"and briefly: {question}"
        )

    if mode == PromptMode.CANCEL:
        task = str(scenario_data.get("task_action") or scenario_data.get("task_id") or "the task")
        return f"Confirm the cancellation status for {task} in one concise message."

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
    self_model: Any = None,
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
    trace_id = (
        envelope.cognitive_trace_id or envelope.request_id or f"front-{uuid.uuid4().hex[:12]}"
    )
    _bind_tool_context(tool_dispatcher, trace_id=trace_id, session_id=envelope.session_id)

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
    if control_section and hasattr(control_section, "domain_context"):
        domain = (control_section.domain_context or {}).get("domain")

    # 5a. Extract affect confidence and tier for conditional tool inclusion
    _front_cfg = get_config().actors.front
    affect_confidence: float = affect_dict.get("confidence", _front_cfg.default_affect_confidence)
    tier: str = _front_cfg.default_tier
    if control_section and hasattr(control_section, "tier"):
        tier = control_section.tier or _front_cfg.default_tier

    # 6. Build scenario data
    scenario_data = _extract_scenario_data(mode, envelope, ss)
    if mode == PromptMode.WEAVE and (
        int(scenario_data.get("result_count", 0) or 0) == 0
        or not str(scenario_data.get("results_summary", "") or "").strip()
    ):
        logger.info("front_handler: WEAVE skipped because no concrete results are available")
        _ack_env = build_final_response(
            payload={"text": "", "is_ack": True},
            parent_id=envelope.envelope_id,
        )
        bus.publish(_ack_env)
        return ReactResult(status="skipped", text="", dispatched_tasks=[])

    # 7. Build chat history
    from k1.concierge.react.history import build_chat_history

    history_active = _get_history_active(ss)
    # History window from SS_READ_CONFIGS
    from k1.concierge.prompt.builder import SS_READ_CONFIGS

    ss_configs = SS_READ_CONFIGS.get(mode, [])
    history_window = next(
        (c.history_window for c in ss_configs if c.section == "history_active"),
        _front_cfg.history_window_fallback,
    )
    messages = build_chat_history(
        history_active,
        window=history_window,
        # M6 E6.2 (C10): In WEAVE mode the LLM needs to see prior weave
        # entries (deferred async results) so it can build on them
        # rather than repeating them.
        include_weave=(mode == PromptMode.WEAVE),
    )

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
    # OPP-6/OPP-7: Enrich prompt with episodic compression + dynamic identity.
    # M6.E1.I3 + M6.E3.I1: use canonical compressor turn shape; forward
    # has_inflight_tasks + active user fields so DynamicIdentityContext can
    # choose EXECUTOR/SUPPORTER/etc. correctly. ``scenario_data`` only carries
    # the two enriched strings as a transport channel -- DynamicPromptBuilder
    # consumes them explicitly and strips them before scenario formatting so
    # they never leak through the _format_scenario_data fallback.
    opp_enrichment = None
    if opp_pipeline is not None:
        try:
            history_active = _get_history_active(ss)
            turns_for_opp = _history_entries_to_opp_turns(history_active)
            task_state_dict = _get_task_state_dict(ss)
            has_inflight = _has_inflight_tasks(task_state_dict)
            active_user_id, active_user_name = _derive_active_user(ss)
            opp_enrichment = opp_pipeline.on_pre_prompt_build(
                turns=turns_for_opp,
                affect_band=affect_band,
                active_domains=[domain] if domain else [],
                active_user_id=active_user_id,
                active_user_name=active_user_name,
                has_inflight_tasks=has_inflight,
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
                logger.info(
                    "front_handler: OPP-7 dynamic identity block injected "
                    "(has_inflight_tasks=%s)",
                    has_inflight,
                )
        except Exception:
            logger.warning("front_handler: OPP prompt enrichment failed", exc_info=True)

    builder = DynamicPromptBuilder()

    # M5.E4: render selfmodel grounding capsule (constitution + actor
    # capabilities + family + freshness). When ``self_model`` is None
    # (no SelfModelHandle attached, e.g. enable_self_model=False) we
    # pass ``grounding_capsule=None`` and stage 9.5 is a no-op,
    # matching the pre-M4 baseline.
    grounding_capsule: Any = None
    if self_model is not None:
        try:
            grounding_capsule = self_model.render_capsule()
            logger.debug(
                "front_handler: render_capsule actor=%s capsule=%s self_block=%r",
                getattr(self_model, "actor_id", "?"),
                grounding_capsule is not None,
                bool(getattr(grounding_capsule, "self_block", "")) if grounding_capsule else False,
            )
        except Exception:
            logger.warning(
                "front_handler: render_capsule() failed; falling back to None",
                exc_info=True,
            )
            grounding_capsule = None

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
        grounding_capsule=grounding_capsule,
    )
    event_turn_text = _build_event_turn_text(mode, scenario_data)
    if event_turn_text:
        if not context.messages or context.messages[-1].content != event_turn_text:
            context.messages.append(ModelMessage(role="user", content=event_turn_text))
            logger.info(
                "front_handler: appended event turn for mode=%s: %s",
                mode.value,
                event_turn_text[:80],
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
    from k1.concierge.bus.builders import SYNTHETIC_ID_START

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
    _write_runtime_prompt_dump(
        envelope=envelope,
        mode=mode,
        context=context,
        domain=domain,
        tier=tier,
        clarify_depth=clarify_depth,
        trace_id=trace_id,
    )

    async def _publish_final_text(text: str) -> None:
        logger.info(
            "front_handler._on_text_response: publishing FINAL text=%s parent_id=%d",
            text[:60],
            parent_id,
        )
        env = build_final_response(
            payload={"text": text, "trace_id": trace_id},
            parent_id=parent_id,
        )
        env = _correlate_envelope(env, envelope, trace_id)
        bus.publish(env)
        logger.info(
            "front_handler._on_text_response: FINAL published (envelope_id=%d)", env.envelope_id
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
        if mode == PromptMode.HITL_RESOLVE:
            return
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
            env = _correlate_envelope(env, envelope, trace_id)
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
            env = _correlate_envelope(env, envelope, trace_id)
            bus.publish(env)
            _stream_chunk_idx += 1

    async def _on_text_response(text: str) -> None:
        """Emit k1.response.final.v1 on bus -- Epic 6.3.3."""
        await _publish_final_text(text)

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
    #
    #       Per-task tier (set by execute_dispatch_task from plan/multi-intent
    #       /depends_on signals) WINS over the front actor's session tier.
    #       Falling back to the session tier (and then LOW) preserves prior
    #       behaviour for tools that omit tier from their dispatch payload.
    for task_spec in normal_dispatches:
        per_task_tier = task_spec.get("tier")
        if per_task_tier in {"LOW", "MEDIUM", "HIGH"}:
            canonical_tier = per_task_tier
        elif tier in {"LOW", "MEDIUM", "HIGH"}:
            canonical_tier = tier
        else:
            canonical_tier = "LOW"
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
        env = _correlate_envelope(env, envelope, trace_id)
        bus.publish(env)

    # 10c. Emit response.final AFTER all dispatches (correct FSM ordering)
    #      For STANDARD/PRESENT modes, emit stream chunks first (Epic 4.2).
    _final_text = result.text or ""
    if mode == PromptMode.STANDARD and normal_dispatches:
        _final_text = _build_dispatch_ack(normal_dispatches)
        logger.info("front_handler: replaced post-dispatch text with deterministic ack")
    # WEAVE degenerate guard: if the LLM produced the generic fallback
    # ("Let me think about that for a moment.") during a WEAVE/proactive
    # delivery, replace it with a deterministic summary built from the
    # Back worker's final_answer.  This prevents useless "thinking" phrases
    # leaking to the user after routine task completions.
    if mode == PromptMode.WEAVE:
        _degenerate_fallback = get_config().react.front_degenerate_fallback
        if not _final_text or _final_text.strip() == _degenerate_fallback.strip():
            _weave_payload = _parse_payload(envelope)
            _weave_pending = _weave_payload.get("results") or []
            _weave_lines: list[str] = []
            for _r in _weave_pending:
                _inner = _r.get("result", _r) if isinstance(_r, dict) else {}
                _fa = _inner.get("final_answer", "") if isinstance(_inner, dict) else ""
                if _fa:
                    _action = (
                        str(_inner.get("action", "") or "") if isinstance(_inner, dict) else ""
                    )
                    _weave_lines.append(
                        _user_safe_failure_text(_action)
                        if _looks_internal_failure_text(_fa)
                        else _fa
                    )
            if _weave_lines:
                _final_text = " ".join(_weave_lines)
                logger.info(
                    "front_handler: WEAVE degenerate suppressed, "
                    "using Back final_answer (%d chars)",
                    len(_final_text),
                )
            else:
                # Nothing useful from Back either — suppress entirely.
                _final_text = ""
                logger.info("front_handler: WEAVE degenerate suppressed, no final_answer available")
    if mode == PromptMode.HITL_RELAY:
        _degenerate_fallback = get_config().react.front_degenerate_fallback
        if not _final_text or _final_text.strip() == _degenerate_fallback.strip():
            _question = str(scenario_data.get("hil_question") or "").strip()
            _final_text = _question if _question else ""
            logger.info("front_handler: HITL_RELAY degenerate replaced with deterministic prompt")
    if mode == PromptMode.HITL_RESOLVE and _final_text:
        _final_text = "Got it. I'll keep going."
        logger.info("front_handler: HITL_RESOLVE final text replaced with deterministic ack")
    if _final_text:
        clean_text = _strip_leaked_reasoning(_final_text)
        clean_text = _strip_leaked_system_blocks(clean_text)
        clean_text = _strip_leaked_back_frame(clean_text)
        if clean_text:
            if mode in (PromptMode.STANDARD, PromptMode.PRESENT):
                await _emit_streaming_response(
                    bus=bus,
                    text=clean_text,
                    trace_id=trace_id,
                    parent_id=parent_id,
                    source_envelope=envelope,
                )
            await _on_text_response(clean_text)
        else:
            logger.info(
                "front_handler: final text suppressed after leak guards mode=%s", mode.value
            )

    # 11. Post-loop: auto-emit task.resume after HITL_RESOLVE (Epic 6.4.4)
    if mode == PromptMode.HITL_RESOLVE:
        task_state_section = _safe_get_section(ss, "task_state")
        suspended_task: dict[str, Any] = {}
        if task_state_section and hasattr(task_state_section, "get_all"):
            tasks = task_state_section.get_all()
            suspended_task = next(
                (t for t in tasks if _task_has_status(t, "SUSPENDED")),
                {},
            )
        suspended_task_id = _task_field(suspended_task, "task_id", "")
        # E1.M2.1 / E4: when the suspension was created by the unified
        # HumanInTheLoopService, ``pending_hil.envelope`` carries the
        # original HILEnvelope.  In that case we publish ONLY the
        # unified TOPIC_HIL_RESPONSE -- the service resolves the Future
        # and the caller (Fabric / Back / Planner / Orchestrator)
        # continues in-process.  We must NOT also emit the legacy
        # TOPIC_TASK_RESUME or downstream Back would attempt a double
        # resume.  Legacy emission is only correct for legacy task
        # suspensions (no envelope under pending_hil).
        pending_hil = _task_pending_hil_payload(suspended_task) if suspended_task else {}
        incoming_envelope = pending_hil.get("envelope") or pending_hil.get("compat_hil_envelope")
        resolution_frame = _build_resolution_frame(scenario_data) if suspended_task_id else None
        resolution = resolution_frame.to_resolution_dict() if resolution_frame else None

        if incoming_envelope:
            from k1.concierge.actors.front_hil_envelope import (
                build_hil_response_envelope_dict,
                is_legacy_bridge_envelope,
            )

            try:
                resp_payload = build_hil_response_envelope_dict(
                    incoming_envelope,
                    resolution or _build_resolution(scenario_data),
                    raw_user_text=(
                        resolution_frame.raw_user_text
                        if resolution_frame
                        else scenario_data.get("user_answer")
                    ),
                )
                bus.publish(build_hil_response(resp_payload, parent_id=parent_id))
                logger.info(
                    "front_emit_hil_response hil_request_id=%s kind=%s",
                    resp_payload.get("hil_request_id"),
                    resp_payload.get("kind"),
                )
                if is_legacy_bridge_envelope(incoming_envelope) and suspended_task_id:
                    emit_task_resume(
                        bus=bus,
                        task_id=suspended_task_id,
                        user_answer=json.dumps(resolution or {}),
                        resolution=resolution,
                        resolution_frame=resolution_frame.to_dict() if resolution_frame else None,
                        parent_id=parent_id,
                        trace_id=trace_id,
                        source_envelope=envelope,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "front_emit_hil_response_failed error=%s envelope_keys=%s",
                    exc,
                    (
                        list(incoming_envelope.keys())
                        if isinstance(incoming_envelope, dict)
                        else type(incoming_envelope).__name__
                    ),
                )
        elif suspended_task_id and resolution is not None:
            # Legacy path: no unified envelope -- emit TOPIC_TASK_RESUME so
            # Back's back_resume_handler can pick up the resolution.  Once
            # E4 Back migration retires the bus round-trip this branch can
            # be deleted along with back_resume_handler.
            emit_task_resume(
                bus=bus,
                task_id=suspended_task_id,
                user_answer=json.dumps(resolution),
                resolution=resolution,
                resolution_frame=resolution_frame.to_dict() if resolution_frame else None,
                parent_id=parent_id,
                trace_id=trace_id,
                source_envelope=envelope,
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
    from k1.concierge.bus.topics import FRONT_SUBSCRIPTIONS

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
    resolution_frame: dict[str, Any] | None = None,
    parent_id: int = 0,
    trace_id: str = "",
    source_envelope: Envelope | None = None,
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

    payload = {
        "task_id": task_id,
        "resolution": resolved_payload,
        "answer": user_answer,
        "trace_id": trace_id,
    }
    if resolution_frame is not None:
        payload["resolution_frame"] = resolution_frame
    elif (
        isinstance(resolved_payload, dict)
        and resolved_payload.get("_frame_type") == "hil_resolution"
    ):
        payload["resolution_frame"] = resolved_payload

    env = build_task_resume(payload=payload, parent_id=parent_id)
    if source_envelope is not None:
        env = _correlate_envelope(env, source_envelope, trace_id)
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
    source_envelope: Envelope | None = None,
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
        if source_envelope is not None:
            env = _correlate_envelope(env, source_envelope, trace_id)
        bus.publish(env)
