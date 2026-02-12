"""
k1.orchestrator.workflows.workflow_registry -- WorkflowRegistry (4.1.1 + 4.1.4).

Thin service layer over IWorkflowStoragePort for managing saved
workflows. STATELESS -- no in-memory cache in V1. All reads go through
the storage port.

Design decisions:
  - ADR-1.1.9: K1 SQLite LOCAL COLD persistence
  - ORCH-002: Hexagonal port/adapter

Anti-hallucination rules:
  - STATELESS: No in-memory cache. Do NOT add caching.
  - WorkflowSpec is FROZEN (immutable) -- bump_version() creates NEW instance.
  - save() and bump_version() are NOT idempotent.
  - delete() is soft-delete (active=False). Only purge() is hard-delete.
  - Version bumps are monotonic and append-only -- no rollback in V1.
  - WorkflowVersionPointer is embedded -- not a separate service.

Constructor dependency chain (OrchestratorFactory step 14 in 6.2.1):
  1. storage: IWorkflowStoragePort -- for all persistence operations

Exports:
  WorkflowRegistry
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Dict, List, Optional

from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort
from k1.orchestrator.types import PlanStep, TriggerSpec
from k1.orchestrator.workflows.workflow_types import (
    VersionEntry,
    WorkflowSpec,
    WorkflowVersionPointer,
)


class WorkflowRegistry:
    """Thin service layer over IWorkflowStoragePort.

    STATELESS -- no in-memory cache. All reads go through ``storage``.

    Embeds WorkflowVersionPointer logic (4.1.4) for version management.
    """

    def __init__(self, storage: IWorkflowStoragePort) -> None:
        self._storage = storage

    # -- Public API ----------------------------------------------------------

    async def save(self, spec: WorkflowSpec) -> str:
        """Validate *spec*, persist via storage, return workflow_id.

        Raises:
            ValueError: If spec.name is duplicate (already exists in storage).
        """
        # Validate spec fields (post_init handles name/steps/version checks)
        self._validate_trigger(spec.trigger)

        # Duplicate name check
        existing = await self._storage.list_workflows(active_only=False)
        for wf in existing:
            if wf.name == spec.name and wf.workflow_id != spec.workflow_id:
                raise ValueError(
                    f"Workflow with name '{spec.name}' already exists "
                    f"(workflow_id={wf.workflow_id})"
                )

        await self._storage.save_workflow(spec)
        return spec.workflow_id

    async def get(self, workflow_id: str) -> Optional[WorkflowSpec]:
        """Returns None if not found."""
        return await self._storage.get_workflow(workflow_id)

    async def list_active(self) -> List[WorkflowSpec]:
        """Filters by active=True via storage."""
        return await self._storage.list_workflows(active_only=True)

    async def delete(self, workflow_id: str) -> None:
        """Soft-delete: sets active=False, preserves for audit."""
        await self._storage.delete_workflow(workflow_id)

    async def purge(self, workflow_id: str) -> None:
        """Hard-delete. Permanently removes workflow and all associated data."""
        await self._storage.purge_workflow(workflow_id)

    async def update_trigger(self, workflow_id: str, trigger: TriggerSpec) -> None:
        """Updates trigger for existing workflow, bumps version.

        Raises:
            ValueError: If workflow not found.
        """
        self._validate_trigger(trigger)
        spec = await self._storage.get_workflow(workflow_id)
        if spec is None:
            raise ValueError(f"Workflow '{workflow_id}' not found")

        # Build version pointer from current state and bump
        pointer = WorkflowVersionPointer(
            workflow_id=workflow_id,
            active_version=spec.version,
            version_history=[],
        )
        new_version = self._bump(
            pointer,
            new_plan_id=spec.source_plan_id,
            new_steps=list(spec.steps),
            summary=f"Trigger updated to {trigger.type.value}",
        )

        updated = replace(
            spec,
            trigger=trigger,
            version=new_version,
            updated_at=time.time(),
        )
        await self._storage.save_workflow(updated)
        await self._storage.save_trigger(workflow_id, trigger)

    async def bump_version(
        self,
        workflow_id: str,
        new_steps: List[PlanStep],
        new_deps: Dict[str, List[str]],
        source_plan_id: Optional[str] = None,
        summary: str = "Version bump",
    ) -> str:
        """Create new version with updated steps/deps, set as active version.

        Returns new version string ('1.0.0' -> '2.0.0', monotonic major).
        Uses embedded WorkflowVersionPointer (4.1.4).

        Raises:
            ValueError: If workflow not found or new_steps is empty.
        """
        if not new_steps:
            raise ValueError("new_steps must be non-empty")

        spec = await self._storage.get_workflow(workflow_id)
        if spec is None:
            raise ValueError(f"Workflow '{workflow_id}' not found")

        plan_id = source_plan_id if source_plan_id else spec.source_plan_id

        # Build version pointer from current state and bump
        pointer = WorkflowVersionPointer(
            workflow_id=workflow_id,
            active_version=spec.version,
            version_history=[],
        )
        new_version = self._bump(
            pointer,
            new_plan_id=plan_id,
            new_steps=new_steps,
            summary=summary,
        )

        updated = replace(
            spec,
            version=new_version,
            steps=new_steps,
            dependencies=new_deps,
            source_plan_id=plan_id,
            updated_at=time.time(),
        )
        await self._storage.save_workflow(updated)
        return new_version

    # -- Embedded WorkflowVersionPointer logic (4.1.4) ----------------------

    @staticmethod
    def _bump(
        pointer: WorkflowVersionPointer,
        new_plan_id: str,
        new_steps: List[PlanStep],
        summary: str,
    ) -> str:
        """Increment major version ('1.0.0' -> '2.0.0').

        Appends VersionEntry to history. Returns new version string.
        Version format: semver major-only (1.0.0, 2.0.0, ...) for
        simplicity in V1 -- minor/patch reserved for future partial updates.
        """
        current = pointer.active_version
        parts = current.split(".")
        major = int(parts[0])
        new_version = f"{major + 1}.0.0"

        entry = VersionEntry(
            version=new_version,
            created_at=time.time(),
            source_plan_id=new_plan_id,
            step_count=len(new_steps),
            change_summary=summary,
        )
        pointer.version_history.append(entry)
        pointer.active_version = new_version

        return new_version

    # -- Private helpers -----------------------------------------------------

    @staticmethod
    def _validate_trigger(trigger: TriggerSpec) -> None:
        """Validate trigger spec rules.

        TriggerSpec.__post_init__ already validates CRON/EVENT/MANUAL rules,
        but we re-check here for defense-in-depth.
        """
        from k1.orchestrator.types import TriggerType

        if trigger.type == TriggerType.CRON and not trigger.schedule:
            raise ValueError("CRON trigger requires a schedule")
        if trigger.type == TriggerType.EVENT and not trigger.event_topic:
            raise ValueError("EVENT trigger requires an event_topic")
        if trigger.type == TriggerType.MANUAL:
            if trigger.schedule is not None or trigger.event_topic is not None:
                raise ValueError("MANUAL trigger must have schedule=None and event_topic=None")
