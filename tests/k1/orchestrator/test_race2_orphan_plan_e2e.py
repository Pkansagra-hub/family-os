"""Epic 7.3A.8 -- RACE-2 orphan plan end-to-end integration tests.

Reference: Schema Whiteboard §10.10 (late CommittedPlan after pending context expiry).

Process-path focus:
- dispatch_high() stores PendingPlanContext
- timeout reaper expires context
- late CommittedPlan routes to orphan handling (FAILED)
- WAL recovery is attempted when entries exist
- orphan path does not execute DAG nor pollute executed_plans dedup
- orphan path emits diagnostic delta with orphan reason
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest

from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_DELTA_V1
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import CommittedPlan, PlanStep, ProcessResult, TaskEnvelope


async def _svc():
    service = await OrchestratorFactory.create_standalone()
    return (
        service,
        service._planner_port,
        service._delta_port,
        service._bridge_port,
        service._fabric_port,
    )


def _high_envelope(*, trace_id: str | None = None) -> TaskEnvelope:
    return TaskEnvelope(
        intent="race2-orphan-e2e",
        trace_id=trace_id or str(uuid4()),
        tier="HIGH",
        capabilities=[],
        params={},
        context={"session_id": "s-race2"},
    )


def _late_plan(*, request_id: str, trace_id: str, plan_id: str | None = None) -> CommittedPlan:
    return CommittedPlan(
        plan_id=plan_id or f"plan-{uuid4()}",
        request_id=request_id,
        intent="race2-orphan-e2e",
        steps=[PlanStep(id="s1", capability="tool.race2.orphan")],
        dependencies={},
        trace_id=trace_id,
    )


class TestRace2OrphanPlanE2E:
    @pytest.mark.asyncio
    async def test_dispatch_high_creates_pending_context(self) -> None:
        service, planner, _, _, _ = await _svc()

        trace_id = str(uuid4())
        phase1 = await service.process(_high_envelope(trace_id=trace_id))

        assert phase1 == ProcessResult.DEFERRED
        assert len(service.pending_plans) == 1
        assert planner.request_log
        req_id = planner.request_log[-1].request_id
        assert req_id in service.pending_plans

    @pytest.mark.asyncio
    async def test_reaper_expires_pending_before_late_plan_arrival(self) -> None:
        service, planner, delta, _, _ = await _svc()

        trace_id = str(uuid4())
        await service.process(_high_envelope(trace_id=trace_id))
        req_id = planner.request_log[-1].request_id

        # Deterministically age out context (clock-less timeout simulation).
        service.pending_plans[req_id].created_at = time.time() - 1.0
        service.pending_plans[req_id].timeout_ms = 10

        reaped = await service.reap_stale_contexts()

        assert reaped == 1
        assert req_id not in service.pending_plans
        assert req_id in planner.cancel_log
        assert len(delta.get_emitted(ORCH_DAG_COMPLETED)) >= 1

    @pytest.mark.asyncio
    async def test_late_committed_plan_without_pending_context_returns_failed(self) -> None:
        service, planner, _, _, _ = await _svc()

        trace_id = str(uuid4())
        await service.process(_high_envelope(trace_id=trace_id))
        req_id = planner.request_log[-1].request_id
        service.pending_plans.pop(req_id, None)

        result = await service.process(_late_plan(request_id=req_id, trace_id=trace_id))

        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_orphan_plan_attempts_wal_recovery_when_wal_exists(self) -> None:
        service, planner, delta, bridge, _ = await _svc()

        trace_id = str(uuid4())
        await service.process(_high_envelope(trace_id=trace_id))
        req_id = planner.request_log[-1].request_id

        plan = _late_plan(request_id=req_id, trace_id=trace_id)
        service.pending_plans.pop(req_id, None)

        bridge.inject_wal(
            plan.plan_id,
            [
                {
                    "entry_type": "PLAN_START",
                    "payload": {"note": "simulated prior write"},
                    "trace_id": trace_id,
                }
            ],
        )

        result = await service.process(plan)

        assert result == ProcessResult.FAILED
        # Orphan path should not emit DAG completion for late plan.
        assert delta.get_emitted(ORCH_DAG_COMPLETED) == []

    @pytest.mark.asyncio
    async def test_orphan_plan_does_not_execute_dag_steps(self) -> None:
        service, planner, _, _, fabric = await _svc()

        trace_id = str(uuid4())
        await service.process(_high_envelope(trace_id=trace_id))
        req_id = planner.request_log[-1].request_id

        plan = _late_plan(request_id=req_id, trace_id=trace_id)
        service.pending_plans.pop(req_id, None)

        before_calls = len(fabric.call_log)
        result = await service.process(plan)

        assert result == ProcessResult.FAILED
        assert len(fabric.call_log) == before_calls

    @pytest.mark.asyncio
    async def test_orphan_plan_not_recorded_in_executed_plans_dedup(self) -> None:
        service, planner, _, _, _ = await _svc()

        trace_id = str(uuid4())
        await service.process(_high_envelope(trace_id=trace_id))
        req_id = planner.request_log[-1].request_id

        plan = _late_plan(request_id=req_id, trace_id=trace_id, plan_id=f"plan-{uuid4()}")
        service.pending_plans.pop(req_id, None)

        result = await service.process(plan)

        assert result == ProcessResult.FAILED
        assert plan.plan_id not in service.executed_plans

    @pytest.mark.asyncio
    async def test_orphan_plan_emits_error_delta_with_reason(self) -> None:
        service, planner, delta, _, _ = await _svc()

        trace_id = str(uuid4())
        await service.process(_high_envelope(trace_id=trace_id))
        req_id = planner.request_log[-1].request_id

        plan = _late_plan(request_id=req_id, trace_id=trace_id)
        service.pending_plans.pop(req_id, None)

        result = await service.process(plan)

        assert result == ProcessResult.FAILED
        orphan_deltas = [
            payload
            for topic, payload, emitted_trace in delta.emitted
            if topic == ORCH_DELTA_V1
            and emitted_trace == trace_id
            and payload.get("reason") == "orphan_plan_no_context"
            and payload.get("plan_id") == plan.plan_id
            and payload.get("request_id") == plan.request_id
        ]
        assert orphan_deltas

    @pytest.mark.asyncio
    async def test_orphan_plan_through_mailbox_process_one_emits_processing_error_delta(
        self,
    ) -> None:
        service, planner, delta, _, _ = await _svc()

        trace_id = str(uuid4())
        await service.process(_high_envelope(trace_id=trace_id))
        req_id = planner.request_log[-1].request_id

        plan = _late_plan(request_id=req_id, trace_id=trace_id)
        service.pending_plans.pop(req_id, None)

        await service._process_one(plan)

        assert any(
            topic == ORCH_DELTA_V1
            and payload.get("type") == "processing_error"
            and payload.get("reason") == "orphan_plan_no_context"
            and emitted_trace == trace_id
            for topic, payload, emitted_trace in delta.emitted
        )
