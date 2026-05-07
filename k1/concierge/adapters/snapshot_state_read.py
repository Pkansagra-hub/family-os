"""
k1.concierge.adapters.snapshot_state_read -- SnapshotStateReadAdapter for shared Planner.

Shared Planner (SIM-D-25) serves ALL sessions. The real
SessionStateReadAdapter is session-locked at construction (SIM-GAP-49).

Fix (SIM-D-38): Before each pipeline run, PlannerAgent calls
adapter.bind(request.context) to set the active snapshot.
read_sections() then returns filtered sections from that snapshot.

Used by: Shared PlannerAgent.

Protocol: k1.planner.ports.state_read_port.IStateReadPort
Decision: SIM-D-38
Gap: SIM-GAP-49
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from k1.fabric.ports.state_reader import SessionSnapshot


class SnapshotStateReadAdapter:
    """IStateReadPort that reads from a bound SessionSnapshot.

    PlannerAgent calls ``bind(request.context)`` before each pipeline
    run. ``read_sections()`` returns filtered sections from that snapshot.

    If no snapshot is bound, returns an empty SessionSnapshot.
    """

    def __init__(self) -> None:
        self._snapshot: Optional[SessionSnapshot] = None

    def bind(self, snapshot: Optional[SessionSnapshot]) -> None:
        """Set the active snapshot. Called before each pipeline run."""
        self._snapshot = snapshot

    async def read_sections(
        self,
        sections: List[str],
        trace_id: str = "",
    ) -> SessionSnapshot:
        if self._snapshot is None:
            return SessionSnapshot()
        # Filter to requested sections only
        filtered: Dict[str, Dict[str, Any]] = {
            name: data for name, data in self._snapshot.sections.items() if name in sections
        }
        return SessionSnapshot(
            session_id=self._snapshot.session_id,
            sections=filtered,
            timestamp_ms=self._snapshot.timestamp_ms,
        )
