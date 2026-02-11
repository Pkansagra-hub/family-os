"""
Tests for OrchestratorService -- Central Dispatch (Issues 2.1.1-2.1.6).

Validates: process() routing, tier dispatch, two-phase HIGH protocol,
RACE condition handling, stale context reaping, error classification,
LRU dedup, per-step error isolation (2.1.3), aggregate() pure function
(2.1.5), save_workflow delta emission (2.1.6), and all helper methods.

Test Philosophy: Protocol-based fakes implementing the same Protocols
as production collaborators. NO magic mocking. Every fake records calls
for assertion and returns deterministic results.

Coverage targets (by method):
  process()               -- isinstance routing for all 5 message types + unknown
  _route_task()           -- tier routing MEDIUM / HIGH / invalid
  _dispatch_medium()      -- single + batch capabilities, safety_band check
  _dispatch_high()        -- full two-phase flow, PlanAck handling, capacity guard
  _receive_plan()         -- RACE-1/2/3, constraint validation, ConcurrencyGuard
  receive_plan_failed()   -- pending context pop, emit
  receive_plan_cancelled()-- pending context pop
  _dispatch_workflow()    -- concurrency guard + delegation
  _save_workflow()        -- delegation
  _handle_interrupt()     -- CANCEL_DAG + PAUSE rejection
  reap_stale_contexts()   -- timeout expiry for plans + HIL
  _build_context()        -- context extraction per message type
  _validate_envelope()    -- missing trace_id, intent, invalid tier
  _record_executed_plan() -- LRU eviction boundary
  _handle_adapter_error() -- severity -> ProcessResult mapping
  _result_to_process_result() -- AggregatedResult -> ProcessResult mapping
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from k1.fabric.ports.state_reader import SessionSnapshot
from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.events import (
    ORCH_DAG_COMPLETED,
    ORCH_PLAN_REQUESTED,
    ORCH_TASK_ACCEPTED,
    ORCH_WORKFLOW_SAVED,
)
from k1.orchestrator.orchestration.orchestrator_service import (
    AdapterException,
    OrchestratorService,
    ValidationResultLike,
)
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
    PlanRequest,
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
# Fakes -- deterministic Protocol implementations for testing
# ===========================================================================


class FakeDeltaEmitPort:
    """Records all emitted events for assertion."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    async def emit(self, event_topic: str, payload: Dict[str, Any], trace_id: str) -> None:
        self.events.append({"topic": event_topic, "payload": payload, "trace_id": trace_id})

    async def emit_progress(self, step_id: str, summary: str, trace_id: str) -> None:
        self.events.append({"topic": "__progress__", "step_id": step_id, "summary": summary})

    async def emit_hil_request(
        self,
        request_id: str,
        question: str,
        options: List[str],
        trace_id: str,
    ) -> None:
        self.events.append({"topic": "__hil__", "request_id": request_id, "question": question})

    def find(self, topic: str) -> List[Dict[str, Any]]:
        """Return all events matching a specific topic."""
        return [e for e in self.events if e["topic"] == topic]


class FakeBridgeWritePort:
    """Records audit submissions and WAL writes."""

    def __init__(self) -> None:
        self.audits: List[Dict[str, Any]] = []
        self.wal_entries: Dict[str, List[Dict[str, Any]]] = {}

    async def submit_audit(self, run_manifest: Dict[str, Any], trace_id: str) -> None:
        self.audits.append({"manifest": run_manifest, "trace_id": trace_id})

    async def write_wal(
        self, dag_id: str, entry_type: str, payload: Dict[str, Any], trace_id: str
    ) -> None:
        self.wal_entries.setdefault(dag_id, []).append({"type": entry_type, "payload": payload})

    async def read_wal(self, dag_id: str) -> Optional[List[Dict[str, Any]]]:
        return self.wal_entries.get(dag_id)

    async def list_wal_ids(self) -> List[str]:
        return list(self.wal_entries.keys())

    async def submit_deferred_result(
        self,
        request_id: str,
        result: Dict[str, Any],
        trace_id: str,
    ) -> None:
        pass


class FakeStateReadPort:
    """Returns canned SessionSnapshot or section data."""

    def __init__(
        self,
        snapshot: Optional[SessionSnapshot] = None,
        sections: Optional[Dict[str, Dict[str, Any]]] = None,
        raise_on_snapshot: bool = False,
        raise_on_section: bool = False,
    ) -> None:
        self._snapshot = snapshot or SessionSnapshot(session_id="s1")
        self._sections = sections or {}
        self._raise_on_snapshot = raise_on_snapshot
        self._raise_on_section = raise_on_section

    async def read_section(self, session_id: str, section_name: str) -> Optional[Dict[str, Any]]:
        if self._raise_on_section:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="state_read",
                    operation="read_section",
                    error_code="UNAVAILABLE",
                    error_message="State unavailable",
                )
            )
        return self._sections.get(section_name)

    async def read_sections(
        self, session_id: str, section_names: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        return {k: v for k, v in self._sections.items() if k in section_names}

    async def get_snapshot(self, session_id: str) -> SessionSnapshot:
        if self._raise_on_snapshot:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="state_read",
                    operation="get_snapshot",
                    error_code="UNAVAILABLE",
                    error_message="State unavailable",
                )
            )
        return self._snapshot


class FakeFabricGatewayPort:
    """Returns canned CapabilityResults and RegistryEntries.

    Supports per-call error injection via raise_on_execute_indices
    for testing per-step error isolation (2.1.3).
    """

    def __init__(
        self,
        registry: Optional[Dict[str, RegistryEntry]] = None,
        results: Optional[List[CapabilityResult]] = None,
        raise_on_execute: bool = False,
        raise_on_registry: bool = False,
        registry_error_severity: ErrorSeverity = ErrorSeverity.RECOVERABLE,
        raise_on_execute_indices: Optional[set] = None,
    ) -> None:
        self._registry = registry or {}
        self._results = results or []
        self._result_idx = 0
        self._raise_on_execute = raise_on_execute
        self._raise_on_registry = raise_on_registry
        self._registry_error_severity = registry_error_severity
        self._raise_on_execute_indices = raise_on_execute_indices or set()
        self.executed: List[CapabilityRequest] = []

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        current_idx = len(self.executed)
        self.executed.append(request)
        if self._raise_on_execute or current_idx in self._raise_on_execute_indices:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="fabric",
                    operation="execute",
                    error_code="TIMEOUT",
                    error_message="Fabric timeout",
                )
            )
        idx = min(self._result_idx, len(self._results) - 1)
        self._result_idx += 1
        return self._results[idx]

    async def execute_batch(self, requests: List[CapabilityRequest]) -> List[CapabilityResult]:
        results = []
        for req in requests:
            results.append(await self.execute(req))
        return results

    async def query_registry(self, capability_name: str) -> Optional[RegistryEntry]:
        if self._raise_on_registry:
            raise AdapterException(
                AdapterError(
                    severity=self._registry_error_severity,
                    adapter_name="fabric",
                    operation="query_registry",
                    error_code="UNAVAILABLE",
                    error_message="Registry unavailable",
                )
            )
        return self._registry.get(capability_name)


class FakePlannerPort:
    """Returns canned PlanAck and records cancel calls."""

    def __init__(
        self,
        ack: Optional[PlanAck] = None,
        raise_on_request: bool = False,
    ) -> None:
        self._ack = ack or PlanAck(request_id="", status="ACCEPTED")
        self._raise_on_request = raise_on_request
        self.requested: List[PlanRequest] = []
        self.cancelled: List[str] = []

    async def request_plan(self, plan_request: PlanRequest) -> PlanAck:
        self.requested.append(plan_request)
        if self._raise_on_request:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="planner",
                    operation="request_plan",
                    error_code="UNREACHABLE",
                    error_message="Planner unreachable",
                )
            )
        return PlanAck(request_id=plan_request.request_id, status=self._ack.status)

    async def cancel_plan(self, request_id: str) -> None:
        self.cancelled.append(request_id)

    async def micro_replan(self, *args: Any, **kwargs: Any) -> Any:
        pass


class FakeDAGExecutor:
    """Returns a canned AggregatedResult from execute()."""

    def __init__(
        self,
        result: Optional[AggregatedResult] = None,
        raise_on_execute: bool = False,
    ) -> None:
        self._result = result or AggregatedResult.from_medium([], "t1")
        self._raise_on_execute = raise_on_execute
        self.executed: List[CommittedPlan] = []

    async def execute(self, plan: CommittedPlan, ctx: ProcessingContext) -> AggregatedResult:
        self.executed.append(plan)
        if self._raise_on_execute:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.TERMINAL,
                    adapter_name="dag_executor",
                    operation="execute",
                    error_code="INTERNAL",
                    error_message="DAG execution failed",
                )
            )
        return self._result


class FakeConstraintResolver:
    """Returns canned validation result."""

    def __init__(self, valid: bool = True, issues: Optional[List[str]] = None) -> None:
        self._valid = valid
        self._issues = issues or []

    async def validate(self, plan: CommittedPlan, ctx: ProcessingContext) -> ValidationResultLike:
        return _FakeValidation(self._valid, self._issues)


class _FakeValidation:
    """Implements ValidationResultLike protocol."""

    def __init__(self, valid: bool, issues: List[str]) -> None:
        self._valid = valid
        self._issues = issues

    @property
    def valid(self) -> bool:
        return self._valid

    @property
    def issues(self) -> List[str]:
        return self._issues


class FakeWorkflowEngine:
    """Returns canned ProcessResult from workflow ops."""

    def __init__(self, result: ProcessResult = ProcessResult.COMPLETED) -> None:
        self._result = result
        self.executed: List[WorkflowRunRequest] = []
        self.saved: List[WorkflowSaveRequest] = []

    async def execute_workflow(
        self, request: WorkflowRunRequest, ctx: ProcessingContext
    ) -> ProcessResult:
        self.executed.append(request)
        return self._result

    async def save_workflow(
        self, request: WorkflowSaveRequest, ctx: ProcessingContext
    ) -> ProcessResult:
        self.saved.append(request)
        return self._result


class FakeConnectorLifecycle:
    """Placeholder -- no methods consumed in 2.1.1."""

    pass


class FakeErrorRouter:
    """Returns a configurable severity classification."""

    def __init__(self, severity: ErrorSeverity = ErrorSeverity.DEGRADED) -> None:
        self._severity = severity
        self.classified: List[AdapterException] = []

    def classify(self, error: AdapterException, ctx: ProcessingContext) -> ErrorSeverity:
        self.classified.append(error)
        return self._severity


class FakeConcurrencyGuard:
    """Tracks acquire/release calls. allow=False simulates contention."""

    def __init__(self, allow: bool = True) -> None:
        self._allow = allow
        self.acquired: int = 0
        self.released: int = 0

    def acquire(self, ctx: ProcessingContext) -> bool:
        self.acquired += 1
        return self._allow

    def release(self, ctx: ProcessingContext) -> None:
        self.released += 1


class FakeMailboxPort:
    """In-process fake mailbox for testing re-enqueue behaviour.

    Records enqueued messages for assertion. Optionally raises on
    enqueue to simulate MailboxFullError.
    """

    def __init__(self, *, raise_on_enqueue: bool = False) -> None:
        self.enqueued: List[tuple] = []
        self._raise_on_enqueue = raise_on_enqueue

    def enqueue(self, message: Any, priority: str = "INTERACTIVE") -> int:
        if self._raise_on_enqueue:
            raise RuntimeError("Mailbox full (fake)")
        self.enqueued.append((message, priority))
        return len(self.enqueued) - 1

    def dequeue(self) -> Optional[Any]:
        return self.enqueued.pop(0)[0] if self.enqueued else None

    def depth(self) -> int:
        return len(self.enqueued)

    def peek_priority(self) -> Optional[str]:
        return self.enqueued[0][1] if self.enqueued else None


# ===========================================================================
# Helpers
# ===========================================================================


def _default_config(**overrides: Any) -> OrchestratorConfig:
    """Build a default OrchestratorConfig, overridable for test scenarios."""
    defaults = {
        "mailbox_capacity": 64,
        "max_concurrent_dags": 1,
        "default_step_timeout_ms": 10_000,
        "plan_request_timeout_ms": 30_000,
        "max_pending_plans": 5,
    }
    defaults.update(overrides)
    return OrchestratorConfig(**defaults)


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
    trace_id: str = "",
) -> WorkflowSaveRequest:
    tid = trace_id or str(uuid4())
    return WorkflowSaveRequest(
        committed_plan_id=committed_plan_id,
        workflow_name="test-workflow",
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


def _default_registry(*cap_names: str) -> Dict[str, RegistryEntry]:
    return {
        name: RegistryEntry(
            name=name,
            provider_type="tool",
            safety_band_min="GREEN",
            availability="AVAILABLE",
        )
        for name in cap_names
    }


def _build_service(
    *,
    config: Optional[OrchestratorConfig] = None,
    mailbox: Optional[FakeMailboxPort] = None,
    dag_executor: Optional[FakeDAGExecutor] = None,
    constraint_resolver: Optional[FakeConstraintResolver] = None,
    workflow_engine: Optional[FakeWorkflowEngine] = None,
    error_router: Optional[FakeErrorRouter] = None,
    concurrency_guard: Optional[FakeConcurrencyGuard] = None,
    fabric_port: Optional[FakeFabricGatewayPort] = None,
    planner_port: Optional[FakePlannerPort] = None,
    state_port: Optional[FakeStateReadPort] = None,
    delta_port: Optional[FakeDeltaEmitPort] = None,
    bridge_port: Optional[FakeBridgeWritePort] = None,
) -> OrchestratorService:
    """Build OrchestratorService with sensible fake defaults."""
    return OrchestratorService(
        mailbox=mailbox or FakeMailboxPort(),
        dag_executor=dag_executor or FakeDAGExecutor(),
        constraint_resolver=constraint_resolver or FakeConstraintResolver(),
        workflow_engine=workflow_engine or FakeWorkflowEngine(),
        connector_lifecycle=FakeConnectorLifecycle(),
        error_router=error_router or FakeErrorRouter(),
        concurrency_guard=concurrency_guard or FakeConcurrencyGuard(),
        fabric_port=fabric_port
        or FakeFabricGatewayPort(
            registry=_default_registry("tool.test.a", "tool.test.b"),
            results=[_success_result()],
        ),
        planner_port=planner_port or FakePlannerPort(),
        state_port=state_port or FakeStateReadPort(),
        delta_port=delta_port or FakeDeltaEmitPort(),
        bridge_port=bridge_port or FakeBridgeWritePort(),
        config=config or _default_config(),
    )


# ===========================================================================
# Tests: process() routing
# ===========================================================================


class TestProcessRouting:
    """Validate isinstance-based dispatch in process()."""

    @pytest.mark.asyncio
    async def test_routes_task_envelope(self) -> None:
        """TaskEnvelope routes to _route_task -> _dispatch_medium."""
        svc = _build_service()
        envelope = _make_envelope(tier="MEDIUM")
        result = await svc.process(envelope)
        assert result == ProcessResult.COMPLETED

    @pytest.mark.asyncio
    async def test_routes_committed_plan(self) -> None:
        """CommittedPlan routes to _receive_plan."""
        plan = _make_plan()
        svc = _build_service()
        # Pre-park a PendingPlanContext so receive_plan has something to correlate.
        svc._pending_plans[plan.request_id] = PendingPlanContext(
            request_id=plan.request_id,
            task_envelope=_make_envelope(tier="HIGH"),
            state_snapshot=SessionSnapshot(session_id="s1"),
        )
        result = await svc.process(plan)
        assert result in (ProcessResult.COMPLETED, ProcessResult.DEGRADED)

    @pytest.mark.asyncio
    async def test_routes_workflow_run_request(self) -> None:
        """WorkflowRunRequest routes to _dispatch_workflow."""
        svc = _build_service()
        req = _make_workflow_run_request()
        result = await svc.process(req)
        assert result == ProcessResult.COMPLETED

    @pytest.mark.asyncio
    async def test_routes_workflow_save_request(self) -> None:
        """WorkflowSaveRequest routes to _save_workflow."""
        svc = _build_service()
        req = _make_workflow_save_request()
        result = await svc.process(req)
        assert result == ProcessResult.COMPLETED

    @pytest.mark.asyncio
    async def test_routes_interrupt_request(self) -> None:
        """InterruptRequest routes to _handle_interrupt."""
        svc = _build_service()
        req = _make_interrupt()
        result = await svc.process(req)
        assert result == ProcessResult.CANCELLED

    @pytest.mark.asyncio
    async def test_unknown_message_type_returns_failed(self) -> None:
        """Unknown message type returns FAILED."""
        svc = _build_service()
        result = await svc.process("not a real message")  # type: ignore[arg-type]
        assert result == ProcessResult.FAILED


# ===========================================================================
# Tests: _route_task() and _validate_envelope()
# ===========================================================================


class TestRouteTask:
    """Validate TaskEnvelope routing by tier."""

    @pytest.mark.asyncio
    async def test_medium_tier_dispatches_to_fabric(self) -> None:
        """MEDIUM tier executes via Fabric and emits TASK_ACCEPTED."""
        delta = FakeDeltaEmitPort()
        svc = _build_service(delta_port=delta)
        envelope = _make_envelope(tier="MEDIUM")
        result = await svc.process(envelope)

        assert result == ProcessResult.COMPLETED
        accepted = delta.find(ORCH_TASK_ACCEPTED)
        assert len(accepted) == 1
        assert accepted[0]["payload"]["tier"] == "MEDIUM"

    @pytest.mark.asyncio
    async def test_high_tier_defers_to_planner(self) -> None:
        """HIGH tier sends PlanRequest and returns DEFERRED."""
        delta = FakeDeltaEmitPort()
        planner = FakePlannerPort()
        svc = _build_service(delta_port=delta, planner_port=planner)
        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)

        assert result == ProcessResult.DEFERRED
        assert len(planner.requested) == 1
        plan_requested = delta.find(ORCH_PLAN_REQUESTED)
        assert len(plan_requested) == 1

    @pytest.mark.asyncio
    async def test_missing_intent_fails(self) -> None:
        """TaskEnvelope with empty intent is rejected."""
        svc = _build_service()
        # Cannot create TaskEnvelope with empty intent due to __post_init__
        # So we test _validate_envelope directly
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
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
        result = svc._validate_envelope(envelope, ctx)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_missing_trace_id_fails(self) -> None:
        """TaskEnvelope with empty trace_id is rejected."""
        svc = _build_service()
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
        envelope = TaskEnvelope.__new__(TaskEnvelope)
        object.__setattr__(envelope, "intent", "test")
        object.__setattr__(envelope, "trace_id", "")
        object.__setattr__(envelope, "tier", "MEDIUM")
        object.__setattr__(envelope, "capabilities", ["tool.test.a"])
        object.__setattr__(envelope, "envelope_id", "e1")
        object.__setattr__(envelope, "context", {})
        object.__setattr__(envelope, "params", {})
        object.__setattr__(envelope, "constraints", {})
        object.__setattr__(envelope, "timeout_ms", 30000)
        object.__setattr__(envelope, "caller_id", "")
        result = svc._validate_envelope(envelope, ctx)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_invalid_tier_in_validate_envelope(self) -> None:
        """TaskEnvelope with tier=LOW is rejected by _validate_envelope."""
        svc = _build_service()
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="LOW")
        envelope = TaskEnvelope.__new__(TaskEnvelope)
        object.__setattr__(envelope, "intent", "test")
        object.__setattr__(envelope, "trace_id", "t1")
        object.__setattr__(envelope, "tier", "LOW")
        object.__setattr__(envelope, "capabilities", [])
        object.__setattr__(envelope, "envelope_id", "e1")
        object.__setattr__(envelope, "context", {})
        object.__setattr__(envelope, "params", {})
        object.__setattr__(envelope, "constraints", {})
        object.__setattr__(envelope, "timeout_ms", 30000)
        object.__setattr__(envelope, "caller_id", "")
        result = svc._validate_envelope(envelope, ctx)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_valid_envelope_returns_none(self) -> None:
        """Valid TaskEnvelope passes validation (returns None)."""
        svc = _build_service()
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
        envelope = _make_envelope(tier="MEDIUM")
        result = svc._validate_envelope(envelope, ctx)
        assert result is None


# ===========================================================================
# Tests: route_task dispatch error handling (Issue 2.1.2)
# ===========================================================================


class TestRouteTaskDispatchErrors:
    """Validate route_task error handling per Issue 2.1.2.

    Tests cover: AdapterException classification via ErrorRouter,
    re-enqueue on RECOVERABLE (once guard), DEGRADED/TERMINAL mapping,
    mailbox full fallback, and bounded LRU for requeued IDs.
    """

    @pytest.mark.asyncio
    async def test_recoverable_requeues_once_returns_deferred(self) -> None:
        """RECOVERABLE adapter error -> re-enqueue to mailbox -> DEFERRED."""
        mailbox = FakeMailboxPort()
        error_router = FakeErrorRouter(severity=ErrorSeverity.RECOVERABLE)
        fabric = FakeFabricGatewayPort(
            raise_on_registry=True,
            registry_error_severity=ErrorSeverity.RECOVERABLE,
        )
        delta = FakeDeltaEmitPort()
        svc = _build_service(
            mailbox=mailbox,
            error_router=error_router,
            fabric_port=fabric,
            delta_port=delta,
        )
        envelope = _make_envelope(tier="MEDIUM")
        result = await svc.process(envelope)

        assert result == ProcessResult.DEFERRED
        assert len(mailbox.enqueued) == 1
        assert mailbox.enqueued[0][0] is envelope
        assert mailbox.enqueued[0][1] == "INTERACTIVE"
        assert envelope.envelope_id in svc.requeued_envelope_ids
        assert len(error_router.classified) == 1
        assert len(delta.find(ORCH_TASK_ACCEPTED)) == 1

    @pytest.mark.asyncio
    async def test_recoverable_already_requeued_returns_failed(self) -> None:
        """Second RECOVERABLE for same envelope_id -> once guard -> FAILED."""
        mailbox = FakeMailboxPort()
        error_router = FakeErrorRouter(severity=ErrorSeverity.RECOVERABLE)
        fabric = FakeFabricGatewayPort(
            raise_on_registry=True,
            registry_error_severity=ErrorSeverity.RECOVERABLE,
        )
        svc = _build_service(
            mailbox=mailbox,
            error_router=error_router,
            fabric_port=fabric,
        )
        envelope = _make_envelope(tier="MEDIUM")
        r1 = await svc.process(envelope)
        assert r1 == ProcessResult.DEFERRED

        r2 = await svc.process(envelope)
        assert r2 == ProcessResult.FAILED
        assert len(mailbox.enqueued) == 1  # only one enqueue, not two

    @pytest.mark.asyncio
    async def test_degraded_dispatch_error_returns_degraded(self) -> None:
        """DEGRADED adapter error from dispatch -> DEGRADED."""
        error_router = FakeErrorRouter(severity=ErrorSeverity.DEGRADED)
        fabric = FakeFabricGatewayPort(
            raise_on_registry=True,
            registry_error_severity=ErrorSeverity.DEGRADED,
        )
        svc = _build_service(error_router=error_router, fabric_port=fabric)
        envelope = _make_envelope(tier="MEDIUM")
        result = await svc.process(envelope)

        assert result == ProcessResult.DEGRADED
        assert len(error_router.classified) == 1

    @pytest.mark.asyncio
    async def test_terminal_dispatch_error_returns_failed(self) -> None:
        """TERMINAL adapter error from dispatch -> FAILED."""
        error_router = FakeErrorRouter(severity=ErrorSeverity.TERMINAL)
        fabric = FakeFabricGatewayPort(
            raise_on_registry=True,
            registry_error_severity=ErrorSeverity.TERMINAL,
        )
        svc = _build_service(error_router=error_router, fabric_port=fabric)
        envelope = _make_envelope(tier="MEDIUM")
        result = await svc.process(envelope)

        assert result == ProcessResult.FAILED
        assert len(error_router.classified) == 1

    @pytest.mark.asyncio
    async def test_requeue_mailbox_full_returns_failed(self) -> None:
        """RECOVERABLE but mailbox rejects enqueue -> FAILED."""
        mailbox = FakeMailboxPort(raise_on_enqueue=True)
        error_router = FakeErrorRouter(severity=ErrorSeverity.RECOVERABLE)
        fabric = FakeFabricGatewayPort(
            raise_on_registry=True,
            registry_error_severity=ErrorSeverity.RECOVERABLE,
        )
        svc = _build_service(
            mailbox=mailbox,
            error_router=error_router,
            fabric_port=fabric,
        )
        envelope = _make_envelope(tier="MEDIUM")
        result = await svc.process(envelope)

        assert result == ProcessResult.FAILED
        assert len(mailbox.enqueued) == 0

    @pytest.mark.asyncio
    async def test_task_accepted_emitted_before_dispatch_error(self) -> None:
        """TASK_ACCEPTED event is emitted even when dispatch subsequently fails."""
        delta = FakeDeltaEmitPort()
        error_router = FakeErrorRouter(severity=ErrorSeverity.TERMINAL)
        fabric = FakeFabricGatewayPort(
            raise_on_registry=True,
            registry_error_severity=ErrorSeverity.TERMINAL,
        )
        svc = _build_service(
            delta_port=delta,
            error_router=error_router,
            fabric_port=fabric,
        )
        envelope = _make_envelope(tier="MEDIUM")
        await svc.process(envelope)

        accepted = delta.find(ORCH_TASK_ACCEPTED)
        assert len(accepted) == 1
        assert accepted[0]["payload"]["envelope_id"] == envelope.envelope_id

    @pytest.mark.asyncio
    async def test_validation_failure_skips_task_accepted(self) -> None:
        """Validation failure returns FAILED without emitting TASK_ACCEPTED."""
        delta = FakeDeltaEmitPort()
        svc = _build_service(delta_port=delta)
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
        assert len(delta.find(ORCH_TASK_ACCEPTED)) == 0

    @pytest.mark.asyncio
    async def test_error_router_receives_adapter_exception(self) -> None:
        """ErrorRouter.classify receives the AdapterException from dispatch."""
        error_router = FakeErrorRouter(severity=ErrorSeverity.TERMINAL)
        fabric = FakeFabricGatewayPort(
            raise_on_registry=True,
            registry_error_severity=ErrorSeverity.TERMINAL,
        )
        svc = _build_service(error_router=error_router, fabric_port=fabric)
        envelope = _make_envelope(tier="MEDIUM")
        await svc.process(envelope)

        assert len(error_router.classified) == 1
        exc = error_router.classified[0]
        assert exc.adapter_name == "fabric"
        assert exc.operation == "query_registry"
        assert exc.error_code == "UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_requeue_bounded_lru_eviction(self) -> None:
        """Requeued envelope IDs bounded to _EXECUTED_PLANS_MAX (100)."""
        mailbox = FakeMailboxPort()
        error_router = FakeErrorRouter(severity=ErrorSeverity.RECOVERABLE)
        fabric = FakeFabricGatewayPort(
            raise_on_registry=True,
            registry_error_severity=ErrorSeverity.RECOVERABLE,
        )
        svc = _build_service(
            mailbox=mailbox,
            error_router=error_router,
            fabric_port=fabric,
        )
        for _ in range(105):
            envelope = _make_envelope(tier="MEDIUM")
            await svc.process(envelope)

        assert len(svc.requeued_envelope_ids) == 100
        assert len(mailbox.enqueued) == 105  # all 105 unique envelopes re-enqueued

    @pytest.mark.asyncio
    async def test_requeue_uses_interactive_priority(self) -> None:
        """Re-enqueued messages use INTERACTIVE priority."""
        mailbox = FakeMailboxPort()
        error_router = FakeErrorRouter(severity=ErrorSeverity.RECOVERABLE)
        fabric = FakeFabricGatewayPort(
            raise_on_registry=True,
            registry_error_severity=ErrorSeverity.RECOVERABLE,
        )
        svc = _build_service(
            mailbox=mailbox,
            error_router=error_router,
            fabric_port=fabric,
        )
        envelope = _make_envelope(tier="MEDIUM")
        await svc.process(envelope)

        assert len(mailbox.enqueued) == 1
        assert mailbox.enqueued[0][1] == "INTERACTIVE"


# ===========================================================================
# Tests: _dispatch_medium()
# ===========================================================================


class TestDispatchMedium:
    """Validate MEDIUM tier capability execution."""

    @pytest.mark.asyncio
    async def test_single_capability_success(self) -> None:
        """Single capability execution returns COMPLETED."""
        delta = FakeDeltaEmitPort()
        bridge = FakeBridgeWritePort()
        fabric = FakeFabricGatewayPort(
            registry=_default_registry("tool.test.a"),
            results=[_success_result()],
        )
        svc = _build_service(fabric_port=fabric, delta_port=delta, bridge_port=bridge)
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a"])
        result = await svc.process(envelope)

        assert result == ProcessResult.COMPLETED
        assert len(fabric.executed) == 1
        dag_completed = delta.find(ORCH_DAG_COMPLETED)
        assert len(dag_completed) == 1
        assert len(bridge.audits) == 1

    @pytest.mark.asyncio
    async def test_batch_two_capabilities(self) -> None:
        """Two capabilities execute as batch via execute_batch."""
        fabric = FakeFabricGatewayPort(
            registry=_default_registry("tool.test.a", "tool.test.b"),
            results=[_success_result(), _success_result()],
        )
        svc = _build_service(fabric_port=fabric)
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a", "tool.test.b"])
        result = await svc.process(envelope)

        assert result == ProcessResult.COMPLETED
        assert len(fabric.executed) == 2

    @pytest.mark.asyncio
    async def test_capability_not_found_fails(self) -> None:
        """Unknown capability in registry returns FAILED."""
        fabric = FakeFabricGatewayPort(
            registry={},  # Empty registry
            results=[_success_result()],
        )
        svc = _build_service(fabric_port=fabric)
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.unknown"])
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_safety_band_insufficient_fails(self) -> None:
        """Capability with insufficient safety_band returns FAILED."""
        registry = {
            "tool.test.a": RegistryEntry(
                name="tool.test.a",
                provider_type="tool",
                safety_band_min="RED",  # Requires RED
                availability="AVAILABLE",
            )
        }
        state = FakeStateReadPort(
            sections={"control": {"safety_band": "GREEN"}}  # Current is GREEN
        )
        fabric = FakeFabricGatewayPort(registry=registry, results=[_success_result()])
        svc = _build_service(fabric_port=fabric, state_port=state)
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a"])
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_fabric_execute_error_handled(self) -> None:
        """AdapterException from Fabric.execute() is caught per-step.

        With per-step isolation (2.1.3), a single capability that raises
        AdapterException produces a FAILED StepResult. Since there is
        only one step and it failed, the overall result is FAILED.
        ErrorRouter is NOT invoked at dispatch_medium level.
        """
        fabric = FakeFabricGatewayPort(
            registry=_default_registry("tool.test.a"),
            results=[],
            raise_on_execute=True,
        )
        delta = FakeDeltaEmitPort()
        svc = _build_service(fabric_port=fabric, delta_port=delta)
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a"])
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED
        # Per-step isolation still emits DAG_COMPLETED with the failure
        dag_completed = delta.find(ORCH_DAG_COMPLETED)
        assert len(dag_completed) == 1
        assert dag_completed[0]["payload"]["failed"] == 1

    @pytest.mark.asyncio
    async def test_partial_failure_returns_degraded(self) -> None:
        """One success + one failure returns DEGRADED via result mapping."""
        fabric = FakeFabricGatewayPort(
            registry=_default_registry("tool.test.a", "tool.test.b"),
            results=[_success_result(), _failure_result()],
        )
        svc = _build_service(fabric_port=fabric)
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a", "tool.test.b"])
        result = await svc.process(envelope)
        assert result == ProcessResult.DEGRADED

    # -- 2.1.3: per-step error isolation -----------------------------------

    @pytest.mark.asyncio
    async def test_per_step_isolation_first_fails_second_succeeds(self) -> None:
        """First step raises AdapterException; second step still executes.

        Per 2.1.3 spec: step fails, other steps continue -> DEGRADED.
        """
        fabric = FakeFabricGatewayPort(
            registry=_default_registry("tool.test.a", "tool.test.b"),
            results=[_success_result()],  # Only second call consumes this
            raise_on_execute_indices={0},  # First call raises
        )
        delta = FakeDeltaEmitPort()
        svc = _build_service(fabric_port=fabric, delta_port=delta)
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a", "tool.test.b"])
        result = await svc.process(envelope)

        assert result == ProcessResult.DEGRADED
        # Both steps were attempted
        assert len(fabric.executed) == 2
        # DAG_COMPLETED emitted with 1 failed + 1 completed
        dag_completed = delta.find(ORCH_DAG_COMPLETED)
        assert len(dag_completed) == 1
        assert dag_completed[0]["payload"]["failed"] == 1
        assert dag_completed[0]["payload"]["completed"] == 1

    @pytest.mark.asyncio
    async def test_per_step_isolation_second_fails_first_succeeds(self) -> None:
        """Second step raises AdapterException; first step already succeeded."""
        fabric = FakeFabricGatewayPort(
            registry=_default_registry("tool.test.a", "tool.test.b"),
            results=[_success_result()],  # First call consumes this
            raise_on_execute_indices={1},  # Second call raises
        )
        svc = _build_service(fabric_port=fabric)
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a", "tool.test.b"])
        result = await svc.process(envelope)

        assert result == ProcessResult.DEGRADED
        assert len(fabric.executed) == 2

    @pytest.mark.asyncio
    async def test_per_step_isolation_both_fail_returns_failed(self) -> None:
        """Both steps raise AdapterException -> all FAILED -> FAILED."""
        fabric = FakeFabricGatewayPort(
            registry=_default_registry("tool.test.a", "tool.test.b"),
            results=[],
            raise_on_execute_indices={0, 1},
        )
        svc = _build_service(fabric_port=fabric)
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a", "tool.test.b"])
        result = await svc.process(envelope)

        assert result == ProcessResult.FAILED
        # Both steps were still attempted (isolation, not short-circuit)
        assert len(fabric.executed) == 2

    @pytest.mark.asyncio
    async def test_single_cap_adapter_error_returns_failed(self) -> None:
        """Single capability AdapterException -> 1 failed, 0 completed -> FAILED."""
        fabric = FakeFabricGatewayPort(
            registry=_default_registry("tool.test.a"),
            results=[],
            raise_on_execute_indices={0},
        )
        svc = _build_service(fabric_port=fabric)
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a"])
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    # -- 2.1.3: ORCH-10 precondition tests ---------------------------------

    @pytest.mark.asyncio
    async def test_orch10_empty_capabilities_fails(self) -> None:
        """ORCH-10: empty capabilities list returns FAILED."""
        svc = _build_service()
        # Bypass __post_init__ to test dispatch_medium's defensive check.
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
        svc = _build_service()
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
        fabric = FakeFabricGatewayPort(
            registry=_default_registry("tool.test.a"),
            results=[],
            raise_on_execute_indices={0},
        )
        delta = FakeDeltaEmitPort()
        svc = _build_service(fabric_port=fabric, delta_port=delta)
        envelope = _make_envelope(tier="MEDIUM", capabilities=["tool.test.a"])
        await svc.process(envelope)

        dag_completed = delta.find(ORCH_DAG_COMPLETED)
        step_results = dag_completed[0]["payload"]["step_results"]
        assert len(step_results) == 1
        assert step_results[0]["status"] == "FAILED"
        assert step_results[0]["error_detail"] == "Fabric timeout"


# ===========================================================================
# Tests: _dispatch_high() -- Phase 1
# ===========================================================================


class TestDispatchHigh:
    """Validate HIGH tier plan request flow."""

    @pytest.mark.asyncio
    async def test_successful_plan_request_returns_deferred(self) -> None:
        """Plan accepted by Planner returns DEFERRED."""
        planner = FakePlannerPort(ack=PlanAck(request_id="", status="ACCEPTED"))
        svc = _build_service(planner_port=planner)
        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)

        assert result == ProcessResult.DEFERRED
        assert len(svc.pending_plans) == 1
        assert len(planner.requested) == 1

    @pytest.mark.asyncio
    async def test_plan_rejected_returns_failed(self) -> None:
        """Plan rejected by Planner returns FAILED."""
        planner = FakePlannerPort(ack=PlanAck(request_id="", status="REJECTED"))
        svc = _build_service(planner_port=planner)
        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_planner_unreachable_returns_failed(self) -> None:
        """AdapterException from Planner returns FAILED."""
        planner = FakePlannerPort(raise_on_request=True)
        svc = _build_service(planner_port=planner)
        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_pending_plans_limit_exceeded(self) -> None:
        """Exceeding max_pending_plans returns FAILED and cancels."""
        config = _default_config(max_pending_plans=1)
        planner = FakePlannerPort()
        svc = _build_service(config=config, planner_port=planner)

        # Fill up the pending_plans
        svc._pending_plans["existing"] = PendingPlanContext(
            request_id="existing",
            task_envelope=_make_envelope(tier="HIGH"),
            state_snapshot=SessionSnapshot(session_id="s1"),
        )

        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)
        assert result == ProcessResult.FAILED
        # Should have attempted to cancel the newly requested plan
        assert len(planner.cancelled) == 1

    @pytest.mark.asyncio
    async def test_request_id_echoed_in_pending_context(self) -> None:
        """PendingPlanContext stores the request_id sent to Planner."""
        planner = FakePlannerPort()
        svc = _build_service(planner_port=planner)
        envelope = _make_envelope(tier="HIGH")
        await svc.process(envelope)

        assert len(planner.requested) == 1
        sent_request_id = planner.requested[0].request_id
        assert sent_request_id in svc.pending_plans
        assert svc.pending_plans[sent_request_id].request_id == sent_request_id

    @pytest.mark.asyncio
    async def test_state_snapshot_failure_still_sends_plan(self) -> None:
        """Snapshot failure should not block plan request."""
        state = FakeStateReadPort(raise_on_snapshot=True)
        planner = FakePlannerPort()
        svc = _build_service(state_port=state, planner_port=planner)
        envelope = _make_envelope(tier="HIGH")
        result = await svc.process(envelope)
        # Should still send plan even without snapshot
        assert result == ProcessResult.DEFERRED
        assert len(planner.requested) == 1

    # -- 2.1.4: additional edge cases --------------------------------------

    @pytest.mark.asyncio
    async def test_plan_requested_event_emitted_with_fields(self) -> None:
        """PLAN_REQUESTED event includes request_id, intent, tier, trace_id."""
        delta = FakeDeltaEmitPort()
        planner = FakePlannerPort()
        svc = _build_service(delta_port=delta, planner_port=planner)
        envelope = _make_envelope(tier="HIGH", intent="book flight")
        result = await svc.process(envelope)

        assert result == ProcessResult.DEFERRED
        plan_events = delta.find(ORCH_PLAN_REQUESTED)
        assert len(plan_events) == 1
        payload = plan_events[0]["payload"]
        assert payload["intent"] == "book flight"
        assert payload["tier"] == "HIGH"
        assert "request_id" in payload
        assert "trace_id" in payload

    @pytest.mark.asyncio
    async def test_plan_request_uses_config_timeout(self) -> None:
        """PlanRequest.timeout_ms comes from OrchestratorConfig, not envelope."""
        config = _default_config(plan_request_timeout_ms=99_000)
        planner = FakePlannerPort()
        svc = _build_service(config=config, planner_port=planner)
        envelope = _make_envelope(tier="HIGH")
        await svc.process(envelope)

        assert len(planner.requested) == 1
        assert planner.requested[0].timeout_ms == 99_000

    @pytest.mark.asyncio
    async def test_pending_context_stores_envelope_and_snapshot(self) -> None:
        """PendingPlanContext holds the original TaskEnvelope and snapshot."""
        planner = FakePlannerPort()
        snapshot = SessionSnapshot(session_id="s-custom")
        state = FakeStateReadPort(snapshot=snapshot)
        svc = _build_service(planner_port=planner, state_port=state)
        envelope = _make_envelope(tier="HIGH", intent="complex task")
        await svc.process(envelope)

        assert len(svc.pending_plans) == 1
        ctx = list(svc.pending_plans.values())[0]
        assert ctx.task_envelope is envelope
        assert ctx.state_snapshot is snapshot

    @pytest.mark.asyncio
    async def test_plan_request_carries_envelope_constraints(self) -> None:
        """PlanRequest.constraints are populated from envelope.constraints."""
        planner = FakePlannerPort()
        svc = _build_service(planner_port=planner)
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

        assert len(planner.requested) == 1
        pr = planner.requested[0]
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
        dag_result = AggregatedResult.from_medium(
            step_results=[
                StepResult(
                    step_id="s1",
                    capability_name="tool.test.a",
                    status=StepStatus.COMPLETED,
                    duration_ms=100,
                )
            ],
            trace_id="t1",
            duration_ms=150,
        )
        executor = FakeDAGExecutor(result=dag_result)
        guard = FakeConcurrencyGuard()
        delta = FakeDeltaEmitPort()
        bridge = FakeBridgeWritePort()
        svc = _build_service(
            dag_executor=executor,
            concurrency_guard=guard,
            delta_port=delta,
            bridge_port=bridge,
        )

        plan = _make_plan(request_id="req1")
        self._park_plan(svc, "req1")
        result = await svc.process(plan)

        assert result == ProcessResult.COMPLETED
        assert guard.acquired == 1
        assert guard.released == 1
        assert len(executor.executed) == 1
        assert len(delta.find(ORCH_DAG_COMPLETED)) == 1
        assert len(bridge.audits) == 1

    @pytest.mark.asyncio
    async def test_race3_duplicate_plan_returns_completed(self) -> None:
        """RACE-3: plan_id already in executed_plans -> COMPLETED (dedup)."""
        svc = _build_service()
        plan = _make_plan(plan_id="dup-plan", request_id="req1")
        self._park_plan(svc, "req1")
        # Pre-populate executed_plans with this plan_id
        svc._executed_plans["dup-plan"] = time.time()
        result = await svc.process(plan)
        assert result == ProcessResult.COMPLETED

    @pytest.mark.asyncio
    async def test_race2_orphan_plan_returns_failed(self) -> None:
        """RACE-2: request_id not in pending_plans -> FAILED (orphan)."""
        svc = _build_service()
        plan = _make_plan(request_id="nonexistent")
        result = await svc.process(plan)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_constraint_validation_failure(self) -> None:
        """Invalid plan per ConstraintResolver returns FAILED."""
        resolver = FakeConstraintResolver(valid=False, issues=["bad constraint"])
        svc = _build_service(constraint_resolver=resolver)
        plan = _make_plan(request_id="req1")
        self._park_plan(svc, "req1")
        result = await svc.process(plan)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_concurrency_guard_rejected(self) -> None:
        """ConcurrencyGuard rejection returns DEFERRED."""
        guard = FakeConcurrencyGuard(allow=False)
        svc = _build_service(concurrency_guard=guard)
        plan = _make_plan(request_id="req1")
        self._park_plan(svc, "req1")
        result = await svc.process(plan)
        assert result == ProcessResult.DEFERRED

    @pytest.mark.asyncio
    async def test_dag_executor_failure_returns_failed(self) -> None:
        """DAGExecutor AdapterException returns FAILED via error router."""
        router = FakeErrorRouter(severity=ErrorSeverity.TERMINAL)
        executor = FakeDAGExecutor(raise_on_execute=True)
        guard = FakeConcurrencyGuard()
        svc = _build_service(
            dag_executor=executor,
            error_router=router,
            concurrency_guard=guard,
        )
        plan = _make_plan(request_id="req1")
        self._park_plan(svc, "req1")
        result = await svc.process(plan)
        assert result == ProcessResult.FAILED
        # ConcurrencyGuard MUST be released even on failure
        assert guard.released == 1

    @pytest.mark.asyncio
    async def test_executed_plans_lru_records(self) -> None:
        """Plan execution records plan_id in executed_plans LRU."""
        svc = _build_service()
        plan = _make_plan(plan_id="plan-abc", request_id="req1")
        self._park_plan(svc, "req1")
        await svc.process(plan)
        assert "plan-abc" in svc.executed_plans

    @pytest.mark.asyncio
    async def test_state_re_snapshot_failure_proceeds(self) -> None:
        """RACE-1: snapshot re-read failure does not block execution."""
        state = FakeStateReadPort(raise_on_snapshot=True)
        svc = _build_service(state_port=state)
        plan = _make_plan(request_id="req1")
        self._park_plan(svc, "req1")
        result = await svc.process(plan)
        # Should still complete (proceeds with stale snapshot)
        assert result in (ProcessResult.COMPLETED, ProcessResult.FAILED)


# ===========================================================================
# Tests: receive_plan_failed() / receive_plan_cancelled()
# ===========================================================================


class TestPlanFailureHandlers:
    """Validate plan failure and cancellation handling."""

    @pytest.mark.asyncio
    async def test_plan_failed_with_pending_context(self) -> None:
        """Plan failure pops pending context and returns FAILED."""
        delta = FakeDeltaEmitPort()
        svc = _build_service(delta_port=delta)
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
        assert len(delta.find(ORCH_DAG_COMPLETED)) == 1

    @pytest.mark.asyncio
    async def test_plan_failed_no_context(self) -> None:
        """Plan failure with unknown request_id still returns FAILED."""
        svc = _build_service()
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
        svc = _build_service()
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
        svc = _build_service()
        result = await svc.receive_plan_cancelled(request_id="nope", trace_id="t1")
        assert result == ProcessResult.CANCELLED


# ===========================================================================
# Tests: _dispatch_workflow() / _save_workflow()
# ===========================================================================


class TestWorkflow:
    """Validate workflow dispatch and save."""

    @pytest.mark.asyncio
    async def test_dispatch_workflow_success(self) -> None:
        """Workflow execution delegates to WorkflowEngine."""
        engine = FakeWorkflowEngine(result=ProcessResult.COMPLETED)
        guard = FakeConcurrencyGuard()
        svc = _build_service(workflow_engine=engine, concurrency_guard=guard)
        req = _make_workflow_run_request()
        result = await svc.process(req)

        assert result == ProcessResult.COMPLETED
        assert len(engine.executed) == 1
        assert guard.acquired == 1
        assert guard.released == 1

    @pytest.mark.asyncio
    async def test_dispatch_workflow_concurrency_rejected(self) -> None:
        """ConcurrencyGuard rejection defers workflow."""
        guard = FakeConcurrencyGuard(allow=False)
        svc = _build_service(concurrency_guard=guard)
        req = _make_workflow_run_request()
        result = await svc.process(req)
        assert result == ProcessResult.DEFERRED

    @pytest.mark.asyncio
    async def test_save_workflow_success(self) -> None:
        """Workflow save delegates to WorkflowEngine."""
        engine = FakeWorkflowEngine(result=ProcessResult.COMPLETED)
        svc = _build_service(workflow_engine=engine)
        req = _make_workflow_save_request()
        result = await svc.process(req)

        assert result == ProcessResult.COMPLETED
        assert len(engine.saved) == 1

    @pytest.mark.asyncio
    async def test_save_workflow_engine_error(self) -> None:
        """AdapterException in save_workflow returns classified result."""
        engine = FakeWorkflowEngine()

        async def raise_save(request: WorkflowSaveRequest, ctx: ProcessingContext) -> ProcessResult:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="workflow_engine",
                    operation="save_workflow",
                    error_code="STORAGE",
                    error_message="Failed to save",
                )
            )

        engine.save_workflow = raise_save  # type: ignore[assignment]
        router = FakeErrorRouter(severity=ErrorSeverity.DEGRADED)
        svc = _build_service(workflow_engine=engine, error_router=router)
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
        svc = _build_service()
        req = _make_interrupt(interrupt_type="CANCEL_DAG")
        result = await svc.process(req)
        assert result == ProcessResult.CANCELLED

    @pytest.mark.asyncio
    async def test_pause_rejected_in_v1(self) -> None:
        """PAUSE interrupt returns FAILED in V1."""
        svc = _build_service()
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
        planner = FakePlannerPort()
        delta = FakeDeltaEmitPort()
        svc = _build_service(planner_port=planner, delta_port=delta)

        # Create a plan context that expired 10 seconds ago
        svc._pending_plans["exp1"] = PendingPlanContext(
            request_id="exp1",
            task_envelope=_make_envelope(tier="HIGH"),
            state_snapshot=SessionSnapshot(session_id="s1"),
            created_at=time.time() - 60,  # 60 seconds ago
            timeout_ms=1000,  # 1 second timeout -> expired
        )

        reaped = await svc.reap_stale_contexts()
        assert reaped == 1
        assert "exp1" not in svc.pending_plans
        assert len(planner.cancelled) == 1
        assert len(delta.find(ORCH_DAG_COMPLETED)) == 1

    @pytest.mark.asyncio
    async def test_reap_does_not_touch_active_context(self) -> None:
        """Active (non-expired) PendingPlanContext is not reaped."""
        svc = _build_service()
        svc._pending_plans["active1"] = PendingPlanContext(
            request_id="active1",
            task_envelope=_make_envelope(tier="HIGH"),
            state_snapshot=SessionSnapshot(session_id="s1"),
            created_at=time.time(),  # Just now
            timeout_ms=60_000,  # 60s timeout -> not expired
        )

        reaped = await svc.reap_stale_contexts()
        assert reaped == 0
        assert "active1" in svc.pending_plans

    @pytest.mark.asyncio
    async def test_reap_expired_hil_context(self) -> None:
        """Expired PendingHILContext is reaped."""
        svc = _build_service()
        svc._pending_hil["hil1"] = PendingHILContext(
            request_id="hil1",
            dag_execution_id="dag-1",
            current_wave_index=0,
            completed_waves=[],
            remaining_waves=[],
            question="Continue?",
            options=["yes", "no"],
            timeout_fallback="GRACEFUL_FAIL",
            created_at=time.time() - 300,  # 5 minutes ago
            timeout_ms=1000,  # 1 second timeout -> expired
        )

        reaped = await svc.reap_stale_contexts()
        assert reaped == 1
        assert "hil1" not in svc.pending_hil

    @pytest.mark.asyncio
    async def test_reap_multiple_types(self) -> None:
        """Both plan + HIL contexts reaped in single call."""
        planner = FakePlannerPort()
        svc = _build_service(planner_port=planner)

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

    def test_task_envelope_context(self) -> None:
        """TaskEnvelope extracts trace_id, envelope_id, tier."""
        svc = _build_service()
        envelope = _make_envelope(tier="MEDIUM", trace_id="trace-1")
        ctx = svc._build_context(envelope)

        assert ctx.trace_id == "trace-1"
        assert ctx.request_id == envelope.envelope_id
        assert ctx.tier == "MEDIUM"

    def test_committed_plan_context(self) -> None:
        """CommittedPlan extracts trace_id, request_id, tier=HIGH."""
        svc = _build_service()
        plan = _make_plan(trace_id="trace-2", request_id="req-2")
        ctx = svc._build_context(plan)

        assert ctx.trace_id == "trace-2"
        assert ctx.request_id == "req-2"
        assert ctx.tier == "HIGH"

    def test_workflow_run_context(self) -> None:
        """WorkflowRunRequest extracts trace_id, request_id, tier=WORKFLOW."""
        svc = _build_service()
        req = _make_workflow_run_request(trace_id="trace-3")
        ctx = svc._build_context(req)

        assert ctx.trace_id == "trace-3"
        assert ctx.tier == "WORKFLOW"

    def test_interrupt_context(self) -> None:
        """InterruptRequest extracts tier=REALTIME."""
        svc = _build_service()
        req = _make_interrupt(trace_id="trace-4")
        ctx = svc._build_context(req)

        assert ctx.trace_id == "trace-4"
        assert ctx.tier == "REALTIME"

    def test_missing_trace_id_generates_fallback(self) -> None:
        """Message without trace_id gets a generated uuid."""
        svc = _build_service()
        ctx = svc._build_context("something weird")  # type: ignore[arg-type]
        assert ctx.trace_id  # Non-empty
        assert ctx.request_id  # Non-empty


# ===========================================================================
# Tests: _record_executed_plan() LRU
# ===========================================================================


class TestRecordExecutedPlan:
    """Validate bounded LRU eviction for executed_plans."""

    def test_records_plan_id(self) -> None:
        """Recording a plan_id adds it to executed_plans."""
        svc = _build_service()
        svc._record_executed_plan("plan-1")
        assert "plan-1" in svc.executed_plans

    def test_lru_eviction_at_capacity(self) -> None:
        """Oldest entry evicted when exceeding _EXECUTED_PLANS_MAX."""
        svc = _build_service()
        # Fill to capacity (100)
        for i in range(100):
            svc._record_executed_plan(f"plan-{i}")
        assert len(svc.executed_plans) == 100
        assert "plan-0" in svc.executed_plans

        # Add one more -- oldest (plan-0) should be evicted
        svc._record_executed_plan("plan-100")
        assert len(svc.executed_plans) == 100
        assert "plan-0" not in svc.executed_plans
        assert "plan-100" in svc.executed_plans

    def test_move_to_end_on_rerecord(self) -> None:
        """Re-recording an existing plan_id moves it to end (LRU)."""
        svc = _build_service()
        svc._record_executed_plan("a")
        svc._record_executed_plan("b")
        svc._record_executed_plan("a")  # Re-record 'a'

        keys = list(svc.executed_plans.keys())
        assert keys[-1] == "a"  # 'a' is now most recent


# ===========================================================================
# Tests: _handle_adapter_error()
# ===========================================================================


class TestHandleAdapterError:
    """Validate error severity to ProcessResult mapping."""

    def _make_exc(self) -> AdapterException:
        return AdapterException(
            AdapterError(
                severity=ErrorSeverity.DEGRADED,
                adapter_name="test",
                operation="op",
                error_code="ERR",
                error_message="fail",
            )
        )

    def test_terminal_returns_failed(self) -> None:
        """TERMINAL severity maps to FAILED."""
        router = FakeErrorRouter(severity=ErrorSeverity.TERMINAL)
        svc = _build_service(error_router=router)
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
        result = svc._handle_adapter_error(self._make_exc(), ctx)
        assert result == ProcessResult.FAILED

    def test_degraded_returns_degraded(self) -> None:
        """DEGRADED severity maps to DEGRADED."""
        router = FakeErrorRouter(severity=ErrorSeverity.DEGRADED)
        svc = _build_service(error_router=router)
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
        result = svc._handle_adapter_error(self._make_exc(), ctx)
        assert result == ProcessResult.DEGRADED

    def test_recoverable_returns_deferred(self) -> None:
        """RECOVERABLE severity maps to DEFERRED."""
        router = FakeErrorRouter(severity=ErrorSeverity.RECOVERABLE)
        svc = _build_service(error_router=router)
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
        result = svc._handle_adapter_error(self._make_exc(), ctx)
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

    def test_medium_no_plan_id_uses_from_medium(self) -> None:
        """plan_id=None delegates to AggregatedResult.from_medium()."""
        svc = _build_service()
        step_results = [
            StepResult(step_id="s1", capability_name="a", status=StepStatus.COMPLETED),
        ]
        result = svc.aggregate(step_results, None, [], "t1", 100)
        assert result.plan_id is None
        assert result.success is True
        assert result.total_steps == 1
        assert result.completed == 1
        assert result.duration_ms == 100

    def test_high_with_plan_id_uses_from_dag(self) -> None:
        """plan_id set delegates to AggregatedResult.from_dag()."""
        svc = _build_service()
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

    def test_empty_steps_succeeds(self) -> None:
        """Empty step_results -> success=True (0 failed, 0 cancelled)."""
        svc = _build_service()
        result = svc.aggregate([], None, [], "t1")
        assert result.success is True
        assert result.total_steps == 0

    def test_all_cancelled_no_success(self) -> None:
        """All cancelled -> success=False."""
        svc = _build_service()
        step_results = [
            StepResult(step_id="s1", capability_name="a", status=StepStatus.CANCELLED),
        ]
        result = svc.aggregate(step_results, None, [], "t1")
        assert result.success is False
        assert result.cancelled == 1

    def test_pure_function_no_side_effects(self) -> None:
        """aggregate() does not emit events or modify service state."""
        delta = FakeDeltaEmitPort()
        bridge = FakeBridgeWritePort()
        svc = _build_service(delta_port=delta, bridge_port=bridge)
        svc.aggregate(
            [StepResult(step_id="s1", capability_name="a", status=StepStatus.COMPLETED)],
            None,
            [],
            "t1",
            10,
        )
        # No events emitted -- aggregate is pure.
        assert len(delta.events) == 0
        assert len(bridge.audits) == 0

    def test_trace_id_propagated(self) -> None:
        """trace_id is propagated to AggregatedResult."""
        svc = _build_service()
        result = svc.aggregate([], None, [], "trace-xyz")
        assert result.trace_id == "trace-xyz"

    def test_duration_ms_propagated(self) -> None:
        """duration_ms is propagated to AggregatedResult."""
        svc = _build_service()
        result = svc.aggregate([], None, [], "t1", 12345)
        assert result.duration_ms == 12345

    def test_dag_with_compensations_and_skipped(self) -> None:
        """HIGH tier aggregate with mixed statuses and compensations."""
        svc = _build_service()
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
        delta = FakeDeltaEmitPort()
        engine = FakeWorkflowEngine(result=ProcessResult.COMPLETED)
        svc = _build_service(delta_port=delta, workflow_engine=engine)
        req = _make_workflow_save_request()
        result = await svc.process(req)

        assert result == ProcessResult.COMPLETED
        saved_events = delta.find(ORCH_WORKFLOW_SAVED)
        assert len(saved_events) == 1
        payload = saved_events[0]["payload"]
        assert payload["committed_plan_id"] == req.committed_plan_id
        assert payload["workflow_name"] == req.workflow_name
        assert "trigger_type" in payload
        assert "trace_id" in payload

    @pytest.mark.asyncio
    async def test_save_failure_no_delta(self) -> None:
        """Failed save does NOT emit ORCH_WORKFLOW_SAVED delta."""
        delta = FakeDeltaEmitPort()
        engine = FakeWorkflowEngine(result=ProcessResult.FAILED)
        svc = _build_service(delta_port=delta, workflow_engine=engine)
        req = _make_workflow_save_request()
        result = await svc.process(req)

        assert result == ProcessResult.FAILED
        saved_events = delta.find(ORCH_WORKFLOW_SAVED)
        assert len(saved_events) == 0

    @pytest.mark.asyncio
    async def test_save_adapter_error_no_delta(self) -> None:
        """AdapterException from engine does NOT emit delta."""
        delta = FakeDeltaEmitPort()
        engine = FakeWorkflowEngine()

        async def raise_save(request: WorkflowSaveRequest, ctx: ProcessingContext) -> ProcessResult:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.DEGRADED,
                    adapter_name="workflow_engine",
                    operation="save_workflow",
                    error_code="STORAGE",
                    error_message="Failed to save",
                )
            )

        engine.save_workflow = raise_save  # type: ignore[assignment]
        router = FakeErrorRouter(severity=ErrorSeverity.DEGRADED)
        svc = _build_service(delta_port=delta, workflow_engine=engine, error_router=router)
        req = _make_workflow_save_request()
        result = await svc.process(req)

        assert result == ProcessResult.DEGRADED
        saved_events = delta.find(ORCH_WORKFLOW_SAVED)
        assert len(saved_events) == 0

    @pytest.mark.asyncio
    async def test_save_delta_contains_trigger_type(self) -> None:
        """ORCH_WORKFLOW_SAVED delta payload includes trigger_type from spec."""
        delta = FakeDeltaEmitPort()
        engine = FakeWorkflowEngine(result=ProcessResult.COMPLETED)
        svc = _build_service(delta_port=delta, workflow_engine=engine)
        req = _make_workflow_save_request()
        await svc.process(req)

        saved_events = delta.find(ORCH_WORKFLOW_SAVED)
        assert saved_events[0]["payload"]["trigger_type"] == "MANUAL"


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

    def test_pending_plans_initially_empty(self) -> None:
        svc = _build_service()
        assert svc.pending_plans == {}

    def test_pending_hil_initially_empty(self) -> None:
        svc = _build_service()
        assert svc.pending_hil == {}

    def test_executed_plans_initially_empty(self) -> None:
        svc = _build_service()
        assert len(svc.executed_plans) == 0

    def test_config_returns_injected_config(self) -> None:
        cfg = _default_config(max_pending_plans=42)
        svc = _build_service(config=cfg)
        assert svc.config.max_pending_plans == 42


# ===========================================================================
# Tests: Edge cases and integration
# ===========================================================================


class TestEdgeCases:
    """Edge cases and full flow integration tests."""

    @pytest.mark.asyncio
    async def test_process_catches_uncaught_exception(self) -> None:
        """Unhandled exception in dispatch returns FAILED (never crashes)."""
        # WorkflowEngine that raises a raw RuntimeError (not AdapterException).
        engine = FakeWorkflowEngine()

        async def explode(request: WorkflowRunRequest, ctx: ProcessingContext) -> ProcessResult:
            raise RuntimeError("Unexpected boom")

        engine.execute_workflow = explode  # type: ignore[assignment]
        svc = _build_service(workflow_engine=engine)
        req = _make_workflow_run_request()
        result = await svc.process(req)
        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_full_high_tier_flow_dispatch_then_receive(self) -> None:
        """Full two-phase flow: dispatch_high -> receive_plan -> COMPLETED."""
        dag_result = AggregatedResult.from_medium(
            step_results=[
                StepResult(
                    step_id="s1",
                    capability_name="tool.test.a",
                    status=StepStatus.COMPLETED,
                    duration_ms=200,
                )
            ],
            trace_id="t1",
            duration_ms=250,
        )
        executor = FakeDAGExecutor(result=dag_result)
        planner = FakePlannerPort()
        guard = FakeConcurrencyGuard()
        delta = FakeDeltaEmitPort()
        svc = _build_service(
            dag_executor=executor,
            planner_port=planner,
            concurrency_guard=guard,
            delta_port=delta,
        )

        # Phase 1: dispatch_high
        envelope = _make_envelope(tier="HIGH")
        result1 = await svc.process(envelope)
        assert result1 == ProcessResult.DEFERRED
        assert len(svc.pending_plans) == 1

        # Extract the request_id that was sent
        sent_request_id = planner.requested[0].request_id

        # Phase 2: receive_plan
        plan = _make_plan(request_id=sent_request_id)
        result2 = await svc.process(plan)
        assert result2 == ProcessResult.COMPLETED
        assert len(svc.pending_plans) == 0
        assert plan.plan_id in svc.executed_plans

    @pytest.mark.asyncio
    async def test_adapter_error_caught_in_process(self) -> None:
        """AdapterException raised at process level is caught and classified."""
        router = FakeErrorRouter(severity=ErrorSeverity.RECOVERABLE)
        engine = FakeWorkflowEngine()

        async def raise_adapter(
            request: WorkflowRunRequest, ctx: ProcessingContext
        ) -> ProcessResult:
            raise AdapterException(
                AdapterError(
                    severity=ErrorSeverity.RECOVERABLE,
                    adapter_name="test",
                    operation="test",
                    error_code="TEST",
                    error_message="test error",
                )
            )

        engine.execute_workflow = raise_adapter  # type: ignore[assignment]
        svc = _build_service(error_router=router, workflow_engine=engine)
        req = _make_workflow_run_request()
        result = await svc.process(req)
        assert result == ProcessResult.DEFERRED  # RECOVERABLE -> DEFERRED
        assert len(router.classified) == 1
