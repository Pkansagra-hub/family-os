"""StepRunner tests (Epic 7.1.3) using factory-backed real test adapters.

No fake adapter classes are used. Tests obtain StepRunner via
OrchestratorFactory.create_standalone() and script behavior through
MockFabricAdapter.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional
from uuid import uuid4

import pytest

from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.orchestration.step_runner import StepRunner
from k1.orchestrator.types import PlanStep, SchemaResult, StepStatus


async def _svc():
    service = await OrchestratorFactory.create_standalone()
    fabric: MockFabricAdapter = service._fabric_port  # type: ignore[assignment]
    runner: StepRunner = service._dag_executor._step_runner  # type: ignore[assignment]
    return service, runner, fabric


def _step(
    sid: str = "s1",
    capability: str = "cap.test",
    *,
    params: Optional[Dict[str, Any]] = None,
    timeout_ms: Optional[int] = None,
    prompt_template: Optional[str] = None,
    tools_granted: Optional[list[str]] = None,
    activity_profile: Optional[str] = None,
    output_schema: Optional[Dict[str, Any]] = None,
) -> PlanStep:
    return PlanStep(
        id=sid,
        capability=capability,
        params=params or {},
        timeout_ms=timeout_ms,
        prompt_template=prompt_template,
        tools_granted=tools_granted,
        activity_profile=activity_profile,
        output_schema=output_schema,
    )


def _ok(data: Optional[Dict[str, Any]] = None, *, trace_id: str = "trace-1") -> CapabilityResult:
    return CapabilityResult.success_result(
        request_id=f"r-{uuid4()}",
        data=data if data is not None else {"ok": True},
        provider_id="mock",
        trace_id=trace_id,
    )


def _fail(
    *,
    retriable: bool,
    message: str = "boom",
    code: str = "ERR",
    trace_id: str = "trace-1",
) -> CapabilityResult:
    return CapabilityResult.failure_result(
        request_id=f"r-{uuid4()}",
        error_code=code,
        error_message=message,
        retriable=retriable,
        provider_id="mock",
        trace_id=trace_id,
    )


class TestBasicExecution:
    @pytest.mark.asyncio
    async def test_agent_step_executes_successfully(self) -> None:
        _, runner, fabric = await _svc()
        step = _step("agent", "agent.summarize")

        result = await runner.run(step, {"text": "hello"}, {}, "trace-a")

        assert result.status == StepStatus.COMPLETED
        fabric.assert_called("agent.summarize", 1)

    @pytest.mark.asyncio
    async def test_tool_step_executes_successfully(self) -> None:
        _, runner, fabric = await _svc()
        step = _step("tool", "tool.calendar.search")

        result = await runner.run(step, {"q": "today"}, {}, "trace-t")

        assert result.status == StepStatus.COMPLETED
        fabric.assert_called("tool.calendar.search", 1)

    @pytest.mark.asyncio
    async def test_prompt_template_field_is_forwarded(self) -> None:
        _, runner, fabric = await _svc()
        step = _step("p1", "agent.writer", prompt_template="Write: {x}")

        await runner.run(step, {"x": "abc"}, {}, "trace-p")

        req = fabric.call_log[0]
        assert req.prompt_template == "Write: {x}"


class TestRequestShape:
    @pytest.mark.asyncio
    async def test_request_core_fields(self) -> None:
        _, runner, fabric = await _svc()
        step = _step("s7", "cap.s7")

        await runner.run(step, {"k": 1}, {}, "trace-42")

        req = fabric.call_log[0]
        assert req.capability_name == "cap.s7"
        assert req.params == {"k": 1}
        assert req.caller == "orchestrator"
        assert req.caller_id == "s7"
        assert req.plan_id == "s7"
        assert req.step_id == "s7"
        assert req.trace_id == "trace-42"
        assert req.tier == "HIGH"

    @pytest.mark.asyncio
    async def test_timeout_uses_step_override(self) -> None:
        _, runner, fabric = await _svc()
        step = _step("s1", "cap.s1", timeout_ms=4567)

        await runner.run(step, {}, {}, "trace-1")

        assert fabric.call_log[0].timeout_ms == 4567

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_policy_default(self) -> None:
        _, runner, fabric = await _svc()
        step = _step("s1", "cap.s1")

        await runner.run(step, {}, {}, "trace-1")

        assert fabric.call_log[0].timeout_ms == runner._policies.step_timeout_default_ms

    @pytest.mark.asyncio
    async def test_tools_granted_maps_to_context_override(self) -> None:
        _, runner, fabric = await _svc()
        step = _step("s1", "cap.s1", tools_granted=["search", "calc"])

        await runner.run(step, {}, {}, "trace-1")

        assert fabric.call_log[0].context_override == {"tools_granted": ["search", "calc"]}

    @pytest.mark.asyncio
    async def test_activity_profile_maps_to_context_override(self) -> None:
        _, runner, fabric = await _svc()
        step = _step("s1", "cap.s1", activity_profile="calendar.v1")

        await runner.run(step, {}, {}, "trace-1")

        assert fabric.call_log[0].context_override == {"activity_profile": "calendar.v1"}

    @pytest.mark.asyncio
    async def test_activity_profile_and_tools_granted_share_context_override(self) -> None:
        _, runner, fabric = await _svc()
        step = _step(
            "s1",
            "cap.s1",
            tools_granted=["search", "calc"],
            activity_profile="calendar.v1",
        )

        await runner.run(step, {}, {}, "trace-1")

        assert fabric.call_log[0].context_override == {
            "tools_granted": ["search", "calc"],
            "activity_profile": "calendar.v1",
        }

    @pytest.mark.asyncio
    async def test_context_override_absent_without_tools_or_activity_profile(self) -> None:
        _, runner, fabric = await _svc()
        step = _step("s1", "cap.s1")

        await runner.run(step, {}, {}, "trace-1")

        assert fabric.call_log[0].context_override is None


class TestRetryPolicy:
    @pytest.mark.asyncio
    async def test_transient_failure_retries_then_succeeds(self) -> None:
        _, runner, fabric = await _svc()
        calls = {"n": 0}

        async def _seq(request: CapabilityRequest) -> CapabilityResult:
            fabric.call_log.append(request)
            calls["n"] += 1
            if calls["n"] == 1:
                return _fail(retriable=True, message="transient")
            return _ok(trace_id=request.trace_id)

        fabric.execute = _seq  # type: ignore[assignment]
        step = _step("s1", "cap.retry")

        result = await runner.run(step, {}, {}, "trace-r")

        assert result.status == StepStatus.COMPLETED
        assert result.retry_attempts == 1
        assert len(fabric.call_log) == 2

    @pytest.mark.asyncio
    async def test_retriable_exhausts_budget(self) -> None:
        _, runner, fabric = await _svc()
        fabric.script_result("cap.fail", _fail(retriable=True, message="still failing"))
        step = _step("s1", "cap.fail")

        result = await runner.run(step, {}, {}, "trace-f")

        assert result.status == StepStatus.FAILED
        assert result.retry_attempts == runner._policies.normal_retries
        assert len(fabric.call_log) == 1 + runner._policies.normal_retries

    @pytest.mark.asyncio
    async def test_permanent_failure_no_retry(self) -> None:
        _, runner, fabric = await _svc()
        fabric.script_result("cap.perm", _fail(retriable=False, message="fatal"))
        step = _step("s1", "cap.perm")

        result = await runner.run(step, {}, {}, "trace-p")

        assert result.status == StepStatus.FAILED
        assert result.retry_attempts == 0
        assert len(fabric.call_log) == 1


class TestSchemaRetry:
    @pytest.mark.asyncio
    async def test_schema_retry_injects_schema_hint(self) -> None:
        _, runner, fabric = await _svc()
        calls = {"n": 0}

        async def _seq(request: CapabilityRequest) -> CapabilityResult:
            fabric.call_log.append(request)
            calls["n"] += 1
            if calls["n"] == 1:
                return _ok({"wrong": 1}, trace_id=request.trace_id)
            return _ok({"summary": "ok"}, trace_id=request.trace_id)

        fabric.execute = _seq  # type: ignore[assignment]
        step = _step(
            "s1",
            "cap.schema",
            output_schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        )

        result = await runner.run(step, {"x": 1}, {}, "trace-s")

        assert result.status == StepStatus.COMPLETED
        assert result.schema_retry is True
        assert len(fabric.call_log) == 2
        assert "__schema_hint" in fabric.call_log[1].params
        assert fabric.call_log[1].params["x"] == 1

    @pytest.mark.asyncio
    async def test_schema_retry_budget_exhausted_keeps_completed(self) -> None:
        _, runner, fabric = await _svc()
        fabric.script_result("cap.schema", _ok({"wrong": True}))
        step = _step("s1", "cap.schema", output_schema={"type": "object", "required": ["summary"]})

        result = await runner.run(step, {}, {}, "trace-s")

        # Current implementation returns COMPLETED when Fabric succeeded,
        # even if schema remains invalid after schema-retry budget.
        assert result.status == StepStatus.COMPLETED
        assert result.schema_retry is True
        assert len(fabric.call_log) == 2

    @pytest.mark.asyncio
    async def test_schema_then_retriable_failure_uses_normal_retry_budget(self) -> None:
        _, runner, fabric = await _svc()
        calls = {"n": 0}

        async def _seq(request: CapabilityRequest) -> CapabilityResult:
            fabric.call_log.append(request)
            calls["n"] += 1
            if calls["n"] == 1:
                return _ok({"wrong": True}, trace_id=request.trace_id)
            if calls["n"] == 2:
                return _fail(retriable=True, message="temp", trace_id=request.trace_id)
            return _ok({"summary": "ok"}, trace_id=request.trace_id)

        fabric.execute = _seq  # type: ignore[assignment]
        step = _step(
            "s1",
            "cap.combo",
            output_schema={"type": "object", "required": ["summary"]},
        )

        result = await runner.run(step, {}, {}, "trace-c")

        assert result.status == StepStatus.COMPLETED
        assert result.schema_retry is True
        assert result.retry_attempts == 1
        assert len(fabric.call_log) == 3


class TestSchemaValidationHelpers:
    @pytest.mark.asyncio
    async def test_validate_output_schema_valid(self) -> None:
        _, runner, _ = await _svc()
        sv = runner.validate_output_schema(
            _ok({"name": "x"}),
            {"type": "object", "properties": {"name": {"type": "string"}}},
        )
        assert sv.valid is True
        assert sv.errors == []

    @pytest.mark.asyncio
    async def test_validate_output_schema_none_data_invalid(self) -> None:
        _, runner, _ = await _svc()
        result = CapabilityResult(
            request_id="r1",
            success=True,
            data=None,
            error=None,
            provider_id="mock",
            trace_id="trace-1",
        )
        sv = runner.validate_output_schema(result, {"type": "object"})
        assert sv.valid is False
        assert "None" in sv.errors[0]

    def test_build_schema_suggestion_caps_error_list(self) -> None:
        msg = StepRunner._build_schema_suggestion([f"e{i}" for i in range(8)])
        assert "(and 3 more)" in msg

    @pytest.mark.asyncio
    async def test_build_schema_retry_request_preserves_identity_fields(self) -> None:
        _, runner, _ = await _svc()
        step = _step("sid", "cap.x")
        req = runner._build_request(step, {"a": 1}, "trace-z")
        new_req = runner._build_schema_retry_request(
            req,
            step,
            SchemaResult(valid=False, errors=["bad"], suggestion="fix it"),
        )
        assert new_req.capability_name == req.capability_name
        assert new_req.trace_id == req.trace_id
        assert new_req.params["__schema_hint"] == "fix it"
        assert "__schema_hint" not in req.params


class TestFailuresAndTiming:
    @pytest.mark.asyncio
    async def test_execute_exception_wrapped_as_failure(self) -> None:
        _, runner, fabric = await _svc()

        async def _boom(request: CapabilityRequest) -> CapabilityResult:
            fabric.call_log.append(request)
            raise RuntimeError("connection lost")

        fabric.execute = _boom  # type: ignore[assignment]
        step = _step("s1", "cap.ex")

        result = await runner.run(step, {}, {}, "trace-e")

        assert result.status == StepStatus.FAILED
        assert result.error_detail == "connection lost"
        assert result.result is not None
        assert result.result.error is not None
        assert result.result.error.code == "execution_exception"

    @pytest.mark.asyncio
    async def test_duration_reflects_runtime(self) -> None:
        _, runner, fabric = await _svc()
        fabric.script_timeout("cap.slow", 0.03)
        step = _step("s1", "cap.slow")

        start = time.monotonic()
        result = await runner.run(step, {}, {}, "trace-d")
        elapsed_ms = int((time.monotonic() - start) * 1000)

        assert result.status == StepStatus.COMPLETED
        assert result.duration_ms >= 20
        assert elapsed_ms >= 20

    def test_repr_contains_policy_values(self) -> None:
        # Non-async: repr is pure and static.
        from k1.orchestrator.types import OrchestratorPolicies

        runner = StepRunner(  # type: ignore[arg-type]
            fabric_port=MockFabricAdapter(),
            error_router=object(),
            policies=OrchestratorPolicies(normal_retries=5, step_timeout_default_ms=10000),
        )
        r = repr(runner)
        assert "StepRunner" in r
        assert "retries=5" in r
        assert "timeout=10000ms" in r
