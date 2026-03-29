"""Epic 7.5.3 -- Orchestrator + real WorkflowStorage integration tests.

These tests wire a real SQLite-backed workflow storage adapter while keeping
all other Orchestrator ports as in-memory test adapters.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.adapters.mock_state_read_adapter import MockStateReadAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.adapters.test_mailbox_adapter import TestMailboxAdapter
from k1.orchestrator.adapters.workflow_storage_adapter import WorkflowStorageAdapter
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    PlanStep,
    ProactiveGap,
    ProactiveGapStatus,
    ProcessResult,
    RegistryEntry,
    TriggerSpec,
    TriggerType,
    WorkflowRunRequest,
)
from k1.orchestrator.workflows.persistence.sqlite_adapter import SQLiteWorkflowAdapter
from k1.orchestrator.workflows.workflow_types import WorkflowSpec


def _step(step_id: str = "s1", capability: str = "tool.workflow.storage.test") -> PlanStep:
    return PlanStep(id=step_id, capability=capability, params={"q": "ok"})


def _spec(
    *,
    workflow_id: str,
    name: str,
    trigger: TriggerSpec,
    active: bool = True,
    capability: str = "tool.workflow.storage.test",
) -> WorkflowSpec:
    now = time.time()
    return WorkflowSpec(
        workflow_id=workflow_id,
        name=name,
        source_plan_id="plan-storage-int",
        version="1.0.0",
        trigger=trigger,
        steps=[_step(capability=capability)],
        dependencies={},
        active=active,
        created_at=now,
        updated_at=now,
        created_by="test",
    )


async def _make_service_with_real_storage(db_path: str):
    raw_sqlite = SQLiteWorkflowAdapter(db_path)
    storage = WorkflowStorageAdapter(raw_sqlite)

    mailbox = TestMailboxAdapter()
    fabric = MockFabricAdapter()
    planner = MockPlannerAdapter()
    state = MockStateReadAdapter()
    delta = TestDeltaAdapter()
    bridge = MockBridgeAdapter()
    event = TestEventAdapter()

    service = await OrchestratorFactory.create_with_ports(
        mailbox=mailbox,
        fabric=fabric,
        planner=planner,
        state=state,
        delta=delta,
        bridge=bridge,
        event=event,
        storage=storage,
    )
    await service.init()

    return service, fabric, storage, raw_sqlite


class TestOrchestratorWorkflowStorageIntegration:
    @pytest.mark.asyncio
    async def test_save_and_read_workflow_spec_roundtrip(self, tmp_path) -> None:
        db_path = tmp_path / "workflow_storage_roundtrip.db"
        service, _, storage, raw_sqlite = await _make_service_with_real_storage(str(db_path))
        try:
            spec = _spec(
                workflow_id="wf-rt-1",
                name="wf-roundtrip",
                trigger=TriggerSpec(type=TriggerType.MANUAL),
            )

            await storage.save_workflow(spec)
            loaded = await storage.get_workflow("wf-rt-1")

            assert loaded == spec
        finally:
            await service.shutdown()
            raw_sqlite.close()

    @pytest.mark.asyncio
    async def test_list_active_returns_only_enabled_workflows(self, tmp_path) -> None:
        db_path = tmp_path / "workflow_storage_active.db"
        service, _, storage, raw_sqlite = await _make_service_with_real_storage(str(db_path))
        try:
            active = _spec(
                workflow_id="wf-a",
                name="wf-active",
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                active=True,
            )
            inactive = _spec(
                workflow_id="wf-b",
                name="wf-inactive",
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                active=False,
            )

            await storage.save_workflow(active)
            await storage.save_workflow(inactive)

            active_only = await storage.list_workflows(active_only=True)
            all_workflows = await storage.list_workflows(active_only=False)

            assert [w.workflow_id for w in active_only] == ["wf-a"]
            assert {w.workflow_id for w in all_workflows} == {"wf-a", "wf-b"}
        finally:
            await service.shutdown()
            raw_sqlite.close()

    @pytest.mark.asyncio
    async def test_delete_workflow_removes_from_active_registry(self, tmp_path) -> None:
        db_path = tmp_path / "workflow_storage_delete.db"
        service, _, storage, raw_sqlite = await _make_service_with_real_storage(str(db_path))
        try:
            spec = _spec(
                workflow_id="wf-del",
                name="wf-delete",
                trigger=TriggerSpec(type=TriggerType.MANUAL),
            )
            await storage.save_workflow(spec)

            await storage.delete_workflow("wf-del")

            active_only = await storage.list_workflows(active_only=True)
            loaded = await storage.get_workflow("wf-del")

            assert "wf-del" not in {w.workflow_id for w in active_only}
            assert loaded is not None
            assert loaded.active is False
        finally:
            await service.shutdown()
            raw_sqlite.close()

    @pytest.mark.asyncio
    async def test_trigger_state_persists_across_shutdown_and_reinit(self, tmp_path) -> None:
        db_path = tmp_path / "workflow_storage_trigger_state.db"

        service1, _, storage1, raw_sqlite1 = await _make_service_with_real_storage(str(db_path))
        try:
            spec = _spec(
                workflow_id="wf-trg",
                name="wf-trigger",
                trigger=TriggerSpec(type=TriggerType.CRON, schedule="0 9 * * MON"),
            )
            await storage1.save_workflow(spec)
            await storage1.save_trigger("wf-trg", spec.trigger)

            now = time.time()
            next_fire = now + 120.0
            last_fire = now - 60.0
            await storage1.update_trigger_state("wf-trg", next_fire=next_fire, last_fire=last_fire)
        finally:
            await service1.shutdown()
            raw_sqlite1.close()

        service2, _, storage2, raw_sqlite2 = await _make_service_with_real_storage(str(db_path))
        try:
            due_before = await storage2.get_due_triggers(now=next_fire - 1.0)
            due_at = await storage2.get_due_triggers(now=next_fire)

            assert due_before == []
            assert len(due_at) == 1
            assert due_at[0][0] == "wf-trg"
            assert due_at[0][1].type == TriggerType.CRON
        finally:
            await service2.shutdown()
            raw_sqlite2.close()

    @pytest.mark.asyncio
    async def test_run_manifest_audit_trail_persists_after_workflow_execution(
        self, tmp_path
    ) -> None:
        db_path = tmp_path / "workflow_storage_runs.db"
        service, fabric, storage, raw_sqlite = await _make_service_with_real_storage(str(db_path))
        try:
            capability = "tool.workflow.storage.execute"
            fabric.register_capability(
                capability,
                RegistryEntry(
                    name=capability,
                    provider_type="mock",
                    safety_band_min="GREEN",
                    availability="AVAILABLE",
                    estimated_duration_ms=50,
                ),
            )

            spec = _spec(
                workflow_id="wf-run",
                name="wf-runner",
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                capability=capability,
            )
            await storage.save_workflow(spec)

            result = await service.process(
                WorkflowRunRequest(
                    workflow_id="wf-run",
                    version="1.0.0",
                    trigger_type=TriggerType.MANUAL,
                    trace_id="trace-workflow-storage-run",
                )
            )

            runs = await storage.get_runs("wf-run", limit=1)

            assert result == ProcessResult.COMPLETED
            assert len(runs) == 1
            run = runs[0]
            assert run["workflow_id"] == "wf-run"
            assert "COMPLETED" in str(run.get("status", ""))
            assert run.get("started_at") is not None
            assert run.get("completed_at") is not None
            assert run.get("steps_total") == 1
        finally:
            await service.shutdown()
            raw_sqlite.close()

    @pytest.mark.asyncio
    async def test_proactive_gap_storage_roundtrip(self, tmp_path) -> None:
        db_path = tmp_path / "workflow_storage_gaps.db"
        service, _, storage, raw_sqlite = await _make_service_with_real_storage(str(db_path))
        try:
            spec = _spec(
                workflow_id="wf-gap",
                name="wf-gap",
                trigger=TriggerSpec(type=TriggerType.MANUAL),
            )
            await storage.save_workflow(spec)

            gap = ProactiveGap(
                workflow_id="wf-gap",
                gap_type="CAPABILITY_REMOVED",
                affected_step_id="s1",
                capability_name="tool.workflow.storage.missing",
                old_contract_version="1.0.0",
                new_contract_version="N/A",
                description="Capability removed",
                justification="Cannot execute safely",
                status=ProactiveGapStatus.PENDING,
            )

            await storage.save_gap(gap)
            pending = await storage.get_pending_gaps()

            assert len(pending) == 1
            assert pending[0].workflow_id == "wf-gap"
            assert pending[0].capability_name == "tool.workflow.storage.missing"
            assert pending[0].status == ProactiveGapStatus.PENDING
        finally:
            await service.shutdown()
            raw_sqlite.close()

    @pytest.mark.asyncio
    async def test_concurrent_save_and_load_operations_are_consistent(self, tmp_path) -> None:
        db_path = tmp_path / "workflow_storage_concurrency.db"
        service, _, storage, raw_sqlite = await _make_service_with_real_storage(str(db_path))
        try:
            specs = [
                _spec(
                    workflow_id=f"wf-conc-{i}",
                    name=f"wf-conc-{i}",
                    trigger=TriggerSpec(type=TriggerType.MANUAL),
                )
                for i in range(10)
            ]

            await asyncio.gather(*(storage.save_workflow(spec) for spec in specs))
            loaded = await asyncio.gather(
                *(storage.get_workflow(spec.workflow_id) for spec in specs)
            )

            assert all(item is not None for item in loaded)
            assert {item.workflow_id for item in loaded if item is not None} == {
                spec.workflow_id for spec in specs
            }
        finally:
            await service.shutdown()
            raw_sqlite.close()

    @pytest.mark.asyncio
    async def test_sqlite_wal_allows_concurrent_reads_and_writes(self, tmp_path) -> None:
        db_path = tmp_path / "workflow_storage_wal.db"
        service, _, storage, raw_sqlite = await _make_service_with_real_storage(str(db_path))
        try:

            async def writer() -> None:
                for i in range(20):
                    await storage.save_workflow(
                        _spec(
                            workflow_id=f"wf-wal-{i}",
                            name=f"wf-wal-{i}",
                            trigger=TriggerSpec(type=TriggerType.MANUAL),
                        )
                    )
                    await asyncio.sleep(0)

            async def reader() -> None:
                for _ in range(20):
                    await storage.list_workflows(active_only=False)
                    await asyncio.sleep(0)

            await asyncio.wait_for(asyncio.gather(writer(), reader()), timeout=5.0)

            all_workflows = await storage.list_workflows(active_only=False)
            assert len(all_workflows) >= 20
        finally:
            await service.shutdown()
            raw_sqlite.close()
