"""Epic 7.3.2 -- HIGH tier end-to-end integration tests.

These tests validate the asynchronous two-phase HIGH-tier protocol:
  1) TaskEnvelope(HIGH) dispatched via OrchestratorService.process() -> DEFERRED
  2) Planner emits PLAN_READY; orchestrator receives via event subscription,
     enqueues to mailbox, and executes DAG in phase 2.

All assertions use factory-created service + real in-memory test adapters.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from k1.orchestrator.events import (
    ORCH_DAG_COMPLETED,
    ORCH_DAG_STARTED,
    ORCH_PLAN_REQUESTED,
    ORCH_TASK_ACCEPTED,
    PLAN_READY,
)
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    ConditionExpr,
    PlanStep,
    ProcessResult,
    RegistryEntry,
    TaskEnvelope,
)
from tests.k1.orchestrator.helpers import cap_result


def _assert_dag_completed_payload_shape(payload: dict) -> None:
    required = {
        "trace_id",
        "success",
        "completed",
        "failed",
        "cancelled",
        "skipped",
    }
    missing = sorted(required.difference(payload.keys()))
    assert not missing, f"Missing ORCH_DAG_COMPLETED payload keys: {missing}"


def _register_capability(fabric, *names: str) -> None:
    for name in names:
        fabric.register_capability(
            name,
            RegistryEntry(
                name=name,
                provider_type="mock",
                safety_band_min="GREEN",
                availability="AVAILABLE",
                estimated_duration_ms=100,
            ),
        )


def _high_envelope(*, trace_id: str | None = None, session_id: str = "s-high-e2e") -> TaskEnvelope:
    return TaskEnvelope(
        intent="high-e2e",
        trace_id=trace_id or str(uuid4()),
        tier="HIGH",
        capabilities=[],
        params={},
        context={"session_id": session_id},
    )


async def _wait_until(predicate, *, timeout_s: float = 2.0, step_s: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(step_s)
    raise AssertionError("Timed out waiting for asynchronous condition")


async def _wait_for_next_dag_complete(delta, *, baseline: int) -> dict:
    await _wait_until(lambda: len(delta.get_emitted(ORCH_DAG_COMPLETED)) > baseline)
    return delta.get_emitted(ORCH_DAG_COMPLETED)[-1]


async def _init_service():
    service = await OrchestratorFactory.create_standalone()
    await service.init()
    return (
        service,
        service._fabric_port,
        service._planner_port,
        service._delta_port,
        service._event_port,
        service._bridge_port,
    )


def _emit_plan_ready(
    event,
    *,
    plan_id: str,
    request_id: str,
    trace_id: str,
    steps: list[PlanStep],
    dependencies: dict[str, list[str]],
) -> None:
    event.fire(
        PLAN_READY,
        {
            "plan_id": plan_id,
            "request_id": request_id,
            "intent": "high-e2e",
            "steps": steps,
            "trace_id": trace_id,
            "dependencies": dependencies,
        },
    )


class TestHighTierE2E:
    @pytest.mark.asyncio
    async def test_phase1_dispatch_is_deferred_and_plan_requested_event_emitted(self) -> None:
        service, _, planner, delta, _, _ = await _init_service()
        try:
            trace_id = str(uuid4())
            result = await service.process(_high_envelope(trace_id=trace_id))

            assert result == ProcessResult.DEFERRED
            assert len(planner.request_log) == 1
            delta.assert_emitted(ORCH_TASK_ACCEPTED, count=1)
            delta.assert_emitted(ORCH_PLAN_REQUESTED, count=1)
            requested = delta.get_emitted(ORCH_PLAN_REQUESTED)[0]
            assert requested["trace_id"] == trace_id
            assert requested["request_id"] == planner.request_log[0].request_id
            assert requested["tier"] == "HIGH"
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_two_phase_linear_three_step_executes_and_emits_lifecycle(self) -> None:
        service, fabric, planner, delta, event, bridge = await _init_service()
        try:
            _register_capability(fabric, "tool.a", "tool.b", "tool.c")
            trace_id = str(uuid4())

            result = await service.process(_high_envelope(trace_id=trace_id))
            assert result == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id

            steps = [
                PlanStep(id="s1", capability="tool.a"),
                PlanStep(id="s2", capability="tool.b"),
                PlanStep(id="s3", capability="tool.c"),
            ]
            deps = {"s2": ["s1"], "s3": ["s2"]}
            plan_id = f"plan-{uuid4()}"
            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(
                event,
                plan_id=plan_id,
                request_id=request_id,
                trace_id=trace_id,
                steps=steps,
                dependencies=deps,
            )

            completed_payload = await _wait_for_next_dag_complete(delta, baseline=baseline)
            _assert_dag_completed_payload_shape(completed_payload)
            assert completed_payload["trace_id"] == trace_id
            assert completed_payload["success"] is True
            assert completed_payload["completed"] == 3
            assert completed_payload["failed"] == 0
            assert [call.capability_name for call in fabric.call_log] == [
                "tool.a",
                "tool.b",
                "tool.c",
            ]

            delta.assert_emitted(ORCH_DAG_STARTED, count=1)
            bridge.assert_wal_written(plan_id, "PLAN_START")
            bridge.assert_wal_written(plan_id, "DAG_COMPLETE")
            wal_types = [e["entry_type"] for e in bridge.get_wal(plan_id)]
            assert wal_types.count("WAVE_COMPLETE") == 3
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_two_phase_parallel_five_step_executes_in_waves(self) -> None:
        service, fabric, planner, delta, event, bridge = await _init_service()
        try:
            _register_capability(fabric, "tool.p1", "tool.p2", "tool.p3", "tool.p4", "tool.p5")
            result = await service.process(_high_envelope())
            assert result == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            trace_id = planner.request_log[-1].trace_id

            steps = [
                PlanStep(id="s1", capability="tool.p1"),
                PlanStep(id="s2", capability="tool.p2"),
                PlanStep(id="s3", capability="tool.p3"),
                PlanStep(id="s4", capability="tool.p4"),
                PlanStep(id="s5", capability="tool.p5"),
            ]
            deps = {"s4": ["s1", "s2", "s3"], "s5": ["s1", "s2", "s3"]}
            plan_id = f"plan-{uuid4()}"

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(
                event,
                plan_id=plan_id,
                request_id=request_id,
                trace_id=trace_id,
                steps=steps,
                dependencies=deps,
            )

            completed_payload = await _wait_for_next_dag_complete(delta, baseline=baseline)
            _assert_dag_completed_payload_shape(completed_payload)
            assert completed_payload["success"] is True
            assert completed_payload["failed"] == 0
            assert len(fabric.call_log) == 5

            wal_types = [e["entry_type"] for e in bridge.get_wal(plan_id)]
            assert wal_types.count("WAVE_COMPLETE") == 2
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_param_resolution_uses_prior_step_output(self) -> None:
        service, fabric, planner, delta, event, _ = await _init_service()
        try:
            _register_capability(fabric, "tool.source", "tool.consumer")
            fabric.script_result("tool.source", cap_result({"answer": 42}))

            result = await service.process(_high_envelope())
            assert result == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            trace_id = planner.request_log[-1].trace_id

            steps = [
                PlanStep(id="s1", capability="tool.source"),
                PlanStep(
                    id="s2",
                    capability="tool.consumer",
                    params={"value": "$s1.result.answer"},
                ),
            ]
            deps = {"s2": ["s1"]}

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(
                event,
                plan_id=f"plan-{uuid4()}",
                request_id=request_id,
                trace_id=trace_id,
                steps=steps,
                dependencies=deps,
            )

            await _wait_for_next_dag_complete(delta, baseline=baseline)
            call_by_cap = {c.capability_name: c for c in fabric.call_log}
            assert call_by_cap["tool.consumer"].params["value"] == 42
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_conditional_false_branch_skips_step(self) -> None:
        service, fabric, planner, delta, event, _ = await _init_service()
        try:
            _register_capability(fabric, "tool.cond.source", "tool.cond.child")
            fabric.script_result("tool.cond.source", cap_result({"run_child": False}))

            result = await service.process(_high_envelope())
            assert result == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            trace_id = planner.request_log[-1].trace_id

            steps = [
                PlanStep(id="s1", capability="tool.cond.source"),
                PlanStep(
                    id="s2",
                    capability="tool.cond.child",
                    condition=ConditionExpr(
                        type="EQ",
                        path="s1.result.data.run_child",
                        literal=True,
                    ),
                ),
            ]
            deps = {"s2": ["s1"]}

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(
                event,
                plan_id=f"plan-{uuid4()}",
                request_id=request_id,
                trace_id=trace_id,
                steps=steps,
                dependencies=deps,
            )

            payload = await _wait_for_next_dag_complete(delta, baseline=baseline)
            _assert_dag_completed_payload_shape(payload)
            fabric.assert_not_called("tool.cond.child")
            assert payload["cancelled"] == 1
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_failure_path_with_side_effect_step_returns_failed_and_persists_wal(self) -> None:
        service, fabric, planner, delta, event, bridge = await _init_service()
        try:
            _register_capability(fabric, "tool.fail", "tool.undo")
            fabric.script_result("tool.fail", cap_result(success=False))

            result = await service.process(_high_envelope())
            assert result == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            trace_id = planner.request_log[-1].trace_id
            plan_id = f"plan-{uuid4()}"

            steps = [
                PlanStep(
                    id="s1",
                    capability="tool.fail",
                    has_side_effects=True,
                    compensation="tool.undo",
                ),
            ]
            deps = {}

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(
                event,
                plan_id=plan_id,
                request_id=request_id,
                trace_id=trace_id,
                steps=steps,
                dependencies=deps,
            )

            payload = await _wait_for_next_dag_complete(delta, baseline=baseline)
            _assert_dag_completed_payload_shape(payload)
            assert payload["success"] is False
            assert payload["failed"] >= 1
            bridge.assert_wal_written(plan_id, "DAG_COMPLETE")
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_wal_markers_written_for_high_tier_run(self) -> None:
        service, fabric, planner, delta, event, bridge = await _init_service()
        try:
            _register_capability(fabric, "tool.w1", "tool.w2")
            result = await service.process(_high_envelope())
            assert result == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            trace_id = planner.request_log[-1].trace_id
            plan_id = f"plan-{uuid4()}"

            steps = [
                PlanStep(id="s1", capability="tool.w1"),
                PlanStep(id="s2", capability="tool.w2"),
            ]
            deps = {"s2": ["s1"]}
            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(
                event,
                plan_id=plan_id,
                request_id=request_id,
                trace_id=trace_id,
                steps=steps,
                dependencies=deps,
            )

            await _wait_for_next_dag_complete(delta, baseline=baseline)
            wal = bridge.get_wal(plan_id)
            assert wal[0]["entry_type"] == "PLAN_START"
            assert any(e["entry_type"] == "WAVE_COMPLETE" for e in wal)
            assert wal[-1]["entry_type"] == "DAG_COMPLETE"
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_concurrency_guard_activates_during_execution_and_releases(self) -> None:
        service, fabric, planner, delta, event, _ = await _init_service()
        try:
            _register_capability(fabric, "tool.slow")
            fabric.script_timeout("tool.slow", delay_s=0.2)

            result = await service.process(_high_envelope())
            assert result == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            trace_id = planner.request_log[-1].trace_id

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(
                event,
                plan_id=f"plan-{uuid4()}",
                request_id=request_id,
                trace_id=trace_id,
                steps=[PlanStep(id="s1", capability="tool.slow")],
                dependencies={},
            )

            await _wait_until(
                lambda: getattr(service._concurrency_guard, "active", False), timeout_s=1.0
            )
            await _wait_for_next_dag_complete(delta, baseline=baseline)
            await _wait_until(
                lambda: not getattr(service._concurrency_guard, "active", False),
                timeout_s=1.0,
            )
        finally:
            await service.shutdown()
            await _wait_until(
                lambda: not getattr(service._concurrency_guard, "active", False),
                timeout_s=1.0,
            )
