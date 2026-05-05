"""
k1.orchestrator.adapters.delta_emit_adapter -- DeltaEmitAdapter (6.1.5).

Production adapter for IDeltaEmitPort.

Design:
  - Dual-publish: IEventPort for module-to-module events,
    IDeltaBusPort for user-facing delta stream.
  - All methods are fire-and-forget: catch all exceptions, log
    warning, return silently. The Orchestrator's core task
    processing MUST NOT be affected by delta delivery failures.
  - IEventPort.emit() is SYNC (Fabric convention).
  - IDeltaBusPort.emit_delta() is SYNC (fire-and-forget with
    internal buffering).
  - Topics prefixed with ``k1.hil.`` or ``k1.orchestration.`` are
    dual-published to both event_port and delta_bus.
  - Internal-only events go to event_port only.

Error Mapping:
  - ALL failures -> log warning, return silently.
  - NEVER raises -- fire-and-forget contract.

References:
  - Issue 6.1.5 in orchestrator-implementation-plan.md
  - ORCH-009 (trace_id on all events)
  - k1/fabric/ports/event_port.py (IEventPort)
  - k1/fabric/ports/delta_bus.py (IDeltaBusPort, DeltaPayload)

Exports:
  DeltaEmitAdapter
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from k1.fabric.ports.delta_bus import IDeltaBusPort
from k1.fabric.ports.event_port import IEventPort

logger = logging.getLogger(__name__)

# Topics that are dual-published to both event_port AND delta_bus.
_DELTA_BUS_PREFIXES = ("k1.hil.", "k1.orchestration.")


# ---------------------------------------------------------------------------
# 6.1.5 -- DeltaEmitAdapter
# ---------------------------------------------------------------------------


class DeltaEmitAdapter:
    """
    Production IDeltaEmitPort adapter.

    Wraps Fabric's ``IEventPort`` (module-to-module events) and
    ``IDeltaBusPort`` (user-facing delta stream).

    All methods are fire-and-forget: exceptions are caught, logged,
    and silently swallowed.

    ORCH-09 enforcement:
        ``emit()`` injects ``trace_id`` into the payload dict before
        publishing, ensuring every event carries correlation context.

    Dual-publish semantics:
        Events whose topic starts with ``k1.hil.`` or ``k1.orchestration.``
        are published to BOTH the internal event bus AND the delta bus
        for Concierge consumption.  Internal-only events (e.g.
        ``k1.orchestration.error.routed``) go to event_port only when
        they don't match these prefixes.
    """

    __slots__ = ("_event_port", "_delta_bus")

    def __init__(
        self,
        event_port: IEventPort,
        delta_bus: IDeltaBusPort,
    ) -> None:
        self._event_port = event_port
        self._delta_bus = delta_bus

    # ------------------------------------------------------------------
    # IDeltaEmitPort.emit
    # ------------------------------------------------------------------

    async def emit(
        self,
        event_topic: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        """Fire-and-forget event emission with optional delta-bus dual-publish."""
        try:
            # ORCH-09: inject trace_id into payload
            payload["trace_id"] = trace_id

            # Primary: module-to-module event bus (SYNC)
            self._event_port.emit(event_topic, payload)

            # Dual-publish to delta bus for user-facing topics
            if event_topic.startswith(_DELTA_BUS_PREFIXES):
                self._delta_bus.emit_delta(
                    agent_id="orchestrator",
                    delta_type=event_topic,
                    section="orchestration",
                    data=payload,
                )
        except Exception:
            logger.warning(
                "DeltaEmitAdapter.emit failed for topic=%s trace_id=%s",
                event_topic,
                trace_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # IDeltaEmitPort.emit_progress
    # ------------------------------------------------------------------

    async def emit_progress(
        self,
        step_id: str,
        summary: str,
        trace_id: str,
    ) -> None:
        """Emit a human-readable progress delta (shorthand)."""
        await self.emit(
            "k1.hil.progress.v1",
            {"step_id": step_id, "summary": summary},
            trace_id,
        )
