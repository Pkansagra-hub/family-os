"""
k1.orchestrator.adapters.test_workflow_storage_adapter -- TestWorkflowStorageAdapter (6.1.16).

Test/mock adapter for IWorkflowStoragePort.

Design:
  - In-memory dict-based storage for all four concerns:
    workflows, triggers, runs, and proactive gaps.
  - Convenience helpers for test setup and assertion.
  - No external dependencies (pure Python dicts/lists).
  - Mirrors IWorkflowStoragePort method signatures exactly.

Stored State:
  workflows   -- Dict[workflow_id, WorkflowSpec]
  triggers    -- Dict[workflow_id, TriggerSpec]
  trigger_times -- Dict[workflow_id, (next_fire, last_fire)]
  runs        -- Dict[workflow_id, List[RunManifest]]
  gaps        -- List[ProactiveGap]

References:
  - Issue 6.1.16 in orchestrator-implementation-plan.md
  - k1/orchestrator/ports/workflow_storage_port.py (IWorkflowStoragePort)

Exports:
  TestWorkflowStorageAdapter
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

from k1.orchestrator.types import ProactiveGap, ProactiveGapStatus, TriggerSpec
from k1.orchestrator.workflows.workflow_types import WorkflowSpec

# ---------------------------------------------------------------------------
# 6.1.16 -- TestWorkflowStorageAdapter
# ---------------------------------------------------------------------------


class TestWorkflowStorageAdapter:
    """
    Test IWorkflowStoragePort adapter with in-memory storage.

    Pre-populate via ``inject_workflow()``, ``inject_trigger()``,
    ``inject_run()``, ``inject_gap()`` helpers.

    All mutations are logged to ``call_log`` for assertion.

    Operation Semantics:
      - ``save_workflow`` upserts by workflow_id.
      - ``delete_workflow`` sets active=False (soft delete via replace).
      - ``purge_workflow`` removes workflow + associated triggers, runs, gaps.
      - ``get_due_triggers`` returns triggers whose next_fire <= now AND enabled.
      - ``get_pending_gaps`` returns gaps with status=PENDING.
    """

    def __init__(self) -> None:
        self.workflows: Dict[str, WorkflowSpec] = {}
        self.triggers: Dict[str, TriggerSpec] = {}
        self.trigger_times: Dict[str, Tuple[float, float]] = {}
        self.runs: Dict[str, list] = {}
        self.gaps: List[ProactiveGap] = []
        self.call_log: List[Tuple[str, Any]] = []

    # ==================================================================
    # IWorkflowStoragePort -- Workflow CRUD
    # ==================================================================

    async def save_workflow(self, spec: WorkflowSpec) -> None:
        """Upsert by workflow_id."""
        self.call_log.append(("save_workflow", spec.workflow_id))
        self.workflows[spec.workflow_id] = spec

    async def get_workflow(self, workflow_id: str) -> Optional[WorkflowSpec]:
        """Returns None if not found."""
        self.call_log.append(("get_workflow", workflow_id))
        return self.workflows.get(workflow_id)

    async def list_workflows(self, active_only: bool = True) -> List[WorkflowSpec]:
        """List workflows, optionally filtering active only."""
        self.call_log.append(("list_workflows", active_only))
        specs = list(self.workflows.values())
        if active_only:
            specs = [s for s in specs if s.active]
        return specs

    async def delete_workflow(self, workflow_id: str) -> None:
        """Soft-delete: set active=False."""
        self.call_log.append(("delete_workflow", workflow_id))
        spec = self.workflows.get(workflow_id)
        if spec is not None:
            self.workflows[workflow_id] = replace(spec, active=False)

    async def purge_workflow(self, workflow_id: str) -> None:
        """Hard-delete: remove workflow and all associated data."""
        self.call_log.append(("purge_workflow", workflow_id))
        self.workflows.pop(workflow_id, None)
        self.triggers.pop(workflow_id, None)
        self.trigger_times.pop(workflow_id, None)
        self.runs.pop(workflow_id, None)
        self.gaps = [g for g in self.gaps if g.workflow_id != workflow_id]

    # ==================================================================
    # IWorkflowStoragePort -- Trigger state
    # ==================================================================

    async def save_trigger(self, workflow_id: str, trigger: TriggerSpec) -> None:
        """Persist trigger spec for a workflow."""
        self.call_log.append(("save_trigger", workflow_id))
        self.triggers[workflow_id] = trigger
        # Initialize fire times if not set (next_fire=0 means immediately due).
        if workflow_id not in self.trigger_times:
            self.trigger_times[workflow_id] = (0.0, 0.0)

    async def get_due_triggers(self, now: float) -> List[Tuple[str, TriggerSpec]]:
        """Return (workflow_id, trigger) pairs where next_fire <= now AND enabled."""
        self.call_log.append(("get_due_triggers", now))
        result: List[Tuple[str, TriggerSpec]] = []
        for wf_id, trigger in self.triggers.items():
            if not trigger.enabled:
                continue
            times = self.trigger_times.get(wf_id, (0.0, 0.0))
            if times[0] <= now:
                result.append((wf_id, trigger))
        return result

    async def update_trigger_state(
        self, workflow_id: str, next_fire: float, last_fire: float
    ) -> None:
        """Update fire timestamps."""
        self.call_log.append(("update_trigger_state", workflow_id))
        self.trigger_times[workflow_id] = (next_fire, last_fire)

    # ==================================================================
    # IWorkflowStoragePort -- Run manifests
    # ==================================================================

    async def save_run(self, manifest: object) -> None:
        """Persist a run manifest."""
        self.call_log.append(("save_run", getattr(manifest, "run_id", None)))
        wf_id = getattr(manifest, "workflow_id", "unknown")
        if wf_id not in self.runs:
            self.runs[wf_id] = []
        self.runs[wf_id].append(manifest)

    async def get_runs(self, workflow_id: str, limit: int = 10) -> list:
        """Return recent runs (newest first, limited)."""
        self.call_log.append(("get_runs", workflow_id))
        runs = self.runs.get(workflow_id, [])
        # Newest first: reverse the insertion order.
        return list(reversed(runs))[:limit]

    # ==================================================================
    # IWorkflowStoragePort -- Proactive gaps
    # ==================================================================

    async def save_gap(self, gap: ProactiveGap) -> None:
        """Persist a proactive gap."""
        self.call_log.append(("save_gap", gap.gap_id))
        self.gaps.append(gap)

    async def get_pending_gaps(self) -> List[ProactiveGap]:
        """Return gaps with status=PENDING."""
        self.call_log.append(("get_pending_gaps", None))
        return [g for g in self.gaps if g.status == ProactiveGapStatus.PENDING]

    # ==================================================================
    # Test helpers
    # ==================================================================

    def inject_workflow(self, spec: WorkflowSpec) -> None:
        """Pre-populate a workflow without logging (test setup)."""
        self.workflows[spec.workflow_id] = spec

    def inject_trigger(
        self,
        workflow_id: str,
        trigger: TriggerSpec,
        next_fire: float = 0.0,
        last_fire: float = 0.0,
    ) -> None:
        """Pre-populate a trigger with fire times (test setup)."""
        self.triggers[workflow_id] = trigger
        self.trigger_times[workflow_id] = (next_fire, last_fire)

    def inject_run(self, manifest: object) -> None:
        """Pre-populate a run manifest (test setup)."""
        wf_id = getattr(manifest, "workflow_id", "unknown")
        if wf_id not in self.runs:
            self.runs[wf_id] = []
        self.runs[wf_id].append(manifest)

    def inject_gap(self, gap: ProactiveGap) -> None:
        """Pre-populate a gap (test setup)."""
        self.gaps.append(gap)

    def assert_workflow_saved(self, workflow_id: str) -> None:
        """Assert that save_workflow was called for the given id."""
        saves = [wf_id for op, wf_id in self.call_log if op == "save_workflow"]
        assert workflow_id in saves, f"save_workflow not called for {workflow_id}; saves={saves}"

    def assert_run_saved(self, run_id: str) -> None:
        """Assert that save_run was called for the given run_id."""
        saves = [rid for op, rid in self.call_log if op == "save_run"]
        assert run_id in saves, f"save_run not called for {run_id}; saves={saves}"

    def assert_gap_saved(self, gap_id: str) -> None:
        """Assert that save_gap was called for the given gap_id."""
        saves = [gid for op, gid in self.call_log if op == "save_gap"]
        assert gap_id in saves, f"save_gap not called for {gap_id}; saves={saves}"

    def clear(self) -> None:
        """Reset all state (use between tests)."""
        self.workflows.clear()
        self.triggers.clear()
        self.trigger_times.clear()
        self.runs.clear()
        self.gaps.clear()
        self.call_log.clear()
