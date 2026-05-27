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
    PromptMode,
    get_max_iterations,
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
    augmented_configs: list[SSReadConfig] = []
    for cfg in _configs:
        if cfg.section == "temporal":
            continue
        augmented_configs.append(cfg)
        if cfg.section == "affective_now":
            augmented_configs.append(SSReadConfig("trust_level", "full"))
    SS_READ_CONFIGS[_mode] = augmented_configs


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
    """Format referents (salience-ranked), topic, user intent, QUD, commitments."""
    lines: list[str] = []
    # Primary topic first -- anchors the rest of the block
    if hasattr(section, "get_primary_topic"):
        topic = section.get_primary_topic()
        if topic:
            lines.append(f"Topic: {topic.name}")
    # User intent (when classifier has set it)
    user_intent = getattr(section, "_user_intent", None) or getattr(section, "user_intent", None)
    if isinstance(user_intent, str) and user_intent:
        lines.append(f"User intent: {user_intent}")
    elif isinstance(user_intent, dict) and user_intent.get("intent"):
        lines.append(f"User intent: {user_intent['intent']}")
    # Referents: salience-ranked, top 5, with entity_type when present
    if hasattr(section, "_referents") and section._referents:
        refs = list(section._referents.values())
        refs.sort(key=lambda r: getattr(r, "salience", 0.0), reverse=True)
        for ref in refs[:5]:
            text = getattr(ref, "text", "")
            sal = getattr(ref, "salience", 0.0)
            etype = getattr(ref, "entity_type", "") or getattr(ref, "type", "")
            tag = f" [{etype}]" if etype else ""
            lines.append(f"- referent: {text}{tag} (salience: {sal:.2f})")
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
    """Slim: topic + top-3 salient referents + open commitment count."""
    parts: list[str] = []
    if hasattr(section, "get_primary_topic"):
        topic = section.get_primary_topic()
        if topic:
            parts.append(f"Topic: {topic.name}")
    if hasattr(section, "_referents") and section._referents:
        refs = list(section._referents.values())
        refs.sort(key=lambda r: getattr(r, "salience", 0.0), reverse=True)
        top = [getattr(r, "text", "") for r in refs[:3] if getattr(r, "text", "")]
        if top:
            parts.append("Top refs: " + ", ".join(top))
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
    """Full: active thread + lifecycle state + arc stage + resumption hint."""
    lines: list[str] = []
    thread = getattr(section, "_primary_thread", None)
    if thread is None and hasattr(section, "primary_thread"):
        thread = section.primary_thread
    if thread:
        title = getattr(thread, "title", "")
        state = getattr(thread, "state", "") or getattr(thread, "status", "")
        header = f"Thread: {title}"
        if state:
            header += f" [{state}]"
        lines.append(header)
        goal = getattr(thread, "goal", "")
        if goal:
            lines.append(f"Goal: {goal}")
        entities = getattr(thread, "related_entities", None)
        if entities:
            lines.append(f"Entities: {', '.join(entities)}")
        hint = getattr(thread, "resumption_hint", "")
        if hint:
            lines.append(f"Resumption: {hint}")
    arc = getattr(section, "_arc", None) or getattr(section, "arc", None)
    if arc is not None:
        stage = getattr(arc, "stage", "")
        if stage:
            lines.append(f"Arc stage: {stage}")
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
    """Full: emotion, intensity, V/A + arc trajectory + recent emotion drift."""
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

    # Emotional ARC -- progression matters more than the snapshot.
    # Renders prior turn emotions so Front can read drift (neutral -> playful).
    recent = getattr(section, "recent_emotions", None) or []
    if recent:
        try:
            arc_labels = [getattr(s, "emotion", "") for s in recent if getattr(s, "emotion", "")]
        except Exception:
            arc_labels = []
        if arc_labels:
            arc_labels = arc_labels[-5:] + [emotion]
            lines.append("Arc: " + " -> ".join(arc_labels))
    trajectory = getattr(section, "trajectory", None)
    if trajectory is not None:
        traj_name = getattr(trajectory, "name", str(trajectory))
        lines.append(f"Trajectory: {traj_name}")
    if getattr(section, "empathy_needed", False):
        lines.append("Posture cue: empathy_needed=true (lead with warmth)")
    if getattr(section, "celebration_appropriate", False):
        lines.append("Posture cue: celebration_appropriate=true (mirror their lift)")

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


def _render_trust_level_full(section: Any, cfg: SSReadConfig) -> str:
    """Full: trust score/band + latest calibration signal for Front."""
    score = getattr(section, "trust_score", None)
    confidence = getattr(section, "confidence", None)
    band = getattr(section, "band", "steady")
    stance = getattr(section, "stance", "calibrating")
    last_signal = getattr(section, "_last_signal", "")
    last_reason = getattr(section, "_last_reason", "")
    recent = getattr(section, "_recent_signals", None) or []
    lines = [
        f"Trust score: {score if score is not None else 0.5}",
        f"Band: {band}",
        f"Confidence: {confidence if confidence is not None else 0.5}",
        f"Stance: {stance}",
    ]
    if last_signal:
        lines.append(f"Latest signal: {last_signal}")
    if last_reason:
        lines.append(f"Reason: {last_reason}")
    if recent:
        labels = [str(item.get("signal") or "") for item in recent[-3:] if isinstance(item, dict)]
        labels = [item for item in labels if item]
        if labels:
            lines.append("Recent signals: " + " -> ".join(labels))
    lines.append(
        "Guidance: low/guarded trust means be explicit and ask before assumptions; "
        "steady/high trust means stay concise without skipping policy gates."
    )
    return "\n".join(lines)


def _render_trust_level_slim(section: Any, cfg: SSReadConfig) -> str:
    """Slim: compact trust score/band."""
    score = getattr(section, "trust_score", 0.5)
    band = getattr(section, "band", "steady")
    return f"Trust: {score} ({band})"


# Control-section fields that are pure telemetry / storage bookkeeping
# and carry no meaning for the Front LLM. These are stripped before the
# control snapshot is seated into the Active Work block.
_CONTROL_NOISE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "tier",
        "budget_bytes",
        "current_size_bytes",
        "utilization_pct",
        "can_evict",
        "schema_version",
        "last_updated_ms",
        "session_id",
        "current_turn_id",
        "turn_count",
        "agent_count",
        "is_locked",
    }
)


def _render_control_full(section: Any, cfg: SSReadConfig) -> str:
    """Full: meaningful control-flow fields only.

    Strips storage bookkeeping (bytes, utilization, schema_version, ids,
    counts) that the LLM cannot act on. Pretty-prints nested dicts as
    ``key.subkey: value`` lines (avoids Python ``repr`` leaking into the
    prompt).
    """
    if hasattr(section, "get_metadata"):
        meta = section.get_metadata()
        lines: list[str] = []
        for key, val in meta.items():
            if key in _CONTROL_NOISE_FIELDS:
                continue
            if isinstance(val, dict):
                if not val:
                    continue
                for sub_key, sub_val in val.items():
                    lines.append(f"{key}.{sub_key}: {sub_val}")
            elif isinstance(val, (list, tuple)):
                if not val:
                    continue
                lines.append(f"{key}: {', '.join(str(v) for v in val)}")
            elif val in (None, "", 0):
                continue
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
    "trust_level": (_render_trust_level_full, _render_trust_level_slim),
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

        role_contract = PROMPT_SECTIONS.get("FRONT_ROLE_CONTRACT", "")
        behavior_parts: list[str] = []
        final_output_rule = ""

        # Stage 1: Select prompt sections from MODE_SECTIONS. Iteration 1
        # seats FRONT_ROLE_CONTRACT before the Situation Frame; all other
        # static sections become behavior/tool guidance after CURRENT EVENT.
        section_keys = MODE_SECTIONS.get(mode, [])
        for key in section_keys:
            if key == "FRONT_ROLE_CONTRACT":
                continue
            section_text = PROMPT_SECTIONS.get(key, "")
            if section_text:
                if key == "FINAL_OUTPUT_RULE":
                    final_output_rule = section_text
                else:
                    behavior_parts.append(section_text)
        logger.debug(
            "  Stage 1  sections=%d keys=%s",
            len(section_keys),
            section_keys,
        )

        # Stage 2: Append mode-specific example from MODE_EXAMPLES
        example_text = MODE_EXAMPLES.get(mode, "")
        if example_text:
            behavior_parts.append(example_text)
            logger.debug("  Stage 2  example appended (len=%d)", len(example_text))

        # Stage 3: Append affect tone modifier (skip neutral -- empty string)
        tone_block = AFFECT_TONE_BLOCKS.get(affect_band.band, "")
        if tone_block:
            behavior_parts.append(tone_block)

        # Stage 3b: Append affect x mode interaction block
        interaction_block = get_affect_mode_interaction(mode.name, affect_band.band)
        if interaction_block:
            behavior_parts.append(interaction_block)
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
            behavior_parts.append(depth_block)

        # Stage 5: Append domain rules (only for applicable modes)
        # RC-3 fix: consult is_domain_applicable() to avoid leaking
        # domain rules into modes where they are irrelevant.
        if domain and is_domain_applicable(domain, mode.value):
            domain_block = get_domain_rules(domain)
            if domain_block:
                behavior_parts.append(domain_block)

        # Stage 6: Append anti-pattern subset
        if mode in ANTI_PATTERN_KEYS:
            ap_key = ANTI_PATTERN_KEYS[mode]
            ap_text = PROMPT_SECTIONS.get(ap_key, "")
            if ap_text:
                behavior_parts.append(ap_text)

        active_actor_block = ""
        visible_space_block = ""
        if grounding_capsule is not None:
            active_actor_block = self._build_active_actor_block(grounding_capsule)
            visible_space_block = self._build_visible_space_block(grounding_capsule)

        # Stage 7: Format and append scenario data from template
        scenario_payload = scenario_data
        if (
            scenario_data
            and (active_actor_block or visible_space_block)
            and mode in (PromptMode.STANDARD, PromptMode.INTERRUPT)
        ):
            scenario_payload = dict(scenario_data)
            scenario_payload["_suppress_active_member_block"] = True

        scenario_block = ""
        if scenario_payload:
            scenario_block = self._format_scenario_data(mode, scenario_payload)

        # Stage 8: Read and render SS sections per mode config into the
        # Situation Frame seats instead of a late standalone block.
        # M6.E1.I4: when an OPP-6 compressed_context is present we replace
        # the raw history_active SS read with the compressed block at the
        # conversation-state position.
        interaction_profile_block = ""
        conversation_state_block = ""
        active_work_block = ""
        trust_calibration_block = ""
        if ss is not None:
            ss_configs = SS_READ_CONFIGS.get(mode, [])
            interaction_profile_block = self._read_ss_body_for_sections(
                ss,
                ss_configs,
                {"persona"},
            )
            trust_calibration_block = self._read_ss_body_for_sections(
                ss,
                ss_configs,
                {"trust_level"},
            )
            conversation_configs = [
                cfg
                for cfg in ss_configs
                if cfg.section
                in {
                    "history_active",
                    "beliefs_active",
                    "scoreboard",
                    "clarifications",
                    "narrative_active",
                }
            ]
            if compressed_context_block:
                conversation_configs = [
                    cfg for cfg in conversation_configs if cfg.section != "history_active"
                ]
            conversation_parts: list[str] = []
            conversation_body = self._read_ss_body(ss, conversation_configs)
            if conversation_body:
                conversation_parts.append(conversation_body)
            if compressed_context_block:
                conversation_parts.append(compressed_context_block)
                logger.debug(
                    "  Stage 8  history_active replaced by OPP-6 compressed_context (len=%d)",
                    len(compressed_context_block),
                )
            conversation_state_block = "\n\n".join(conversation_parts)
            active_work_block = self._read_ss_body_for_sections(
                ss,
                ss_configs,
                {"control", "task_state", "task_artifacts"},
            )
        elif compressed_context_block:
            conversation_state_block = compressed_context_block

        # Stage 9: Apply affect modifiers + pre-call budget check
        base_max_iter = self._get_max_iterations(mode, affect_band)
        modifiers = compute_affect_modifiers(affect_band)
        max_iter, _ = apply_affect_modifiers(modifiers, base_max_iter, behavior_parts)
        logger.debug(
            "  Stage 9  base_iter=%d adjusted_iter=%d skip_refine=%s",
            base_max_iter,
            max_iter,
            modifiers.skip_refine_affect,
        )

        # Stage 9.5: Build Iteration 1/2 Situation Frame seats.
        live_grounding_blocks = self._build_grounding_live_blocks(grounding_projection)
        if not live_grounding_blocks:
            now_block = self._build_now_block(ss)
            if now_block:
                live_grounding_blocks = [now_block]
        now_block_text = ""
        place_block_text = ""
        grounding_meta_block_text = ""
        for live_block in live_grounding_blocks:
            if live_block.startswith("== NOW =="):
                now_block_text = live_block
            elif live_block.startswith("== PLACE =="):
                place_block_text = live_block
            elif live_block.startswith("== GROUNDING =="):
                grounding_meta_block_text = live_block
            elif live_block.startswith("== TIME =="):
                now_block_text = live_block
            elif live_block.startswith("== PLACE AND DEVICE =="):
                place_block_text = live_block
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
        if identity_block_text:
            logger.debug(
                "  Stage 9.5  OPP-7 identity_block seated (len=%d)", len(identity_block_text)
            )
        if capsule_text:
            logger.debug(
                "  Stage 9.5  capsule split: conscience_promoted=%s body_len=%d",
                bool(conscience_block_text),
                len(capsule_text),
            )

        situation_frame = self._build_situation_frame(
            active_actor_block=active_actor_block,
            visible_space_block=visible_space_block,
            conscience_block=conscience_block_text,
            now_block=now_block_text,
            place_block=place_block_text,
            identity_block=identity_block_text,
            reference_profile_block=capsule_text,
            affective_posture_block=affect_state_block,
            trust_calibration_block=trust_calibration_block,
            interaction_profile_block=interaction_profile_block,
            conversation_state_block=conversation_state_block,
            active_work_block=active_work_block,
            grounding_meta_block=grounding_meta_block_text,
        )
        current_event = self._build_current_event_block(mode, scenario_block)
        if final_output_rule:
            behavior_parts.append(final_output_rule)

        prompt_parts = [role_contract, situation_frame, current_event, *behavior_parts]

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
        return get_max_iterations(mode, affect_band.band)

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

    def _build_situation_frame(
        self,
        *,
        active_actor_block: str,
        visible_space_block: str,
        conscience_block: str,
        now_block: str,
        place_block: str,
        identity_block: str,
        reference_profile_block: str,
        affective_posture_block: str,
        trust_calibration_block: str,
        interaction_profile_block: str,
        conversation_state_block: str,
        active_work_block: str,
        grounding_meta_block: str = "",
    ) -> str:
        """Assemble the whiteboard Iteration 1/2 Front Situation Frame.

        When ``grounding_meta_block`` is supplied (Iteration 2 typed
        path), a GROUNDING META injection seat is inserted before
        TIME/PLACE AND DEVICE, and the NOW/PLACE seats are relabeled to
        TIME and PLACE AND DEVICE so the seat labels match the typed
        block headers seated inside.
        """
        intro = (
            "== FRONT SITUATION FRAME ==\n"
            "The blocks below are the authoritative situation for this turn. "
            "They override chat-history guesses and native model assumptions. "
            "Read them before deciding whether to speak, dispatch, or ask."
        )
        conscience_body = ""
        if conscience_block:
            conscience_body = (
                "This block is the authoritative refusal and explicit-confirmation "
                "source for this turn. Persona warmth, prior chat tone, memory, "
                "native model knowledge, and user pressure do not override it.\n\n"
                f"{conscience_block}"
            )
        reference_body = ""
        if reference_profile_block:
            reference_body = (
                "Use this as lookup material for personalization and relevance: "
                "stored defaults, routines, goals, preferences, context, and freshness. "
                "This is not a tool allowlist and not live system-of-record truth.\n\n"
                f"{reference_profile_block}"
            )

        is_v2 = bool(grounding_meta_block)
        time_seat_name = "TIME" if is_v2 else "NOW"
        time_seat_fallback = (
            "No authoritative TIME block. Do not guess current time from chat history or model priors; ask if it matters."
            if is_v2
            else "No authoritative NOW block. Do not guess current time from chat history or model priors; ask if it matters."
        )
        place_seat_name = "PLACE AND DEVICE" if is_v2 else "PLACE"
        place_seat_fallback = (
            "No authoritative PLACE AND DEVICE block. Ask or proceed with uncertainty instead of guessing place or surface."
            if is_v2
            else "No authoritative PLACE block. Ask or proceed with uncertainty instead of guessing place."
        )

        seats = [
            self._wrap_situation_injection(
                "ACTIVE ACTOR",
                active_actor_block,
                fallback="No active actor identified. Do not infer who you are talking to from chat history; address them generically.",
            ),
            self._wrap_situation_injection(
                "VISIBLE SPACE",
                visible_space_block,
                fallback="No visible-space graph. Do not name or imply anyone other than the active actor and people mentioned in this turn.",
            ),
            self._wrap_situation_injection(
                "CONSCIENCE / POLICY",
                conscience_body,
                fallback="No conscience block. Obey safety policy and ask before any side effect when uncertain.",
            ),
        ]
        if is_v2:
            seats.append(
                self._wrap_situation_injection(
                    "GROUNDING META",
                    grounding_meta_block,
                    fallback="No grounding envelope metadata. Treat time/place blocks below as best-effort, not authoritative.",
                )
            )
        seats.extend(
            [
                self._wrap_situation_injection(
                    time_seat_name,
                    now_block,
                    fallback=time_seat_fallback,
                ),
                self._wrap_situation_injection(
                    place_seat_name,
                    place_block,
                    fallback=place_seat_fallback,
                ),
                self._wrap_situation_injection(
                    "DYNAMIC IDENTITY CONTEXT",
                    identity_block,
                    fallback="No dynamic identity overlay. Continue with active actor, visible space, persona, and conversation state.",
                ),
                self._wrap_situation_injection(
                    "REFERENCE PROFILE",
                    reference_body,
                    fallback="No reference profile. Personalize only from visible state, memory results, and the current conversation.",
                ),
                self._wrap_situation_injection(
                    "AFFECTIVE POSTURE",
                    affective_posture_block,
                ),
                self._wrap_situation_injection(
                    "TRUST CALIBRATION",
                    trust_calibration_block,
                    fallback="No trust calibration yet. Be warm and explicit by default; never use trust as permission to bypass policy or side-effect gates.",
                ),
                self._wrap_situation_injection(
                    "INTERACTION PROFILE",
                    interaction_profile_block,
                    fallback="No persona overrides this turn. Default to the role contract and current affect for tone, length, and formality.",
                ),
                self._wrap_situation_injection(
                    "CONVERSATION STATE",
                    conversation_state_block,
                    fallback="No rendered beliefs, scoreboard, or narrative yet. Use the chat history below as the only conversational context.",
                ),
                self._wrap_situation_injection(
                    "ACTIVE WORK",
                    active_work_block,
                    fallback="No active tasks or artifacts. Do not claim work is in progress or complete.",
                ),
                self._wrap_situation_injection(
                    "MEMORY AND AUTHORITY BOUNDARY",
                    self._memory_authority_boundary_block(),
                ),
            ]
        )
        return "\n\n".join([intro, *seats])

    @staticmethod
    def _wrap_situation_injection(
        name: str,
        body: str,
        *,
        source: str = "",
        fallback: str = "",
    ) -> str:
        # ``source`` is developer-only provenance kept on the signature for
        # logging and back-compat; it must NEVER be emitted to the LLM.
        content = body.strip() if body else fallback
        parts = [f"-- INJECT: {name} --"]
        if content:
            parts.append(content)
        parts.append(f"-- END INJECT: {name} --")
        return "\n".join(parts)

    @staticmethod
    def _memory_authority_boundary_block() -> str:
        return (
            "For recent conversation, rely on the messages and rendered history already in this prompt. "
            "For durable historical context, routines, preferences, and prior events, call recall_memory. "
            "For any live system-of-record read or write, route through dispatch_task or a safe capability invocation; "
            "never answer live state from memory. To find what capabilities exist for a user intent, call "
            "discover_capabilities, and to invoke a known safe capability directly, call invoke_capability. "
            "Your own general knowledge is available as background framing only; it is not authoritative for facts "
            "about this user, their space, or any live system.\n\n"
            "Rules:\n"
            "- Memory is historical context, not live state.\n"
            "- Live records, schedules, account data, prices, device state, availability, and external truth require dispatch_task or a safe capability.\n"
            "- If the user asks to add what you know as general context, preserve provenance in reference_context.\n"
            "- Do not store capability-owned live records as beliefs."
        )

    @staticmethod
    def _build_current_event_block(mode: PromptMode, scenario_block: str) -> str:
        lines = [
            "== CURRENT EVENT ==",
            f"Prompt mode: {mode.value}",
            "This is the event to answer right now. The user's actual message is the last entry in the chat history below; do not ask them to repeat it.",
        ]
        if scenario_block:
            lines.extend(["", scenario_block])
        return "\n".join(lines)

    def _read_ss_body_for_sections(
        self,
        ss: Any,
        configs: list[SSReadConfig],
        sections: set[str],
    ) -> str:
        return self._read_ss_body(ss, [cfg for cfg in configs if cfg.section in sections])

    def _read_ss_body(self, ss: Any, configs: list[SSReadConfig]) -> str:
        block = self._read_ss_sections(ss, configs)
        prefix = "== SESSION STATE ==\n\n"
        if block.startswith(prefix):
            return block[len(prefix) :]
        return block

    # -----------------------------------------------------------------
    # Stage 9.5 helpers — promote live signals + split capsule
    # -----------------------------------------------------------------

    @staticmethod
    def _build_grounding_live_blocks(projection: Any) -> list[str]:
        """Render Front live grounding blocks from a GroundingProjection.

        Iteration switch (``prompt.front_prompt_iteration``):
        - ``v1`` -> legacy ``== NOW ==`` / ``== PLACE ==`` rendered blocks.
        - ``v2`` -> typed ``== GROUNDING ==`` / ``== TIME ==`` /
          ``== PLACE AND DEVICE ==`` blocks sourced directly from the typed
          ``GroundingProjection``. No fallback chain when projection is
          present (M4.I11).
        """
        if projection is None:
            return []
        iteration = "v1"
        try:
            iteration = (
                str(getattr(get_config().prompt, "front_prompt_iteration", "v1")).strip().lower()
            )
        except Exception:
            iteration = "v1"
        try:
            if iteration == "v2":
                from k1.grounding.service.prompt_block_renderer import (
                    render_grounding_meta_block_v2,
                    render_place_and_device_block_v2,
                    render_time_block_v2,
                )

                blocks = [
                    render_grounding_meta_block_v2(projection),
                    render_time_block_v2(projection),
                    render_place_and_device_block_v2(projection),
                ]
                return [block for block in blocks if block]

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
        """Consolidated ``== AFFECTIVE POSTURE ==`` block.

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
        intensity = None
        confidence = None
        if ss is not None:
            section = _safe_get_ss_section(ss, "affective_now")
            if section is not None:
                emotion = getattr(section, "current_emotion", None)
                valence = getattr(section, "valence", None)
                arousal = getattr(section, "arousal", None)
            intensity = getattr(section, "intensity", None)
            confidence = getattr(section, "confidence", None)

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

        lines = ["== AFFECTIVE POSTURE ==", f"Band: {band.upper()}"]
        raw_parts = []
        if emotion:
            raw_parts.append(f"emotion={emotion}")
        if valence is not None:
            raw_parts.append(f"valence={valence}")
        if arousal is not None:
            raw_parts.append(f"arousal={arousal}")
        if intensity is not None:
            raw_parts.append(f"intensity={intensity}")
        if confidence is not None:
            raw_parts.append(f"confidence={confidence}")
        if raw_parts:
            lines.append(f"Raw: {' '.join(raw_parts)}")
        lines.append(f"Tone rule: {tone}")
        if length_hint:
            lines.append(f"Response length: {length_hint}")
        return "\n".join(lines)

    @staticmethod
    def _build_active_actor_block(grounding_capsule: Any) -> str:
        """Compose the ACTIVE ACTOR seat from the typed self block.

        Wording is address-the-user: this block tells YOU (the model) who
        the human in front of you is. It never says YOU are that person.
        """
        self_block = getattr(grounding_capsule, "self_block", "") or ""
        if not self_block:
            return ""
        parts = [
            "The person you are talking to right now is identified below. "
            "Address them by name and calibrate to their role and style; "
            "do not infer a different actor from chat history.",
            self_block,
            "Rules:\n"
            "- You are the Concierge speaking TO this person; you are not them.\n"
            "- Address and calibrate to this actor.\n"
            "- If display_name is absent, stay natural and avoid forced naming.",
        ]
        return "\n\n".join(parts)

    @staticmethod
    def _build_visible_space_block(grounding_capsule: Any) -> str:
        """Compose the VISIBLE SPACE seat from the typed space graph block."""
        space_graph_block = getattr(grounding_capsule, "space_graph_block", "") or ""
        if not space_graph_block:
            return ""
        parts = [
            "These are the people, roles, and relationships visible in the "
            'user\'s space this turn. Resolve relationship language ("my kid", '
            '"my wife", "the boss") through this graph before naming anyone.',
            space_graph_block,
            "Rules:\n"
            "- Before naming, referencing, or inferring another actor, look here.\n"
            "- If an actor or attribute is not visible here, do not disclose it.\n"
            "- If a reference is unresolved, ask or use a generic noun.",
        ]
        return "\n\n".join(parts)

    @staticmethod
    def _render_capsule_without_conscience(grounding_capsule: Any) -> str:
        """Render capsule WITHOUT:
        - ``conscience_block`` (promoted near SAFETY rules)
        - ``self_block`` (promoted to ACTIVE ACTOR when M7 field is set)
        - ``space_graph_block`` (promoted to VISIBLE SPACE when M7 field is set)

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
