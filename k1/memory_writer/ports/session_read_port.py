"""
k1.memory_writer.ports.session_read_port -- ISessionReadPort protocol.

Read-only async access to SessionState for Memory Writer v2.

CRITICAL INVARIANT (MW-01):
  NO write methods. This port is intentionally read-only. Memory Writer
  NEVER writes SessionState. Any implementor adding a write method
  violates the MW architectural contract.

CRITICAL INVARIANT (MW-02):
  Reads MUST be lock-free and complete in <1ms P99. Implementations
  must use the latest committed snapshot without triggering reconstruction.

SessionState sections read by MW (section-agnostic via snapshot_all):
  All sections from SessionState.ALL_SECTIONS are read EXCEPT those
  in MWConfig.skip_sections (default: telemetry, artifacts_warm).
  New sections are automatically included without config changes.

Production adapter: SessionReadAdapter in adapters/session_read_adapter.py
Test adapter: In adapters/test_adapters.py

References:
  - MW-01 (Memory Writer never writes SessionState)
  - MW-02 (Lock-free <1ms reads)
  - k1/orchestrator/ports/state_read_port.py (pattern reference)
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ISessionReadPort(Protocol):
    """
    Read-only async access to SessionState sections.

    MW-01: This port provides read-only access ONLY. There are
    NO write methods. Memory Writer MUST NOT circumvent this port.

    MW-02: All reads must be lock-free and complete in <1ms P99.
    Implementations must support concurrent reads from multiple
    asyncio tasks without external synchronization.
    """

    async def snapshot(
        self,
        sections: List[str],
    ) -> Dict[str, Any]:
        """
        Retrieve multiple SessionState sections in a single atomic read.

        This is the primary read method for MW. The ContextBuilder
        requests all 13 sections in one call for consistency.

        Args:
            sections: List of section names to retrieve
                (e.g. ["beliefs_active", "history_active", "affective_now"]).

        Returns:
            Dict mapping section name -> section data.
            Missing or unavailable sections are omitted from the result.

        Raises:
            AdapterError: If SessionState is unreachable.
        """
        ...  # pragma: no cover

    async def read_section(
        self,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single named section from SessionState.

        Used by PersonResolver for targeted active_persons lookup.

        Args:
            name: Section name (e.g. "beliefs_active", "persona").

        Returns:
            Section data as a dict, or None if the section is
            unavailable or does not exist.

        Raises:
            AdapterError: If SessionState is unreachable.
        """
        ...  # pragma: no cover

    async def list_sections(self) -> FrozenSet[str]:
        """
        Return the authoritative set of all SessionState section names.

        Delegates to ALL_SECTIONS at the adapter level. MW uses this
        to discover sections dynamically instead of hardcoding names.

        Returns:
            FrozenSet of section name strings.
        """
        ...  # pragma: no cover

    async def snapshot_all(
        self,
        exclude: FrozenSet[str] = frozenset(),
    ) -> Dict[str, Any]:
        """
        Read ALL SessionState sections in one call, minus excluded ones.

        This is the section-agnostic replacement for snapshot(sections).
        MW no longer enumerates section names — it reads everything except
        the skip list (default: telemetry, artifacts_warm).

        New sections added to SessionState are automatically included
        without MW config changes.

        Args:
            exclude: Section names to skip (e.g. {"telemetry", "artifacts_warm"}).

        Returns:
            Dict mapping section name -> section data.
            Missing or unavailable sections are omitted.
        """
        ...  # pragma: no cover

    async def read_archived_history(
        self,
        session_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Read archived ``history_active`` turns from the LOCAL COLD tier.

        This is the **enriched** read path for Memory Writer. It is
        EXPLICITLY NOT bound by MW-02 (<1ms P99). The hot path already
        delivers the live in-tier history via ``snapshot()`` /
        ``snapshot_all()``; this method exists so the session-batch
        extractor can recover archived turns that have been demoted
        out of the 16KB ``history_active`` window into LOCAL COLD
        SQLite, without bloating the hot/warm tier budgets.

        Returned dicts have the same shape as
        ``HistoryActiveSection.to_dict()["turns"][i]`` (turn_id,
        turn_number, user_message, assistant_response, timestamp_ms,
        ...). Order: oldest first. Duplicates across archive entries
        are de-duplicated by ``turn_id``.

        Implementations may return ``[]`` when no cold archive is
        configured (test/standalone mode). Callers MUST treat this
        path as best-effort and never fail on it.

        Args:
            session_id: Session whose archived history to fetch.
            limit: Soft cap on the number of turns returned
                (default 50, large enough for typical session-batch
                extraction without going wild on memory).

        Returns:
            List of turn dicts, oldest first. Empty list if no
            archive is available or the session has no archived turns.
        """
        ...  # pragma: no cover
