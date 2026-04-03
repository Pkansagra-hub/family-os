"""
k1.concierge.adapters.null_bridge_write -- Null IBridgeWritePort for startup tier.

Shared Orchestrator needs IBridgeWritePort at construction. When Bridge
is offline (SIM-D-33), this null adapter silently drops all writes and
returns empty for reads.

Used by: Shared OrchestratorService when bridge_client is None.

Protocol: k1.orchestrator.ports.bridge_write_port.IBridgeWritePort
Decision: SIM-D-33
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class NullBridgeWriteAdapter:
    """Null IBridgeWritePort — drops writes, returns empty for reads.

    Satisfies IBridgeWritePort structurally. Used by shared
    Orchestrator when Bridge is offline (edge-first fallback).
    """

    async def submit_audit(self, run_manifest: Dict[str, Any], trace_id: str) -> None:
        pass  # Silent drop

    async def write_wal(
        self,
        dag_id: str,
        entry_type: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        pass  # Silent drop

    async def read_wal(self, dag_id: str) -> Optional[List[Dict[str, Any]]]:
        return None

    async def list_wal_ids(self) -> List[str]:
        return []

    async def submit_deferred_result(
        self, result: Dict[str, Any], workflow_id: str, trace_id: str
    ) -> None:
        pass  # Silent drop
