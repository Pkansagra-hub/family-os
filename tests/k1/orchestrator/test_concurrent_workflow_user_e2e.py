"""Epic 7.3A.6 -- Concurrent workflow + user task end-to-end integration tests.

Focus:
- Mailbox priority and ConcurrencyGuard interaction under active DAG load.
- Single-DAG invariant (ORCH-02) under concurrent user/workflow traffic.

Notes:
- Guard deferral behavior is exercised through service._process_one(), because
  deferral/re-enqueue logic lives in the mailbox processing path.
- Uses real in-memory adapters; no mocks beyond existing test adapters.
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

import pytest

from k1.fabric.ports.state_reader import SessionSnapshot
from k1.orchestrator.adapters.mailbox_adapter import MailboxAdapter
from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.adapters.mock_state_read_adapter import MockStateReadAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.adapters.test_workflow_storage_adapter import TestWorkflowStorageAdapter
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    CommittedPlan,
    InterruptRequest,
    PendingPlanContext,
    PlanStep,
    ProcessResult,
    RegistryEntry,
    TaskEnvelope,
    TriggerSpec,
    TriggerType,
    WorkflowRunRequest,
)
from k1.orchestrator.workflows.workflow_types import WorkflowSpec


def _entry(name: str) -> RegistryEntry:
    return RegistryEntry(
        name=name,
        provider_type="mock",
        safety_band_min="GREEN",
        availability="AVAILABLE",
        estimated_duration_ms=100,
    )


async def _svc():
    mailbox = MailboxAdapter(max_depth=256)
    fabric = MockFabricAdapter()
    planner = MockPlannerAdapter()
    state = MockStateReadAdapter()
    delta = TestDeltaAdapter()
    bridge = MockBridgeAdapter()
    event = TestEventAdapter()
    storage = TestWorkflowStorageAdapter()

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

    return service, mailbox, fabric, delta


async def _wait_until(predicate, *, timeout_s: float = 2.0, step_s: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(step_s)
    raise AssertionError("Timed out waiting for condition")


def _dag_plan(*, trace_id: str, request_id: str, plan_id: str, capability: str) -> CommittedPlan:
    return CommittedPlan(
        plan_id=plan_id,
        request_id=request_id,
        intent="concurrent-user-workflow",
        trace_id=trace_id,
        steps=[
            PlanStep(id="s1", capability=capability),
            PlanStep(id="s2", capability="tool.concurrent.user.s2", deps=["s1"]),
            PlanStep(id="s3", capability="tool.concurrent.user.s3", deps=["s2"]),
        ],
        dependencies={"s2": ["s1"], "s3": ["s2"]},
    )


def _seed_pending(service, plan: CommittedPlan) -> None:
    service._pending_plans[plan.request_id] = PendingPlanContext(
        request_id=plan.request_id,
        task_envelope=TaskEnvelope(intent="concurrent", trace_id=plan.trace_id, tier="HIGH"),
        state_snapshot=SessionSnapshot(session_id="s-concurrent"),
        created_at=time.time(),
        timeout_ms=45_000,
    )


async def _register_workflow(service, fabric, *, workflow_id: str, capability: str) -> None:
    fabric.register_capability(capability, _entry(capability))
    spec = WorkflowSpec(
        workflow_id=workflow_id,
        name=f"wf-{workflow_id}",
        source_plan_id=f"plan-{workflow_id}",
        version="1.0.0",
        trigger=TriggerSpec(type=TriggerType.MANUAL),
        steps=[PlanStep(id="w1", capability=capability)],
        dependencies={},
        active=True,
    )
    await service._workflow_engine.registry.save(spec)


class TestConcurrentWorkflowUserE2E:
    @pytest.mark.asyncio
    async def test_workflow_request_deferred_to_background_while_user_dag_active(self) -> None:
        service, mailbox, fabric, _ = await _svc()

        for cap in (
            "tool.concurrent.user.s1",
            "tool.concurrent.user.s2",
            "tool.concurrent.user.s3",
        ):
            fabric.register_capability(cap, _entry(cap))
        fabric.script_timeout("tool.concurrent.user.s1", delay_s=0.2)

        trace_id = str(uuid4())
        plan_id = f"plan-{uuid4()}"
        request_id = f"req-{uuid4()}"
        plan = _dag_plan(
            trace_id=trace_id,
            request_id=request_id,
            plan_id=plan_id,
            capability="tool.concurrent.user.s1",
        )
        _seed_pending(service, plan)

        await _register_workflow(
            service,
            fabric,
            workflow_id="wf-bg-defer",
            capability="tool.workflow.bg.defer",
        )
        workflow_req = WorkflowRunRequest(
            workflow_id="wf-bg-defer",
            version="1.0.0",
            trigger_type=TriggerType.CRON,
            trace_id=str(uuid4()),
        )

        dag_task = asyncio.create_task(service.process(plan))
        await _wait_until(lambda: service._concurrency_guard.active)

        await service._process_one(workflow_req)

        assert mailbox.depth() == 1
        assert mailbox.peek_priority() == "BACKGROUND"

        await dag_task

    @pytest.mark.asyncio
    async def test_deferred_workflow_runs_after_guard_release(self) -> None:
        service, mailbox, fabric, _ = await _svc()

        for cap in (
            "tool.concurrent.user.s1",
            "tool.concurrent.user.s2",
            "tool.concurrent.user.s3",
        ):
            fabric.register_capability(cap, _entry(cap))
        fabric.script_timeout("tool.concurrent.user.s1", delay_s=0.2)

        await _register_workflow(
            service,
            fabric,
            workflow_id="wf-after-release",
            capability="tool.workflow.after.release",
        )
        workflow_req = WorkflowRunRequest(
            workflow_id="wf-after-release",
            version="1.0.0",
            trigger_type=TriggerType.CRON,
            trace_id=str(uuid4()),
        )

        plan = _dag_plan(
            trace_id=str(uuid4()),
            request_id=f"req-{uuid4()}",
            plan_id=f"plan-{uuid4()}",
            capability="tool.concurrent.user.s1",
        )
        _seed_pending(service, plan)

        dag_task = asyncio.create_task(service.process(plan))
        await _wait_until(lambda: service._concurrency_guard.active)
        await service._process_one(workflow_req)

        dag_result = await dag_task
        assert dag_result in {ProcessResult.FAILED, ProcessResult.DEGRADED, ProcessResult.COMPLETED}
        assert service._concurrency_guard.active is False

        queued = mailbox.dequeue()
        assert isinstance(queued, WorkflowRunRequest)
        run_result = await service.process(queued)
        assert run_result == ProcessResult.COMPLETED

    @pytest.mark.asyncio
    async def test_interrupt_realtime_path_not_starved_during_active_workflow(self) -> None:
        service, _, fabric, _ = await _svc()

        await _register_workflow(
            service,
            fabric,
            workflow_id="wf-realtime",
            capability="tool.workflow.realtime",
        )
        fabric.script_timeout("tool.workflow.realtime", delay_s=0.2)

        workflow_req = WorkflowRunRequest(
            workflow_id="wf-realtime",
            version="1.0.0",
            trigger_type=TriggerType.MANUAL,
            trace_id=str(uuid4()),
        )

        wf_task = asyncio.create_task(service.process(workflow_req))
        await _wait_until(lambda: service._concurrency_guard.active)

        interrupt_result = await service.process(
            InterruptRequest(
                target_dag_id=f"plan-{uuid4()}",
                interrupt_type="CANCEL_DAG",
                reason="user-realtime-cancel",
                trace_id=str(uuid4()),
            )
        )

        assert interrupt_result == ProcessResult.CANCELLED
        await wf_task

    @pytest.mark.asyncio
    async def test_multiple_deferred_workflow_requests_fifo_within_background_band(self) -> None:
        service, mailbox, fabric, _ = await _svc()

        for cap in (
            "tool.concurrent.user.s1",
            "tool.concurrent.user.s2",
            "tool.concurrent.user.s3",
        ):
            fabric.register_capability(cap, _entry(cap))
        fabric.script_timeout("tool.concurrent.user.s1", delay_s=0.2)

        await _register_workflow(
            service, fabric, workflow_id="wf-fifo-a", capability="tool.wf.fifo.a"
        )
        await _register_workflow(
            service, fabric, workflow_id="wf-fifo-b", capability="tool.wf.fifo.b"
        )

        req_a = WorkflowRunRequest(
            workflow_id="wf-fifo-a",
            version="1.0.0",
            trigger_type=TriggerType.CRON,
            trace_id=str(uuid4()),
        )
        req_b = WorkflowRunRequest(
            workflow_id="wf-fifo-b",
            version="1.0.0",
            trigger_type=TriggerType.CRON,
            trace_id=str(uuid4()),
        )

        plan = _dag_plan(
            trace_id=str(uuid4()),
            request_id=f"req-{uuid4()}",
            plan_id=f"plan-{uuid4()}",
            capability="tool.concurrent.user.s1",
        )
        _seed_pending(service, plan)

        dag_task = asyncio.create_task(service.process(plan))
        await _wait_until(lambda: service._concurrency_guard.active)

        await service._process_one(req_a)
        await service._process_one(req_b)

        first = mailbox.dequeue()
        second = mailbox.dequeue()

        assert isinstance(first, WorkflowRunRequest)
        assert isinstance(second, WorkflowRunRequest)
        assert first.workflow_id == "wf-fifo-a"
        assert second.workflow_id == "wf-fifo-b"

        await dag_task

    @pytest.mark.asyncio
    async def test_single_dag_invariant_second_dag_message_is_deferred(self) -> None:
        service, mailbox, fabric, _ = await _svc()

        for cap in (
            "tool.concurrent.user.s1",
            "tool.concurrent.user.s2",
            "tool.concurrent.user.s3",
            "tool.concurrent.second.s1",
        ):
            fabric.register_capability(cap, _entry(cap))
        fabric.script_timeout("tool.concurrent.user.s1", delay_s=0.2)

        first_plan = _dag_plan(
            trace_id=str(uuid4()),
            request_id=f"req-{uuid4()}",
            plan_id=f"plan-{uuid4()}",
            capability="tool.concurrent.user.s1",
        )
        _seed_pending(service, first_plan)

        second_msg = TaskEnvelope(
            intent="second-high-task",
            trace_id=str(uuid4()),
            tier="HIGH",
            capabilities=[],
            params={},
            context={"session_id": "s-concurrent"},
        )

        dag_task = asyncio.create_task(service.process(first_plan))
        await _wait_until(lambda: service._concurrency_guard.active)

        await service._process_one(second_msg)
        assert mailbox.depth() == 1
        assert mailbox.peek_priority() == "BACKGROUND"

        await dag_task
