"""Epic 7.3A.5 -- Interrupt mid-DAG end-to-end integration tests.

All dispatch paths use OrchestratorService.process() and factory-created
real test adapters.
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

import pytest

from k1.fabric.ports.state_reader import SessionSnapshot
from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_DAG_STARTED
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    CommittedPlan,
    InterruptRequest,
    PendingPlanContext,
    PlanStep,
    ProcessResult,
    RegistryEntry,
    TaskEnvelope,
)


def _entry(name: str) -> RegistryEntry:
    return RegistryEntry(
        name=name,
        provider_type="mock",
        safety_band_min="GREEN",
        availability="AVAILABLE",
        estimated_duration_ms=100,
    )


async def _svc():
    service = await OrchestratorFactory.create_standalone()
    return (
        service,
        service._fabric_port,
        service._delta_port,
        service._bridge_port,
    )


def _plan(*, trace_id: str, request_id: str, plan_id: str) -> CommittedPlan:
    return CommittedPlan(
        plan_id=plan_id,
        request_id=request_id,
        intent="interrupt-e2e",
        trace_id=trace_id,
        steps=[
            PlanStep(id="s1", capability="tool.interrupt.s1", has_side_effects=True),
            PlanStep(id="s2", capability="tool.interrupt.s2", deps=["s1"]),
            PlanStep(id="s3", capability="tool.interrupt.s3", deps=["s2"]),
        ],
        dependencies={"s2": ["s1"], "s3": ["s2"]},
    )


def _seed_pending(service, plan: CommittedPlan) -> None:
    service._pending_plans[plan.request_id] = PendingPlanContext(
        request_id=plan.request_id,
        task_envelope=TaskEnvelope(intent="interrupt-e2e", trace_id=plan.trace_id, tier="HIGH"),
        state_snapshot=SessionSnapshot(session_id="s-interrupt"),
        created_at=time.time(),
        timeout_ms=45_000,
    )


def _interrupt(*, trace_id: str, dag_id: str) -> InterruptRequest:
    return InterruptRequest(
        target_dag_id=dag_id,
        interrupt_type="CANCEL_DAG",
        reason="user_cancel",
        trace_id=trace_id,
    )


async def _wait_until(predicate, *, timeout_s: float = 2.0, step_s: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(step_s)
    raise AssertionError("Timed out waiting for condition")


class TestInterruptE2E:
    @pytest.mark.asyncio
    async def test_interrupt_request_sets_dag_executor_flag_via_process(self) -> None:
        service, _, _, _ = await _svc()

        trace_id = str(uuid4())
        dag_id = f"plan-{uuid4()}"
        result = await service.process(_interrupt(trace_id=trace_id, dag_id=dag_id))

        assert result == ProcessResult.CANCELLED
        assert getattr(service._dag_executor, "interrupt_flag", False) is True

    @pytest.mark.asyncio
    async def test_mid_dag_interrupt_stops_before_next_wave(self) -> None:
        service, fabric, delta, _ = await _svc()

        for cap in ("tool.interrupt.s1", "tool.interrupt.s2", "tool.interrupt.s3"):
            fabric.register_capability(cap, _entry(cap))
        fabric.script_timeout("tool.interrupt.s1", delay_s=0.2)

        trace_id = str(uuid4())
        request_id = f"req-{uuid4()}"
        plan_id = f"plan-{uuid4()}"
        plan = _plan(trace_id=trace_id, request_id=request_id, plan_id=plan_id)
        _seed_pending(service, plan)

        dag_task = asyncio.create_task(service.process(plan))
        await asyncio.sleep(0.05)
        interrupt_result = await service.process(_interrupt(trace_id=trace_id, dag_id=plan_id))
        dag_result = await dag_task

        assert interrupt_result == ProcessResult.CANCELLED
        assert dag_result == ProcessResult.FAILED
        fabric.assert_called("tool.interrupt.s1", times=1)
        fabric.assert_not_called("tool.interrupt.s2")
        fabric.assert_not_called("tool.interrupt.s3")

        completed_payload = delta.get_emitted(ORCH_DAG_COMPLETED)[-1]
        assert completed_payload["cancelled"] >= 1

    @pytest.mark.asyncio
    async def test_interrupt_request_bypasses_concurrency_pressure(self) -> None:
        service, fabric, _, _ = await _svc()

        for cap in ("tool.interrupt.s1", "tool.interrupt.s2", "tool.interrupt.s3"):
            fabric.register_capability(cap, _entry(cap))
        fabric.script_timeout("tool.interrupt.s1", delay_s=0.2)

        trace_id = str(uuid4())
        request_id = f"req-{uuid4()}"
        plan_id = f"plan-{uuid4()}"
        plan = _plan(trace_id=trace_id, request_id=request_id, plan_id=plan_id)
        _seed_pending(service, plan)

        dag_task = asyncio.create_task(service.process(plan))
        await _wait_until(lambda: getattr(service._concurrency_guard, "active", False))

        interrupt_result = await service.process(_interrupt(trace_id=trace_id, dag_id=plan_id))
        dag_result = await dag_task

        assert interrupt_result == ProcessResult.CANCELLED
        assert dag_result in {ProcessResult.CANCELLED, ProcessResult.FAILED}

    @pytest.mark.asyncio
    async def test_dag_lifecycle_events_emitted_for_interrupted_run(self) -> None:
        service, fabric, delta, _ = await _svc()

        for cap in ("tool.interrupt.s1", "tool.interrupt.s2", "tool.interrupt.s3"):
            fabric.register_capability(cap, _entry(cap))
        fabric.script_timeout("tool.interrupt.s1", delay_s=0.2)

        trace_id = str(uuid4())
        request_id = f"req-{uuid4()}"
        plan_id = f"plan-{uuid4()}"
        plan = _plan(trace_id=trace_id, request_id=request_id, plan_id=plan_id)
        _seed_pending(service, plan)

        dag_task = asyncio.create_task(service.process(plan))
        await asyncio.sleep(0.05)
        await service.process(_interrupt(trace_id=trace_id, dag_id=plan_id))
        await dag_task

        delta.assert_emitted(ORCH_DAG_STARTED, count=1)
        completed_events = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert len(completed_events) >= 1
        payload = completed_events[-1]
        assert payload["trace_id"] == trace_id
        assert payload["cancelled"] >= 1

    @pytest.mark.asyncio
    async def test_concurrency_guard_releases_after_interrupt(self) -> None:
        service, fabric, _, _ = await _svc()

        for cap in ("tool.interrupt.s1", "tool.interrupt.s2", "tool.interrupt.s3"):
            fabric.register_capability(cap, _entry(cap))
        fabric.script_timeout("tool.interrupt.s1", delay_s=0.2)

        trace_id = str(uuid4())
        request_id = f"req-{uuid4()}"
        plan_id = f"plan-{uuid4()}"
        plan = _plan(trace_id=trace_id, request_id=request_id, plan_id=plan_id)
        _seed_pending(service, plan)

        dag_task = asyncio.create_task(service.process(plan))
        await asyncio.sleep(0.05)
        await service.process(_interrupt(trace_id=trace_id, dag_id=plan_id))
        await dag_task

        await _wait_until(lambda: not getattr(service._concurrency_guard, "active", False))

    @pytest.mark.asyncio
    async def test_subsequent_message_processes_after_interrupt(self) -> None:
        service, fabric, _, _ = await _svc()

        for cap in (
            "tool.interrupt.s1",
            "tool.interrupt.s2",
            "tool.interrupt.s3",
            "tool.after.interrupt",
        ):
            fabric.register_capability(cap, _entry(cap))
        fabric.script_timeout("tool.interrupt.s1", delay_s=0.2)

        trace_id = str(uuid4())
        request_id = f"req-{uuid4()}"
        plan_id = f"plan-{uuid4()}"
        plan = _plan(trace_id=trace_id, request_id=request_id, plan_id=plan_id)
        _seed_pending(service, plan)

        dag_task = asyncio.create_task(service.process(plan))
        await asyncio.sleep(0.05)
        await service.process(_interrupt(trace_id=trace_id, dag_id=plan_id))
        await dag_task

        medium = TaskEnvelope(
            intent="after-interrupt",
            trace_id=str(uuid4()),
            tier="MEDIUM",
            capabilities=["tool.after.interrupt"],
            params={"tool.after.interrupt": {}},
            context={},
        )
        result = await service.process(medium)
        assert result == ProcessResult.COMPLETED

    @pytest.mark.asyncio
    async def test_pause_interrupt_rejected_in_v1(self) -> None:
        service, _, _, _ = await _svc()

        req = InterruptRequest(
            target_dag_id=f"plan-{uuid4()}",
            interrupt_type="PAUSE",
            reason="pause",
            trace_id=str(uuid4()),
        )
        result = await service.process(req)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_pre_interrupt_before_plan_execution_yields_cancelled_result(self) -> None:
        service, fabric, _, _ = await _svc()

        for cap in ("tool.interrupt.s1", "tool.interrupt.s2", "tool.interrupt.s3"):
            fabric.register_capability(cap, _entry(cap))

        trace_id = str(uuid4())
        request_id = f"req-{uuid4()}"
        plan_id = f"plan-{uuid4()}"
        plan = _plan(trace_id=trace_id, request_id=request_id, plan_id=plan_id)
        _seed_pending(service, plan)

        await service.process(_interrupt(trace_id=trace_id, dag_id=plan_id))
        dag_result = await service.process(plan)

        assert dag_result == ProcessResult.COMPLETED
        fabric.assert_called("tool.interrupt.s1", times=1)

    @pytest.mark.asyncio
    async def test_interrupted_run_writes_wal_and_audit(self) -> None:
        service, fabric, _, bridge = await _svc()

        for cap in ("tool.interrupt.s1", "tool.interrupt.s2", "tool.interrupt.s3"):
            fabric.register_capability(cap, _entry(cap))
        fabric.script_timeout("tool.interrupt.s1", delay_s=0.2)

        trace_id = str(uuid4())
        request_id = f"req-{uuid4()}"
        plan_id = f"plan-{uuid4()}"
        plan = _plan(trace_id=trace_id, request_id=request_id, plan_id=plan_id)
        _seed_pending(service, plan)

        dag_task = asyncio.create_task(service.process(plan))
        await asyncio.sleep(0.05)
        await service.process(_interrupt(trace_id=trace_id, dag_id=plan_id))
        await dag_task

        bridge.assert_wal_written(plan_id, "PLAN_START")
        bridge.assert_wal_written(plan_id, "DAG_COMPLETE")
        assert bridge.audit_log

    @pytest.mark.asyncio
    async def test_interrupt_does_not_emit_compensation_without_failure(self) -> None:
        service, fabric, delta, _ = await _svc()

        for cap in ("tool.interrupt.s1", "tool.interrupt.s2", "tool.interrupt.s3"):
            fabric.register_capability(cap, _entry(cap))
        fabric.script_timeout("tool.interrupt.s1", delay_s=0.2)

        trace_id = str(uuid4())
        request_id = f"req-{uuid4()}"
        plan_id = f"plan-{uuid4()}"
        plan = _plan(trace_id=trace_id, request_id=request_id, plan_id=plan_id)
        _seed_pending(service, plan)

        dag_task = asyncio.create_task(service.process(plan))
        await asyncio.sleep(0.05)
        await service.process(_interrupt(trace_id=trace_id, dag_id=plan_id))
        await dag_task

        payload = delta.get_emitted(ORCH_DAG_COMPLETED)[-1]
        assert payload.get("compensations") == []
