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

SessionState sections read by MW (13 of 15, skip telemetry + artifacts_warm):
  Hot (10):  beliefs_active, beliefs_history, history_active, history_recent,
             affective_now, affective_baseline, narrative_active, scoreboard,
             control, persona
  Warm (3):  task_state, ifl, meta
  Skipped:   telemetry, artifacts_warm

Production adapter: SessionReadAdapter in adapters/session_read_adapter.py
Test adapter: In adapters/test_adapters.py

References:
  - MW-01 (Memory Writer never writes SessionState)
  - MW-02 (Lock-free <1ms reads)
  - k1/orchestrator/ports/state_read_port.py (pattern reference)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


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
