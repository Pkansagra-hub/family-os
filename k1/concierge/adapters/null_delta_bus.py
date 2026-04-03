"""
k1.concierge.adapters.null_delta_bus -- Null IDeltaBusPort for startup tier.

Shared Fabric (SIM-D-34/D-35) needs IDeltaBusPort at construction,
but real delta routing is per-session. This null adapter silently
drops all deltas.

Used by: Shared Fabric instance (for Orchestrator + Planner capability execution).

Protocol: k1.fabric.ports.delta_bus.IDeltaBusPort
Gap: SIM-GAP-47
"""

from __future__ import annotations

from typing import Any, Dict


class NullDeltaBusAdapter:
    """Null IDeltaBusPort — silently drops all deltas.

    Satisfies IDeltaBusPort structurally. Used by shared Fabric
    at startup tier when no delta bus routing is needed.
    """

    def emit_delta(
        self,
        agent_id: str,
        delta_type: str,
        section: str,
        data: Dict[str, Any],
    ) -> None:
        pass  # Silent drop
