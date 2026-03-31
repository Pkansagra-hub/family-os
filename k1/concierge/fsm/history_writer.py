"""
k1.concierge.fsm.history_writer -- HistoryWriter & history converters.

V2 Design Ref: Section 5 (TypedHistoryEntry, history_active section)

The FSM is the Single Writer for history_active (V2 Section 5).
This module provides:
  - HistoryWriter: Stateless writer that creates TypedHistoryEntry objects
    and appends them to the controller's history list.
  - history_to_front_messages(): Convert typed entries to Front LLM chat format.
  - history_to_back_context(): Convert typed entries to Back LLM condensed format.

The TypedHistoryEntry class itself is defined in controller.py (where it is
used inline). This module wraps the write logic and provides the read/conversion
APIs for DynamicPromptBuilder (M09) and back_handler (M07).

What each LLM sees (V2 Section 5):
  Front LLM: Last 20 entries, all types, formatted as user/assistant messages.
  Back LLM:  Last 5 entries, filtered to "user", "final", "hitl_response" only.
  FSM:       All entries, all types.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from k1.concierge.config import get_config
from k1.concierge.fsm.controller import TypedHistoryEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (backward-compat; runtime reads from config)
# ---------------------------------------------------------------------------

# Default history windows (V2 Section 5)
FRONT_HISTORY_WINDOW = 20
BACK_HISTORY_WINDOW = 5

# Entry types that map to "user" role in chat messages
USER_ENTRY_TYPES = frozenset({"user", "hitl_response"})

# Entry types that map to "assistant" role in chat messages
ASSISTANT_ENTRY_TYPES = frozenset(
    {
        "final",
        "weave",
        "clarification",
        "hitl_request",
        "error",
        "proactive",
    }
)

# Entry types that Back LLM sees (decision-relevant only)
BACK_RELEVANT_TYPES = frozenset({"user", "final", "hitl_response"})


# ---------------------------------------------------------------------------
# HistoryWriter
# ---------------------------------------------------------------------------


class HistoryWriter:
    """Writes TypedHistoryEntry objects at event boundaries.

    The FSM calls this writer at each event boundary to create and record
    history entries. This is a thin wrapper that creates TypedHistoryEntry
    and appends it to the provided history list.

    Event-to-entry mapping (V2 Section 5):
      | Event                          | entry_type       | source  |
      |--------------------------------|------------------|---------|
      | user.input received            | "user"           | "user"  |
      | k1.response.final.v1           | "final"          | "front" |
      | Weave response                 | "weave"          | "front" |
      | clarification request          | "clarification"  | "front" |
      | task.suspended (HITL relay)    | "hitl_request"   | "back"  |
      | User answers HITL              | "hitl_response"  | "user"  |
      | task.failed presented          | "error"          | "front" |
      | Proactive fill                 | "proactive"      | "system"|
    """

    def __init__(self, history: list[TypedHistoryEntry]) -> None:
        """Initialize writer with a reference to the controller's history list.

        Args:
            history: The controller's mutable history list. Entries are
                     appended in place.
        """
        self._history = history

    @property
    def entries(self) -> list[TypedHistoryEntry]:
        """All entries written so far."""
        return self._history

    @property
    def count(self) -> int:
        """Number of entries written."""
        return len(self._history)

    def write(
        self,
        turn_number: int,
        entry_type: str,
        role: str,
        text: str = "",
        source: str = "",
        task_id: str | None = None,
        timestamp_ms: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> TypedHistoryEntry:
        """Create and append a TypedHistoryEntry.

        Args:
            turn_number: Current turn (incremented on each user.input).
            entry_type: One of the 9 entry types.
            role: "user" or "assistant" or "system".
            text: The actual content.
            source: "user", "front", "back", or "system".
            task_id: Associated task (for weave, hitl, error entries).
            timestamp_ms: Event timestamp (defaults to now).
            metadata: Optional dict with emotion, intent, tool_calls_summary, etc.

        Returns:
            The created TypedHistoryEntry.
        """
        entry = TypedHistoryEntry(
            turn_number=turn_number,
            entry_type=entry_type,
            role=role,
            text=text,
            timestamp_ms=timestamp_ms or int(time.time() * 1000),
            source=source,
            task_id=task_id,
            metadata=metadata,
        )
        self._history.append(entry)
        logger.debug(
            "HistoryWriter: wrote entry type=%s, turn=%d, role=%s",
            entry_type,
            turn_number,
            role,
        )
        return entry

    def get_entries_by_turn(self, turn_number: int) -> list[TypedHistoryEntry]:
        """Return all entries for a specific turn number."""
        return [e for e in self._history if e.turn_number == turn_number]

    def get_entries_by_type(self, entry_type: str) -> list[TypedHistoryEntry]:
        """Return all entries of a specific type."""
        return [e for e in self._history if e.entry_type == entry_type]

    def last_n(self, n: int) -> list[TypedHistoryEntry]:
        """Return the last N entries."""
        return self._history[-n:] if n > 0 else []


# ---------------------------------------------------------------------------
# History converters (V2 Section 5)
# ---------------------------------------------------------------------------


def history_to_front_messages(
    entries: list[TypedHistoryEntry],
    window: int | None = None,
) -> list[dict[str, str]]:
    """Convert TypedHistoryEntry list to Front LLM chat messages.

    Front sees the last `window` entries formatted as alternating
    user/assistant messages. Entry types are preserved as prefixes
    so the model can distinguish acks from finals, HITL questions
    from regular responses, and weave results from primary answers.

    Args:
        entries: Full history entry list.
        window: Number of entries to include (default from config).

    Returns:
        List of {"role": "user"|"assistant", "content": text} dicts.
    """
    if window is None:
        window = get_config().fsm.front_history_window

    # Entry types that get a distinguishing prefix
    _ENTRY_PREFIX: dict[str, str] = {
        "hitl_request": "[clarification question] ",
        "hitl_response": "[clarification answer] ",
        "weave": "[async result] ",
        "error": "[error] ",
        "proactive": "[proactive] ",
        "clarification": "[clarification] ",
    }

    messages: list[dict[str, str]] = []
    for entry in entries[-window:]:
        prefix = _ENTRY_PREFIX.get(entry.entry_type, "")
        content = f"{prefix}{entry.text}" if prefix else entry.text
        if entry.entry_type in USER_ENTRY_TYPES:
            messages.append({"role": "user", "content": content})
        elif entry.entry_type in ASSISTANT_ENTRY_TYPES:
            messages.append({"role": "assistant", "content": content})
        # System entries (artifact, cancel_confirmed) are skipped in chat
    return messages


def history_to_back_context(
    entries: list[TypedHistoryEntry],
    window: int | None = None,
) -> list[dict[str, Any]]:
    """Convert TypedHistoryEntry list to Back LLM chat messages.

    Back only sees decision-relevant types: "user", "final", "hitl_response".
    Returns proper chat messages (role/content) so the Back LLM can
    continue the conversation and resolve references like "do it" or
    "the cheaper one".

    Args:
        entries: Full history entry list.
        window: Number of relevant entries to include (default from config).

    Returns:
        List of {"role": "user"|"assistant", "content": str} dicts.
    """
    if window is None:
        window = get_config().fsm.back_history_window
    filtered = [e for e in entries if e.entry_type in BACK_RELEVANT_TYPES]
    messages: list[dict[str, Any]] = []
    for e in filtered[-window:]:
        role = "user" if e.entry_type in ("user", "hitl_response") else "assistant"
        messages.append({"role": role, "content": e.text[:500]})
    return messages
