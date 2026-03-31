"""
k1.concierge.delta.overflow -- Section overflow handling for the delta pipeline.

V2 Design Ref: Section 5, HOT Tier Budget
V2 Design Ref: Section 5, Pruning Lifecycle
V2 Design Ref: Section 5, MutationGuard budget enforcement

When MutationGuard rejects a delta write due to section capacity,
the overflow handler evicts the oldest entries from the section
to make room, then the DeltaApplicator retries the write.

Eviction strategies per section (V2 Section 5, HOT Tier Budget):
    task_artifacts:  Evict oldest artifacts by timestamp_ns.
                     Budget: 4KB. Evict presented artifacts to WARM
                     after 10 turns.
    task_state:      Evict terminal tasks (COMPLETED, FAILED, CANCELLED).
                     Budget: 4KB. Clear after Front presents results.
    history_active:  Sliding window, keep last 20 entries.
                     Budget: 8KB. Evict older to WARM.
    beliefs_active:  Evict low-confidence beliefs.
                     Budget: 8KB. Evict after 20 turns without reinforcement.
    clarifications:  Clear resolved clarifications.
                     Budget: 4KB. Clear after 5 turns.

HOT Tier budgets (V2 Section 5):
    control=8KB, beliefs_active=8KB, scoreboard=6KB, history_active=8KB,
    clarifications=4KB, affective_now=4KB, narrative_active=4KB, meta=2KB,
    task_state=4KB, task_artifacts=4KB.  Total: 52KB.

The existing EvictionEngine (poc/k1_poc/sessionstate/eviction.py) handles
WARM->COLD eviction.  This handler covers HOT section overflow by
demoting oldest entries to WARM.
"""

from __future__ import annotations

import logging
from typing import Any

from k1.concierge.config import get_config

logger = logging.getLogger(__name__)


# =========================================================================
# Section budgets from V2 Section 5, HOT Tier Budget table
# Kept as module constants for backward compatibility; runtime reads from config
# =========================================================================

SECTION_BUDGETS: dict[str, int] = {
    "control": 8192,
    "beliefs_active": 8192,
    "scoreboard": 6144,
    "history_active": 8192,
    "clarifications": 4096,
    "affective_now": 4096,
    "narrative_active": 4096,
    "meta": 2048,
    "task_state": 4096,
    "task_artifacts": 4096,
}

HOT_BUDGET_TOTAL: int = 53248  # 52KB (V2 Section 5)

# Terminal task statuses eligible for eviction (V2 Section 5)
TERMINAL_TASK_STATUSES: frozenset[str] = frozenset({"COMPLETED", "FAILED", "CANCELLED"})

# Default sliding window size for history_active (V2 Section 5)
HISTORY_WINDOW_SIZE: int = 20


class SectionOverflowHandler:
    """Handles section capacity overflow by evicting oldest entries.

    Strategy per section (V2 Section 5, HOT Tier Budget):
        task_artifacts:  Evict oldest artifacts by creation timestamp.
        task_state:      Evict terminal tasks (COMPLETED/FAILED/CANCELLED).
        history_active:  Sliding window (keep last 20 entries).
        Default:         No eviction (section does not support it).

    The handler is used by DeltaApplicator's evict_fn callback when
    MutationGuard rejects a write.

    Attributes:
        _budgets:       Per-section budget in bytes.
        _eviction_log:  Audit trail of eviction actions.
        _total_evicted: Total number of entries evicted.
    """

    __slots__ = ("_budgets", "_eviction_log", "_total_evicted", "_history_window")

    def __init__(
        self,
        section_budgets: dict[str, int] | None = None,
        history_window: int | None = None,
    ) -> None:
        _overflow_cfg = get_config().delta.overflow
        self._budgets = section_budgets or dict(_overflow_cfg.section_budgets)
        self._history_window = (
            history_window if history_window is not None else _overflow_cfg.history_window_size
        )
        self._eviction_log: list[dict[str, Any]] = []
        self._total_evicted: int = 0
        logger.info(
            "SectionOverflowHandler initialized (sections=%d, history_window=%d)",
            len(self._budgets),
            self._history_window,
        )

    def evict_oldest(
        self,
        section: str,
        current_data: dict[str, Any],
        needed_bytes: int,
    ) -> tuple[dict[str, Any], list[str]]:
        """Evict oldest entries from a section to free space.

        Dispatches to section-specific eviction strategy.

        Args:
            section:       Target section name.
            current_data:  Current section data dict (key -> value).
            needed_bytes:  How many bytes the caller needs freed.

        Returns:
            (remaining_data, evicted_keys): Updated data dict and
            list of keys that were evicted (for WARM demotion).
        """
        if section == "task_artifacts":
            return self._evict_artifacts(current_data, needed_bytes)
        if section == "task_state":
            return self._evict_terminal_tasks(current_data)
        if section == "history_active":
            return self._evict_oldest_turns(current_data, self._history_window)
        # No eviction strategy for this section
        return current_data, []

    def _evict_artifacts(
        self,
        data: dict[str, Any],
        needed_bytes: int,
    ) -> tuple[dict[str, Any], list[str]]:
        """Evict oldest artifacts by timestamp_ns.

        V2 Section 5: "Evict presented artifacts to WARM after 10 turns."
        Here we evict by oldest timestamp_ns first until we've freed
        enough bytes to satisfy the write.
        """
        if not data:
            return data, []

        # Sort by timestamp_ns (oldest first)
        items = sorted(
            data.items(),
            key=lambda kv: (kv[1].get("timestamp_ns", 0) if isinstance(kv[1], dict) else 0),
        )

        evicted_keys: list[str] = []
        freed = 0
        for key, value in items:
            freed += len(str(value).encode("utf-8"))
            evicted_keys.append(key)
            if freed >= needed_bytes:
                break

        remaining = {k: v for k, v in data.items() if k not in set(evicted_keys)}
        self._record_eviction("task_artifacts", evicted_keys, freed)
        return remaining, evicted_keys

    def _evict_terminal_tasks(
        self,
        data: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        """Evict terminal tasks (COMPLETED, FAILED, CANCELLED).

        V2 Section 5: "Clear completed/failed tasks after Front
        presents results."  Active tasks (DISPATCHED, IN_PROGRESS,
        SUSPENDED) are never evicted.
        """
        evicted: list[str] = []
        remaining: dict[str, Any] = {}
        for key, value in data.items():
            status = value.get("status", "") if isinstance(value, dict) else ""
            if status in TERMINAL_TASK_STATUSES:
                evicted.append(key)
            else:
                remaining[key] = value

        if evicted:
            freed = sum(len(str(data[k]).encode("utf-8")) for k in evicted)
            self._record_eviction("task_state", evicted, freed)
        return remaining, evicted

    def _evict_oldest_turns(
        self,
        data: dict[str, Any],
        keep: int,
    ) -> tuple[dict[str, Any], list[str]]:
        """Sliding window: keep only the last N turns.

        V2 Section 5: "Sliding window: keep last 20 entries, evict
        older to WARM."  Turns are sorted by key (turn-001, turn-002...).
        """
        if len(data) <= keep:
            return data, []

        items = sorted(data.items(), key=lambda kv: kv[0])
        evicted_keys = [k for k, _ in items[:-keep]]
        remaining = dict(items[-keep:])

        freed = sum(len(str(data[k]).encode("utf-8")) for k in evicted_keys)
        self._record_eviction("history_active", evicted_keys, freed)
        return remaining, evicted_keys

    def _record_eviction(
        self,
        section: str,
        evicted_keys: list[str],
        freed_bytes: int,
    ) -> None:
        """Record an eviction in the audit log."""
        self._total_evicted += len(evicted_keys)
        self._eviction_log.append(
            {
                "section": section,
                "evicted_count": len(evicted_keys),
                "evicted_keys": evicted_keys,
                "freed_bytes": freed_bytes,
            }
        )
        logger.info(
            "Evicted %d entries from %s, freed ~%d bytes",
            len(evicted_keys),
            section,
            freed_bytes,
        )

    @property
    def eviction_log(self) -> list[dict[str, Any]]:
        """Read-only copy of the eviction audit trail."""
        return list(self._eviction_log)

    @property
    def total_evicted(self) -> int:
        """Total number of entries evicted across all sections."""
        return self._total_evicted

    def get_budget(self, section: str) -> int | None:
        """Get the budget for a section in bytes.

        Args:
            section: Section name.

        Returns:
            Budget in bytes, or None if the section has no budget.
        """
        return self._budgets.get(section)
