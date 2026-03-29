"""
Tests for OrchestratorService -- 7.1.1 Rewritten with Real Adapters.

ALL tests use OrchestratorFactory.create_standalone() -- no direct
OrchestratorService construction, no hand-built fakes.

Test adapters accessed through service attributes:
  - service._fabric_port  (MockFabricAdapter)
  - service._planner_port (MockPlannerAdapter)
  - service._delta_port   (TestDeltaAdapter)
  - service._event_port   (TestEventAdapter)
  - service._mailbox      (TestMailboxAdapter)
  - service._state_port   (MockStateReadAdapter)
  - service._bridge_port  (MockBridgeAdapter)

Coverage targets:
  process()                 -- isinstance routing for all 5 types + unknown
  _route_task()             -- MEDIUM / HIGH tier routing
  _dispatch_medium()        -- 1-2 caps, safety_band, per-step error isolation
  _dispatch_high()          -- two-phase: PlanRequest -> DEFERRED
  _receive_plan()           -- RACE-3 dedup, RACE-2 orphan, correlation
  receive_plan_failed()     -- pending context pop, emit
  receive_plan_cancelled()  -- pending context pop
  _save_workflow()          -- delegation + WORKFLOW_SAVED delta
  _handle_interrupt()       -- CANCEL_DAG + PAUSE rejection
  reap_stale_contexts()     -- timeout expiry
  _build_context()          -- extraction per message type
  _validate_envelope()      -- missing trace_id, intent, invalid tier
  _record_executed_plan()   -- LRU eviction boundary
  _handle_adapter_error()   -- severity -> ProcessResult mapping
  _result_to_process_result -- AggregatedResult -> ProcessResult mapping
  aggregate()               -- pure function (from_medium, from_dag)

Invariants verified: ORCH-01, ORCH-02, ORCH-09, ORCH-10, ORCH-11.

Reference: Issue 7.1.1 in orchestrator-implementation-plan.md
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from k1.fabric.ports.state_reader import SessionSnapshot
from k1.fabric.types import CapabilityResult
from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.adapters.mock_state_read_adapter import MockStateReadAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.adapters.test_mailbox_adapter import TestMailboxAdapter
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.events import (
    ORCH_DAG_COMPLETED,
    ORCH_PLAN_REQUESTED,
    ORCH_TASK_ACCEPTED,
    ORCH_WORKFLOW_SAVED,
)
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.orchestration.orchestrator_service import AdapterException, OrchestratorService
from k1.orchestrator.types import (
    AdapterError,
    AggregatedResult,
    CommittedPlan,
    CompensationRecord,
    ErrorSeverity,
    InterruptRequest,
    PendingHILContext,
    PendingPlanContext,
    PlanAck,
    PlanStep,
    ProcessingContext,
    ProcessResult,
    RegistryEntry,
    StepResult,
    StepStatus,
    TaskEnvelope,
    TriggerSpec,
    TriggerType,
    WorkflowRunRequest,
    WorkflowSaveRequest,
)

# ===========================================================================
# Typed adapter access from factory-created service
# ===========================================================================


async def _svc():
    """Create an OrchestratorService via factory with all test adapters.

    Returns (service, fabric, planner, delta, event, mailbox, state) tuple.
    Every test gets a fresh instance -- no shared state.
    """
    service = await OrchestratorFactory.create_standalone()
    fabric: MockFabricAdapter = service._fabric_port  # type: ignore[assignment]
    planner: MockPlannerAdapter = service._planner_port  # type: ignore[assignment]
    delta: TestDeltaAdapter = service._delta_port  # type: ignore[assignment]
    event: TestEventAdapter = service._event_port  # type: ignore[assignment]
    mailbox: TestMailboxAdapter = service._mailbox  # type: ignore[assignment]
    state: MockStateReadAdapter = service._state_port  # type: ignore[assignment]
    return service, fabric, planner, delta, event, mailbox, state


# ===========================================================================
# Helpers -- build domain objects with sane defaults
# ===========================================================================


def _make_envelope(
    *,
    tier: str = "MEDIUM",
    intent: str = "test intent",
    trace_id: str = "",
    capabilities: Optional[List[str]] = None,
    params: Optional[Dict[str, Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> TaskEnvelope:
    """Build a TaskEnvelope with sane defaults."""
    tid = trace_id or str(uuid4())
    caps = capabilities or (["tool.test.a"] if tier == "MEDIUM" else [])
    return TaskEnvelope(
        intent=intent,
        trace_id=tid,
        tier=tier,
        capabilities=caps,
        params=params or {},
        context=context or {"session_id": "s1"},
    )


def _make_plan(
    *,
    plan_id: str = "",
    request_id: str = "",
    intent: str = "plan intent",
    trace_id: str = "",
    steps: Optional[List[PlanStep]] = None,
) -> CommittedPlan:
    """Build a CommittedPlan with sane defaults."""
    pid = plan_id or str(uuid4())
    rid = request_id or str(uuid4())
    tid = trace_id or str(uuid4())
    default_steps = steps or [
        PlanStep(
            id="s1",
            capability="tool.test.a",
            params={},
            deps=[],
        )
    ]
    return CommittedPlan(
        plan_id=pid,
        request_id=rid,
        intent=intent,
        steps=default_steps,
        trace_id=tid,
    )


def _make_workflow_run_request(
    *,
    workflow_id: str = "wf-1",
    trace_id: str = "",
) -> WorkflowRunRequest:
    tid = trace_id or str(uuid4())
    return WorkflowRunRequest(
        workflow_id=workflow_id,
        version="1",
        trigger_type=TriggerType.MANUAL,
        trace_id=tid,
    )


def _make_workflow_save_request(
    *,
    committed_plan_id: str = "plan-1",
    workflow_name: str = "test-workflow",
    trace_id: str = "",
) -> WorkflowSaveRequest:
    tid = trace_id or str(uuid4())
    return WorkflowSaveRequest(
        committed_plan_id=committed_plan_id,
        workflow_name=workflow_name,
        trigger_spec=TriggerSpec(type=TriggerType.MANUAL),
        trace_id=tid,
    )


def _make_interrupt(
    *,
    interrupt_type: str = "CANCEL_DAG",
    trace_id: str = "",
) -> InterruptRequest:
    tid = trace_id or str(uuid4())
    return InterruptRequest(
        interrupt_type=interrupt_type,
        trace_id=tid,
    )


def _success_result(cap_name: str = "tool.test.a") -> CapabilityResult:
    return CapabilityResult.success_result(
        request_id="r1",
        data={"answer": "42"},
        provider_id="p1",
        trace_id="t1",
        duration_ms=100,
    )


def _failure_result(cap_name: str = "tool.test.a") -> CapabilityResult:
    return CapabilityResult.failure_result(
        request_id="r1",
        error_code="ERR",
        error_message="Something failed",
        retriable=False,
        provider_id="p1",
        trace_id="t1",
        duration_ms=50,
    )


def _register_caps(fabric: MockFabricAdapter, *cap_names: str) -> None:
    """Register capabilities in MockFabricAdapter registry."""
    for name in cap_names:
        fabric.register_capability(
            name,
            RegistryEntry(
                name=name,
                provider_type="tool",
                safety_band_min="GREEN",
                availability="AVAILABLE",
            ),
        )


class _StubWorkflowEngine:
    """Lightweight workflow engine stub for tests that need to control
    execute_workflow / save_workflow outcomes without the real engine."""

    def __init__(self, *, execute=None, save=None):
        self._execute = execute
        self._save = save

    async def execute_workflow(self, request, ctx):
        if self._execute:
            return await self._execute(request, ctx)
        return ProcessResult.FAILED

    async def save_workflow(self, request, ctx):
        if self._save:
            return await self._save(request, ctx)
        return ProcessResult.FAILED


# ===========================================================================
# Tests: process() routing
# ===========================================================================


class TestProcessRouting:
    """Validate isinstance-based dispatch in process()."""

    @pytest.mark.asyncio
    async def test_route_task_envelope_medium(self) -> None:
        """TaskEnvelope with MEDIUM tier routes to _dispatch_medium."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a")
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a"])
        result = await svc.process(envelope)
        assert result == ProcessResult.COMPLETED

    @pytest.mark.asyncio
    async def test_route_task_envelope_high(self) -> None:
        """TaskEnvelope with HIGH tier routes to _dispatch_high -> DEFERRED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)
        assert result == ProcessResult.DEFERRED

    @pytest.mark.asyncio
    async def test_route_committed_plan(self) -> None:
        """CommittedPlan routes to _receive_plan (orphan -> FAILED)."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        plan = _make_plan(request_id="no-context")
        result = await svc.process(plan)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_route_workflow_run_request(self) -> None:
        """WorkflowRunRequest routes to _dispatch_workflow."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        req = _make_workflow_run_request()
        result = await svc.process(req)
        # WorkflowEngine with test adapters returns FAILED (no workflow stored)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_route_workflow_save_request(self) -> None:
        """WorkflowSaveRequest routes to _save_workflow."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        req = _make_workflow_save_request()
        result = await svc.process(req)
        # V1 save_workflow stub returns FAILED
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_route_interrupt_cancel_dag(self) -> None:
        """InterruptRequest with CANCEL_DAG returns CANCELLED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        req = _make_interrupt(interrupt_type="CANCEL_DAG")
        result = await svc.process(req)
        assert result == ProcessResult.CANCELLED

    @pytest.mark.asyncio
    async def test_unknown_message_type_returns_failed(self) -> None:
        """Unknown message type returns FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        result = await svc.process("not a real message")  # type: ignore[arg-type]
        assert result == ProcessResult.FAILED


# ===========================================================================
# Tests: _route_task() dispatch error handling
# ===========================================================================


class TestRouteTaskDispatchErrors:
    """Test error routing within _route_task catch block."""

    @pytest.mark.asyncio
    async def test_recoverable_adapter_error_requeues(self) -> None:
        """RECOVERABLE AdapterException -> requeue -> DEFERRED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise_qr(cap_name: str):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.RECOVERABLE,
                    adapter_name="fabric",
                    operation="query_registry",
                    error_code="UNAVAILABLE",
                    error_message="Registry unavailable",
                )
            )

        fabric.query_registry = _raise_qr  # type: ignore[assignment]

        envelope = _make_envelope(tier="MEDIUM")
        result = await svc.process(envelope)
        assert result == ProcessResult.DEFERRED
        assert len(mailbox.enqueued_log) == 1
        assert mailbox.enqueued_log[0][1] == "INTERACTIVE"

    @pytest.mark.asyncio
    async def test_degraded_adapter_error_returns_degraded(self) -> None:
        """DEGRADED AdapterException -> DEGRADED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise_qr(cap_name: str):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="fabric",
                    operation="query_registry",
                    error_code="PARTIAL",
                    error_message="Registry degraded",
                )
            )

        fabric.query_registry = _raise_qr  # type: ignore[assignment]

        envelope = _make_envelope(tier="MEDIUM")
        result = await svc.process(envelope)
        assert result == ProcessResult.DEGRADED

    @pytest.mark.asyncio
    async def test_terminal_adapter_error_returns_failed(self) -> None:
        """TERMINAL AdapterException -> FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise_qr(cap_name: str):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.TERMINAL,
                    adapter_name="fabric",
                    operation="query_registry",
                    error_code="UNAVAILABLE",
                    error_message="Registry down",
                )
            )

        fabric.query_registry = _raise_qr  # type: ignore[assignment]

        envelope = _make_envelope(tier="MEDIUM")
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_requeue_once_guard_prevents_infinite_retry(self) -> None:
        """Second requeue of same envelope returns FAILED (once guard)."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise_qr(cap_name: str):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.RECOVERABLE,
                    adapter_name="fabric",
                    operation="query_registry",
                    error_code="UNAVAILABLE",
                    error_message="Registry unavailable",
                )
            )

        fabric.query_registry = _raise_qr  # type: ignore[assignment]

        envelope = _make_envelope(tier="MEDIUM")
        result1 = await svc.process(envelope)
        assert result1 == ProcessResult.DEFERRED

        result2 = await svc.process(envelope)  # Same envelope -> once guard
        assert result2 == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_task_accepted_emitted_before_dispatch_error(self) -> None:
        """TASK_ACCEPTED event emitted before dispatch error."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise_qr(cap_name: str):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.TERMINAL,
                    adapter_name="fabric",
                    operation="query_registry",
                    error_code="UNAVAILABLE",
                    error_message="Registry down",
                )
            )

        fabric.query_registry = _raise_qr  # type: ignore[assignment]

        envelope = _make_envelope(tier="MEDIUM")
        await svc.process(envelope)

        accepted = delta.get_emitted(ORCH_TASK_ACCEPTED)
        assert len(accepted) == 1
        assert accepted[0]["envelope_id"] == envelope.envelope_id

    @pytest.mark.asyncio
    async def test_validation_failure_skips_task_accepted(self) -> None:
        """Validation failure returns FAILED without emitting TASK_ACCEPTED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        # Create invalid envelope bypassing __post_init__
        envelope = TaskEnvelope.__new__(TaskEnvelope)
        object.__setattr__(envelope, "intent", "")
        object.__setattr__(envelope, "trace_id", "t1")
        object.__setattr__(envelope, "tier", "MEDIUM")
        object.__setattr__(envelope, "capabilities", ["tool.test.a"])
        object.__setattr__(envelope, "envelope_id", "e1")
        object.__setattr__(envelope, "context", {})
        object.__setattr__(envelope, "params", {})
        object.__setattr__(envelope, "constraints", {})
        object.__setattr__(envelope, "timeout_ms", 30000)
        object.__setattr__(envelope, "caller_id", "")

        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED
        assert len(delta.get_emitted(ORCH_TASK_ACCEPTED)) == 0

    @pytest.mark.asyncio
    async def test_requeue_bounded_lru_eviction(self) -> None:
        """Requeued envelope IDs bounded to 100."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise_qr(cap_name: str):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.RECOVERABLE,
                    adapter_name="fabric",
                    operation="query_registry",
                    error_code="UNAVAILABLE",
                    error_message="Unavailable",
                )
            )

        fabric.query_registry = _raise_qr  # type: ignore[assignment]

        for _ in range(105):
            envelope = _make_envelope(tier="MEDIUM")
            await svc.process(envelope)

        assert len(svc.requeued_envelope_ids) == 100
        assert len(mailbox.enqueued_log) == 105

    @pytest.mark.asyncio
    async def test_requeue_uses_interactive_priority(self) -> None:
        """Re-enqueued messages use INTERACTIVE priority."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise_qr(cap_name: str):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.RECOVERABLE,
                    adapter_name="fabric",
                    operation="query_registry",
                    error_code="UNAVAILABLE",
                    error_message="Unavailable",
                )
            )

        fabric.query_registry = _raise_qr  # type: ignore[assignment]

        envelope = _make_envelope(tier="MEDIUM")
        await svc.process(envelope)

        assert len(mailbox.enqueued_log) == 1
        assert mailbox.enqueued_log[0][1] == "INTERACTIVE"


# ===========================================================================
# Tests: _dispatch_medium()
# ===========================================================================


class TestDispatchMedium:
    """Validate MEDIUM tier capability execution."""

    @pytest.mark.asyncio
    async def test_single_capability_success(self) -> None:
        """Single capability execution returns COMPLETED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        bridge: MockBridgeAdapter = svc._bridge_port  # type: ignore[assignment]
        _register_caps(fabric, "tool.test.a")

        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a"])
        result = await svc.process(envelope)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("tool.test.a")
        dag_completed = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert len(dag_completed) == 1
        bridge.assert_audit_written(1)

    @pytest.mark.asyncio
    async def test_batch_two_capabilities(self) -> None:
        """Two capabilities execute as batch."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a", "tool.test.b")

        envelope = _make_envelope(
            tier="MEDIUM",
            capabilities=["tool.test.a", "tool.test.b"],
        )
        result = await svc.process(envelope)

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("tool.test.a")
        fabric.assert_called("tool.test.b")

    @pytest.mark.asyncio
    async def test_capability_not_found_fails(self) -> None:
        """Unknown capability in registry returns FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        # Don't register "tool.unknown" -> query_registry returns None
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.unknown"])
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_safety_band_insufficient_fails(self) -> None:
        """Capability with insufficient safety_band returns FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        fabric.register_capability(
            "tool.test.a",
            RegistryEntry(
                name="tool.test.a",
                provider_type="tool",
                safety_band_min="RED",
                availability="AVAILABLE",
            ),
        )
        state.set_section("s1", "control", {"safety_band": "GREEN"})

        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a"])
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_fabric_execute_error_per_step(self) -> None:
        """AdapterException from execute() caught per-step -> FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a")
        fabric.script_error(
            "tool.test.a",
            AdapterError(
                severity=ErrorSeverity.DEGRADED,
                adapter_name="fabric",
                operation="execute",
                error_code="TIMEOUT",
                error_message="Fabric timeout",
            ),
        )

        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a"])
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED
        dag_completed = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert len(dag_completed) == 1
        assert dag_completed[0]["failed"] == 1

    @pytest.mark.asyncio
    async def test_partial_failure_returns_degraded(self) -> None:
        """One success + one failure result returns DEGRADED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a", "tool.test.b")
        fabric.script_result("tool.test.b", _failure_result("tool.test.b"))

        envelope = _make_envelope(
            tier="MEDIUM",
            capabilities=["tool.test.a", "tool.test.b"],
        )
        result = await svc.process(envelope)
        assert result == ProcessResult.DEGRADED

    @pytest.mark.asyncio
    async def test_per_step_isolation_first_fails_second_succeeds(self) -> None:
        """First step error, second succeeds -> DEGRADED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a", "tool.test.b")
        fabric.script_error(
            "tool.test.a",
            AdapterError(
                severity=ErrorSeverity.DEGRADED,
                adapter_name="fabric",
                operation="execute",
                error_code="TIMEOUT",
                error_message="Fabric timeout",
            ),
        )
        # tool.test.b uses default (generic success)

        envelope = _make_envelope(
            tier="MEDIUM",
            capabilities=["tool.test.a", "tool.test.b"],
        )
        result = await svc.process(envelope)

        assert result == ProcessResult.DEGRADED
        assert len(fabric.call_log) == 2
        dag_completed = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert len(dag_completed) == 1
        assert dag_completed[0]["failed"] == 1
        assert dag_completed[0]["completed"] == 1

    @pytest.mark.asyncio
    async def test_per_step_isolation_second_fails_first_succeeds(self) -> None:
        """Second step error, first succeeds -> DEGRADED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a", "tool.test.b")
        fabric.script_error(
            "tool.test.b",
            AdapterError(
                severity=ErrorSeverity.DEGRADED,
                adapter_name="fabric",
                operation="execute",
                error_code="ERR",
                error_message="Error",
            ),
        )

        envelope = _make_envelope(
            tier="MEDIUM",
            capabilities=["tool.test.a", "tool.test.b"],
        )
        result = await svc.process(envelope)

        assert result == ProcessResult.DEGRADED
        assert len(fabric.call_log) == 2

    @pytest.mark.asyncio
    async def test_per_step_isolation_both_fail_returns_failed(self) -> None:
        """Both steps error -> all FAILED -> FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a", "tool.test.b")
        for cap in ("tool.test.a", "tool.test.b"):
            fabric.script_error(
                cap,
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="fabric",
                    operation="execute",
                    error_code="ERR",
                    error_message="Error",
                ),
            )

        envelope = _make_envelope(
            tier="MEDIUM",
            capabilities=["tool.test.a", "tool.test.b"],
        )
        result = await svc.process(envelope)

        assert result == ProcessResult.FAILED
        # Both steps still attempted (isolation, not short-circuit)
        assert len(fabric.call_log) == 2

    @pytest.mark.asyncio
    async def test_orch10_empty_capabilities_fails(self) -> None:
        """ORCH-10: empty capabilities list returns FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        envelope = TaskEnvelope.__new__(TaskEnvelope)
        object.__setattr__(envelope, "intent", "test")
        object.__setattr__(envelope, "trace_id", str(uuid4()))
        object.__setattr__(envelope, "tier", "MEDIUM")
        object.__setattr__(envelope, "capabilities", [])
        object.__setattr__(envelope, "envelope_id", str(uuid4()))
        object.__setattr__(envelope, "context", {"session_id": "s1"})
        object.__setattr__(envelope, "params", {})
        object.__setattr__(envelope, "constraints", {})
        object.__setattr__(envelope, "timeout_ms", 30000)
        object.__setattr__(envelope, "caller_id", "")

        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_orch10_three_capabilities_fails(self) -> None:
        """ORCH-10: more than 2 capabilities returns FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        envelope = TaskEnvelope.__new__(TaskEnvelope)
        object.__setattr__(envelope, "intent", "test")
        object.__setattr__(envelope, "trace_id", str(uuid4()))
        object.__setattr__(envelope, "tier", "MEDIUM")
        object.__setattr__(envelope, "capabilities", ["a", "b", "c"])
        object.__setattr__(envelope, "envelope_id", str(uuid4()))
        object.__setattr__(envelope, "context", {"session_id": "s1"})
        object.__setattr__(envelope, "params", {})
        object.__setattr__(envelope, "constraints", {})
        object.__setattr__(envelope, "timeout_ms", 30000)
        object.__setattr__(envelope, "caller_id", "")

        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_step_error_detail_captures_adapter_message(self) -> None:
        """Per-step AdapterException error_message is captured in StepResult."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a")
        fabric.script_error(
            "tool.test.a",
            AdapterError(
                severity=ErrorSeverity.DEGRADED,
                adapter_name="fabric",
                operation="execute",
                error_code="TIMEOUT",
                error_message="Fabric timeout",
            ),
        )

        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a"])
        await svc.process(envelope)

        dag_completed = delta.get_emitted(ORCH_DAG_COMPLETED)
        step_results = dag_completed[0]["step_results"]
        assert len(step_results) == 1
        assert step_results[0]["status"] == "FAILED"
        assert step_results[0]["error_detail"] == "Fabric timeout"

    @pytest.mark.asyncio
    async def test_dag_completed_emitted_on_success(self) -> None:
        """DAG_COMPLETED delta emitted on successful execution."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a")

        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a"])
        await svc.process(envelope)

        delta.assert_emitted(ORCH_DAG_COMPLETED, 1)
        dag = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert dag[0]["completed"] == 1
        assert dag[0]["success"] is True


# ===========================================================================
# Tests: _dispatch_high() -- Phase 1
# ===========================================================================


class TestDispatchHigh:
    """Validate HIGH tier plan request flow."""

    @pytest.mark.asyncio
    async def test_successful_plan_request_returns_deferred(self) -> None:
        """Plan accepted by Planner returns DEFERRED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)

        assert result == ProcessResult.DEFERRED
        assert len(svc.pending_plans) == 1
        planner.assert_plan_requested(1)

    @pytest.mark.asyncio
    async def test_plan_rejected_returns_failed(self) -> None:
        """Plan rejected by Planner returns FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        # Monkey-patch planner to always reject
        async def _reject(req):
            planner.request_log.append(req)
            return PlanAck(request_id=req.request_id, status="REJECTED")

        planner.request_plan = _reject  # type: ignore[assignment]

        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_planner_unreachable_returns_failed(self) -> None:
        """AdapterException from Planner returns FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise(req):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.TERMINAL,
                    adapter_name="planner",
                    operation="request_plan",
                    error_code="UNAVAILABLE",
                    error_message="Planner unreachable",
                )
            )

        planner.request_plan = _raise  # type: ignore[assignment]

        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_pending_plans_limit_exceeded(self) -> None:
        """Exceeding max_pending_plans returns FAILED and cancels."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        # Manually set a tight config
        svc._config = OrchestratorConfig.from_dict(
            {
                "admin_enabled": False,
                "max_pending_plans": 1,
            }
        )
        # Fill up the pending_plans
        svc._pending_plans["existing"] = PendingPlanContext(
            request_id="existing",
            task_envelope=_make_envelope(tier="HIGH"),
            state_snapshot=SessionSnapshot(session_id="s1"),
        )

        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED
        assert len(planner.cancel_log) == 1

    @pytest.mark.asyncio
    async def test_request_id_echoed_in_pending_context(self) -> None:
        """PendingPlanContext stores the request_id sent to Planner."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        envelope = _make_envelope(tier="HIGH")
        await svc.process(envelope)

        assert len(planner.request_log) == 1
        sent_request_id = planner.request_log[0].request_id
        assert sent_request_id in svc.pending_plans
        assert svc.pending_plans[sent_request_id].request_id == sent_request_id

    @pytest.mark.asyncio
    async def test_state_snapshot_failure_still_sends_plan(self) -> None:
        """Snapshot failure should not block plan request."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise_snapshot(session_id: str):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="state_read",
                    operation="get_snapshot",
                    error_code="UNAVAILABLE",
                    error_message="State unavailable",
                )
            )

        state.get_snapshot = _raise_snapshot  # type: ignore[assignment]

        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)
        assert result == ProcessResult.DEFERRED
        planner.assert_plan_requested(1)

    @pytest.mark.asyncio
    async def test_plan_requested_event_emitted_with_fields(self) -> None:
        """PLAN_REQUESTED event includes request_id, intent, tier, trace_id."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        envelope = _make_envelope(tier="HIGH", intent="book flight")
        result = await svc.process(envelope)

        assert result == ProcessResult.DEFERRED
        plan_events = delta.get_emitted(ORCH_PLAN_REQUESTED)
        assert len(plan_events) == 1
        payload = plan_events[0]
        assert payload["intent"] == "book flight"
        assert payload["tier"] == "HIGH"
        assert "request_id" in payload
        assert "trace_id" in payload

    @pytest.mark.asyncio
    async def test_plan_request_uses_config_timeout(self) -> None:
        """PlanRequest.timeout_ms comes from OrchestratorConfig."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        svc._config = OrchestratorConfig.from_dict(
            {
                "admin_enabled": False,
                "plan_request_timeout_ms": 99000,
            }
        )

        envelope = _make_envelope(tier="HIGH")
        await svc.process(envelope)

        assert len(planner.request_log) == 1
        assert planner.request_log[0].timeout_ms == 99000

    @pytest.mark.asyncio
    async def test_pending_context_stores_envelope_and_snapshot(self) -> None:
        """PendingPlanContext holds the original TaskEnvelope."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        envelope = _make_envelope(tier="HIGH", intent="complex task")
        await svc.process(envelope)

        assert len(svc.pending_plans) == 1
        ctx = list(svc.pending_plans.values())[0]
        assert ctx.task_envelope is envelope

    @pytest.mark.asyncio
    async def test_plan_request_carries_envelope_constraints(self) -> None:
        """PlanRequest.constraints populated from envelope.constraints."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        envelope = TaskEnvelope(
            intent="constrained task",
            trace_id=str(uuid4()),
            tier="HIGH",
            capabilities=[],
            params={},
            context={"session_id": "s1"},
            constraints={"max_steps": 3, "region": "US"},
        )
        await svc.process(envelope)

        assert len(planner.request_log) == 1
        pr = planner.request_log[0]
        assert pr.constraints == {"max_steps": 3, "region": "US"}
        assert pr.intent == "constrained task"


# ===========================================================================
# Tests: _receive_plan() -- Phase 2
# ===========================================================================


class TestReceivePlan:
    """Validate CommittedPlan execution flow."""

    def _park_plan(
        self,
        svc: OrchestratorService,
        request_id: str,
        envelope: Optional[TaskEnvelope] = None,
    ) -> None:
        """Helper: park a PendingPlanContext with the given request_id."""
        svc._pending_plans[request_id] = PendingPlanContext(
            request_id=request_id,
            task_envelope=envelope or _make_envelope(tier="HIGH"),
            state_snapshot=SessionSnapshot(session_id="s1"),
        )

    @pytest.mark.asyncio
    async def test_successful_plan_execution(self) -> None:
        """Valid plan with parked context executes and returns COMPLETED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        bridge: MockBridgeAdapter = svc._bridge_port  # type: ignore[assignment]
        _register_caps(fabric, "tool.test.a")

        plan = _make_plan(request_id="req1")
        self._park_plan(svc, "req1")
        result = await svc.process(plan)

        assert result == ProcessResult.COMPLETED
        # DAGExecutor emits DAG_COMPLETED + audit internally,
        # then _receive_plan._emit_result emits again -> 2 each.
        dag_events = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert len(dag_events) >= 1
        assert len(bridge.audit_log) >= 1

    @pytest.mark.asyncio
    async def test_race3_duplicate_plan_returns_completed(self) -> None:
        """RACE-3: plan_id already in executed_plans -> COMPLETED (dedup)."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        plan = _make_plan(plan_id="dup-plan", request_id="req1")
        self._park_plan(svc, "req1")
        svc._executed_plans["dup-plan"] = time.time()
        result = await svc.process(plan)
        assert result == ProcessResult.COMPLETED

    @pytest.mark.asyncio
    async def test_race2_orphan_plan_returns_failed(self) -> None:
        """RACE-2: request_id not in pending_plans -> FAILED (orphan)."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        plan = _make_plan(request_id="nonexistent")
        result = await svc.process(plan)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_constraint_validation_failure(self) -> None:
        """Invalid plan per ConstraintResolver returns FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        # Don't register capability -> ConstraintResolver.validate() will fail
        plan = _make_plan(
            request_id="req1",
            steps=[PlanStep(id="s1", capability="tool.nonexistent", params={}, deps=[])],
        )
        self._park_plan(svc, "req1")
        result = await svc.process(plan)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_concurrency_guard_rejected(self) -> None:
        """ConcurrencyGuard rejection returns DEFERRED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a")
        # Pre-acquire the lock so next acquire returns False
        await svc._concurrency_guard.acquire()

        plan = _make_plan(request_id="req1")
        self._park_plan(svc, "req1")
        result = await svc.process(plan)
        assert result == ProcessResult.DEFERRED

        # Release for cleanup
        svc._concurrency_guard.release()

    @pytest.mark.asyncio
    async def test_executed_plans_lru_records(self) -> None:
        """Plan execution records plan_id in executed_plans LRU."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a")
        plan = _make_plan(plan_id="plan-abc", request_id="req1")
        self._park_plan(svc, "req1")
        await svc.process(plan)
        assert "plan-abc" in svc.executed_plans


# ===========================================================================
# Tests: receive_plan_failed() / receive_plan_cancelled()
# ===========================================================================


class TestPlanFailureHandlers:
    """Validate plan failure and cancellation handling."""

    @pytest.mark.asyncio
    async def test_plan_failed_with_pending_context(self) -> None:
        """Plan failure pops pending context and returns FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        svc._pending_plans["req1"] = PendingPlanContext(
            request_id="req1",
            task_envelope=_make_envelope(tier="HIGH"),
            state_snapshot=SessionSnapshot(session_id="s1"),
        )

        result = await svc.receive_plan_failed(
            request_id="req1",
            reason="TIMEOUT",
            error_detail="Planner timed out",
            trace_id="t1",
        )

        assert result == ProcessResult.FAILED
        assert "req1" not in svc.pending_plans
        delta.assert_emitted(ORCH_DAG_COMPLETED, 1)

    @pytest.mark.asyncio
    async def test_plan_failed_no_context(self) -> None:
        """Plan failure with unknown request_id still returns FAILED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        result = await svc.receive_plan_failed(
            request_id="unknown",
            reason="UNKNOWN",
            error_detail=None,
            trace_id="t1",
        )
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_plan_cancelled_with_context(self) -> None:
        """Plan cancellation pops pending context, returns CANCELLED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        svc._pending_plans["req1"] = PendingPlanContext(
            request_id="req1",
            task_envelope=_make_envelope(tier="HIGH"),
            state_snapshot=SessionSnapshot(session_id="s1"),
        )
        result = await svc.receive_plan_cancelled(request_id="req1", trace_id="t1")
        assert result == ProcessResult.CANCELLED
        assert "req1" not in svc.pending_plans

    @pytest.mark.asyncio
    async def test_plan_cancelled_no_context(self) -> None:
        """Plan cancellation with unknown request_id returns CANCELLED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        result = await svc.receive_plan_cancelled(request_id="nope", trace_id="t1")
        assert result == ProcessResult.CANCELLED


# ===========================================================================
# Tests: _dispatch_workflow() / _save_workflow()
# ===========================================================================


class TestWorkflow:
    """Validate workflow dispatch and save."""

    @pytest.mark.asyncio
    async def test_dispatch_workflow_success(self) -> None:
        """Workflow execution via monkey-patched engine returns COMPLETED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _execute(request, ctx):
            return ProcessResult.COMPLETED

        svc._workflow_engine = _StubWorkflowEngine(execute=_execute)

        req = _make_workflow_run_request()
        result = await svc.process(req)
        assert result == ProcessResult.COMPLETED

    @pytest.mark.asyncio
    async def test_dispatch_workflow_concurrency_rejected(self) -> None:
        """ConcurrencyGuard rejection defers workflow."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        await svc._concurrency_guard.acquire()

        req = _make_workflow_run_request()
        result = await svc.process(req)
        assert result == ProcessResult.DEFERRED

        svc._concurrency_guard.release()

    @pytest.mark.asyncio
    async def test_save_workflow_success(self) -> None:
        """Workflow save returns COMPLETED and emits delta."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _save(request, ctx):
            return ProcessResult.COMPLETED

        svc._workflow_engine = _StubWorkflowEngine(save=_save)

        req = _make_workflow_save_request()
        result = await svc.process(req)
        assert result == ProcessResult.COMPLETED
        saved = delta.get_emitted(ORCH_WORKFLOW_SAVED)
        assert len(saved) == 1
        assert saved[0]["committed_plan_id"] == req.committed_plan_id

    @pytest.mark.asyncio
    async def test_save_workflow_engine_error(self) -> None:
        """AdapterException in save_workflow returns classified result."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise_save(request, ctx):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="workflow_engine",
                    operation="save_workflow",
                    error_code="STORAGE",
                    error_message="Failed to save",
                )
            )

        svc._workflow_engine = _StubWorkflowEngine(save=_raise_save)

        req = _make_workflow_save_request()
        result = await svc.process(req)
        assert result == ProcessResult.DEGRADED


# ===========================================================================
# Tests: _handle_interrupt()
# ===========================================================================


class TestHandleInterrupt:
    """Validate interrupt handling."""

    @pytest.mark.asyncio
    async def test_cancel_dag_returns_cancelled(self) -> None:
        """CANCEL_DAG interrupt returns CANCELLED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        req = _make_interrupt(interrupt_type="CANCEL_DAG")
        result = await svc.process(req)
        assert result == ProcessResult.CANCELLED

    @pytest.mark.asyncio
    async def test_pause_rejected_in_v1(self) -> None:
        """PAUSE interrupt returns FAILED in V1."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        req = _make_interrupt(interrupt_type="PAUSE")
        result = await svc.process(req)
        assert result == ProcessResult.FAILED


# ===========================================================================
# Tests: reap_stale_contexts()
# ===========================================================================


class TestReapStaleContexts:
    """Validate timeout reaping for pending plans and HIL."""

    @pytest.mark.asyncio
    async def test_reap_expired_plan_context(self) -> None:
        """Expired PendingPlanContext is reaped and Planner cancel sent."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        svc._pending_plans["exp1"] = PendingPlanContext(
            request_id="exp1",
            task_envelope=_make_envelope(tier="HIGH"),
            state_snapshot=SessionSnapshot(session_id="s1"),
            created_at=time.time() - 60,
            timeout_ms=1000,
        )

        reaped = await svc.reap_stale_contexts()
        assert reaped == 1
        assert "exp1" not in svc.pending_plans
        assert len(planner.cancel_log) == 1
        delta.assert_emitted(ORCH_DAG_COMPLETED, 1)

    @pytest.mark.asyncio
    async def test_reap_does_not_touch_active_context(self) -> None:
        """Active (non-expired) PendingPlanContext is not reaped."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        svc._pending_plans["active1"] = PendingPlanContext(
            request_id="active1",
            task_envelope=_make_envelope(tier="HIGH"),
            state_snapshot=SessionSnapshot(session_id="s1"),
            created_at=time.time(),
            timeout_ms=60_000,
        )

        reaped = await svc.reap_stale_contexts()
        assert reaped == 0
        assert "active1" in svc.pending_plans

    @pytest.mark.asyncio
    async def test_reap_expired_hil_context(self) -> None:
        """Expired PendingHILContext is reaped."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        svc._pending_hil["hil1"] = PendingHILContext(
            request_id="hil1",
            dag_execution_id="dag-1",
            current_wave_index=0,
            completed_waves=[],
            remaining_waves=[],
            question="Continue?",
            options=["yes", "no"],
            timeout_fallback="GRACEFUL_FAIL",
            created_at=time.time() - 300,
            timeout_ms=1000,
        )

        reaped = await svc.reap_stale_contexts()
        assert reaped == 1
        assert "hil1" not in svc.pending_hil

    @pytest.mark.asyncio
    async def test_reap_multiple_types(self) -> None:
        """Both plan + HIL contexts reaped in single call."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        svc._pending_plans["p1"] = PendingPlanContext(
            request_id="p1",
            task_envelope=_make_envelope(tier="HIGH"),
            state_snapshot=SessionSnapshot(session_id="s1"),
            created_at=time.time() - 60,
            timeout_ms=100,
        )
        svc._pending_hil["h1"] = PendingHILContext(
            request_id="h1",
            dag_execution_id="dag-1",
            current_wave_index=0,
            completed_waves=[],
            remaining_waves=[],
            question="?",
            options=[],
            timeout_fallback="CONTINUE",
            created_at=time.time() - 60,
            timeout_ms=100,
        )

        reaped = await svc.reap_stale_contexts()
        assert reaped == 2


# ===========================================================================
# Tests: _build_context()
# ===========================================================================


class TestBuildContext:
    """Validate ProcessingContext construction per message type."""

    @pytest.mark.asyncio
    async def test_task_envelope_context(self) -> None:
        """TaskEnvelope extracts trace_id, envelope_id, tier."""
        svc, *_ = await _svc()
        envelope = _make_envelope(tier="MEDIUM", trace_id="trace-1")
        ctx = svc._build_context(envelope)

        assert ctx.trace_id == "trace-1"
        assert ctx.request_id == envelope.envelope_id
        assert ctx.tier == "MEDIUM"

    @pytest.mark.asyncio
    async def test_committed_plan_context(self) -> None:
        """CommittedPlan extracts trace_id, request_id, tier=HIGH."""
        svc, *_ = await _svc()
        plan = _make_plan(trace_id="trace-2", request_id="req-2")
        ctx = svc._build_context(plan)

        assert ctx.trace_id == "trace-2"
        assert ctx.request_id == "req-2"
        assert ctx.tier == "HIGH"

    @pytest.mark.asyncio
    async def test_workflow_run_context(self) -> None:
        """WorkflowRunRequest extracts trace_id, tier=WORKFLOW."""
        svc, *_ = await _svc()
        req = _make_workflow_run_request(trace_id="trace-3")
        ctx = svc._build_context(req)

        assert ctx.trace_id == "trace-3"
        assert ctx.tier == "WORKFLOW"

    @pytest.mark.asyncio
    async def test_interrupt_context(self) -> None:
        """InterruptRequest extracts tier=REALTIME."""
        svc, *_ = await _svc()
        req = _make_interrupt(trace_id="trace-4")
        ctx = svc._build_context(req)

        assert ctx.trace_id == "trace-4"
        assert ctx.tier == "REALTIME"

    @pytest.mark.asyncio
    async def test_missing_trace_id_generates_fallback(self) -> None:
        """Message without trace_id gets a generated uuid."""
        svc, *_ = await _svc()
        ctx = svc._build_context("something weird")  # type: ignore[arg-type]
        assert ctx.trace_id  # Non-empty
        assert ctx.request_id  # Non-empty


# ===========================================================================
# Tests: _record_executed_plan() LRU
# ===========================================================================


class TestRecordExecutedPlan:
    """Validate bounded LRU eviction for executed_plans."""

    @pytest.mark.asyncio
    async def test_records_plan_id(self) -> None:
        """Recording a plan_id adds it to executed_plans."""
        svc, *_ = await _svc()
        svc._record_executed_plan("plan-1")
        assert "plan-1" in svc.executed_plans

    @pytest.mark.asyncio
    async def test_lru_eviction_at_capacity(self) -> None:
        """Oldest entry evicted when exceeding 100."""
        svc, *_ = await _svc()
        for i in range(100):
            svc._record_executed_plan(f"plan-{i}")
        assert len(svc.executed_plans) == 100
        assert "plan-0" in svc.executed_plans

        svc._record_executed_plan("plan-100")
        assert len(svc.executed_plans) == 100
        assert "plan-0" not in svc.executed_plans
        assert "plan-100" in svc.executed_plans

    @pytest.mark.asyncio
    async def test_move_to_end_on_rerecord(self) -> None:
        """Re-recording an existing plan_id moves it to end (LRU)."""
        svc, *_ = await _svc()
        svc._record_executed_plan("a")
        svc._record_executed_plan("b")
        svc._record_executed_plan("a")

        keys = list(svc.executed_plans.keys())
        assert keys[-1] == "a"


# ===========================================================================
# Tests: _handle_adapter_error()
# ===========================================================================


class TestHandleAdapterError:
    """Validate error severity to ProcessResult mapping."""

    @staticmethod
    def _make_exc(severity: ErrorSeverity) -> AdapterException:
        return AdapterException(
            AdapterError(
                severity=severity,
                adapter_name="test",
                operation="op",
                error_code="ERR",
                error_message="fail",
            )
        )

    @pytest.mark.asyncio
    async def test_terminal_returns_failed(self) -> None:
        """TERMINAL severity maps to FAILED."""
        svc, *_ = await _svc()
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
        result = svc._handle_adapter_error(self._make_exc(ErrorSeverity.TERMINAL), ctx)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_degraded_returns_degraded(self) -> None:
        """DEGRADED severity maps to DEGRADED."""
        svc, *_ = await _svc()
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
        result = svc._handle_adapter_error(self._make_exc(ErrorSeverity.DEGRADED), ctx)
        assert result == ProcessResult.DEGRADED

    @pytest.mark.asyncio
    async def test_recoverable_returns_deferred(self) -> None:
        """RECOVERABLE severity maps to DEFERRED."""
        svc, *_ = await _svc()
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
        result = svc._handle_adapter_error(self._make_exc(ErrorSeverity.RECOVERABLE), ctx)
        assert result == ProcessResult.DEFERRED


# ===========================================================================
# Tests: _result_to_process_result()
# ===========================================================================


class TestResultToProcessResult:
    """Validate AggregatedResult -> ProcessResult mapping."""

    def test_all_completed_is_completed(self) -> None:
        """All steps completed -> COMPLETED."""
        result = AggregatedResult.from_medium(
            step_results=[
                StepResult(step_id="s1", capability_name="a", status=StepStatus.COMPLETED)
            ],
            trace_id="t1",
        )
        assert OrchestratorService._result_to_process_result(result) == ProcessResult.COMPLETED

    def test_all_cancelled_is_cancelled(self) -> None:
        """All steps cancelled -> CANCELLED."""
        result = AggregatedResult(
            total_steps=1,
            completed=0,
            failed=0,
            cancelled=1,
            skipped=0,
            step_results=[
                StepResult(step_id="s1", capability_name="a", status=StepStatus.CANCELLED)
            ],
            success=False,
            duration_ms=0,
            trace_id="t1",
        )
        assert OrchestratorService._result_to_process_result(result) == ProcessResult.CANCELLED

    def test_mixed_success_failure_is_degraded(self) -> None:
        """Some completed + some failed -> DEGRADED."""
        result = AggregatedResult(
            total_steps=2,
            completed=1,
            failed=1,
            cancelled=0,
            skipped=0,
            step_results=[
                StepResult(step_id="s1", capability_name="a", status=StepStatus.COMPLETED),
                StepResult(step_id="s2", capability_name="b", status=StepStatus.FAILED),
            ],
            success=False,
            duration_ms=0,
            trace_id="t1",
        )
        assert OrchestratorService._result_to_process_result(result) == ProcessResult.DEGRADED

    def test_all_failed_is_failed(self) -> None:
        """All steps failed -> FAILED."""
        result = AggregatedResult(
            total_steps=1,
            completed=0,
            failed=1,
            cancelled=0,
            skipped=0,
            step_results=[StepResult(step_id="s1", capability_name="a", status=StepStatus.FAILED)],
            success=False,
            duration_ms=0,
            trace_id="t1",
        )
        assert OrchestratorService._result_to_process_result(result) == ProcessResult.FAILED

    def test_empty_result_is_completed(self) -> None:
        """Empty result (no steps) -> COMPLETED (success=True)."""
        result = AggregatedResult.from_medium(step_results=[], trace_id="t1")
        assert OrchestratorService._result_to_process_result(result) == ProcessResult.COMPLETED


# ===========================================================================
# Tests: aggregate() -- Pure aggregation (Issue 2.1.5)
# ===========================================================================


class TestAggregate:
    """Validate aggregate() pure function (2.1.5)."""

    @pytest.mark.asyncio
    async def test_medium_no_plan_id_uses_from_medium(self) -> None:
        """plan_id=None delegates to AggregatedResult.from_medium()."""
        svc, *_ = await _svc()
        step_results = [
            StepResult(step_id="s1", capability_name="a", status=StepStatus.COMPLETED),
        ]
        result = svc.aggregate(step_results, None, [], "t1", 100)
        assert result.plan_id is None
        assert result.success is True
        assert result.total_steps == 1
        assert result.completed == 1
        assert result.duration_ms == 100

    @pytest.mark.asyncio
    async def test_high_with_plan_id_uses_from_dag(self) -> None:
        """plan_id set delegates to AggregatedResult.from_dag()."""
        svc, *_ = await _svc()
        step_results = [
            StepResult(step_id="s1", capability_name="a", status=StepStatus.COMPLETED),
            StepResult(
                step_id="s2", capability_name="b", status=StepStatus.FAILED, error_detail="err"
            ),
        ]
        comp = CompensationRecord(
            dag_id="d1",
            step_id="s2",
            compensation_capability="rollback.b",
        )
        result = svc.aggregate(step_results, "plan-1", [comp], "t1", 500)
        assert result.plan_id == "plan-1"
        assert result.success is False
        assert result.failed == 1
        assert result.completed == 1
        assert len(result.compensations) == 1
        assert result.compensations[0].compensation_capability == "rollback.b"

    @pytest.mark.asyncio
    async def test_empty_steps_succeeds(self) -> None:
        """Empty step_results -> success=True."""
        svc, *_ = await _svc()
        result = svc.aggregate([], None, [], "t1")
        assert result.success is True
        assert result.total_steps == 0

    @pytest.mark.asyncio
    async def test_all_cancelled_no_success(self) -> None:
        """All cancelled -> success=False."""
        svc, *_ = await _svc()
        step_results = [
            StepResult(step_id="s1", capability_name="a", status=StepStatus.CANCELLED),
        ]
        result = svc.aggregate(step_results, None, [], "t1")
        assert result.success is False
        assert result.cancelled == 1

    @pytest.mark.asyncio
    async def test_pure_function_no_side_effects(self) -> None:
        """aggregate() does not emit events or modify service state."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        bridge: MockBridgeAdapter = svc._bridge_port  # type: ignore[assignment]
        svc.aggregate(
            [StepResult(step_id="s1", capability_name="a", status=StepStatus.COMPLETED)],
            None,
            [],
            "t1",
            10,
        )
        # No events emitted -- aggregate is pure.
        assert len(delta.emitted) == 0
        assert len(bridge.audit_log) == 0

    @pytest.mark.asyncio
    async def test_trace_id_propagated(self) -> None:
        """trace_id is propagated to AggregatedResult."""
        svc, *_ = await _svc()
        result = svc.aggregate([], None, [], "trace-xyz")
        assert result.trace_id == "trace-xyz"

    @pytest.mark.asyncio
    async def test_duration_ms_propagated(self) -> None:
        """duration_ms is propagated to AggregatedResult."""
        svc, *_ = await _svc()
        result = svc.aggregate([], None, [], "t1", 12345)
        assert result.duration_ms == 12345

    @pytest.mark.asyncio
    async def test_dag_with_compensations_and_skipped(self) -> None:
        """HIGH tier aggregate with mixed statuses and compensations."""
        svc, *_ = await _svc()
        step_results = [
            StepResult(step_id="s1", capability_name="a", status=StepStatus.COMPLETED),
            StepResult(
                step_id="s2", capability_name="b", status=StepStatus.FAILED, error_detail="timeout"
            ),
            StepResult(step_id="s3", capability_name="c", status=StepStatus.SKIPPED),
        ]
        comps = [
            CompensationRecord(dag_id="d1", step_id="s2", compensation_capability="undo.b"),
        ]
        result = svc.aggregate(step_results, "plan-77", comps, "t1", 1000)
        assert result.total_steps == 3
        assert result.completed == 1
        assert result.failed == 1
        assert result.skipped == 1
        assert result.success is False
        assert result.plan_id == "plan-77"


# ===========================================================================
# Tests: _save_workflow() expanded (Issue 2.1.6)
# ===========================================================================


class TestSaveWorkflowExpanded:
    """Validate expanded save_workflow with delta emission (2.1.6)."""

    @pytest.mark.asyncio
    async def test_save_emits_workflow_saved_delta(self) -> None:
        """Successful save emits ORCH_WORKFLOW_SAVED delta."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _save_ok(request, ctx):
            return ProcessResult.COMPLETED

        svc._workflow_engine = _StubWorkflowEngine(save=_save_ok)

        req = _make_workflow_save_request()
        result = await svc.process(req)
        assert result == ProcessResult.COMPLETED
        saved_events = delta.get_emitted(ORCH_WORKFLOW_SAVED)
        assert len(saved_events) == 1
        payload = saved_events[0]
        assert payload["committed_plan_id"] == req.committed_plan_id
        assert payload["workflow_name"] == req.workflow_name
        assert "trigger_type" in payload
        assert "trace_id" in payload

    @pytest.mark.asyncio
    async def test_save_failure_no_delta(self) -> None:
        """Failed save does NOT emit ORCH_WORKFLOW_SAVED delta."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _save_fail(request, ctx):
            return ProcessResult.FAILED

        svc._workflow_engine = _StubWorkflowEngine(save=_save_fail)

        req = _make_workflow_save_request()
        result = await svc.process(req)
        assert result == ProcessResult.FAILED
        assert len(delta.get_emitted(ORCH_WORKFLOW_SAVED)) == 0

    @pytest.mark.asyncio
    async def test_save_adapter_error_no_delta(self) -> None:
        """AdapterException from engine does NOT emit delta."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise_save(request, ctx):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="workflow_engine",
                    operation="save_workflow",
                    error_code="STORAGE",
                    error_message="Failed to save",
                )
            )

        svc._workflow_engine = _StubWorkflowEngine(save=_raise_save)

        req = _make_workflow_save_request()
        result = await svc.process(req)
        assert result == ProcessResult.DEGRADED
        assert len(delta.get_emitted(ORCH_WORKFLOW_SAVED)) == 0

    @pytest.mark.asyncio
    async def test_save_delta_contains_trigger_type(self) -> None:
        """ORCH_WORKFLOW_SAVED delta payload includes trigger_type."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _save_ok(request, ctx):
            return ProcessResult.COMPLETED

        svc._workflow_engine = _StubWorkflowEngine(save=_save_ok)

        req = _make_workflow_save_request()
        await svc.process(req)

        saved = delta.get_emitted(ORCH_WORKFLOW_SAVED)
        assert saved[0]["trigger_type"] == "MANUAL"


# ===========================================================================
# Tests: AdapterException
# ===========================================================================


class TestAdapterException:
    """Validate AdapterException wraps AdapterError correctly."""

    def test_wraps_adapter_error_fields(self) -> None:
        """All AdapterError fields delegated to exception."""
        detail = AdapterError(
            severity=ErrorSeverity.DEGRADED,
            adapter_name="fabric",
            operation="execute",
            error_code="TIMEOUT",
            error_message="Request timed out",
            trace_id="t1",
        )
        exc = AdapterException(detail)

        assert exc.detail is detail
        assert exc.adapter_name == "fabric"
        assert exc.operation == "execute"
        assert exc.error_code == "TIMEOUT"
        assert exc.error_message == "Request timed out"
        assert exc.severity == ErrorSeverity.DEGRADED
        assert exc.trace_id == "t1"
        assert str(exc) == "Request timed out"

    def test_is_exception_subclass(self) -> None:
        """AdapterException is a proper Exception."""
        exc = AdapterException(
            AdapterError(
                severity=ErrorSeverity.RECOVERABLE,
                adapter_name="test",
                operation="op",
                error_code="E",
                error_message="msg",
            )
        )
        assert isinstance(exc, Exception)

    def test_catchable_in_try_except(self) -> None:
        """AdapterException can be caught with except."""
        with pytest.raises(AdapterException):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.TERMINAL,
                    adapter_name="test",
                    operation="op",
                    error_code="E",
                    error_message="boom",
                )
            )


# ===========================================================================
# Tests: Properties
# ===========================================================================


class TestServiceProperties:
    """Test read-only property accessors."""

    @pytest.mark.asyncio
    async def test_pending_plans_initially_empty(self) -> None:
        svc, *_ = await _svc()
        assert svc.pending_plans == {}

    @pytest.mark.asyncio
    async def test_pending_hil_initially_empty(self) -> None:
        svc, *_ = await _svc()
        assert svc.pending_hil == {}

    @pytest.mark.asyncio
    async def test_executed_plans_initially_empty(self) -> None:
        svc, *_ = await _svc()
        assert len(svc.executed_plans) == 0

    @pytest.mark.asyncio
    async def test_config_returns_injected_config(self) -> None:
        svc, *_ = await _svc()
        assert svc.config is not None
        assert hasattr(svc.config, "max_pending_plans")


# ===========================================================================
# Tests: Edge cases and integration
# ===========================================================================


class TestEdgeCases:
    """Edge cases and full flow integration tests."""

    @pytest.mark.asyncio
    async def test_process_catches_uncaught_exception(self) -> None:
        """Unhandled exception in dispatch returns FAILED (never crashes)."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _explode(request, ctx):
            raise RuntimeError("Unexpected boom")

        svc._workflow_engine = _StubWorkflowEngine(execute=_explode)

        req = _make_workflow_run_request()
        result = await svc.process(req)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_full_high_tier_flow_dispatch_then_receive(self) -> None:
        """Full two-phase flow: dispatch_high -> receive_plan -> COMPLETED."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()
        _register_caps(fabric, "tool.test.a")

        # Phase 1: dispatch_high
        envelope = _make_envelope(tier="HIGH")
        result1 = await svc.process(envelope)
        assert result1 == ProcessResult.DEFERRED
        assert len(svc.pending_plans) == 1

        # Extract the request_id that was sent
        sent_request_id = planner.request_log[0].request_id

        # Phase 2: receive_plan
        plan = _make_plan(request_id=sent_request_id)
        result2 = await svc.process(plan)
        assert result2 == ProcessResult.COMPLETED
        assert len(svc.pending_plans) == 0
        assert plan.plan_id in svc.executed_plans

    @pytest.mark.asyncio
    async def test_adapter_error_caught_in_process(self) -> None:
        """AdapterException raised at process level is caught and classified."""
        svc, fabric, planner, delta, event, mailbox, state = await _svc()

        async def _raise_adapter(request, ctx):
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.RECOVERABLE,
                    adapter_name="test",
                    operation="test",
                    error_code="TEST",
                    error_message="test error",
                )
            )

        svc._workflow_engine = _StubWorkflowEngine(execute=_raise_adapter)

        req = _make_workflow_run_request()
        result = await svc.process(req)
        assert result == ProcessResult.DEFERRED  # RECOVERABLE -> DEFERRED
