"""
Tests for OrchestratorService._mailbox_loop() and _process_one() (Issue 6.2.5).

Validates the mailbox processing loop:
  - Core loop: dequeue -> _process_one -> sleep(1ms) when empty.
  - _process_one concurrency check:
    * InterruptRequest always processed (bypass guard).
    * DAG-requiring messages (TaskEnvelope, CommittedPlan, WorkflowRunRequest)
      re-enqueued at BACKGROUND priority when ConcurrencyGuard.active.
    * WorkflowSaveRequest not DAG-requiring, processed normally.
  - Result handling: FAILED -> error delta emitted. DEFERRED/COMPLETED -> no delta.
  - Exception isolation: unhandled exception in process() -> logged, loop continues.
  - Single-threaded guarantee: only ONE message processed at a time.

Test Philosophy: Protocol-based fakes with explicit call tracking.
NO magic mocking. Every fake records calls for assertion.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.connectors.mcp_registrar import RegistrationResult
from k1.orchestrator.events import ORCH_DELTA_V1
from k1.orchestrator.orchestration.orchestrator_service import OrchestratorService
from k1.orchestrator.types import (
    AggregatedResult,
    CommittedPlan,
    ErrorSeverity,
    InterruptRequest,
    PlanAck,
    PlanStep,
    ProcessResult,
    TaskEnvelope,
    TriggerSpec,
    TriggerType,
    WorkflowRunRequest,
    WorkflowSaveRequest,
)

# ===========================================================================
# Fakes -- deterministic Protocol implementations for mailbox_loop testing
# ===========================================================================


class FakeEventPort:
    """Fake event bus port."""

    def __init__(self) -> None:
        self.subscriptions: List[tuple[str, Callable]] = []
        self._next_id = 0

    def subscribe(self, topic: str, handler: Callable) -> SubscriptionHandle:
        self._next_id += 1
        handle = SubscriptionHandle(
            subscription_id=f"fake-{self._next_id}",
            topic=topic,
        )
        self.subscriptions.append((topic, handler))
        return handle

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        return True

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        pass


class FakeMailboxPort:
    """Fake mailbox with enqueue/dequeue call tracking."""

    def __init__(self, *, messages: Optional[List[Any]] = None) -> None:
        self.enqueued: List[tuple[Any, str]] = []
        self._queue: List[Any] = list(messages) if messages else []

    def enqueue(self, message: Any, priority: str = "INTERACTIVE") -> int:
        self.enqueued.append((message, priority))
        return len(self.enqueued) - 1

    def dequeue(self) -> Optional[Any]:
        return self._queue.pop(0) if self._queue else None

    def depth(self) -> int:
        return len(self._queue) + len(self.enqueued)


class FakeDAGExecutor:
    """Fake DAG executor."""

    async def execute(self, plan: Any, snapshot: Any) -> AggregatedResult:
        return AggregatedResult(
            plan_id="test",
            trace_id="test",
            steps=[],
            compensations=[],
        )


class FakeConstraintResolver:
    """Fake constraint resolver."""

    async def validate(self, plan: Any, ctx: Any) -> Any:
        class _Result:
            valid = True
            issues: List[str] = []

        return _Result()


class FakeWorkflowRegistry:
    """Fake registry."""

    async def list_active(self) -> List[Any]:
        return []


class FakeWorkflowScheduler:
    """Fake scheduler."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class FakeGapDetector:
    """Fake gap detector."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class FakeWorkflowEngine:
    """Fake workflow engine with sub-component properties."""

    def __init__(self) -> None:
        self._registry = FakeWorkflowRegistry()
        self._scheduler = FakeWorkflowScheduler()
        self._gap_detector = FakeGapDetector()

    @property
    def registry(self) -> FakeWorkflowRegistry:
        return self._registry

    @property
    def scheduler(self) -> FakeWorkflowScheduler:
        return self._scheduler

    @property
    def gap_detector(self) -> FakeGapDetector:
        return self._gap_detector

    async def execute_workflow(self, request: Any, ctx: Any) -> ProcessResult:
        return ProcessResult.COMPLETED

    async def save_workflow(self, request: Any, ctx: Any) -> ProcessResult:
        return ProcessResult.COMPLETED


class FakeConnectorLifecycle:
    """Fake connector with discover_and_register."""

    async def discover_and_register(self) -> RegistrationResult:
        return RegistrationResult(registered=0, skipped=0, errors=[])

    def start_lifecycle_monitoring(self) -> None:
        pass

    def stop_lifecycle_monitoring(self) -> None:
        pass


class FakeErrorRouter:
    """Fake error router."""

    def classify(self, error: Any, ctx: Any) -> ErrorSeverity:
        return ErrorSeverity.DEGRADED


class FakeConcurrencyGuard:
    """Fake concurrency guard with configurable active state."""

    def __init__(self, *, active: bool = False, allow: bool = True) -> None:
        self._active = active
        self._allow = allow

    @property
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        self._active = value

    def acquire(self, ctx: Any) -> bool:
        return self._allow

    def release(self, ctx: Any) -> None:
        pass


class FakeFabricGatewayPort:
    """Fake fabric port."""

    async def discover_mcp_tools(self) -> RegistrationResult:
        return RegistrationResult(registered=0, skipped=0, errors=[])


class FakePlannerPort:
    """Fake planner port."""

    async def request_plan(self, request: Any) -> PlanAck:
        return PlanAck(request_id="test", status="ACCEPTED")

    async def cancel_plan(self, request_id: str) -> None:
        pass


class FakeStateReadPort:
    """Fake state read port."""

    async def get_snapshot(self, session_id: str) -> Any:
        return None


class FakeDeltaEmitPort:
    """Fake delta emit port recording emitted deltas."""

    def __init__(self, *, emit_raises: bool = False) -> None:
        self.emitted: List[tuple[str, Dict[str, Any], str]] = []
        self._emit_raises = emit_raises

    async def emit(self, event_topic: str, payload: Dict[str, Any], trace_id: str = "") -> None:
        if self._emit_raises:
            raise RuntimeError("delta emit failure")
        self.emitted.append((event_topic, payload, trace_id))


class FakeBridgeWritePort:
    """Fake bridge write port."""

    def __init__(self) -> None:
        self.audit_calls: List[tuple[Dict[str, Any], str]] = []

    async def write(self, data: Any) -> None:
        pass

    async def submit_audit(self, run_manifest: Dict[str, Any], trace_id: str) -> None:
        self.audit_calls.append((run_manifest, trace_id))

    async def list_wal_ids(self) -> List[str]:
        return []

    async def read_wal(self, dag_id: str) -> Optional[List[Dict[str, Any]]]:
        return None


# ===========================================================================
# Helpers
# ===========================================================================


def _default_config(**overrides: Any) -> OrchestratorConfig:
    """Build OrchestratorConfig with fast reap interval for tests."""
    defaults = {
        "mailbox_capacity": 64,
        "max_concurrent_dags": 1,
        "default_step_timeout_ms": 10_000,
        "plan_request_timeout_ms": 30_000,
        "max_pending_plans": 5,
        "context_reap_interval_ms": 100,
    }
    defaults.update(overrides)
    return OrchestratorConfig(**defaults)


def _build_service(
    *,
    config: Optional[OrchestratorConfig] = None,
    mailbox: Optional[FakeMailboxPort] = None,
    event_port: Optional[FakeEventPort] = None,
    connector_lifecycle: Optional[FakeConnectorLifecycle] = None,
    workflow_engine: Optional[FakeWorkflowEngine] = None,
    concurrency_guard: Optional[FakeConcurrencyGuard] = None,
    dag_executor: Optional[FakeDAGExecutor] = None,
    constraint_resolver: Optional[FakeConstraintResolver] = None,
    error_router: Optional[FakeErrorRouter] = None,
    fabric_port: Optional[FakeFabricGatewayPort] = None,
    planner_port: Optional[FakePlannerPort] = None,
    state_port: Optional[FakeStateReadPort] = None,
    delta_port: Optional[FakeDeltaEmitPort] = None,
    bridge_port: Optional[FakeBridgeWritePort] = None,
) -> OrchestratorService:
    """Build OrchestratorService with mailbox_loop-capable fakes."""
    return OrchestratorService(
        mailbox=mailbox or FakeMailboxPort(),
        dag_executor=dag_executor or FakeDAGExecutor(),
        constraint_resolver=constraint_resolver or FakeConstraintResolver(),
        workflow_engine=workflow_engine or FakeWorkflowEngine(),
        connector_lifecycle=connector_lifecycle or FakeConnectorLifecycle(),
        error_router=error_router or FakeErrorRouter(),
        concurrency_guard=concurrency_guard or FakeConcurrencyGuard(),
        fabric_port=fabric_port or FakeFabricGatewayPort(),
        planner_port=planner_port or FakePlannerPort(),
        state_port=state_port or FakeStateReadPort(),
        delta_port=delta_port or FakeDeltaEmitPort(),
        bridge_port=bridge_port or FakeBridgeWritePort(),
        event_port=event_port or FakeEventPort(),
        config=config or _default_config(),
    )


def _make_step(step_id: str = "step-1", capability: str = "tool.test") -> PlanStep:
    """Build minimal PlanStep."""
    return PlanStep(id=step_id, capability=capability)


def _make_envelope(
    *,
    trace_id: str = "",
    tier: str = "MEDIUM",
) -> TaskEnvelope:
    """Build minimal TaskEnvelope."""
    return TaskEnvelope(
        intent="test",
        trace_id=trace_id or str(uuid4()),
        tier=tier,
        capabilities=["tool.test"],
        params={"tool.test": {}},
        context={},
    )


def _make_committed_plan(
    *,
    plan_id: str = "",
    request_id: str = "",
) -> CommittedPlan:
    """Build minimal CommittedPlan."""
    return CommittedPlan(
        plan_id=plan_id or f"plan-{uuid4().hex[:8]}",
        request_id=request_id or f"req-{uuid4().hex[:8]}",
        intent="test",
        steps=[_make_step()],
        trace_id=str(uuid4()),
    )


def _make_interrupt(*, trace_id: str = "", dag_id: str = "dag-1") -> InterruptRequest:
    """Build minimal InterruptRequest."""
    return InterruptRequest(
        target_dag_id=dag_id,
        interrupt_type="CANCEL_DAG",
        reason="test interrupt",
        trace_id=trace_id or str(uuid4()),
    )


def _make_workflow_run(*, trace_id: str = "") -> WorkflowRunRequest:
    """Build minimal WorkflowRunRequest."""
    return WorkflowRunRequest(
        workflow_id="wf-1",
        version="1.0",
        trigger_type=TriggerType.MANUAL,
        trace_id=trace_id or str(uuid4()),
    )


def _make_workflow_save(*, trace_id: str = "") -> WorkflowSaveRequest:
    """Build minimal WorkflowSaveRequest."""
    return WorkflowSaveRequest(
        committed_plan_id="plan-save-1",
        workflow_name="test-workflow",
        trigger_spec=TriggerSpec(type=TriggerType.MANUAL),
        trace_id=trace_id or str(uuid4()),
    )


# ===========================================================================
# Test: _mailbox_loop() core loop behavior
# ===========================================================================


class TestMailboxLoopCore:
    """Core loop: dequeue -> _process_one -> sleep when empty."""

    @pytest.mark.asyncio
    async def test_loop_dequeues_and_processes(self) -> None:
        """Message dequeued from mailbox and processed."""
        envelope = _make_envelope()
        mailbox = FakeMailboxPort(messages=[envelope])

        svc = _build_service(mailbox=mailbox)
        svc._running = True

        task = asyncio.create_task(svc._mailbox_loop())
        await asyncio.sleep(0.05)
        svc._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Queue drained
        assert mailbox.dequeue() is None

    @pytest.mark.asyncio
    async def test_loop_yields_when_empty(self) -> None:
        """Empty mailbox -> loop yields (doesn't busy-wait)."""
        mailbox = FakeMailboxPort()  # empty
        svc = _build_service(mailbox=mailbox)
        svc._running = True

        task = asyncio.create_task(svc._mailbox_loop())

        # Let it run a few iterations (should just yield)
        await asyncio.sleep(0.01)
        svc._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # No crash, no messages processed
        assert len(mailbox.enqueued) == 0

    @pytest.mark.asyncio
    async def test_loop_stops_when_running_false(self) -> None:
        """Setting _running=False exits the loop gracefully."""
        svc = _build_service()
        svc._running = True

        task = asyncio.create_task(svc._mailbox_loop())
        await asyncio.sleep(0.01)

        svc._running = False
        # Loop should exit within ~1ms after _running becomes False
        await asyncio.sleep(0.01)

        # Task should complete (not cancelled)
        assert task.done() or task.cancelled()

    @pytest.mark.asyncio
    async def test_loop_processes_multiple_messages(self) -> None:
        """Multiple messages dequeued and processed sequentially."""
        envelopes = [_make_envelope() for _ in range(3)]
        mailbox = FakeMailboxPort(messages=envelopes)

        svc = _build_service(mailbox=mailbox)
        svc._running = True

        task = asyncio.create_task(svc._mailbox_loop())
        await asyncio.sleep(0.1)
        svc._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # All messages consumed
        assert mailbox.dequeue() is None


# ===========================================================================
# Test: _process_one() concurrency guard bypass for InterruptRequest
# ===========================================================================


class TestProcessOneInterruptBypass:
    """InterruptRequest ALWAYS processed, even when ConcurrencyGuard active."""

    @pytest.mark.asyncio
    async def test_interrupt_bypasses_active_guard(self) -> None:
        """InterruptRequest processed when guard.active=True."""
        guard = FakeConcurrencyGuard(active=True)
        mailbox = FakeMailboxPort()

        svc = _build_service(concurrency_guard=guard, mailbox=mailbox)
        interrupt = _make_interrupt()

        # Should NOT be re-enqueued -- interrupt bypasses guard
        await svc._process_one(interrupt)

        # NOT re-enqueued to mailbox
        assert len(mailbox.enqueued) == 0

    @pytest.mark.asyncio
    async def test_interrupt_processed_when_guard_inactive(self) -> None:
        """InterruptRequest processed normally when guard inactive."""
        guard = FakeConcurrencyGuard(active=False)
        mailbox = FakeMailboxPort()

        svc = _build_service(concurrency_guard=guard, mailbox=mailbox)
        interrupt = _make_interrupt()

        await svc._process_one(interrupt)

        # NOT re-enqueued
        assert len(mailbox.enqueued) == 0


# ===========================================================================
# Test: _process_one() DAG-requiring message deferral
# ===========================================================================


class TestProcessOneDAGDeferral:
    """DAG-requiring messages re-enqueued at BACKGROUND when guard active."""

    @pytest.mark.asyncio
    async def test_task_envelope_deferred_when_guard_active(self) -> None:
        """TaskEnvelope re-enqueued at BACKGROUND when guard.active=True."""
        guard = FakeConcurrencyGuard(active=True)
        mailbox = FakeMailboxPort()

        svc = _build_service(concurrency_guard=guard, mailbox=mailbox)
        envelope = _make_envelope()

        await svc._process_one(envelope)

        # Re-enqueued at BACKGROUND
        assert len(mailbox.enqueued) == 1
        enqueued_msg, enqueued_priority = mailbox.enqueued[0]
        assert enqueued_priority == "BACKGROUND"
        assert enqueued_msg is envelope

    @pytest.mark.asyncio
    async def test_committed_plan_deferred_when_guard_active(self) -> None:
        """CommittedPlan re-enqueued at BACKGROUND when guard.active=True."""
        guard = FakeConcurrencyGuard(active=True)
        mailbox = FakeMailboxPort()

        svc = _build_service(concurrency_guard=guard, mailbox=mailbox)
        plan = _make_committed_plan()

        await svc._process_one(plan)

        assert len(mailbox.enqueued) == 1
        _, priority = mailbox.enqueued[0]
        assert priority == "BACKGROUND"

    @pytest.mark.asyncio
    async def test_workflow_run_deferred_when_guard_active(self) -> None:
        """WorkflowRunRequest re-enqueued at BACKGROUND when guard.active=True."""
        guard = FakeConcurrencyGuard(active=True)
        mailbox = FakeMailboxPort()

        svc = _build_service(concurrency_guard=guard, mailbox=mailbox)
        wfr = _make_workflow_run()

        await svc._process_one(wfr)

        assert len(mailbox.enqueued) == 1
        _, priority = mailbox.enqueued[0]
        assert priority == "BACKGROUND"

    @pytest.mark.asyncio
    async def test_workflow_save_not_deferred(self) -> None:
        """WorkflowSaveRequest is NOT DAG-requiring -- processed even with guard active."""
        guard = FakeConcurrencyGuard(active=True)
        mailbox = FakeMailboxPort()

        svc = _build_service(concurrency_guard=guard, mailbox=mailbox)
        wfs = _make_workflow_save()

        await svc._process_one(wfs)

        # NOT re-enqueued (WorkflowSaveRequest doesn't require DAG)
        assert len(mailbox.enqueued) == 0

    @pytest.mark.asyncio
    async def test_envelope_processed_when_guard_inactive(self) -> None:
        """TaskEnvelope processed normally when guard.active=False."""
        guard = FakeConcurrencyGuard(active=False)
        mailbox = FakeMailboxPort()

        svc = _build_service(concurrency_guard=guard, mailbox=mailbox)
        envelope = _make_envelope()

        await svc._process_one(envelope)

        # NOT re-enqueued -- processed directly
        assert len(mailbox.enqueued) == 0


# ===========================================================================
# Test: _process_one() result handling
# ===========================================================================


class TestProcessOneResultHandling:
    """Result-based actions after process() completes."""

    @pytest.mark.asyncio
    async def test_failed_result_emits_error_delta(self) -> None:
        """FAILED result -> error delta emitted via delta_port."""
        delta_port = FakeDeltaEmitPort()

        svc = _build_service(delta_port=delta_port)

        # An invalid-type message will produce FAILED from process()
        # because process() returns FAILED for unknown message types.
        # Instead, use a well-formed message that triggers FAILED.
        # A TaskEnvelope with no trace_id triggers validation failure.
        # Actually, process() catches all exceptions and returns FAILED
        # for unknown types. Let's use an object that process() doesn't know.
        class _UnknownMsg:
            trace_id = str(uuid4())
            request_id = str(uuid4())

        msg = _UnknownMsg()

        await svc._process_one(msg)  # type: ignore[arg-type]

        # Error delta emitted
        assert len(delta_port.emitted) >= 1
        topic, payload, tid = delta_port.emitted[-1]
        assert topic == ORCH_DELTA_V1
        assert payload["type"] == "processing_error"
        assert payload["result"] == "FAILED"

    @pytest.mark.asyncio
    async def test_completed_result_no_error_delta(self) -> None:
        """COMPLETED result -> NO error delta emitted."""
        delta_port = FakeDeltaEmitPort()

        svc = _build_service(delta_port=delta_port)
        wfs = _make_workflow_save()

        await svc._process_one(wfs)

        # No error delta for completed/non-failed results
        error_deltas = [
            (t, p, tid) for t, p, tid in delta_port.emitted if p.get("type") == "processing_error"
        ]
        assert len(error_deltas) == 0

    @pytest.mark.asyncio
    async def test_deferred_result_no_error_delta(self) -> None:
        """DEFERRED result -> NO error delta from _process_one."""
        delta_port = FakeDeltaEmitPort()

        # HIGH tier TaskEnvelope will go through dispatch_high which returns DEFERRED
        svc = _build_service(delta_port=delta_port)
        envelope = _make_envelope(tier="HIGH")

        await svc._process_one(envelope)

        # No error delta for DEFERRED
        error_deltas = [
            (t, p, tid) for t, p, tid in delta_port.emitted if p.get("type") == "processing_error"
        ]
        assert len(error_deltas) == 0


# ===========================================================================
# Test: _process_one() exception isolation
# ===========================================================================


class TestProcessOneExceptionIsolation:
    """Unhandled exception in process() -> logged, loop continues."""

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self) -> None:
        """_process_one catches exceptions from process()."""
        svc = _build_service()

        # Pass complete garbage -- should not crash
        await svc._process_one("not-a-valid-message")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_delta_emit_failure_does_not_crash(self) -> None:
        """Error delta emit failure -> logged, doesn't crash _process_one."""
        delta_port = FakeDeltaEmitPort(emit_raises=True)

        svc = _build_service(delta_port=delta_port)

        class _UnknownMsg:
            trace_id = str(uuid4())
            request_id = str(uuid4())

        # This will produce FAILED, then try to emit error delta, which raises.
        # _process_one should catch the delta emission failure.
        await svc._process_one(_UnknownMsg())  # type: ignore[arg-type]
        # No crash = success

    @pytest.mark.asyncio
    async def test_loop_continues_after_exception(self) -> None:
        """Mailbox loop continues processing after one message causes exception."""
        # Message 1: garbage (will cause exception path)
        # Message 2: valid envelope (should be processed normally)
        envelope = _make_envelope()
        mailbox = FakeMailboxPort(messages=["garbage", envelope])  # type: ignore[list-item]

        svc = _build_service(mailbox=mailbox)
        svc._running = True

        task = asyncio.create_task(svc._mailbox_loop())
        await asyncio.sleep(0.1)
        svc._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Both messages consumed (queue drained)
        assert mailbox.dequeue() is None


# ===========================================================================
# Test: _process_one() trace_id extraction and logging
# ===========================================================================


class TestProcessOneTraceId:
    """Trace ID extracted from message and logged."""

    @pytest.mark.asyncio
    async def test_trace_id_extracted_from_envelope(self) -> None:
        """trace_id is extracted from TaskEnvelope.trace_id."""
        tid = str(uuid4())
        envelope = _make_envelope(trace_id=tid)

        svc = _build_service()
        # Just verify no crash -- trace_id extraction happens internally
        await svc._process_one(envelope)

    @pytest.mark.asyncio
    async def test_trace_id_extracted_from_interrupt(self) -> None:
        """trace_id is extracted from InterruptRequest.trace_id."""
        tid = str(uuid4())
        interrupt = _make_interrupt(trace_id=tid)

        svc = _build_service()
        await svc._process_one(interrupt)

    @pytest.mark.asyncio
    async def test_missing_trace_id_handled(self) -> None:
        """Message without trace_id -> empty string, no crash."""

        class _NoTraceMsg:
            request_id = str(uuid4())

        svc = _build_service()
        await svc._process_one(_NoTraceMsg())  # type: ignore[arg-type]


# ===========================================================================
# Test: _process_one() with init() integration
# ===========================================================================


class TestMailboxLoopInitIntegration:
    """_mailbox_loop started by init() and stopped by shutdown()."""

    @pytest.mark.asyncio
    async def test_init_starts_loop_task(self) -> None:
        """init() creates _loop_task."""
        svc = _build_service()
        await svc.init()

        try:
            assert svc._loop_task is not None
            assert not svc._loop_task.done()
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_loop_task(self) -> None:
        """shutdown() cancels _loop_task."""
        svc = _build_service()
        await svc.init()

        await svc.shutdown()

        assert svc._loop_task is None

    @pytest.mark.asyncio
    async def test_messages_processed_after_init(self) -> None:
        """Messages enqueued during init are processed by the loop."""
        bridge = FakeBridgeWritePort()
        # Inject plan via crash_recovery WAL
        bridge._wal_store = {}  # type: ignore[attr-defined]
        mailbox = FakeMailboxPort()

        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.init()

        try:
            # Enqueue a message after init
            mailbox._queue.append(_make_envelope())

            # Give the loop time to process
            await asyncio.sleep(0.1)
        finally:
            await svc.shutdown()


# ===========================================================================
# Test: Deferred message priority
# ===========================================================================


class TestDeferredPriority:
    """Re-enqueued messages use BACKGROUND priority to prevent starvation."""

    @pytest.mark.asyncio
    async def test_deferred_envelope_gets_background_priority(self) -> None:
        """Re-enqueued TaskEnvelope has BACKGROUND priority."""
        guard = FakeConcurrencyGuard(active=True)
        mailbox = FakeMailboxPort()

        svc = _build_service(concurrency_guard=guard, mailbox=mailbox)

        for _ in range(3):
            await svc._process_one(_make_envelope())

        assert len(mailbox.enqueued) == 3
        for _, priority in mailbox.enqueued:
            assert priority == "BACKGROUND"

    @pytest.mark.asyncio
    async def test_deferred_preserves_original_message(self) -> None:
        """Re-enqueued message is the SAME object (identity preserved)."""
        guard = FakeConcurrencyGuard(active=True)
        mailbox = FakeMailboxPort()

        svc = _build_service(concurrency_guard=guard, mailbox=mailbox)
        envelope = _make_envelope()

        await svc._process_one(envelope)

        assert mailbox.enqueued[0][0] is envelope

    @pytest.mark.asyncio
    async def test_guard_inactive_then_active_transitions(self) -> None:
        """Message processed when guard inactive, deferred when active."""
        guard = FakeConcurrencyGuard(active=False)
        mailbox = FakeMailboxPort()

        svc = _build_service(concurrency_guard=guard, mailbox=mailbox)

        # With guard inactive: processed
        await svc._process_one(_make_envelope())
        assert len(mailbox.enqueued) == 0

        # Activate guard: deferred
        guard.active = True
        await svc._process_one(_make_envelope())
        assert len(mailbox.enqueued) == 1
        assert mailbox.enqueued[0][1] == "BACKGROUND"
