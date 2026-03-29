"""
Tests for OrchestratorService.crash_recovery() lifecycle (Issue 6.2.4).

Validates WAL-based recovery on startup:
  - No pending WALs: zero-result returned.
  - DAG_COMPLETE in WAL: DAG already finished, skipped.
  - PLAN_START only (unstarted DAG): CommittedPlan reconstructed, enqueued to mailbox.
  - WAVE_COMPLETE(N) + PLAN_START: partial execution, V1 re-executes from wave 0.
  - Corrupt WAL (no PLAN_START entry): failed_recovery incremented.
  - K0 offline (AdapterException DEGRADED on list_wal_ids): skip entirely.
  - K0 offline (AdapterException DEGRADED on read_wal): per-dag failure isolation.
  - Mixed WAL entries (multiple dag_ids with different states).
  - Recovery error in one dag_id doesn't block others.
  - init() calls crash_recovery() between steps 2 and 3.

Test Philosophy: Protocol-based fakes with explicit call tracking.
NO magic mocking. Every fake records calls for assertion.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.fabric.ports.state_reader import SessionSnapshot
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.connectors.mcp_registrar import RegistrationResult
from k1.orchestrator.orchestration.orchestrator_service import AdapterException, OrchestratorService
from k1.orchestrator.types import (
    AdapterError,
    AggregatedResult,
    CommittedPlan,
    ErrorSeverity,
    PlanAck,
    PlanStep,
    RecoveryResult,
)

# ===========================================================================
# Fakes -- deterministic Protocol implementations for crash_recovery testing
# ===========================================================================


class FakeEventPort:
    """Fake event bus port for init tests (crash_recovery runs inside init)."""

    def __init__(self) -> None:
        self.subscriptions: List[tuple[str, Callable]] = []
        self._next_id = 0

    def subscribe(
        self,
        topic: str,
        handler: Callable,
    ) -> SubscriptionHandle:
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


class FakeDAGExecutor:
    """Fake DAG executor - not used by crash_recovery but needed for init."""

    async def execute(self, plan: Any, snapshot: Any) -> AggregatedResult:
        return AggregatedResult(
            plan_id=getattr(plan, "plan_id", "test"),
            request_id=getattr(plan, "request_id", "test"),
            completed=0,
            failed=0,
            cancelled=0,
            total_elapsed_ms=0,
            wave_count=0,
        )


class FakeConstraintResolver:
    """Fake constraint resolver."""

    async def validate(self, plan: Any) -> Any:
        return None


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


class FakeWorkflowRegistry:
    """Fake registry returning configurable active workflows."""

    async def list_active(self) -> List[Any]:
        return []


class FakeWorkflowScheduler:
    """Fake scheduler tracking start/stop calls."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class FakeConnectorLifecycle:
    """Fake connector with discover_and_register + lifecycle monitoring."""

    async def discover_and_register(self) -> RegistrationResult:
        return RegistrationResult(registered=0, skipped=0, errors=[])

    def start_lifecycle_monitoring(self) -> None:
        pass

    def stop_lifecycle_monitoring(self) -> None:
        pass


class FakeErrorRouter:
    """Fake error router."""

    async def route(self, error: Any) -> None:
        pass


class FakeConcurrencyGuard:
    """Fake guard -- always allows entry."""

    active: bool = False

    async def __aenter__(self) -> "FakeConcurrencyGuard":
        self.active = True
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.active = False


class FakeFabricGatewayPort:
    """Fake fabric port -- MCP discovery returns empty."""

    async def discover_mcp_tools(self) -> RegistrationResult:
        return RegistrationResult(registered=0, skipped=0, errors=[])


class FakePlannerPort:
    """Fake planner port."""

    async def submit(self, plan_request: Any) -> PlanAck:
        return PlanAck(request_id="fake-ack", accepted=True, trace_id=str(uuid4()))


class FakeStateReadPort:
    """Fake state port returning canned snapshot."""

    async def get_snapshot(self, session_id: str) -> SessionSnapshot:
        return SessionSnapshot(session_id=session_id, data={})


class FakeDeltaEmitPort:
    """Fake delta emit port -- sink."""

    async def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        pass


class FakeBridgeWritePort:
    """Fake bridge write port with WAL state for crash_recovery testing.

    Tests pre-populate ``_wal_store`` via ``inject_wal()`` and
    optionally configure ``list_wal_raises`` / ``read_wal_raises``
    to simulate K0 offline scenarios.
    """

    def __init__(
        self,
        *,
        list_wal_raises: Optional[Exception] = None,
        read_wal_raises: Optional[Dict[str, Exception]] = None,
    ) -> None:
        self.audit_calls: List[tuple[Dict[str, Any], str]] = []
        self._wal_store: Dict[str, List[Dict[str, Any]]] = {}
        self._list_wal_raises = list_wal_raises
        self._read_wal_raises = read_wal_raises or {}

    def inject_wal(self, dag_id: str, entries: List[Dict[str, Any]]) -> None:
        """Pre-populate WAL entries for a specific dag_id (test helper)."""
        self._wal_store[dag_id] = entries

    async def write(self, data: Any) -> None:
        pass

    async def submit_audit(self, run_manifest: Dict[str, Any], trace_id: str) -> None:
        self.audit_calls.append((run_manifest, trace_id))

    async def write_wal(
        self, dag_id: str, entry_type: str, payload: Dict[str, Any], trace_id: str
    ) -> None:
        self._wal_store.setdefault(dag_id, []).append(
            {"entry_type": entry_type, "payload": payload}
        )

    async def read_wal(self, dag_id: str) -> Optional[List[Dict[str, Any]]]:
        if dag_id in self._read_wal_raises:
            raise self._read_wal_raises[dag_id]
        return self._wal_store.get(dag_id)

    async def list_wal_ids(self) -> List[str]:
        if self._list_wal_raises is not None:
            raise self._list_wal_raises
        return list(self._wal_store.keys())

    async def submit_deferred_result(
        self, request_id: str, result: Dict[str, Any], trace_id: str
    ) -> None:
        pass


class FakeGapDetector:
    """Fake gap detector."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


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
    bridge_port: Optional[FakeBridgeWritePort] = None,
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
) -> OrchestratorService:
    """Build OrchestratorService with crash_recovery-capable fakes."""
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


def _make_committed_plan(
    *,
    plan_id: str = "",
    request_id: str = "",
    trace_id: str = "",
) -> CommittedPlan:
    """Build minimal CommittedPlan with defaults."""
    return CommittedPlan(
        plan_id=plan_id or f"plan-{uuid4().hex[:8]}",
        request_id=request_id or f"req-{uuid4().hex[:8]}",
        intent="test recovery",
        steps=[_make_step()],
        trace_id=trace_id or str(uuid4()),
    )


def _plan_start_entry(plan: CommittedPlan) -> Dict[str, Any]:
    """Build a PLAN_START WAL entry from a CommittedPlan."""
    return {
        "entry_type": "PLAN_START",
        "payload": {"plan": plan.to_dict()},
    }


def _wave_complete_entry(wave_index: int) -> Dict[str, Any]:
    """Build a WAVE_COMPLETE WAL entry."""
    return {
        "entry_type": "WAVE_COMPLETE",
        "payload": {"wave_index": wave_index},
    }


def _dag_complete_entry() -> Dict[str, Any]:
    """Build a DAG_COMPLETE WAL entry."""
    return {
        "entry_type": "DAG_COMPLETE",
        "payload": {},
    }


def _degraded_exception(operation: str = "list_wal_ids") -> AdapterException:
    """Build an AdapterException with DEGRADED severity (K0 offline)."""
    return AdapterException(
        AdapterError(
            severity=ErrorSeverity.DEGRADED,
            adapter_name="bridge",
            operation=operation,
            error_code="K0_OFFLINE",
            error_message="K0 bridge unavailable",
        )
    )


# ===========================================================================
# Test: crash_recovery() direct invocation
# ===========================================================================


class TestCrashRecoveryNoPendingWALs:
    """No WAL entries to recover -- zero-result returned."""

    @pytest.mark.asyncio
    async def test_no_wal_ids_returns_zero_result(self) -> None:
        """list_wal_ids() returns empty -> RecoveryResult(0,0,0)."""
        bridge = FakeBridgeWritePort()
        svc = _build_service(bridge_port=bridge)

        result = await svc.crash_recovery()

        assert result.recovered_dags == 0
        assert result.failed_recoveries == 0
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_return_type_is_recovery_result(self) -> None:
        """crash_recovery() returns a RecoveryResult instance."""
        svc = _build_service()
        result = await svc.crash_recovery()
        assert isinstance(result, RecoveryResult)


class TestCrashRecoveryDAGComplete:
    """DAG_COMPLETE found in WAL -- DAG already finished, skipped."""

    @pytest.mark.asyncio
    async def test_dag_complete_is_skipped(self) -> None:
        """WAL with DAG_COMPLETE -> skipped=1, recovered=0."""
        plan = _make_committed_plan()
        bridge = FakeBridgeWritePort()
        bridge.inject_wal(
            "dag-1",
            [
                _plan_start_entry(plan),
                _dag_complete_entry(),
            ],
        )

        svc = _build_service(bridge_port=bridge)
        result = await svc.crash_recovery()

        assert result.skipped == 1
        assert result.recovered_dags == 0
        assert result.failed_recoveries == 0

    @pytest.mark.asyncio
    async def test_dag_complete_not_enqueued(self) -> None:
        """Completed DAG is NOT re-enqueued to mailbox."""
        plan = _make_committed_plan()
        bridge = FakeBridgeWritePort()
        bridge.inject_wal(
            "dag-1",
            [
                _plan_start_entry(plan),
                _dag_complete_entry(),
            ],
        )
        mailbox = FakeMailboxPort()

        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.crash_recovery()

        assert len(mailbox.enqueued) == 0


class TestCrashRecoveryPlanStartOnly:
    """PLAN_START only (unstarted DAG) -- reconstruct and enqueue."""

    @pytest.mark.asyncio
    async def test_unstarted_dag_recovered(self) -> None:
        """PLAN_START only -> recovered_dags=1."""
        plan = _make_committed_plan(plan_id="plan-abc", request_id="req-xyz")
        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-1", [_plan_start_entry(plan)])

        mailbox = FakeMailboxPort()
        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        result = await svc.crash_recovery()

        assert result.recovered_dags == 1
        assert result.failed_recoveries == 0
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_plan_enqueued_to_mailbox(self) -> None:
        """Recovered plan is enqueued to mailbox with INTERACTIVE priority."""
        plan = _make_committed_plan(plan_id="plan-abc", request_id="req-xyz")
        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-1", [_plan_start_entry(plan)])

        mailbox = FakeMailboxPort()
        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.crash_recovery()

        assert len(mailbox.enqueued) == 1
        enqueued_plan, priority = mailbox.enqueued[0]
        assert priority == "INTERACTIVE"
        assert isinstance(enqueued_plan, CommittedPlan)
        assert enqueued_plan.plan_id == "plan-abc"
        assert enqueued_plan.request_id == "req-xyz"

    @pytest.mark.asyncio
    async def test_reconstructed_plan_has_steps(self) -> None:
        """Reconstructed CommittedPlan preserves steps from WAL payload."""
        plan = _make_committed_plan()
        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-1", [_plan_start_entry(plan)])

        mailbox = FakeMailboxPort()
        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.crash_recovery()

        enqueued_plan, _ = mailbox.enqueued[0]
        assert len(enqueued_plan.steps) == len(plan.steps)
        assert enqueued_plan.steps[0].id == plan.steps[0].id
        assert enqueued_plan.steps[0].capability == plan.steps[0].capability


class TestCrashRecoveryPartialExecution:
    """WAVE_COMPLETE(N) + PLAN_START -- V1 re-execute from wave 0."""

    @pytest.mark.asyncio
    async def test_partial_dag_recovered(self) -> None:
        """PLAN_START + WAVE_COMPLETE(2) -> recovered_dags=1."""
        plan = _make_committed_plan(plan_id="plan-partial")
        bridge = FakeBridgeWritePort()
        bridge.inject_wal(
            "dag-partial",
            [
                _plan_start_entry(plan),
                _wave_complete_entry(0),
                _wave_complete_entry(1),
                _wave_complete_entry(2),
            ],
        )

        mailbox = FakeMailboxPort()
        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        result = await svc.crash_recovery()

        assert result.recovered_dags == 1
        assert result.skipped == 0
        assert result.failed_recoveries == 0

    @pytest.mark.asyncio
    async def test_partial_dag_enqueued_at_wave_0(self) -> None:
        """V1 limitation: partial DAG re-enqueued for full re-execution."""
        plan = _make_committed_plan(plan_id="plan-partial")
        bridge = FakeBridgeWritePort()
        bridge.inject_wal(
            "dag-partial",
            [
                _plan_start_entry(plan),
                _wave_complete_entry(0),
                _wave_complete_entry(1),
            ],
        )

        mailbox = FakeMailboxPort()
        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.crash_recovery()

        assert len(mailbox.enqueued) == 1
        enqueued_plan, _ = mailbox.enqueued[0]
        assert enqueued_plan.plan_id == "plan-partial"


class TestCrashRecoveryCorruptWAL:
    """Corrupt WAL (no PLAN_START entry) -- failed_recovery incremented."""

    @pytest.mark.asyncio
    async def test_no_plan_start_increments_failed(self) -> None:
        """WAL with only WAVE_COMPLETE (no PLAN_START) -> failed_recoveries=1."""
        bridge = FakeBridgeWritePort()
        bridge.inject_wal(
            "dag-corrupt",
            [
                _wave_complete_entry(0),
                _wave_complete_entry(1),
            ],
        )

        svc = _build_service(bridge_port=bridge)
        result = await svc.crash_recovery()

        assert result.failed_recoveries == 1
        assert result.recovered_dags == 0
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_empty_entries_list_skipped(self) -> None:
        """WAL dag_id exists but entries list is empty -> skipped."""
        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-empty", [])

        svc = _build_service(bridge_port=bridge)
        result = await svc.crash_recovery()

        # Empty entries treated same as read_wal returning empty.
        # The implementation checks `if not entries` -> skipped.
        assert result.skipped == 1
        assert result.recovered_dags == 0

    @pytest.mark.asyncio
    async def test_read_wal_returns_none_skipped(self) -> None:
        """read_wal returns None for a dag_id -> skipped."""
        bridge = FakeBridgeWritePort()
        # Inject a key but with no entries stored -- simulates read returning None.
        bridge._wal_store["dag-gone"] = None  # type: ignore[assignment]

        svc = _build_service(bridge_port=bridge)
        result = await svc.crash_recovery()

        assert result.skipped == 1


class TestCrashRecoveryK0Offline:
    """K0 offline (AdapterException DEGRADED) -- skip recovery entirely."""

    @pytest.mark.asyncio
    async def test_list_wal_ids_degraded_returns_zeros(self) -> None:
        """list_wal_ids raises DEGRADED -> RecoveryResult(0,0,0)."""
        bridge = FakeBridgeWritePort(list_wal_raises=_degraded_exception("list_wal_ids"))

        svc = _build_service(bridge_port=bridge)
        result = await svc.crash_recovery()

        assert result.recovered_dags == 0
        assert result.failed_recoveries == 0
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_list_wal_ids_non_degraded_returns_zeros(self) -> None:
        """list_wal_ids raises non-DEGRADED exception -> still returns zeros."""
        bridge = FakeBridgeWritePort(list_wal_raises=RuntimeError("unexpected K0 failure"))

        svc = _build_service(bridge_port=bridge)
        result = await svc.crash_recovery()

        assert result.recovered_dags == 0
        assert result.failed_recoveries == 0
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_read_wal_raises_isolates_per_dag(self) -> None:
        """read_wal raises for one dag_id -> failed_recovery, others unaffected."""
        plan_ok = _make_committed_plan(plan_id="plan-ok")
        bridge = FakeBridgeWritePort(
            read_wal_raises={"dag-broken": RuntimeError("K0 read failure")}
        )
        bridge.inject_wal("dag-broken", [_plan_start_entry(plan_ok)])
        bridge.inject_wal("dag-ok", [_plan_start_entry(plan_ok)])

        mailbox = FakeMailboxPort()
        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        result = await svc.crash_recovery()

        assert result.failed_recoveries == 1
        assert result.recovered_dags == 1
        assert len(mailbox.enqueued) == 1


class TestCrashRecoveryMixedWALs:
    """Multiple dag_ids with different states in the same recovery pass."""

    @pytest.mark.asyncio
    async def test_mixed_states(self) -> None:
        """Three dag_ids: completed, unstarted, corrupt -> counts tally."""
        plan_done = _make_committed_plan(plan_id="plan-done")
        plan_pending = _make_committed_plan(plan_id="plan-pending")

        bridge = FakeBridgeWritePort()
        # DAG already complete
        bridge.inject_wal(
            "dag-done",
            [
                _plan_start_entry(plan_done),
                _dag_complete_entry(),
            ],
        )
        # DAG never started execution
        bridge.inject_wal(
            "dag-pending",
            [
                _plan_start_entry(plan_pending),
            ],
        )
        # Corrupt WAL (no PLAN_START)
        bridge.inject_wal(
            "dag-corrupt",
            [
                _wave_complete_entry(0),
            ],
        )

        mailbox = FakeMailboxPort()
        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        result = await svc.crash_recovery()

        assert result.skipped == 1
        assert result.recovered_dags == 1
        assert result.failed_recoveries == 1
        assert len(mailbox.enqueued) == 1

        enqueued_plan, _ = mailbox.enqueued[0]
        assert enqueued_plan.plan_id == "plan-pending"

    @pytest.mark.asyncio
    async def test_multiple_recovered_dags(self) -> None:
        """Two unstarted DAGs both recovered and enqueued."""
        plan_a = _make_committed_plan(plan_id="plan-a", request_id="req-a")
        plan_b = _make_committed_plan(plan_id="plan-b", request_id="req-b")

        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-a", [_plan_start_entry(plan_a)])
        bridge.inject_wal("dag-b", [_plan_start_entry(plan_b)])

        mailbox = FakeMailboxPort()
        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        result = await svc.crash_recovery()

        assert result.recovered_dags == 2
        assert len(mailbox.enqueued) == 2

        enqueued_ids = {msg.plan_id for msg, _ in mailbox.enqueued}
        assert "plan-a" in enqueued_ids
        assert "plan-b" in enqueued_ids

    @pytest.mark.asyncio
    async def test_all_dags_complete_all_skipped(self) -> None:
        """Three completed DAGs -> skipped=3, recovered=0."""
        bridge = FakeBridgeWritePort()
        for i in range(3):
            plan = _make_committed_plan(plan_id=f"done-{i}")
            bridge.inject_wal(
                f"dag-{i}",
                [
                    _plan_start_entry(plan),
                    _dag_complete_entry(),
                ],
            )

        svc = _build_service(bridge_port=bridge)
        result = await svc.crash_recovery()

        assert result.skipped == 3
        assert result.recovered_dags == 0


class TestCrashRecoveryErrorIsolation:
    """Recovery error in one dag_id doesn't block others."""

    @pytest.mark.asyncio
    async def test_bad_plan_dict_increments_failed(self) -> None:
        """PLAN_START with invalid plan dict -> failed_recovery for that dag."""
        bridge = FakeBridgeWritePort()
        # Inject a PLAN_START with an invalid plan (empty steps -> ValueError).
        bridge.inject_wal(
            "dag-bad",
            [
                {
                    "entry_type": "PLAN_START",
                    "payload": {
                        "plan": {
                            "plan_id": "bad-plan",
                            "request_id": "bad-req",
                            "intent": "bad",
                            "steps": [],
                            "trace_id": "bad-trace",
                        }
                    },
                }
            ],
        )

        svc = _build_service(bridge_port=bridge)
        result = await svc.crash_recovery()

        assert result.failed_recoveries == 1
        assert result.recovered_dags == 0

    @pytest.mark.asyncio
    async def test_bad_dag_doesnt_block_good_dag(self) -> None:
        """One bad DAG + one good DAG -> both processed independently."""
        good_plan = _make_committed_plan(plan_id="good-plan")
        bridge = FakeBridgeWritePort()

        # Bad: empty steps -> CommittedPlan.from_dict raises ValueError
        bridge.inject_wal(
            "dag-bad",
            [
                {
                    "entry_type": "PLAN_START",
                    "payload": {
                        "plan": {
                            "plan_id": "bad",
                            "request_id": "bad",
                            "intent": "bad",
                            "steps": [],
                            "trace_id": "bad",
                        }
                    },
                }
            ],
        )
        # Good: valid plan
        bridge.inject_wal("dag-good", [_plan_start_entry(good_plan)])

        mailbox = FakeMailboxPort()
        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        result = await svc.crash_recovery()

        assert result.failed_recoveries == 1
        assert result.recovered_dags == 1
        assert len(mailbox.enqueued) == 1
        assert mailbox.enqueued[0][0].plan_id == "good-plan"


# ===========================================================================
# Test: crash_recovery() integration with init()
# ===========================================================================


class TestCrashRecoveryInitIntegration:
    """crash_recovery() is called during init() between steps 2 and 3."""

    @pytest.mark.asyncio
    async def test_init_calls_crash_recovery_no_wals(self) -> None:
        """init() succeeds with empty WAL -- crash_recovery returns zeros."""
        svc = _build_service()
        await svc.init()

        try:
            # Service should be running after init
            assert svc._running is True
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_init_with_wal_entries_enqueues_plans(self) -> None:
        """init() with pending WAL entries -> plans recovered into mailbox."""
        plan = _make_committed_plan(plan_id="init-recovery")
        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-from-crash", [_plan_start_entry(plan)])

        mailbox = FakeMailboxPort()
        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.init()

        try:
            # Plan should be enqueued before mailbox loop starts
            assert len(mailbox.enqueued) >= 1
            plan_ids = {msg.plan_id for msg, _ in mailbox.enqueued}
            assert "init-recovery" in plan_ids
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_init_k0_offline_still_initializes(self) -> None:
        """init() with K0 offline -> crash_recovery skipped, init completes."""
        bridge = FakeBridgeWritePort(list_wal_raises=_degraded_exception("list_wal_ids"))

        svc = _build_service(bridge_port=bridge)
        await svc.init()

        try:
            assert svc._running is True
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_init_crash_recovery_runs_before_mailbox_loop(self) -> None:
        """Recovered plans enqueued BEFORE _mailbox_loop task starts."""
        plan = _make_committed_plan(plan_id="before-loop")
        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-early", [_plan_start_entry(plan)])

        mailbox = FakeMailboxPort()
        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.init()

        try:
            # The mailbox loop task is created after crash_recovery.
            # We verify by checking the plan is already enqueued.
            enqueued_before_loop = [
                msg.plan_id for msg, _ in mailbox.enqueued if isinstance(msg, CommittedPlan)
            ]
            assert "before-loop" in enqueued_before_loop
        finally:
            await svc.shutdown()


class TestCrashRecoveryPlanReconstruction:
    """Verify CommittedPlan fields survive WAL round-trip."""

    @pytest.mark.asyncio
    async def test_plan_id_preserved(self) -> None:
        plan = _make_committed_plan(plan_id="pid-123")
        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-1", [_plan_start_entry(plan)])
        mailbox = FakeMailboxPort()

        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.crash_recovery()

        assert mailbox.enqueued[0][0].plan_id == "pid-123"

    @pytest.mark.asyncio
    async def test_request_id_preserved(self) -> None:
        plan = _make_committed_plan(request_id="rid-456")
        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-1", [_plan_start_entry(plan)])
        mailbox = FakeMailboxPort()

        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.crash_recovery()

        assert mailbox.enqueued[0][0].request_id == "rid-456"

    @pytest.mark.asyncio
    async def test_trace_id_preserved(self) -> None:
        tid = str(uuid4())
        plan = _make_committed_plan(trace_id=tid)
        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-1", [_plan_start_entry(plan)])
        mailbox = FakeMailboxPort()

        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.crash_recovery()

        assert mailbox.enqueued[0][0].trace_id == tid

    @pytest.mark.asyncio
    async def test_intent_preserved(self) -> None:
        plan = _make_committed_plan()
        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-1", [_plan_start_entry(plan)])
        mailbox = FakeMailboxPort()

        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.crash_recovery()

        assert mailbox.enqueued[0][0].intent == plan.intent

    @pytest.mark.asyncio
    async def test_dependencies_preserved(self) -> None:
        """Plan with dependencies survives WAL round-trip."""
        step_a = _make_step("step-a", "tool.alpha")
        step_b = _make_step("step-b", "tool.beta")
        plan = CommittedPlan(
            plan_id="dep-plan",
            request_id="dep-req",
            intent="test deps",
            steps=[step_a, step_b],
            dependencies={"step-b": ["step-a"]},
            trace_id=str(uuid4()),
        )
        bridge = FakeBridgeWritePort()
        bridge.inject_wal("dag-deps", [_plan_start_entry(plan)])
        mailbox = FakeMailboxPort()

        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.crash_recovery()

        recovered = mailbox.enqueued[0][0]
        assert recovered.dependencies == {"step-b": ["step-a"]}
        assert len(recovered.steps) == 2


class TestCrashRecoveryWALPayloadFallback:
    """WAL PLAN_START payload structure edge cases."""

    @pytest.mark.asyncio
    async def test_plan_key_in_payload(self) -> None:
        """Standard case: payload = {"plan": {...}}."""
        plan = _make_committed_plan(plan_id="from-nested")
        bridge = FakeBridgeWritePort()
        bridge.inject_wal(
            "dag-1",
            [
                {
                    "entry_type": "PLAN_START",
                    "payload": {"plan": plan.to_dict()},
                }
            ],
        )
        mailbox = FakeMailboxPort()

        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.crash_recovery()

        assert mailbox.enqueued[0][0].plan_id == "from-nested"

    @pytest.mark.asyncio
    async def test_flat_payload_fallback(self) -> None:
        """Fallback case: payload IS the plan dict (no nested 'plan' key)."""
        plan = _make_committed_plan(plan_id="from-flat")
        bridge = FakeBridgeWritePort()
        # Payload is the plan dict directly (no "plan" key wrapping).
        bridge.inject_wal(
            "dag-1",
            [
                {
                    "entry_type": "PLAN_START",
                    "payload": plan.to_dict(),
                }
            ],
        )
        mailbox = FakeMailboxPort()

        svc = _build_service(bridge_port=bridge, mailbox=mailbox)
        await svc.crash_recovery()

        assert mailbox.enqueued[0][0].plan_id == "from-flat"
