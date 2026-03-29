"""TestDeltaAdapter -- in-memory IDeltaEmitPort implementation (SS16.2.6).

Implements the IDeltaEmitPort Protocol (SS15.7) with:
- Synchronous emit() that never raises, never blocks
- Ordered capture of all emitted DeltaPayload objects
- Rich assertion helpers for delta type filtering and stage transitions
- Protocol-structural compliance with IDeltaEmitPort

File location: tests/k1/planner/adapters/ (SS30.3)
Never importable from production code.
"""

from __future__ import annotations

from typing import List

from k1.planner.types import DeltaPayload


class TestDeltaAdapter:
    """In-memory IDeltaEmitPort for deterministic testing (SS16.2.6).

    Constructor takes no arguments. Internal state is a simple ordered
    capture list of all emitted DeltaPayload objects.

    Internal state
    --------------
    _capture : List[DeltaPayload]
        Ordered list of all emitted deltas.
    """

    def __init__(self) -> None:
        self._capture: List[DeltaPayload] = []

    # ------------------------------------------------------------------
    # IDeltaEmitPort Protocol method
    # ------------------------------------------------------------------

    def emit(self, delta: DeltaPayload) -> None:
        """Append delta to capture list. Synchronous, never raises."""
        self._capture.append(delta)

    # ------------------------------------------------------------------
    # Assertion / introspection helpers (test-only)
    # ------------------------------------------------------------------

    def get_deltas(self) -> List[DeltaPayload]:
        """Return all captured deltas in emission order."""
        return list(self._capture)

    def get_deltas_by_type(self, delta_type: str) -> List[DeltaPayload]:
        """Return deltas filtered by delta_type."""
        return [d for d in self._capture if d.delta_type == delta_type]

    @property
    def delta_count(self) -> int:
        """Total number of captured deltas."""
        return len(self._capture)

    def assert_delta_count(self, n: int) -> None:
        """Assert total number of captured deltas."""
        assert self.delta_count == n, f"Expected {n} deltas, got {self.delta_count}"

    def assert_stage_transitions(self, expected_stages: List[str]) -> None:
        """Assert stage_transition delta sequence matches expected stages.

        Extracts 'to' field from all stage_transition deltas and compares
        against the expected ordered list of stage names.
        """
        transitions = self.get_deltas_by_type("stage_transition")
        actual_stages = [d.data.get("to", "") for d in transitions]
        assert actual_stages == expected_stages, (
            f"Expected stage transitions {expected_stages}, " f"got {actual_stages}"
        )

    def get_stage_transition_sequence(self) -> List[str]:
        """Return ordered list of 'to' stage names from stage_transition deltas."""
        transitions = self.get_deltas_by_type("stage_transition")
        return [d.data.get("to", "") for d in transitions]

    def assert_has_delta_type(self, delta_type: str) -> None:
        """Assert at least one delta of the given type was emitted."""
        found = self.get_deltas_by_type(delta_type)
        assert len(found) > 0, (
            f"No delta with type '{delta_type}' found "
            f"(have: {[d.delta_type for d in self._capture]})"
        )

    def assert_no_delta_type(self, delta_type: str) -> None:
        """Assert no delta of the given type was emitted."""
        found = self.get_deltas_by_type(delta_type)
        assert len(found) == 0, f"Expected no '{delta_type}' deltas, found {len(found)}"

    def clear(self) -> None:
        """Reset capture list. Useful between test phases."""
        self._capture.clear()
