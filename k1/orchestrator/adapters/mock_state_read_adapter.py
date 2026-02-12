"""
k1.orchestrator.adapters.mock_state_read_adapter -- MockStateReadAdapter (6.1.11).

Test/mock adapter for IStateReadPort.

Design:
  - In-memory section store: session_id -> section_name -> data dict.
  - All reads logged to read_log for assertion.
  - Convenience helpers: set_section, set_safety_band, set_user_preferences.
  - get_snapshot() builds SessionSnapshot from stored sections.
  - Intentionally has write helpers (for test setup). Does NOT violate
    ORCH-01 -- this is a mock, not production code.

References:
  - Issue 6.1.11 in orchestrator-implementation-plan.md
  - k1/orchestrator/ports/state_read_port.py (IStateReadPort)

Exports:
  MockStateReadAdapter
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from k1.fabric.ports.state_reader import SessionSnapshot
from k1.fabric.types import SafetyBand

# ---------------------------------------------------------------------------
# 6.1.11 -- MockStateReadAdapter
# ---------------------------------------------------------------------------


class MockStateReadAdapter:
    """
    Test IStateReadPort adapter with in-memory section storage.

    Pre-populate per-session section data via ``set_section()``,
    ``set_safety_band()``, or ``set_user_preferences()``.

    All read calls are logged to ``read_log`` for assertion.
    """

    def __init__(self) -> None:
        self.sections: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.read_log: List[tuple] = []

    # ------------------------------------------------------------------
    # IStateReadPort.read_section
    # ------------------------------------------------------------------

    async def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        """Return stored section data or None."""
        self.read_log.append((session_id, section))
        return self.sections.get(session_id, {}).get(section)

    # ------------------------------------------------------------------
    # IStateReadPort.read_sections
    # ------------------------------------------------------------------

    async def read_sections(
        self,
        session_id: str,
        names: List[str],
    ) -> Dict[str, Any]:
        """Return dict of requested sections (missing sections omitted)."""
        result: Dict[str, Any] = {}
        session_data = self.sections.get(session_id, {})
        for name in names:
            self.read_log.append((session_id, name))
            if name in session_data:
                result[name] = session_data[name]
        return result

    # ------------------------------------------------------------------
    # IStateReadPort.get_snapshot
    # ------------------------------------------------------------------

    async def get_snapshot(
        self,
        session_id: str,
    ) -> SessionSnapshot:
        """Build SessionSnapshot from all stored sections for session_id."""
        session_data = self.sections.get(session_id, {})
        self.read_log.append((session_id, "__snapshot__"))
        return SessionSnapshot(
            session_id=session_id,
            sections=dict(session_data),
            timestamp_ms=int(time.time() * 1000),
        )

    # ------------------------------------------------------------------
    # Test helpers -- data setup
    # ------------------------------------------------------------------

    def set_section(
        self,
        session_id: str,
        name: str,
        data: Dict[str, Any],
    ) -> None:
        """Store section data for a session."""
        self.sections.setdefault(session_id, {})[name] = data

    def set_safety_band(
        self,
        session_id: str,
        band: SafetyBand,
    ) -> None:
        """Shorthand: set control section with safety_band."""
        self.set_section(session_id, "control", {"safety_band": band})

    def set_user_preferences(
        self,
        session_id: str,
        prefs: dict,
    ) -> None:
        """Shorthand: set persona section with user preferences."""
        self.set_section(session_id, "persona", prefs)

    # ------------------------------------------------------------------
    # Test helpers -- assertions
    # ------------------------------------------------------------------

    def assert_read(self, section: str, times: int = 1) -> None:
        """Assert that *section* was read exactly *times* times."""
        actual = sum(1 for _, s in self.read_log if s == section)
        assert actual == times, f"Expected section '{section}' read {times} time(s), got {actual}"

    def clear(self) -> None:
        """Clear all stored sections and logs."""
        self.sections.clear()
        self.read_log.clear()
