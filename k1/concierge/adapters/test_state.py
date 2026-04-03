"""
k1.concierge.adapters.test_state -- Test adapter for IStatePort.

In-memory section store. Mirrors the actual SSM read surface
(get_section, get_snapshot) as used by Concierge actors.
"""

from __future__ import annotations

import types
from typing import Any


class InMemoryStateAdapter:
    """Test adapter for IStatePort — in-memory section store."""

    def __init__(self) -> None:
        self._sections: dict[str, Any] = {}

    def get_section(self, name: str) -> Any:
        return self._sections.get(name)

    def get_snapshot(self) -> dict[str, Any]:
        return dict(self._sections)

    # -- Test helpers ----------------------------------------------------------

    def seed(self, name: str, section: Any) -> None:
        """Seed a section with an arbitrary object (e.g., a real Section or mock)."""
        self._sections[name] = section

    def seed_dict(self, name: str, data: dict[str, Any]) -> None:
        """Seed with a SimpleNamespace so .attr access works like real sections."""
        self._sections[name] = types.SimpleNamespace(**data)

    def clear(self) -> None:
        """Remove all seeded sections."""
        self._sections.clear()
