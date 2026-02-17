"""TestStateReadAdapter -- in-memory IStateReadPort implementation (SS16.2.4).

Implements the IStateReadPort Protocol (SS15.5) with:
- Constructor injection of preset snapshot and sections
- Capture-mode recording of all read_sections calls
- Zero I/O, purely in-memory section intersection
- No write methods (PLAN-01 enforced at interface level)
- Protocol-structural compliance with IStateReadPort

File location: tests/k1/planner/adapters/ (SS30.3)
Never importable from production code.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from k1.fabric.ports.state_reader import SessionSnapshot


class TestStateReadAdapter:
    """In-memory IStateReadPort for deterministic testing (SS16.2.4).

    Constructor
    -----------
    preset_snapshot : Optional[SessionSnapshot]
        Snapshot returned by get_snapshot(). If None, returns empty.
    preset_sections : Dict[str, Dict[str, Any]]
        Section data keyed by section name. read_sections() intersects
        requested sections with this dict -- missing sections omitted.

    Internal state
    --------------
    _read_log : List[List[str]]
        Capture list recording requested section names per call.
    _snapshot_log : List[str]
        Capture list recording trace_ids from get_snapshot() calls.
    """

    def __init__(
        self,
        preset_snapshot: Optional[SessionSnapshot] = None,
        preset_sections: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self._preset_snapshot: Optional[SessionSnapshot] = preset_snapshot
        self._preset_sections: Dict[str, Dict[str, Any]] = dict(preset_sections or {})
        self._read_log: List[List[str]] = []
        self._snapshot_log: List[str] = []

    # ------------------------------------------------------------------
    # IStateReadPort Protocol methods
    # ------------------------------------------------------------------

    async def read_sections(
        self,
        sections: List[str],
        trace_id: str = "",
    ) -> SessionSnapshot:
        """Return snapshot with keys from sections intersected with preset.

        Missing sections are omitted (not None-valued), matching the
        production adapter contract.
        """
        self._read_log.append(list(sections))

        matched: Dict[str, Dict[str, Any]] = {}
        for name in sections:
            if name in self._preset_sections:
                matched[name] = self._preset_sections[name]

        return SessionSnapshot(
            sections=matched,
            section_names=sorted(matched.keys()),
        )

    async def get_snapshot(self, trace_id: str = "") -> SessionSnapshot:
        """Return preset snapshot or empty SessionSnapshot."""
        self._snapshot_log.append(trace_id)
        if self._preset_snapshot is not None:
            return self._preset_snapshot
        return SessionSnapshot()

    # ------------------------------------------------------------------
    # Assertion / introspection helpers (test-only)
    # ------------------------------------------------------------------

    @property
    def read_log(self) -> List[List[str]]:
        """Read-only access to read_sections() call log."""
        return list(self._read_log)

    @property
    def snapshot_log(self) -> List[str]:
        """Read-only access to get_snapshot() call log."""
        return list(self._snapshot_log)

    @property
    def read_count(self) -> int:
        """Number of read_sections() calls."""
        return len(self._read_log)

    def assert_read_count(self, n: int) -> None:
        """Assert read_sections() was called exactly n times."""
        assert self.read_count == n, f"Expected {n} read_sections calls, got {self.read_count}"

    def assert_sections_requested(self, call_index: int, expected: List[str]) -> None:
        """Assert sections requested in a specific call."""
        assert call_index < len(self._read_log), (
            f"Call index {call_index} out of range " f"(only {len(self._read_log)} calls recorded)"
        )
        actual = self._read_log[call_index]
        assert sorted(actual) == sorted(expected), (
            f"Call {call_index}: expected sections {sorted(expected)}, " f"got {sorted(actual)}"
        )

    def get_all_requested_sections(self) -> List[str]:
        """Return flat list of all ever-requested section names (with dupes)."""
        return [s for call in self._read_log for s in call]
