"""
k1.orchestrator.ports.workflow_storage_port -- IWorkflowStoragePort (4.1.6).

8th port for Orchestrator hexagonal architecture. Workflow-specific
persistence covering WorkflowSpec, TriggerSpec, RunManifest, and
ProactiveGap lifecycle.

Design:
  - All methods ASYNC (production adapter uses SQLite via aiosqlite
    or run_in_executor).
  - Protocol class with ZERO implementation logic.
  - Follows same patterns as the other 7 Orchestrator ports.

CRITICAL: Port file contains ZERO implementation logic. Every method
body is ``...`` (Protocol). Do NOT add default implementations, helper
methods, or state.

Production adapter: SQLiteWorkflowAdapter (4.1.5) in
  k1/orchestrator/workflows/persistence/sqlite_adapter.py
Test adapter: InMemoryWorkflowAdapter (6.1.16) in
  k1/orchestrator/adapters/test_workflow_storage_adapter.py

References:
  - ADR-1.1.9 (Workflow Persistence Strategy)
  - orchestrator-implementation-plan.md Issue 4.1.6

Exports:
  IWorkflowStoragePort
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Protocol, Tuple, runtime_checkable

if TYPE_CHECKING:
    from k1.orchestrator.types import ProactiveGap, TriggerSpec
    from k1.orchestrator.workflows.workflow_types import WorkflowSpec


# ---------------------------------------------------------------------------
# Port protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IWorkflowStoragePort(Protocol):
    """
    Async persistence port for workflow data.

    Covers four storage concerns:
      1. Workflow specs (save, get, list, delete)
      2. Trigger state (save, get_due, update_state)
      3. Run manifests (save, get_runs)
      4. Proactive gaps (save, get_pending)

    Performance:
      ``get_due_triggers()`` is called every ~1 s by WorkflowScheduler
      tick -- implementations MUST ensure O(log n) via index.

    Transaction safety:
      Port does NOT define transaction boundaries. The adapter
      decides (e.g., SQLite uses connection-level transactions).
    """

    # -- Workflow CRUD -------------------------------------------------------

    async def save_workflow(self, spec: "WorkflowSpec") -> None:
        """Upsert by workflow_id."""
        ...  # pragma: no cover

    async def get_workflow(self, workflow_id: str) -> Optional["WorkflowSpec"]:
        """Returns None if not found."""
        ...  # pragma: no cover

    async def list_workflows(self, active_only: bool = True) -> List["WorkflowSpec"]:
        """List stored workflows, optionally filtering by active flag."""
        ...  # pragma: no cover

    async def delete_workflow(self, workflow_id: str) -> None:
        """Soft delete (set active=False)."""
        ...  # pragma: no cover

    async def purge_workflow(self, workflow_id: str) -> None:
        """Hard delete -- permanently removes workflow and all data."""
        ...  # pragma: no cover

    # -- Trigger state -------------------------------------------------------

    async def save_trigger(self, workflow_id: str, trigger: "TriggerSpec") -> None:
        """Persist trigger spec for a workflow."""
        ...  # pragma: no cover

    async def get_due_triggers(self, now: float) -> List[Tuple[str, "TriggerSpec"]]:
        """Return (workflow_id, trigger) pairs where next_fire_time <= *now*
        AND enabled=True.

        Called every ~1 s by WorkflowScheduler -- must be efficient.
        """
        ...  # pragma: no cover

    async def update_trigger_state(
        self, workflow_id: str, next_fire: float, last_fire: float
    ) -> None:
        """Update next/last fire timestamps for a workflow trigger."""
        ...  # pragma: no cover

    # -- Run manifests -------------------------------------------------------

    async def save_run(self, manifest: object) -> None:
        """Persist a RunManifest. Type is ``RunManifest`` (4.2.4).

        Accepts ``object`` here to avoid circular import -- actual
        type enforcement lives in adapter + tests.
        """
        ...  # pragma: no cover

    async def get_runs(self, workflow_id: str, limit: int = 10) -> list:
        """Return recent RunManifests for a workflow (newest first)."""
        ...  # pragma: no cover

    # -- Proactive gaps ------------------------------------------------------

    async def save_gap(self, gap: "ProactiveGap") -> None:
        """Persist a ProactiveGap detection."""
        ...  # pragma: no cover

    async def get_pending_gaps(self) -> List["ProactiveGap"]:
        """Return gaps with status=PENDING."""
        ...  # pragma: no cover
