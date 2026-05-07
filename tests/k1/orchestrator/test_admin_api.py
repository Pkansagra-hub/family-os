"""
Tests for Epic 6.3: Admin API (IAdminPort + AdminHttpAdapter).

Validates:
  6.3.1 -- IAdminPort Protocol definition and type compliance.
  6.3.2 -- AdminHttpAdapter: all 18 endpoints, lifecycle (start/stop),
           JSON responses with X-Trace-Id header, method implementations.
  6.3.3 -- Factory wiring: admin_enabled creates adapter, admin_enabled=False
           skips admin. init() starts admin, shutdown() stops admin.

Test strategy:
  - Direct method calls for IAdminPort compliance (no HTTP).
  - aiohttp test_utils.TestClient for HTTP endpoint tests.
  - Factory integration tests for wiring validation.

Test Philosophy: Protocol-based fakes, explicit assertions, no magic mocking.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

import pytest
from aiohttp.test_utils import TestClient, TestServer

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.orchestrator.adapters.admin_http_adapter import AdminHttpAdapter
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.connectors.mcp_registrar import RegistrationResult
from k1.orchestrator.degradation import CircuitBreaker
from k1.orchestrator.orchestration.orchestrator_service import OrchestratorService
from k1.orchestrator.ports.admin_port import IAdminPort
from k1.orchestrator.types import (
    ActiveDAGInfo,
    AggregatedResult,
    DrainResult,
    ErrorSeverity,
    HealthStatus,
    PlanAck,
    ProcessResult,
)

# ===========================================================================
# Fakes -- minimal Protocol implementations for admin testing
# ===========================================================================


class FakeMailbox:
    """Fake IMailboxPort -- FIFO queue with depth tracking."""

    def __init__(self) -> None:
        self._queue: List[Any] = []
        self._log: List[tuple] = []

    def enqueue(self, msg: Any, priority: str = "INTERACTIVE") -> int:
        self._queue.append(msg)
        self._log.append((msg, priority))
        return 0

    def dequeue(self) -> Optional[Any]:
        return self._queue.pop(0) if self._queue else None

    def depth(self) -> int:
        return len(self._queue)

    def peek_priority(self) -> Optional[str]:
        return "INTERACTIVE" if self._queue else None


class FakeDeltaEmitPort:
    """Fake IDeltaEmitPort -- captures emitted events."""

    def __init__(self) -> None:
        self.emitted: List[tuple] = []

    async def emit(self, event_topic: str, payload: Dict[str, Any], trace_id: str) -> None:
        self.emitted.append((event_topic, payload, trace_id))

    async def emit_progress(self, step_id: str, summary: str, trace_id: str) -> None:
        self.emitted.append(("progress", {"step_id": step_id, "summary": summary}, trace_id))

class FakeFabricPort:
    """Fake IFabricGatewayPort."""

    async def execute(self, *a: Any, **kw: Any) -> Any:
        return None

    async def list_capabilities(self) -> list:
        return []

    async def check_capability(self, *a: Any, **kw: Any) -> Any:
        return None


class FakePlannerPort:
    """Fake IPlannerPort."""

    def __init__(self) -> None:
        self._cb: Any = None

    async def request_plan(self, *a: Any, **kw: Any) -> PlanAck:
        return PlanAck(request_id="r-1", status="ACCEPTED")

    async def cancel_plan(self, *a: Any, **kw: Any) -> None:
        pass


class FakeStatePort:
    """Fake IStateReadPort."""

    async def read_section(self, *a: Any, **kw: Any) -> dict:
        return {}

    async def read_full(self, *a: Any, **kw: Any) -> dict:
        return {}

    async def snapshot(self, *a: Any, **kw: Any) -> Any:
        return None


class FakeBridgePort:
    """Fake IBridgeWritePort."""

    async def write_wal(self, *a: Any, **kw: Any) -> None:
        pass

    async def read_wal(self, *a: Any, **kw: Any) -> list:
        return []

    async def list_wal_ids(self) -> list:
        return []

    async def submit_audit(self, *a: Any, **kw: Any) -> None:
        pass


class FakeEventPort:
    """Fake IEventSubscriptionPort."""

    def subscribe(
        self, topic: str, handler: Callable[[str, Dict[str, Any]], None]
    ) -> SubscriptionHandle:
        return SubscriptionHandle(subscription_id=f"sub-{topic}", topic=topic)

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        return True

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        pass


class FakeWorkflowStoragePort:
    """Fake IWorkflowStoragePort."""

    async def store_workflow(self, *a: Any, **kw: Any) -> None:
        pass

    async def load_workflow(self, *a: Any, **kw: Any) -> None:
        return None

    async def list_workflows(self, *a: Any, **kw: Any) -> list:
        return []

    async def update_trigger_state(self, *a: Any, **kw: Any) -> None:
        pass


class FakeDAGExecutor:
    """Fake DAGExecutorLike."""

    def __init__(self) -> None:
        self.interrupt_flag: bool = False
        self._current_dag_info: Optional[ActiveDAGInfo] = None

    async def execute(self, plan: Any, ctx: Any) -> AggregatedResult:
        return AggregatedResult.from_medium(step_results=[], trace_id="t", duration_ms=0)


class FakeConstraintResolver:
    """Fake ConstraintResolverLike."""

    async def validate(self, plan: Any, ctx: Any) -> Any:
        class _FakeResult:
            valid = True
            issues: list = []

        return _FakeResult()


class FakeWorkflowRegistry:
    async def list_active(self) -> list:
        return []


class FakeWorkflowScheduler:
    _started = False
    _triggers: dict = {}

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False


class FakeWorkflowEngine:
    """Fake WorkflowEngineLike with registry/scheduler/gap_detector."""

    def __init__(self) -> None:
        self.registry = FakeWorkflowRegistry()
        self.scheduler = FakeWorkflowScheduler()
        self.gap_detector = _FakeGapDetector()

    async def execute_workflow(self, request: Any, ctx: Any) -> ProcessResult:
        return ProcessResult.COMPLETED

    async def save_workflow(self, request: Any, ctx: Any) -> ProcessResult:
        return ProcessResult.COMPLETED


class _FakeGapDetector:
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class FakeConnectorLifecycle:
    """Fake ConnectorLifecycleLike."""

    def __init__(self) -> None:
        self._last_registration: Optional[RegistrationResult] = None

    async def discover_and_register(self) -> RegistrationResult:
        result = RegistrationResult(registered=0, skipped=0, errors=[])
        self._last_registration = result
        return result

    def start_lifecycle_monitoring(self) -> None:
        pass

    def stop_lifecycle_monitoring(self) -> None:
        pass


class FakeErrorRouter:
    """Fake ErrorRouterLike."""

    def classify(self, error: Any, ctx: Any) -> ErrorSeverity:
        return ErrorSeverity.RECOVERABLE


class FakeConcurrencyGuard:
    """Fake ConcurrencyGuardLike with controllable active state."""

    def __init__(self) -> None:
        self.active: bool = False

    def acquire(self, ctx: Any) -> bool:
        if self.active:
            return False
        self.active = True
        return True

    def release(self, ctx: Any) -> None:
        self.active = False


# ===========================================================================
# Helpers
# ===========================================================================


def _default_config(**overrides: Any) -> OrchestratorConfig:
    """Build OrchestratorConfig with admin enabled for tests."""
    defaults: Dict[str, Any] = {
        "admin_enabled": True,
        "admin_port": 8081,
        "context_reap_interval_ms": 600_000,
    }
    defaults.update(overrides)
    return OrchestratorConfig(**defaults)


def _build_service(
    config: Optional[OrchestratorConfig] = None,
    concurrency_guard: Optional[FakeConcurrencyGuard] = None,
    dag_executor: Optional[FakeDAGExecutor] = None,
    connector_lifecycle: Optional[FakeConnectorLifecycle] = None,
    planner_port: Optional[FakePlannerPort] = None,
    mailbox: Optional[FakeMailbox] = None,
) -> OrchestratorService:
    """Build a minimally wired OrchestratorService for admin tests."""
    cfg = config or _default_config()
    mb = mailbox or FakeMailbox()
    guard = concurrency_guard or FakeConcurrencyGuard()
    executor = dag_executor or FakeDAGExecutor()
    lifecycle = connector_lifecycle or FakeConnectorLifecycle()
    pp = planner_port or FakePlannerPort()
    return OrchestratorService(
        mailbox=mb,
        dag_executor=executor,
        constraint_resolver=FakeConstraintResolver(),
        workflow_engine=FakeWorkflowEngine(),
        connector_lifecycle=lifecycle,
        error_router=FakeErrorRouter(),
        concurrency_guard=guard,
        fabric_port=FakeFabricPort(),
        planner_port=pp,
        state_port=FakeStatePort(),
        delta_port=FakeDeltaEmitPort(),
        bridge_port=FakeBridgePort(),
        event_port=FakeEventPort(),
        config=cfg,
    )


def _build_adapter(
    service: Optional[OrchestratorService] = None,
    config: Optional[OrchestratorConfig] = None,
    **service_kw: Any,
) -> AdminHttpAdapter:
    """Build an AdminHttpAdapter wrapping a service."""
    cfg = config or _default_config()
    svc = service or _build_service(config=cfg, **service_kw)
    return AdminHttpAdapter(svc, cfg)


# ===========================================================================
# 6.3.1 -- IAdminPort Protocol tests
# ===========================================================================


class TestIAdminPortProtocol:
    """Validate IAdminPort Protocol definition."""

    def test_admin_http_adapter_is_runtime_checkable(self) -> None:
        """AdminHttpAdapter should pass isinstance check against IAdminPort."""
        adapter = _build_adapter()
        assert isinstance(adapter, IAdminPort)

    def test_protocol_has_health_methods(self) -> None:
        """IAdminPort must declare health_live, health_ready, health_status."""
        assert hasattr(IAdminPort, "health_live")
        assert hasattr(IAdminPort, "health_ready")
        assert hasattr(IAdminPort, "health_status")

    def test_protocol_has_dag_methods(self) -> None:
        """IAdminPort must declare list_active_dags, get_dag_detail, cancel_dag."""
        assert hasattr(IAdminPort, "list_active_dags")
        assert hasattr(IAdminPort, "get_dag_detail")
        assert hasattr(IAdminPort, "cancel_dag")

    def test_protocol_has_cb_methods(self) -> None:
        """IAdminPort must declare list_circuit_breakers, set_cb_state."""
        assert hasattr(IAdminPort, "list_circuit_breakers")
        assert hasattr(IAdminPort, "set_cb_state")

    def test_protocol_has_scheduler_methods(self) -> None:
        """IAdminPort must declare list_triggers, get_trigger."""
        assert hasattr(IAdminPort, "list_triggers")
        assert hasattr(IAdminPort, "get_trigger")

    def test_protocol_has_drain(self) -> None:
        """IAdminPort must declare drain."""
        assert hasattr(IAdminPort, "drain")

    def test_protocol_has_config(self) -> None:
        """IAdminPort must declare get_config."""
        assert hasattr(IAdminPort, "get_config")

    def test_protocol_has_mailbox_methods(self) -> None:
        """IAdminPort must declare get_mailbox_depth, get_mailbox_stats."""
        assert hasattr(IAdminPort, "get_mailbox_depth")
        assert hasattr(IAdminPort, "get_mailbox_stats")

    def test_protocol_has_mcp_methods(self) -> None:
        """IAdminPort must declare list_mcp_servers, trigger_mcp_rediscovery."""
        assert hasattr(IAdminPort, "list_mcp_servers")
        assert hasattr(IAdminPort, "trigger_mcp_rediscovery")

    def test_protocol_has_metrics_and_version(self) -> None:
        """IAdminPort must declare get_metrics, get_version."""
        assert hasattr(IAdminPort, "get_metrics")
        assert hasattr(IAdminPort, "get_version")


# ===========================================================================
# 6.3.2 -- AdminHttpAdapter direct method tests (no HTTP)
# ===========================================================================


class TestAdminHealthMethods:
    """Test health_live, health_ready, health_status (direct calls)."""

    @pytest.mark.asyncio
    async def test_health_live_always_alive(self) -> None:
        adapter = _build_adapter()
        result = await adapter.health_live()
        assert result == {"status": "alive"}

    @pytest.mark.asyncio
    async def test_health_ready_before_init(self) -> None:
        """Before init(), ready should be False."""
        adapter = _build_adapter()
        result = await adapter.health_ready()
        assert result["ready"] is False
        assert result["initialized"] is False
        assert result["running"] is False

    @pytest.mark.asyncio
    async def test_health_ready_after_init(self) -> None:
        """After init(), ready should be True."""
        service = _build_service()
        await service.init()
        try:
            adapter = AdminHttpAdapter(service, service.config)
            result = await adapter.health_ready()
            assert result["ready"] is True
            assert result["initialized"] is True
            assert result["running"] is True
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_health_status_healthy(self) -> None:
        """Status is HEALTHY when no CB issues and mailbox not full."""
        adapter = _build_adapter()
        status = await adapter.health_status()
        assert isinstance(status, HealthStatus)
        assert status.status == "HEALTHY"
        assert status.mailbox_depth == 0
        assert status.active_dags == 0

    @pytest.mark.asyncio
    async def test_health_status_with_active_dag(self) -> None:
        """active_dags=1 when concurrency guard is active."""
        guard = FakeConcurrencyGuard()
        guard.active = True
        service = _build_service(concurrency_guard=guard)
        adapter = AdminHttpAdapter(service, service.config)
        status = await adapter.health_status()
        assert status.active_dags == 1


class TestAdminDAGMethods:
    """Test list_active_dags, get_dag_detail, cancel_dag."""

    @pytest.mark.asyncio
    async def test_list_dags_empty_when_idle(self) -> None:
        adapter = _build_adapter()
        dags = await adapter.list_active_dags()
        assert dags == []

    @pytest.mark.asyncio
    async def test_list_dags_with_dag_info(self) -> None:
        """Returns DAG info when executor has _current_dag_info."""
        executor = FakeDAGExecutor()
        dag_info = ActiveDAGInfo(
            dag_id="dag-1",
            plan_id="plan-1",
            current_wave=2,
            total_waves=5,
            steps_completed=3,
            steps_failed=0,
            started_at=time.time(),
            trace_id="t-1",
        )
        executor._current_dag_info = dag_info
        guard = FakeConcurrencyGuard()
        guard.active = True
        service = _build_service(dag_executor=executor, concurrency_guard=guard)
        adapter = AdminHttpAdapter(service, service.config)
        dags = await adapter.list_active_dags()
        assert len(dags) == 1
        assert dags[0].dag_id == "dag-1"

    @pytest.mark.asyncio
    async def test_get_dag_detail_not_found(self) -> None:
        adapter = _build_adapter()
        detail = await adapter.get_dag_detail("nonexistent")
        assert detail is None

    @pytest.mark.asyncio
    async def test_cancel_dag_not_found(self) -> None:
        adapter = _build_adapter()
        cancelled = await adapter.cancel_dag("nonexistent")
        assert cancelled is False

    @pytest.mark.asyncio
    async def test_cancel_dag_sets_interrupt_flag(self) -> None:
        """cancel_dag sets interrupt_flag on DAGExecutor."""
        executor = FakeDAGExecutor()
        dag_info = ActiveDAGInfo(
            dag_id="dag-1",
            plan_id="p-1",
            current_wave=1,
            total_waves=3,
            steps_completed=1,
            steps_failed=0,
            started_at=time.time(),
            trace_id="t-1",
        )
        executor._current_dag_info = dag_info
        guard = FakeConcurrencyGuard()
        guard.active = True
        service = _build_service(dag_executor=executor, concurrency_guard=guard)
        adapter = AdminHttpAdapter(service, service.config)
        cancelled = await adapter.cancel_dag("dag-1")
        assert cancelled is True
        assert executor.interrupt_flag is True


class TestAdminCBMethods:
    """Test list_circuit_breakers, set_cb_state."""

    @pytest.mark.asyncio
    async def test_list_cbs_empty_when_no_cb(self) -> None:
        adapter = _build_adapter()
        cbs = await adapter.list_circuit_breakers()
        assert cbs == {}

    @pytest.mark.asyncio
    async def test_list_cbs_returns_cb_when_present(self) -> None:
        """list_circuit_breakers returns non-empty dict when CB exists."""
        pp = FakePlannerPort()
        pp._cb = CircuitBreaker("CB_PLANNER", failure_threshold=3)
        adapter = _build_adapter(planner_port=pp)
        cbs = await adapter.list_circuit_breakers()
        assert "CB_PLANNER" in cbs
        cb_state = cbs["CB_PLANNER"]
        assert cb_state.state == "CLOSED"
        assert cb_state.failure_count == 0
        assert cb_state.config.name == "CB_PLANNER"

    @pytest.mark.asyncio
    async def test_list_cbs_reflects_open_state(self) -> None:
        """CB in OPEN state is reflected in the returned state."""
        pp = FakePlannerPort()
        cb = CircuitBreaker("CB_PLANNER", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        pp._cb = cb
        adapter = _build_adapter(planner_port=pp)
        cbs = await adapter.list_circuit_breakers()
        assert cbs["CB_PLANNER"].state == "OPEN"
        assert cbs["CB_PLANNER"].failure_count == 2

    @pytest.mark.asyncio
    async def test_set_cb_state_open_trips_breaker(self) -> None:
        """set_cb_state('OPEN') trips the circuit breaker."""
        pp = FakePlannerPort()
        pp._cb = CircuitBreaker("CB_PLANNER")
        adapter = _build_adapter(planner_port=pp)
        ok = await adapter.set_cb_state("CB_PLANNER", "OPEN")
        assert ok is True
        assert pp._cb.state.value == "OPEN"

    @pytest.mark.asyncio
    async def test_set_cb_state_closed_resets_breaker(self) -> None:
        """set_cb_state('CLOSED') resets the circuit breaker."""
        pp = FakePlannerPort()
        cb = CircuitBreaker("CB_PLANNER", failure_threshold=2)
        cb.trip()
        pp._cb = cb
        adapter = _build_adapter(planner_port=pp)
        ok = await adapter.set_cb_state("CB_PLANNER", "CLOSED")
        assert ok is True
        assert pp._cb.state.value == "CLOSED"

    @pytest.mark.asyncio
    async def test_set_cb_unknown_name_returns_false(self) -> None:
        adapter = _build_adapter()
        ok = await adapter.set_cb_state("CB_UNKNOWN", "OPEN")
        assert ok is False

    @pytest.mark.asyncio
    async def test_set_cb_invalid_state_returns_false(self) -> None:
        adapter = _build_adapter()
        ok = await adapter.set_cb_state("CB_PLANNER", "INVALID_STATE")
        assert ok is False


class TestAdminSchedulerMethods:
    """Test list_triggers, get_trigger."""

    @pytest.mark.asyncio
    async def test_list_triggers_empty(self) -> None:
        adapter = _build_adapter()
        triggers = await adapter.list_triggers()
        assert triggers == []

    @pytest.mark.asyncio
    async def test_get_trigger_not_found(self) -> None:
        adapter = _build_adapter()
        trigger = await adapter.get_trigger("wf-nonexistent")
        assert trigger is None


class TestAdminDrain:
    """Test drain operation."""

    @pytest.mark.asyncio
    async def test_drain_immediate_when_no_active_dag(self) -> None:
        """Drain completes immediately when no DAG is active."""
        adapter = _build_adapter()
        result = await adapter.drain(timeout_ms=1000)
        assert isinstance(result, DrainResult)
        assert result.drained is True
        assert result.active_dags_remaining == 0
        assert result.timeout_reached is False

    @pytest.mark.asyncio
    async def test_drain_stops_running_flag(self) -> None:
        """Drain sets _running to False on the service."""
        service = _build_service()
        service._running = True
        adapter = AdminHttpAdapter(service, service.config)
        await adapter.drain(timeout_ms=100)
        assert service._running is False


class TestAdminConfigMethod:
    """Test get_config."""

    @pytest.mark.asyncio
    async def test_get_config_returns_dict(self) -> None:
        adapter = _build_adapter()
        cfg = await adapter.get_config()
        assert isinstance(cfg, dict)
        assert "admin_enabled" in cfg
        assert "admin_port" in cfg
        assert cfg["admin_enabled"] is True

    @pytest.mark.asyncio
    async def test_get_config_matches_source(self) -> None:
        config = _default_config(mailbox_capacity=42)
        adapter = _build_adapter(config=config)
        cfg = await adapter.get_config()
        assert cfg["mailbox_capacity"] == 42


class TestAdminMailboxMethods:
    """Test get_mailbox_depth, get_mailbox_stats."""

    @pytest.mark.asyncio
    async def test_mailbox_depth_empty(self) -> None:
        adapter = _build_adapter()
        depth = await adapter.get_mailbox_depth()
        assert depth["depth"] == 0
        assert "capacity" in depth

    @pytest.mark.asyncio
    async def test_mailbox_depth_with_messages(self) -> None:
        mb = FakeMailbox()
        mb.enqueue("msg1")
        mb.enqueue("msg2")
        service = _build_service(mailbox=mb)
        adapter = AdminHttpAdapter(service, service.config)
        depth = await adapter.get_mailbox_depth()
        assert depth["depth"] == 2

    @pytest.mark.asyncio
    async def test_mailbox_stats(self) -> None:
        adapter = _build_adapter()
        stats = await adapter.get_mailbox_stats()
        assert stats["depth"] == 0
        assert stats["pending_plans"] == 0
        assert "capacity" in stats


class TestAdminMCPMethods:
    """Test list_mcp_servers, trigger_mcp_rediscovery."""

    @pytest.mark.asyncio
    async def test_list_mcp_servers_empty(self) -> None:
        adapter = _build_adapter()
        servers = await adapter.list_mcp_servers()
        assert servers == []

    @pytest.mark.asyncio
    async def test_trigger_mcp_rediscovery(self) -> None:
        adapter = _build_adapter()
        result = await adapter.trigger_mcp_rediscovery()
        assert result["triggered"] is True
        assert result["registered"] == 0


class TestAdminMetricsVersion:
    """Test get_metrics, get_version."""

    @pytest.mark.asyncio
    async def test_get_metrics(self) -> None:
        adapter = _build_adapter()
        metrics = await adapter.get_metrics()
        assert "uptime_ms" in metrics
        assert "mailbox_depth" in metrics
        assert "pending_plans" in metrics
        assert metrics["initialized"] is False

    @pytest.mark.asyncio
    async def test_get_version(self) -> None:
        adapter = _build_adapter()
        version = await adapter.get_version()
        assert "version" in version
        assert "python" in version
        assert "platform" in version
        assert "build" in version


# ===========================================================================
# 6.3.2 -- HTTP endpoint tests (via aiohttp TestClient)
# ===========================================================================


class TestAdminHTTPEndpoints:
    """Test all 18 HTTP endpoints using aiohttp TestClient."""

    @pytest.fixture
    def adapter(self) -> AdminHttpAdapter:
        return _build_adapter()

    @pytest.fixture
    async def client(self, adapter: AdminHttpAdapter) -> TestClient:
        """Create aiohttp TestClient from the adapter's app."""
        server = TestServer(adapter._app)
        client = TestClient(server)
        await client.start_server()
        yield client
        await client.close()

    @pytest.mark.asyncio
    async def test_get_health_live(self, client: TestClient) -> None:
        resp = await client.get("/health/live")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "alive"
        assert "X-Trace-Id" in resp.headers

    @pytest.mark.asyncio
    async def test_get_health_ready_not_initialized(self, client: TestClient) -> None:
        resp = await client.get("/health/ready")
        assert resp.status == 503
        data = await resp.json()
        assert data["ready"] is False

    @pytest.mark.asyncio
    async def test_get_health_status(self, client: TestClient) -> None:
        resp = await client.get("/health/status")
        assert resp.status == 200
        data = await resp.json()
        assert "status" in data
        assert "uptime_ms" in data
        assert "mailbox_depth" in data

    @pytest.mark.asyncio
    async def test_get_admin_dags_empty(self, client: TestClient) -> None:
        resp = await client.get("/admin/dags")
        assert resp.status == 200
        data = await resp.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_get_dag_not_found(self, client: TestClient) -> None:
        resp = await client.get("/admin/dags/nonexistent")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_cancel_dag_not_found(self, client: TestClient) -> None:
        resp = await client.post("/admin/dags/nonexistent/cancel")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_get_circuit_breakers(self, client: TestClient) -> None:
        resp = await client.get("/admin/circuit-breakers")
        assert resp.status == 200
        data = await resp.json()
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_set_cb_state_invalid(self, client: TestClient) -> None:
        resp = await client.post(
            "/admin/circuit-breakers/CB_UNKNOWN/state",
            json={"state": "OPEN"},
        )
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_get_scheduler_triggers(self, client: TestClient) -> None:
        resp = await client.get("/admin/scheduler/triggers")
        assert resp.status == 200
        data = await resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_trigger_not_found(self, client: TestClient) -> None:
        resp = await client.get("/admin/scheduler/triggers/wf-missing")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_post_drain(self, client: TestClient) -> None:
        resp = await client.post("/admin/drain", json={"timeout_ms": 100})
        assert resp.status == 200
        data = await resp.json()
        assert data["drained"] is True

    @pytest.mark.asyncio
    async def test_get_config(self, client: TestClient) -> None:
        resp = await client.get("/admin/config")
        assert resp.status == 200
        data = await resp.json()
        assert "admin_enabled" in data

    @pytest.mark.asyncio
    async def test_get_mailbox_depth(self, client: TestClient) -> None:
        resp = await client.get("/admin/mailbox/depth")
        assert resp.status == 200
        data = await resp.json()
        assert "depth" in data
        assert "capacity" in data

    @pytest.mark.asyncio
    async def test_get_mailbox_stats(self, client: TestClient) -> None:
        resp = await client.get("/admin/mailbox/stats")
        assert resp.status == 200
        data = await resp.json()
        assert "pending_plans" in data

    @pytest.mark.asyncio
    async def test_get_mcp_servers(self, client: TestClient) -> None:
        resp = await client.get("/admin/mcp/servers")
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_post_mcp_rediscover(self, client: TestClient) -> None:
        resp = await client.post("/admin/mcp/rediscover")
        assert resp.status == 200
        data = await resp.json()
        assert data["triggered"] is True

    @pytest.mark.asyncio
    async def test_get_metrics(self, client: TestClient) -> None:
        resp = await client.get("/admin/metrics")
        assert resp.status == 200
        data = await resp.json()
        assert "uptime_ms" in data

    @pytest.mark.asyncio
    async def test_get_version(self, client: TestClient) -> None:
        resp = await client.get("/admin/version")
        assert resp.status == 200
        data = await resp.json()
        assert "version" in data
        assert "python" in data


# ===========================================================================
# 6.3.2 -- Lifecycle tests (start/stop)
# ===========================================================================


class TestAdminLifecycle:
    """Test AdminHttpAdapter start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        """start() creates runner+site, stop() cleans up."""
        adapter = _build_adapter()
        await adapter.start(port=18091)
        assert adapter._runner is not None
        assert adapter._site is not None
        await adapter.stop()
        assert adapter._runner is None
        assert adapter._site is None

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self) -> None:
        """stop() is safe to call when never started."""
        adapter = _build_adapter()
        await adapter.stop()  # Should not raise


# ===========================================================================
# 6.3.3 -- Factory wiring tests
# ===========================================================================


class TestAdminFactoryWiring:
    """Test factory wiring of admin adapter."""

    @pytest.mark.asyncio
    async def test_standalone_no_admin(self) -> None:
        """create_standalone() should NOT create admin adapter."""
        from k1.orchestrator.factory import OrchestratorFactory

        service = await OrchestratorFactory.create_standalone()
        assert service._admin is None

    @pytest.mark.asyncio
    async def test_for_testing_no_admin(self) -> None:
        """create_for_testing() with default config should NOT create admin."""
        from k1.orchestrator.factory import OrchestratorFactory

        service = await OrchestratorFactory.create_for_testing()
        assert service._admin is None

    @pytest.mark.asyncio
    async def test_for_testing_with_admin_enabled(self) -> None:
        """create_for_testing() with admin_enabled=True creates admin adapter."""
        from k1.orchestrator.factory import OrchestratorFactory

        config = OrchestratorConfig.from_dict({"admin_enabled": True})
        service = await OrchestratorFactory.create_for_testing(config=config)
        assert service._admin is not None
        assert isinstance(service._admin, AdminHttpAdapter)

    @pytest.mark.asyncio
    async def test_admin_attribute_exists_on_service(self) -> None:
        """OrchestratorService should have _admin slot."""
        service = _build_service()
        assert hasattr(service, "_admin")
        assert service._admin is None


# ===========================================================================
# 6.3.3 -- Init/shutdown integration with admin
# ===========================================================================


class TestAdminInitShutdownIntegration:
    """Test admin start/stop within init()/shutdown() lifecycle."""

    @pytest.mark.asyncio
    async def test_init_starts_admin_when_enabled(self) -> None:
        """init() starts admin HTTP server when config.admin_enabled=True."""
        config = _default_config(admin_enabled=True, admin_port=18092)
        service = _build_service(config=config)
        adapter = AdminHttpAdapter(service, config)
        service._admin = adapter
        await service.init()
        try:
            assert adapter._runner is not None
            assert adapter._site is not None
        finally:
            await service.shutdown()
            # After shutdown, admin should be stopped.
            assert adapter._runner is None

    @pytest.mark.asyncio
    async def test_init_skips_admin_when_disabled(self) -> None:
        """init() does not start admin when config.admin_enabled=False."""
        config = _default_config(admin_enabled=False)
        service = _build_service(config=config)
        adapter = AdminHttpAdapter(service, config)
        service._admin = adapter
        await service.init()
        try:
            # Admin should NOT be started (admin_enabled=False).
            assert adapter._runner is None
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_init_skips_admin_when_none(self) -> None:
        """init() handles _admin=None gracefully."""
        config = _default_config(admin_enabled=True)
        service = _build_service(config=config)
        service._admin = None
        await service.init()
        try:
            assert service.initialized is True
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_stops_admin(self) -> None:
        """shutdown() stops admin server."""
        config = _default_config(admin_enabled=True, admin_port=18093)
        service = _build_service(config=config)
        adapter = AdminHttpAdapter(service, config)
        service._admin = adapter
        await service.init()
        assert adapter._runner is not None
        await service.shutdown()
        assert adapter._runner is None
