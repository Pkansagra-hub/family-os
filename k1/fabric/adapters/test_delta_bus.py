"""
k1.fabric.adapters.test_delta_bus -- TestDeltaBusAdapter (5.2.7).

In-memory delta capture for testing agent delta emission.

Design:
  - ``emit_delta()`` stores every call as a ``CapturedDelta`` record.
  - ``drain()`` returns and clears all captured deltas.
  - ``get_deltas()`` returns captured deltas without clearing.
  - Filter helpers: by agent_id, delta_type, section.
  - ``assert_emitted()`` for test assertions.
  - Thread-safe via RLock.
  - No real Delta Bus dependency.

Structural subtyping:
  Satisfies IDeltaBusPort protocol without inheriting from it.

Exports:
  TestDeltaBusAdapter
  CapturedDelta
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Captured delta record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapturedDelta:
    """Record of an emitted delta for test assertions."""

    agent_id: str = ""
    delta_type: str = ""
    section: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "agent_id": self.agent_id,
            "delta_type": self.delta_type,
            "section": self.section,
            "data": dict(self.data),
            "timestamp_ms": self.timestamp_ms,
        }


# ---------------------------------------------------------------------------
# TestDeltaBusAdapter
# ---------------------------------------------------------------------------


class TestDeltaBusAdapter:
    """
    In-memory delta capture stub for testing (5.2.7).

    Implements IDeltaBusPort structurally:
      - emit_delta(agent_id, delta_type, section, data) -> None

    Capture helpers:
      - get_deltas(agent_id?, delta_type?, section?) -- filtered view
      - drain() -- return + clear all captured deltas
      - assert_emitted(agent_id?, delta_type?, section?, count?) -- assertion
      - clear() -- discard all captured deltas
      - delta_count -- total captured
      - agent_ids -- set of unique agent IDs seen

    Thread-safe via RLock for concurrent agent emission testing.
    """

    def __init__(self) -> None:
        self._deltas: List[CapturedDelta] = []
        self._lock = threading.RLock()

    # -- Protocol method ---------------------------------------------------

    def emit_delta(
        self,
        agent_id: str,
        delta_type: str,
        section: str,
        data: Dict[str, Any],
    ) -> None:
        """Capture a delta emission."""
        with self._lock:
            self._deltas.append(
                CapturedDelta(
                    agent_id=agent_id,
                    delta_type=delta_type,
                    section=section,
                    data=dict(data),
                    timestamp_ms=int(time.time() * 1000),
                )
            )

    # -- Query helpers -----------------------------------------------------

    def get_deltas(
        self,
        *,
        agent_id: Optional[str] = None,
        delta_type: Optional[str] = None,
        section: Optional[str] = None,
    ) -> List[CapturedDelta]:
        """Return captured deltas, optionally filtered."""
        with self._lock:
            result = list(self._deltas)

        if agent_id is not None:
            result = [d for d in result if d.agent_id == agent_id]
        if delta_type is not None:
            result = [d for d in result if d.delta_type == delta_type]
        if section is not None:
            result = [d for d in result if d.section == section]
        return result

    def drain(self) -> List[CapturedDelta]:
        """Return and clear all captured deltas."""
        with self._lock:
            result = list(self._deltas)
            self._deltas.clear()
            return result

    def clear(self) -> None:
        """Discard all captured deltas."""
        with self._lock:
            self._deltas.clear()

    # -- Assertions --------------------------------------------------------

    def assert_emitted(
        self,
        *,
        agent_id: Optional[str] = None,
        delta_type: Optional[str] = None,
        section: Optional[str] = None,
        count: Optional[int] = None,
    ) -> None:
        """
        Assert deltas matching the filter were emitted.

        If ``count`` is given, asserts exactly that many matches.
        If ``count`` is None, asserts at least one match.
        """
        matches = self.get_deltas(
            agent_id=agent_id,
            delta_type=delta_type,
            section=section,
        )
        actual = len(matches)

        if count is not None:
            if actual != count:
                filters = self._describe_filter(agent_id, delta_type, section)
                raise AssertionError(f"Expected {count} delta(s) matching {filters}, got {actual}")
        else:
            if actual == 0:
                filters = self._describe_filter(agent_id, delta_type, section)
                raise AssertionError(f"Expected at least 1 delta matching {filters}, got 0")

    # -- Introspection -----------------------------------------------------

    @property
    def delta_count(self) -> int:
        """Total captured deltas."""
        with self._lock:
            return len(self._deltas)

    @property
    def agent_ids(self) -> set[str]:
        """Set of unique agent IDs that have emitted deltas."""
        with self._lock:
            return {d.agent_id for d in self._deltas}

    # -- Internals ---------------------------------------------------------

    @staticmethod
    def _describe_filter(
        agent_id: Optional[str],
        delta_type: Optional[str],
        section: Optional[str],
    ) -> str:
        """Build a human-readable filter description."""
        parts = []
        if agent_id is not None:
            parts.append(f"agent_id={agent_id!r}")
        if delta_type is not None:
            parts.append(f"delta_type={delta_type!r}")
        if section is not None:
            parts.append(f"section={section!r}")
        return "{" + ", ".join(parts) + "}" if parts else "{all}"

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"TestDeltaBusAdapter(deltas={len(self._deltas)}, "
                f"agents={len({d.agent_id for d in self._deltas})})"
            )
