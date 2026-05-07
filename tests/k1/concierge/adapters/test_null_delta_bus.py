"""
C2-prep Issue 4.2 — NullDeltaBusAdapter tests.

Validates null adapter satisfies IDeltaBusPort and silently drops all deltas.
"""

from __future__ import annotations

from k1.concierge.adapters.null_delta_bus import NullDeltaBusAdapter
from k1.fabric.ports.delta_bus import IDeltaBusPort


class TestNullDeltaBusProtocol:
    def test_satisfies_ideltabusport(self) -> None:
        assert isinstance(NullDeltaBusAdapter(), IDeltaBusPort)


class TestNullDeltaBusBehaviour:
    def test_emit_delta_does_not_raise(self) -> None:
        adapter = NullDeltaBusAdapter()
        # Should silently succeed
        adapter.emit_delta("agent-1", "plan_update", "beliefs", {"key": "val"})

    def test_emit_delta_accepts_empty_data(self) -> None:
        adapter = NullDeltaBusAdapter()
        adapter.emit_delta("agent-1", "state_change", "cognitive", {})
