"""
k1.concierge.fsm.idempotency -- Idempotency ledger for FSM envelope dedup.

M2 E2.3.2 / E2.3.5: Replaces the unbounded _seen_user_input_ids set
with an LRU-based ledger that:
  - Tracks processed envelope IDs to prevent duplicate processing.
  - Uses OrderedDict for O(1) lookup + LRU eviction.
  - Evicts OLDEST entry when at capacity (not clear-all).
  - Configurable max_entries (default 500 from config).

Used by ConciergeController for:
  - User input dedup (replaces _seen_user_input_ids)
  - Task lifecycle idempotency (task.complete, task.failed, task.suspended, task.resume)
"""

from __future__ import annotations

from collections import OrderedDict


class IdempotencyLedger:
    """Tracks processed envelope IDs to prevent duplicate processing.

    Uses envelope_id as the idempotency key. Maintains a bounded
    LRU cache of recently processed IDs. When capacity is reached,
    the OLDEST entry is evicted (not all entries).
    """

    __slots__ = ("_processed", "_max_entries")

    def __init__(self, max_entries: int = 500) -> None:
        self._processed: OrderedDict[int, int] = OrderedDict()
        self._max_entries = max_entries

    def check_and_mark(self, envelope_id: int, turn_number: int) -> bool:
        """Return True if this is a NEW event. False if duplicate.

        If new, the envelope_id is recorded with the current turn_number.
        If the ledger is at capacity, the oldest entry is evicted.
        """
        if envelope_id in self._processed:
            return False
        self._processed[envelope_id] = turn_number
        if len(self._processed) > self._max_entries:
            self._processed.popitem(last=False)
        return True

    def contains(self, envelope_id: int) -> bool:
        """Check if an envelope_id has been processed (without marking)."""
        return envelope_id in self._processed

    @property
    def size(self) -> int:
        """Number of entries currently tracked."""
        return len(self._processed)

    @property
    def max_entries(self) -> int:
        """Configured maximum capacity."""
        return self._max_entries

    def reset(self) -> None:
        """Clear all tracked entries."""
        self._processed.clear()


__all__ = [
    "IdempotencyLedger",
]
