"""
k1.orchestrator.ports.delta_emit_port -- IDeltaEmitPort port (1.4.5).

Async fire-and-forget port for emitting events and progress deltas.

Design:
  - All methods ASYNC, fire-and-forget.
  - Delta delivery is best-effort. Orchestrator NEVER fails because
    delta delivery failed.
  - All methods catch exceptions internally, log warning, and return
    silently.
  - Uses event catalog constants (k1.orchestrator.events) for topic strings.

Consumers:
  - OrchestratorService (2.1.x) -- emit task accepted, DAG completed
  - DAGExecutor (2.2.x) -- emit step/wave progress deltas
  - StepRunner (2.3.x) -- emit step lifecycle events
  - ErrorRouter (2.1.7) -- emit error.routed diagnostic events
  - ExecutionMonitor (3.2.6) -- emit progress + optional HIL override

Production adapter: DeltaEmitAdapter (6.1.5) in adapters/delta_emit_adapter.py
Test adapter: TestDeltaAdapter (6.1.12) in adapters/test_delta_adapter.py

References:
  - ORCH-009 (trace_id on all events)
  - docs/whiteboard/schema_whiteboard.md (S3 -- event payload schemas)

Exports:
  IDeltaEmitPort
"""

from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IDeltaEmitPort(Protocol):
    """
    Async fire-and-forget port for event emission and progress deltas.

    All methods are best-effort: if emission fails (bus down, network
    error), the method logs a warning and returns silently. The
    Orchestrator's core task processing MUST NOT be affected by
    delta delivery failures.

    ORCH-09: every event payload MUST carry a ``cognitive_trace_id``
    (passed as ``trace_id`` parameter). The adapter is responsible
    for inserting it into the payload if not already present.

    Thread safety:
      Implementations MUST support concurrent emit() calls from
      multiple asyncio tasks (DAG wave parallel dispatch).
    """

    async def emit(
        self,
        event_topic: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        """
        Emit a typed event to the DeltaBus.

        The payload is a JSON-serializable dict (e.g.
        ``AggregatedResult.to_dict()``, ``StepResult.to_dict()``).

        Args:
            event_topic: Event topic string from the event catalog
                (e.g. ``ORCH_DAG_COMPLETED``).
            payload: Event payload dict. Should conform to the
                JSON Schema for this event topic.
            trace_id: Cognitive trace identifier for correlation.

        Returns:
            None. Fire-and-forget -- never raises.
        """
        ...  # pragma: no cover

    async def emit_progress(
        self,
        step_id: str,
        summary: str,
        trace_id: str,
    ) -> None:
        """
        Emit a human-readable progress delta.

        Shorthand for ``k1.orchestration.delta.v1`` events. Used
        by Concierge PROGRESSING state to show partial progress
        to the user.

        Args:
            step_id: The step this progress relates to.
            summary: Human-readable progress summary
                (e.g. ``"Step 2 of 5 complete: calendar search done"``).
            trace_id: Cognitive trace identifier for correlation.

        Returns:
            None. Fire-and-forget -- never raises.
        """
        ...  # pragma: no cover
