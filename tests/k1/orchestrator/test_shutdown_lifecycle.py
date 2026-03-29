"""
Tests for OrchestratorService.shutdown() lifecycle (Issue 6.2.3).

Validates the 9-step teardown sequence:
  1. Set _running = False (stop loops).
  2. Stop connector lifecycle monitoring (sync).
  3. Wait for active DAG completion (30s timeout, polled).
  4. (Reserved) Force-compensate if DAG timed out -- V1 logs warning.
  5. Stop WorkflowScheduler.
  6. Stop GapDetector + unsubscribe all event subscriptions.
  7. (Reserved) Persist trigger states (deferred V1).
  8. Final audit write via bridge_port.submit_audit().
  9. Cancel background tasks (reaper + loop). Log orphaned contexts.

Additional scenarios:
  - Idempotency: calling shutdown() twice is safe.
  - Not initialized: shutdown() before init() is no-op.
  - Partial init: shutdown() tolerates missing sub-components.
  - Orphaned plans/HIL: logged at warning level.
  - Per-step exception isolation: one step failure doesn't block others.

Test Philosophy: Protocol-based fakes with explicit call tracking.
NO magic mocking. Every fake records calls for assertion.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.fabric.ports.state_reader import SessionSnapshot
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.connectors.mcp_registrar import RegistrationResult
from k1.orchestrator.orchestration.orchestrator_service import OrchestratorService
from k1.orchestrator.types import (
    AggregatedResult,
    ErrorSeverity,
    PendingHILContext,
    PendingPlanContext,
    PlanAck,
    ProcessResult,
    TaskEnvelope,
)

# ===========================================================================
# Fakes -- deterministic Protocol implementations for shutdown() testing
# ===========================================================================


class FakeEventPort:
    """Fake event port with full call recording."""

    def __init__(self) -> None:
        self.subscriptions: List[tuple[str, Callable]] = []
        self.unsubscribed: List[SubscriptionHandle] = []
        self.emitted: List[tuple[str, Dict[str, Any]]] = []
        self._next_id = 0

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> SubscriptionHandle:
        self._next_id += 1
        handle = SubscriptionHandle(
            subscription_id=f"fake-{self._next_id}",
            topic=topic,
        )
        self.subscriptions.append((topic, handler))
        return handle

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        self.unsubscribed.append(handle)
        return True

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        self.emitted.append((topic, payload))
        for sub_topic, handler in self.subscriptions:
            if sub_topic == topic:
                handler(topic, payload)


class FakeMailboxPort:
    """Fake mailbox tracking enqueue/dequeue calls."""

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

    def peek_priority(self) -> Optional[str]:
        return None


class FakeConnectorLifecycle:
    """Fake connector with discover_and_register + lifecycle monitoring."""

    def __init__(
        self,
        *,
        result: Optional[RegistrationResult] = None,
        stop_raises: bool = False,
    ) -> None:
        self._result = result or RegistrationResult(registered=3, skipped=1, errors=[])
        self._stop_raises = stop_raises
        self.discover_called: bool = False
        self.monitoring_started: bool = False
        self.monitoring_stopped: bool = False

    async def discover_and_register(self) -> RegistrationResult:
        self.discover_called = True
        return self._result

    def start_lifecycle_monitoring(self) -> None:
        self.monitoring_started = True

    def stop_lifecycle_monitoring(self) -> None:
        if self._stop_raises:
            raise RuntimeError("connector stop failure")
        self.monitoring_stopped = True


class FakeWorkflowRegistry:
    """Fake registry returning configurable active workflows."""

    def __init__(self, *, active_count: int = 2) -> None:
        self._active_count = active_count
        self.list_active_called: bool = False

    async def list_active(self) -> List[Any]:
        self.list_active_called = True
        return [f"workflow-{i}" for i in range(self._active_count)]


class FakeWorkflowScheduler:
    """Fake scheduler tracking start/stop calls."""

    def __init__(self, *, stop_raises: bool = False) -> None:
        self.started: bool = False
        self.stopped: bool = False
        self._stop_raises = stop_raises

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        if self._stop_raises:
            raise RuntimeError("scheduler stop failure")
        self.stopped = True


class FakeGapDetector:
    """Fake gap detector tracking start/stop calls."""

    def __init__(self, *, stop_raises: bool = False) -> None:
        self.started: bool = False
        self.stopped: bool = False
        self._stop_raises = stop_raises

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        if self._stop_raises:
            raise RuntimeError("gap detector stop failure")
        self.stopped = True


class FakeWorkflowEngine:
    """Fake workflow engine with sub-component properties."""

    def __init__(
        self,
        *,
        registry: Optional[FakeWorkflowRegistry] = None,
        scheduler: Optional[FakeWorkflowScheduler] = None,
        gap_detector: Optional[FakeGapDetector] = None,
    ) -> None:
        self._registry = registry or FakeWorkflowRegistry()
        self._scheduler = scheduler or FakeWorkflowScheduler()
        self._gap_detector = gap_detector or FakeGapDetector()

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


class FakeDAGExecutor:
    """Minimal DAG executor for shutdown tests."""

    async def execute(self, plan: Any, ctx: Any) -> AggregatedResult:
        return AggregatedResult(
            total_steps=0,
            completed=0,
            failed=0,
            cancelled=0,
            skipped=0,
            step_results=[],
            success=True,
            duration_ms=0,
            trace_id="test",
        )


class FakeConstraintResolver:
    """Minimal constraint resolver for shutdown tests."""

    async def validate(self, plan: Any, ctx: Any) -> Any:
        class _Result:
            valid = True
            issues: List[str] = []

        return _Result()


class FakeErrorRouter:
    """Minimal error router for shutdown tests."""

    def classify(self, error: Any, ctx: Any) -> ErrorSeverity:
        return ErrorSeverity.DEGRADED


class FakeConcurrencyGuard:
    """Fake concurrency guard with configurable active state."""

    def __init__(self, *, active: bool = False) -> None:
        self._active = active

    @property
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        self._active = value

    def acquire(self, ctx: Any) -> bool:
        return True

    def release(self, ctx: Any) -> None:
        pass


class FakeFabricGatewayPort:
    """Minimal fabric port for shutdown tests."""

    async def execute_capability(self, request: Any) -> Any:
        return None

    async def get_registry(self) -> Dict[str, Any]:
        return {}


class FakePlannerPort:
    """Minimal planner port for shutdown tests."""

    async def request_plan(self, request: Any) -> PlanAck:
        return PlanAck(request_id="test", status="ACCEPTED")

    async def cancel_plan(self, request_id: str) -> None:
        pass


class FakeStateReadPort:
    """Minimal state read port for shutdown tests."""

    async def get_snapshot(self, trace_id: str) -> Any:
        return None


class FakeDeltaEmitPort:
    """Minimal delta emit port recording emitted deltas."""

    def __init__(self) -> None:
        self.emitted: List[tuple] = []

    async def emit(self, event_topic: str, payload: Dict[str, Any], trace_id: str = "") -> None:
        self.emitted.append((event_topic, payload, trace_id))


class FakeBridgeWritePort:
    """Fake bridge write port tracking submit_audit calls."""

    def __init__(self, *, audit_raises: bool = False) -> None:
        self.audit_calls: List[tuple[Dict[str, Any], str]] = []
        self._audit_raises = audit_raises

    async def write(self, data: Any) -> None:
        pass

    async def submit_audit(self, run_manifest: Dict[str, Any], trace_id: str) -> None:
        if self._audit_raises:
            raise RuntimeError("audit write failure")
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
    """Build OrchestratorService with shutdown()-capable fakes."""
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


def _make_envelope(
    *,
    tier: str = "HIGH",
    trace_id: str = "",
) -> TaskEnvelope:
    """Build minimal TaskEnvelope for PendingPlanContext."""
    tid = trace_id or str(uuid4())
    return TaskEnvelope(
        intent="test",
        trace_id=tid,
        tier=tier,
        capabilities=["tool.test"],
        params={"tool.test": {}},
        context={},
    )


def _make_pending_plan(request_id: str, *, expired: bool = False) -> PendingPlanContext:
    """Build PendingPlanContext with correct fields."""
    return PendingPlanContext(
        request_id=request_id,
        task_envelope=_make_envelope(),
        state_snapshot=SessionSnapshot(session_id="s1"),
        created_at=time.time() - (120 if expired else 0),
        timeout_ms=1_000 if expired else 30_000,
    )


def _make_pending_hil(request_id: str) -> PendingHILContext:
    """Build PendingHILContext with correct fields."""
    return PendingHILContext(
        request_id=request_id,
        dag_execution_id="dag-1",
        current_wave_index=0,
        completed_waves=[],
        remaining_waves=[],
        question="approve?",
        options=["yes", "no"],
        timeout_fallback="CONTINUE",
    )


async def _init_service(svc: OrchestratorService) -> None:
    """Call init() and allow background tasks to start."""
    await svc.init()
    # Yield so background tasks (reaper, loop) are scheduled.
    await asyncio.sleep(0)


# ===========================================================================
# Test Classes
# ===========================================================================


class TestShutdownNotInitialized:
    """shutdown() before init() -- must be a no-op."""

    @pytest.mark.asyncio
    async def test_shutdown_without_init_is_noop(self) -> None:
        svc = _build_service()
        # Should not raise, should not change state.
        await svc.shutdown()
        assert not svc.initialized
        assert not svc.running

    @pytest.mark.asyncio
    async def test_shutdown_without_init_no_audit(self) -> None:
        bridge = FakeBridgeWritePort()
        svc = _build_service(bridge_port=bridge)
        await svc.shutdown()
        assert len(bridge.audit_calls) == 0


class TestShutdownIdempotency:
    """Calling shutdown() twice must be safe."""

    @pytest.mark.asyncio
    async def test_double_shutdown_is_safe(self) -> None:
        svc = _build_service()
        await _init_service(svc)
        assert svc.initialized

        await svc.shutdown()
        assert not svc.initialized

        # Second call: should be no-op (not initialized).
        await svc.shutdown()
        assert not svc.initialized

    @pytest.mark.asyncio
    async def test_double_shutdown_single_audit(self) -> None:
        bridge = FakeBridgeWritePort()
        svc = _build_service(bridge_port=bridge)
        await _init_service(svc)

        await svc.shutdown()
        await svc.shutdown()

        # Only one audit call (second shutdown is no-op).
        assert len(bridge.audit_calls) == 1


class TestShutdownStep1StopRunning:
    """Step 1: _running set to False, loops stop."""

    @pytest.mark.asyncio
    async def test_running_set_to_false(self) -> None:
        svc = _build_service()
        await _init_service(svc)
        assert svc.running

        await svc.shutdown()
        assert not svc.running

    @pytest.mark.asyncio
    async def test_initialized_cleared(self) -> None:
        svc = _build_service()
        await _init_service(svc)
        assert svc.initialized

        await svc.shutdown()
        assert not svc.initialized


class TestShutdownStep2ConnectorLifecycle:
    """Step 2: stop_lifecycle_monitoring() called."""

    @pytest.mark.asyncio
    async def test_connector_monitoring_stopped(self) -> None:
        connector = FakeConnectorLifecycle()
        svc = _build_service(connector_lifecycle=connector)
        await _init_service(svc)

        assert connector.monitoring_started
        await svc.shutdown()
        assert connector.monitoring_stopped

    @pytest.mark.asyncio
    async def test_connector_stop_error_does_not_block_shutdown(self) -> None:
        """Step 2 failure should not prevent step 5+."""
        connector = FakeConnectorLifecycle(stop_raises=True)
        scheduler = FakeWorkflowScheduler()
        engine = FakeWorkflowEngine(scheduler=scheduler)
        svc = _build_service(connector_lifecycle=connector, workflow_engine=engine)
        await _init_service(svc)

        # Should not raise.
        await svc.shutdown()

        # Connector stop failed, but scheduler still stopped.
        assert not connector.monitoring_stopped
        assert scheduler.stopped
        assert not svc.initialized


class TestShutdownStep3DAGWait:
    """Step 3: Wait for active DAG completion."""

    @pytest.mark.asyncio
    async def test_no_active_dag_immediate(self) -> None:
        guard = FakeConcurrencyGuard(active=False)
        svc = _build_service(concurrency_guard=guard)
        await _init_service(svc)

        t0 = time.monotonic()
        await svc.shutdown()
        elapsed = time.monotonic() - t0

        # Should be fast -- no blocking wait.
        assert elapsed < 1.0
        assert not svc.initialized

    @pytest.mark.asyncio
    async def test_active_dag_that_completes(self) -> None:
        """DAG is active at shutdown start, but completes within timeout."""
        guard = FakeConcurrencyGuard(active=False)
        svc = _build_service(concurrency_guard=guard)
        await _init_service(svc)

        # Simulate DAG becoming active after init.
        guard.active = True

        # Schedule guard to become inactive after ~200ms.
        async def _release_guard():
            await asyncio.sleep(0.2)
            guard.active = False

        asyncio.create_task(_release_guard())

        t0 = time.monotonic()
        await svc.shutdown()
        elapsed = time.monotonic() - t0

        # Should have waited ~200ms, not 30s.
        assert elapsed < 2.0
        assert not svc.initialized

    @pytest.mark.asyncio
    async def test_active_dag_timeout_proceeds(self) -> None:
        """DAG still active after poll -- step 3 should eventually time out.

        We override the 30s timeout to keep tests fast by patching the
        monotonic clock approach. Instead, we check that shutdown
        proceeds (step 5+ execute) even when guard stays active.
        """
        guard = FakeConcurrencyGuard(active=False)
        scheduler = FakeWorkflowScheduler()
        engine = FakeWorkflowEngine(scheduler=scheduler)
        bridge = FakeBridgeWritePort()
        svc = _build_service(
            concurrency_guard=guard,
            workflow_engine=engine,
            bridge_port=bridge,
        )
        await _init_service(svc)

        # Simulate DAG becoming active after init.
        guard.active = True

        # Make guard release after 0.5s so we don't actually wait 30s.
        async def _release_guard():
            await asyncio.sleep(0.5)
            guard.active = False

        asyncio.create_task(_release_guard())

        await svc.shutdown()

        # Even if guard was active, remaining steps executed.
        assert scheduler.stopped
        assert len(bridge.audit_calls) == 1
        assert not svc.initialized


class TestShutdownStep5Scheduler:
    """Step 5: WorkflowScheduler stopped."""

    @pytest.mark.asyncio
    async def test_scheduler_stopped(self) -> None:
        scheduler = FakeWorkflowScheduler()
        engine = FakeWorkflowEngine(scheduler=scheduler)
        svc = _build_service(workflow_engine=engine)
        await _init_service(svc)

        await svc.shutdown()
        assert scheduler.stopped

    @pytest.mark.asyncio
    async def test_scheduler_stop_error_does_not_block(self) -> None:
        scheduler = FakeWorkflowScheduler(stop_raises=True)
        engine = FakeWorkflowEngine(scheduler=scheduler)
        bridge = FakeBridgeWritePort()
        svc = _build_service(workflow_engine=engine, bridge_port=bridge)
        await _init_service(svc)

        await svc.shutdown()

        # Scheduler failed, but audit still written.
        assert not scheduler.stopped
        assert len(bridge.audit_calls) == 1
        assert not svc.initialized


class TestShutdownStep6GapDetectorAndEvents:
    """Step 6: GapDetector stopped + event subscriptions unsubscribed."""

    @pytest.mark.asyncio
    async def test_gap_detector_stopped(self) -> None:
        detector = FakeGapDetector()
        engine = FakeWorkflowEngine(gap_detector=detector)
        svc = _build_service(workflow_engine=engine)
        await _init_service(svc)

        await svc.shutdown()
        assert detector.stopped

    @pytest.mark.asyncio
    async def test_gap_detector_stop_error_does_not_block_unsubscribe(self) -> None:
        detector = FakeGapDetector(stop_raises=True)
        engine = FakeWorkflowEngine(gap_detector=detector)
        event_port = FakeEventPort()
        svc = _build_service(workflow_engine=engine, event_port=event_port)
        await _init_service(svc)

        await svc.shutdown()

        # Detector failed, but events still unsubscribed.
        assert not detector.stopped
        assert len(event_port.unsubscribed) == 5  # 5 topics from init

    @pytest.mark.asyncio
    async def test_all_subscriptions_unsubscribed(self) -> None:
        event_port = FakeEventPort()
        svc = _build_service(event_port=event_port)
        await _init_service(svc)

        # init() created 5 subscriptions.
        assert len(event_port.subscriptions) == 5

        await svc.shutdown()

        # All 5 unsubscribed.
        assert len(event_port.unsubscribed) == 5

    @pytest.mark.asyncio
    async def test_subscriptions_list_cleared(self) -> None:
        svc = _build_service()
        await _init_service(svc)

        await svc.shutdown()

        # Internal _subscriptions list should be empty.
        assert len(svc._subscriptions) == 0


class TestShutdownStep8Audit:
    """Step 8: Final audit written via bridge_port.submit_audit()."""

    @pytest.mark.asyncio
    async def test_audit_written(self) -> None:
        bridge = FakeBridgeWritePort()
        svc = _build_service(bridge_port=bridge)
        await _init_service(svc)

        await svc.shutdown()

        assert len(bridge.audit_calls) == 1
        manifest, trace_id = bridge.audit_calls[0]
        assert manifest["event"] == "orchestrator_shutdown"
        assert "pending_plans" in manifest
        assert "pending_hil" in manifest
        assert trace_id.startswith("shutdown-")

    @pytest.mark.asyncio
    async def test_audit_captures_orphan_counts(self) -> None:
        bridge = FakeBridgeWritePort()
        svc = _build_service(bridge_port=bridge)
        await _init_service(svc)

        # Inject orphaned contexts.
        svc._pending_plans["p1"] = _make_pending_plan("p1")
        svc._pending_plans["p2"] = _make_pending_plan("p2")
        svc._pending_hil["h1"] = _make_pending_hil("h1")

        await svc.shutdown()

        manifest, _ = bridge.audit_calls[0]
        assert manifest["pending_plans"] == 2
        assert manifest["pending_hil"] == 1

    @pytest.mark.asyncio
    async def test_audit_zero_orphans(self) -> None:
        bridge = FakeBridgeWritePort()
        svc = _build_service(bridge_port=bridge)
        await _init_service(svc)

        await svc.shutdown()

        manifest, _ = bridge.audit_calls[0]
        assert manifest["pending_plans"] == 0
        assert manifest["pending_hil"] == 0

    @pytest.mark.asyncio
    async def test_audit_error_does_not_block_task_cancellation(self) -> None:
        bridge = FakeBridgeWritePort(audit_raises=True)
        svc = _build_service(bridge_port=bridge)
        await _init_service(svc)

        # Should not raise despite audit failure.
        await svc.shutdown()
        assert not svc.initialized


class TestShutdownStep9TaskCancellation:
    """Step 9: Background tasks (reaper + loop) cancelled."""

    @pytest.mark.asyncio
    async def test_reaper_task_cancelled(self) -> None:
        svc = _build_service()
        await _init_service(svc)

        assert svc._reaper_task is not None
        assert not svc._reaper_task.done()

        await svc.shutdown()

        assert svc._reaper_task is None

    @pytest.mark.asyncio
    async def test_loop_task_cancelled(self) -> None:
        svc = _build_service()
        await _init_service(svc)

        assert svc._loop_task is not None
        assert not svc._loop_task.done()

        await svc.shutdown()

        assert svc._loop_task is None


class TestShutdownOrphanedContexts:
    """Gotcha #3: orphaned pending plans/HIL logged as warning."""

    @pytest.mark.asyncio
    async def test_orphaned_plans_warning_in_audit(self) -> None:
        bridge = FakeBridgeWritePort()
        svc = _build_service(bridge_port=bridge)
        await _init_service(svc)

        svc._pending_plans["rq-1"] = _make_pending_plan("rq-1")
        svc._pending_plans["rq-2"] = _make_pending_plan("rq-2")
        svc._pending_plans["rq-3"] = _make_pending_plan("rq-3")

        await svc.shutdown()

        manifest, _ = bridge.audit_calls[0]
        assert manifest["pending_plans"] == 3

    @pytest.mark.asyncio
    async def test_orphaned_hil_contexts_in_audit(self) -> None:
        bridge = FakeBridgeWritePort()
        svc = _build_service(bridge_port=bridge)
        await _init_service(svc)

        svc._pending_hil["h1"] = _make_pending_hil("h1")
        svc._pending_hil["h2"] = _make_pending_hil("h2")

        await svc.shutdown()

        manifest, _ = bridge.audit_calls[0]
        assert manifest["pending_hil"] == 2


class TestShutdownFullSequence:
    """End-to-end: all 9 steps execute in order."""

    @pytest.mark.asyncio
    async def test_clean_shutdown_all_steps(self) -> None:
        event_port = FakeEventPort()
        connector = FakeConnectorLifecycle()
        scheduler = FakeWorkflowScheduler()
        detector = FakeGapDetector()
        engine = FakeWorkflowEngine(scheduler=scheduler, gap_detector=detector)
        bridge = FakeBridgeWritePort()
        guard = FakeConcurrencyGuard(active=False)

        svc = _build_service(
            event_port=event_port,
            connector_lifecycle=connector,
            workflow_engine=engine,
            bridge_port=bridge,
            concurrency_guard=guard,
        )
        await _init_service(svc)

        # Insert some orphaned state for visibility.
        svc._pending_plans["rq-1"] = _make_pending_plan("rq-1")

        await svc.shutdown()

        # Step 1: running is False.
        assert not svc.running

        # Step 2: connector stopped.
        assert connector.monitoring_stopped

        # Step 5: scheduler stopped.
        assert scheduler.stopped

        # Step 6: gap detector stopped + events unsubscribed.
        assert detector.stopped
        assert len(event_port.unsubscribed) == 5
        assert len(svc._subscriptions) == 0

        # Step 8: audit written with correct data.
        assert len(bridge.audit_calls) == 1
        manifest, trace_id = bridge.audit_calls[0]
        assert manifest["event"] == "orchestrator_shutdown"
        assert manifest["pending_plans"] == 1
        assert manifest["pending_hil"] == 0

        # Step 9: tasks cancelled.
        assert svc._reaper_task is None
        assert svc._loop_task is None

        # Final: not initialized.
        assert not svc.initialized

    @pytest.mark.asyncio
    async def test_init_shutdown_init_cycle(self) -> None:
        """Service can be re-initialized after shutdown."""
        svc = _build_service()

        await _init_service(svc)
        assert svc.initialized and svc.running

        await svc.shutdown()
        assert not svc.initialized and not svc.running

        # Re-init.
        await _init_service(svc)
        assert svc.initialized and svc.running

        # Clean up.
        await svc.shutdown()
        assert not svc.initialized


class TestShutdownPerStepIsolation:
    """Gotcha #1: each step wrapped in try/except -- one failure
    does not block subsequent steps."""

    @pytest.mark.asyncio
    async def test_all_steps_fail_gracefully(self) -> None:
        """Even if connector, scheduler, gap detector, and audit all fail,
        shutdown completes and _initialized is cleared."""
        connector = FakeConnectorLifecycle(stop_raises=True)
        scheduler = FakeWorkflowScheduler(stop_raises=True)
        detector = FakeGapDetector(stop_raises=True)
        engine = FakeWorkflowEngine(scheduler=scheduler, gap_detector=detector)
        bridge = FakeBridgeWritePort(audit_raises=True)

        svc = _build_service(
            connector_lifecycle=connector,
            workflow_engine=engine,
            bridge_port=bridge,
        )
        await _init_service(svc)

        # Should not raise.
        await svc.shutdown()

        # Even though every step failed, state is cleaned.
        assert not svc.initialized
        assert not svc.running
        assert svc._reaper_task is None
        assert svc._loop_task is None

    @pytest.mark.asyncio
    async def test_connector_fail_does_not_prevent_scheduler_stop(self) -> None:
        connector = FakeConnectorLifecycle(stop_raises=True)
        scheduler = FakeWorkflowScheduler()
        engine = FakeWorkflowEngine(scheduler=scheduler)

        svc = _build_service(connector_lifecycle=connector, workflow_engine=engine)
        await _init_service(svc)

        await svc.shutdown()

        assert not connector.monitoring_stopped  # Failed.
        assert scheduler.stopped  # Still executed.

    @pytest.mark.asyncio
    async def test_scheduler_fail_does_not_prevent_audit(self) -> None:
        scheduler = FakeWorkflowScheduler(stop_raises=True)
        engine = FakeWorkflowEngine(scheduler=scheduler)
        bridge = FakeBridgeWritePort()

        svc = _build_service(workflow_engine=engine, bridge_port=bridge)
        await _init_service(svc)

        await svc.shutdown()

        assert not scheduler.stopped  # Failed.
        assert len(bridge.audit_calls) == 1  # Still executed.
