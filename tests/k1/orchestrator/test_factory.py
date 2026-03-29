"""
tests.k1.orchestrator.test_factory -- OrchestratorFactory tests (6.2.1).

Verifies:
  1. create_standalone() returns OrchestratorService with all test adapters, < 10ms.
  2. create_for_testing() allows port overrides.
  3. create_for_testing() rejects unknown override keys.
  4. create_with_ports() accepts arbitrary adapters.
  5. Construction order enforced (earlier deps available to later steps).
  6. ExecutionMonitor lazy init resolves correctly (circular dep).
  7. Guard list correct size and order.
  8. OrchestratorPolicies correctly derived from OrchestratorConfig.
  9. _build_test_adapters returns all 8 ports.
  10. OrchestratorFactory cannot be instantiated (static-only guard).
  11. Missing adapter keys in _construct_orchestrator raises KeyError.
  12. Config override in create_for_testing is respected.
"""

from __future__ import annotations

import time

import pytest

from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.adapters.mock_state_read_adapter import MockStateReadAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.adapters.test_mailbox_adapter import TestMailboxAdapter
from k1.orchestrator.adapters.test_workflow_storage_adapter import (
    TestWorkflowStorageAdapter,
)
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.orchestration.guards import (
    ConditionalEdgeEvaluator,
    ExecutionMonitor,
    MicroReplanCheckpoint,
    OutputSchemaGuard,
)
from k1.orchestrator.orchestration.orchestrator_service import OrchestratorService
from k1.orchestrator.types import OrchestratorPolicies

# ======================================================================
# Test: Static-only guard
# ======================================================================


class TestFactoryInstantiationGuard:
    """OrchestratorFactory must not be instantiable."""

    def test_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="static factory"):
            OrchestratorFactory()  # type: ignore[misc]


# ======================================================================
# Test: _build_policies
# ======================================================================


class TestBuildPolicies:
    """_build_policies maps OrchestratorConfig -> OrchestratorPolicies."""

    def test_default_config(self) -> None:
        config = OrchestratorConfig.default()
        policies = OrchestratorFactory._build_policies(config)

        assert isinstance(policies, OrchestratorPolicies)
        assert policies.normal_retries == config.step_max_retries
        assert policies.schema_retries == 1
        assert policies.step_timeout_default_ms == config.default_step_timeout_ms
        assert policies.max_steps_per_plan == 50
        assert policies.max_waves_per_plan == 20
        assert policies.max_concurrent_per_wave == config.max_wave_parallelism

    def test_custom_config(self) -> None:
        config = OrchestratorConfig.from_dict(
            {
                "step_max_retries": 5,
                "default_step_timeout_ms": 60000,
                "max_wave_parallelism": 3,
            }
        )
        policies = OrchestratorFactory._build_policies(config)

        assert policies.normal_retries == 5
        assert policies.step_timeout_default_ms == 60000
        assert policies.max_concurrent_per_wave == 3


# ======================================================================
# Test: _build_test_adapters
# ======================================================================


class TestBuildTestAdapters:
    """_build_test_adapters returns all 8 port adapters."""

    def test_returns_all_8_ports(self) -> None:
        adapters = OrchestratorFactory._build_test_adapters()

        assert len(adapters) == 8
        expected_keys = {
            "mailbox",
            "fabric",
            "planner",
            "state",
            "delta",
            "bridge",
            "event",
            "storage",
        }
        assert set(adapters.keys()) == expected_keys

    def test_correct_adapter_types(self) -> None:
        adapters = OrchestratorFactory._build_test_adapters()

        assert isinstance(adapters["mailbox"], TestMailboxAdapter)
        assert isinstance(adapters["fabric"], MockFabricAdapter)
        assert isinstance(adapters["planner"], MockPlannerAdapter)
        assert isinstance(adapters["state"], MockStateReadAdapter)
        assert isinstance(adapters["delta"], TestDeltaAdapter)
        assert isinstance(adapters["bridge"], MockBridgeAdapter)
        assert isinstance(adapters["event"], TestEventAdapter)
        assert isinstance(adapters["storage"], TestWorkflowStorageAdapter)


# ======================================================================
# Test: _build_guards
# ======================================================================


class TestBuildGuards:
    """Guard list: 4 guards in correct order, ExecutionMonitor has service_ref=None."""

    def test_guard_count_and_order(self) -> None:
        planner = MockPlannerAdapter()
        delta = TestDeltaAdapter()
        guards = OrchestratorFactory._build_guards(planner, delta)

        assert len(guards) == 4
        assert isinstance(guards[0], OutputSchemaGuard)
        assert isinstance(guards[1], ConditionalEdgeEvaluator)
        assert isinstance(guards[2], MicroReplanCheckpoint)
        assert isinstance(guards[3], ExecutionMonitor)

    def test_execution_monitor_service_ref_none(self) -> None:
        planner = MockPlannerAdapter()
        delta = TestDeltaAdapter()
        guards = OrchestratorFactory._build_guards(planner, delta)

        monitor: ExecutionMonitor = guards[3]
        assert monitor._service_ref is None

    def test_custom_max_micro_replans(self) -> None:
        planner = MockPlannerAdapter()
        delta = TestDeltaAdapter()
        guards = OrchestratorFactory._build_guards(
            planner,
            delta,
            max_micro_replans=3,
        )

        checkpoint: MicroReplanCheckpoint = guards[2]
        assert checkpoint._max_replans == 3


# ======================================================================
# Test: _construct_orchestrator -- missing keys
# ======================================================================


class TestConstructOrchestratorValidation:
    """_construct_orchestrator rejects incomplete adapter dicts."""

    def test_missing_adapter_key_raises(self) -> None:
        config = OrchestratorConfig.default()
        adapters = OrchestratorFactory._build_test_adapters()
        del adapters["delta"]

        with pytest.raises(KeyError, match="delta"):
            OrchestratorFactory._construct_orchestrator(config, adapters)

    def test_missing_multiple_keys_lists_all(self) -> None:
        config = OrchestratorConfig.default()
        adapters = {"mailbox": TestMailboxAdapter()}  # missing 7 keys

        with pytest.raises(KeyError, match="Missing adapter"):
            OrchestratorFactory._construct_orchestrator(config, adapters)


# ======================================================================
# Test: create_standalone()
# ======================================================================


class TestCreateStandalone:
    """create_standalone: all test adapters, < 10ms, valid wiring."""

    @pytest.mark.asyncio
    async def test_returns_orchestrator_service(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        assert isinstance(service, OrchestratorService)

    @pytest.mark.asyncio
    async def test_completes_under_10ms(self) -> None:
        t0 = time.monotonic()
        await OrchestratorFactory.create_standalone()
        elapsed_ms = (time.monotonic() - t0) * 1000
        assert elapsed_ms < 10, f"create_standalone took {elapsed_ms:.1f}ms (limit 10ms)"

    @pytest.mark.asyncio
    async def test_execution_monitor_service_ref_set(self) -> None:
        """ExecutionMonitor._service_ref must point to the created service."""
        service = await OrchestratorFactory.create_standalone()
        # Access DAGExecutor's guards through internal attributes.
        dag = service._dag_executor
        guards = dag._guards
        monitor = guards[3]
        assert isinstance(monitor, ExecutionMonitor)
        assert monitor._service_ref is service

    @pytest.mark.asyncio
    async def test_uses_default_config(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        # create_standalone() disables admin to avoid HTTP server in tests
        expected = OrchestratorConfig.from_dict({"admin_enabled": False})
        assert service._config == expected


# ======================================================================
# Test: create_for_testing(overrides)
# ======================================================================


class TestCreateForTesting:
    """create_for_testing: test adapters with optional overrides."""

    @pytest.mark.asyncio
    async def test_no_overrides(self) -> None:
        service = await OrchestratorFactory.create_for_testing()
        assert isinstance(service, OrchestratorService)

    @pytest.mark.asyncio
    async def test_override_single_port(self) -> None:
        custom_delta = TestDeltaAdapter()
        service = await OrchestratorFactory.create_for_testing(
            overrides={"delta": custom_delta},
        )
        assert service._delta_port is custom_delta

    @pytest.mark.asyncio
    async def test_override_multiple_ports(self) -> None:
        custom_fabric = MockFabricAdapter()
        custom_planner = MockPlannerAdapter()
        service = await OrchestratorFactory.create_for_testing(
            overrides={
                "fabric": custom_fabric,
                "planner": custom_planner,
            },
        )
        assert service._fabric_port is custom_fabric
        assert service._planner_port is custom_planner

    @pytest.mark.asyncio
    async def test_unknown_override_key_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown port key"):
            await OrchestratorFactory.create_for_testing(
                overrides={"nonexistent_port": object()},
            )

    @pytest.mark.asyncio
    async def test_config_override(self) -> None:
        custom_config = OrchestratorConfig.from_dict(
            {
                "max_concurrent_dags": 3,
                "max_wave_parallelism": 7,
            }
        )
        service = await OrchestratorFactory.create_for_testing(
            config=custom_config,
        )
        assert service._config.max_concurrent_dags == 3
        assert service._config.max_wave_parallelism == 7


# ======================================================================
# Test: create_with_ports(**ports)
# ======================================================================


class TestCreateWithPorts:
    """create_with_ports: caller provides all 8 adapters explicitly."""

    @pytest.mark.asyncio
    async def test_all_ports_wired(self) -> None:
        mailbox = TestMailboxAdapter()
        fabric = MockFabricAdapter()
        planner = MockPlannerAdapter()
        state = MockStateReadAdapter()
        delta = TestDeltaAdapter()
        bridge = MockBridgeAdapter()
        event = TestEventAdapter()
        storage = TestWorkflowStorageAdapter()

        service = await OrchestratorFactory.create_with_ports(
            mailbox=mailbox,
            fabric=fabric,
            planner=planner,
            state=state,
            delta=delta,
            bridge=bridge,
            event=event,
            storage=storage,
        )

        assert isinstance(service, OrchestratorService)
        assert service._mailbox is mailbox
        assert service._fabric_port is fabric
        assert service._planner_port is planner
        assert service._state_port is state
        assert service._delta_port is delta
        assert service._bridge_port is bridge

    @pytest.mark.asyncio
    async def test_custom_config(self) -> None:
        custom_config = OrchestratorConfig.from_dict(
            {
                "step_max_retries": 10,
            }
        )
        service = await OrchestratorFactory.create_with_ports(
            config=custom_config,
            mailbox=TestMailboxAdapter(),
            fabric=MockFabricAdapter(),
            planner=MockPlannerAdapter(),
            state=MockStateReadAdapter(),
            delta=TestDeltaAdapter(),
            bridge=MockBridgeAdapter(),
            event=TestEventAdapter(),
            storage=TestWorkflowStorageAdapter(),
        )
        assert service._config.step_max_retries == 10


# ======================================================================
# Test: Wiring integrity
# ======================================================================


class TestWiringIntegrity:
    """Deep checks on internal wiring correctness."""

    @pytest.mark.asyncio
    async def test_error_router_receives_delta_port(self) -> None:
        delta = TestDeltaAdapter()
        service = await OrchestratorFactory.create_for_testing(
            overrides={"delta": delta},
        )
        # ErrorRouter stores delta as _delta_port
        router = service._error_router
        assert router._delta_port is delta

    @pytest.mark.asyncio
    async def test_step_runner_receives_policies(self) -> None:
        config = OrchestratorConfig.from_dict({"step_max_retries": 7})
        service = await OrchestratorFactory.create_for_testing(config=config)

        # StepRunner stores policies as _policies
        dag = service._dag_executor
        step_runner = dag._step_runner
        assert step_runner._policies.normal_retries == 7

    @pytest.mark.asyncio
    async def test_workflow_engine_is_wired(self) -> None:
        """WorkflowEngine facade is assigned to OrchestratorService."""
        from k1.orchestrator.workflows.workflow_engine import WorkflowEngine

        service = await OrchestratorFactory.create_standalone()
        assert isinstance(service._workflow_engine, WorkflowEngine)

    @pytest.mark.asyncio
    async def test_connector_lifecycle_is_wired(self) -> None:
        from k1.orchestrator.connectors.connector_lifecycle import (
            ConnectorLifecycleManager,
        )

        service = await OrchestratorFactory.create_standalone()
        assert isinstance(service._connector_lifecycle, ConnectorLifecycleManager)

    @pytest.mark.asyncio
    async def test_concurrency_guard_not_in_dag_guards(self) -> None:
        """ConcurrencyGuard wraps _process_one, NOT in DAG guard list."""
        from k1.orchestrator.orchestration.guards import ConcurrencyGuard

        service = await OrchestratorFactory.create_standalone()
        dag = service._dag_executor
        for g in dag._guards:
            assert not isinstance(g, ConcurrencyGuard)

    @pytest.mark.asyncio
    async def test_dag_executor_has_param_resolver(self) -> None:
        service = await OrchestratorFactory.create_standalone()
        dag = service._dag_executor
        assert dag._param_resolver is not None
