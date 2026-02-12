"""
k1.orchestrator.adapters.bridge_write_adapter -- BridgeWriteAdapter (6.1.6).

Production adapter for IBridgeWritePort.

Design:
  - Wraps a K0 Bridge client for audit, WAL, and deferred-result writes.
  - Write methods (submit_audit, write_wal, submit_deferred_result) are
    fire-and-forget: catch all exceptions, log warning, return silently.
    K0 offline = data lost (Edge-First V1 limitation).
  - Read methods (read_wal, list_wal_ids) raise AdapterException(DEGRADED)
    if K0 is unreachable, because read failures block crash recovery.
  - Bridge client protocol: ``async write(channel, payload, *, trace_id)``
    and ``async read(channel, key)``.

Error Mapping:
  - Write failure -> log warning, return silently (fire-and-forget).
  - Read failure -> AdapterException(DEGRADED, "K0 unreachable").

References:
  - Issue 6.1.6 in orchestrator-implementation-plan.md
  - Edge-First architecture (K0 writes are best-effort)
  - docs/whiteboard/schema_whiteboard.md (S7 -- CB_BRIDGE)

Exports:
  BridgeWriteAdapter
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import AdapterError, ErrorSeverity

logger = logging.getLogger(__name__)

# Valid WAL entry types for runtime validation.
_VALID_WAL_ENTRY_TYPES = frozenset({"PLAN_START", "WAVE_COMPLETE", "STEP_COMPLETE", "DAG_COMPLETE"})


# ---------------------------------------------------------------------------
# Bridge client structural protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IBridgeClient(Protocol):
    """Structural protocol for the K0 Bridge connector."""

    async def write(
        self,
        channel: str,
        payload: Dict[str, Any],
        *,
        trace_id: str,
    ) -> None: ...

    async def read(
        self,
        channel: str,
        key: str,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# 6.1.6 -- BridgeWriteAdapter
# ---------------------------------------------------------------------------


class BridgeWriteAdapter:
    """
    Production IBridgeWritePort adapter wrapping a K0 Bridge client.

    Write methods are fire-and-forget (Edge-First: K0 offline = data lost).
    Read methods raise ``AdapterException(DEGRADED)`` on failure because
    they block crash recovery.

    The adapter validates WAL ``entry_type`` values against the known set
    and logs a warning for unknown types (does not reject -- forward
    compatibility).
    """

    __slots__ = ("_bridge",)

    def __init__(self, bridge_client: IBridgeClient) -> None:
        self._bridge = bridge_client

    # ------------------------------------------------------------------
    # IBridgeWritePort.submit_audit  (fire-and-forget)
    # ------------------------------------------------------------------

    async def submit_audit(
        self,
        run_manifest: Dict[str, Any],
        trace_id: str,
    ) -> None:
        """Write a completed DAG execution record to K0 for audit trail."""
        try:
            await self._bridge.write("audit", run_manifest, trace_id=trace_id)
        except Exception:
            logger.warning(
                "BridgeWriteAdapter.submit_audit failed trace_id=%s",
                trace_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # IBridgeWritePort.write_wal  (fire-and-forget)
    # ------------------------------------------------------------------

    async def write_wal(
        self,
        dag_id: str,
        entry_type: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        """Write a WAL entry for crash recovery."""
        if entry_type not in _VALID_WAL_ENTRY_TYPES:
            logger.warning(
                "BridgeWriteAdapter.write_wal: unknown entry_type=%s dag_id=%s",
                entry_type,
                dag_id,
            )
        try:
            await self._bridge.write(
                "wal",
                {
                    "dag_id": dag_id,
                    "entry_type": entry_type,
                    "payload": payload,
                },
                trace_id=trace_id,
            )
        except Exception:
            logger.warning(
                "BridgeWriteAdapter.write_wal failed dag_id=%s entry_type=%s trace_id=%s",
                dag_id,
                entry_type,
                trace_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # IBridgeWritePort.read_wal  (raises on failure)
    # ------------------------------------------------------------------

    async def read_wal(
        self,
        dag_id: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """Read WAL entries for crash recovery. Raises on K0 failure."""
        try:
            entries = await self._bridge.read("wal", dag_id)
            if entries is None:
                return None
            if isinstance(entries, list):
                return entries
            # Unexpected type -- wrap as list for forward compatibility
            return [entries]  # type: ignore[list-item]
        except Exception as exc:
            raise AdapterException(
                AdapterError(
                    adapter_name="bridge_write",
                    operation="read_wal",
                    error_code="K0_UNREACHABLE",
                    error_message=f"K0 Bridge read failed for dag_id={dag_id}: {exc}",
                    severity=ErrorSeverity.DEGRADED,
                )
            ) from exc

    # ------------------------------------------------------------------
    # IBridgeWritePort.list_wal_ids  (raises on failure)
    # ------------------------------------------------------------------

    async def list_wal_ids(self) -> List[str]:
        """List all dag_ids with active WAL entries. Raises on K0 failure."""
        try:
            result = await self._bridge.read("wal_ids", "")
            if result is None:
                return []
            if isinstance(result, list):
                return result
            return []
        except Exception as exc:
            raise AdapterException(
                AdapterError(
                    adapter_name="bridge_write",
                    operation="list_wal_ids",
                    error_code="K0_UNREACHABLE",
                    error_message=f"K0 Bridge list_wal_ids failed: {exc}",
                    severity=ErrorSeverity.DEGRADED,
                )
            ) from exc

    # ------------------------------------------------------------------
    # IBridgeWritePort.submit_deferred_result  (fire-and-forget)
    # ------------------------------------------------------------------

    async def submit_deferred_result(
        self,
        result: Dict[str, Any],
        workflow_id: str,
        trace_id: str,
    ) -> None:
        """Persist a workflow execution result for later retrieval."""
        try:
            await self._bridge.write(
                "deferred_result",
                {
                    "workflow_id": workflow_id,
                    "result": result,
                },
                trace_id=trace_id,
            )
        except Exception:
            logger.warning(
                "BridgeWriteAdapter.submit_deferred_result failed " "workflow_id=%s trace_id=%s",
                workflow_id,
                trace_id,
                exc_info=True,
            )
