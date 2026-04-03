"""TestStateReadAdapter -- test adapter for IStateReadPort [6.1.3].

Scripted persona + control snapshots. Read-only (MH-01).
"""

from __future__ import annotations

from typing import Any, Dict, List

from k1.model_hub.ports.state_read_port import StateSnapshot


class TestStateReadAdapter:
    """Deterministic IStateReadPort for testing.

    Configurable:
      - sections: Dict mapping section name -> section data.
        Pre-load with persona/control snapshots before test.

    Capture:
      - read_calls: All section lists requested via read().

    isinstance(adapter, IStateReadPort) == True.
    """

    def __init__(self, sections: Dict[str, Any] | None = None) -> None:
        self._sections: Dict[str, Any] = sections or {}
        self._read_calls: List[List[str]] = []

    async def read(self, sections: List[str]) -> StateSnapshot:
        """Return scripted sections, capture call."""
        self._read_calls.append(list(sections))
        data = {s: self._sections.get(s) for s in sections if s in self._sections}
        return StateSnapshot(sections=data)

    # -- Test inspection -------------------------------------------------------

    @property
    def read_calls(self) -> List[List[str]]:
        return [list(c) for c in self._read_calls]

    def set_section(self, name: str, data: Any) -> None:
        """Set or update a section for future reads."""
        self._sections[name] = data

    def reset(self) -> None:
        self._read_calls.clear()


__all__ = ["TestStateReadAdapter"]
