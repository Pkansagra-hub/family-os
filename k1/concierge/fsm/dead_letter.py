"""
k1.concierge.fsm.dead_letter -- Dead-letter payload schema and helpers.

M2 E2.2.1: Defines the canonical dead-letter envelope payload
used when the FSM guard matrix rejects an event, when pending
results overflow or expire, or when weave queues overflow.

Dead-letter reasons:
    invalid_transition   -- Guard matrix rejected event for current state.
    re_entrant_drop      -- User input arrived during DISPATCHING.
    cancel_incompatible  -- Task cancel in non-cancellable state.
    overflow             -- Queue exceeded max depth, oldest evicted.
    expired              -- Pending result exceeded TTL.
    weave_overflow       -- Weave batcher queue exceeded max depth.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeadLetterPayload:
    """Structured payload for dead-letter bus events.

    Every dead-letter envelope carries this schema so consumers
    can classify, count, and optionally retry rejected events.
    """

    original_topic: str
    original_envelope_id: int
    reason: str
    fsm_state_at_rejection: str
    turn_number: int = 0
    task_id: str = ""
    original_payload_summary: str = ""
    rejected_at_ns: int = field(default_factory=time.monotonic_ns)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON transport."""
        return {
            "original_topic": self.original_topic,
            "original_envelope_id": self.original_envelope_id,
            "reason": self.reason,
            "fsm_state_at_rejection": self.fsm_state_at_rejection,
            "turn_number": self.turn_number,
            "task_id": self.task_id,
            "original_payload_summary": self.original_payload_summary,
            "rejected_at_ns": self.rejected_at_ns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeadLetterPayload:
        """Deserialize from a plain dict."""
        return cls(
            original_topic=data.get("original_topic", ""),
            original_envelope_id=data.get("original_envelope_id", 0),
            reason=data.get("reason", ""),
            fsm_state_at_rejection=data.get("fsm_state_at_rejection", ""),
            turn_number=data.get("turn_number", 0),
            task_id=data.get("task_id", ""),
            original_payload_summary=data.get("original_payload_summary", ""),
            rejected_at_ns=data.get("rejected_at_ns", 0),
        )


def build_dead_letter_payload(
    *,
    original_topic: str,
    original_envelope_id: int,
    reason: str,
    fsm_state: str,
    turn_number: int = 0,
    task_id: str = "",
    payload_summary: str = "",
) -> DeadLetterPayload:
    """Convenience factory for DeadLetterPayload."""
    return DeadLetterPayload(
        original_topic=original_topic,
        original_envelope_id=original_envelope_id,
        reason=reason,
        fsm_state_at_rejection=fsm_state,
        turn_number=turn_number,
        task_id=task_id,
        original_payload_summary=payload_summary[:500],
    )
