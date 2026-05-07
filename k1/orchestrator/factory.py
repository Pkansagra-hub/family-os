"""
k1.orchestrator.factory -- OrchestratorFactory (6.2.1).

Composition root for the Orchestrator subsystem.  Static methods only,
NO constructor.  Every object is created with explicit dependency
injection -- no service locator, no global state, no singletons.

Factory Methods:
  create_standalone()        -- all test adapters, zero deps, < 10ms, NO init()
  create_for_testing(...)    -- test adapters with optional overrides, NO init()
  create_with_ports(...)     -- caller provides exact adapters, NO init()
  create_production(config)  -- full prod stack, calls init() automatically

Private Helpers:
  _build_policies(config)          -- OrchestratorConfig -> OrchestratorPolicies
  _build_test_adapters()           -- 8 test adapters dict
  _build_guards(planner, delta)    -- ordered DAGGuard list
  _construct_orchestrator(config, adapters) -- 15-step dependency wiring

Design constraints:
  - OrchestratorFactory has NO constructor (static methods only).
  - Construction order is STRICT (factory-discovery.md section 10).
  - ExecutionMonitor circular dep resolved via lazy init (section 11).
  - ConcurrencyGuard NOT in guards list (wraps _process_one).
  - SubStepObserver NOT in guards list (managed by DAGExecutor lifecycle).
  - create_production() calls init(); test methods do NOT.
  - Factory does NOT implement lifecycle (6.2.2-6.2.5).

References:
  - docs/plans/factory-discovery.md (comprehensive wiring reference)
  - orchestrator-implementation-plan.md Issue 6.2.1
  - OrchestratorService Protocols (orchestrator_service.py lines 80-148)

Exports:
  OrchestratorFactory
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from k1.kernel.ports.hil_port import IHILPort
from k1.orchestrator.adapters.admin_http_adapter import AdminHttpAdapter

# -----------------------------------------------------------------------
# Test adapters (used by create_standalone / create_for_testing)
# -----------------------------------------------------------------------
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

# -----------------------------------------------------------------------
# Config + domain types
# -----------------------------------------------------------------------
from k1.orchestrator.config import OrchestratorConfig

# -----------------------------------------------------------------------
# Connector subsystem
# -----------------------------------------------------------------------
from k1.orchestrator.connectors.connector_lifecycle import ConnectorLifecycleManager
from k1.orchestrator.connectors.mcp_discovery import MCPToolDiscovery
from k1.orchestrator.connectors.mcp_registrar import MCPRegistrationBridge
from k1.orchestrator.metrics import OrchestratorMetrics
from k1.orchestrator.orchestration.constraint_resolver import ConstraintResolver

# -----------------------------------------------------------------------
# Core services
# -----------------------------------------------------------------------
from k1.orchestrator.orchestration.dag_executor import DAGExecutor
from k1.orchestrator.orchestration.error_router import ErrorRouter

# -----------------------------------------------------------------------
# Guards
# -----------------------------------------------------------------------
from k1.orchestrator.orchestration.guards import (
    ConcurrencyGuard,
    ConditionalEdgeEvaluator,
    ExecutionMonitor,
    FailureReplanCheckpoint,
    MicroReplanCheckpoint,
    OutputSchemaGuard,
)
from k1.orchestrator.orchestration.orchestrator_service import OrchestratorService
from k1.orchestrator.orchestration.param_resolver import ParamResolver
from k1.orchestrator.orchestration.step_runner import StepRunner

# -----------------------------------------------------------------------
# Port interfaces (used for type annotations in factory methods)
# -----------------------------------------------------------------------
from k1.orchestrator.ports.bridge_write_port import IBridgeWritePort
from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
from k1.orchestrator.ports.event_subscription_port import IEventSubscriptionPort
from k1.orchestrator.ports.fabric_gateway_port import IFabricGatewayPort
from k1.orchestrator.ports.mailbox_port import IMailboxPort
from k1.orchestrator.ports.planner_port import IPlannerPort
from k1.orchestrator.ports.state_read_port import IStateReadPort
from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort
from k1.orchestrator.types import OrchestratorPolicies

# -----------------------------------------------------------------------
# Workflow subsystem
# -----------------------------------------------------------------------
from k1.orchestrator.workflows.cross_workflow_resolver import (
    CrossWorkflowResolver,
    WorkflowDepthGuard,
)
from k1.orchestrator.workflows.gap_detector import ProactiveGapDetector
from k1.orchestrator.workflows.system_clock import SystemClock
from k1.orchestrator.workflows.workflow_compiler import WorkflowCompiler
from k1.orchestrator.workflows.workflow_engine import WorkflowEngine
from k1.orchestrator.workflows.workflow_registry import WorkflowRegistry
from k1.orchestrator.workflows.workflow_scheduler import WorkflowScheduler
from k1.orchestrator.workflows.workflow_supervisor import WorkflowRunSupervisor

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Port key constants (used as dict keys in adapter maps)
# -----------------------------------------------------------------------
_PORT_MAILBOX = "mailbox"
_PORT_FABRIC = "fabric"
_PORT_PLANNER = "planner"
_PORT_STATE = "state"
_PORT_DELTA = "delta"
_PORT_BRIDGE = "bridge"
_PORT_EVENT = "event"
_PORT_STORAGE = "storage"

_ALL_PORT_KEYS = frozenset(
    {
        _PORT_MAILBOX,
        _PORT_FABRIC,
        _PORT_PLANNER,
        _PORT_STATE,
        _PORT_DELTA,
        _PORT_BRIDGE,
        _PORT_EVENT,
        _PORT_STORAGE,
    }
)


class OrchestratorFactory:
    """Composition root for the Orchestrator subsystem.

    Static methods only.  No constructor, no instance state.
    Each factory method returns a fully wired OrchestratorService
    ready for use (or for the caller to init() manually in test
    scenarios).
    """

    # Prevent accidental instantiation.
    def __init__(self) -> None:
        raise TypeError(
            "OrchestratorFactory is a static factory.  "
            "Use OrchestratorFactory.create_standalone(), "
            "create_for_testing(), create_with_ports(), "
            "or create_production()."
        )

    # ==================================================================
    # Private: OrchestratorConfig -> OrchestratorPolicies
    # ==================================================================

    @staticmethod
    def _build_policies(config: OrchestratorConfig) -> OrchestratorPolicies:
        """Map OrchestratorConfig fields to OrchestratorPolicies.

        StepRunner and DAGExecutor consume OrchestratorPolicies, not
        OrchestratorConfig.  This helper bridges the two.

        Mapping (factory-discovery.md section 13):
          normal_retries       <- config.step_max_retries
          schema_retries       <- 1 (hardcoded V1)
          step_timeout_default <- config.default_step_timeout_ms
          max_steps_per_plan   <- 50 (hardcoded V1)
          max_waves_per_plan   <- 20 (hardcoded V1)
          max_concurrent       <- config.max_wave_parallelism
        """
        return OrchestratorPolicies(
            normal_retries=config.step_max_retries,
            schema_retries=1,
            step_timeout_default_ms=config.default_step_timeout_ms,
            max_steps_per_plan=50,
            max_waves_per_plan=20,
            max_concurrent_per_wave=config.max_wave_parallelism,
        )

    # ==================================================================
    # Private: build all 8 test adapters
    # ==================================================================

    @staticmethod
    def _build_test_adapters() -> Dict[str, Any]:
        """Instantiate all 8 test/mock adapters with default config.

        Returns a dict keyed by port name constants.  Every adapter
        is zero-config except MockPlannerAdapter and MockBridgeAdapter
        which accept optional callbacks/stores but default to None.
        """
        return {
            _PORT_MAILBOX: TestMailboxAdapter(),
            _PORT_FABRIC: MockFabricAdapter(),
            _PORT_PLANNER: MockPlannerAdapter(),
            _PORT_STATE: MockStateReadAdapter(),
            _PORT_DELTA: TestDeltaAdapter(),
            _PORT_BRIDGE: MockBridgeAdapter(),
            _PORT_EVENT: TestEventAdapter(),
            _PORT_STORAGE: TestWorkflowStorageAdapter(),
        }

    # ==================================================================
    # Private: build ordered DAG guard list
    # ==================================================================

    @staticmethod
    def _build_guards(
        planner_port: IPlannerPort,
        delta_port: IDeltaEmitPort,
        hil_port: IHILPort,
        *,
        max_micro_replans: int = 1,
    ) -> list:
        """Build the ordered DAGGuard list for DAGExecutor (step 12).

        Guard order matches OrchestratorConfig.guard_order default:
          [OutputSchemaGuard, ConditionalEdgeEvaluator,
           MicroReplanCheckpoint, ExecutionMonitor]

        ConcurrencyGuard is NOT in this list (wraps _process_one).
        SubStepObserver is NOT in this list (DAGExecutor lifecycle).

        ExecutionMonitor is created with service_ref=None.
        The caller MUST set ExecutionMonitor._service_ref after
        OrchestratorService is constructed (lazy init, section 11).

        Args:
            planner_port: For MicroReplanCheckpoint.
            delta_port: For ExecutionMonitor.emit_progress.
            hil_port: For ExecutionMonitor.after_wave override prompts.
            max_micro_replans: MicroReplanCheckpoint limit (default 1).

        Returns:
            list of 4 DAGGuard instances in execution order.
        """
        return [
            OutputSchemaGuard(),
            ConditionalEdgeEvaluator(),
            MicroReplanCheckpoint(planner_port, max_replans=max_micro_replans),
            ExecutionMonitor(delta_port, hil_port=hil_port),
            # M16.E2.I2: failure-driven replan runs LAST so the kernel's
            # ``_verify_orchestrator_monitor_binding`` (slot 3 ==
            # ExecutionMonitor) stays satisfied. ExecutionMonitor only
            # emits progress + override prompts and does not consume
            # downstream metadata, so this ordering is semantically safe.
            FailureReplanCheckpoint(planner_port, max_replans=max_micro_replans),
        ]

    # ==================================================================
    # Private: 15-step wiring
    # ==================================================================

    @staticmethod
    def _construct_orchestrator(
        config: OrchestratorConfig,
        adapters: Dict[str, Any],
        hil_port: Optional[IHILPort] = None,
    ) -> OrchestratorService:
        """Wire all components in dependency-safe order (15 steps).

        This is the heart of the composition root.  Every object is
        constructed exactly once, with explicit constructor injection.
        No default arguments are silently used -- every dep is visible.

        Steps are numbered to match factory-discovery.md section 10.

        Args:
            config: Validated OrchestratorConfig.
            adapters: Dict mapping port key -> adapter instance.
                      Must contain all 8 port keys.

        Returns:
            Fully wired OrchestratorService (NOT yet init()'d).

        Raises:
            KeyError: If any required port key is missing from adapters.
        """
        # -- Validate adapter keys upfront ------------------------------------
        missing = _ALL_PORT_KEYS - adapters.keys()
        if missing:
            raise KeyError(
                f"Missing adapter(s) for port(s): {sorted(missing)}.  "
                f"Required keys: {sorted(_ALL_PORT_KEYS)}"
            )

        # -- Unpack adapters (typed refs for readability) ---------------------
        mailbox_port: IMailboxPort = adapters[_PORT_MAILBOX]
        fabric_port: IFabricGatewayPort = adapters[_PORT_FABRIC]
        planner_port: IPlannerPort = adapters[_PORT_PLANNER]
        state_port: IStateReadPort = adapters[_PORT_STATE]
        delta_port: IDeltaEmitPort = adapters[_PORT_DELTA]
        bridge_port: IBridgeWritePort = adapters[_PORT_BRIDGE]
        event_port: IEventSubscriptionPort = adapters[_PORT_EVENT]
        storage_port: IWorkflowStoragePort = adapters[_PORT_STORAGE]

        # -- Derive policies from config --------------------------------------
        policies = OrchestratorFactory._build_policies(config)
        metrics = OrchestratorMetrics(enabled=config.metrics_enabled)

        # -- HIL port (use defensive null adapter when caller did not wire one) ---
        effective_hil_port: IHILPort = hil_port or _NullHILAdapter()

        # =====================================================================
        # STEP 1: ErrorRouter (depends only on delta_port)
        # =====================================================================
        error_router = ErrorRouter(delta_port)

        # =====================================================================
        # STEP 2: ConcurrencyGuard (zero deps -- asyncio.Lock internal)
        # =====================================================================
        concurrency_guard = ConcurrencyGuard()

        # =====================================================================
        # STEP 11: StepRunner (fabric_port, error_router, policies)
        # =====================================================================
        step_runner = StepRunner(fabric_port, error_router, policies, metrics=metrics)

        # =====================================================================
        # STEP 12: Guards (ordered DAGGuard list)
        #   ExecutionMonitor gets service_ref=None (lazy init).
        # =====================================================================
        guards = OrchestratorFactory._build_guards(
            planner_port,
            delta_port,
            effective_hil_port,
            max_micro_replans=config.max_micro_replans,
        )

        # =====================================================================
        # STEP 13: DAGExecutor
        #   9 positional args: 5 ports + step_runner + error_router
        #   + guards + param_resolver
        # =====================================================================
        dag_executor = DAGExecutor(
            fabric_port,
            planner_port,
            delta_port,
            state_port,
            bridge_port,
            step_runner,
            error_router,
            guards,
            ParamResolver(registry=None),
            metrics,
        )

        # =====================================================================
        # STEP 14a: ConstraintResolver
        # =====================================================================
        constraint_resolver = ConstraintResolver(
            fabric_port,
            hil_port=effective_hil_port,
        )

        # =====================================================================
        # STEP 14b: Workflow subsystem
        # =====================================================================
        clock = SystemClock()

        registry = WorkflowRegistry(storage_port)

        compiler = WorkflowCompiler(
            fabric_port,
            delta_port,
            storage_port,
            state_port,
            clock,
        )

        scheduler = WorkflowScheduler(
            storage_port,
            mailbox_port,
            state_port,
            clock,
            tick_interval_s=config.scheduler_tick_interval_ms / 1000.0,
            metrics=metrics,
        )

        depth_guard = WorkflowDepthGuard(max_depth=config.max_workflow_depth)

        cross_resolver = CrossWorkflowResolver(registry, compiler, depth_guard)

        supervisor = WorkflowRunSupervisor(
            registry,
            compiler,
            storage_port,
            delta_port,
            bridge_port,
        )

        gap_detector = ProactiveGapDetector(
            registry,
            compiler,
            storage_port,
            event_port,
            delta_port,
        )

        workflow_engine = WorkflowEngine(
            supervisor=supervisor,
            dag_executor=dag_executor,
            constraint_resolver=constraint_resolver,
            registry=registry,
            compiler=compiler,
            scheduler=scheduler,
            cross_resolver=cross_resolver,
            gap_detector=gap_detector,
            delta=delta_port,
            bridge=bridge_port,
        )

        # =====================================================================
        # STEP 15: Connector subsystem
        # =====================================================================
        discovery = MCPToolDiscovery(config_path=config.mcp_config_path)
        registrar = MCPRegistrationBridge(fabric_port, delta_port)
        connector_lifecycle = ConnectorLifecycleManager(
            discovery,
            registrar,
            event_port,
            delta_port,
            metrics,
        )

        # =====================================================================
        # FINAL: OrchestratorService (keyword-only constructor)
        # =====================================================================
        service = OrchestratorService(
            mailbox=mailbox_port,
            dag_executor=dag_executor,  # type: ignore[arg-type]  # DAGExecutor vs DAGExecutorLike param name (pre-existing)
            constraint_resolver=constraint_resolver,
            workflow_engine=workflow_engine,
            connector_lifecycle=connector_lifecycle,
            error_router=error_router,
            concurrency_guard=concurrency_guard,
            fabric_port=fabric_port,
            planner_port=planner_port,
            state_port=state_port,
            delta_port=delta_port,
            bridge_port=bridge_port,
            event_port=event_port,
            config=config,
            metrics=metrics,
            hil_port=effective_hil_port,
        )

        # =====================================================================
        # POST: ExecutionMonitor no longer needs service back-reference (E6.M1.3).
        # =====================================================================

        # =====================================================================
        # STEP 15.5: Admin HTTP adapter (6.3.3)
        #   Created AFTER service (circular dep -- reads service state).
        #   Injected via service._admin attribute.
        #   Lifecycle (start/stop) managed by service.init()/shutdown().
        #   Disabled in test configs (admin_enabled=False).
        # =====================================================================
        if config.admin_enabled:
            admin_adapter = AdminHttpAdapter(service, config)
            service._admin = admin_adapter

        logger.debug(
            "OrchestratorFactory._construct_orchestrator: wiring complete "
            "(guards=%d, config=%s)",
            len(guards),
            type(config).__name__,
        )

        return service

    # ==================================================================
    # Public: create_standalone() -- all test adapters, zero deps
    # ==================================================================

    @staticmethod
    async def create_standalone() -> OrchestratorService:
        """Create an OrchestratorService with all test adapters.

        Zero external dependencies, default OrchestratorConfig.
        Completes in < 10ms (no I/O, no init()).
        Used for unit testing the service in isolation.

        Returns:
            OrchestratorService wired with test adapters.
            Caller must call init() manually if needed.
        """
        config = OrchestratorConfig.from_dict({"admin_enabled": False})
        adapters = OrchestratorFactory._build_test_adapters()
        return OrchestratorFactory._construct_orchestrator(config, adapters)

    # ==================================================================
    # Public: create_for_testing(overrides) -- test adapters + overrides
    # ==================================================================

    @staticmethod
    async def create_for_testing(
        overrides: Optional[Dict[str, Any]] = None,
        *,
        config: Optional[OrchestratorConfig] = None,
        hil_port: Optional[IHILPort] = None,
    ) -> OrchestratorService:
        """Create an OrchestratorService with test adapters, allowing overrides.

        Starts with all 8 test adapters, then replaces any port whose
        key appears in ``overrides``.  This is the recommended entry
        point for integration tests that need one or two real adapters
        while keeping everything else mocked.

        Args:
            overrides: Dict mapping port key -> adapter instance.
                       Valid keys: mailbox, fabric, planner, state,
                       delta, bridge, event, storage.
            config: Optional OrchestratorConfig override.

        Returns:
            OrchestratorService wired with merged adapters.
            Caller must call init() manually if needed.

        Raises:
            KeyError: If an override key is not a valid port key.
        """
        if overrides:
            unknown = set(overrides) - _ALL_PORT_KEYS
            if unknown:
                raise KeyError(
                    f"Unknown port key(s) in overrides: {sorted(unknown)}.  "
                    f"Valid keys: {sorted(_ALL_PORT_KEYS)}"
                )

        effective_config = config or OrchestratorConfig.from_dict({"admin_enabled": False})
        adapters = OrchestratorFactory._build_test_adapters()

        if overrides:
            adapters.update(overrides)

        return OrchestratorFactory._construct_orchestrator(effective_config, adapters, hil_port)

    # ==================================================================
    # Public: create_with_ports(**ports) -- caller provides adapters
    # ==================================================================

    @staticmethod
    async def create_with_ports(
        *,
        config: Optional[OrchestratorConfig] = None,
        mailbox: IMailboxPort,
        fabric: IFabricGatewayPort,
        planner: IPlannerPort,
        state: IStateReadPort,
        delta: IDeltaEmitPort,
        bridge: IBridgeWritePort,
        event: IEventSubscriptionPort,
        storage: IWorkflowStoragePort,
        hil_port: Optional[IHILPort] = None,
    ) -> OrchestratorService:
        """Create an OrchestratorService with explicitly provided adapters.

        Every port must be supplied.  No defaults, no test fallbacks.
        This is for cross-subsystem integration tests mixing real and
        test adapters with full control.

        Args:
            config: Optional OrchestratorConfig (defaults to default()).
            mailbox: IMailboxPort implementation.
            fabric: IFabricGatewayPort implementation.
            planner: IPlannerPort implementation.
            state: IStateReadPort implementation.
            delta: IDeltaEmitPort implementation.
            bridge: IBridgeWritePort implementation.
            event: IEventSubscriptionPort implementation.
            storage: IWorkflowStoragePort implementation.

        Returns:
            OrchestratorService wired with provided adapters.
            Caller must call init() manually if needed.
        """
        effective_config = config or OrchestratorConfig.from_dict({"admin_enabled": False})
        adapters: Dict[str, Any] = {
            _PORT_MAILBOX: mailbox,
            _PORT_FABRIC: fabric,
            _PORT_PLANNER: planner,
            _PORT_STATE: state,
            _PORT_DELTA: delta,
            _PORT_BRIDGE: bridge,
            _PORT_EVENT: event,
            _PORT_STORAGE: storage,
        }
        return OrchestratorFactory._construct_orchestrator(effective_config, adapters, hil_port)

    # ==================================================================
    # Public: create_production(config) -- full prod stack
    # ==================================================================

    @staticmethod
    async def create_production(
        config: OrchestratorConfig,
        *,
        mailbox: IMailboxPort,
        fabric: IFabricGatewayPort,
        planner: IPlannerPort,
        state: IStateReadPort,
        delta: IDeltaEmitPort,
        bridge: IBridgeWritePort,
        event: IEventSubscriptionPort,
        storage: IWorkflowStoragePort,
        hil_port: Optional[IHILPort] = None,
    ) -> OrchestratorService:
        """Create a fully initialized production OrchestratorService.

        All adapters must be provided (production adapters are created
        by the caller or by a higher-level bootstrap function that has
        access to external dependencies like Fabric, Planner mailbox,
        bridge client, etc.).

        This is the ONLY factory method that calls init().
        The returned service is ready to accept messages.

        Args:
            config: Validated OrchestratorConfig for production.
            mailbox: Production IMailboxPort (e.g. MailboxAdapter).
            fabric: Production IFabricGatewayPort (e.g. FabricGatewayAdapter).
            planner: Production IPlannerPort (e.g. PlannerAdapter).
            state: Production IStateReadPort (e.g. StateReadAdapter).
            delta: Production IDeltaEmitPort (e.g. DeltaEmitAdapter).
            bridge: Production IBridgeWritePort (e.g. BridgeWriteAdapter).
            event: Production IEventSubscriptionPort (e.g. EventSubscriptionAdapter).
            storage: Production IWorkflowStoragePort (e.g. WorkflowStorageAdapter).

        Returns:
            Fully initialized OrchestratorService, ready for traffic.
        """
        adapters: Dict[str, Any] = {
            _PORT_MAILBOX: mailbox,
            _PORT_FABRIC: fabric,
            _PORT_PLANNER: planner,
            _PORT_STATE: state,
            _PORT_DELTA: delta,
            _PORT_BRIDGE: bridge,
            _PORT_EVENT: event,
            _PORT_STORAGE: storage,
        }
        service = OrchestratorFactory._construct_orchestrator(config, adapters, hil_port)

        # Production is the ONLY path that calls init().
        # Test methods leave init() to the caller for lifecycle control.
        await service.init()

        logger.info(
            "OrchestratorFactory.create_production: service initialized " "(config=%s)",
            type(config).__name__,
        )

        return service


# ---------------------------------------------------------------------------
# _NullHILAdapter -- defensive fallback when caller does not supply hil_port.
# Mirrors k1.planner.factory._NullHILAdapter (E5). Returns timed_out responses
# so production paths remain importable without requiring kernel-owned
# HumanInTheLoopService until E7 wires it through KernelService.
# ---------------------------------------------------------------------------


class _NullHILAdapter:
    """In-process IHILPort that always times out. See OrchestratorFactory."""

    __slots__ = ()

    async def ask_clarification(self, req: Any) -> Any:
        from k1.hil.types import ClarificationResponse

        return ClarificationResponse(
            hil_request_id="",
            answer=None,
            timed_out=True,
            round_budget_exhausted=False,
        )

    async def request_approval(self, req: Any) -> Any:
        from k1.hil.types import ApprovalResponse

        return ApprovalResponse(
            hil_request_id="",
            decision="reject",
            modifications=None,
            timed_out=True,
        )

    async def needs_human(self, req: Any) -> Any:
        from k1.hil.types import NeedsHumanResponse

        return NeedsHumanResponse(
            hil_request_id="",
            decision="timeout",
            resolution={},
            raw_user_text=None,
            timed_out=True,
        )

    async def request_override(self, req: Any) -> Any:
        from k1.hil.types import OverrideResponse

        return OverrideResponse(
            hil_request_id="",
            choice="abort",
            selected_alternative=None,
            fallback_action=None,
            timed_out=True,
        )

    async def gate_capability(self, req: Any) -> Any:
        from k1.hil.types import GateDecision, GateOutcome

        return GateDecision(
            outcome=GateOutcome.ALLOW,
            hil_request_id=None,
            reason="null_hil_default_allow",
            user_approved=None,
            audit_only=False,
        )

    def reset_round_budget(self, caller_key: str) -> None:
        return None

    async def shutdown(self) -> None:
        return None


__all__ = ["OrchestratorFactory"]
