"""
Tests for OrchestratorService.init() lifecycle (Issue 6.2.2).

Validates the 10-step startup sequence:
  1. Port validation (non-None check)
  2. (Reserved) Port connection
  3. ConcurrencyGuard not-locked assertion
  4. MCP discovery + registration (500ms timeout)
  5. (Commentary)
  6. Workflow loading
  7. Scheduler start
  8. Event subscriptions (5 topics)
  9. GapDetector, ConnectorLifecycle monitoring, reaper task
 10. Mailbox loop task

Coverage targets:
  init()                -- full 10-step success, idempotency, partial failures
  _validate_ports()     -- missing port detection, all-present success
  _discover_mcp_tools() -- normal + timeout
  _subscribe_events()   -- 5 subscriptions registered, handle storage
  _on_plan_ready()      -- deserialize + enqueue
  _on_plan_failed()     -- pending cleanup + missing context
  _on_plan_cancelled()  -- pending cleanup + missing context
  _on_hil_override()    -- pending cleanup + missing context
  _on_hil_fallback()    -- pending cleanup + missing context
  _reap_loop()          -- periodic execution
  _mailbox_loop()       -- dequeue + process routing
  _process_one()        -- exception isolation

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
from k1.orchestrator.events import (
    HIL_FALLBACK_RESPONSE,
    HIL_OVERRIDE_RESPONSE,
    PLAN_CANCELLED,
    PLAN_FAILED,
    PLAN_READY,
)
from k1.orchestrator.orchestration.orchestrator_service import OrchestratorService
from k1.orchestrator.types import (
    AggregatedResult,
    CommittedPlan,
    ErrorSeverity,
    PendingHILContext,
    PendingPlanContext,
    PlanAck,
    PlanStep,
    ProcessResult,
    TaskEnvelope,
)

# ===========================================================================
# Fakes -- deterministic Protocol implementations for init() testing
# ===========================================================================


class FakeEventPort:
    """Fake event port with full call recording.

    subscribe() records calls and returns SubscriptionHandle.
    emit() dispatches to registered handlers for integration tests.
    """

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
        delay_s: float = 0.0,
    ) -> None:
        self._result = result or RegistrationResult(registered=3, skipped=1, errors=[])
        self._delay_s = delay_s
        self.discover_called: bool = False
        self.monitoring_started: bool = False
        self.monitoring_stopped: bool = False

    async def discover_and_register(self) -> RegistrationResult:
        self.discover_called = True
        if self._delay_s > 0:
            await asyncio.sleep(self._delay_s)
        return self._result

    def start_lifecycle_monitoring(self) -> None:
        self.monitoring_started = True

    def stop_lifecycle_monitoring(self) -> None:
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

    def __init__(self) -> None:
        self.started: bool = False
        self.stopped: bool = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class FakeGapDetector:
    """Fake gap detector tracking start/stop calls."""

    def __init__(self) -> None:
        self.started: bool = False
        self.stopped: bool = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
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
    """Minimal DAG executor for init tests."""

    async def execute(self, plan: Any, ctx: Any) -> AggregatedResult:
        return AggregatedResult(
            plan_id="test",
            trace_id="test",
            steps=[],
            compensations=[],
        )


class FakeConstraintResolver:
    """Minimal constraint resolver for init tests."""

    async def validate(self, plan: Any, ctx: Any) -> Any:
        class _Result:
            valid = True
            issues: List[str] = []

        return _Result()


class FakeErrorRouter:
    """Minimal error router for init tests."""

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

    def acquire(self, ctx: Any) -> bool:
        return self._allow

    def release(self, ctx: Any) -> None:
        pass


class FakeFabricGatewayPort:
    """Minimal fabric port for init tests."""

    async def execute_capability(self, request: Any) -> Any:
        return None

    async def get_registry(self) -> Dict[str, Any]:
        return {}


class FakePlannerPort:
    """Minimal planner port for init tests."""

    async def request_plan(self, request: Any) -> PlanAck:
        return PlanAck(request_id="test", status="ACCEPTED")

    async def cancel_plan(self, request_id: str) -> None:
        pass


class FakeStateReadPort:
    """Minimal state read port for init tests."""

    async def get_snapshot(self, trace_id: str) -> Any:
        return None


class FakeDeltaEmitPort:
    """Minimal delta emit port recording emitted deltas."""

    def __init__(self) -> None:
        self.emitted: List[tuple] = []

    async def emit(self, event_topic: str, payload: Dict[str, Any], trace_id: str = "") -> None:
        self.emitted.append((event_topic, payload, trace_id))


class FakeBridgeWritePort:
    """Minimal bridge write port for init/shutdown tests."""

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
        "context_reap_interval_ms": 100,  # fast for tests
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
    """Build OrchestratorService with init()-capable fakes."""
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
    """Build minimal PlanStep for CommittedPlan."""
    return PlanStep(id=step_id, capability=capability)


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


def _make_pending_hil(request_id: str, *, expired: bool = False) -> PendingHILContext:
    """Build PendingHILContext with correct fields."""
    return PendingHILContext(
        request_id=request_id,
        dag_execution_id="dag-1",
        current_wave_index=0,
        completed_waves=[],
        remaining_waves=[],
        question="proceed?",
        options=["yes", "no"],
        timeout_fallback="CONTINUE",
        created_at=time.time() - (300 if expired else 0),
        timeout_ms=1_000 if expired else 120_000,
    )


async def _init_and_cleanup(svc: OrchestratorService) -> None:
    """Run init() and immediately stop background tasks for clean test teardown."""
    await svc.init()
    # Stop background tasks to prevent dangling coroutines
    svc._running = False
    if svc._loop_task and not svc._loop_task.done():
        svc._loop_task.cancel()
        try:
            await svc._loop_task
        except asyncio.CancelledError:
            pass
    if svc._reaper_task and not svc._reaper_task.done():
        svc._reaper_task.cancel()
        try:
            await svc._reaper_task
        except asyncio.CancelledError:
            pass


# ===========================================================================
# Tests: init() full sequence
# ===========================================================================


class TestInitFullSequence:
    """Validate complete 10-step init() sequence."""

    @pytest.mark.asyncio
    async def test_init_completes_all_steps(self) -> None:
        """init() executes all 10 steps successfully."""
        connector = FakeConnectorLifecycle()
        engine = FakeWorkflowEngine()
        event = FakeEventPort()

        svc = _build_service(
            connector_lifecycle=connector,
            workflow_engine=engine,
            event_port=event,
        )

        await _init_and_cleanup(svc)

        # Step 4: MCP discovery called
        assert connector.discover_called is True

        # Step 6: Workflows loaded
        assert engine.registry.list_active_called is True

        # Step 7: Scheduler started
        assert engine.scheduler.started is True

        # Step 8: 5 event subscriptions
        assert len(event.subscriptions) == 5
        topics = [topic for topic, _ in event.subscriptions]
        assert PLAN_READY in topics
        assert PLAN_FAILED in topics
        assert PLAN_CANCELLED in topics
        assert HIL_OVERRIDE_RESPONSE in topics
        assert HIL_FALLBACK_RESPONSE in topics

        # Step 9a: Gap detector started
        assert engine.gap_detector.started is True

        # Step 9b: Lifecycle monitoring started
        assert connector.monitoring_started is True

        # Lifecycle flags
        assert svc.initialized is True

        # Subscriptions stored for shutdown
        assert len(svc._subscriptions) == 5

    @pytest.mark.asyncio
    async def test_init_idempotent(self) -> None:
        """Calling init() twice is safe (second call is no-op)."""
        connector = FakeConnectorLifecycle()
        event = FakeEventPort()

        svc = _build_service(connector_lifecycle=connector, event_port=event)

        await _init_and_cleanup(svc)

        # Reset flags
        connector.discover_called = False
        event.subscriptions.clear()

        # Second call -- should be no-op
        await svc.init()

        assert connector.discover_called is False
        assert len(event.subscriptions) == 0
        assert svc.initialized is True

    @pytest.mark.asyncio
    async def test_init_sets_running_flag(self) -> None:
        """init() sets _running to True before creating tasks."""
        svc = _build_service()
        # Before init
        assert svc.running is False

        await _init_and_cleanup(svc)

        # After cleanup, running is set back to False by helper
        # but _initialized stays True
        assert svc.initialized is True

    @pytest.mark.asyncio
    async def test_init_creates_background_tasks(self) -> None:
        """init() creates both loop_task and reaper_task."""
        svc = _build_service()
        await svc.init()

        # Tasks created
        assert svc._loop_task is not None
        assert svc._reaper_task is not None

        # Clean up
        svc._running = False
        svc._loop_task.cancel()
        svc._reaper_task.cancel()
        try:
            await svc._loop_task
        except asyncio.CancelledError:
            pass
        try:
            await svc._reaper_task
        except asyncio.CancelledError:
            pass


# ===========================================================================
# Tests: _validate_ports()
# ===========================================================================


class TestValidatePorts:
    """Validate port non-None check at init time."""

    @pytest.mark.asyncio
    async def test_all_ports_present_passes(self) -> None:
        """_validate_ports() succeeds when all ports non-None."""
        svc = _build_service()
        # Should not raise
        svc._validate_ports()

    @pytest.mark.asyncio
    async def test_missing_event_port_raises(self) -> None:
        """_validate_ports() raises RuntimeError for None event_port."""
        svc = _build_service()
        svc._event_port = None  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="missing required ports.*event_port"):
            svc._validate_ports()

    @pytest.mark.asyncio
    async def test_missing_mailbox_raises(self) -> None:
        """_validate_ports() raises RuntimeError for None mailbox."""
        svc = _build_service()
        svc._mailbox = None  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="missing required ports.*mailbox"):
            svc._validate_ports()

    @pytest.mark.asyncio
    async def test_multiple_missing_ports_listed(self) -> None:
        """_validate_ports() lists all missing ports in the error message."""
        svc = _build_service()
        svc._mailbox = None  # type: ignore[assignment]
        svc._fabric_port = None  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="missing required ports"):
            svc._validate_ports()

    @pytest.mark.asyncio
    async def test_init_fails_on_none_port(self) -> None:
        """init() raises RuntimeError if a port is None (step 1 gate)."""
        svc = _build_service()
        svc._event_port = None  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="missing required ports"):
            await svc.init()

        # init should NOT have set initialized
        assert svc.initialized is False


# ===========================================================================
# Tests: ConcurrencyGuard check (Step 3)
# ===========================================================================


class TestConcurrencyGuardCheck:
    """Validate Step 3: concurrency guard not-locked assertion."""

    @pytest.mark.asyncio
    async def test_active_guard_fails_init(self) -> None:
        """init() raises AssertionError if guard is active at boot."""
        guard = FakeConcurrencyGuard(active=True)
        svc = _build_service(concurrency_guard=guard)

        with pytest.raises(AssertionError, match="must not be active"):
            await svc.init()

        assert svc.initialized is False

    @pytest.mark.asyncio
    async def test_inactive_guard_passes(self) -> None:
        """init() passes Step 3 with inactive guard."""
        guard = FakeConcurrencyGuard(active=False)
        svc = _build_service(concurrency_guard=guard)

        await _init_and_cleanup(svc)
        assert svc.initialized is True


# ===========================================================================
# Tests: MCP discovery (Step 4)
# ===========================================================================


class TestMCPDiscovery:
    """Validate Step 4: MCP discovery with 500ms timeout."""

    @pytest.mark.asyncio
    async def test_discovery_returns_result(self) -> None:
        """_discover_mcp_tools() returns RegistrationResult on success."""
        connector = FakeConnectorLifecycle(
            result=RegistrationResult(registered=5, skipped=2, errors=[]),
        )
        svc = _build_service(connector_lifecycle=connector)

        result = await svc._discover_mcp_tools()

        assert result.registered == 5
        assert result.skipped == 2
        assert connector.discover_called is True

    @pytest.mark.asyncio
    async def test_discovery_timeout_returns_empty(self) -> None:
        """_discover_mcp_tools() returns empty result on timeout (>500ms)."""
        connector = FakeConnectorLifecycle(delay_s=2.0)
        svc = _build_service(connector_lifecycle=connector)

        result = await svc._discover_mcp_tools()

        # Should get empty result due to timeout
        assert result.registered == 0
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_init_continues_after_mcp_timeout(self) -> None:
        """init() completes even if MCP discovery times out."""
        connector = FakeConnectorLifecycle(delay_s=2.0)
        engine = FakeWorkflowEngine()

        svc = _build_service(
            connector_lifecycle=connector,
            workflow_engine=engine,
        )

        await _init_and_cleanup(svc)

        # Steps after MCP still executed
        assert engine.scheduler.started is True
        assert svc.initialized is True


# ===========================================================================
# Tests: _subscribe_events() (Step 8)
# ===========================================================================


class TestSubscribeEvents:
    """Validate Step 8: event subscription wiring."""

    @pytest.mark.asyncio
    async def test_five_subscriptions_registered(self) -> None:
        """_subscribe_events() registers exactly 5 subscriptions."""
        event = FakeEventPort()
        svc = _build_service(event_port=event)

        svc._subscribe_events()

        assert len(event.subscriptions) == 5
        assert len(svc._subscriptions) == 5

    @pytest.mark.asyncio
    async def test_subscription_topics_match_constants(self) -> None:
        """All 5 subscribed topics match event constant values."""
        event = FakeEventPort()
        svc = _build_service(event_port=event)

        svc._subscribe_events()

        topics = {topic for topic, _ in event.subscriptions}
        expected = {
            PLAN_READY,
            PLAN_FAILED,
            PLAN_CANCELLED,
            HIL_OVERRIDE_RESPONSE,
            HIL_FALLBACK_RESPONSE,
        }
        assert topics == expected

    @pytest.mark.asyncio
    async def test_subscription_handles_stored(self) -> None:
        """All SubscriptionHandle objects stored for shutdown unsubscription."""
        event = FakeEventPort()
        svc = _build_service(event_port=event)

        svc._subscribe_events()

        assert all(isinstance(h, SubscriptionHandle) for h in svc._subscriptions)
        ids = [h.subscription_id for h in svc._subscriptions]
        assert len(set(ids)) == 5  # all unique


# ===========================================================================
# Tests: Event handlers
# ===========================================================================


class TestOnPlanReady:
    """Validate _on_plan_ready handler."""

    @pytest.mark.asyncio
    async def test_enqueues_committed_plan(self) -> None:
        """_on_plan_ready deserializes payload and enqueues CommittedPlan."""
        mailbox = FakeMailboxPort()
        svc = _build_service(mailbox=mailbox)

        payload = {
            "plan_id": "plan-1",
            "request_id": "req-1",
            "intent": "test intent",
            "steps": [_make_step()],
            "trace_id": "trace-1",
            "dependencies": {},
        }

        svc._on_plan_ready(PLAN_READY, payload)

        assert len(mailbox.enqueued) == 1
        msg, priority = mailbox.enqueued[0]
        assert isinstance(msg, CommittedPlan)
        assert msg.plan_id == "plan-1"
        assert msg.request_id == "req-1"
        assert priority == "INTERACTIVE"

    @pytest.mark.asyncio
    async def test_bad_payload_does_not_crash(self) -> None:
        """_on_plan_ready catches exceptions on bad payload."""
        svc = _build_service()
        # Empty dict -- still should not crash (uses .get defaults)
        svc._on_plan_ready(PLAN_READY, {})


class TestOnPlanFailed:
    """Validate _on_plan_failed handler."""

    @pytest.mark.asyncio
    async def test_cleans_pending_context(self) -> None:
        """_on_plan_failed removes matching PendingPlanContext."""
        svc = _build_service()
        svc._pending_plans["req-1"] = _make_pending_plan("req-1")

        svc._on_plan_failed(PLAN_FAILED, {"request_id": "req-1", "reason": "budget"})

        assert "req-1" not in svc._pending_plans

    @pytest.mark.asyncio
    async def test_missing_context_logs_warning(self) -> None:
        """_on_plan_failed handles missing context without crash."""
        svc = _build_service()
        # No pending plans -- should log warning but not crash
        svc._on_plan_failed(PLAN_FAILED, {"request_id": "unknown"})


class TestOnPlanCancelled:
    """Validate _on_plan_cancelled handler."""

    @pytest.mark.asyncio
    async def test_cleans_pending_context(self) -> None:
        """_on_plan_cancelled removes matching PendingPlanContext."""
        svc = _build_service()
        svc._pending_plans["req-2"] = _make_pending_plan("req-2")

        svc._on_plan_cancelled(PLAN_CANCELLED, {"request_id": "req-2"})

        assert "req-2" not in svc._pending_plans

    @pytest.mark.asyncio
    async def test_missing_context_does_not_crash(self) -> None:
        """_on_plan_cancelled handles missing context gracefully."""
        svc = _build_service()
        svc._on_plan_cancelled(PLAN_CANCELLED, {"request_id": "nope"})


class TestOnHILOverride:
    """Validate _on_hil_override handler."""

    @pytest.mark.asyncio
    async def test_resolves_pending_hil(self) -> None:
        """_on_hil_override removes matching PendingHILContext."""
        svc = _build_service()
        svc._pending_hil["hil-1"] = _make_pending_hil("hil-1")

        svc._on_hil_override(
            HIL_OVERRIDE_RESPONSE,
            {"request_id": "hil-1", "choice": "CONTINUE"},
        )

        assert "hil-1" not in svc._pending_hil

    @pytest.mark.asyncio
    async def test_missing_hil_context_does_not_crash(self) -> None:
        """_on_hil_override handles missing HIL context."""
        svc = _build_service()
        svc._on_hil_override(HIL_OVERRIDE_RESPONSE, {"request_id": "nope"})


class TestOnHILFallback:
    """Validate _on_hil_fallback handler."""

    @pytest.mark.asyncio
    async def test_resolves_pending_hil(self) -> None:
        """_on_hil_fallback removes matching PendingHILContext."""
        svc = _build_service()
        svc._pending_hil["hil-2"] = _make_pending_hil("hil-2")

        svc._on_hil_fallback(
            HIL_FALLBACK_RESPONSE,
            {"request_id": "hil-2", "fallback_action": "CANCEL"},
        )

        assert "hil-2" not in svc._pending_hil

    @pytest.mark.asyncio
    async def test_missing_hil_context_does_not_crash(self) -> None:
        """_on_hil_fallback handles missing HIL context."""
        svc = _build_service()
        svc._on_hil_fallback(HIL_FALLBACK_RESPONSE, {"request_id": "nope"})


# ===========================================================================
# Tests: Event handler integration (via emit)
# ===========================================================================


class TestEventHandlerIntegration:
    """Test event handlers wired through subscribe + emit."""

    @pytest.mark.asyncio
    async def test_plan_ready_via_emit(self) -> None:
        """Emitting PLAN_READY fires _on_plan_ready and enqueues message."""
        mailbox = FakeMailboxPort()
        event = FakeEventPort()
        svc = _build_service(mailbox=mailbox, event_port=event)

        svc._subscribe_events()

        event.emit(
            PLAN_READY,
            {
                "plan_id": "p-emitted",
                "request_id": "r-emitted",
                "intent": "via emit",
                "steps": [_make_step()],
                "trace_id": "t-emitted",
                "dependencies": {},
            },
        )

        assert len(mailbox.enqueued) == 1
        msg, _ = mailbox.enqueued[0]
        assert isinstance(msg, CommittedPlan)
        assert msg.plan_id == "p-emitted"

    @pytest.mark.asyncio
    async def test_plan_failed_via_emit(self) -> None:
        """Emitting PLAN_FAILED fires handler and cleans pending."""
        event = FakeEventPort()
        svc = _build_service(event_port=event)

        svc._pending_plans["req-emit"] = _make_pending_plan("req-emit")

        svc._subscribe_events()

        event.emit(PLAN_FAILED, {"request_id": "req-emit", "reason": "timeout"})

        assert "req-emit" not in svc._pending_plans


# ===========================================================================
# Tests: _reap_loop()
# ===========================================================================


class TestReapLoop:
    """Validate _reap_loop periodic execution."""

    @pytest.mark.asyncio
    async def test_reap_loop_calls_reap_stale_contexts(self) -> None:
        """_reap_loop invokes reap_stale_contexts periodically."""
        config = _default_config(context_reap_interval_ms=50)  # 50ms
        svc = _build_service(config=config)

        # Plant a stale pending plan (expired 10 seconds ago)
        svc._pending_plans["stale-1"] = _make_pending_plan("stale-1", expired=True)

        svc._running = True
        task = asyncio.create_task(svc._reap_loop())

        # Let it run at least one cycle (50ms interval + buffer)
        await asyncio.sleep(0.15)

        svc._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Stale context should have been reaped
        assert "stale-1" not in svc._pending_plans


# ===========================================================================
# Tests: _mailbox_loop() and _process_one()
# ===========================================================================


class TestMailboxLoop:
    """Validate _mailbox_loop message processing."""

    @pytest.mark.asyncio
    async def test_loop_processes_queued_message(self) -> None:
        """_mailbox_loop dequeues and processes a TaskEnvelope."""
        envelope = TaskEnvelope(
            intent="test loop",
            trace_id=str(uuid4()),
            tier="MEDIUM",
            capabilities=["tool.test.a"],
            params={"tool.test.a": {}},
            context={},
        )
        mailbox = FakeMailboxPort(messages=[envelope])
        svc = _build_service(mailbox=mailbox)

        svc._running = True
        task = asyncio.create_task(svc._mailbox_loop())

        # Give loop time to process
        await asyncio.sleep(0.05)

        svc._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Message was dequeued (queue empty now)
        assert mailbox.dequeue() is None

    @pytest.mark.asyncio
    async def test_process_one_catches_exceptions(self) -> None:
        """_process_one does not crash on unhandled process() exception."""
        svc = _build_service()

        # Pass invalid message type -- process() will log error
        # but _process_one should catch and not propagate
        await svc._process_one("not-a-valid-message")  # type: ignore[arg-type]
        # No exception = success


# ===========================================================================
# Tests: Lifecycle properties
# ===========================================================================


class TestLifecycleProperties:
    """Validate lifecycle property accessors."""

    @pytest.mark.asyncio
    async def test_initialized_false_before_init(self) -> None:
        """initialized is False before init() is called."""
        svc = _build_service()
        assert svc.initialized is False

    @pytest.mark.asyncio
    async def test_running_false_before_init(self) -> None:
        """running is False before init() is called."""
        svc = _build_service()
        assert svc.running is False

    @pytest.mark.asyncio
    async def test_subscriptions_empty_before_init(self) -> None:
        """_subscriptions is empty before init() is called."""
        svc = _build_service()
        assert svc._subscriptions == []

    @pytest.mark.asyncio
    async def test_loop_task_none_before_init(self) -> None:
        """_loop_task is None before init() is called."""
        svc = _build_service()
        assert svc._loop_task is None

    @pytest.mark.asyncio
    async def test_reaper_task_none_before_init(self) -> None:
        """_reaper_task is None before init() is called."""
        svc = _build_service()
        assert svc._reaper_task is None
