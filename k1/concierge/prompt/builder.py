"""
k1.concierge.prompt.builder -- DynamicPromptBuilder and BuiltContext.

Mode-driven prompt assembly for Front LLM. Replaces the monolithic
prompt approach with mode-specific tool selection, SS read configs,
iteration limits, and affect modulation.

V2 Design Ref: Section 16.3 (PromptMode Architecture)

The DynamicPromptBuilder.build() method produces a BuiltContext containing
everything react_loop() needs for one Front LLM invocation:
    - system_prompt: assembled prompt text
    - messages: chat history as ModelMessage list
    - tools: filtered ToolSchema list per mode
    - max_iterations: mode + affect adjusted
    - mode: resolved PromptMode (for observability)
    - affect_band: computed band string
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from k1.concierge.llm.types import ModelMessage, ToolSchema

logger = logging.getLogger(__name__)
from k1.concierge.config import get_config
from k1.concierge.prompt.affect import (
    AFFECT_TONE_BLOCKS,
    AffectBand,
    AffectModifiers,
    compute_affect_modifiers,
    get_affect_mode_interaction,
)
from k1.concierge.prompt.clarify_depth import CLARIFY_DEPTH_BLOCKS
from k1.concierge.prompt.domain_rules import get_domain_rules, is_domain_applicable
from k1.concierge.prompt.mode import (
    CRISIS_ITERATIONS_TABLE,
    MAX_ITERATIONS_TABLE,
    PromptMode,
    get_tool_allowlist,
)
from k1.concierge.prompt.scenario_templates import SCENARIO_DATA_TEMPLATES
from k1.concierge.prompt.sections import (
    ANTI_PATTERN_KEYS,
    MODE_EXAMPLES,
    MODE_SECTIONS,
    PROMPT_SECTIONS,
)

# =========================================================================
# SSReadConfig -- per-section read directive
# =========================================================================


@dataclass(frozen=True)
class SSReadConfig:
    """Specifies how to read one SS section for a given mode.

    Attributes:
        section: SS section name (e.g. "beliefs_active", "control")
        read_mode: "full" | "slim" | "skip"
        history_window: Only meaningful for "history_active" section
    """

    section: str
    read_mode: Literal["full", "slim", "skip"]
    history_window: int = 20


# =========================================================================
# SS Read Configs per mode (V2 Section 16.3)
# =========================================================================

SS_READ_CONFIGS: dict[PromptMode, list[SSReadConfig]] = {
    PromptMode.STANDARD: [
        SSReadConfig("temporal", "full"),
        SSReadConfig("beliefs_active", "full"),
        SSReadConfig("scoreboard", "full"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("narrative_active", "full"),
        SSReadConfig("control", "full"),
        SSReadConfig("history_active", "full", history_window=20),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
    ],
    PromptMode.CLARIFY_ASK: [
        SSReadConfig("temporal", "slim"),
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("scoreboard", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=10),
        SSReadConfig("persona", "full"),
    ],
    PromptMode.CLARIFY_RESOLVE: [
        SSReadConfig("temporal", "slim"),
        SSReadConfig("beliefs_active", "full"),
        SSReadConfig("scoreboard", "full"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=15),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "slim"),
    ],
    PromptMode.HITL_RELAY: [
        SSReadConfig("temporal", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.HITL_RESOLVE: [
        SSReadConfig("temporal", "slim"),
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("scoreboard", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.PRESENT: [
        SSReadConfig("temporal", "full"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "slim"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=10),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
        SSReadConfig("beliefs_active", "slim"),
    ],
    PromptMode.WEAVE: [
        SSReadConfig("temporal", "full"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=10),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
        SSReadConfig("beliefs_active", "slim"),
    ],
    PromptMode.CANCEL: [
        SSReadConfig("temporal", "slim"),
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "slim"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.INTERRUPT: [
        SSReadConfig("temporal", "full"),
        SSReadConfig("beliefs_active", "full"),
        SSReadConfig("scoreboard", "full"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("narrative_active", "full"),
        SSReadConfig("control", "full"),
        SSReadConfig("history_active", "full", history_window=20),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "full"),
    ],
    PromptMode.ERROR: [
        SSReadConfig("temporal", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "slim"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "slim"),
    ],
}

for _mode, _configs in list(SS_READ_CONFIGS.items()):
    SS_READ_CONFIGS[_mode] = [cfg for cfg in _configs if cfg.section != "temporal"]


# =========================================================================
# BuiltContext -- output of DynamicPromptBuilder.build()
# =========================================================================


# =========================================================================
# SS section helper: safe section access
# =========================================================================


def _safe_get_ss_section(ss: Any, section_name: str) -> Any:
    """Get an SS section by name, returning None on any failure.

    Supports get_section(name) on SessionStateManager.
    """
    try:
        if hasattr(ss, "get_section"):
            return ss.get_section(section_name)
    except Exception:
        pass
    return None


# =========================================================================
# SECTION_RENDERERS -- 10 pairs of (full_fn, slim_fn) (E4.4.1)
# =========================================================================


def _render_task_state_full(section: Any, cfg: SSReadConfig) -> str:
    """Delegate to section.to_prompt(). Suppress empty placeholder strings."""
    if hasattr(section, "to_prompt"):
        text = section.to_prompt() or ""
        stripped = text.strip().lower()
        if stripped in {"", "(no active task)", "(no task)", "(none)"}:
            return ""
        return text
    return ""


def _render_task_state_slim(section: Any, cfg: SSReadConfig) -> str:
    """Delegate to section.to_slim_prompt(). Suppress empty placeholder strings."""
    if hasattr(section, "to_slim_prompt"):
        text = section.to_slim_prompt() or ""
        stripped = text.strip().lower()
        if stripped in {"", "(no active task)", "(no task)", "(none)"}:
            return ""
        return text
    return ""


def _render_task_artifacts_full(section: Any, cfg: SSReadConfig) -> str:
    """Delegate to section.to_prompt(). Suppress empty placeholder strings."""
    if hasattr(section, "to_prompt"):
        text = section.to_prompt() or ""
        stripped = text.strip().lower()
        if stripped in {"", "(no artifacts)", "(none)", "0 artifact(s)"}:
            return ""
        return text
    return ""


def _render_task_artifacts_slim(section: Any, cfg: SSReadConfig) -> str:
    """Delegate to section.to_slim_prompt(). Suppress empty placeholder strings."""
    if hasattr(section, "to_slim_prompt"):
        text = section.to_slim_prompt() or ""
        stripped = text.strip().lower()
        if stripped in {"", "(no artifacts)", "(none)", "0 artifact(s)"}:
            return ""
        return text
    return ""


def _render_history_active_full(section: Any, cfg: SSReadConfig) -> str:
    """Call format_for_prompt(n=window)."""
    if hasattr(section, "format_for_prompt"):
        return section.format_for_prompt(n=cfg.history_window)
    return ""


def _render_history_active_slim(section: Any, cfg: SSReadConfig) -> str:
    """Slim: format_for_prompt with reduced window."""
    if hasattr(section, "format_for_prompt"):
        window = min(5, cfg.history_window)
        return section.format_for_prompt(n=window)
    return ""


def _render_beliefs_active_full(section: Any, cfg: SSReadConfig) -> str:
    """Format facts as SVO lines with confidence."""
    lines: list[str] = []
    facts = []
    if hasattr(section, "list_facts"):
        facts = section.list_facts()
    for f in facts:
        subj = getattr(f, "subject", "")
        pred = getattr(f, "predicate", "")
        obj = getattr(f, "object", "")
        conf = getattr(f, "confidence", 1.0)
        lines.append(f"- {subj} {pred} {obj} (confidence: {conf})")
    # Entity refs
    if hasattr(section, "_entities") and section._entities:
        for eid, eref in section._entities.items():
            name = getattr(eref, "display_name", eid)
            etype = getattr(eref, "type", "")
            if etype:
                lines.append(f"  [entity: {name} ({etype})]")
            else:
                lines.append(f"  [entity: {name}]")
    # Mentioned time/location
    if hasattr(section, "_mentioned_time") and section._mentioned_time:
        raw = getattr(section._mentioned_time, "raw_text", "")
        if raw:
            lines.append(f"  [time: {raw}]")
    if hasattr(section, "_mentioned_location") and section._mentioned_location:
        raw = getattr(section._mentioned_location, "raw_text", "")
        if raw:
            lines.append(f"  [mentioned location: {raw}]")
    return "\n".join(lines)


def _render_beliefs_active_slim(section: Any, cfg: SSReadConfig) -> str:
    """Slim: fact count + pinned facts only."""
    count = 0
    if hasattr(section, "get_fact_count"):
        count = section.get_fact_count()
    pinned: list[str] = []
    if hasattr(section, "get_pinned_fact_ids"):
        pinned = section.get_pinned_fact_ids()
    parts = [f"Facts: {count}"]
    if pinned:
        parts.append(f"Pinned: {', '.join(pinned)}")
    return "\n".join(parts)


def _render_scoreboard_full(section: Any, cfg: SSReadConfig) -> str:
    """Format referents, current topic, QUD stack, and open commitments."""
    lines: list[str] = []
    # Referents
    if hasattr(section, "_referents"):
        for ref in section._referents.values():
            text = getattr(ref, "text", "")
            sal = getattr(ref, "salience", 0)
            lines.append(f"- referent: {text} (salience: {sal:.2f})")
    # Primary topic
    if hasattr(section, "get_primary_topic"):
        topic = section.get_primary_topic()
        if topic:
            lines.append(f"Topic: {topic.name}")
    # QUD stack
    if hasattr(section, "_qud_stack"):
        for q in section._qud_stack:
            status = getattr(q, "status", "")
            lines.append(f"- QUD: {q.text} [{status}]")
    # Open commitments
    if hasattr(section, "get_open_commitments"):
        open_commitments = section.get_open_commitments()
        if open_commitments:
            lines.append("== OPEN COMMITMENTS ==")
            for c in open_commitments:
                lines.append(f"- [{c.id[:8]}] {c.description} | TRIGGER: {c.trigger_condition}")
                if c.linked_entities:
                    lines.append(f"  entities: {', '.join(c.linked_entities)}")
                if c.linked_content_summary:
                    lines.append(f"  content: {c.linked_content_summary}")
    return "\n".join(lines)


def _render_scoreboard_slim(section: Any, cfg: SSReadConfig) -> str:
    """Slim: current topic + referent count + open commitment count."""
    parts: list[str] = []
    if hasattr(section, "get_primary_topic"):
        topic = section.get_primary_topic()
        if topic:
            parts.append(f"Topic: {topic.name}")
    ref_count = len(section._referents) if hasattr(section, "_referents") else 0
    parts.append(f"Referents: {ref_count}")
    if hasattr(section, "get_open_commitments"):
        open_c = section.get_open_commitments()
        if open_c:
            parts.append(f"Open commitments: {len(open_c)}")
            for c in open_c:
                parts.append(f"  - {c.description} (trigger: {c.trigger_condition})")
    return "\n".join(parts)


def _render_clarifications_full(section: Any, cfg: SSReadConfig) -> str:
    """Format pending + blocking clarifications."""
    lines: list[str] = []
    pending = []
    if hasattr(section, "list_pending"):
        pending = section.list_pending()
    elif hasattr(section, "get_pending"):
        pending = section.get_pending()
    for c in pending:
        q = getattr(c, "question", "")
        pri = getattr(c, "priority", 0)
        lines.append(f"- pending: {q} (priority: {pri})")
    if hasattr(section, "get_blocking"):
        blocking = section.get_blocking()
        if blocking:
            lines.append(f"- BLOCKING: {blocking.question}")
    return "\n".join(lines)


def _render_clarifications_slim(section: Any, cfg: SSReadConfig) -> str:
    """Slim: count of pending."""
    count = 0
    if hasattr(section, "list_pending"):
        count = len(section.list_pending())
    elif hasattr(section, "get_pending"):
        count = len(section.get_pending())
    return f"Pending: {count}"


def _render_narrative_active_full(section: Any, cfg: SSReadConfig) -> str:
    """Full: active thread name, goal, related entities."""
    lines: list[str] = []
    thread = getattr(section, "_primary_thread", None)
    if thread is None and hasattr(section, "primary_thread"):
        thread = section.primary_thread
    if thread:
        lines.append(f"Thread: {thread.title}")
        if thread.goal:
            lines.append(f"Goal: {thread.goal}")
        if thread.related_entities:
            lines.append(f"Entities: {', '.join(thread.related_entities)}")
    return "\n".join(lines)


def _render_narrative_active_slim(section: Any, cfg: SSReadConfig) -> str:
    """Slim: active thread name only."""
    if hasattr(section, "get_active_thread_name"):
        name = section.get_active_thread_name()
        if name:
            return f"Thread: {name}"
    return ""


def _tone_to_hints(tone: dict[str, Any]) -> list[str]:
    """Convert tone adjustment dict to natural-language advisory hints."""
    hints: list[str] = []
    warmth = tone.get("warmth", 0.0)
    formality = tone.get("formality", 0.0)
    pace = tone.get("pace", "")
    mirror = tone.get("mirror_intensity", 0.0)

    if warmth > 0.1:
        hints.append("- Use a warmer, more caring tone")
    elif warmth < -0.1:
        hints.append("- Use a cooler, more matter-of-fact tone")

    if formality > 0.1:
        hints.append("- Be more structured and formal")
    elif formality < -0.1:
        hints.append("- Be more casual and approachable")

    if pace == "slower":
        hints.append("- Slower pacing. Shorter sentences. Less cognitive load.")
    elif pace == "faster":
        hints.append("- Quick, energetic pacing. Match their momentum.")

    if mirror > 0.5:
        hints.append("- Mirror their emotional energy and language style")
    elif mirror > 0.2:
        hints.append("- Lightly reflect their emotional tone")

    return hints


def _style_to_hints(style: dict[str, Any]) -> list[str]:
    """Convert response style dict to natural-language advisory hints."""
    hints: list[str] = []
    length_pref = style.get("response_length_preference", "balanced")
    msg_style = style.get("message_style", "single_complete")
    verbosity = style.get("verbosity_level", 0.5)

    if length_pref == "concise":
        hints.append("- User prefers SHORT responses. Be brief and direct.")
    elif length_pref == "detailed":
        hints.append("- User prefers DETAILED responses. Elaborate when helpful.")

    if msg_style == "conversational_bursts":
        hints.append("- User sends rapid short messages. Match with concise replies.")

    if verbosity < 0.3:
        hints.append("- Minimize filler words and preamble.")
    elif verbosity > 0.7:
        hints.append("- OK to be more expressive and thorough.")

    return hints


def _render_affective_now_full(section: Any, cfg: SSReadConfig) -> str:
    """Full: emotion, intensity, valence, arousal + tone/style hints."""
    emotion = getattr(section, "current_emotion", "neutral")
    intensity = getattr(section, "intensity", 0.0)
    valence = getattr(section, "valence", 0.0)
    arousal = getattr(section, "arousal", 0.5)
    lines = [
        f"Emotion: {emotion}",
        f"Intensity: {intensity}",
        f"Valence: {valence}",
        f"Arousal: {arousal}",
    ]

    # Tone adjustment from AffectiveMirror (Experience Layer)
    tone = getattr(section, "_tone_adjustment", None)
    if tone and isinstance(tone, dict):
        tone_hints = _tone_to_hints(tone)
        if tone_hints:
            lines.append("== TONE FINE-TUNING ==")
            lines.extend(tone_hints)

    # Response style from ResponseStyleAdapter (Experience Layer)
    style = getattr(section, "_response_style", None)
    if style and isinstance(style, dict):
        style_hints = _style_to_hints(style)
        if style_hints:
            lines.append("== RESPONSE STYLE ==")
            lines.extend(style_hints)

    return "\n".join(lines)


def _render_affective_now_slim(section: Any, cfg: SSReadConfig) -> str:
    """Slim: emotion (intensity) + style hint when non-default."""
    emotion = getattr(section, "current_emotion", "neutral")
    intensity = getattr(section, "intensity", 0.0)
    parts = [f"{emotion} ({intensity})"]
    style = getattr(section, "_response_style", None)
    if style and isinstance(style, dict):
        pref = style.get("response_length_preference", "")
        if pref and pref != "balanced":
            parts.append(f"Style: {pref}")
    return " | ".join(parts)


def _render_control_full(section: Any, cfg: SSReadConfig) -> str:
    """Full: get_metadata() dict including fsm_overlay. Pretty-prints
    nested dicts as ``key.subkey: value`` lines (avoids Python ``repr``
    leaking into the prompt)."""
    if hasattr(section, "get_metadata"):
        meta = section.get_metadata()
        lines: list[str] = []
        for key, val in meta.items():
            if isinstance(val, dict):
                if not val:
                    continue
                for sub_key, sub_val in val.items():
                    lines.append(f"{key}.{sub_key}: {sub_val}")
            else:
                lines.append(f"{key}: {val}")
        return "\n".join(lines)
    return ""


def _render_control_slim(section: Any, cfg: SSReadConfig) -> str:
    """Slim: fsm_state + safety band only."""
    parts: list[str] = []
    if hasattr(section, "get_metadata"):
        meta = section.get_metadata()
        if "fsm_state" in meta:
            parts.append(f"FSM: {meta['fsm_state']}")
        parts.append(f"Safety: {meta.get('safety_band', 'unknown')}")
    elif hasattr(section, "fsm_overlay"):
        overlay = section.fsm_overlay
        if overlay.get("fsm_state"):
            parts.append(f"FSM: {overlay['fsm_state']}")
    return "\n".join(parts)


def _render_persona_full(section: Any, cfg: SSReadConfig) -> str:
    """Full: preferences (payment_method, dietary, accessibility etc)."""
    lines: list[str] = []
    if hasattr(section, "get_all_preferences"):
        prefs = section.get_all_preferences()
        for key, val in prefs.items():
            lines.append(f"{key}: {val}")
    return "\n".join(lines)


def _render_persona_slim(section: Any, cfg: SSReadConfig) -> str:
    """Slim: preference key names only."""
    if hasattr(section, "get_all_preferences"):
        keys = list(section.get_all_preferences().keys())
        if keys:
            return f"Preferences: {', '.join(keys)}"
    return ""


def _build_temporal_projection(section: Any, *, consumer: str) -> Any | None:
    if section is None or not hasattr(section, "to_dict"):
        return None
    try:
        from k1.temporal.serialization import (
            dict_to_anchor,
            dict_to_resolution,
            dict_to_window,
        )
        from k1.temporal.types import TemporalProjection

        payload = section.to_dict() or {}
        anchor_payload = payload.get("anchor")
        if not isinstance(anchor_payload, dict) or not anchor_payload:
            return None
        windows_payload = payload.get("windows") or {}
        resolutions_payload = payload.get("resolved_expressions") or []
        return TemporalProjection(
            anchor=dict_to_anchor(anchor_payload),
            windows={
                str(key): dict_to_window(value)
                for key, value in windows_payload.items()
                if isinstance(value, dict)
            },
            resolved_expressions=tuple(
                dict_to_resolution(value)
                for value in resolutions_payload
                if isinstance(value, dict)
            ),
            consumer=consumer,
            freshness="live",
            precision="execution" if consumer != "front" else "anchor",
        )
    except Exception:
        logger.exception("Temporal projection build failed")
        return None


def _render_temporal_full(section: Any, cfg: SSReadConfig) -> str:
    projection = _build_temporal_projection(section, consumer="front")
    if projection is None:
        return ""
    from k1.temporal.service.projection_renderer import render_execution_block

    return render_execution_block(projection)


def _render_temporal_slim(section: Any, cfg: SSReadConfig) -> str:
    projection = _build_temporal_projection(section, consumer="front")
    if projection is None:
        return ""
    from k1.temporal.service.projection_renderer import render_now_block

    return render_now_block(projection)


SECTION_SOURCE_MAP: dict[str, str] = {}


# Dispatch table: section_name -> (full_renderer, slim_renderer)
SECTION_RENDERERS: dict[str, tuple] = {
    "task_state": (_render_task_state_full, _render_task_state_slim),
    "task_artifacts": (_render_task_artifacts_full, _render_task_artifacts_slim),
    "history_active": (_render_history_active_full, _render_history_active_slim),
    "beliefs_active": (_render_beliefs_active_full, _render_beliefs_active_slim),
    "scoreboard": (_render_scoreboard_full, _render_scoreboard_slim),
    "clarifications": (_render_clarifications_full, _render_clarifications_slim),
    "narrative_active": (_render_narrative_active_full, _render_narrative_active_slim),
    "affective_now": (_render_affective_now_full, _render_affective_now_slim),
    "control": (_render_control_full, _render_control_slim),
    "persona": (_render_persona_full, _render_persona_slim),
    "temporal": (_render_temporal_full, _render_temporal_slim),
}


# =========================================================================
# BuiltContext -- output of DynamicPromptBuilder.build()
# =========================================================================


@dataclass
class BuiltContext:
    """Complete assembled context for a single Front LLM invocation.

    Returned by DynamicPromptBuilder.build(). Consumed by react_loop().

    Attributes:
        system_prompt: Assembled prompt text (sections + examples + affect
            tone + depth + domain rules + anti-pattern + scenario data)
        messages: Chat history + current input as ModelMessage list
        tools: Filtered ToolSchema list for this mode
        max_iterations: From MAX_ITERATIONS_TABLE, with crisis override
        mode: The resolved PromptMode (for observability/logging)
        affect_band: Computed band string
        estimated_tokens: Approximate token count for system_prompt
    """

    system_prompt: str
    messages: list[ModelMessage] = field(default_factory=list)
    tools: list[ToolSchema] = field(default_factory=list)
    max_iterations: int = 6
    mode: PromptMode = PromptMode.STANDARD
    affect_band: str = "neutral"
    estimated_tokens: int = 0


# =========================================================================
# apply_affect_modifiers -- standalone helper
# =========================================================================


def apply_affect_modifiers(
    modifiers: AffectModifiers,
    base_max_iterations: int,
    prompt_parts: list[str],
    tools: list[ToolSchema] | None = None,
) -> tuple[int, list[ToolSchema]]:
    """Apply affect-band modifiers to builder intermediates.

    Adjusts max_iterations by delta, filters tools (removes refine_affect
    when skip_refine_affect is True), and injects response_length_hint
    into the prompt parts list.

    Called by DynamicPromptBuilder.build() after base assembly stages.

    Args:
        modifiers: AffectModifiers from compute_affect_modifiers().
        base_max_iterations: Base iteration count from _get_max_iterations().
        prompt_parts: Mutable list of prompt sections. response_length_hint
            is appended in-place if non-empty.
        tools: Tool schemas list. refine_affect is removed if
            skip_refine_affect is True. None treated as empty list.

    Returns:
        Tuple of (adjusted_max_iterations, filtered_tools).
    """
    # 1. Adjust max_iterations by delta (minimum 1)
    adjusted_iterations = max(1, base_max_iterations + modifiers.max_iterations_delta)

    # 2. Inject response_length_hint into prompt
    if modifiers.response_length_hint:
        prompt_parts.append(f"== RESPONSE LENGTH ==\n{modifiers.response_length_hint}")

    # 3. Filter tools: remove refine_affect if skip_refine_affect
    adjusted_tools = list(tools) if tools else []
    if modifiers.skip_refine_affect:
        adjusted_tools = [t for t in adjusted_tools if t.name != "refine_affect"]

    return adjusted_iterations, adjusted_tools


# =========================================================================
# DynamicPromptBuilder
# =========================================================================


class DynamicPromptBuilder:
    """Mode-driven prompt assembly for Front LLM.

    V2 Design Doc Section 6.1: 9-stage assembly pipeline + affect modifiers.

    Assembly pipeline:
      1. Select prompt sections from MODE_SECTIONS[mode]
      2. Append mode-specific example from MODE_EXAMPLES[mode]
      3. Append affect tone modifier from AFFECT_TONE_BLOCKS[band]
      3b. Append affect x mode interaction block (if exists)
      4. Append clarification depth block (CLARIFY_ASK only)
      5. Append domain rules from DOMAIN_RULES[domain]
      6. Append anti-pattern subset from ANTI_PATTERN_KEYS[mode]
      7. Format and append scenario data from SCENARIO_DATA_TEMPLATES[mode]
      8. Read SS sections per SS_READ_CONFIGS[mode] (placeholder for SS)
      9. Apply affect modifiers + pre-call budget check

    After assembly:
      - Interpolate {max_iterations} placeholder
      - Filter tools by mode allowlist (with conditional inclusion)
      - Apply affect modifier tool filtering (remove refine_affect)
      - Build chat history with mode-appropriate window
    """

    # Gemini 2.5 Pro context window (V2 Section 26.9)
    CONTEXT_WINDOW = 128_000
    SAFETY_MARGIN = 0.80
    MAX_CONTEXT_TOKENS = int(CONTEXT_WINDOW * SAFETY_MARGIN)  # 102,400

    # Token estimation: ~4 chars per token (rough approximation)
    CHARS_PER_TOKEN = 4

    @property
    def _context_window(self) -> int:
        return get_config().prompt.context_window

    @property
    def _safety_margin(self) -> float:
        return get_config().prompt.safety_margin

    @property
    def _max_context_tokens(self) -> int:
        return int(self._context_window * self._safety_margin)

    @property
    def _chars_per_token(self) -> int:
        return get_config().prompt.chars_per_token

    def build(
        self,
        mode: PromptMode,
        affect_band: AffectBand,
        history_messages: list[ModelMessage] | None = None,
        all_tool_schemas: list[ToolSchema] | None = None,
        scenario_data: dict[str, Any] | None = None,
        clarify_depth: int = 0,
        domain: str | None = None,
        affect_confidence: float = 1.0,
        tier: str = "LOW",
        ss: Any = None,
        grounding_capsule: Any = None,
        grounding_projection: Any = None,
    ) -> BuiltContext:
        """Assemble complete context for one Front LLM invocation.

        V2 Design Doc Section 6.1: 9-stage pipeline.

        Args:
            mode: Resolved PromptMode from determine_mode().
            affect_band: Computed AffectBand from compute_affect_band().
            history_messages: Pre-built chat history from build_chat_history().
            all_tool_schemas: Full FRONT_TOOL_SCHEMAS list to filter from.
            scenario_data: Mode-specific data dict for prompt injection.
            clarify_depth: Clarification re-ask depth (0=first, 1=re-ask, 2=final).
            domain: Optional domain string from Phase 1 classification.
            affect_confidence: Phase 1 affect confidence for conditional tools.
            tier: Task complexity tier for conditional tool inclusion.
            ss: SessionStateManager instance (duck typed). When provided,
                stage 8 reads and renders SS sections per SS_READ_CONFIGS.
                When None, stage 8 is a no-op (backward compatible).
            grounding_capsule: Optional ``GroundingCapsule`` from
                ``k1.selfmodel`` (M4). When provided, stage 9.5 appends
                its ``as_prompt_text()`` output to ``prompt_parts`` so
                every Front prompt is grounded in the actor's
                SituationFrame. ``None`` keeps the pre-M4 baseline.
            grounding_projection: Optional ``GroundingProjection`` from
                ``k1.grounding``. When provided, stage 9.5 renders NOW
                and PLACE from the projection. Temporal SessionState is
                not read directly for prompt construction.

        Returns:
            BuiltContext with everything react_loop() needs.
        """
        messages = list(history_messages) if history_messages else []
        all_schemas = all_tool_schemas or []

        # M6.E1.I4 / M6.E3.I2: OPP-6 compressed_context and OPP-7
        # identity_block are smuggled through ``scenario_data`` by
        # ``front_handler``. The builder consumes them explicitly and
        # strips them before scenario formatting so they cannot leak via
        # the ``_format_scenario_data`` fallback (which prints unknown keys
        # as raw ``key: value`` text). They are then re-injected at their
        # canonical positions: compressed_context REPLACES the history_active
        # SS read at Stage 8, identity_block is appended after Stage 9.5
        # promoted blocks.
        compressed_context_block = ""
        identity_block_text = ""
        if scenario_data:
            compressed_context_block = str(scenario_data.get("compressed_context", "") or "")
            identity_block_text = str(scenario_data.get("identity_block", "") or "")
            if compressed_context_block or identity_block_text:
                scenario_data = {
                    k: v
                    for k, v in scenario_data.items()
                    if k not in ("compressed_context", "identity_block")
                }

        logger.info(
            "DynamicPromptBuilder.build START  mode=%s affect=%s domain=%s tier=%s depth=%d",
            mode.value,
            affect_band.band,
            domain,
            tier,
            clarify_depth,
        )

        prompt_parts: list[str] = []

        # Stage 1: Select and concatenate prompt sections from MODE_SECTIONS
        section_keys = MODE_SECTIONS.get(mode, [])
        for key in section_keys:
            section_text = PROMPT_SECTIONS.get(key, "")
            if section_text:
                prompt_parts.append(section_text)
        logger.debug(
            "  Stage 1  sections=%d keys=%s",
            len(section_keys),
            section_keys,
        )

        # Stage 2: Append mode-specific example from MODE_EXAMPLES
        example_text = MODE_EXAMPLES.get(mode, "")
        if example_text:
            prompt_parts.append(example_text)
            logger.debug("  Stage 2  example appended (len=%d)", len(example_text))

        # Stage 3: Append affect tone modifier (skip neutral -- empty string)
        tone_block = AFFECT_TONE_BLOCKS.get(affect_band.band, "")
        if tone_block:
            prompt_parts.append(tone_block)

        # Stage 3b: Append affect x mode interaction block
        interaction_block = get_affect_mode_interaction(mode.name, affect_band.band)
        if interaction_block:
            prompt_parts.append(interaction_block)
            logger.debug("  Stage 3b  affect x mode interaction appended")

        # Stage 4: Append clarification depth block (CLARIFY_ASK only)
        if mode == PromptMode.CLARIFY_ASK and clarify_depth in CLARIFY_DEPTH_BLOCKS:
            depth_block = CLARIFY_DEPTH_BLOCKS[clarify_depth]
            # Format placeholders if scenario_data provides them
            if scenario_data and "{" in depth_block:
                try:
                    depth_block = depth_block.format(
                        field=scenario_data.get("gap_field", ""),
                        previous_question=scenario_data.get("previous_question", ""),
                    )
                except KeyError:
                    pass  # Use raw template if formatting fails
            prompt_parts.append(depth_block)

        # Stage 5: Append domain rules (only for applicable modes)
        # RC-3 fix: consult is_domain_applicable() to avoid leaking
        # domain rules into modes where they are irrelevant.
        if domain and is_domain_applicable(domain, mode.value):
            domain_block = get_domain_rules(domain)
            if domain_block:
                prompt_parts.append(domain_block)

        # Stage 6: Append anti-pattern subset
        if mode in ANTI_PATTERN_KEYS:
            ap_key = ANTI_PATTERN_KEYS[mode]
            ap_text = PROMPT_SECTIONS.get(ap_key, "")
            if ap_text:
                prompt_parts.append(ap_text)

        active_member_block = ""
        if grounding_capsule is not None:
            active_member_block = self._build_active_member_block(grounding_capsule)

        # Stage 7: Format and append scenario data from template
        scenario_payload = scenario_data
        if (
            scenario_data
            and active_member_block
            and mode in (PromptMode.STANDARD, PromptMode.INTERRUPT)
        ):
            scenario_payload = dict(scenario_data)
            scenario_payload["_suppress_active_member_block"] = True

        if scenario_payload:
            scenario_block = self._format_scenario_data(mode, scenario_payload)
            if scenario_block:
                prompt_parts.append(scenario_block)

        # Stage 8: Read and render SS sections per mode config.
        # M6.E1.I4: when an OPP-6 compressed_context is present we replace
        # the raw history_active SS read with the compressed block at the
        # same position. We do this by filtering history_active out of the
        # configs list before delegating to ``_read_ss_sections`` (which
        # owns the rendering of all other sections unchanged), then append
        # the compressed block. This keeps the SessionState section
        # untouched and the substitution surface explicit + observable.
        if ss is not None:
            ss_configs = SS_READ_CONFIGS.get(mode, [])
            if compressed_context_block:
                ss_configs = [c for c in ss_configs if c.section != "history_active"]
            ss_block = self._read_ss_sections(ss, ss_configs)
            if ss_block:
                prompt_parts.append(ss_block)
            if compressed_context_block:
                prompt_parts.append(compressed_context_block)
                logger.debug(
                    "  Stage 8  history_active replaced by OPP-6 " "compressed_context (len=%d)",
                    len(compressed_context_block),
                )

        # Stage 9: Apply affect modifiers + pre-call budget check
        base_max_iter = self._get_max_iterations(mode, affect_band)
        modifiers = compute_affect_modifiers(affect_band)
        max_iter, _ = apply_affect_modifiers(modifiers, base_max_iter, prompt_parts)
        logger.debug(
            "  Stage 9  base_iter=%d adjusted_iter=%d skip_refine=%s",
            base_max_iter,
            max_iter,
            modifiers.skip_refine_affect,
        )

        # Stage 9.5: Promote LIVE turn-specific signals + split capsule.
        #
        # Rationale (audit findings, May 2026): the previous layout buried
        # CURRENT TIME, affect band, and the conscience block at positions
        # 14+, 16, and 17 — even though IDENTITY/SAFETY rules at positions 1
        # and 10 directly reference them. We now promote three blocks to
        # sit RIGHT AFTER IDENTITY so they precede every rule that depends
        # on them:
        #   1. == NOW ==              one-line clock from temporal_context
        #   2. == AFFECT STATE ==     band + tone-rule + length-rule (consolidated)
        #   3. == CONSCIENCE ==       forbidden / must_ask acts (from capsule)
        #
        # The remaining capsule blocks ([self] / [preferences] / [space]
        # / etc. and the freshness footer) stay at the bottom under a
        # tightened == GROUNDING == header.
        #
        # M6 framing note: the LLM previously confused the conscience
        # (behavioural) with ``tools=[]`` (capability menu). The new
        # preamble keeps that disambiguation while being much shorter.
        live_grounding_blocks = self._build_grounding_live_blocks(grounding_projection)
        if not live_grounding_blocks:
            now_block = self._build_now_block(ss)
            if now_block:
                live_grounding_blocks = [now_block]
        affect_state_block = self._build_affect_state_block(affect_band, modifiers, ss)
        conscience_block_text = ""
        capsule_text = ""
        if grounding_capsule is not None:
            conscience_block_text = getattr(grounding_capsule, "conscience_block", "") or ""
            try:
                capsule_text = self._render_capsule_without_conscience(grounding_capsule)
            except Exception:
                logger.exception("  Stage 9.5  capsule render raised; skipping capsule body")
                capsule_text = ""

        # Compute insertion index: directly after IDENTITY (always part[0]
        # when present). For modes whose first section is not IDENTITY we
        # still insert at index 0.
        insert_idx = 1 if prompt_parts and prompt_parts[0].startswith("== IDENTITY ==") else 0

        # Promotion order (inserted at insert_idx in sequence):
        #   [self]+[space]  ->  NOW  ->  AFFECT STATE  ->  CONSCIENCE
        # This ensures IDENTITY is immediately followed by WHO the user is,
        # then the live turn signals, then the refusal authority — all before
        # any rule section that references them.
        promoted: list[str] = []
        if active_member_block:
            promoted.append(active_member_block)
        promoted.extend(live_grounding_blocks)
        if affect_state_block:
            promoted.append(affect_state_block)
        if conscience_block_text:
            conscience_header = (
                "== CONSCIENCE (live, from constitution) ==\n"
                "This block is the ONLY authoritative refusal source for this turn.\n"
                "  forbidden=...  -> these act ids MUST NOT be performed.\n"
                "  must_ask=...   -> these act ids REQUIRE explicit user confirmation.\n"
                "  everything else is allowed by default.\n"
                "Read this BEFORE the SAFETY & HITL RELAY rules below.\n\n" + conscience_block_text
            )
            promoted.append(conscience_header)

        # Insert in original order at insert_idx
        for i, block in enumerate(promoted):
            prompt_parts.insert(insert_idx + i, block)

        # M6.E3.I2: OPP-7 dynamic identity block. Appended AFTER promoted
        # blocks (so static IDENTITY + member + NOW + AFFECT + CONSCIENCE
        # are already in place) and BEFORE late grounding/reference body.
        # The block carries its own ``== DYNAMIC IDENTITY CONTEXT ==``
        # header from ``IdentitySnapshot.to_prompt_block()``. It must NOT
        # flow through scenario formatting; ``build`` already stripped it
        # from ``scenario_data`` at the top of the method.
        if identity_block_text:
            prompt_parts.append(identity_block_text)
            logger.debug(
                "  Stage 9.5  OPP-7 identity_block appended (len=%d)",
                len(identity_block_text),
            )

        # Late grounding (reference-lookup blocks: prefs, hobbies, goals,
        # routines, context, freshness). Identity + space + conscience
        # are already promoted earlier in this stage.
        if capsule_text:
            preamble = (
                "== REFERENCE PROFILE (live projection) ==\n"
                "Look up facts here when personalizing a response. These supplement\n"
                "the [self]/[space] blocks already shown above.\n"
                "- [preferences]  stored defaults for decisions (payment, dietary, etc.)\n"
                "- [hobbies]      likes/dislikes for tone + recommendation flavoring\n"
                "- [goals]        active goals for relevance-ranking + suggestions\n"
                "- [routines]     regular patterns for habit-aware responses\n"
                "- [context]      current device/situation override\n"
                "- [freshness]    staleness signal — stale = note but proceed\n"
                "- NOT a tool allowlist; tools are listed under `tools=[...]`."
            )
            prompt_parts.append(preamble)
            prompt_parts.append(capsule_text)
            logger.debug(
                "  Stage 9.5  capsule split: conscience_promoted=%s body_len=%d",
                bool(conscience_block_text),
                len(capsule_text),
            )

        # Assemble and interpolate placeholders
        system_prompt = "\n\n".join(part for part in prompt_parts if part)
        system_prompt = system_prompt.replace("{max_iterations}", str(max_iter))

        # RC-1 fix: interpolate {open_gaps_list} from scenario_data
        # STATE_INTERP_CLARIFY contains this placeholder; without
        # interpolation the raw string leaks into the LLM prompt.
        if "{open_gaps_list}" in system_prompt:
            gaps_value = (scenario_data or {}).get("open_gaps_list", "(none provided)")
            system_prompt = system_prompt.replace("{open_gaps_list}", str(gaps_value))

        # Filter tools by mode allowlist (with conditional inclusion)
        tools = self._select_tools(mode, all_schemas, affect_confidence, tier)

        # Apply affect modifier tool filtering
        if modifiers.skip_refine_affect:
            tools = [t for t in tools if t.name != "refine_affect"]

        # Estimate tokens and compress if needed
        estimated_tokens = self._estimate_tokens(system_prompt)
        if estimated_tokens > self._max_context_tokens:
            logger.warning(
                "  Prompt exceeds budget  tokens=%d max=%d -- compressing",
                estimated_tokens,
                self.MAX_CONTEXT_TOKENS,
            )
            system_prompt = self._compress_prompt(system_prompt)
            estimated_tokens = self._estimate_tokens(system_prompt)

        logger.info(
            "DynamicPromptBuilder.build DONE  mode=%s tools=%d max_iter=%d tokens=%d affect=%s",
            mode.value,
            len(tools),
            max_iter,
            estimated_tokens,
            affect_band.band,
        )

        return BuiltContext(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            max_iterations=max_iter,
            mode=mode,
            affect_band=affect_band.band,
            estimated_tokens=estimated_tokens,
        )

    def _get_max_iterations(self, mode: PromptMode, affect_band: AffectBand) -> int:
        """Get iteration limit with crisis override."""
        if affect_band.band == "crisis":
            return CRISIS_ITERATIONS_TABLE[mode]
        return MAX_ITERATIONS_TABLE[mode]

    def _select_tools(
        self,
        mode: PromptMode,
        all_schemas: list[ToolSchema],
        affect_confidence: float = 1.0,
        tier: str = "LOW",
    ) -> list[ToolSchema]:
        """Filter tool schemas by mode allowlist with conditional inclusion."""
        allowed_names = get_tool_allowlist(mode, affect_confidence, tier)
        return [t for t in all_schemas if t.name in allowed_names]

    # -----------------------------------------------------------------
    # Stage 9.5 helpers — promote live signals + split capsule
    # -----------------------------------------------------------------

    @staticmethod
    def _build_grounding_live_blocks(projection: Any) -> list[str]:
        """Render Front live grounding blocks from a GroundingProjection."""
        if projection is None:
            return []
        try:
            from k1.grounding.service.prompt_block_renderer import (
                render_now_block,
                render_place_block,
            )

            blocks = [render_now_block(projection)]
            place = render_place_block(projection)
            if place:
                blocks.append(place)
            return [block for block in blocks if block]
        except Exception:
            logger.exception("  Stage 9.5  grounding projection render raised; skipping")
            return []

    @staticmethod
    def _build_now_block(ss: Any) -> str:
        """One-line ``== NOW ==`` header derived from the temporal section.

        Returns ``""`` if ss is None or temporal anchor unavailable.
        """
        if ss is None:
            return ""
        section = _safe_get_ss_section(ss, "temporal")
        projection = _build_temporal_projection(section, consumer="front")
        if projection is None:
            return ""
        from k1.temporal.service.projection_renderer import render_now_block

        return render_now_block(projection)

    @staticmethod
    def _build_affect_state_block(
        affect_band: AffectBand,
        modifiers: Any,
        ss: Any,
    ) -> str:
        """Consolidated ``== AFFECT STATE ==`` block.

        Combines: resolved band, tone rule (from AFFECT_TONE_BLOCKS body),
        response-length rule (from AffectModifiers), and raw valence/arousal
        from affective_now. Replaces the previously scattered TONE: ... and
        == RESPONSE LENGTH == blocks (those remain available downstream as
        reference material but are now headlined here).
        """
        band = getattr(affect_band, "band", "neutral")
        valence = None
        arousal = None
        emotion = None
        if ss is not None:
            section = _safe_get_ss_section(ss, "affective_now")
            if section is not None:
                emotion = getattr(section, "current_emotion", None)
                valence = getattr(section, "valence", None)
                arousal = getattr(section, "arousal", None)

        length_hint = ""
        if modifiers is not None:
            length_hint = getattr(modifiers, "response_length_hint", "") or ""

        # Compact one-line tone rule per band
        tone_rules = {
            "crisis": "Calm + structured. Lead with action. Max 3 numbered options. NO empathy monologue.",
            "low": "Gentle + brief. Don't force cheerfulness. Offer help without pressure.",
            "elevated": "Acknowledge feeling in ONE sentence, then move to action.",
            "positive": "Match energy. Be playful. Slightly more expressive than baseline.",
            "neutral": "Natural voice. Efficient + warm. Light wit OK.",
        }
        tone = tone_rules.get(band, tone_rules["neutral"])

        lines = ["== AFFECT STATE ==", f"Band: {band.upper()}"]
        raw_parts = []
        if emotion:
            raw_parts.append(f"emotion={emotion}")
        if valence is not None:
            raw_parts.append(f"valence={valence}")
        if arousal is not None:
            raw_parts.append(f"arousal={arousal}")
        if raw_parts:
            lines.append(f"Raw: {' '.join(raw_parts)}")
        lines.append(f"Tone rule: {tone}")
        if length_hint:
            lines.append(f"Response length: {length_hint}")
        return "\n".join(lines)

    @staticmethod
    def _build_active_member_block(grounding_capsule: Any) -> str:
        """Compose ``== ACTIVE MEMBER ==`` from M7 typed ``self_block`` +
        ``space_graph_block`` only.

        Placed at position 2 (right after IDENTITY) so every rule that
        references 'the user' or 'the family' is grounded before the LLM
        reads it.

        Only uses M7 typed fields. Legacy ``actor_block`` / ``family_block``
        are intentionally excluded so backward-compat tests that use only
        legacy fields are unaffected by this promotion.
        """
        self_block = getattr(grounding_capsule, "self_block", "") or ""
        space_graph_block = getattr(grounding_capsule, "space_graph_block", "") or ""
        if not self_block and not space_graph_block:
            return ""
        parts = [
            "== ACTIVE MEMBER (authoritative — read before all rules) ==",
            "Ground truth for who you are talking to and their space.\n"
            "These blocks override any inference from chat history.",
        ]
        if self_block:
            parts.append(self_block)
        if space_graph_block:
            parts.append(space_graph_block)
        return "\n\n".join(parts)

    @staticmethod
    def _render_capsule_without_conscience(grounding_capsule: Any) -> str:
        """Render capsule WITHOUT:
        - ``conscience_block`` (promoted near SAFETY rules)
        - ``self_block`` (promoted to ACTIVE MEMBER when M7 field is set)
        - ``space_graph_block`` (promoted to ACTIVE MEMBER when M7 field is set)

        If only the legacy ``actor_block`` / ``family_block`` fields are
        present (no M7 typed blocks), they fall through here unchanged for
        backward compatibility.
        """
        self_block = getattr(grounding_capsule, "self_block", "") or ""
        space_graph_block = getattr(grounding_capsule, "space_graph_block", "") or ""
        # If M7 typed block is set it was already promoted — don't duplicate.
        # If only legacy is set, keep it in the tail for back-compat.
        identity_slot = "" if self_block else (getattr(grounding_capsule, "actor_block", "") or "")
        space_slot = (
            "" if space_graph_block else (getattr(grounding_capsule, "family_block", "") or "")
        )
        ordered = [
            identity_slot,
            getattr(grounding_capsule, "preferences_block", ""),
            getattr(grounding_capsule, "hobbies_block", ""),
            getattr(grounding_capsule, "goals_block", ""),
            getattr(grounding_capsule, "routines_block", ""),
            space_slot,
            getattr(grounding_capsule, "context_block", ""),
            getattr(grounding_capsule, "freshness_footer", ""),
        ]
        return "\n".join(p for p in ordered if p)

    def _format_scenario_data(self, mode: PromptMode, data: dict[str, Any]) -> str:
        """Format scenario data using SCENARIO_DATA_TEMPLATES.

        Uses the mode's template from SCENARIO_DATA_TEMPLATES and fills
        {placeholders} from the data dict. Falls back to key/value
        listing if template is empty or formatting fails.
        """
        if not data:
            return ""

        if mode in (PromptMode.STANDARD, PromptMode.INTERRUPT) and data.get(
            "_suppress_active_member_block"
        ):
            return str(data.get("async_results_context", "") or "")

        template = SCENARIO_DATA_TEMPLATES.get(mode, "")
        if template:
            try:
                return template.format(**data)
            except KeyError:
                # Missing placeholder -- fall through to key/value listing
                pass

        # Fallback: key/value listing for modes without templates
        lines = [f"== SCENARIO: {mode.value.upper()} =="]
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"  {key}: {', '.join(str(v) for v in value)}")
            else:
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: len(text) / CHARS_PER_TOKEN.

        Fast heuristic for budget checking, not a precise tokenizer.
        Sufficient for pre-call compression decisions.
        """
        return len(text) // self._chars_per_token

    def _compress_prompt(self, prompt: str) -> str:
        """Compress prompt to fit within token budget.

        M13.E4 — capsule-aware compression. The grounding capsule
        (M4 ``[grounding]`` block + ``as_prompt_text()`` payload) is
        appended LAST in the assembly pipeline (Stage 9.5). Naive
        head-or-tail truncation would either drop it entirely
        (tail-cut) or destroy mode framing (head-cut). Instead:

          1. Locate the ``[grounding]`` marker.
          2. If found: keep the grounding tail intact and truncate
             from the head of the pre-grounding region. The capsule
             is the only authoritative source of conscience refusal,
             so it must survive at all costs.
          3. If not found: fall back to the legacy tail-cut.

        A structured log line ``capsule_truncated.v1`` is emitted on
        the path that preserves the capsule so downstream telemetry
        can detect compression pressure.
        """
        target_chars = self._max_context_tokens * self._chars_per_token
        if len(prompt) <= target_chars:
            return prompt

        marker = "[grounding]"
        idx = prompt.find(marker)
        if idx == -1:
            # No capsule present — legacy behaviour.
            return prompt[:target_chars] + "\n\n[Context truncated for budget]"

        capsule_block = prompt[idx:]
        capsule_len = len(capsule_block)
        # Reserve room for a one-line truncation marker (~64 chars).
        truncation_marker = "\n\n[Context truncated for budget — capsule preserved]\n\n"
        budget_for_head = target_chars - capsule_len - len(truncation_marker)
        if budget_for_head <= 0:
            # Capsule alone exceeds budget — preserve it whole and let
            # the caller see an over-budget prompt rather than drop it.
            logger.warning(
                "capsule_truncated.v1 mode=capsule_only_overflow " "capsule_len=%d budget_chars=%d",
                capsule_len,
                target_chars,
            )
            return capsule_block

        head = prompt[:idx]
        if len(head) > budget_for_head:
            head = head[:budget_for_head]
            logger.warning(
                "capsule_truncated.v1 mode=head_truncated "
                "capsule_len=%d head_kept=%d budget_chars=%d",
                capsule_len,
                len(head),
                target_chars,
            )
            return head + truncation_marker + capsule_block

        # Should not happen (we already failed the size guard above)
        # but stay safe.
        return prompt

    def _get_history_window(self, mode: PromptMode) -> int:
        """Get history window for a mode from SS_READ_CONFIGS.

        Returns the history_window configured for history_active in
        the mode's SS_READ_CONFIGS, or 0 if history_active is skipped.
        """
        configs = SS_READ_CONFIGS.get(mode, [])
        return next(
            (c.history_window for c in configs if c.section == "history_active"),
            0,
        )

    # =====================================================================
    # Stage 8: SS section rendering (E4.4.1)
    # =====================================================================

    def _read_ss_sections(
        self,
        ss: Any,
        configs: list[SSReadConfig],
    ) -> str:
        """Render SS sections per mode config into a prompt block.

        For each SSReadConfig:
        - Skip if read_mode == "skip"
        - Get the section from ss (via get_section or _safe_get_section)
        - Look up (full_fn, slim_fn) in SECTION_RENDERERS
        - Call appropriate renderer
        - Assemble as labeled blocks

        Args:
            ss: SessionStateManager (duck typed, has get_section()).
            configs: List of SSReadConfig for the current mode.

        Returns:
            Assembled SS block string, or empty string if nothing rendered.
        """
        parts: list[str] = []
        for cfg in configs:
            if cfg.read_mode == "skip":
                continue
            # Get section from SS manager (resolve virtual names via source map)
            source_name = SECTION_SOURCE_MAP.get(cfg.section, cfg.section)
            section = _safe_get_ss_section(ss, source_name)
            if section is None:
                continue
            renderers = SECTION_RENDERERS.get(cfg.section)
            if renderers is None:
                logger.warning("No renderer for SS section %r -- skipped", cfg.section)
                continue
            full_fn, slim_fn = renderers
            try:
                if cfg.read_mode == "full":
                    text = full_fn(section, cfg)
                else:
                    text = slim_fn(section, cfg)
            except Exception:
                logger.exception("Renderer error for SS section %r -- skipped", cfg.section)
                continue
            if text:
                parts.append(f"## {cfg.section}\n{text}")

        if not parts:
            return ""
        return "== SESSION STATE ==\n\n" + "\n\n".join(parts)
