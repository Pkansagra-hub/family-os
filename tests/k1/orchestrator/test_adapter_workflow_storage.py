"""
tests.k1.orchestrator.test_adapter_workflow_storage
-- Tests for WorkflowStorageAdapter (6.1.15) and TestWorkflowStorageAdapter (6.1.16).

Coverage:
  WorkflowStorageAdapter (production):
    - Delegates all 11 methods to inner storage.
    - Wraps non-AdapterException errors as AdapterException(DEGRADED).
    - Passes through existing AdapterExceptions unchanged.

  TestWorkflowStorageAdapter (test/mock):
    - Workflow CRUD (save, get, list, delete soft, purge hard).
    - Trigger state (save, get_due with time/enabled filter, update_state).
    - Run manifests (save, get with limit + newest-first ordering).
    - Proactive gaps (save, get_pending with PENDING filter).
    - Test helpers (inject_workflow, inject_trigger, inject_run, inject_gap).
    - Assertion helpers (assert_workflow_saved, assert_run_saved, assert_gap_saved).
    - clear() resets all state.
    - call_log captures every operation.
    - __init__.py wiring: all 16 adapters importable.
"""

from __future__ import annotations

import time
from typing import Any, Optional
from unittest.mock import AsyncMock

import pytest

from k1.orchestrator.adapters.test_workflow_storage_adapter import TestWorkflowStorageAdapter
from k1.orchestrator.adapters.workflow_storage_adapter import WorkflowStorageAdapter
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import (
    AdapterError,
    ErrorSeverity,
    ProactiveGap,
    ProactiveGapStatus,
    TriggerSpec,
    TriggerType,
)
from k1.orchestrator.workflows.workflow_types import RunManifest, RunStatus, WorkflowSpec

# ---------------------------------------------------------------------------
# Fixtures -- reusable domain objects
# ---------------------------------------------------------------------------


def _make_plan_step(step_id: str = "s1", capability: str = "tool.echo") -> Any:
    """Return a minimal PlanStep-like object for WorkflowSpec construction."""
    from k1.fabric.types import PlanStep

    return PlanStep(id=step_id, capability=capability)


def _make_trigger(
    ttype: TriggerType = TriggerType.MANUAL,
    schedule: Optional[str] = None,
    event_topic: Optional[str] = None,
    enabled: bool = True,
) -> TriggerSpec:
    return TriggerSpec(
        type=ttype,
        schedule=schedule,
        event_topic=event_topic,
        enabled=enabled,
    )


def _make_workflow(
    wf_id: str = "wf-1",
    name: str = "Test Workflow",
    active: bool = True,
) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=wf_id,
        name=name,
        source_plan_id="plan-1",
        version="1.0.0",
        trigger=_make_trigger(),
        steps=[_make_plan_step()],
        dependencies={},
        active=active,
        created_at=time.time(),
        updated_at=time.time(),
        created_by="test",
    )


def _make_run_manifest(
    run_id: str = "run-1",
    workflow_id: str = "wf-1",
) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        workflow_id=workflow_id,
        version="1.0.0",
        compiled_hash="abc123",
        trigger_type="MANUAL",
        status=RunStatus.RUNNING,
        started_at=time.time(),
    )


def _make_gap(
    workflow_id: str = "wf-1",
    gap_id: str = "gap-1",
    status: ProactiveGapStatus = ProactiveGapStatus.PENDING,
) -> ProactiveGap:
    return ProactiveGap(
        workflow_id=workflow_id,
        gap_type="SCHEMA_DRIFT",
        affected_step_id="s1",
        capability_name="tool.echo",
        old_contract_version="1.0.0",
        new_contract_version="2.0.0",
        description="Schema changed",
        justification="Breaking field removed",
        gap_id=gap_id,
        status=status,
    )


# ===========================================================================
# A. WorkflowStorageAdapter (6.1.15) -- production delegation + error wrap
# ===========================================================================


class TestWorkflowStorageAdapterProduction:
    """Tests for WorkflowStorageAdapter (production wrapper)."""

    # ------------------------------------------------------------------
    # Delegation: every method calls inner storage
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_save_workflow_delegates(self) -> None:
        inner = AsyncMock()
        adapter = WorkflowStorageAdapter(inner)
        spec = _make_workflow()
        await adapter.save_workflow(spec)
        inner.save_workflow.assert_awaited_once_with(spec)

    @pytest.mark.asyncio
    async def test_get_workflow_delegates(self) -> None:
        inner = AsyncMock()
        inner.get_workflow.return_value = _make_workflow()
        adapter = WorkflowStorageAdapter(inner)
        result = await adapter.get_workflow("wf-1")
        inner.get_workflow.assert_awaited_once_with("wf-1")
        assert result is not None
        assert result.workflow_id == "wf-1"

    @pytest.mark.asyncio
    async def test_get_workflow_returns_none(self) -> None:
        inner = AsyncMock()
        inner.get_workflow.return_value = None
        adapter = WorkflowStorageAdapter(inner)
        assert await adapter.get_workflow("nope") is None

    @pytest.mark.asyncio
    async def test_list_workflows_delegates(self) -> None:
        inner = AsyncMock()
        inner.list_workflows.return_value = [_make_workflow()]
        adapter = WorkflowStorageAdapter(inner)
        result = await adapter.list_workflows(active_only=True)
        inner.list_workflows.assert_awaited_once_with(True)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_workflows_all(self) -> None:
        inner = AsyncMock()
        inner.list_workflows.return_value = []
        adapter = WorkflowStorageAdapter(inner)
        await adapter.list_workflows(active_only=False)
        inner.list_workflows.assert_awaited_once_with(False)

    @pytest.mark.asyncio
    async def test_delete_workflow_delegates(self) -> None:
        inner = AsyncMock()
        adapter = WorkflowStorageAdapter(inner)
        await adapter.delete_workflow("wf-1")
        inner.delete_workflow.assert_awaited_once_with("wf-1")

    @pytest.mark.asyncio
    async def test_purge_workflow_delegates(self) -> None:
        inner = AsyncMock()
        adapter = WorkflowStorageAdapter(inner)
        await adapter.purge_workflow("wf-1")
        inner.purge_workflow.assert_awaited_once_with("wf-1")

    @pytest.mark.asyncio
    async def test_save_trigger_delegates(self) -> None:
        inner = AsyncMock()
        adapter = WorkflowStorageAdapter(inner)
        trigger = _make_trigger()
        await adapter.save_trigger("wf-1", trigger)
        inner.save_trigger.assert_awaited_once_with("wf-1", trigger)

    @pytest.mark.asyncio
    async def test_get_due_triggers_delegates(self) -> None:
        inner = AsyncMock()
        inner.get_due_triggers.return_value = [("wf-1", _make_trigger())]
        adapter = WorkflowStorageAdapter(inner)
        result = await adapter.get_due_triggers(100.0)
        inner.get_due_triggers.assert_awaited_once_with(100.0)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_update_trigger_state_delegates(self) -> None:
        inner = AsyncMock()
        adapter = WorkflowStorageAdapter(inner)
        await adapter.update_trigger_state("wf-1", 200.0, 100.0)
        inner.update_trigger_state.assert_awaited_once_with("wf-1", 200.0, 100.0)

    @pytest.mark.asyncio
    async def test_save_run_delegates(self) -> None:
        inner = AsyncMock()
        adapter = WorkflowStorageAdapter(inner)
        manifest = _make_run_manifest()
        await adapter.save_run(manifest)
        inner.save_run.assert_awaited_once_with(manifest)

    @pytest.mark.asyncio
    async def test_get_runs_delegates(self) -> None:
        inner = AsyncMock()
        inner.get_runs.return_value = [_make_run_manifest()]
        adapter = WorkflowStorageAdapter(inner)
        result = await adapter.get_runs("wf-1", limit=5)
        inner.get_runs.assert_awaited_once_with("wf-1", 5)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_save_gap_delegates(self) -> None:
        inner = AsyncMock()
        adapter = WorkflowStorageAdapter(inner)
        gap = _make_gap()
        await adapter.save_gap(gap)
        inner.save_gap.assert_awaited_once_with(gap)

    @pytest.mark.asyncio
    async def test_get_pending_gaps_delegates(self) -> None:
        inner = AsyncMock()
        inner.get_pending_gaps.return_value = [_make_gap()]
        adapter = WorkflowStorageAdapter(inner)
        result = await adapter.get_pending_gaps()
        inner.get_pending_gaps.assert_awaited_once()
        assert len(result) == 1

    # ------------------------------------------------------------------
    # Error wrapping: non-AdapterException -> AdapterException(DEGRADED)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_save_workflow_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.save_workflow.side_effect = RuntimeError("disk full")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException) as exc_info:
            await adapter.save_workflow(_make_workflow())
        err = exc_info.value.detail
        assert err.severity == ErrorSeverity.DEGRADED
        assert err.adapter_name == "workflow_storage"
        assert err.operation == "save_workflow"
        assert "disk full" in err.error_message

    @pytest.mark.asyncio
    async def test_get_workflow_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.get_workflow.side_effect = IOError("read error")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException) as exc_info:
            await adapter.get_workflow("wf-1")
        assert exc_info.value.detail.operation == "get_workflow"

    @pytest.mark.asyncio
    async def test_list_workflows_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.list_workflows.side_effect = ValueError("bad query")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException):
            await adapter.list_workflows()

    @pytest.mark.asyncio
    async def test_delete_workflow_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.delete_workflow.side_effect = RuntimeError("lock")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException) as exc_info:
            await adapter.delete_workflow("wf-1")
        assert exc_info.value.detail.operation == "delete_workflow"

    @pytest.mark.asyncio
    async def test_purge_workflow_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.purge_workflow.side_effect = RuntimeError("cascade")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException):
            await adapter.purge_workflow("wf-1")

    @pytest.mark.asyncio
    async def test_save_trigger_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.save_trigger.side_effect = RuntimeError("oops")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException):
            await adapter.save_trigger("wf-1", _make_trigger())

    @pytest.mark.asyncio
    async def test_get_due_triggers_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.get_due_triggers.side_effect = RuntimeError("timeout")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException):
            await adapter.get_due_triggers(100.0)

    @pytest.mark.asyncio
    async def test_update_trigger_state_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.update_trigger_state.side_effect = RuntimeError("fail")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException):
            await adapter.update_trigger_state("wf-1", 200.0, 100.0)

    @pytest.mark.asyncio
    async def test_save_run_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.save_run.side_effect = RuntimeError("serialize")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException):
            await adapter.save_run(_make_run_manifest())

    @pytest.mark.asyncio
    async def test_get_runs_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.get_runs.side_effect = RuntimeError("corrupt")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException):
            await adapter.get_runs("wf-1")

    @pytest.mark.asyncio
    async def test_save_gap_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.save_gap.side_effect = RuntimeError("constraint")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException):
            await adapter.save_gap(_make_gap())

    @pytest.mark.asyncio
    async def test_get_pending_gaps_wraps_error(self) -> None:
        inner = AsyncMock()
        inner.get_pending_gaps.side_effect = RuntimeError("table missing")
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException):
            await adapter.get_pending_gaps()

    # ------------------------------------------------------------------
    # Passthrough: existing AdapterException is NOT double-wrapped
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_adapter_exception_passthrough(self) -> None:
        original = AdapterException(
            AdapterError(
                severity=ErrorSeverity.TERMINAL,
                adapter_name="inner",
                operation="save_workflow",
                error_code="INNER_ERROR",
                error_message="inner boom",
            )
        )
        inner = AsyncMock()
        inner.save_workflow.side_effect = original
        adapter = WorkflowStorageAdapter(inner)
        with pytest.raises(AdapterException) as exc_info:
            await adapter.save_workflow(_make_workflow())
        # Same object, not re-wrapped.
        assert exc_info.value is original
        assert exc_info.value.detail.adapter_name == "inner"


# ===========================================================================
# B. TestWorkflowStorageAdapter (6.1.16) -- in-memory mock
# ===========================================================================


class TestTestWorkflowStorageAdapterWorkflows:
    """Workflow CRUD tests for the in-memory adapter."""

    @pytest.mark.asyncio
    async def test_save_and_get_workflow(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        spec = _make_workflow("wf-1")
        await adapter.save_workflow(spec)
        result = await adapter.get_workflow("wf-1")
        assert result is not None
        assert result.workflow_id == "wf-1"
        assert result.name == "Test Workflow"

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        assert await adapter.get_workflow("nope") is None

    @pytest.mark.asyncio
    async def test_save_upserts(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_workflow(_make_workflow("wf-1", name="V1"))
        await adapter.save_workflow(_make_workflow("wf-1", name="V2"))
        result = await adapter.get_workflow("wf-1")
        assert result is not None
        assert result.name == "V2"

    @pytest.mark.asyncio
    async def test_list_workflows_active_only(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_workflow(_make_workflow("wf-1", active=True))
        await adapter.save_workflow(_make_workflow("wf-2", active=False))
        active = await adapter.list_workflows(active_only=True)
        assert len(active) == 1
        assert active[0].workflow_id == "wf-1"

    @pytest.mark.asyncio
    async def test_list_workflows_all(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_workflow(_make_workflow("wf-1", active=True))
        await adapter.save_workflow(_make_workflow("wf-2", active=False))
        all_wfs = await adapter.list_workflows(active_only=False)
        assert len(all_wfs) == 2

    @pytest.mark.asyncio
    async def test_delete_soft_deletes(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_workflow(_make_workflow("wf-1"))
        await adapter.delete_workflow("wf-1")
        spec = await adapter.get_workflow("wf-1")
        assert spec is not None
        assert spec.active is False

    @pytest.mark.asyncio
    async def test_delete_missing_noop(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.delete_workflow("wf-missing")  # no error

    @pytest.mark.asyncio
    async def test_purge_hard_deletes(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_workflow(_make_workflow("wf-1"))
        await adapter.save_trigger("wf-1", _make_trigger())
        await adapter.save_run(_make_run_manifest("r1", "wf-1"))
        await adapter.save_gap(_make_gap("wf-1"))
        await adapter.purge_workflow("wf-1")
        assert await adapter.get_workflow("wf-1") is None
        assert "wf-1" not in adapter.triggers
        assert "wf-1" not in adapter.runs

    @pytest.mark.asyncio
    async def test_purge_missing_noop(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.purge_workflow("wf-missing")


class TestTestWorkflowStorageAdapterTriggers:
    """Trigger state tests."""

    @pytest.mark.asyncio
    async def test_save_and_get_due_triggers(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        trigger = _make_trigger(TriggerType.MANUAL, enabled=True)
        await adapter.save_trigger("wf-1", trigger)
        # Default next_fire=0.0, so any now > 0 should be due.
        due = await adapter.get_due_triggers(100.0)
        assert len(due) == 1
        assert due[0][0] == "wf-1"

    @pytest.mark.asyncio
    async def test_get_due_triggers_respects_fire_time(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        trigger = _make_trigger(TriggerType.MANUAL, enabled=True)
        await adapter.save_trigger("wf-1", trigger)
        await adapter.update_trigger_state("wf-1", next_fire=500.0, last_fire=0.0)
        # now=100 < next_fire=500 -> not due
        due = await adapter.get_due_triggers(100.0)
        assert len(due) == 0
        # now=600 > next_fire=500 -> due
        due = await adapter.get_due_triggers(600.0)
        assert len(due) == 1

    @pytest.mark.asyncio
    async def test_get_due_triggers_skips_disabled(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        trigger = _make_trigger(TriggerType.MANUAL, enabled=False)
        await adapter.save_trigger("wf-1", trigger)
        due = await adapter.get_due_triggers(100.0)
        assert len(due) == 0

    @pytest.mark.asyncio
    async def test_update_trigger_state(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        trigger = _make_trigger()
        await adapter.save_trigger("wf-1", trigger)
        await adapter.update_trigger_state("wf-1", 999.0, 500.0)
        assert adapter.trigger_times["wf-1"] == (999.0, 500.0)

    @pytest.mark.asyncio
    async def test_multiple_triggers_filtered(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        t1 = _make_trigger(TriggerType.MANUAL, enabled=True)
        t2 = _make_trigger(TriggerType.MANUAL, enabled=True)
        t3 = _make_trigger(TriggerType.MANUAL, enabled=False)
        await adapter.save_trigger("wf-1", t1)
        await adapter.save_trigger("wf-2", t2)
        await adapter.save_trigger("wf-3", t3)
        await adapter.update_trigger_state("wf-2", next_fire=9999.0, last_fire=0.0)
        due = await adapter.get_due_triggers(100.0)
        # wf-1: due (next=0, enabled). wf-2: not due (next=9999). wf-3: disabled.
        assert len(due) == 1
        assert due[0][0] == "wf-1"


class TestTestWorkflowStorageAdapterRuns:
    """Run manifest tests."""

    @pytest.mark.asyncio
    async def test_save_and_get_runs(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        m = _make_run_manifest("r1", "wf-1")
        await adapter.save_run(m)
        runs = await adapter.get_runs("wf-1")
        assert len(runs) == 1
        assert runs[0].run_id == "r1"

    @pytest.mark.asyncio
    async def test_get_runs_newest_first(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_run(_make_run_manifest("r1", "wf-1"))
        await adapter.save_run(_make_run_manifest("r2", "wf-1"))
        await adapter.save_run(_make_run_manifest("r3", "wf-1"))
        runs = await adapter.get_runs("wf-1")
        assert [r.run_id for r in runs] == ["r3", "r2", "r1"]

    @pytest.mark.asyncio
    async def test_get_runs_respects_limit(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        for i in range(5):
            await adapter.save_run(_make_run_manifest(f"r{i}", "wf-1"))
        runs = await adapter.get_runs("wf-1", limit=2)
        assert len(runs) == 2
        assert runs[0].run_id == "r4"  # newest

    @pytest.mark.asyncio
    async def test_get_runs_empty(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        assert await adapter.get_runs("wf-nowhere") == []

    @pytest.mark.asyncio
    async def test_runs_isolated_per_workflow(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_run(_make_run_manifest("r1", "wf-1"))
        await adapter.save_run(_make_run_manifest("r2", "wf-2"))
        assert len(await adapter.get_runs("wf-1")) == 1
        assert len(await adapter.get_runs("wf-2")) == 1


class TestTestWorkflowStorageAdapterGaps:
    """Proactive gap tests."""

    @pytest.mark.asyncio
    async def test_save_and_get_pending(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        gap = _make_gap("wf-1", "g1", ProactiveGapStatus.PENDING)
        await adapter.save_gap(gap)
        pending = await adapter.get_pending_gaps()
        assert len(pending) == 1
        assert pending[0].gap_id == "g1"

    @pytest.mark.asyncio
    async def test_get_pending_filters_non_pending(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_gap(_make_gap("wf-1", "g1", ProactiveGapStatus.PENDING))
        await adapter.save_gap(_make_gap("wf-1", "g2", ProactiveGapStatus.RESOLVED))
        await adapter.save_gap(_make_gap("wf-1", "g3", ProactiveGapStatus.ASKED))
        pending = await adapter.get_pending_gaps()
        assert len(pending) == 1
        assert pending[0].gap_id == "g1"

    @pytest.mark.asyncio
    async def test_no_pending_gaps(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        assert await adapter.get_pending_gaps() == []


class TestTestWorkflowStorageAdapterHelpers:
    """Test setup/assertion helpers."""

    @pytest.mark.asyncio
    async def test_inject_workflow(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        adapter.inject_workflow(_make_workflow("wf-1"))
        # Injected without call_log entry.
        assert len(adapter.call_log) == 0
        result = await adapter.get_workflow("wf-1")
        assert result is not None

    @pytest.mark.asyncio
    async def test_inject_trigger(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        adapter.inject_trigger("wf-1", _make_trigger(), next_fire=50.0, last_fire=10.0)
        assert adapter.trigger_times["wf-1"] == (50.0, 10.0)

    @pytest.mark.asyncio
    async def test_inject_run(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        adapter.inject_run(_make_run_manifest("r1", "wf-1"))
        runs = await adapter.get_runs("wf-1")
        assert len(runs) == 1

    @pytest.mark.asyncio
    async def test_inject_gap(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        adapter.inject_gap(_make_gap("wf-1", "g1"))
        pending = await adapter.get_pending_gaps()
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_assert_workflow_saved_pass(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_workflow(_make_workflow("wf-1"))
        adapter.assert_workflow_saved("wf-1")  # no error

    @pytest.mark.asyncio
    async def test_assert_workflow_saved_fail(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        with pytest.raises(AssertionError, match="save_workflow not called"):
            adapter.assert_workflow_saved("wf-missing")

    @pytest.mark.asyncio
    async def test_assert_run_saved_pass(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_run(_make_run_manifest("r1", "wf-1"))
        adapter.assert_run_saved("r1")

    @pytest.mark.asyncio
    async def test_assert_run_saved_fail(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        with pytest.raises(AssertionError, match="save_run not called"):
            adapter.assert_run_saved("r-missing")

    @pytest.mark.asyncio
    async def test_assert_gap_saved_pass(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_gap(_make_gap("wf-1", "g1"))
        adapter.assert_gap_saved("g1")

    @pytest.mark.asyncio
    async def test_assert_gap_saved_fail(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        with pytest.raises(AssertionError, match="save_gap not called"):
            adapter.assert_gap_saved("g-missing")

    @pytest.mark.asyncio
    async def test_clear_resets_all(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_workflow(_make_workflow("wf-1"))
        await adapter.save_trigger("wf-1", _make_trigger())
        await adapter.save_run(_make_run_manifest("r1", "wf-1"))
        await adapter.save_gap(_make_gap("wf-1"))
        adapter.clear()
        assert len(adapter.workflows) == 0
        assert len(adapter.triggers) == 0
        assert len(adapter.trigger_times) == 0
        assert len(adapter.runs) == 0
        assert len(adapter.gaps) == 0
        assert len(adapter.call_log) == 0

    @pytest.mark.asyncio
    async def test_call_log_records_operations(self) -> None:
        adapter = TestWorkflowStorageAdapter()
        await adapter.save_workflow(_make_workflow("wf-1"))
        await adapter.get_workflow("wf-1")
        await adapter.list_workflows()
        await adapter.delete_workflow("wf-1")
        ops = [op for op, _ in adapter.call_log]
        assert ops == ["save_workflow", "get_workflow", "list_workflows", "delete_workflow"]


# ===========================================================================
# C. __init__.py wiring -- all 16 adapters importable
# ===========================================================================


class TestAdapterWiring:
    """Verify all 16 adapters are properly exported from __init__.py."""

    def test_all_16_adapters_in_init(self) -> None:
        from k1.orchestrator import adapters

        expected = [
            "BridgeWriteAdapter",
            "DeltaEmitAdapter",
            "EventSubscriptionAdapter",
            "FabricGatewayAdapter",
            "MailboxAdapter",
            "MockBridgeAdapter",
            "MockFabricAdapter",
            "MockPlannerAdapter",
            "MockStateReadAdapter",
            "PlannerAdapter",
            "StateReadAdapter",
            "TestDeltaAdapter",
            "TestEventAdapter",
            "TestMailboxAdapter",
            "TestWorkflowStorageAdapter",
            "WorkflowStorageAdapter",
        ]
        assert sorted(adapters.__all__) == expected
        # Also verify each is actually importable.
        for name in expected:
            cls = getattr(adapters, name)
            assert cls is not None, f"{name} not importable from adapters"

    def test_count_is_16(self) -> None:
        from k1.orchestrator.adapters import __all__

        assert len(__all__) == 16
