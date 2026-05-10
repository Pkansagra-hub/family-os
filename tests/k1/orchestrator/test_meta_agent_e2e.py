"""Epic 7.3A.1 -- Meta-Agent DAG end-to-end integration tests.

These tests exercise advanced two-step meta-agent DAG execution through
OrchestratorService.process() only (no direct DAGExecutor/StepRunner calls).

Flow under test:
  HIGH TaskEnvelope -> plan request deferred -> PLAN_READY event ->
  DAG execution with dynamic capability resolution + schema guards + saga.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_DAG_STARTED, ORCH_PLAN_REQUESTED
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import CommittedPlan, PlanStep, ProcessResult, RegistryEntry, TaskEnvelope


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


def _high_envelope(*, trace_id: str | None = None, session_id: str = "s-meta-e2e") -> TaskEnvelope:
    return TaskEnvelope(
        intent="meta-agent-e2e",
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
    raise AssertionError("Timed out waiting for async condition")


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


def _load_meta_plan(*, request_id: str, trace_id: str, plan_id: str | None = None) -> CommittedPlan:
    fixture_path = Path(__file__).parent / "fixtures" / "committed_plan_meta_agent.json"
    with open(fixture_path, encoding="utf-8") as f:
        payload = json.load(f)

    plan = CommittedPlan.from_dict(payload)

    # Normalize fixture to current runtime contract used in this suite:
    # - dynamic capability ref should point to build_agent step id
    # - explicit schema requirements for ORCH-15 verification
    build_step = replace(
        plan.steps[0],
        output_schema={
            "type": "object",
            "required": ["agent_id"],
            "properties": {
                "agent_id": {"type": "string"},
                "capabilities": {"type": "array", "items": {"type": "string"}},
            },
        },
    )
    execute_step = replace(
        plan.steps[1],
        capability="$build_agent.result.agent_id",
        deps=["build_agent"],
        params={
            "task": "analyze_dataset",
            "dataset_path": "/data/input.csv",
            "agent_name": "$build_agent.result.agent_id",
        },
        output_schema={
            "type": "object",
            "required": ["analysis", "insights"],
            "properties": {
                "analysis": {"type": "object"},
                "insights": {"type": "array", "items": {"type": "string"}},
            },
        },
    )

    return replace(
        plan,
        plan_id=plan_id or f"meta-plan-{uuid4()}",
        request_id=request_id,
        trace_id=trace_id,
        steps=[build_step, execute_step],
        dependencies={"execute_agent": ["build_agent"]},
    )


def _emit_plan_ready(event, *, plan: CommittedPlan) -> None:
    event.fire(
        "k1.planner.plan.ready.v1",
        {
            "plan_id": plan.plan_id,
            "request_id": plan.request_id,
            "intent": plan.intent,
            "steps": plan.steps,
            "trace_id": plan.trace_id,
            "dependencies": plan.dependencies,
        },
    )


class TestMetaAgentE2E:
    @pytest.mark.asyncio
    async def test_meta_agent_two_step_success_via_process(self) -> None:
        service, fabric, planner, delta, event, _ = await _init_service()
        try:
            _register_capability(
                fabric,
                "agent.builder.create",
                "$build_agent.result.agent_id",
                "agent.execute.diabetes",
                "agent.builder.destroy",
            )
            fabric.script_result(
                "agent.builder.create",
                CapabilityResult.success_result(
                    request_id="r-build",
                    data={"agent_id": "agent.execute.diabetes", "capabilities": ["analysis"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )
            fabric.script_result(
                "agent.execute.diabetes",
                CapabilityResult.success_result(
                    request_id="r-exec",
                    data={"analysis": {"risk": "low"}, "insights": ["ok"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )

            trace_id = str(uuid4())
            result = await service.process(_high_envelope(trace_id=trace_id))
            assert result == ProcessResult.DEFERRED

            request_id = planner.request_log[-1].request_id
            plan = _load_meta_plan(request_id=request_id, trace_id=trace_id)

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(event, plan=plan)

            completed = await _wait_for_next_dag_complete(delta, baseline=baseline)
            assert completed["success"] is True
            assert completed["completed"] == 2
            assert [c.capability_name for c in fabric.call_log][:2] == [
                "agent.builder.create",
                "agent.execute.diabetes",
            ]
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_dynamic_capability_resolution_uses_merged_results(self) -> None:
        service, fabric, planner, delta, event, _ = await _init_service()
        try:
            _register_capability(
                fabric,
                "agent.builder.create",
                "$build_agent.result.agent_id",
                "agent.execute.diabetes",
                "agent.builder.destroy",
            )
            fabric.script_result(
                "agent.builder.create",
                CapabilityResult.success_result(
                    request_id="r-build",
                    data={"agent_id": "agent.execute.diabetes", "capabilities": ["analysis"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )

            captured: list[CapabilityRequest] = []

            async def _exec(req: CapabilityRequest) -> CapabilityResult:
                fabric.call_log.append(req)
                captured.append(req)
                if req.capability_name == "agent.builder.create":
                    return CapabilityResult.success_result(
                        request_id=req.request_id,
                        data={"agent_id": "agent.execute.diabetes", "capabilities": ["analysis"]},
                        provider_id="mock",
                        trace_id=req.trace_id,
                    )
                if req.capability_name == "agent.execute.diabetes":
                    return CapabilityResult.success_result(
                        request_id=req.request_id,
                        data={"analysis": {"risk": "low"}, "insights": ["ok"]},
                        provider_id="mock",
                        trace_id=req.trace_id,
                    )
                return CapabilityResult.success_result(
                    request_id=req.request_id,
                    data={},
                    provider_id="mock",
                    trace_id=req.trace_id,
                )

            fabric.execute = _exec  # type: ignore[assignment]

            trace_id = str(uuid4())
            assert await service.process(_high_envelope(trace_id=trace_id)) == ProcessResult.DEFERRED

            request_id = planner.request_log[-1].request_id
            plan = _load_meta_plan(request_id=request_id, trace_id=trace_id)

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(event, plan=plan)
            done = await _wait_for_next_dag_complete(delta, baseline=baseline)

            assert done["success"] is True
            assert any(c.capability_name == "agent.execute.diabetes" for c in captured)
            assert not any(c.capability_name == "$build_agent.result.agent_id" for c in captured)
            execute_req = [c for c in captured if c.capability_name == "agent.execute.diabetes"][0]
            assert execute_req.params["agent_name"] == "agent.execute.diabetes"
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_output_schema_guard_retries_for_both_steps(self) -> None:
        service, fabric, planner, delta, event, _ = await _init_service()
        try:
            _register_capability(
                fabric,
                "agent.builder.create",
                "$build_agent.result.agent_id",
                "agent.execute.diabetes",
                "agent.builder.destroy",
            )

            state = {"build": 0, "exec": 0}
            captured: list[CapabilityRequest] = []

            async def _exec(req: CapabilityRequest) -> CapabilityResult:
                fabric.call_log.append(req)
                captured.append(req)

                if req.capability_name == "agent.builder.create":
                    state["build"] += 1
                    if state["build"] == 1:
                        return CapabilityResult.success_result(
                            request_id=req.request_id,
                            data={"wrong": True},
                            provider_id="mock",
                            trace_id=req.trace_id,
                        )
                    return CapabilityResult.success_result(
                        request_id=req.request_id,
                        data={"agent_id": "agent.execute.diabetes", "capabilities": ["analysis"]},
                        provider_id="mock",
                        trace_id=req.trace_id,
                    )

                if req.capability_name == "agent.execute.diabetes":
                    state["exec"] += 1
                    if state["exec"] == 1:
                        return CapabilityResult.success_result(
                            request_id=req.request_id,
                            data={"analysis": {"risk": "low"}},  # missing insights
                            provider_id="mock",
                            trace_id=req.trace_id,
                        )
                    return CapabilityResult.success_result(
                        request_id=req.request_id,
                        data={"analysis": {"risk": "low"}, "insights": ["ok"]},
                        provider_id="mock",
                        trace_id=req.trace_id,
                    )

                return CapabilityResult.success_result(
                    request_id=req.request_id,
                    data={},
                    provider_id="mock",
                    trace_id=req.trace_id,
                )

            fabric.execute = _exec  # type: ignore[assignment]

            trace_id = str(uuid4())
            assert await service.process(_high_envelope(trace_id=trace_id)) == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            plan = _load_meta_plan(request_id=request_id, trace_id=trace_id)

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(event, plan=plan)
            done = await _wait_for_next_dag_complete(delta, baseline=baseline)

            assert done["success"] is True
            assert state["build"] == 2
            assert state["exec"] == 2
            schema_hints = [c.params.get("__schema_hint") for c in captured if c.params.get("__schema_hint")]
            assert len(schema_hints) >= 2
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_build_agent_failure_returns_failed_and_no_compensation(self) -> None:
        service, fabric, planner, delta, event, bridge = await _init_service()
        try:
            _register_capability(
                fabric,
                "agent.builder.create",
                "$build_agent.result.agent_id",
                "agent.execute.diabetes",
                "agent.builder.destroy",
            )
            fabric.script_result(
                "agent.builder.create",
                CapabilityResult.failure_result(
                    request_id="r-build-fail",
                    error_code="BUILD_FAILED",
                    error_message="build failed",
                    retriable=False,
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )

            trace_id = str(uuid4())
            assert await service.process(_high_envelope(trace_id=trace_id)) == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            plan = _load_meta_plan(request_id=request_id, trace_id=trace_id)

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(event, plan=plan)
            completed = await _wait_for_next_dag_complete(delta, baseline=baseline)

            assert completed["success"] is False
            assert completed["failed"] >= 1
            fabric.assert_called("agent.builder.create", times=1)
            fabric.assert_not_called("agent.execute.diabetes")
            fabric.assert_not_called("agent.builder.destroy")
            assert bridge.get_wal(plan.plan_id)
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_execute_failure_triggers_saga_compensation(self) -> None:
        service, fabric, planner, delta, event, bridge = await _init_service()
        try:
            _register_capability(
                fabric,
                "agent.builder.create",
                "$build_agent.result.agent_id",
                "agent.execute.diabetes",
                "agent.builder.destroy",
            )
            fabric.script_result(
                "agent.builder.create",
                CapabilityResult.success_result(
                    request_id="r-build",
                    data={"agent_id": "agent.execute.diabetes", "capabilities": ["analysis"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )
            fabric.script_result(
                "agent.execute.diabetes",
                CapabilityResult.failure_result(
                    request_id="r-exec-fail",
                    error_code="EXEC_FAILED",
                    error_message="execution failed",
                    retriable=False,
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )

            trace_id = str(uuid4())
            assert await service.process(_high_envelope(trace_id=trace_id)) == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            plan = _load_meta_plan(request_id=request_id, trace_id=trace_id)

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(event, plan=plan)
            completed = await _wait_for_next_dag_complete(delta, baseline=baseline)

            assert completed["success"] is False
            # build -> execute -> compensation
            assert [c.capability_name for c in fabric.call_log][:3] == [
                "agent.builder.create",
                "agent.execute.diabetes",
                "agent.builder.destroy",
            ]
            wal = bridge.get_wal(plan.plan_id)
            # M5.2.3: COMPENSATION split into STARTED + COMPLETE phases.
            assert any(e["entry_type"] == "COMPENSATION_COMPLETE" for e in wal)
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_events_include_dag_and_step_completed(self) -> None:
        service, fabric, planner, delta, event, _ = await _init_service()
        try:
            _register_capability(
                fabric,
                "agent.builder.create",
                "$build_agent.result.agent_id",
                "agent.execute.diabetes",
                "agent.builder.destroy",
            )
            fabric.script_result(
                "agent.builder.create",
                CapabilityResult.success_result(
                    request_id="r-build",
                    data={"agent_id": "agent.execute.diabetes", "capabilities": ["analysis"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )
            fabric.script_result(
                "agent.execute.diabetes",
                CapabilityResult.success_result(
                    request_id="r-exec",
                    data={"analysis": {"risk": "low"}, "insights": ["ok"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )

            trace_id = str(uuid4())
            assert await service.process(_high_envelope(trace_id=trace_id)) == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            plan = _load_meta_plan(request_id=request_id, trace_id=trace_id)

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(event, plan=plan)
            await _wait_for_next_dag_complete(delta, baseline=baseline)

            topics = [topic for topic, _, _ in delta.emitted]
            assert ORCH_DAG_STARTED in topics
            assert "k1.orchestration.step.completed.v1" in topics
            assert ORCH_DAG_COMPLETED in topics

            step_payloads = [p for t, p, _ in delta.emitted if t == "k1.orchestration.step.completed.v1"]
            step_ids = {p.get("step_id") for p in step_payloads}
            assert "build_agent" in step_ids
            assert "execute_agent" in step_ids
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_orch03_topological_order_build_before_execute(self) -> None:
        service, fabric, planner, delta, event, _ = await _init_service()
        try:
            _register_capability(
                fabric,
                "agent.builder.create",
                "$build_agent.result.agent_id",
                "agent.execute.diabetes",
                "agent.builder.destroy",
            )
            fabric.script_result(
                "agent.builder.create",
                CapabilityResult.success_result(
                    request_id="r-build",
                    data={"agent_id": "agent.execute.diabetes", "capabilities": ["analysis"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )
            fabric.script_result(
                "agent.execute.diabetes",
                CapabilityResult.success_result(
                    request_id="r-exec",
                    data={"analysis": {"risk": "low"}, "insights": ["ok"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )

            trace_id = str(uuid4())
            assert await service.process(_high_envelope(trace_id=trace_id)) == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            plan = _load_meta_plan(request_id=request_id, trace_id=trace_id)

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(event, plan=plan)
            done = await _wait_for_next_dag_complete(delta, baseline=baseline)

            assert done["success"] is True
            call_names = [c.capability_name for c in fabric.call_log]
            assert call_names.index("agent.builder.create") < call_names.index("agent.execute.diabetes")
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_plan_requested_event_emitted_in_phase1(self) -> None:
        service, _, _, delta, _, _ = await _init_service()
        try:
            trace_id = str(uuid4())
            result = await service.process(_high_envelope(trace_id=trace_id))
            assert result == ProcessResult.DEFERRED

            delta.assert_emitted(ORCH_PLAN_REQUESTED, count=1)
            payload = delta.get_emitted(ORCH_PLAN_REQUESTED)[0]
            assert payload["trace_id"] == trace_id
            assert payload["tier"] == "HIGH"
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_trace_id_propagates_on_meta_agent_events(self) -> None:
        service, fabric, planner, delta, event, _ = await _init_service()
        try:
            _register_capability(
                fabric,
                "agent.builder.create",
                "$build_agent.result.agent_id",
                "agent.execute.diabetes",
                "agent.builder.destroy",
            )
            fabric.script_result(
                "agent.builder.create",
                CapabilityResult.success_result(
                    request_id="r-build",
                    data={"agent_id": "agent.execute.diabetes", "capabilities": ["analysis"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )
            fabric.script_result(
                "agent.execute.diabetes",
                CapabilityResult.success_result(
                    request_id="r-exec",
                    data={"analysis": {"risk": "low"}, "insights": ["ok"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )

            trace_id = str(uuid4())
            assert await service.process(_high_envelope(trace_id=trace_id)) == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            plan = _load_meta_plan(request_id=request_id, trace_id=trace_id)

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(event, plan=plan)
            await _wait_for_next_dag_complete(delta, baseline=baseline)

            for topic, payload, emitted_trace_id in delta.emitted:
                if topic in {
                    ORCH_PLAN_REQUESTED,
                    ORCH_DAG_STARTED,
                    ORCH_DAG_COMPLETED,
                    "k1.orchestration.step.completed.v1",
                }:
                    assert emitted_trace_id == trace_id
                    if isinstance(payload, dict) and "trace_id" in payload:
                        assert payload["trace_id"] == trace_id
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_audit_and_wal_written_for_meta_agent_execution(self) -> None:
        service, fabric, planner, delta, event, bridge = await _init_service()
        try:
            _register_capability(
                fabric,
                "agent.builder.create",
                "$build_agent.result.agent_id",
                "agent.execute.diabetes",
                "agent.builder.destroy",
            )
            fabric.script_result(
                "agent.builder.create",
                CapabilityResult.success_result(
                    request_id="r-build",
                    data={"agent_id": "agent.execute.diabetes", "capabilities": ["analysis"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )
            fabric.script_result(
                "agent.execute.diabetes",
                CapabilityResult.success_result(
                    request_id="r-exec",
                    data={"analysis": {"risk": "low"}, "insights": ["ok"]},
                    provider_id="mock",
                    trace_id="trace-meta",
                ),
            )

            trace_id = str(uuid4())
            assert await service.process(_high_envelope(trace_id=trace_id)) == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            plan = _load_meta_plan(request_id=request_id, trace_id=trace_id)

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            _emit_plan_ready(event, plan=plan)
            await _wait_for_next_dag_complete(delta, baseline=baseline)

            wal = bridge.get_wal(plan.plan_id)
            assert wal is not None
            assert wal[0]["entry_type"] == "PLAN_START"
            assert wal[-1]["entry_type"] == "DAG_COMPLETE"
            assert bridge.audit_log
        finally:
            await service.shutdown()
