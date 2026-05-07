"""M17.E1.I3 — FabricDispatchAdapter workflow.* routing tests.

Validates that:
* ``capability_name`` starting with ``workflow.`` is intercepted before
  the fabric resolution step and forwarded to ``WorkflowEngine``.
* RUN mode (default) builds a ``WorkflowRunRequest`` and translates the
  engine's ``ProcessResult`` into a ``CapabilityResult``.
* SAVE mode (``params["_persist"] = True``) builds a
  ``WorkflowSaveRequest`` with the supplied trigger spec.
* Dict ``_trigger_spec`` values coerce to the real ``TriggerSpec``.
* When the adapter is built without a ``workflow_engine`` the request
  surfaces a clear ``workflow_engine_not_wired`` error rather than
  silently falling through to the fabric (which would return the generic
  ``resolution_failed``).
"""

from __future__ import annotations

from typing import Any, List

import pytest

from k1.concierge.adapters.fabric_dispatch import FabricDispatchAdapter
from k1.fabric.types import CapabilityRequest
from k1.orchestrator.types import (
    ProcessResult,
    TriggerSpec,
    TriggerType,
    WorkflowRunRequest,
    WorkflowSaveRequest,
)

# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class _FabricSpy:
    """Records `execute()` calls; should NEVER be called for workflow.*."""

    def __init__(self) -> None:
        self.calls: List[CapabilityRequest] = []

    async def execute(self, request: CapabilityRequest) -> Any:  # pragma: no cover
        self.calls.append(request)
        raise AssertionError("fabric.execute called for workflow.* — should have been intercepted")


class _WorkflowEngineSpy:
    """Minimal WorkflowEngineLike stub returning a configurable result."""

    def __init__(
        self,
        execute_result: ProcessResult = ProcessResult.COMPLETED,
        save_result: ProcessResult = ProcessResult.COMPLETED,
    ) -> None:
        self._execute_result = execute_result
        self._save_result = save_result
        self.execute_calls: List[WorkflowRunRequest] = []
        self.save_calls: List[WorkflowSaveRequest] = []

    async def execute_workflow(self, request: WorkflowRunRequest, ctx: Any) -> ProcessResult:
        self.execute_calls.append(request)
        return self._execute_result

    async def save_workflow(self, request: WorkflowSaveRequest, ctx: Any) -> ProcessResult:
        self.save_calls.append(request)
        return self._save_result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_run_intercepts_and_forwards_to_engine() -> None:
    fabric = _FabricSpy()
    engine = _WorkflowEngineSpy()
    adapter = FabricDispatchAdapter(
        fabric_port=fabric,
        workflow_engine=engine,
    )

    req = CapabilityRequest(
        capability_name="workflow.morning_briefing",
        params={"foo": "bar"},
        trace_id="trace-1",
        caller="concierge",
        caller_id="concierge.back",
    )
    result = await adapter.dispatch_direct(req)

    assert fabric.calls == []
    assert len(engine.execute_calls) == 1
    run_req = engine.execute_calls[0]
    assert run_req.workflow_id == "morning_briefing"
    assert run_req.trigger_type == TriggerType.MANUAL
    assert run_req.trigger_context == {
        "caller": "concierge",
        "caller_id": "concierge.back",
    }
    assert run_req.param_overrides == {"foo": "bar"}

    assert result.success is True
    assert result.provider_id == "workflow_engine"
    assert result.data["mode"] == "run"
    assert result.data["workflow_id"] == "morning_briefing"
    assert result.data["process_result"] == "COMPLETED"


@pytest.mark.asyncio
async def test_workflow_run_degraded_is_success_with_status() -> None:
    engine = _WorkflowEngineSpy(execute_result=ProcessResult.DEGRADED)
    adapter = FabricDispatchAdapter(
        fabric_port=_FabricSpy(),
        workflow_engine=engine,
    )

    result = await adapter.dispatch_direct(
        CapabilityRequest(
            capability_name="workflow.flaky",
            params={},
            trace_id="t",
            caller="concierge",
        )
    )

    assert result.success is True
    assert result.data["process_result"] == "DEGRADED"


@pytest.mark.asyncio
async def test_workflow_run_failure_returns_typed_error() -> None:
    engine = _WorkflowEngineSpy(execute_result=ProcessResult.FAILED)
    adapter = FabricDispatchAdapter(
        fabric_port=_FabricSpy(),
        workflow_engine=engine,
    )

    result = await adapter.dispatch_direct(
        CapabilityRequest(
            capability_name="workflow.broken",
            params={},
            trace_id="t",
            caller="concierge",
        )
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "workflow_failed"
    assert "FAILED" in result.error.message


@pytest.mark.asyncio
async def test_workflow_save_with_real_trigger_spec() -> None:
    engine = _WorkflowEngineSpy()
    adapter = FabricDispatchAdapter(
        fabric_port=_FabricSpy(),
        workflow_engine=engine,
    )

    spec = TriggerSpec(type=TriggerType.CRON, schedule="0 9 * * *", timezone="UTC")
    req = CapabilityRequest(
        capability_name="workflow.daily_briefing",
        params={
            "_persist": True,
            "_trigger_spec": spec,
            "_committed_plan_id": "plan-abc",
            "_workflow_name": "Morning Briefing",
        },
        trace_id="trace-2",
        caller="concierge",
        caller_id="concierge.back",
    )
    result = await adapter.dispatch_direct(req)

    assert engine.execute_calls == []
    assert len(engine.save_calls) == 1
    save_req = engine.save_calls[0]
    assert save_req.committed_plan_id == "plan-abc"
    assert save_req.workflow_name == "Morning Briefing"
    assert save_req.trigger_spec is spec
    assert save_req.trace_id == "trace-2"

    assert result.success is True
    assert result.data["mode"] == "save"
    assert result.data["workflow_name"] == "Morning Briefing"


@pytest.mark.asyncio
async def test_workflow_save_coerces_dict_trigger_spec() -> None:
    engine = _WorkflowEngineSpy()
    adapter = FabricDispatchAdapter(
        fabric_port=_FabricSpy(),
        workflow_engine=engine,
    )

    req = CapabilityRequest(
        capability_name="workflow.noop",
        params={
            "_persist": True,
            "_trigger_spec": {"type": "EVENT", "event_topic": "k1.alarm.fired.v1"},
            "_committed_plan_id": "plan-xyz",
        },
        trace_id="t3",
        caller="concierge",
    )
    result = await adapter.dispatch_direct(req)

    assert result.success is True
    save_req = engine.save_calls[0]
    assert save_req.trigger_spec.type == TriggerType.EVENT
    assert save_req.trigger_spec.event_topic == "k1.alarm.fired.v1"
    # workflow_name defaults to the workflow_id when omitted.
    assert save_req.workflow_name == "noop"


@pytest.mark.asyncio
async def test_workflow_save_default_trigger_is_manual() -> None:
    engine = _WorkflowEngineSpy()
    adapter = FabricDispatchAdapter(
        fabric_port=_FabricSpy(),
        workflow_engine=engine,
    )

    result = await adapter.dispatch_direct(
        CapabilityRequest(
            capability_name="workflow.adhoc",
            params={"_persist": True, "_committed_plan_id": "plan-1"},
            trace_id="t",
            caller="concierge",
        )
    )

    assert result.success is True
    assert engine.save_calls[0].trigger_spec.type == TriggerType.MANUAL


@pytest.mark.asyncio
async def test_workflow_dispatch_without_engine_returns_clear_error() -> None:
    fabric = _FabricSpy()
    adapter = FabricDispatchAdapter(
        fabric_port=fabric,
        workflow_engine=None,  # explicitly unwired
    )

    result = await adapter.dispatch_direct(
        CapabilityRequest(
            capability_name="workflow.something",
            params={},
            trace_id="t",
            caller="concierge",
        )
    )

    # MUST NOT have called the fabric.
    assert fabric.calls == []
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "workflow_engine_not_wired"


@pytest.mark.asyncio
async def test_non_workflow_capability_still_routes_to_fabric() -> None:
    """LOW tier (tool.*) still goes through the fabric unchanged."""

    class _OkFabric:
        def __init__(self) -> None:
            self.calls: List[CapabilityRequest] = []

        async def execute(self, request: CapabilityRequest) -> Any:
            self.calls.append(request)
            from k1.fabric.types import CapabilityResult

            return CapabilityResult(
                request_id=request.request_id,
                trace_id=request.trace_id,
                success=True,
                data={"ok": True},
                provider_id="test-provider",
            )

    fabric = _OkFabric()
    engine = _WorkflowEngineSpy()
    adapter = FabricDispatchAdapter(
        fabric_port=fabric,
        workflow_engine=engine,
    )

    result = await adapter.dispatch_direct(
        CapabilityRequest(
            capability_name="tool.execute.send_message",
            params={"to": "x"},
            trace_id="t",
            caller="concierge",
        )
    )

    assert len(fabric.calls) == 1
    assert engine.execute_calls == []
    assert engine.save_calls == []
    assert result.success is True


@pytest.mark.asyncio
async def test_workflow_save_invalid_trigger_type_is_request_invalid() -> None:
    engine = _WorkflowEngineSpy()
    adapter = FabricDispatchAdapter(
        fabric_port=_FabricSpy(),
        workflow_engine=engine,
    )

    result = await adapter.dispatch_direct(
        CapabilityRequest(
            capability_name="workflow.bad",
            params={
                "_persist": True,
                "_trigger_spec": {"type": "NOPE"},
                "_committed_plan_id": "p",
            },
            trace_id="t",
            caller="concierge",
        )
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "workflow_request_invalid"
    assert engine.save_calls == []
