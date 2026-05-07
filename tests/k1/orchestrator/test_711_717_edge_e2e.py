"""Unified edge-case E2E tests for milestones 7.1.1 through 7.1.7.

This file intentionally consolidates high-value edge behavior across:
  - 7.1.1 OrchestratorService
  - 7.1.2 DAGExecutor
  - 7.1.3 StepRunner
  - 7.1.4 ConstraintResolver
  - 7.1.5 WorkflowEngine
  - 7.1.6 ConnectorLifecycleManager
  - 7.1.7 ErrorRouter

All tests use OrchestratorFactory.create_standalone() and real in-memory adapters.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_ERROR_ROUTED
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.orchestration.error_router import ErrorRouter
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import (
    AdapterError,
    CommittedPlan,
    ErrorSeverity,
    InterruptRequest,
    PlanStep,
    ProcessingContext,
    ProcessResult,
    RegistryEntry,
    StepStatus,
    TaskEnvelope,
    TriggerSpec,
    TriggerType,
    WorkflowRunRequest,
)
from k1.orchestrator.workflows.workflow_types import WorkflowSpec


class _Transport:
    """Tiny MCP transport for ConnectorLifecycle discovery tests."""

    def __init__(self, tools_by_server: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
        self.tools_by_server = tools_by_server or {}

    async def list_tools(self, server: Any) -> List[Dict[str, Any]]:
        return self.tools_by_server.get(server.id, [])


def _yaml(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.write(fd, content.encode("utf-8"))
    os.close(fd)
    return path


async def _svc():
    service = await OrchestratorFactory.create_standalone()
    fabric: MockFabricAdapter = service._fabric_port  # type: ignore[assignment]
    delta: TestDeltaAdapter = service._delta_port  # type: ignore[assignment]
    event: TestEventAdapter = service._event_port  # type: ignore[assignment]
    return service, fabric, delta, event


def _register(fabric: MockFabricAdapter, name: str) -> None:
    fabric.register_capability(
        name,
        RegistryEntry(
            name=name,
            provider_type="tool",
            safety_band_min="GREEN",
            availability="AVAILABLE",
        ),
    )


def _medium_envelope(trace_id: str, capabilities: List[str]) -> TaskEnvelope:
    return TaskEnvelope(
        intent="edge-medium",
        trace_id=trace_id,
        tier="MEDIUM",
        capabilities=capabilities,
        params={cap: {} for cap in capabilities},
        context={"session_id": "s-edge"},
    )


def _high_envelope(trace_id: str) -> TaskEnvelope:
    return TaskEnvelope(
        intent="edge-high",
        trace_id=trace_id,
        tier="HIGH",
        capabilities=[],
        params={},
        context={"session_id": "s-edge"},
    )


def _unsafe_medium_envelope_with_many_caps(trace_id: str, cap_count: int) -> TaskEnvelope:
    """Build intentionally invalid MEDIUM envelope bypassing __post_init__."""
    envelope = TaskEnvelope.__new__(TaskEnvelope)
    object.__setattr__(envelope, "intent", "invalid-medium")
    object.__setattr__(envelope, "trace_id", trace_id)
    object.__setattr__(envelope, "tier", "MEDIUM")
    object.__setattr__(envelope, "capabilities", [f"tool.invalid.{i}" for i in range(cap_count)])
    object.__setattr__(envelope, "params", {})
    object.__setattr__(envelope, "context", {"session_id": "s-edge"})
    object.__setattr__(envelope, "constraints", {})
    object.__setattr__(envelope, "timeout_ms", 30000)
    object.__setattr__(envelope, "caller_id", "")
    object.__setattr__(envelope, "envelope_id", str(uuid4()))
    return envelope


@pytest.mark.asyncio
async def test_711_orchestrator_two_phase_orphan_then_success() -> None:
    service, fabric, delta, _ = await _svc()
    _register(fabric, "tool.edge.ok")

    trace_id = str(uuid4())
    deferred = await service.process(_high_envelope(trace_id))
    assert deferred == ProcessResult.DEFERRED
    assert len(service.pending_plans) == 1

    orphan_plan = CommittedPlan(
        plan_id="orphan-plan",
        request_id="missing-request-id",
        intent="edge-high",
        steps=[PlanStep(id="s1", capability="tool.edge.ok")],
        trace_id=trace_id,
    )
    orphan_result = await service.process(orphan_plan)
    assert orphan_result == ProcessResult.FAILED

    request_id = service._planner_port.request_log[0].request_id  # type: ignore[attr-defined]
    valid_plan = CommittedPlan(
        plan_id="valid-plan",
        request_id=request_id,
        intent="edge-high",
        steps=[PlanStep(id="s1", capability="tool.edge.ok")],
        trace_id=trace_id,
    )
    ok = await service.process(valid_plan)
    assert ok == ProcessResult.COMPLETED
    assert len(delta.get_emitted(ORCH_DAG_COMPLETED)) >= 1


@pytest.mark.asyncio
async def test_711_orchestrator_medium_orch10_violation_fails() -> None:
    service, _, _, _ = await _svc()
    invalid = _unsafe_medium_envelope_with_many_caps(str(uuid4()), 3)
    result = await service.process(invalid)
    assert result == ProcessResult.FAILED


@pytest.mark.asyncio
async def test_711_orchestrator_recoverable_requeue_once_then_fail() -> None:
    service, fabric, _, _ = await _svc()

    async def _raise_query_registry(_: str):
        raise AdapterException(
            AdapterError(
                severity=ErrorSeverity.RECOVERABLE,
                adapter_name="fabric",
                operation="query_registry",
                error_code="UNAVAILABLE",
                error_message="transient registry error",
            )
        )

    fabric.query_registry = _raise_query_registry  # type: ignore[assignment]
    envelope = _medium_envelope(str(uuid4()), ["tool.edge.requeue"])

    first = await service.process(envelope)
    second = await service.process(envelope)

    assert first == ProcessResult.DEFERRED
    assert second == ProcessResult.FAILED
    assert len(service._mailbox.enqueued_log) == 1


@pytest.mark.asyncio
async def test_711_orchestrator_pause_interrupt_rejected_v1() -> None:
    service, _, _, _ = await _svc()
    pause = InterruptRequest(interrupt_type="PAUSE", trace_id=str(uuid4()))
    result = await service.process(pause)
    assert result == ProcessResult.FAILED


@pytest.mark.asyncio
async def test_712_dag_executor_interrupt_and_wal_edges() -> None:
    service, fabric, _, _ = await _svc()
    dag = service._dag_executor
    bridge = service._bridge_port

    _register(fabric, "tool.edge.s1")
    _register(fabric, "tool.edge.s2")
    fabric.script_timeout("tool.edge.s1", 0.03)

    plan = CommittedPlan(
        plan_id="dag-edge-1",
        request_id="req-edge-1",
        intent="interrupt",
        steps=[
            PlanStep(id="s1", capability="tool.edge.s1"),
            PlanStep(id="s2", capability="tool.edge.s2"),
        ],
        dependencies={"s2": ["s1"]},
        trace_id="trace-dag-edge",
    )

    async def _flip_interrupt() -> None:
        await asyncio.sleep(0.01)
        dag.interrupt_flag = True

    snapshot = await service._state_port.get_snapshot("s-edge")
    flipper = asyncio.create_task(_flip_interrupt())
    result = await dag.execute(plan, snapshot)  # type: ignore[arg-type]
    await flipper

    assert result.success is False
    s2 = [r for r in result.step_results if r.step_id == "s2"][0]
    assert s2.status in {StepStatus.CANCELLED, StepStatus.FAILED}

    wal = bridge.get_wal("dag-edge-1")
    assert wal is not None
    assert any(e["entry_type"] == "PLAN_START" for e in wal)


@pytest.mark.asyncio
async def test_712_dag_executor_dependency_failure_cancels_dependents() -> None:
    service, fabric, _, _ = await _svc()
    dag = service._dag_executor

    _register(fabric, "tool.dep.s1")
    _register(fabric, "tool.dep.s2")
    _register(fabric, "tool.dep.s3")
    fabric.script_result(
        "tool.dep.s1",
        CapabilityResult.failure_result(
            request_id="r-fail",
            error_code="ERR",
            error_message="boom",
            retriable=False,
            provider_id="mock",
            trace_id="trace-dep",
        ),
    )

    plan = CommittedPlan(
        plan_id="dag-dep-fail",
        request_id="req-dep-fail",
        intent="dep-fail",
        steps=[
            PlanStep(id="s1", capability="tool.dep.s1"),
            PlanStep(id="s2", capability="tool.dep.s2"),
            PlanStep(id="s3", capability="tool.dep.s3"),
        ],
        dependencies={"s2": ["s1"], "s3": ["s2"]},
        trace_id="trace-dep",
    )

    snapshot = await service._state_port.get_snapshot("s-edge")
    result = await dag.execute(plan, snapshot)  # type: ignore[arg-type]

    assert result.success is False
    s2 = [r for r in result.step_results if r.step_id == "s2"][0]
    s3 = [r for r in result.step_results if r.step_id == "s3"][0]
    assert s2.status == StepStatus.CANCELLED
    assert s3.status == StepStatus.CANCELLED


@pytest.mark.asyncio
async def test_713_step_runner_schema_retry_edge() -> None:
    service, fabric, _, _ = await _svc()
    runner = service._dag_executor._step_runner

    calls = {"n": 0}

    async def _seq(request: CapabilityRequest) -> CapabilityResult:
        fabric.call_log.append(request)
        calls["n"] += 1
        if calls["n"] == 1:
            return CapabilityResult.success_result(
                request_id="r1",
                data={"wrong": True},
                provider_id="mock",
                trace_id=request.trace_id,
            )
        return CapabilityResult.success_result(
            request_id="r2",
            data={"summary": "ok"},
            provider_id="mock",
            trace_id=request.trace_id,
        )

    fabric.execute = _seq  # type: ignore[assignment]

    step = PlanStep(
        id="schema-step",
        capability="tool.edge.schema",
        output_schema={"type": "object", "required": ["summary"]},
    )

    result = await runner.run(step, {}, {}, "trace-schema-edge")
    assert result.status == StepStatus.COMPLETED
    assert result.schema_retry is True
    assert len(fabric.call_log) == 2


@pytest.mark.asyncio
async def test_713_step_runner_permanent_failure_no_retry() -> None:
    service, fabric, _, _ = await _svc()
    runner = service._dag_executor._step_runner

    fabric.script_result(
        "tool.edge.perm",
        CapabilityResult.failure_result(
            request_id="r-perm",
            error_code="PERM",
            error_message="fatal",
            retriable=False,
            provider_id="mock",
            trace_id="trace-perm",
        ),
    )

    result = await runner.run(PlanStep(id="p1", capability="tool.edge.perm"), {}, {}, "trace-perm")
    assert result.status == StepStatus.FAILED
    assert result.retry_attempts == 0
    assert len(fabric.call_log) == 1


@pytest.mark.asyncio
async def test_713_step_runner_retriable_exhausts_budget() -> None:
    service, fabric, _, _ = await _svc()
    runner = service._dag_executor._step_runner

    fabric.script_result(
        "tool.edge.retry",
        CapabilityResult.failure_result(
            request_id="r-retry",
            error_code="TEMP",
            error_message="temporary",
            retriable=True,
            provider_id="mock",
            trace_id="trace-retry",
        ),
    )

    result = await runner.run(
        PlanStep(id="r1", capability="tool.edge.retry"), {}, {}, "trace-retry"
    )
    assert result.status == StepStatus.FAILED
    assert result.retry_attempts == runner._policies.normal_retries
    assert len(fabric.call_log) == 1 + runner._policies.normal_retries


@pytest.mark.asyncio
async def test_714_constraint_resolver_hil_edge() -> None:
    service, _, delta, _ = await _svc()
    resolver = service._constraint_resolver

    plan = CommittedPlan(
        plan_id="constraint-edge-1",
        request_id="req-constraint-1",
        intent="constraint",
        steps=[PlanStep(id="s1", capability="tool.missing.edge")],
        trace_id="trace-constraint-edge",
    )

    validation = await resolver.validate(
        plan,
        service._build_context(_high_envelope("trace-constraint-edge")),
    )
    assert validation.valid is False
    assert validation.hil_required is True
    assert validation.hil_response is not None
    assert validation.hil_response.timed_out is True


@pytest.mark.asyncio
async def test_714_constraint_resolver_auto_alternative_resolution() -> None:
    service, fabric, _, _ = await _svc()
    resolver = service._constraint_resolver

    _register(fabric, "tool.calendar.find")
    plan = CommittedPlan(
        plan_id="constraint-alt-1",
        request_id="req-constraint-alt-1",
        intent="constraint-alt",
        steps=[PlanStep(id="s1", capability="tool.calendar.search")],
        trace_id="trace-constraint-alt",
    )

    validation = await resolver.validate(
        plan, service._build_context(_high_envelope("trace-constraint-alt"))
    )
    assert validation.valid is True
    assert validation.hil_required is False
    assert len(validation.alternatives_applied) >= 1


@pytest.mark.asyncio
async def test_715_workflow_engine_execute_missing_then_success_edge() -> None:
    service, fabric, _, _ = await _svc()
    engine = service._workflow_engine

    missing_spec = WorkflowSpec(
        workflow_id="wf-edge-missing",
        name="wf-edge-missing",
        source_plan_id="plan-missing",
        version="1.0.0",
        trigger=TriggerSpec(type=TriggerType.MANUAL),
        steps=[PlanStep(id="s1", capability="tool.workflow.missing")],
        dependencies={},
        active=True,
    )
    await engine.registry.save(missing_spec)

    missing_result = await engine.execute_workflow(
        WorkflowRunRequest(
            workflow_id="wf-edge-missing",
            version="1.0.0",
            trigger_type=TriggerType.MANUAL,
            trace_id="trace-wf-missing",
        ),
        service._build_context(_high_envelope("trace-wf-missing")),
    )
    assert missing_result == ProcessResult.FAILED

    _register(fabric, "tool.workflow.ok")
    ok_spec = WorkflowSpec(
        workflow_id="wf-edge-ok",
        name="wf-edge-ok",
        source_plan_id="plan-ok",
        version="1.0.0",
        trigger=TriggerSpec(type=TriggerType.MANUAL),
        steps=[PlanStep(id="s1", capability="tool.workflow.ok")],
        dependencies={},
        active=True,
    )
    await engine.registry.save(ok_spec)

    ok_result = await engine.execute_workflow(
        WorkflowRunRequest(
            workflow_id="wf-edge-ok",
            version="1.0.0",
            trigger_type=TriggerType.MANUAL,
            trace_id="trace-wf-ok",
        ),
        service._build_context(_high_envelope("trace-wf-ok")),
    )
    assert ok_result in {ProcessResult.COMPLETED, ProcessResult.DEGRADED}


@pytest.mark.asyncio
async def test_715_workflow_engine_duplicate_name_rejected() -> None:
    service, _, _, _ = await _svc()
    engine = service._workflow_engine

    spec_a = WorkflowSpec(
        workflow_id="wf-dup-a",
        name="same-name",
        source_plan_id="plan-a",
        version="1.0.0",
        trigger=TriggerSpec(type=TriggerType.MANUAL),
        steps=[PlanStep(id="s1", capability="tool.workflow.a")],
        dependencies={},
        active=True,
    )
    spec_b = WorkflowSpec(
        workflow_id="wf-dup-b",
        name="same-name",
        source_plan_id="plan-b",
        version="1.0.0",
        trigger=TriggerSpec(type=TriggerType.MANUAL),
        steps=[PlanStep(id="s1", capability="tool.workflow.b")],
        dependencies={},
        active=True,
    )

    await engine.registry.save(spec_a)
    with pytest.raises(ValueError):
        await engine.registry.save(spec_b)


@pytest.mark.asyncio
async def test_716_connector_lifecycle_discovery_refresh_edge() -> None:
    service, _, _, event = await _svc()
    lifecycle = service._connector_lifecycle

    path = _yaml(
        """servers:
  - id: cal
    type: remote
    endpoint: http://cal
"""
    )
    try:
        lifecycle._discovery._config_path = path  # type: ignore[attr-defined]
        lifecycle._discovery._transport = _Transport(  # type: ignore[attr-defined]
            {"cal": [{"name": "create_event", "description": "Create"}]}
        )

        first = await lifecycle.discover_and_register()
        assert first.registered == 1
        assert len(lifecycle.get_capabilities("cal")) == 1

        lifecycle.start_lifecycle_monitoring()
        event.fire(
            "k1.fabric.provider.health.changed.v1",
            {"provider_id": "mcp.cal", "old_state": "DEGRADED", "new_state": "HEALTHY"},
        )
        assert lifecycle.get_pending_refreshes() == ["cal"]

        refreshed = await lifecycle.refresh("cal")
        assert refreshed.registered == 1
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_716_connector_lifecycle_empty_config_discovers_none() -> None:
    service, _, _, _ = await _svc()
    lifecycle = service._connector_lifecycle
    path = _yaml("servers: []")
    try:
        lifecycle._discovery._config_path = path  # type: ignore[attr-defined]
        lifecycle._discovery._transport = _Transport({})  # type: ignore[attr-defined]
        result = await lifecycle.discover_and_register()
        assert result.registered == 0
        assert result.skipped == 0
        assert result.errors == []
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_716_connector_lifecycle_malformed_config_reports_error() -> None:
    service, _, _, _ = await _svc()
    lifecycle = service._connector_lifecycle
    path = _yaml("servers: {}")
    try:
        lifecycle._discovery._config_path = path  # type: ignore[attr-defined]
        lifecycle._discovery._transport = _Transport({})  # type: ignore[attr-defined]
        result = await lifecycle.discover_and_register()
        assert result.registered == 0
        assert len(result.errors) >= 1
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_717_error_router_multiseverity_edge_matrix() -> None:
    _, _, delta, _ = await _svc()
    router = ErrorRouter(delta)

    retry = await router.route_error(
        AdapterError(
            severity=ErrorSeverity.RECOVERABLE,
            adapter_name="mailbox",
            operation="enqueue",
            error_code="BUSY",
            error_message="busy",
            trace_id="trace-retry",
        ),
        {"trace_id": "trace-retry"},
    )
    assert retry.action == "RETRY"

    fallback = await router.route_error(
        AdapterError(
            severity=ErrorSeverity.DEGRADED,
            adapter_name="planner",
            operation="request_plan",
            error_code="CB_OPEN",
            error_message="circuit open",
            trace_id="trace-fallback",
        ),
        {"trace_id": "trace-fallback"},
    )
    assert fallback.action == "FALLBACK"

    abort = await router.route_error(
        AdapterError(
            severity=ErrorSeverity.TERMINAL,
            adapter_name="fabric_gateway",
            operation="execute",
            error_code="FATAL",
            error_message="fatal",
            trace_id="trace-abort",
        ),
        {"trace_id": "trace-abort"},
    )
    assert abort.action == "ABORT"

    emitted = delta.get_emitted(ORCH_ERROR_ROUTED)
    assert len(emitted) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "severity,adapter,expected_action",
    [
        (ErrorSeverity.RECOVERABLE, "mailbox", "RETRY"),
        (ErrorSeverity.RECOVERABLE, "delta_emit", "RETRY"),
        (ErrorSeverity.RECOVERABLE, "bridge_write", "RETRY"),
        (ErrorSeverity.RECOVERABLE, "event_sub", "RETRY"),
        (ErrorSeverity.DEGRADED, "fabric_gateway", "DEGRADE"),
        (ErrorSeverity.DEGRADED, "planner", "FALLBACK"),
        (ErrorSeverity.DEGRADED, "state_read", "DEGRADE"),
        (ErrorSeverity.TERMINAL, "any", "ABORT"),
    ],
)
async def test_717_error_router_param_matrix(
    severity: ErrorSeverity,
    adapter: str,
    expected_action: str,
) -> None:
    _, _, delta, _ = await _svc()
    router = ErrorRouter(delta)

    action = await router.route_error(
        AdapterError(
            severity=severity,
            adapter_name=adapter,
            operation="op",
            error_code="E",
            error_message="msg",
            trace_id="trace-matrix",
        ),
        {"trace_id": "trace-matrix"},
    )
    assert action.action == expected_action


@pytest.mark.asyncio
async def test_717_error_router_state_read_has_empty_fallback_value() -> None:
    _, _, delta, _ = await _svc()
    router = ErrorRouter(delta)

    action = await router.route_error(
        AdapterError(
            severity=ErrorSeverity.DEGRADED,
            adapter_name="state_read",
            operation="get_snapshot",
            error_code="STALE",
            error_message="stale",
            trace_id="trace-state-read",
        ),
        {},
    )
    assert action.action == "DEGRADE"
    assert action.fallback_value == {}


def test_717_error_router_classify_is_pure_no_emission() -> None:
    delta = TestDeltaAdapter()
    router = ErrorRouter(delta)
    exc = AdapterException(
        AdapterError(
            severity=ErrorSeverity.DEGRADED,
            adapter_name="planner",
            operation="request_plan",
            error_code="CB_OPEN",
            error_message="open",
            trace_id="trace-pure",
        )
    )
    ctx = ProcessingContext(trace_id="trace-pure", request_id="req-pure", tier="HIGH")

    severity = router.classify(exc, ctx)
    assert severity == ErrorSeverity.DEGRADED
    assert delta.emitted == []


@pytest.mark.asyncio
async def test_e2e_single_flow_711_to_717_in_one_run() -> None:
    """Single stitched flow touching all 7.1.x service surfaces in one run."""
    service, fabric, delta, _ = await _svc()

    # 7.1.1 + 7.1.2: medium success, then high two-phase DAG execution.
    _register(fabric, "tool.e2e.medium")
    _register(fabric, "tool.e2e.high")

    medium = await service.process(_medium_envelope("trace-e2e", ["tool.e2e.medium"]))
    assert medium == ProcessResult.COMPLETED

    high_req = await service.process(_high_envelope("trace-e2e"))
    assert high_req == ProcessResult.DEFERRED
    req_id = service._planner_port.request_log[-1].request_id  # type: ignore[attr-defined]

    plan = CommittedPlan(
        plan_id="plan-e2e",
        request_id=req_id,
        intent="edge-high",
        steps=[PlanStep(id="hs1", capability="tool.e2e.high")],
        trace_id="trace-e2e",
    )
    high_result = await service.process(plan)
    assert high_result == ProcessResult.COMPLETED

    # 7.1.7: route a degraded error and verify diagnostic signal was emitted.
    action = await service._error_router.route_error(
        AdapterError(
            severity=ErrorSeverity.DEGRADED,
            adapter_name="state_read",
            operation="get_snapshot",
            error_code="STALE",
            error_message="stale",
            trace_id="trace-e2e",
        ),
        {"trace_id": "trace-e2e"},
    )
    assert action.action == "DEGRADE"

    # Verify completion and error diagnostics both surfaced.
    assert len(delta.get_emitted(ORCH_DAG_COMPLETED)) >= 2
    assert len(delta.get_emitted(ORCH_ERROR_ROUTED)) >= 1
