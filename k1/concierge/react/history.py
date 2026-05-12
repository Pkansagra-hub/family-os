"""
Chat History Helpers -- build_chat_history() and build_chat_history_for_back()
==============================================================================

V2 Design Ref: Section 7.7 (build_chat_history helper)

Extracts the last N user/assistant turns from history_active as
ModelMessage objects for the LLM's messages array. This provides
short-term conversational context separate from long-term context
(Session State in the system prompt).
"""

from __future__ import annotations

import logging
from typing import Any

from k1.concierge.llm.types import ModelMessage

logger = logging.getLogger(__name__)


def build_chat_history(
    history_active: list[Any],
    window: int = 3,
    *,
    include_weave: bool = False,
) -> list[ModelMessage]:
    """Extract last N user/assistant turn pairs as real chat messages.

    Only includes user messages and final responses (not acks, weaves,
    clarifications, HITL, proactive, error entries). This gives the
    LLM natural conversational flow without bloating the context with
    internal mechanics.

    For anything beyond this window, the LLM reads Session State:
      - beliefs_active for stated facts
      - narrative_active for thread history
      - task_artifacts for completed work
      - scoreboard for topic tracking

    Args:
        history_active: List of TypedHistoryEntry objects (duck typed).
            Each must have .entry_type (str) and .text (str) attributes.
        window: Number of user/assistant PAIRS to include.
            So window=3 means up to 6 messages (3 user + 3 assistant).
            Front: varies by mode (SS_READ_CONFIGS).
            Back: fixed at 5 entries.
        include_weave: M6 E6.2 (C10) -- when True, also include prior
            ``weave`` entries as assistant messages.  Used by the front
            handler in WEAVE mode so the LLM sees previously-injected
            async results when generating the next weave response.

    Returns:
        List of ModelMessage with role="user" or role="assistant".
    """
    allowed_types = ("user", "final", "proactive")
    if include_weave:
        allowed_types = allowed_types + ("weave",)
    recent = [e for e in history_active if e.entry_type in allowed_types]
    messages: list[ModelMessage] = []
    for entry in recent[-(window * 2) :]:
        role = "user" if entry.entry_type == "user" else "assistant"
        messages.append(ModelMessage(role=role, content=entry.text))
    logger.debug(
        "build_chat_history: window=%d, candidates=%d, returned=%d messages, include_weave=%s",
        window,
        len(recent),
        len(messages),
        include_weave,
    )
    return messages


def build_chat_history_for_back(
    history_active: list[Any],
    window: int = 3,
) -> list[ModelMessage]:
    """Extract last N decision-relevant messages for Back actor.

    Back gets a different view: includes hitl_response entries (user
    answers to HITL questions) and truncates text to 500 chars. Back
    needs just enough to resolve references, not full conversational
    context.

    Args:
        history_active: List of TypedHistoryEntry objects (duck typed).
            Each must have .entry_type (str) and .text (str) attributes.
        window: Number of entries (NOT pairs) to include.
            Fixed at 3-5 for Back.

    Returns:
        List of ModelMessage with role="user" or role="assistant".
    """
    recent = [e for e in history_active if e.entry_type in ("user", "final", "hitl_response")]
    messages: list[ModelMessage] = []
    for entry in recent[-window:]:
        role = "user" if entry.entry_type in ("user", "hitl_response") else "assistant"
        messages.append(ModelMessage(role=role, content=entry.text[:500]))
    logger.debug(
        "build_chat_history_for_back: window=%d, candidates=%d, returned=%d messages",
        window,
        len(recent),
        len(messages),
    )
    return messages
