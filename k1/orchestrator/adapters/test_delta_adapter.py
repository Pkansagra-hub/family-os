"""
k1.orchestrator.adapters.test_delta_adapter -- TestDeltaAdapter (6.1.12).

Test adapter for IDeltaEmitPort.

Design:
  - Captures ALL emitted events, progress deltas, and HIL requests.
  - Never raises -- fire-and-forget semantics preserved.
  - Assertion helpers for verifying event emission in tests.

References:
  - Issue 6.1.12 in orchestrator-implementation-plan.md
  - k1/orchestrator/ports/delta_emit_port.py (IDeltaEmitPort)

Exports:
  TestDeltaAdapter
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# 6.1.12 -- TestDeltaAdapter
# ---------------------------------------------------------------------------


class TestDeltaAdapter:
    """
    Test IDeltaEmitPort adapter that captures all emissions.

    All emitted events, progress deltas, and HIL requests are stored
    in logs for test assertions. Never raises.
    """

    def __init__(self) -> None:
        self.emitted: List[Tuple[str, Dict[str, Any], str]] = []
        self.progress_log: List[Tuple[str, str, str]] = []

    # ------------------------------------------------------------------
    # IDeltaEmitPort.emit
    # ------------------------------------------------------------------

    async def emit(
        self,
        event_topic: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        """Capture emitted event. Never raises."""
        self.emitted.append((event_topic, payload, trace_id))

    # ------------------------------------------------------------------
    # IDeltaEmitPort.emit_progress
    # ------------------------------------------------------------------

    async def emit_progress(
        self,
        step_id: str,
        summary: str,
        trace_id: str,
    ) -> None:
        """Capture progress delta. Never raises."""
        self.progress_log.append((step_id, summary, trace_id))

    # ------------------------------------------------------------------
    # Test helpers -- assertions
    # ------------------------------------------------------------------

    def assert_emitted(self, topic: str, count: int = 1) -> None:
        """Assert that *topic* was emitted exactly *count* times."""
        actual = sum(1 for t, _, _ in self.emitted if t == topic)
        assert actual == count, f"Expected topic '{topic}' emitted {count} time(s), got {actual}"

    def get_emitted(self, topic: str) -> List[Dict[str, Any]]:
        """Return all payloads emitted for *topic*."""
        return [payload for t, payload, _ in self.emitted if t == topic]

    def assert_progress(self, step_id: str) -> None:
        """Assert that progress was emitted for *step_id*."""
        found = any(sid == step_id for sid, _, _ in self.progress_log)
        assert found, (
            f"Expected progress for step '{step_id}', "
            f"got {[s for s, _, _ in self.progress_log]}"
        )

    def reset(self) -> None:
        """Clear all logs."""
        self.emitted.clear()
        self.progress_log.clear()
