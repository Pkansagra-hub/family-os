"""
Tests for WorkflowRegistry (Issue 4.1.1) + embedded WorkflowVersionPointer (4.1.4).

Thin service layer over IWorkflowStoragePort. STATELESS -- no in-memory cache.
Tests use an in-memory fake storage adapter.

Test classes:
  TestWorkflowRegistryInit        -- Constructor, single dep.
  TestSaveValidation              -- save() validates spec + trigger.
  TestSaveDuplicateName           -- save() rejects duplicate names.
  TestSaveSuccess                 -- save() persists via storage.
  TestGetWorkflow                 -- get() returns spec or None.
  TestListActive                  -- list_active() filters by active=True.
  TestSoftDelete                  -- delete() sets active=False.
  TestHardDelete                  -- purge() removes permanently.
  TestUpdateTrigger               -- update_trigger() validates + bumps version.
  TestBumpVersion                 -- bump_version() creates new version.
  TestBumpVersionPointer          -- _bump() static method logic.
  TestVersionMonotonic            -- Version bumps are monotonic.
  TestStateless                   -- No in-memory cache (repeated reads hit storage).
  TestWorkflowTypes               -- WorkflowSpec, DynamicExpr, VersionEntry types.
  TestDynamicExprParse            -- DynamicExpr.parse() regex matching.
  TestIWorkflowStoragePort        -- Port is runtime_checkable Protocol.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

import pytest

from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort
from k1.orchestrator.types import PlanStep, TriggerSpec, TriggerType
from k1.orchestrator.workflows.workflow_registry import WorkflowRegistry
from k1.orchestrator.workflows.workflow_types import (
    DynamicExpr,
    VersionEntry,
    WorkflowSpec,
    WorkflowVersionPointer,
)

# ===========================================================================
# In-memory fake storage adapter for testing
# ===========================================================================


class FakeWorkflowStorage:
    """Dict-based in-memory IWorkflowStoragePort for testing."""

    def __init__(self) -> None:
        self.workflows: Dict[str, WorkflowSpec] = {}
        self.triggers: Dict[str, TriggerSpec] = {}
        self.save_workflow_calls: int = 0
        self.get_workflow_calls: int = 0
        self.list_workflows_calls: int = 0

    async def save_workflow(self, spec: WorkflowSpec) -> None:
        self.save_workflow_calls += 1
        self.workflows[spec.workflow_id] = spec

    async def get_workflow(self, workflow_id: str) -> Optional[WorkflowSpec]:
        self.get_workflow_calls += 1
        return self.workflows.get(workflow_id)

    async def list_workflows(self, active_only: bool = True) -> List[WorkflowSpec]:
        self.list_workflows_calls += 1
        if active_only:
            return [w for w in self.workflows.values() if w.active]
        return list(self.workflows.values())

    async def delete_workflow(self, workflow_id: str) -> None:
        if workflow_id in self.workflows:
            spec = self.workflows[workflow_id]
            self.workflows[workflow_id] = replace(spec, active=False)

    async def purge_workflow(self, workflow_id: str) -> None:
        self.workflows.pop(workflow_id, None)
        self.triggers.pop(workflow_id, None)

    async def save_trigger(self, workflow_id: str, trigger: TriggerSpec) -> None:
        self.triggers[workflow_id] = trigger

    async def get_due_triggers(self, now: float) -> List[Tuple[str, TriggerSpec]]:
        return []

    async def update_trigger_state(
        self, workflow_id: str, next_fire: float, last_fire: float
    ) -> None:
        pass

    async def save_run(self, manifest: object) -> None:
        pass

    async def get_runs(self, workflow_id: str, limit: int = 10) -> list:
        return []

    async def save_gap(self, gap: object) -> None:
        pass

    async def get_pending_gaps(self) -> list:
        return []


# ===========================================================================
# Helpers
# ===========================================================================


def _make_step(step_id: str = "s1", capability: str = "cap.test") -> PlanStep:
    return PlanStep(id=step_id, capability=capability, params={"key": "val"})


def _make_trigger(
    trigger_type: TriggerType = TriggerType.MANUAL,
    schedule: Optional[str] = None,
    event_topic: Optional[str] = None,
) -> TriggerSpec:
    return TriggerSpec(
        type=trigger_type,
        schedule=schedule,
        event_topic=event_topic,
    )


def _make_spec(
    workflow_id: str = "wf-001",
    name: str = "Test Workflow",
    version: str = "1.0.0",
    trigger: Optional[TriggerSpec] = None,
    steps: Optional[List[PlanStep]] = None,
    active: bool = True,
) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=workflow_id,
        name=name,
        source_plan_id="plan-001",
        version=version,
        trigger=trigger or _make_trigger(),
        steps=[_make_step()] if steps is None else steps,
        dependencies={},
        active=active,
    )


# ===========================================================================
# TestWorkflowRegistryInit
# ===========================================================================


class TestWorkflowRegistryInit:
    """Constructor and single dependency."""

    def test_constructor_accepts_storage(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        assert registry._storage is storage

    def test_single_dependency(self) -> None:
        """WorkflowRegistry takes exactly one dep: IWorkflowStoragePort."""
        import inspect

        sig = inspect.signature(WorkflowRegistry.__init__)
        params = [p for p in sig.parameters if p != "self"]
        assert params == ["storage"]


# ===========================================================================
# TestSaveValidation
# ===========================================================================


class TestSaveValidation:
    """save() validates WorkflowSpec and trigger."""

    @pytest.mark.asyncio
    async def test_save_valid_spec(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        result = await registry.save(spec)
        assert result == "wf-001"
        assert storage.save_workflow_calls == 1

    @pytest.mark.asyncio
    async def test_save_empty_name_raises(self) -> None:
        """WorkflowSpec.__post_init__ rejects empty name."""
        with pytest.raises(ValueError, match="name"):
            _make_spec(name="")

    @pytest.mark.asyncio
    async def test_save_empty_steps_raises(self) -> None:
        """WorkflowSpec.__post_init__ rejects empty steps."""
        with pytest.raises(ValueError, match="steps"):
            _make_spec(steps=[])

    @pytest.mark.asyncio
    async def test_save_invalid_version_raises(self) -> None:
        """WorkflowSpec.__post_init__ rejects invalid version format."""
        with pytest.raises(ValueError, match="semver"):
            _make_spec(version="v1")

    @pytest.mark.asyncio
    async def test_save_cron_trigger_without_schedule_raises(self) -> None:
        """CRON trigger requires schedule."""
        with pytest.raises(ValueError, match="schedule"):
            _make_trigger(trigger_type=TriggerType.CRON)

    @pytest.mark.asyncio
    async def test_save_event_trigger_without_topic_raises(self) -> None:
        """EVENT trigger requires event_topic."""
        with pytest.raises(ValueError, match="event_topic"):
            _make_trigger(trigger_type=TriggerType.EVENT)

    @pytest.mark.asyncio
    async def test_save_manual_trigger_with_schedule_raises(self) -> None:
        """MANUAL trigger must have schedule=None."""
        with pytest.raises(ValueError, match="MANUAL"):
            TriggerSpec(
                type=TriggerType.MANUAL,
                schedule="0 9 * * MON",
            )

    @pytest.mark.asyncio
    async def test_save_cron_trigger_valid(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        trigger = _make_trigger(
            trigger_type=TriggerType.CRON,
            schedule="0 9 * * MON",
        )
        spec = _make_spec(trigger=trigger)
        result = await registry.save(spec)
        assert result == "wf-001"

    @pytest.mark.asyncio
    async def test_save_event_trigger_valid(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        trigger = _make_trigger(
            trigger_type=TriggerType.EVENT,
            event_topic="user.hello",
        )
        spec = _make_spec(trigger=trigger)
        result = await registry.save(spec)
        assert result == "wf-001"


# ===========================================================================
# TestSaveDuplicateName
# ===========================================================================


class TestSaveDuplicateName:
    """save() rejects duplicate workflow names."""

    @pytest.mark.asyncio
    async def test_duplicate_name_raises(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec1 = _make_spec(workflow_id="wf-001", name="daily-backup")
        await registry.save(spec1)

        spec2 = _make_spec(workflow_id="wf-002", name="daily-backup")
        with pytest.raises(ValueError, match="already exists"):
            await registry.save(spec2)

    @pytest.mark.asyncio
    async def test_same_id_same_name_allows_update(self) -> None:
        """Re-saving same workflow_id with same name is OK (upsert)."""
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec(workflow_id="wf-001", name="daily-backup")
        await registry.save(spec)

        updated = replace(spec, source_plan_id="plan-002")
        result = await registry.save(updated)
        assert result == "wf-001"

    @pytest.mark.asyncio
    async def test_different_names_different_ids_ok(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec1 = _make_spec(workflow_id="wf-001", name="workflow-A")
        spec2 = _make_spec(workflow_id="wf-002", name="workflow-B")
        await registry.save(spec1)
        result = await registry.save(spec2)
        assert result == "wf-002"
        assert len(storage.workflows) == 2

    @pytest.mark.asyncio
    async def test_duplicate_check_includes_inactive(self) -> None:
        """Duplicate check is across ALL workflows, not just active."""
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec1 = _make_spec(workflow_id="wf-001", name="daily-backup")
        await registry.save(spec1)
        await registry.delete("wf-001")

        spec2 = _make_spec(workflow_id="wf-002", name="daily-backup")
        with pytest.raises(ValueError, match="already exists"):
            await registry.save(spec2)


# ===========================================================================
# TestSaveSuccess
# ===========================================================================


class TestSaveSuccess:
    """save() persists via storage correctly."""

    @pytest.mark.asyncio
    async def test_save_persists_spec(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        assert "wf-001" in storage.workflows
        assert storage.workflows["wf-001"].name == "Test Workflow"

    @pytest.mark.asyncio
    async def test_save_returns_workflow_id(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec(workflow_id="my-wf-99")
        result = await registry.save(spec)
        assert result == "my-wf-99"

    @pytest.mark.asyncio
    async def test_save_multiple_workflows(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        for i in range(5):
            spec = _make_spec(workflow_id=f"wf-{i}", name=f"Workflow {i}")
            await registry.save(spec)
        assert len(storage.workflows) == 5


# ===========================================================================
# TestGetWorkflow
# ===========================================================================


class TestGetWorkflow:
    """get() returns spec or None."""

    @pytest.mark.asyncio
    async def test_get_existing(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        result = await registry.get("wf-001")
        assert result is not None
        assert result.name == "Test Workflow"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        result = await registry.get("wf-missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_increments_storage_calls(self) -> None:
        """STATELESS: every get() goes through storage."""
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        storage.get_workflow_calls = 0

        await registry.get("wf-001")
        await registry.get("wf-001")
        await registry.get("wf-001")
        assert storage.get_workflow_calls == 3


# ===========================================================================
# TestListActive
# ===========================================================================


class TestListActive:
    """list_active() filters by active=True."""

    @pytest.mark.asyncio
    async def test_list_active_empty(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        result = await registry.list_active()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_active_filters(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec1 = _make_spec(workflow_id="wf-1", name="Active")
        spec2 = _make_spec(workflow_id="wf-2", name="Inactive", active=False)
        # Directly insert (bypass save validation for inactive spec)
        storage.workflows["wf-1"] = spec1
        storage.workflows["wf-2"] = spec2

        result = await registry.list_active()
        assert len(result) == 1
        assert result[0].workflow_id == "wf-1"

    @pytest.mark.asyncio
    async def test_list_active_after_delete(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        await registry.delete("wf-001")

        result = await registry.list_active()
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_active_multiple(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        for i in range(3):
            spec = _make_spec(workflow_id=f"wf-{i}", name=f"WF {i}")
            await registry.save(spec)
        result = await registry.list_active()
        assert len(result) == 3


# ===========================================================================
# TestSoftDelete
# ===========================================================================


class TestSoftDelete:
    """delete() sets active=False, preserves for audit."""

    @pytest.mark.asyncio
    async def test_delete_sets_inactive(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        await registry.delete("wf-001")

        wf = storage.workflows["wf-001"]
        assert wf.active is False

    @pytest.mark.asyncio
    async def test_delete_preserves_workflow(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        await registry.delete("wf-001")

        assert "wf-001" in storage.workflows
        result = await registry.get("wf-001")
        assert result is not None
        assert result.active is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_safe(self) -> None:
        """Deleting a nonexistent workflow should not raise."""
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        await registry.delete("wf-missing")  # No exception


# ===========================================================================
# TestHardDelete
# ===========================================================================


class TestHardDelete:
    """purge() permanently removes workflow."""

    @pytest.mark.asyncio
    async def test_purge_removes_completely(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        await registry.purge("wf-001")

        assert "wf-001" not in storage.workflows
        result = await registry.get("wf-001")
        assert result is None

    @pytest.mark.asyncio
    async def test_purge_nonexistent_is_safe(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        await registry.purge("wf-missing")  # No exception

    @pytest.mark.asyncio
    async def test_purge_removes_trigger_too(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        trigger = _make_trigger(
            trigger_type=TriggerType.CRON,
            schedule="0 9 * * MON",
        )
        spec = _make_spec(trigger=trigger)
        await registry.save(spec)
        await storage.save_trigger("wf-001", trigger)
        assert "wf-001" in storage.triggers

        await registry.purge("wf-001")
        assert "wf-001" not in storage.triggers


# ===========================================================================
# TestUpdateTrigger
# ===========================================================================


class TestUpdateTrigger:
    """update_trigger() validates trigger, bumps version."""

    @pytest.mark.asyncio
    async def test_update_trigger_basic(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)

        new_trigger = _make_trigger(
            trigger_type=TriggerType.CRON,
            schedule="0 8 * * FRI",
        )
        await registry.update_trigger("wf-001", new_trigger)

        updated = storage.workflows["wf-001"]
        assert updated.trigger.type == TriggerType.CRON
        assert updated.trigger.schedule == "0 8 * * FRI"

    @pytest.mark.asyncio
    async def test_update_trigger_bumps_version(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec(version="1.0.0")
        await registry.save(spec)

        new_trigger = _make_trigger(
            trigger_type=TriggerType.CRON,
            schedule="0 8 * * FRI",
        )
        await registry.update_trigger("wf-001", new_trigger)

        updated = storage.workflows["wf-001"]
        assert updated.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_update_trigger_saves_trigger_to_storage(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)

        new_trigger = _make_trigger(
            trigger_type=TriggerType.EVENT,
            event_topic="system.alarm",
        )
        await registry.update_trigger("wf-001", new_trigger)

        assert "wf-001" in storage.triggers
        assert storage.triggers["wf-001"].event_topic == "system.alarm"

    @pytest.mark.asyncio
    async def test_update_trigger_not_found_raises(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        trigger = _make_trigger()
        with pytest.raises(ValueError, match="not found"):
            await registry.update_trigger("wf-missing", trigger)

    @pytest.mark.asyncio
    async def test_update_trigger_invalid_trigger_raises(self) -> None:
        """CRON without schedule should raise during validation."""
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)

        with pytest.raises(ValueError, match="schedule"):
            await registry.update_trigger(
                "wf-001",
                TriggerSpec(type=TriggerType.CRON),
            )

    @pytest.mark.asyncio
    async def test_update_trigger_updates_updated_at(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        original_updated_at = storage.workflows["wf-001"].updated_at

        new_trigger = _make_trigger()
        await registry.update_trigger("wf-001", new_trigger)

        updated = storage.workflows["wf-001"]
        assert updated.updated_at >= original_updated_at


# ===========================================================================
# TestBumpVersion
# ===========================================================================


class TestBumpVersion:
    """bump_version() creates new version (monotonic major semver)."""

    @pytest.mark.asyncio
    async def test_bump_version_basic(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec(version="1.0.0")
        await registry.save(spec)

        new_steps = [_make_step("s1", "cap.new"), _make_step("s2", "cap.extra")]
        new_version = await registry.bump_version("wf-001", new_steps, {"s2": ["s1"]})
        assert new_version == "2.0.0"

    @pytest.mark.asyncio
    async def test_bump_version_updates_storage(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec(version="1.0.0")
        await registry.save(spec)

        new_steps = [_make_step("s1", "cap.v2")]
        await registry.bump_version("wf-001", new_steps, {})

        updated = storage.workflows["wf-001"]
        assert updated.version == "2.0.0"
        assert len(updated.steps) == 1
        assert updated.steps[0].capability == "cap.v2"

    @pytest.mark.asyncio
    async def test_bump_version_updates_deps(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec(version="1.0.0")
        await registry.save(spec)

        new_steps = [_make_step("s1"), _make_step("s2")]
        new_deps = {"s2": ["s1"]}
        await registry.bump_version("wf-001", new_steps, new_deps)

        updated = storage.workflows["wf-001"]
        assert updated.dependencies == {"s2": ["s1"]}

    @pytest.mark.asyncio
    async def test_bump_version_not_found_raises(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        with pytest.raises(ValueError, match="not found"):
            await registry.bump_version("wf-missing", [_make_step()], {})

    @pytest.mark.asyncio
    async def test_bump_version_empty_steps_raises(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        with pytest.raises(ValueError, match="non-empty"):
            await registry.bump_version("wf-001", [], {})

    @pytest.mark.asyncio
    async def test_bump_version_custom_summary(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        await registry.bump_version(
            "wf-001",
            [_make_step()],
            {},
            summary="Updated capability",
        )
        # Verify version was bumped (summary is in VersionEntry, internal)
        updated = storage.workflows["wf-001"]
        assert updated.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_bump_version_custom_source_plan(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        await registry.bump_version(
            "wf-001",
            [_make_step()],
            {},
            source_plan_id="plan-new",
        )
        updated = storage.workflows["wf-001"]
        assert updated.source_plan_id == "plan-new"

    @pytest.mark.asyncio
    async def test_bump_version_preserves_trigger(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        trigger = _make_trigger(trigger_type=TriggerType.CRON, schedule="0 9 * * MON")
        spec = _make_spec(trigger=trigger)
        await registry.save(spec)
        await registry.bump_version("wf-001", [_make_step()], {})
        updated = storage.workflows["wf-001"]
        assert updated.trigger.type == TriggerType.CRON


# ===========================================================================
# TestBumpVersionPointer
# ===========================================================================


class TestBumpVersionPointer:
    """_bump() static method logic (embedded WorkflowVersionPointer 4.1.4)."""

    def test_bump_increments_major(self) -> None:
        pointer = WorkflowVersionPointer(
            workflow_id="wf-001",
            active_version="1.0.0",
        )
        result = WorkflowRegistry._bump(pointer, "plan-001", [_make_step()], "test")
        assert result == "2.0.0"
        assert pointer.active_version == "2.0.0"

    def test_bump_appends_version_entry(self) -> None:
        pointer = WorkflowVersionPointer(
            workflow_id="wf-001",
            active_version="1.0.0",
        )
        WorkflowRegistry._bump(pointer, "plan-001", [_make_step()], "summary")
        assert len(pointer.version_history) == 1
        entry = pointer.version_history[0]
        assert entry.version == "2.0.0"
        assert entry.source_plan_id == "plan-001"
        assert entry.step_count == 1
        assert entry.change_summary == "summary"

    def test_bump_successive(self) -> None:
        pointer = WorkflowVersionPointer(
            workflow_id="wf-001",
            active_version="1.0.0",
        )
        v2 = WorkflowRegistry._bump(pointer, "plan-2", [_make_step()], "v2")
        v3 = WorkflowRegistry._bump(pointer, "plan-3", [_make_step()], "v3")
        assert v2 == "2.0.0"
        assert v3 == "3.0.0"
        assert len(pointer.version_history) == 2

    def test_bump_step_count_reflects_new_steps(self) -> None:
        pointer = WorkflowVersionPointer(
            workflow_id="wf-001",
            active_version="1.0.0",
        )
        steps = [_make_step(f"s{i}") for i in range(5)]
        WorkflowRegistry._bump(pointer, "plan", steps, "test")
        assert pointer.version_history[0].step_count == 5


# ===========================================================================
# TestVersionMonotonic
# ===========================================================================


class TestVersionMonotonic:
    """Version bumps are monotonic and append-only."""

    @pytest.mark.asyncio
    async def test_sequential_bumps(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec(version="1.0.0")
        await registry.save(spec)

        v2 = await registry.bump_version("wf-001", [_make_step()], {})
        v3 = await registry.bump_version("wf-001", [_make_step()], {})
        v4 = await registry.bump_version("wf-001", [_make_step()], {})

        assert v2 == "2.0.0"
        assert v3 == "3.0.0"
        assert v4 == "4.0.0"

    @pytest.mark.asyncio
    async def test_bump_after_trigger_update(self) -> None:
        """Trigger update bumps to 2.0.0, explicit bump goes to 3.0.0."""
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec(version="1.0.0")
        await registry.save(spec)

        await registry.update_trigger(
            "wf-001",
            _make_trigger(TriggerType.CRON, schedule="0 9 * * MON"),
        )
        assert storage.workflows["wf-001"].version == "2.0.0"

        v3 = await registry.bump_version("wf-001", [_make_step()], {})
        assert v3 == "3.0.0"


# ===========================================================================
# TestStateless
# ===========================================================================


class TestStateless:
    """No in-memory cache -- repeated reads hit storage every time."""

    @pytest.mark.asyncio
    async def test_get_always_reads_storage(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        spec = _make_spec()
        await registry.save(spec)
        storage.get_workflow_calls = 0

        for _ in range(5):
            await registry.get("wf-001")

        assert storage.get_workflow_calls == 5

    @pytest.mark.asyncio
    async def test_list_always_reads_storage(self) -> None:
        storage = FakeWorkflowStorage()
        registry = WorkflowRegistry(storage)
        storage.list_workflows_calls = 0

        for _ in range(3):
            await registry.list_active()

        assert storage.list_workflows_calls == 3

    @pytest.mark.asyncio
    async def test_no_cache_attributes(self) -> None:
        """Registry should have NO internal cache dict/list."""
        registry = WorkflowRegistry(FakeWorkflowStorage())
        attrs = vars(registry)
        for name, val in attrs.items():
            if name == "_storage":
                continue
            assert not isinstance(val, (dict, list, set)), f"Unexpected cache attribute: {name}"


# ===========================================================================
# TestWorkflowTypes
# ===========================================================================


class TestWorkflowTypes:
    """WorkflowSpec, VersionEntry type validation."""

    def test_workflow_spec_is_frozen(self) -> None:
        spec = _make_spec()
        with pytest.raises(AttributeError):
            spec.name = "mutated"  # type: ignore[misc]

    def test_version_entry_is_frozen(self) -> None:
        entry = VersionEntry(
            version="1.0.0",
            created_at=time.time(),
            source_plan_id="plan-1",
            step_count=3,
            change_summary="test",
        )
        with pytest.raises(AttributeError):
            entry.version = "2.0.0"  # type: ignore[misc]

    def test_workflow_version_pointer_is_mutable(self) -> None:
        pointer = WorkflowVersionPointer(
            workflow_id="wf-1",
            active_version="1.0.0",
        )
        pointer.active_version = "2.0.0"
        assert pointer.active_version == "2.0.0"

    def test_workflow_spec_validation_bad_version(self) -> None:
        with pytest.raises(ValueError, match="semver"):
            _make_spec(version="1.0")

    def test_workflow_spec_validation_no_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            _make_spec(name="")

    def test_workflow_spec_validation_no_steps(self) -> None:
        with pytest.raises(ValueError, match="steps"):
            _make_spec(steps=[])

    def test_workflow_spec_valid_versions(self) -> None:
        for v in ["1.0.0", "2.0.0", "100.0.0", "0.0.0"]:
            spec = _make_spec(version=v)
            assert spec.version == v


# ===========================================================================
# TestDynamicExprParse
# ===========================================================================


class TestDynamicExprParse:
    """DynamicExpr.parse() regex matching."""

    def test_parse_date_today(self) -> None:
        result = DynamicExpr.parse("${date.today}")
        assert result is not None
        assert result.namespace == "date"
        assert result.field == "today"
        assert result.offset is None

    def test_parse_date_now(self) -> None:
        result = DynamicExpr.parse("${date.now}")
        assert result is not None
        assert result.namespace == "date"
        assert result.field == "now"

    def test_parse_with_positive_offset(self) -> None:
        result = DynamicExpr.parse("${date.today +2d}")
        assert result is not None
        assert result.offset == "+2d"

    def test_parse_with_negative_offset(self) -> None:
        result = DynamicExpr.parse("${date.now -1h}")
        assert result is not None
        assert result.offset == "-1h"

    def test_parse_user_timezone(self) -> None:
        result = DynamicExpr.parse("${user.timezone}")
        assert result is not None
        assert result.namespace == "user"
        assert result.field == "timezone"

    def test_parse_user_locale(self) -> None:
        result = DynamicExpr.parse("${user.locale}")
        assert result is not None
        assert result.namespace == "user"
        assert result.field == "locale"

    def test_parse_plain_value_returns_none(self) -> None:
        assert DynamicExpr.parse("hello world") is None

    def test_parse_partial_match_returns_none(self) -> None:
        assert DynamicExpr.parse("prefix ${date.today} suffix") is None

    def test_parse_number_returns_none(self) -> None:
        assert DynamicExpr.parse("42") is None

    def test_parse_non_string_returns_none(self) -> None:
        assert DynamicExpr.parse(42) is None  # type: ignore[arg-type]

    def test_parse_empty_string_returns_none(self) -> None:
        assert DynamicExpr.parse("") is None

    def test_parse_minutes_offset(self) -> None:
        result = DynamicExpr.parse("${date.now +30m}")
        assert result is not None
        assert result.offset == "+30m"

    def test_parse_seconds_offset(self) -> None:
        result = DynamicExpr.parse("${date.now -120s}")
        assert result is not None
        assert result.offset == "-120s"

    def test_parse_hours_offset(self) -> None:
        result = DynamicExpr.parse("${date.now +24h}")
        assert result is not None
        assert result.offset == "+24h"

    def test_dynamic_expr_is_frozen(self) -> None:
        expr = DynamicExpr.parse("${date.today}")
        assert expr is not None
        with pytest.raises(AttributeError):
            expr.namespace = "mutated"  # type: ignore[misc]

    def test_parse_raw_preserved(self) -> None:
        raw = "${date.today +2d}"
        result = DynamicExpr.parse(raw)
        assert result is not None
        assert result.raw == raw


# ===========================================================================
# TestIWorkflowStoragePort
# ===========================================================================


class TestIWorkflowStoragePort:
    """Port is runtime_checkable Protocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        assert isinstance(FakeWorkflowStorage(), IWorkflowStoragePort)

    def test_has_12_methods(self) -> None:
        """Port defines 12 async methods (11 original + purge_workflow)."""
        import inspect

        methods = [
            name
            for name, _ in inspect.getmembers(IWorkflowStoragePort, predicate=inspect.isfunction)
            if not name.startswith("_")
        ]
        assert len(methods) == 12

    def test_port_method_names(self) -> None:
        import inspect

        methods = sorted(
            name
            for name, _ in inspect.getmembers(IWorkflowStoragePort, predicate=inspect.isfunction)
            if not name.startswith("_")
        )
        expected = sorted(
            [
                "delete_workflow",
                "get_due_triggers",
                "get_pending_gaps",
                "get_runs",
                "get_workflow",
                "list_workflows",
                "purge_workflow",
                "save_gap",
                "save_run",
                "save_trigger",
                "save_workflow",
                "update_trigger_state",
            ]
        )
        assert methods == expected
