"""
poc.k1_poc.fsm.dead_letter_consumer -- Reconciliation consumer for
dead-letter events.

M2 E2.2.4: Subscribes to TOPIC_DEAD_LETTER, records events for
observability dashboards, and tracks dead-letter rates per topic
and per FSM state to detect systematic routing problems.

Usage:
    consumer = DeadLetterConsumer(bus)
    # ... later ...
    print(consumer.total_dead_letters)
    print(consumer.snapshot())
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import IBus
from poc.k1_poc.bus.topics import TOPIC_DEAD_LETTER
from poc.k1_poc.fsm.dead_letter import DeadLetterPayload

logger = logging.getLogger(__name__)


class DeadLetterConsumer:
    """Subscribes to TOPIC_DEAD_LETTER and records events for observability.

    The consumer maintains:
      - A list of all dead-letter payloads (capped for memory safety).
      - Counters by reason and by FSM state at rejection.

    It does NOT retry events. Retry logic is deferred to M9 (ledger-primary).
    """

    __slots__ = (
        "_bus",
        "_events",
        "_counts_by_reason",
        "_counts_by_state",
        "_counts_by_topic",
        "_handle",
        "_max_events",
    )

    def __init__(self, bus: IBus, *, max_events: int = 1000) -> None:
        self._bus = bus
        self._events: list[DeadLetterPayload] = []
        self._counts_by_reason: dict[str, int] = defaultdict(int)
        self._counts_by_state: dict[str, int] = defaultdict(int)
        self._counts_by_topic: dict[str, int] = defaultdict(int)
        self._max_events = max_events
        self._handle = bus.subscribe(TOPIC_DEAD_LETTER, self._on_dead_letter)

    # -----------------------------------------------------------------
    # Handler
    # -----------------------------------------------------------------

    def _on_dead_letter(self, envelope: Envelope) -> None:
        """Process an incoming dead-letter envelope."""
        try:
            raw = json.loads(envelope.payload) if envelope.payload else {}
            dl = DeadLetterPayload.from_dict(raw)
        except Exception:
            logger.error(
                "DeadLetterConsumer: failed to parse dead-letter payload, " "envelope_id=%d",
                envelope.envelope_id,
            )
            return

        # Cap stored events for memory safety
        if len(self._events) < self._max_events:
            self._events.append(dl)

        self._counts_by_reason[dl.reason] += 1
        self._counts_by_state[dl.fsm_state_at_rejection] += 1
        self._counts_by_topic[dl.original_topic] += 1

        logger.warning(
            "DeadLetterConsumer: reason=%s state=%s topic=%s envelope_id=%d",
            dl.reason,
            dl.fsm_state_at_rejection,
            dl.original_topic,
            dl.original_envelope_id,
        )

    # -----------------------------------------------------------------
    # Query API
    # -----------------------------------------------------------------

    @property
    def total_dead_letters(self) -> int:
        """Total number of dead-letter events received."""
        return sum(self._counts_by_reason.values())

    @property
    def events(self) -> list[DeadLetterPayload]:
        """All recorded dead-letter payloads (up to max_events)."""
        return list(self._events)

    def get_events_by_reason(self, reason: str) -> list[DeadLetterPayload]:
        """Filter recorded events by reason."""
        return [e for e in self._events if e.reason == reason]

    def get_events_by_state(self, state: str) -> list[DeadLetterPayload]:
        """Filter recorded events by FSM state at rejection."""
        return [e for e in self._events if e.fsm_state_at_rejection == state]

    def get_events_by_topic(self, topic: str) -> list[DeadLetterPayload]:
        """Filter recorded events by original topic."""
        return [e for e in self._events if e.original_topic == topic]

    def snapshot(self) -> dict[str, Any]:
        """Return a summary dict for observability dashboards."""
        return {
            "total_dead_letters": self.total_dead_letters,
            "counts_by_reason": dict(self._counts_by_reason),
            "counts_by_state": dict(self._counts_by_state),
            "counts_by_topic": dict(self._counts_by_topic),
            "stored_events": len(self._events),
            "max_events": self._max_events,
        }

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------

    def reset(self) -> None:
        """Clear all recorded events and counters."""
        self._events.clear()
        self._counts_by_reason.clear()
        self._counts_by_state.clear()
        self._counts_by_topic.clear()
