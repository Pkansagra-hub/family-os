"""
k1.orchestrator.adapters.workflow_storage_adapter -- WorkflowStorageAdapter (6.1.15).

Production adapter for IWorkflowStoragePort.

Design:
  - Thin pass-through wrapping SQLiteWorkflowAdapter (4.1.5).
  - Translates storage exceptions into AdapterException(DEGRADED).
  - All methods are async (IWorkflowStoragePort contract).
  - Adapter boundary: callers interact via port protocol, never
    touching SQLite internals directly.

Error Mapping:
  - Any storage failure -> AdapterException(DEGRADED, "workflow_storage")
  - ErrorRouter decides fallback behavior per operation.

References:
  - Issue 6.1.15 in orchestrator-implementation-plan.md
  - ADR-1.1.9 (Workflow Persistence Strategy)
  - k1/orchestrator/ports/workflow_storage_port.py (IWorkflowStoragePort)
  - k1/orchestrator/workflows/persistence/sqlite_adapter.py (SQLiteWorkflowAdapter)

Exports:
  WorkflowStorageAdapter
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort
from k1.orchestrator.types import AdapterError, ErrorSeverity

if TYPE_CHECKING:
    from k1.orchestrator.types import ProactiveGap, TriggerSpec
    from k1.orchestrator.workflows.workflow_types import WorkflowSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 6.1.15 -- WorkflowStorageAdapter
# ---------------------------------------------------------------------------


class WorkflowStorageAdapter:
    """
    Production IWorkflowStoragePort adapter wrapping SQLiteWorkflowAdapter.

    Pure pass-through with error translation.  All methods delegate
    to the underlying ``IWorkflowStoragePort`` implementation and wrap
    failures as ``AdapterException(DEGRADED)``.

    Constructor Args:
        storage: An ``IWorkflowStoragePort`` implementation
            (typically ``SQLiteWorkflowAdapter``, injected by
            OrchestratorFactory).

    Thread Safety:
        Delegates to underlying adapter's thread safety guarantees.
        SQLiteWorkflowAdapter uses internal lock + asyncio.to_thread.
    """

    __slots__ = ("_storage",)

    def __init__(self, storage: IWorkflowStoragePort) -> None:
        self._storage = storage

    def close(self) -> None:
        """Close the underlying storage if it exposes a close hook."""
        close = getattr(self._storage, "close", None)
        if close is None:
            return
        try:
            close()
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("close", exc) from exc

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _wrap(self, operation: str, exc: Exception) -> AdapterException:
        """Build AdapterException for a failed operation."""
        return AdapterException(
            AdapterError(
                severity=ErrorSeverity.DEGRADED,
                adapter_name="workflow_storage",
                operation=operation,
                error_code="WORKFLOW_STORAGE_ERROR",
                error_message=f"{operation} failed: {exc}",
                original_exception=exc,
            )
        )

    # ==================================================================
    # IWorkflowStoragePort -- Workflow CRUD
    # ==================================================================

    async def save_workflow(self, spec: "WorkflowSpec") -> None:
        """Upsert workflow spec via underlying storage."""
        try:
            await self._storage.save_workflow(spec)
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("save_workflow", exc) from exc

    async def get_workflow(self, workflow_id: str) -> Optional["WorkflowSpec"]:
        """Retrieve workflow spec by id."""
        try:
            return await self._storage.get_workflow(workflow_id)
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("get_workflow", exc) from exc

    async def list_workflows(self, active_only: bool = True) -> List["WorkflowSpec"]:
        """List workflows, optionally filtering by active flag."""
        try:
            return await self._storage.list_workflows(active_only)
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("list_workflows", exc) from exc

    async def delete_workflow(self, workflow_id: str) -> None:
        """Soft-delete workflow (set active=False)."""
        try:
            await self._storage.delete_workflow(workflow_id)
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("delete_workflow", exc) from exc

    async def purge_workflow(self, workflow_id: str) -> None:
        """Hard-delete workflow and all related data."""
        try:
            await self._storage.purge_workflow(workflow_id)
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("purge_workflow", exc) from exc

    # ==================================================================
    # IWorkflowStoragePort -- Trigger state
    # ==================================================================

    async def save_trigger(self, workflow_id: str, trigger: "TriggerSpec") -> None:
        """Persist trigger spec for a workflow."""
        try:
            await self._storage.save_trigger(workflow_id, trigger)
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("save_trigger", exc) from exc

    async def get_due_triggers(self, now: float) -> List[Tuple[str, "TriggerSpec"]]:
        """Return due triggers where next_fire_time <= now and enabled."""
        try:
            return await self._storage.get_due_triggers(now)
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("get_due_triggers", exc) from exc

    async def update_trigger_state(
        self, workflow_id: str, next_fire: float, last_fire: float
    ) -> None:
        """Update next/last fire timestamps for a workflow trigger."""
        try:
            await self._storage.update_trigger_state(workflow_id, next_fire, last_fire)
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("update_trigger_state", exc) from exc

    # ==================================================================
    # IWorkflowStoragePort -- Run manifests
    # ==================================================================

    async def save_run(self, manifest: object) -> None:
        """Persist a RunManifest."""
        try:
            await self._storage.save_run(manifest)
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("save_run", exc) from exc

    async def get_runs(self, workflow_id: str, limit: int = 10) -> list:
        """Return recent RunManifests for a workflow (newest first)."""
        try:
            return await self._storage.get_runs(workflow_id, limit)
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("get_runs", exc) from exc

    # ==================================================================
    # IWorkflowStoragePort -- Proactive gaps
    # ==================================================================

    async def save_gap(self, gap: "ProactiveGap") -> None:
        """Persist a ProactiveGap detection."""
        try:
            await self._storage.save_gap(gap)
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("save_gap", exc) from exc

    async def get_pending_gaps(self) -> List["ProactiveGap"]:
        """Return gaps with status=PENDING."""
        try:
            return await self._storage.get_pending_gaps()
        except AdapterException:
            raise
        except Exception as exc:
            raise self._wrap("get_pending_gaps", exc) from exc
