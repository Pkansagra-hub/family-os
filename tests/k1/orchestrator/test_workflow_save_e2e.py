"""Epic 7.3A.3 -- Workflow save + trigger end-to-end integration tests.

Process-only integration path:
  - Build plan through HIGH-tier process() two-phase flow.
  - Save workflow via process(WorkflowSaveRequest).
  - Fire triggers and execute via process(WorkflowRunRequest).

No direct subsystem construction; all access via OrchestratorFactory.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_WORKFLOW_SAVED
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    CommittedPlan,
    PlanStep,
    ProcessResult,
    RegistryEntry,
    TaskEnvelope,
    TriggerSpec,
    TriggerType,
    WorkflowRunRequest,
    WorkflowSaveRequest,
)


def _entry(name: str) -> RegistryEntry:
    return RegistryEntry(
        name=name,
        provider_type="mock",
        safety_band_min="GREEN",
        availability="AVAILABLE",
        estimated_duration_ms=100,
    )


def _high_envelope(*, trace_id: str | None = None, session_id: str = "s-wf-save") -> TaskEnvelope:
    return TaskEnvelope(
        intent="workflow-save-e2e",
        trace_id=trace_id or str(uuid4()),
        tier="HIGH",
        capabilities=[],
        params={},
        context={"session_id": session_id},
    )


async def _svc():
    service = await OrchestratorFactory.create_standalone()
    engine = service._workflow_engine
    storage = engine.registry._storage
    return (
        service,
        service._fabric_port,
        service._planner_port,
        service._mailbox,
        service._delta_port,
        service._event_port,
        service._bridge_port,
        engine,
        storage,
    )


async def _run_high_plan_success(service, fabric, planner, *, capability: str) -> tuple[str, str]:
    fabric.register_capability(capability, _entry(capability))

    envelope = _high_envelope()
    phase1 = await service.process(envelope)
    assert phase1 == ProcessResult.DEFERRED

    request_id = planner.request_log[-1].request_id
    plan_id = f"plan-{uuid4()}"
    plan = CommittedPlan(
        plan_id=plan_id,
        request_id=request_id,
        intent=envelope.intent,
        steps=[PlanStep(id="s1", capability=capability)],
        dependencies={},
        trace_id=envelope.trace_id,
    )

    phase2 = await service.process(plan)
    assert phase2 == ProcessResult.COMPLETED
    return plan_id, envelope.trace_id


async def _save_workflow(
    service,
    *,
    committed_plan_id: str,
    workflow_name: str,
    trigger_spec: TriggerSpec,
    trace_id: str | None = None,
) -> ProcessResult:
    return await service.process(
        WorkflowSaveRequest(
            committed_plan_id=committed_plan_id,
            workflow_name=workflow_name,
            trigger_spec=trigger_spec,
            trace_id=trace_id or str(uuid4()),
        )
    )


class TestWorkflowSaveE2E:
    @pytest.mark.asyncio
    async def test_high_success_then_save_workflow_persists_spec(self) -> None:
        service, fabric, planner, _, delta, _, _, _, storage = await _svc()

        plan_id, trace_id = await _run_high_plan_success(
            service,
            fabric,
            planner,
            capability="tool.wf.save.persist",
        )

        save_result = await _save_workflow(
            service,
            committed_plan_id=plan_id,
            workflow_name="wf-save-persist",
            trigger_spec=TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *"),
            trace_id=trace_id,
        )

        assert save_result == ProcessResult.COMPLETED
        delta.assert_emitted(ORCH_WORKFLOW_SAVED, count=1)

        workflows = await storage.list_workflows(active_only=False)
        saved = [wf for wf in workflows if wf.name == "wf-save-persist"]
        assert len(saved) == 1
        assert saved[0].source_plan_id == plan_id
        assert saved[0].trigger.type == TriggerType.CRON
        assert saved[0].workflow_id in storage.triggers

    @pytest.mark.asyncio
    async def test_scheduler_cron_tick_generates_run_request_and_executes(self) -> None:
        service, fabric, planner, mailbox, delta, _, bridge, engine, storage = await _svc()

        plan_id, _ = await _run_high_plan_success(
            service,
            fabric,
            planner,
            capability="tool.wf.save.cron",
        )

        save_result = await _save_workflow(
            service,
            committed_plan_id=plan_id,
            workflow_name="wf-save-cron-run",
            trigger_spec=TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *"),
        )
        assert save_result == ProcessResult.COMPLETED

        await engine.scheduler._tick()
        msg = mailbox.dequeue()
        assert isinstance(msg, WorkflowRunRequest)
        assert msg.trigger_type == TriggerType.CRON

        dag_completed_before = len(delta.get_emitted(ORCH_DAG_COMPLETED))
        run_result = await service.process(msg)
        assert run_result == ProcessResult.COMPLETED
        assert len(delta.get_emitted(ORCH_DAG_COMPLETED)) > dag_completed_before

        workflows = await storage.list_workflows(active_only=False)
        wf_id = next(w.workflow_id for w in workflows if w.name == "wf-save-cron-run")
        runs = await storage.get_runs(wf_id)
        assert runs
        assert runs[0].status.value == "COMPLETED"
        assert bridge.audit_log

    @pytest.mark.asyncio
    async def test_trigger_state_persists_across_restart_cycle(self) -> None:
        service, fabric, planner, _, _, _, _, engine, storage = await _svc()

        plan_id, _ = await _run_high_plan_success(
            service,
            fabric,
            planner,
            capability="tool.wf.save.restart",
        )
        save_result = await _save_workflow(
            service,
            committed_plan_id=plan_id,
            workflow_name="wf-save-restart",
            trigger_spec=TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *"),
        )
        assert save_result == ProcessResult.COMPLETED

        await engine.scheduler._tick()
        workflows = await storage.list_workflows(active_only=False)
        wf = next(w for w in workflows if w.name == "wf-save-restart")
        next_fire_before, last_fire_before = storage.trigger_times[wf.workflow_id]

        await service.init()
        await asyncio.sleep(0.01)
        await service.shutdown()

        restarted = await OrchestratorFactory.create_for_testing(overrides={"storage": storage})
        await restarted.init()
        try:
            next_fire_after, last_fire_after = storage.trigger_times[wf.workflow_id]
            assert next_fire_after == next_fire_before
            assert last_fire_after == last_fire_before
        finally:
            await restarted.shutdown()

    @pytest.mark.asyncio
    async def test_event_trigger_matching_event_then_tick_executes(self) -> None:
        service, fabric, planner, mailbox, _, event, _, engine, storage = await _svc()

        plan_id, _ = await _run_high_plan_success(
            service,
            fabric,
            planner,
            capability="tool.wf.save.event",
        )
        topic = "k1.demo.workflow.event.v1"
        save_result = await _save_workflow(
            service,
            committed_plan_id=plan_id,
            workflow_name="wf-save-event",
            trigger_spec=TriggerSpec(type=TriggerType.EVENT, event_topic=topic),
        )
        assert save_result == ProcessResult.COMPLETED

        event.fire(topic, {"kind": "match"})
        await engine.scheduler._tick()

        msg = mailbox.dequeue()
        assert isinstance(msg, WorkflowRunRequest)
        assert msg.trigger_type == TriggerType.EVENT

        result = await service.process(msg)
        assert result == ProcessResult.COMPLETED

        workflows = await storage.list_workflows(active_only=False)
        saved = next(w for w in workflows if w.name == "wf-save-event")
        runs = await storage.get_runs(saved.workflow_id)
        assert runs and runs[0].status.value == "COMPLETED"

    @pytest.mark.asyncio
    async def test_invalid_save_rejected_when_plan_not_found(self) -> None:
        service, _, _, _, _, _, _, _, storage = await _svc()

        result = await _save_workflow(
            service,
            committed_plan_id="plan-does-not-exist",
            workflow_name="wf-save-invalid",
            trigger_spec=TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *"),
        )

        assert result == ProcessResult.FAILED
        workflows = await storage.list_workflows(active_only=False)
        assert all(w.name != "wf-save-invalid" for w in workflows)

    @pytest.mark.asyncio
    async def test_duplicate_workflow_name_is_rejected(self) -> None:
        service, fabric, planner, _, _, _, _, _, storage = await _svc()

        plan_id_a, _ = await _run_high_plan_success(
            service,
            fabric,
            planner,
            capability="tool.wf.save.dup.a",
        )
        result_a = await _save_workflow(
            service,
            committed_plan_id=plan_id_a,
            workflow_name="wf-save-dup",
            trigger_spec=TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *"),
        )
        assert result_a == ProcessResult.COMPLETED

        plan_id_b, _ = await _run_high_plan_success(
            service,
            fabric,
            planner,
            capability="tool.wf.save.dup.b",
        )
        result_b = await _save_workflow(
            service,
            committed_plan_id=plan_id_b,
            workflow_name="wf-save-dup",
            trigger_spec=TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *"),
        )

        assert result_b == ProcessResult.FAILED
        workflows = [
            w for w in await storage.list_workflows(active_only=False) if w.name == "wf-save-dup"
        ]
        assert len(workflows) == 1

    @pytest.mark.asyncio
    async def test_run_manifest_and_audit_written_per_execution(self) -> None:
        service, fabric, planner, mailbox, _, _, bridge, engine, storage = await _svc()

        plan_id, trace_id = await _run_high_plan_success(
            service,
            fabric,
            planner,
            capability="tool.wf.save.audit",
        )

        save_result = await _save_workflow(
            service,
            committed_plan_id=plan_id,
            workflow_name="wf-save-audit",
            trigger_spec=TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *"),
            trace_id=trace_id,
        )
        assert save_result == ProcessResult.COMPLETED

        await engine.scheduler._tick()
        msg = mailbox.dequeue()
        assert isinstance(msg, WorkflowRunRequest)

        run_result = await service.process(msg)
        assert run_result == ProcessResult.COMPLETED

        workflows = await storage.list_workflows(active_only=False)
        wf_id = next(w.workflow_id for w in workflows if w.name == "wf-save-audit")
        runs = await storage.get_runs(wf_id)
        assert runs
        assert runs[0].compiled_hash
        assert runs[0].status.value == "COMPLETED"

        assert bridge.audit_log
        manifest, audit_trace = bridge.audit_log[-1]
        assert manifest.get("trace_id") == audit_trace

    @pytest.mark.asyncio
    async def test_orch11_workflow_contract_saved_steps_and_dependencies(self) -> None:
        service, fabric, planner, _, _, _, _, _, storage = await _svc()

        fabric.register_capability("tool.wf.save.contract.a", _entry("tool.wf.save.contract.a"))
        fabric.register_capability("tool.wf.save.contract.b", _entry("tool.wf.save.contract.b"))

        envelope = _high_envelope()
        phase1 = await service.process(envelope)
        assert phase1 == ProcessResult.DEFERRED

        request_id = planner.request_log[-1].request_id
        plan_id = f"plan-{uuid4()}"
        plan = CommittedPlan(
            plan_id=plan_id,
            request_id=request_id,
            intent=envelope.intent,
            steps=[
                PlanStep(id="s1", capability="tool.wf.save.contract.a"),
                PlanStep(id="s2", capability="tool.wf.save.contract.b", deps=["s1"]),
            ],
            dependencies={"s2": ["s1"]},
            trace_id=envelope.trace_id,
        )

        phase2 = await service.process(plan)
        assert phase2 == ProcessResult.COMPLETED

        save_result = await _save_workflow(
            service,
            committed_plan_id=plan_id,
            workflow_name="wf-save-contract",
            trigger_spec=TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *"),
        )
        assert save_result == ProcessResult.COMPLETED

        workflows = await storage.list_workflows(active_only=False)
        wf = next(w for w in workflows if w.name == "wf-save-contract")
        assert len(wf.steps) == 2
        assert wf.dependencies == {"s2": ["s1"]}

    @pytest.mark.asyncio
    async def test_orch12_depth_guard_configuration_present(self) -> None:
        service, _, _, _, _, _, _, engine, _ = await _svc()

        depth_guard = engine.cross_resolver._depth_guard
        assert depth_guard.max_depth == 3

        with pytest.raises(Exception):
            depth_guard.check(4)
