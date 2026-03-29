"""Epic 7.4.5 -- request_id echo contract tests.

Validates the Planner-Orchestrator protocol invariant:
PlanRequest.request_id MUST be echoed unchanged in CommittedPlan.request_id
for PendingPlanContext correlation.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID, uuid4

import jsonschema
import pytest

from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_DELTA_V1, PLAN_READY
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    CommittedPlan,
    PlanStep,
    ProcessResult,
    RegistryEntry,
    TaskEnvelope,
)


def _high_envelope(
    *, trace_id: str | None = None, session_id: str = "s-request-echo"
) -> TaskEnvelope:
    return TaskEnvelope(
        intent="request-id-echo",
        trace_id=trace_id or str(uuid4()),
        tier="HIGH",
        capabilities=[],
        params={},
        context={"session_id": session_id},
    )


def _register_capability(fabric, capability_name: str) -> None:
    fabric.register_capability(
        capability_name,
        RegistryEntry(
            name=capability_name,
            provider_type="mock",
            safety_band_min="GREEN",
            availability="AVAILABLE",
            estimated_duration_ms=50,
        ),
    )


async def _wait_until(predicate, *, timeout_s: float = 2.0, step_s: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(step_s)
    raise AssertionError("Timed out waiting for asynchronous condition")


def _plan(
    *, request_id: str, trace_id: str, plan_id: str | None = None, cap: str = "tool.echo"
) -> CommittedPlan:
    return CommittedPlan(
        plan_id=plan_id or f"plan-{uuid4()}",
        request_id=request_id,
        intent="request-id-echo",
        steps=[PlanStep(id="s1", capability=cap)],
        dependencies={},
        trace_id=trace_id,
    )


class TestRequestIdEchoContract:
    @pytest.mark.asyncio
    async def test_echo_match_correlates_pending_context_and_executes(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        await service.init()
        try:
            fabric = service._fabric_port
            planner = service._planner_port
            delta = service._delta_port
            event = service._event_port

            _register_capability(fabric, "tool.echo")
            trace_id = str(uuid4())

            phase1 = await service.process(_high_envelope(trace_id=trace_id))
            assert phase1 == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id
            assert request_id in service.pending_plans

            baseline = len(delta.get_emitted(ORCH_DAG_COMPLETED))
            ready_plan = _plan(request_id=request_id, trace_id=trace_id)
            event.fire(
                PLAN_READY,
                {
                    "plan_id": ready_plan.plan_id,
                    "request_id": ready_plan.request_id,
                    "intent": ready_plan.intent,
                    "steps": ready_plan.steps,
                    "trace_id": ready_plan.trace_id,
                    "dependencies": ready_plan.dependencies,
                },
            )

            await _wait_until(lambda: len(delta.get_emitted(ORCH_DAG_COMPLETED)) > baseline)
            assert request_id not in service.pending_plans
            assert delta.get_emitted(ORCH_DAG_COMPLETED)[-1]["success"] is True
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_mismatched_echo_triggers_orphan_failed_path(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        try:
            planner = service._planner_port
            delta = service._delta_port

            trace_id = str(uuid4())
            phase1 = await service.process(_high_envelope(trace_id=trace_id))
            assert phase1 == ProcessResult.DEFERRED
            original_request_id = planner.request_log[-1].request_id
            assert original_request_id in service.pending_plans

            mismatched_plan = _plan(request_id=str(uuid4()), trace_id=trace_id)
            phase2 = await service.process(mismatched_plan)

            assert phase2 == ProcessResult.FAILED
            assert original_request_id in service.pending_plans
            assert any(
                topic == ORCH_DELTA_V1 and payload.get("reason") == "orphan_plan_no_context"
                for topic, payload, _ in delta.emitted
            )
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_generated_request_id_is_uuid4(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        try:
            planner = service._planner_port

            result = await service.process(_high_envelope())
            assert result == ProcessResult.DEFERRED

            request_id = planner.request_log[-1].request_id
            parsed = UUID(request_id)
            assert parsed.version == 4
            assert str(parsed) == request_id
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_event_bus_round_trip_preserves_request_id_exactly(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        try:
            planner = service._planner_port
            event = service._event_port
            mailbox = service._mailbox

            # Subscribe handlers without starting background loops so mailbox
            # state is deterministic for this wire-format round-trip check.
            service._subscribe_events()

            trace_id = str(uuid4())
            phase1 = await service.process(_high_envelope(trace_id=trace_id))
            assert phase1 == ProcessResult.DEFERRED
            request_id = planner.request_log[-1].request_id

            payload = {
                "plan_id": f"plan-{uuid4()}",
                "request_id": request_id,
                "intent": "request-id-echo",
                "steps": [PlanStep(id="s1", capability="tool.echo")],
                "trace_id": trace_id,
                "dependencies": {},
            }
            event.fire(PLAN_READY, payload)

            queued = mailbox.dequeue()
            assert isinstance(queued, CommittedPlan)
            assert queued.request_id == request_id
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_multiple_requests_keep_isolated_request_id_correlations(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        try:
            fabric = service._fabric_port
            planner = service._planner_port

            _register_capability(fabric, "tool.echo.a")
            _register_capability(fabric, "tool.echo.b")

            trace_a = str(uuid4())
            trace_b = str(uuid4())

            assert (
                await service.process(_high_envelope(trace_id=trace_a, session_id="s-a"))
                == ProcessResult.DEFERRED
            )
            req_a = planner.request_log[-1].request_id

            assert (
                await service.process(_high_envelope(trace_id=trace_b, session_id="s-b"))
                == ProcessResult.DEFERRED
            )
            req_b = planner.request_log[-1].request_id
            assert req_a != req_b
            assert req_a in service.pending_plans and req_b in service.pending_plans

            plan_a = _plan(request_id=req_a, trace_id=trace_a, cap="tool.echo.a")
            phase_a = await service.process(plan_a)
            assert phase_a in {ProcessResult.COMPLETED, ProcessResult.DEGRADED}
            assert req_a not in service.pending_plans
            assert req_b in service.pending_plans

            plan_b = _plan(request_id=req_b, trace_id=trace_b, cap="tool.echo.b")
            phase_b = await service.process(plan_b)
            assert phase_b in {ProcessResult.COMPLETED, ProcessResult.DEGRADED}
            assert req_b not in service.pending_plans
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_plan_request_wire_format_validates_against_schema(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        try:
            planner = service._planner_port

            phase1 = await service.process(_high_envelope())
            assert phase1 == ProcessResult.DEFERRED
            plan_request = planner.request_log[-1]

            schema_path = (
                Path(__file__).resolve().parents[3]
                / "k1"
                / "contracts"
                / "schemas"
                / "orchestrator"
                / "plan_request.v1.json"
            )
            schema = json.loads(schema_path.read_text(encoding="utf-8"))

            wire_payload = {
                "request_id": plan_request.request_id,
                "intent": plan_request.intent,
                "trace_id": plan_request.trace_id,
                "constraints": plan_request.constraints,
                "timeout_ms": plan_request.timeout_ms,
            }

            jsonschema.validate(
                instance=wire_payload,
                schema=schema,
                format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
            )
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_plan_request_schema_rejects_non_uuid_request_id(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[3]
            / "k1"
            / "contracts"
            / "schemas"
            / "orchestrator"
            / "plan_request.v1.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        bad_payload = {
            "request_id": "not-a-uuid",
            "intent": "request-id-echo",
            "trace_id": str(uuid4()),
            "timeout_ms": 45000,
        }

        validator = jsonschema.Draft7Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        )
        errors = sorted(validator.iter_errors(bad_payload), key=lambda e: e.path)
        assert errors
        assert any(err.path and list(err.path)[0] == "request_id" for err in errors)
        errors = sorted(validator.iter_errors(bad_payload), key=lambda e: e.path)
        assert errors
        assert any(err.path and list(err.path)[0] == "request_id" for err in errors)
