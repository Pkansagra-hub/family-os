"""
MWSessionReader -- Reads SessionState via ISessionReadPort.

Section-agnostic: reads all sections except config.skip_sections.
Returns raw dict. No section-name hardcoding.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from k1.memory_writer.config import MWConfig
from k1.memory_writer.invariants import assert_mw02_read_latency
from k1.memory_writer.ports.session_read_port import ISessionReadPort

log = logging.getLogger(__name__)


class MWSessionReader:
    """Reads SessionState sections via ISessionReadPort.

    Section-agnostic: reads all sections except config.skip_sections.
    Returns raw dict. No section-name hardcoding.
    """

    __slots__ = ("_port", "_config")

    def __init__(self, port: ISessionReadPort, config: MWConfig) -> None:
        self._port = port
        self._config = config

    async def read_snapshot(self) -> Dict[str, Any]:
        """Read all non-skipped sections in one atomic snapshot.

        Uses snapshot_all(exclude=config.skip_sections) from Phase 0.
        Measures latency for MW-02 enforcement.
        """
        start = time.perf_counter_ns()
        snapshot = await self._port.snapshot_all(exclude=self._config.skip_sections)
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        assert_mw02_read_latency(elapsed_ms)
        return snapshot

    async def read_snapshot_enriched(
        self,
        session_id: str,
        history_limit: int = 50,
    ) -> Dict[str, Any]:
        """Read snapshot AND merge cold-archived ``history_active`` turns.

        Used by the session-batch extractor (NOT the per-turn hot path).
        MW-02 latency invariant is INTENTIONALLY NOT enforced here -- this
        path explicitly trades latency for richer context. The hot tier's
        16KB ``history_active`` window holds at most 25 turns; once they
        demote into LOCAL COLD they vanish from the live snapshot. This
        method recovers them so the LLM session-batch prompt sees the full
        conversation arc, without raising any tier budget.

        Merge rules:
          * Cold-archive turns come first (older), live hot turns last.
          * De-duplicated by ``turn_id`` (live wins on collision).
          * If the port has no cold archive wired (or anything fails),
            falls back to the plain snapshot -- never raises.

        Args:
            session_id: Session whose archived history to recover.
            history_limit: Soft cap on archived turns to merge in.

        Returns:
            The snapshot dict, with ``history_active.turns`` extended
            to include archived turns ahead of the live ones.
        """
        snapshot = await self._port.snapshot_all(exclude=self._config.skip_sections)

        # Best-effort: recover cold turns.
        try:
            archived: List[Dict[str, Any]] = await self._port.read_archived_history(
                session_id, limit=history_limit
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.debug("enriched read: archived history fetch failed: %s", exc)
            archived = []

        if not archived:
            return snapshot

        history = snapshot.get("history_active")
        if not isinstance(history, dict):
            history = {}
            snapshot["history_active"] = history
        live_turns = history.get("turns", []) if isinstance(history.get("turns"), list) else []
        live_ids = {
            t.get("turn_id")
            for t in live_turns
            if isinstance(t, dict) and t.get("turn_id")
        }
        # Cold first, dedupe against live.
        merged: List[Dict[str, Any]] = [
            t for t in archived if t.get("turn_id") not in live_ids
        ]
        merged.extend(live_turns)
        history["turns"] = merged
        history["turn_count"] = len(merged)
        history["enriched_from_cold"] = True
        return snapshot
