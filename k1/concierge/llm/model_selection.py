"""
Model Selection Strategy -- Capability-Based Routing
=====================================================

V2 Design Ref: Section 10.3 (model selection, actor-based routing)

The caller expresses INTENT ("fast", "smart", "cheap"), NOT model name.
This decouples callers from provider-specific model identifiers.
When new models arrive, update the tables once -- zero caller changes.
"""

from __future__ import annotations

import logging

from k1.concierge.config import get_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model selection tables
# ---------------------------------------------------------------------------
# Module-level constants kept for backward compatibility.
# Runtime code reads from the central config singleton.

MODEL_SELECTION_TABLE: dict[tuple[str, str], str] = {
    # (capability, actor) -> model
    # Routing: Gemini 3 Flash preview for tools/structured work, 3.1 Pro
    # preview for heavy reasoning/planning, 3.1 Flash-Lite preview for chat.
    (
        "CHAT",
        "front",
    ): "gemini-3.1-flash-lite-preview",  # conversational warmth, fast
    (
        "TOOL_CALL",
        "front",
    ): "gemini-3-flash-preview",  # cognitive tool selection
    (
        "TOOL_CALL",
        "back",
    ): "gemini-3-flash-preview",  # action tool execution
    (
        "STRUCTURED",
        "front",
    ): "gemini-3-flash-preview",  # dispatch intent parsing
    (
        "STRUCTURED",
        "back",
    ): "gemini-3-flash-preview",  # final answer formatting
    (
        "REASON",
        "back",
    ): "gemini-3.1-pro-preview",  # multi-step reasoning
    ("REASON", "front"): "gemini-3.1-pro-preview",  # complex reasoning
    (
        "CHAT",
        "back",
    ): "gemini-3.1-flash-lite-preview",  # error reports (internal, lightweight)
    (
        "STREAM",
        "front",
    ): "gemini-3.1-flash-lite-preview",  # streaming ack/response (speed)
    (
        "TOOL_CALL",
        "planner",
    ): "gemini-3.1-pro-preview",  # planner reasoning
    ("CHAT", "planner"): "gemini-3.1-pro-preview",  # planner chat
}

MODEL_HINT_OVERRIDES: dict[str, str] = {
    "fast": "gemini-3.1-flash-lite-preview",
    "smart": "gemini-3-flash-preview",
    "cheap": "gemini-3.1-flash-lite-preview",
    "thinking": "gemini-3.1-pro-preview",
    "pro": "gemini-3.1-pro-preview",
    "flash": "gemini-3-flash-preview",
}

DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"


def _get_selection_table() -> dict[tuple[str, str], str]:
    """Build flat (capability, actor) -> model dict from config."""
    nested = get_config().llm.model_selection_table
    table: dict[tuple[str, str], str] = {}
    for cap, actors in nested.items():
        for actor, model in actors.items():
            table[(cap, actor)] = model
    return table


def _get_hint_overrides() -> dict[str, str]:
    """Return hint overrides from config."""
    return get_config().llm.model_hint_overrides


def _get_default_model() -> str:
    """Return fallback model from config."""
    return get_config().llm.default_model


# ---------------------------------------------------------------------------
# Selection algorithm
# ---------------------------------------------------------------------------


def select_model(
    capability: str,
    actor: str,
    hint: str | None = None,
    default: str | None = None,
) -> str:
    """Select model based on capability, actor, and hint.

    Selection priority:
      1. If model_hint is set and exists in MODEL_HINT_OVERRIDES, use it.
      2. If model_hint looks like a full model name (contains "-"), use directly.
      3. Look up (capability, actor) in MODEL_SELECTION_TABLE.
      4. Fall back to default model.

    Args:
        capability: "CHAT" | "TOOL_CALL" | "STRUCTURED" | "STREAM" | "REASON"
        actor: "front" | "back" | "planner" | agent name
        hint: "fast" | "smart" | "cheap" | specific model name | None
        default: fallback model if no match found

    Returns:
        Concrete model identifier string.
    """
    fallback = default or _get_default_model()
    hint_overrides = _get_hint_overrides()
    selection_table = _get_selection_table()

    # 1. Check hint overrides
    if hint:
        if hint in hint_overrides:
            return hint_overrides[hint]
        # 2. Hint looks like a full model name
        if "-" in hint:
            return hint

    # 3. Table lookup
    key = (capability.upper() if capability else "", actor.lower() if actor else "")
    if key in selection_table:
        logger.debug(
            "select_model  capability=%s actor=%s hint=%s -> %s (table)",
            capability,
            actor,
            hint,
            selection_table[key],
        )
        return selection_table[key]

    # 4. Try capability-only fallback (any actor)
    for (cap, _act), model in selection_table.items():
        if cap == key[0]:
            logger.debug(
                "select_model  capability=%s actor=%s -> %s (cap-fallback)",
                capability,
                actor,
                model,
            )
            return model

    logger.debug(
        "select_model  capability=%s actor=%s -> %s (default)",
        capability,
        actor,
        fallback,
    )
    return fallback
