"""
k1.concierge.adapters.null_state_reader -- Null ISessionStateReader for startup tier.

Shared Fabric (SIM-D-34/D-35) needs ISessionStateReader at construction,
but real adapters are per-session. This null adapter returns empty for all
reads — no session state available at startup tier.

Used by: Shared Fabric instance (for Orchestrator + Planner capability execution).

Protocol: k1.fabric.ports.state_reader.ISessionStateReader
Gap: SIM-GAP-47
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from k1.fabric.ports.state_reader import SessionSnapshot


class NullSessionStateReaderAdapter:
    """Null ISessionStateReader — all reads return empty.

    Satisfies ISessionStateReader structurally. Used by shared Fabric
    at startup tier when no session context is available.
    """

    def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]:
        return None

    def read_sections(self, session_id: str, names: List[str]) -> Dict[str, Any]:
        return {}

    def get_snapshot(self, session_id: str) -> SessionSnapshot:
        return SessionSnapshot(session_id=session_id)
