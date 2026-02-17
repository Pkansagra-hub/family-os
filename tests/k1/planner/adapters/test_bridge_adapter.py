"""TestBridgeAdapter -- in-memory IBridgePort implementation (SS16.2.5).

Implements the IBridgePort Protocol (SS15.6) with:
- Constructor injection of preset recall data and availability flag
- Capture-mode recording of all recall/persist calls
- Zero I/O, purely in-memory
- persist_plan is fire-and-forget (no return, no exception)
- Protocol-structural compliance with IBridgePort

File location: tests/k1/planner/adapters/ (SS30.3)
Never importable from production code.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from k1.orchestrator.types import CommittedPlan
from k1.planner.types import RecallResponse


class TestBridgeAdapter:
    """In-memory IBridgePort for deterministic testing (SS16.2.5).

    Constructor
    -----------
    preset_recall : Dict[str, Any]
        Data returned by recall() when available. Mapped into
        RecallResponse(facts=..., scores=...).
    available : bool
        Simulates K0 online/offline. When False, recall() returns
        empty RecallResponse and persist_plan() silently drops.

    Internal state
    --------------
    _persist_capture : List[Dict]
        Records all committed plans (via to_dict()).
    _recall_log : List[Dict]
        Records all recall() call arguments.
    """

    def __init__(
        self,
        preset_recall: Optional[Dict[str, Any]] = None,
        available: bool = True,
    ) -> None:
        self._preset_recall: Dict[str, Any] = dict(preset_recall or {})
        self._available: bool = available
        self._persist_capture: List[Dict[str, Any]] = []
        self._recall_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # IBridgePort Protocol methods
    # ------------------------------------------------------------------

    async def recall(
        self,
        query: str,
        selectors: Optional[List[str]] = None,
        *,
        trace_id: str = "",
    ) -> RecallResponse:
        """Query preset recall data or return empty if offline."""
        self._recall_log.append(
            {
                "query": query,
                "selectors": selectors,
                "trace_id": trace_id,
            }
        )

        if not self._available:
            return RecallResponse(trace_id=trace_id)

        return RecallResponse(
            facts=self._preset_recall.get("facts", []),
            scores=self._preset_recall.get("scores", []),
            trace_id=trace_id,
        )

    async def persist_plan(
        self,
        plan: CommittedPlan,
        *,
        trace_id: str = "",
    ) -> None:
        """Fire-and-forget plan persistence. Never raises."""
        if not self._available:
            return  # Silently drop when offline
        self._persist_capture.append(plan.to_dict())

    # ------------------------------------------------------------------
    # Configuration helpers (test-only)
    # ------------------------------------------------------------------

    def set_available(self, available: bool) -> None:
        """Toggle online/offline state mid-test."""
        self._available = available

    def is_available(self) -> bool:
        """Return current availability status."""
        return self._available

    # ------------------------------------------------------------------
    # Assertion / introspection helpers (test-only)
    # ------------------------------------------------------------------

    def get_persisted_plans(self) -> List[Dict[str, Any]]:
        """Return all persisted plan dicts."""
        return list(self._persist_capture)

    @property
    def recall_log(self) -> List[Dict[str, Any]]:
        """Read-only access to recall() call log."""
        return list(self._recall_log)

    @property
    def recall_count(self) -> int:
        """Number of recall() calls."""
        return len(self._recall_log)

    @property
    def persist_count(self) -> int:
        """Number of persist_plan() calls that were captured."""
        return len(self._persist_capture)

    def assert_recall_count(self, n: int) -> None:
        """Assert recall() was called exactly n times."""
        assert self.recall_count == n, f"Expected {n} recall calls, got {self.recall_count}"

    def assert_persist_count(self, n: int) -> None:
        """Assert persist_plan() captured exactly n plans."""
        assert self.persist_count == n, f"Expected {n} persisted plans, got {self.persist_count}"
