"""Per-session correlation context for feedback emission.

Tracks K0 entity references through a conversation turn so feedback
detectors and the emitter can stamp the right correlation block onto
the outgoing :class:`FeedbackEnvelopeV1`.

Cache lives in-process. For multi-replica deployments the caller can
swap :func:`get_context` / :func:`set_context` for a Redis-backed
implementation; the dataclass shape is stable.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field


@dataclass
class ConversationContext:
    """K0/K1 correlation accumulated through one conversation turn.

    Detectors read ``grounded_event_ids`` to point feedback at the
    memory the bot grounded its previous answer in. The emitter copies
    every populated field onto the wire envelope's ``correlation`` block.
    """

    session_id: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    wal_positions: list[int] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    recall_id: str | None = None
    response_id: str | None = None
    grounded_event_ids: list[str] = field(default_factory=list)
    last_user_message: str | None = None
    last_bot_response: str | None = None

    def record_recall(self, *, recall_id: str, event_ids: list[str]) -> None:
        """Call after K0 query.recall returns."""
        self.recall_id = recall_id
        # De-duplicating extend.
        seen = set(self.event_ids)
        for eid in event_ids:
            if eid not in seen:
                self.event_ids.append(eid)
                seen.add(eid)

    def record_response(self, *, response_id: str, grounded_event_ids: list[str]) -> None:
        """Call after the LLM emits a response with grounded memories."""
        self.response_id = response_id
        self.grounded_event_ids = list(grounded_event_ids)

    def record_user_message(self, message: str) -> None:
        self.last_user_message = message

    def record_bot_response(self, message: str) -> None:
        self.last_bot_response = message


_LOCK = threading.RLock()
_CACHE: dict[str, ConversationContext] = {}


def get_context(session_id: str) -> ConversationContext | None:
    """Return the cached context for ``session_id`` or ``None``."""
    with _LOCK:
        return _CACHE.get(session_id)


def set_context(session_id: str, context: ConversationContext) -> None:
    """Cache ``context`` under ``session_id`` (overwrites prior entry)."""
    with _LOCK:
        _CACHE[session_id] = context


def clear_context(session_id: str) -> None:
    """Remove the cached context for ``session_id`` (no-op if absent)."""
    with _LOCK:
        _CACHE.pop(session_id, None)


def reset_all_contexts() -> None:
    """Test seam: drop every cached context."""
    with _LOCK:
        _CACHE.clear()


__all__ = [
    "ConversationContext",
    "get_context",
    "set_context",
    "clear_context",
    "reset_all_contexts",
]
