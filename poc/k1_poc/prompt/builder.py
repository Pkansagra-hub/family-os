"""
poc.k1_poc.prompt.builder -- DynamicPromptBuilder and BuiltContext.

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

from poc.k1_poc.llm.types import ModelMessage, ToolSchema

logger = logging.getLogger(__name__)
from poc.k1_poc.config import get_config
from poc.k1_poc.prompt.affect import (
    AFFECT_TONE_BLOCKS,
    AffectBand,
    AffectModifiers,
    compute_affect_modifiers,
    get_affect_mode_interaction,
)
from poc.k1_poc.prompt.clarify_depth import CLARIFY_DEPTH_BLOCKS
from poc.k1_poc.prompt.domain_rules import get_domain_rules, is_domain_applicable
from poc.k1_poc.prompt.mode import (
    CRISIS_ITERATIONS_TABLE,
    MAX_ITERATIONS_TABLE,
    PromptMode,
    get_tool_allowlist,
)
from poc.k1_poc.prompt.scenario_templates import SCENARIO_DATA_TEMPLATES
from poc.k1_poc.prompt.sections import (
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
        SSReadConfig("temporal_context", "full"),
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
        SSReadConfig("temporal_context", "slim"),
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("scoreboard", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("clarifications", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=10),
        SSReadConfig("persona", "full"),
    ],
    PromptMode.CLARIFY_RESOLVE: [
        SSReadConfig("temporal_context", "slim"),
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
        SSReadConfig("temporal_context", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.HITL_RESOLVE: [
        SSReadConfig("temporal_context", "slim"),
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("scoreboard", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.PRESENT: [
        SSReadConfig("temporal_context", "full"),
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
        SSReadConfig("temporal_context", "full"),
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
        SSReadConfig("temporal_context", "slim"),
        SSReadConfig("beliefs_active", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "slim"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
    ],
    PromptMode.INTERRUPT: [
        SSReadConfig("temporal_context", "full"),
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
        SSReadConfig("temporal_context", "slim"),
        SSReadConfig("affective_now", "full"),
        SSReadConfig("narrative_active", "slim"),
        SSReadConfig("control", "slim"),
        SSReadConfig("history_active", "full", history_window=5),
        SSReadConfig("persona", "full"),
        SSReadConfig("task_state", "full"),
        SSReadConfig("task_artifacts", "slim"),
    ],
}


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
    """Delegate to section.to_prompt()."""
    if hasattr(section, "to_prompt"):
        return section.to_prompt()
    return ""


def _render_task_state_slim(section: Any, cfg: SSReadConfig) -> str:
    """Delegate to section.to_slim_prompt()."""
    if hasattr(section, "to_slim_prompt"):
        return section.to_slim_prompt()
    return ""


def _render_task_artifacts_full(section: Any, cfg: SSReadConfig) -> str:
    """Delegate to section.to_prompt()."""
    if hasattr(section, "to_prompt"):
        return section.to_prompt()
    return ""


def _render_task_artifacts_slim(section: Any, cfg: SSReadConfig) -> str:
    """Delegate to section.to_slim_prompt()."""
    if hasattr(section, "to_slim_prompt"):
        return section.to_slim_prompt()
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
            lines.append(f"  [entity: {name} ({etype})]")
    # Mentioned time/location
    if hasattr(section, "_mentioned_time") and section._mentioned_time:
        raw = getattr(section._mentioned_time, "raw_text", "")
        if raw:
            lines.append(f"  [time: {raw}]")
    if hasattr(section, "_mentioned_location") and section._mentioned_location:
        raw = getattr(section._mentioned_location, "raw_text", "")
        if raw:
            lines.append(f"  [location: {raw}]")
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
    """Full: get_metadata() dict including fsm_overlay."""
    if hasattr(section, "get_metadata"):
        meta = section.get_metadata()
        lines: list[str] = []
        for key, val in meta.items():
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


# =========================================================================
# Temporal context renderers (reads from Control sub-field)
# Architecture ref: skeleton.mmd -> TIME_RESOLUTION -> TEMPORAL_ANCHOR
# Port path: Multimodal section sub-field (Section 5)
# =========================================================================


def _render_temporal_context_full(section: Any, cfg: SSReadConfig) -> str:
    """Full: multi-line temporal anchor from Control sub-field."""
    anchor = None
    if hasattr(section, "get_temporal_anchor"):
        anchor = section.get_temporal_anchor()
    if anchor is None:
        # Lazy fallback: compute from Persona timezone if Phase 1 not run
        from poc.k1_poc.sessionstate.sections.temporal_context import (
            compute_temporal_anchor,
        )

        tz = "UTC"
        if hasattr(section, "get_all_preferences"):
            tz = section.get_all_preferences().get("timezone", "UTC")
        anchor = compute_temporal_anchor(tz).to_dict()
    if not anchor:
        return ""
    # Parse ISO to produce a clear human-readable time
    iso = anchor.get("local_time_iso", "")
    human_time = iso
    try:
        from datetime import datetime as _dt

        parsed = _dt.fromisoformat(iso)
        human_time = parsed.strftime("%I:%M %p on %A, %B %d, %Y")
    except Exception:
        pass
    lines = [
        f"CURRENT TIME: {human_time}",
        f"Day: {anchor.get('day_of_week', '')}",
        f"Time of day: {anchor.get('time_of_day', '')}",
        f"Weekend: {anchor.get('is_weekend', False)}",
        f"Timezone: {anchor.get('timezone', 'UTC')}",
        "Location: Denton, Texas",
    ]
    return "\n".join(lines)


def _render_temporal_context_slim(section: Any, cfg: SSReadConfig) -> str:
    """Slim: one-liner temporal summary."""
    anchor = None
    if hasattr(section, "get_temporal_anchor"):
        anchor = section.get_temporal_anchor()
    if anchor is None:
        from poc.k1_poc.sessionstate.sections.temporal_context import (
            compute_temporal_anchor,
        )

        anchor = compute_temporal_anchor("UTC").to_dict()
    if not anchor:
        return ""
    iso = anchor.get("local_time_iso", "")
    human_time = iso
    try:
        from datetime import datetime as _dt

        parsed = _dt.fromisoformat(iso)
        human_time = parsed.strftime("%I:%M %p %Z")
    except Exception:
        pass
    return f"CURRENT TIME: {human_time} -- {anchor.get('day_of_week', '')} {anchor.get('time_of_day', '')}"


# =========================================================================
# Section source map: virtual prompt sections backed by real SS sections
# Production: temporal_context -> multimodal (Section 5 sub-field)
# POC: temporal_context -> control (sub-field per skeleton.mmd NOTE line 834)
# =========================================================================
SECTION_SOURCE_MAP: dict[str, str] = {
    "temporal_context": "control",
}


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
    "temporal_context": (_render_temporal_context_full, _render_temporal_context_slim),
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

        Returns:
            BuiltContext with everything react_loop() needs.
        """
        messages = list(history_messages) if history_messages else []
        all_schemas = all_tool_schemas or []

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

        # Stage 7: Format and append scenario data from template
        if scenario_data:
            scenario_block = self._format_scenario_data(mode, scenario_data)
            if scenario_block:
                prompt_parts.append(scenario_block)

        # Stage 8: Read and render SS sections per mode config
        if ss is not None:
            ss_configs = SS_READ_CONFIGS.get(mode, [])
            ss_block = self._read_ss_sections(ss, ss_configs)
            if ss_block:
                prompt_parts.append(ss_block)

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

    def _format_scenario_data(self, mode: PromptMode, data: dict[str, Any]) -> str:
        """Format scenario data using SCENARIO_DATA_TEMPLATES.

        Uses the mode's template from SCENARIO_DATA_TEMPLATES and fills
        {placeholders} from the data dict. Falls back to key/value
        listing if template is empty or formatting fails.
        """
        if not data:
            return ""

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

        Compression strategy (V2 Section 26.9):
          1. Truncate from the end (SS sections/scenario data are last,
             lowest priority).
          2. Mark truncation point.

        This is a LAST RESORT. Normal mode-driven assembly should stay
        within budget. If compression is triggered, it indicates an
        unusually large SS state or prompt section set.
        """
        target_chars = self._max_context_tokens * self._chars_per_token
        if len(prompt) <= target_chars:
            return prompt
        return prompt[:target_chars] + "\n\n[Context truncated for budget]"

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
