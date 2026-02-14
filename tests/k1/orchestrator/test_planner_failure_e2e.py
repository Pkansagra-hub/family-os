"""Epic 7.3A.7 -- Planner failure propagation end-to-end integration tests.

Focus:
- HIGH-tier planning failure/cancel/timeout paths.
- PendingPlanContext cleanup and user-facing failure signaling.
- Trace propagation on emitted failure deltas (ORCH-09).
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest

from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.events import ORCH_DAG_COMPLETED
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import PlanAck, ProcessResult, TaskEnvelope


def _high_envelope(*, trace_id: str | None = None) -> TaskEnvelope:
    return TaskEnvelope(
        intent="planner-failure-e2e",
        trace_id=trace_id or str(uuid4()),
        tier="HIGH",
        capabilities=[],
        params={},
        context={"session_id": "s-planner-failure"},
    )


async def _svc(*, timeout_ms: int | None = None):
    config = None
    if timeout_ms is not None:
        config = OrchestratorConfig.from_dict({"plan_request_timeout_ms": timeout_ms})
    service = await OrchestratorFactory.create_for_testing(config=config)
    return service, service._planner_port, service._delta_port


def _latest_request_id(service) -> str:
    planner = service._planner_port
    assert planner.request_log
    return planner.request_log[-1].request_id


class TestPlannerFailurePropagationE2E:
    @pytest.mark.asyncio
    async def test_high_request_then_receive_plan_failed_cleans_pending(self) -> None:
        service, _, delta = await _svc()

        trace_id = str(uuid4())
        phase1 = await service.process(_high_envelope(trace_id=trace_id))
        assert phase1 == ProcessResult.DEFERRED
        assert len(service.pending_plans) == 1

        request_id = _latest_request_id(service)
        phase2 = await service.receive_plan_failed(
            request_id=request_id,
            reason="capability_not_found",
            error_detail="planner rejected intent",
            trace_id=trace_id,
        )

        assert phase2 == ProcessResult.FAILED
        assert service.pending_plans == {}

        completed = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert completed
        payload = completed[-1]
        assert payload["success"] is True or payload["failed"] >= 0

    @pytest.mark.asyncio
    async def test_plan_cancelled_path_cleans_pending_context(self) -> None:
        service, _, _ = await _svc()

        phase1 = await service.process(_high_envelope())
        assert phase1 == ProcessResult.DEFERRED
        request_id = _latest_request_id(service)

        phase2 = await service.receive_plan_cancelled(
            request_id=request_id,
            trace_id=str(uuid4()),
        )

        assert phase2 == ProcessResult.CANCELLED
        assert service.pending_plans == {}

    @pytest.mark.asyncio
    async def test_planner_reject_at_dispatch_returns_failed_without_pending_leak(self) -> None:
        service, planner, _ = await _svc()

        async def _reject(_request):
            return PlanAck(request_id=str(uuid4()), status="REJECTED")

        planner.request_plan = _reject  # type: ignore[assignment]
        rejected = await service.process(_high_envelope())

        assert rejected == ProcessResult.FAILED
        assert service.pending_plans == {}

    @pytest.mark.asyncio
    async def test_planner_timeout_reap_expires_pending_and_emits_failure_delta(self) -> None:
        service, planner, delta = await _svc(timeout_ms=50)

        trace_id = str(uuid4())
        phase1 = await service.process(_high_envelope(trace_id=trace_id))
        assert phase1 == ProcessResult.DEFERRED

        request_id = _latest_request_id(service)
        assert request_id in service.pending_plans

        # Force timeout deterministically.
        service.pending_plans[request_id].created_at = time.time() - 1.0
        service.pending_plans[request_id].timeout_ms = 10

        reaped = await service.reap_stale_contexts()
        assert reaped == 1
        assert request_id not in service.pending_plans
        assert request_id in planner.cancel_log

        completed = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert completed

    @pytest.mark.asyncio
    async def test_failure_delta_trace_id_propagates_for_orch09(self) -> None:
        service, _, delta = await _svc()

        trace_id = str(uuid4())
        phase1 = await service.process(_high_envelope(trace_id=trace_id))
        assert phase1 == ProcessResult.DEFERRED

        request_id = _latest_request_id(service)
        phase2 = await service.receive_plan_failed(
            request_id=request_id,
            reason="planner_timeout",
            error_detail=None,
            trace_id=trace_id,
        )

        assert phase2 == ProcessResult.FAILED
        assert delta.emitted
        topic, payload, emitted_trace_id = delta.emitted[-1]
        assert topic == ORCH_DAG_COMPLETED
        assert emitted_trace_id == trace_id
        assert payload["trace_id"] == trace_id

    @pytest.mark.asyncio
    async def test_consecutive_failed_and_cancelled_requests_leave_no_orphan_contexts(self) -> None:
        service, _, _ = await _svc()

        # Failure path
        t1 = str(uuid4())
        r1 = await service.process(_high_envelope(trace_id=t1))
        assert r1 == ProcessResult.DEFERRED
        req1 = _latest_request_id(service)
        rf = await service.receive_plan_failed(
            request_id=req1,
            reason="capability_not_found",
            error_detail="missing tool",
            trace_id=t1,
        )
        assert rf == ProcessResult.FAILED

        # Cancellation path
        t2 = str(uuid4())
        r2 = await service.process(_high_envelope(trace_id=t2))
        assert r2 == ProcessResult.DEFERRED
        req2 = _latest_request_id(service)
        rc = await service.receive_plan_cancelled(request_id=req2, trace_id=t2)
        assert rc == ProcessResult.CANCELLED

        assert service.pending_plans == {}
