"""DeltaBusAdapter -- production delta emission adapter [F33].

Implements ``IDeltaEmitPort`` (Planner port SS15.7) by wrapping
Fabric's ``IDeltaBusPort`` (5.1.6).

Adapter wiring (SS16.1.6, SS16.3):
    IDeltaEmitPort -> DeltaBusAdapter -> IDeltaBusPort

Design:
    - Synchronous: emit() MUST NOT block
    - Fire-and-forget: emit() MUST NOT raise
    - Pre-stamps agent_id from construction (SS16.1.6)
    - Maps Planner DeltaPayload fields to IDeltaBusPort.emit_delta args
    - Delta loss is acceptable (observability signals, not control-plane)

Import graph (Layer 2)
----------------------
k1.planner.adapters.delta_bus_adapter
  -> k1.planner.types  (DeltaPayload)
  -> typing, logging
"""

from __future__ import annotations

import logging
from typing import Any

from k1.fabric.ports.delta_bus import IDeltaBusPort
from k1.planner.types import DeltaPayload

logger = logging.getLogger(__name__)


class DeltaBusAdapter:
    """Production Delta Bus emission adapter (SS16.1.6).

    Wraps Fabric's ``IDeltaBusPort`` to implement the Planner's
    ``IDeltaEmitPort``.

    Pre-stamps ``agent_id`` at construction time so callers do not
    need to provide it on every emit call (the Planner DeltaPayload
    already carries agent_id, but this adapter uses its own stamped
    value for consistency with SS16.1.6).

    Fire-and-forget contract:
        ``emit()`` catches all exceptions and logs them.  It NEVER
        raises to the caller.  Delta loss is acceptable.
    """

    __slots__ = ("_bus", "_agent_id")

    def __init__(
        self,
        delta_bus: IDeltaBusPort,
        agent_id: str = "planner",
    ) -> None:
        """Initialize DeltaBusAdapter.

        Args:
            delta_bus: Fabric ``IDeltaBusPort`` instance (5.1.6) with
                ``emit_delta(agent_id, delta_type, section, data)`` method.
            agent_id: Pre-stamped agent identifier (default: ``"planner"``).
        """
        self._bus = delta_bus
        self._agent_id: str = agent_id

    # ------------------------------------------------------------------
    # IDeltaEmitPort implementation
    # ------------------------------------------------------------------

    def emit(self, delta: DeltaPayload) -> None:
        """Emit a progress delta to the Delta Bus.

        Fire-and-forget: this method NEVER raises, even on bus failure.

        Maps Planner ``DeltaPayload`` fields to Fabric
        ``IDeltaBusPort.emit_delta(agent_id, delta_type, section, data)``.

        Args:
            delta: ``DeltaPayload`` containing delta_type, section, data,
                and trace_id.
        """
        try:
            self._bus.emit_delta(
                self._agent_id,
                delta.delta_type,
                delta.section,
                delta.data,
            )
        except Exception:
            logger.exception(
                "DeltaBus emit failed, dropping delta (fire-and-forget)",
                extra={
                    "agent_id": self._agent_id,
                    "delta_type": delta.delta_type,
                    "section": delta.section,
                    "trace_id": delta.trace_id,
                },
            )


__all__ = ["DeltaBusAdapter"]
