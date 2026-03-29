"""
k1.orchestrator.orchestration.orchestrator_service -- Central Dispatch.

The OrchestratorService is the single entry point for all message
processing in the Orchestrator actor. It dequeues messages from the
mailbox, routes by type/tier, and coordinates the plan-request /
plan-receive two-phase protocol for HIGH tier tasks.

Design principles:
  - Pure deterministic actor: NO LLM, NO tools, NEVER writes SessionState.
  - Single-mailbox architecture (ORCH-001): one inbound channel.
  - Hexagonal: depends only on port Protocols, never on adapters.
  - ProcessingContext threaded through every call for structured tracing.
  - All adapter errors caught and routed via ErrorRouter; uncaught
    exceptions are TERMINAL.

Issues: 2.1.1 (OrchestratorService), 2.1.2 (route_task dispatch error handling),
  2.1.3 (dispatch_medium per-step isolation), 2.1.4 (dispatch_high two-phase),
  2.1.5 (aggregate pure function), 2.1.6 (save_workflow handler)
Reference:
  - docs/whiteboard/schema_whiteboard.md Section 1 (ProcessingContext lifecycle)
  - docs/whiteboard/schema_whiteboard.md Section 10 (Planner protocol)
  - k1/orchestrator/orchestrator.mmd (ORCH_CORE)

Exports:
  OrchestratorService
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Protocol, cast, runtime_checkable
from uuid import uuid4

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.connectors.mcp_registrar import RegistrationResult
from k1.orchestrator.events import (
    HIL_FALLBACK_RESPONSE,
    HIL_OVERRIDE_RESPONSE,
    ORCH_DAG_COMPLETED,
    ORCH_DELTA_V1,
    ORCH_PLAN_REQUESTED,
    ORCH_TASK_ACCEPTED,
    ORCH_WORKFLOW_SAVED,
    PLAN_CANCELLED,
    PLAN_FAILED,
    PLAN_READY,
)
from k1.orchestrator.metrics import OrchestratorMetrics
from k1.orchestrator.ports.bridge_write_port import IBridgeWritePort
from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
from k1.orchestrator.ports.event_subscription_port import IEventSubscriptionPort
from k1.orchestrator.ports.fabric_gateway_port import IFabricGatewayPort
from k1.orchestrator.ports.mailbox_port import IMailboxPort, MailboxMessage
from k1.orchestrator.ports.planner_port import IPlannerPort
from k1.orchestrator.ports.state_read_port import IStateReadPort
from k1.orchestrator.tracing import trace_phase
from k1.orchestrator.types import (
    AdapterError,
    AggregatedResult,
    CommittedPlan,
    CompensationRecord,
    ErrorSeverity,
    InterruptRequest,
    PendingHILContext,
    PendingPlanContext,
    PlanRequest,
    ProcessingContext,
    ProcessResult,
    RecoveryResult,
    StepResult,
    StepStatus,
    TaskEnvelope,
    WorkflowRunRequest,
    WorkflowSaveRequest,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentinel / placeholder protocols for collaborators not yet implemented.
# These will be replaced with real imports as M2 progresses (2.2, 2.3, 3.x).
# Using Protocol stubs keeps OrchestratorService testable in isolation.
# ---------------------------------------------------------------------------


@runtime_checkable
class DAGExecutorLike(Protocol):
    """Placeholder protocol for DAGExecutor (2.2.x)."""

    async def execute(
        self,
        plan: CommittedPlan,
        ctx: ProcessingContext,
    ) -> AggregatedResult: ...


@runtime_checkable
class ConstraintResolverLike(Protocol):
    """Placeholder protocol for ConstraintResolver (3.1.x)."""

    async def validate(
        self,
        plan: CommittedPlan,
        ctx: ProcessingContext,
    ) -> "ValidationResultLike": ...


@runtime_checkable
class ValidationResultLike(Protocol):
    """Minimal shape of ValidationResult for validate() return."""

    @property
    def valid(self) -> bool: ...

    @property
    def issues(self) -> List[str]: ...


@runtime_checkable
class WorkflowEngineLike(Protocol):
    """Placeholder protocol for WorkflowEngine (4.x)."""

    async def execute_workflow(
        self,
        request: WorkflowRunRequest,
        ctx: ProcessingContext,
    ) -> ProcessResult: ...

    async def save_workflow(
        self,
        request: WorkflowSaveRequest,
        ctx: ProcessingContext,
    ) -> ProcessResult: ...


@runtime_checkable
class ConnectorLifecycleLike(Protocol):
    """Protocol for ConnectorLifecycleManager (5.x)."""

    async def discover_and_register(self) -> RegistrationResult: ...

    def start_lifecycle_monitoring(self) -> None: ...

    def stop_lifecycle_monitoring(self) -> None: ...


@runtime_checkable
class ErrorRouterLike(Protocol):
    """Protocol for ErrorRouter (2.1.7).

    classify() -- sync severity-only interface used by OrchestratorService
    route_error() -- async full interface returning ErrorAction with delta emission
    """

    def classify(self, error: "AdapterException", ctx: ProcessingContext) -> ErrorSeverity: ...


@runtime_checkable
class ConcurrencyGuardLike(Protocol):
    """Protocol for ConcurrencyGuard (3.2.x).

    acquire() is async (asyncio.Lock). release() is sync.
    Both accept ProcessingContext for tracing (may be ignored).
    """

    async def acquire(self, ctx: ProcessingContext) -> bool: ...

    def release(self, ctx: ProcessingContext) -> None: ...


class AdapterException(Exception):
    """Raiseable exception wrapping the AdapterError data-class.

    AdapterError is a frozen dataclass (k1.orchestrator.types) carrying
    structured error metadata.  Python ``except`` clauses require an
    Exception subclass, so port adapters MUST raise AdapterException and
    attach the AdapterError as ``self.detail``.

    Usage in adapter code::

        raise AdapterException(AdapterError(
            severity=ErrorSeverity.DEGRADED,
            adapter_name="fabric",
            operation="execute",
            error_code="TIMEOUT",
            error_message="Capability timed out",
        ))

    Consumers access structured fields via the delegated properties
    (adapter_name, operation, error_code, error_message, severity,
    trace_id) so call-sites remain clean.
    """

    __slots__ = (
        "detail",
        "adapter_name",
        "operation",
        "error_code",
        "error_message",
        "severity",
        "trace_id",
    )

    def __init__(self, detail: AdapterError) -> None:
        self.detail = detail
        self.adapter_name = detail.adapter_name
        self.operation = detail.operation
        self.error_code = detail.error_code
        self.error_message = detail.error_message
        self.severity = detail.severity
        self.trace_id = detail.trace_id
        super().__init__(detail.error_message)


# Maximum entries in executed_plans LRU dedup set (bounded to prevent unbounded growth).
_EXECUTED_PLANS_MAX: int = 100


class OrchestratorService:
    """Central dispatch for the Orchestrator actor.

    Dequeues messages from the mailbox, routes by type (isinstance
    dispatch), and coordinates MEDIUM / HIGH tier processing.

    HIGH tier uses a two-phase protocol:
      Phase 1 -- dispatch_high(): PlanRequest -> Planner (fire-and-forget).
      Phase 2 -- receive_plan(): CommittedPlan arrives via event bus.

    Internal state:
      pending_plans   -- Dict[request_id, PendingPlanContext] for in-flight
                         HIGH tier requests awaiting Planner response.
      pending_hil     -- Dict[request_id, PendingHILContext] for in-flight
                         HIL questions awaiting user response.
      executed_plans  -- OrderedDict[plan_id, float] bounded LRU set for
                         RACE-3 deduplication (max 100 entries).

    Thread safety:
      All public methods are async. The service is designed for single-
      threaded asyncio execution (one mailbox loop), but port calls may
      be concurrent within a wave (DAGExecutor).

    Invariants enforced:
      ORCH-01  -- never writes SessionState (no write port exists).
      ORCH-02  -- never calls LLM (no LLM port exists).
      ORCH-03  -- zero tools (all execution via Fabric port).
      ORCH-09  -- trace_id on every emitted event.
      ORCH-11  -- HIGH tier requires CommittedPlan from Planner.
    """

    __slots__ = (
        "_dag_executor",
        "_constraint_resolver",
        "_workflow_engine",
        "_connector_lifecycle",
        "_error_router",
        "_concurrency_guard",
        "_fabric_port",
        "_planner_port",
        "_state_port",
        "_delta_port",
        "_bridge_port",
        "_event_port",
        "_mailbox",
        "_config",
        "_pending_plans",
        "_pending_hil",
        "_executed_plans",
        "_requeued_envelope_ids",
        "_started_at",
        "_initialized",
        "_running",
        "_loop_task",
        "_reaper_task",
        "_subscriptions",
        "_admin",
        "_metrics",
    )

    def __init__(
        self,
        *,
        mailbox: IMailboxPort,
        dag_executor: DAGExecutorLike,
        constraint_resolver: ConstraintResolverLike,
        workflow_engine: WorkflowEngineLike,
        connector_lifecycle: ConnectorLifecycleLike,
        error_router: ErrorRouterLike,
        concurrency_guard: ConcurrencyGuardLike,
        fabric_port: IFabricGatewayPort,
        planner_port: IPlannerPort,
        state_port: IStateReadPort,
        delta_port: IDeltaEmitPort,
        bridge_port: IBridgeWritePort,
        event_port: IEventSubscriptionPort,
        config: OrchestratorConfig,
        metrics: Optional[OrchestratorMetrics] = None,
    ) -> None:
        # --- Collaborators (injected, never constructed here) ---
        self._mailbox = mailbox
        self._dag_executor = dag_executor
        self._constraint_resolver = constraint_resolver
        self._workflow_engine = workflow_engine
        self._connector_lifecycle = connector_lifecycle
        self._error_router = error_router
        self._concurrency_guard = concurrency_guard

        # --- Port references ---
        self._fabric_port = fabric_port
        self._planner_port = planner_port
        self._state_port = state_port
        self._delta_port = delta_port
        self._bridge_port = bridge_port
        self._event_port = event_port
        self._metrics = metrics or OrchestratorMetrics(enabled=config.metrics_enabled)

        # --- Configuration ---
        self._config = config

        # --- Internal mutable state ---
        self._pending_plans: Dict[str, PendingPlanContext] = {}
        self._pending_hil: Dict[str, PendingHILContext] = {}
        self._executed_plans: OrderedDict[str, float] = OrderedDict()
        self._requeued_envelope_ids: OrderedDict[str, float] = OrderedDict()
        self._started_at: float = time.time()

        # --- Lifecycle state (set by init()) ---
        self._initialized: bool = False
        self._running: bool = False
        self._loop_task: Optional[asyncio.Task[None]] = None
        self._reaper_task: Optional[asyncio.Task[None]] = None
        self._subscriptions: List[SubscriptionHandle] = []
        self._admin: Optional[Any] = None

    # ======================================================================
    # Properties (read-only accessors for internal state -- used by tests
    # and admin API)
    # ======================================================================

    @property
    def pending_plans(self) -> Dict[str, PendingPlanContext]:
        """Active plan requests awaiting Planner response."""
        return self._pending_plans

    @property
    def pending_hil(self) -> Dict[str, PendingHILContext]:
        """Active HIL questions awaiting user response."""
        return self._pending_hil

    @property
    def executed_plans(self) -> OrderedDict[str, float]:
        """Recently executed plan IDs for dedup (bounded LRU)."""
        return self._executed_plans

    @property
    def requeued_envelope_ids(self) -> OrderedDict[str, float]:
        """Envelope IDs re-enqueued via once guard (bounded LRU)."""
        return self._requeued_envelope_ids

    @property
    def config(self) -> OrchestratorConfig:
        """Orchestrator configuration (immutable after init)."""
        return self._config

    @property
    def initialized(self) -> bool:
        """Whether init() has completed successfully."""
        return self._initialized

    @property
    def running(self) -> bool:
        """Whether the mailbox loop and reaper are active."""
        return self._running

    # ======================================================================
    # Lifecycle: init() -- 10-step startup sequence (6.2.2)
    # ======================================================================

    async def init(self) -> None:
        """Initialize the OrchestratorService (10-step startup sequence).

        Idempotent: calling twice is safe (second call is a no-op).

        Steps:
          1. Validate all ports and collaborators non-None.
          2. (Reserved) Connect ports -- no-op for V1 in-process adapters.
          3. Assert concurrency guard not locked at boot.
          4. MCP tool discovery and registration (500ms timeout).
          5. (Commentary) Tools now available for DAG execution.
          6. Load active workflows from WorkflowRegistry.
          7. Start WorkflowScheduler tick loop.
          8. Subscribe to consumed events (5 subscriptions).
          9. Start GapDetector, ConnectorLifecycle monitoring, reaper task.
         10. Start mailbox processing loop.

        Raises:
            RuntimeError: If any required port/collaborator is None.
            AssertionError: If ConcurrencyGuard is active at init time.
        """
        if self._initialized:
            log.warning("init.already_initialized")
            return

        t0 = time.monotonic()

        # Step 1: Validate ports non-None
        self._validate_ports()

        # Step 2: Connect ports (no-op for V1 in-process adapters)
        # Reserved for future: event bus connection setup, adapter handshake.

        # Step 2b: Crash recovery (6.2.4) -- scan WAL, re-enqueue incomplete DAGs.
        # Must run BEFORE mailbox loop starts (Gotcha #3 in spec).
        recovery = await self.crash_recovery()
        log.info(
            "init.crash_recovery",
            extra={
                "recovered": recovery.recovered_dags,
                "failed": recovery.failed_recoveries,
                "skipped": recovery.skipped,
            },
        )

        # Step 3: Assert concurrency guard not locked
        assert not getattr(
            self._concurrency_guard, "active", False
        ), "ConcurrencyGuard must not be active at init time"

        # Step 4: MCP discover + register (500ms timeout)
        registration = await self._discover_mcp_tools()
        self._metrics.set_mcp_registered_capabilities(registration.registered)
        log.info(
            "init.mcp_discovery",
            extra={
                "registered": registration.registered,
                "skipped": registration.skipped,
                "errors": len(registration.errors),
            },
        )

        # Step 5: (Commentary) Tools now available for DAG execution.

        # Step 6: Load active workflows
        workflows = await self._workflow_engine.registry.list_active()  # type: ignore[union-attr]
        self._metrics.set_workflow_active_count(len(workflows))
        self._metrics.set_pending_plans(len(self._pending_plans))
        self._metrics.set_pending_hil(len(self._pending_hil))
        log.info("init.workflows_loaded", extra={"count": len(workflows)})

        # Step 7: Start scheduler
        await self._workflow_engine.scheduler.start()  # type: ignore[union-attr]

        # Step 8: Subscribe to consumed events
        self._subscribe_events()

        # Step 9a: Start gap detector (manages own contract_updated subscription)
        await self._workflow_engine.gap_detector.start()  # type: ignore[union-attr]

        # Step 9b: Start connector lifecycle monitoring (sync call)
        self._connector_lifecycle.start_lifecycle_monitoring()  # type: ignore[union-attr]

        # Step 9c: Start timeout reaper task
        self._running = True
        self._reaper_task = asyncio.create_task(self._reap_loop())

        # Step 10: Start mailbox processing loop
        self._loop_task = asyncio.create_task(self._mailbox_loop())

        # Step 10.5: Start admin HTTP server (if configured and adapter injected).
        if self._admin is not None and self._config.admin_enabled:
            try:
                await self._admin.start(self._config.admin_port)
                log.info(
                    "init.step10_5.admin_started",
                    extra={"port": self._config.admin_port},
                )
            except Exception:
                log.exception("init.step10_5.admin_start_error")

        self._initialized = True

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "init.complete",
            extra={"elapsed_ms": elapsed_ms, "subscriptions": len(self._subscriptions)},
        )

    # ------------------------------------------------------------------
    # init() helpers
    # ------------------------------------------------------------------

    def _validate_ports(self) -> None:
        """Step 1: Validate all injected ports and collaborators are non-None.

        Raises:
            RuntimeError: If any required dependency is None.
        """
        required: Dict[str, Any] = {
            "mailbox": self._mailbox,
            "dag_executor": self._dag_executor,
            "constraint_resolver": self._constraint_resolver,
            "workflow_engine": self._workflow_engine,
            "connector_lifecycle": self._connector_lifecycle,
            "error_router": self._error_router,
            "concurrency_guard": self._concurrency_guard,
            "fabric_port": self._fabric_port,
            "planner_port": self._planner_port,
            "state_port": self._state_port,
            "delta_port": self._delta_port,
            "bridge_port": self._bridge_port,
            "event_port": self._event_port,
        }

        missing = [name for name, ref in required.items() if ref is None]
        if missing:
            raise RuntimeError(f"OrchestratorService.init(): missing required ports: {missing}")

        log.info(
            "init.ports_validated",
            extra={name: type(ref).__name__ for name, ref in required.items()},
        )

    async def _discover_mcp_tools(self) -> RegistrationResult:
        """Step 4: MCP discovery with 500ms timeout (SPEC-10).

        Returns:
            RegistrationResult -- empty result on timeout.
        """
        try:
            return await asyncio.wait_for(
                self._connector_lifecycle.discover_and_register(),  # type: ignore[union-attr]
                timeout=0.5,
            )
        except asyncio.TimeoutError:
            log.warning("init.mcp_discovery_timeout", extra={"timeout_ms": 500})
            return RegistrationResult()

    def _subscribe_events(self) -> None:
        """Step 8: Register event subscriptions for consumed events.

        Subscribes to 5 event topics and stores handles for shutdown
        unsubscription (6.2.3). GapDetector and SubStepObserver manage
        their own subscriptions externally.

        All handlers are SYNC per IEventSubscriptionPort contract.
        """
        subscriptions: List[SubscriptionHandle] = []

        topic_handler_pairs: List[tuple[str, Callable[[str, Dict[str, Any]], None]]] = [
            (PLAN_READY, self._on_plan_ready),
            (PLAN_FAILED, self._on_plan_failed),
            (PLAN_CANCELLED, self._on_plan_cancelled),
            (HIL_OVERRIDE_RESPONSE, self._on_hil_override),
            (HIL_FALLBACK_RESPONSE, self._on_hil_fallback),
        ]

        for topic, handler in topic_handler_pairs:
            handle = self._event_port.subscribe(topic, handler)
            subscriptions.append(handle)
            log.debug(
                "init.subscribed", extra={"topic": topic, "handle_id": handle.subscription_id}
            )

        self._subscriptions = subscriptions

    # ------------------------------------------------------------------
    # crash_recovery() -- WAL-based recovery (6.2.4)
    # ------------------------------------------------------------------

    async def crash_recovery(self) -> RecoveryResult:
        """Scan WAL entries and recover in-flight DAGs after restart.

        Called by init() between steps 2 and 3, BEFORE the mailbox loop
        starts. This prevents race conditions with new incoming messages.

        Logic per WAL entry:
          - DAG_COMPLETE found: DAG finished before crash, skip it.
          - PLAN_START only: DAG never began wave execution.
            Reconstruct CommittedPlan from payload, enqueue to mailbox
            so normal processing pipeline re-executes from wave 0.
          - WAVE_COMPLETE(N): Partial execution. V1 limitation --
            DAGExecutor lacks resume_from_wave, so re-enqueue the full
            plan for re-execution from wave 0 (double-execution of
            completed steps accepted as V1 tradeoff).

        Gotchas:
          1. K0 offline (list_wal_ids/read_wal raises AdapterException
             with DEGRADED severity): skip recovery entirely, return
             zero-result. Documented V1 limitation.
          2. Recovered DAGs use fresh state_port.snapshot() at execution
             time (stale context from crash time is lost).
          3. Must be called BEFORE mailbox loop starts.

        Returns:
            RecoveryResult with counts of recovered, failed, skipped.
        """
        result = RecoveryResult()

        # Step 1: List WAL IDs. K0 offline -> skip entirely.
        try:
            wal_ids = await self._bridge_port.list_wal_ids()  # type: ignore[union-attr]
        except Exception as exc:
            # Gotcha #1: K0 unavailable.
            severity = getattr(getattr(exc, "detail", None), "severity", None)
            if severity == ErrorSeverity.DEGRADED:
                log.warning(
                    "crash_recovery.k0_unavailable",
                    extra={"note": "K0 offline, skipping crash recovery"},
                )
            else:
                log.exception("crash_recovery.list_wal_ids_failed")
            return result

        if not wal_ids:
            log.info("crash_recovery.no_pending_wals")
            return result

        log.info("crash_recovery.scanning", extra={"wal_count": len(wal_ids)})

        # Step 2-7: Process each WAL entry.
        for dag_id in wal_ids:
            try:
                entries = await self._bridge_port.read_wal(dag_id)  # type: ignore[union-attr]
                if not entries:
                    result.skipped += 1
                    continue

                # Classify the WAL state.
                has_dag_complete = any(e.get("entry_type") == "DAG_COMPLETE" for e in entries)
                if has_dag_complete:
                    # Step 4: DAG already finished. Skip.
                    result.skipped += 1
                    log.info(
                        "crash_recovery.dag_already_complete",
                        extra={"dag_id": dag_id},
                    )
                    continue

                # Find PLAN_START entry to reconstruct CommittedPlan.
                plan_start_entry = None
                highest_wave = -1
                for entry in entries:
                    etype = entry.get("entry_type", "")
                    if etype == "PLAN_START":
                        plan_start_entry = entry
                    elif etype == "WAVE_COMPLETE":
                        wave_idx = entry.get("payload", {}).get("wave_index", -1)
                        if wave_idx > highest_wave:
                            highest_wave = wave_idx

                if plan_start_entry is None:
                    # No PLAN_START -- corrupt WAL, cannot recover.
                    log.warning(
                        "crash_recovery.no_plan_start",
                        extra={"dag_id": dag_id, "entry_count": len(entries)},
                    )
                    result.failed_recoveries += 1
                    continue

                # Reconstruct CommittedPlan from PLAN_START payload.
                plan_payload = plan_start_entry.get("payload", {})
                plan_dict = plan_payload.get("plan", plan_payload)

                plan = CommittedPlan.from_dict(plan_dict)

                # Enqueue the recovered plan into the mailbox.
                # The normal mailbox loop will pick it up and route
                # through receive_plan() -> DAGExecutor.execute().
                self._mailbox.enqueue(plan, priority="INTERACTIVE")

                if highest_wave >= 0:
                    # Step 6: WAVE_COMPLETE(N) -- partial execution.
                    # V1: re-execute from wave 0 (no resume support).
                    log.info(
                        "crash_recovery.partial_dag_recovered",
                        extra={
                            "dag_id": dag_id,
                            "plan_id": plan.plan_id,
                            "highest_wave": highest_wave,
                            "note": "V1: re-executing from wave 0",
                        },
                    )
                else:
                    # Step 5: PLAN_START only -- never started.
                    log.info(
                        "crash_recovery.unstarted_dag_recovered",
                        extra={
                            "dag_id": dag_id,
                            "plan_id": plan.plan_id,
                        },
                    )

                result.recovered_dags += 1

            except Exception:
                # Step 8: Recovery error for this dag_id.
                log.exception(
                    "crash_recovery.dag_recovery_failed",
                    extra={"dag_id": dag_id},
                )
                result.failed_recoveries += 1

        log.info(
            "crash_recovery.complete",
            extra={
                "recovered": result.recovered_dags,
                "failed": result.failed_recoveries,
                "skipped": result.skipped,
            },
        )
        return result

    # ------------------------------------------------------------------
    # Event handlers (SYNC -- per IEventSubscriptionPort contract)
    # ------------------------------------------------------------------

    def _on_plan_ready(self, topic: str, payload: Dict[str, Any]) -> None:
        """Handle PLAN_READY: deserialize CommittedPlan and enqueue to mailbox.

        The CommittedPlan is enqueued at INTERACTIVE priority for the
        mailbox loop to pick up and route to _receive_plan().
        """
        try:
            plan = CommittedPlan(
                plan_id=payload.get("plan_id", str(uuid4())),
                request_id=payload.get("request_id", ""),
                intent=payload.get("intent", ""),
                steps=payload.get("steps", []),
                trace_id=payload.get("trace_id", ""),
                dependencies=payload.get("dependencies", {}),
            )
            self._mailbox.enqueue(plan, priority="INTERACTIVE")
            log.info(
                "on_plan_ready.enqueued",
                extra={
                    "plan_id": plan.plan_id,
                    "request_id": plan.request_id,
                    "step_count": len(plan.steps),
                },
            )
        except Exception:
            log.exception("on_plan_ready.failed")

    def _on_plan_failed(self, topic: str, payload: Dict[str, Any]) -> None:
        """Handle PLAN_FAILED: clean up pending plan context.

        Payload is a raw dict (not a typed dataclass). Extracts
        request_id and removes the PendingPlanContext.
        """
        request_id = payload.get("request_id", "")
        pending = self._pending_plans.pop(request_id, None)
        self._metrics.set_pending_plans(len(self._pending_plans))
        if pending is None:
            log.warning(
                "on_plan_failed.no_pending_context",
                extra={"request_id": request_id},
            )
            return
        log.warning(
            "on_plan_failed.cleaned",
            extra={
                "request_id": request_id,
                "reason": payload.get("reason", "unknown"),
            },
        )

    def _on_plan_cancelled(self, topic: str, payload: Dict[str, Any]) -> None:
        """Handle PLAN_CANCELLED: clean up pending plan context.

        Same pattern as _on_plan_failed but for cancellation events.
        """
        request_id = payload.get("request_id", "")
        pending = self._pending_plans.pop(request_id, None)
        self._metrics.set_pending_plans(len(self._pending_plans))
        if pending is None:
            log.warning(
                "on_plan_cancelled.no_pending_context",
                extra={"request_id": request_id},
            )
            return
        log.info(
            "on_plan_cancelled.cleaned",
            extra={"request_id": request_id},
        )

    def _on_hil_override(self, topic: str, payload: Dict[str, Any]) -> None:
        """Handle HIL_OVERRIDE_RESPONSE: resolve pending HIL context.

        Extracts request_id and user choice from payload. Full DAG
        resumption is deferred to the DAG execution pipeline; this
        handler records the resolution and cleans up the pending state.
        """
        request_id = payload.get("request_id", "")
        choice = payload.get("choice", "CONTINUE")
        pending = self._pending_hil.pop(request_id, None)
        self._metrics.set_pending_hil(len(self._pending_hil))
        if pending is None:
            log.warning(
                "on_hil_override.no_pending_context",
                extra={"request_id": request_id},
            )
            return
        log.info(
            "on_hil_override.resolved",
            extra={"request_id": request_id, "choice": choice},
        )
        self._metrics.increment_hil_request(outcome="responded")

    def _on_hil_fallback(self, topic: str, payload: Dict[str, Any]) -> None:
        """Handle HIL_FALLBACK_RESPONSE: resolve pending HIL context with fallback.

        Same as override but the user chose a fallback action instead
        of the primary choice.
        """
        request_id = payload.get("request_id", "")
        fallback_action = payload.get("fallback_action", "CANCEL")
        pending = self._pending_hil.pop(request_id, None)
        self._metrics.set_pending_hil(len(self._pending_hil))
        if pending is None:
            log.warning(
                "on_hil_fallback.no_pending_context",
                extra={"request_id": request_id},
            )
            return
        log.info(
            "on_hil_fallback.resolved",
            extra={"request_id": request_id, "fallback_action": fallback_action},
        )
        self._metrics.increment_hil_request(outcome="responded")

    # ======================================================================
    # Lifecycle: shutdown() -- 9-step teardown sequence (6.2.3)
    # ======================================================================

    async def shutdown(self) -> None:
        """Gracefully shut down the OrchestratorService (9-step sequence).

        Idempotent: calling twice is safe (second call is a no-op).
        Each step is wrapped in try/except so a failure in one step
        does not prevent later steps from executing (Gotcha #1:
        handles partial init -- some ports may not have been started).

        Steps:
          1. Set _running = False to stop mailbox + reaper loops.
          2. Stop connector lifecycle monitoring (sync).
          3. Wait for active DAG completion (30s timeout).
          4. (Reserved) Force-compensate if DAG timed out -- V1 logs warning.
          5. Stop WorkflowScheduler tick loop.
          6. Unsubscribe all event subscriptions.
          7. (Reserved) Persist trigger states -- deferred, scheduler lacks
             get_next_fire/get_last_fire in V1.
          8. Final audit write via bridge_port.submit_audit().
          9. Cancel background tasks (reaper + loop), log orphaned contexts.
        """
        if not self._initialized:
            log.warning("shutdown.not_initialized")
            return

        t0 = time.monotonic()
        trace_id = f"shutdown-{uuid4()}"

        log.info("shutdown.begin", extra={"trace_id": trace_id})

        # Step 1: Signal loops to stop.
        self._running = False

        # Step 2: Stop connector lifecycle monitoring (sync call).
        try:
            self._connector_lifecycle.stop_lifecycle_monitoring()  # type: ignore[union-attr]
            log.info("shutdown.step2.connector_lifecycle_stopped")
        except Exception:
            log.exception("shutdown.step2.connector_lifecycle_error")

        # Step 3: Wait for active DAG completion (30s timeout).
        dag_timed_out = False
        try:
            if getattr(self._concurrency_guard, "active", False):
                log.info("shutdown.step3.waiting_for_active_dag")
                # V1: no _dag_complete_event wiring. Poll concurrency
                # guard with short sleeps up to 30s.
                deadline = time.monotonic() + 30.0
                while getattr(self._concurrency_guard, "active", False):
                    if time.monotonic() >= deadline:
                        dag_timed_out = True
                        break
                    await asyncio.sleep(0.1)

                if dag_timed_out:
                    log.warning(
                        "shutdown.step3.dag_timeout",
                        extra={"timeout_s": 30},
                    )
                else:
                    log.info("shutdown.step3.dag_completed")
            else:
                log.info("shutdown.step3.no_active_dag")
        except Exception:
            log.exception("shutdown.step3.dag_wait_error")

        # Step 4: Force-compensate if DAG timed out.
        #   V1: Saga.compensate() not yet wired (2.2.5 deferred).
        #   Log warning and continue -- DAG results may be incomplete.
        if dag_timed_out:
            try:
                log.warning(
                    "shutdown.step4.force_compensate_deferred",
                    extra={
                        "note": "Saga.compensate() not wired in V1; "
                        "DAG may have incomplete results",
                    },
                )
            except Exception:
                log.exception("shutdown.step4.compensate_error")

        # Step 5: Stop WorkflowScheduler.
        try:
            await self._workflow_engine.scheduler.stop()  # type: ignore[union-attr]
            log.info("shutdown.step5.scheduler_stopped")
        except Exception:
            log.exception("shutdown.step5.scheduler_error")

        # Step 6: Stop GapDetector and unsubscribe all event subscriptions.
        try:
            await self._workflow_engine.gap_detector.stop()  # type: ignore[union-attr]
            log.info("shutdown.step6.gap_detector_stopped")
        except Exception:
            log.exception("shutdown.step6.gap_detector_error")

        try:
            for handle in self._subscriptions:
                self._event_port.unsubscribe(handle)
            unsubscribed_count = len(self._subscriptions)
            self._subscriptions.clear()
            log.info(
                "shutdown.step6.events_unsubscribed",
                extra={"count": unsubscribed_count},
            )
        except Exception:
            log.exception("shutdown.step6.unsubscribe_error")

        # Step 7: Persist trigger states.
        #   V1: WorkflowScheduler does not expose get_next_fire() /
        #   get_last_fire().  Trigger persistence deferred until
        #   scheduler gains these accessors.
        try:
            log.info(
                "shutdown.step7.trigger_persistence_deferred",
                extra={
                    "note": "Scheduler lacks get_next_fire/get_last_fire in V1",
                },
            )
        except Exception:
            log.exception("shutdown.step7.trigger_error")

        # Step 8: Final audit write.
        try:
            orphan_plans = len(self._pending_plans)
            orphan_hil = len(self._pending_hil)

            # Gotcha #3: warn about orphaned contexts.
            if orphan_plans > 0 or orphan_hil > 0:
                log.warning(
                    "shutdown.step8.orphaned_contexts",
                    extra={
                        "pending_plans": orphan_plans,
                        "pending_hil": orphan_hil,
                    },
                )

            await self._bridge_port.submit_audit(  # type: ignore[union-attr]
                {
                    "event": "orchestrator_shutdown",
                    "pending_plans": orphan_plans,
                    "pending_hil": orphan_hil,
                    "trace_id": trace_id,
                },
                trace_id,
            )
            log.info("shutdown.step8.audit_written")
        except Exception:
            log.exception("shutdown.step8.audit_error")

        # Step 8.5: Stop admin HTTP server.
        if self._admin is not None:
            try:
                await self._admin.stop()
                log.info("shutdown.step8_5.admin_stopped")
            except Exception:
                log.exception("shutdown.step8_5.admin_stop_error")

        # Step 9: Cancel background tasks and clear state.
        try:
            if self._reaper_task is not None:
                self._reaper_task.cancel()
                try:
                    await self._reaper_task
                except asyncio.CancelledError:
                    pass
                self._reaper_task = None

            if self._loop_task is not None:
                self._loop_task.cancel()
                try:
                    await self._loop_task
                except asyncio.CancelledError:
                    pass
                self._loop_task = None

            log.info("shutdown.step9.tasks_cancelled")
        except Exception:
            log.exception("shutdown.step9.task_cancel_error")

        self._initialized = False

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "shutdown.complete",
            extra={"elapsed_ms": elapsed_ms, "trace_id": trace_id},
        )

    # ------------------------------------------------------------------
    # Background loops (started by init())
    # ------------------------------------------------------------------

    async def _reap_loop(self) -> None:
        """Periodic reaper for stale pending contexts (Step 9c).

        Runs every config.context_reap_interval_ms milliseconds.
        Delegates to reap_stale_contexts() which is the one-shot
        reaper already implemented.
        """
        interval_s = self._config.context_reap_interval_ms / 1000.0
        while self._running:
            await asyncio.sleep(interval_s)
            try:
                reaped = await self.reap_stale_contexts()
                if reaped > 0:
                    log.info("reap_loop.reaped", extra={"count": reaped})
            except Exception:
                log.exception("reap_loop.error")

    async def _mailbox_loop(self) -> None:
        """Mailbox processing loop (Step 10).

        Polls the mailbox and routes each message through process().
        Yields 1ms when empty to prevent busy-wait.
        """
        while self._running:
            with self._metrics.time_dequeue():
                msg = self._mailbox.dequeue()
            trace_phase(
                log,
                "dequeue",
                trace_id=getattr(msg, "trace_id", "") if msg is not None else None,
                request_id=getattr(msg, "request_id", None) if msg is not None else None,
                success=msg is not None,
                level=logging.DEBUG,
            )
            try:
                self._metrics.set_mailbox_depth(self._mailbox.depth())
            except Exception:
                pass
            if msg is None:
                await asyncio.sleep(0.001)  # 1ms yield
                continue
            await self._process_one(msg)

    async def _process_one(self, msg: MailboxMessage) -> None:
        """Process a single mailbox message (6.2.5).

        Steps:
          1. Extract trace_id from message (all MailboxMessage types have trace_id).
          2. Log message type + trace_id.
          3. Concurrency check:
             - InterruptRequest: ALWAYS processed (bypass guard).
             - DAG-requiring messages (TaskEnvelope, CommittedPlan,
               WorkflowRunRequest): if ConcurrencyGuard.active,
               re-enqueue at BACKGROUND priority and return.
          4. Call self.process(msg).
          5. Log result status.
          6. If FAILED: emit error delta via delta_port.
             If DEFERRED: no action (plan in flight).
             If COMPLETED: no action (process() already emitted).

        Catch-all exception handling ensures the mailbox loop
        never crashes from an unhandled error.
        """
        # Step 1: Extract trace_id.
        trace_id = getattr(msg, "trace_id", "") or ""
        msg_type = type(msg).__name__

        # Step 2: Log inbound message.
        log.info(
            "mailbox_loop.dequeued",
            extra={"message_type": msg_type, "trace_id": trace_id},
        )

        try:
            with self._metrics.time_route(message_type=msg_type):
                trace_phase(
                    log,
                    "route",
                    trace_id=trace_id,
                    request_id=getattr(msg, "request_id", None),
                    tier=getattr(msg, "tier", None),
                    level=logging.DEBUG,
                )
                # Step 3: Concurrency guard check.
                if not isinstance(msg, InterruptRequest):
                    # DAG-requiring types: defer if guard active.
                    if isinstance(msg, (TaskEnvelope, CommittedPlan, WorkflowRunRequest)):
                        if getattr(self._concurrency_guard, "active", False):
                            self._mailbox.enqueue(msg, priority="BACKGROUND")
                            log.info(
                                "mailbox_loop.deferred",
                                extra={
                                    "message_type": msg_type,
                                    "trace_id": trace_id,
                                    "reason": "DAG active, re-enqueued at BACKGROUND",
                                },
                            )
                            return

                # Step 4: Dispatch to process().
                result = await self.process(msg)

                # Step 5: Log result.
                log.info(
                    "mailbox_loop.result",
                    extra={
                        "message_type": msg_type,
                        "trace_id": trace_id,
                        "result": result.value,
                    },
                )
                self._metrics.increment_mailbox_processed(message_type=msg_type)

                # Step 6: Emit error delta on FAILED.
                if result == ProcessResult.FAILED:
                    try:
                        await self._delta_port.emit(  # type: ignore[union-attr]
                            event_topic=ORCH_DELTA_V1,
                            payload={
                                "type": "processing_error",
                                "message_type": msg_type,
                                "trace_id": trace_id,
                                "result": result.value,
                            },
                            trace_id=trace_id,
                        )
                    except Exception:
                        # Fire-and-forget delta emission -- never block the loop.
                        log.warning(
                            "mailbox_loop.error_delta_failed",
                            extra={"trace_id": trace_id},
                        )

        except Exception:
            log.exception(
                "mailbox_loop.unhandled_exception",
                extra={"message_type": msg_type, "trace_id": trace_id},
            )

    # ======================================================================
    # Primary entry point
    # ======================================================================

    async def process(self, message: MailboxMessage) -> ProcessResult:
        """Route a dequeued mailbox message by type.

        This is the single dispatch point. The mailbox loop (6.2.5)
        calls this for every dequeued message. Routing is by
        ``isinstance`` dispatch -- no visitor pattern, no registry.

        Args:
            message: A dequeued MailboxMessage (union type).

        Returns:
            ProcessResult indicating outcome.

        Contract:
            - NEVER raises (all exceptions caught and classified).
            - Emits structured log at entry and exit.
            - Creates ProcessingContext for trace propagation.
        """
        ctx = self._build_context(message)

        log.info(
            "process.entry",
            extra={
                "trace_id": ctx.trace_id,
                "request_id": ctx.request_id,
                "tier": ctx.tier,
                "message_type": type(message).__name__,
            },
        )

        t0 = time.monotonic()
        result = ProcessResult.FAILED  # default pessimistic

        with self._metrics.time_total_overhead(
            message_type=type(message).__name__,
            tier=ctx.tier,
        ):
            try:
                if isinstance(message, TaskEnvelope):
                    result = await self._route_task(message, ctx)
                elif isinstance(message, CommittedPlan):
                    result = await self._receive_plan(message, ctx)
                elif isinstance(message, WorkflowRunRequest):
                    result = await self._dispatch_workflow(message, ctx)
                elif isinstance(message, WorkflowSaveRequest):
                    result = await self._save_workflow(message, ctx)
                elif isinstance(message, InterruptRequest):
                    result = await self._handle_interrupt(message, ctx)
                else:
                    log.warning(
                        "process.unknown_message_type",
                        extra={
                            "trace_id": ctx.trace_id,
                            "message_type": type(message).__name__,
                        },
                    )
                    result = ProcessResult.FAILED

            except AdapterException as exc:
                result = self._handle_adapter_error(exc, ctx)

            except Exception:
                log.exception(
                    "process.unhandled_exception",
                    extra={
                        "trace_id": ctx.trace_id,
                        "request_id": ctx.request_id,
                    },
                )
                result = ProcessResult.FAILED

            finally:
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                log.info(
                    "process.exit",
                    extra={
                        "trace_id": ctx.trace_id,
                        "request_id": ctx.request_id,
                        "result": result.value,
                        "elapsed_ms": elapsed_ms,
                        "message_type": type(message).__name__,
                    },
                )

        return result

    # ======================================================================
    # Task routing (MEDIUM / HIGH)
    # ======================================================================

    async def _route_task(
        self,
        envelope: TaskEnvelope,
        ctx: ProcessingContext,
    ) -> ProcessResult:
        """Route a TaskEnvelope by tier (Issue 2.1.2).

        Steps:
          1. Validate envelope (trace_id, intent, tier).
          2. Emit TASK_ACCEPTED event via delta_port.
          3. Dispatch to _dispatch_medium (MEDIUM) or _dispatch_high (HIGH).

        Error handling (per 2.1.2 contract):
          - Validation failure -> FAILED immediately (no dispatch).
          - AdapterException from dispatch -> classified via ErrorRouter:
              RECOVERABLE -> re-enqueue envelope to mailbox (once).
              DEGRADED    -> return DEGRADED.
              TERMINAL    -> return FAILED.
          - The "once" re-enqueue guard prevents infinite retry loops.

        Args:
            envelope: TaskEnvelope from Concierge.
            ctx: Request-scoped processing context.

        Returns:
            ProcessResult from the tier dispatch or error classification.
        """
        # 1. Validate envelope preconditions (defensive -- TaskEnvelope.__post_init__
        # already validates, but guard against deserialized/constructed envelopes).
        validation_error = self._validate_envelope(envelope, ctx)
        if validation_error is not None:
            return validation_error

        # 2. Emit TASK_ACCEPTED (fire-and-forget, never blocks).
        await self._emit_task_accepted(envelope, ctx)

        # 3. Dispatch by tier with adapter error handling.
        try:
            if envelope.tier == "MEDIUM":
                return await self._dispatch_medium(envelope, ctx)
            elif envelope.tier == "HIGH":
                return await self._dispatch_high(envelope, ctx)
            else:
                # Unreachable (validated above), defensive.
                log.error(
                    "route_task.invalid_tier",
                    extra={
                        "trace_id": ctx.trace_id,
                        "tier": envelope.tier,
                    },
                )
                return ProcessResult.FAILED

        except AdapterException as exc:
            self._emit_error_routed_async(exc, ctx)
            severity = self._error_router.classify(exc, ctx)
            log.warning(
                "route_task.dispatch_error",
                extra={
                    "trace_id": ctx.trace_id,
                    "adapter": exc.adapter_name,
                    "operation": exc.operation,
                    "severity": severity.value,
                    "error_code": exc.error_code,
                    "error_message": exc.error_message,
                    "envelope_id": envelope.envelope_id,
                    "tier": envelope.tier,
                },
            )

            if severity == ErrorSeverity.RECOVERABLE:
                return self._requeue_envelope(envelope, ctx)
            elif severity == ErrorSeverity.DEGRADED:
                return ProcessResult.DEGRADED
            else:
                # TERMINAL
                return ProcessResult.FAILED

    # ======================================================================
    # MEDIUM tier dispatch
    # ======================================================================

    async def _dispatch_medium(
        self,
        envelope: TaskEnvelope,
        ctx: ProcessingContext,
    ) -> ProcessResult:
        """Execute 1-2 capabilities directly via Fabric (no Planner).

        Issue 2.1.3 -- ORCH-10: MEDIUM tier max 2 capabilities,
        no Planner involvement. Per-step error isolation: an
        AdapterException on one step records FAILED for that step
        but does NOT prevent the other step from executing.

        Steps:
          1. ORCH-10 precondition: capabilities non-empty, len <= 2.
          2. Read current safety_band from SessionState.
          3. Query Fabric registry for each capability.
          4. Build CapabilityRequest per capability.
          5. Execute per-step with error isolation.
          6. Aggregate results.
          7. Emit DAG_COMPLETED + audit.

        Args:
            envelope: TaskEnvelope with tier=MEDIUM.
            ctx: Request-scoped processing context.

        Returns:
            COMPLETED, DEGRADED, or FAILED.
        """
        from k1.fabric.types import CapabilityRequest

        t0 = time.monotonic()
        trace_phase(
            log,
            "dispatch_medium",
            trace_id=ctx.trace_id,
            request_id=ctx.request_id,
            tier=ctx.tier,
        )

        # 1. ORCH-10 precondition (defence-in-depth; TaskEnvelope.__post_init__
        #    also validates this, but dispatch_medium is the authoritative gate).
        if not envelope.capabilities or len(envelope.capabilities) > 2:
            log.error(
                "dispatch_medium.orch10_violation",
                extra={
                    "trace_id": ctx.trace_id,
                    "capability_count": len(envelope.capabilities) if envelope.capabilities else 0,
                },
            )
            return ProcessResult.FAILED

        # 2. Read safety_band from SessionState.
        session_id = envelope.context.get("session_id", "")
        safety_band = await self._read_safety_band(session_id, ctx)

        # 3. Validate all capabilities exist and are allowed.
        for cap_name in envelope.capabilities:
            entry = await self._fabric_port.query_registry(cap_name)
            if entry is None:
                log.warning(
                    "dispatch_medium.capability_not_found",
                    extra={
                        "trace_id": ctx.trace_id,
                        "capability": cap_name,
                    },
                )
                return ProcessResult.FAILED

            if safety_band and entry.safety_band_min > safety_band:
                log.warning(
                    "dispatch_medium.safety_band_insufficient",
                    extra={
                        "trace_id": ctx.trace_id,
                        "capability": cap_name,
                        "required": entry.safety_band_min,
                        "current": safety_band,
                    },
                )
                return ProcessResult.FAILED

        # 4. Build CapabilityRequests.
        requests: List[CapabilityRequest] = []
        for cap_name in envelope.capabilities:
            req = CapabilityRequest(
                capability_name=cap_name,
                params=envelope.params.get(cap_name, {}),
                tier="MEDIUM",
                caller="orchestrator",
                caller_id=envelope.envelope_id,
                trace_id=envelope.trace_id,
                timeout_ms=envelope.timeout_ms,
            )
            requests.append(req)

        # 5. Execute per-step with error isolation.
        #    Per 2.1.3 spec: AdapterError(DEGRADED) on one step records
        #    FAILED for that step; the other step still executes.
        step_results: List[StepResult] = []
        for i, (cap_name, req) in enumerate(zip(envelope.capabilities, requests)):
            try:
                with self._metrics.time_adapter_wait(adapter="fabric", operation="execute"):
                    cap_result = await self._fabric_port.execute(req)
                status = StepStatus.COMPLETED if cap_result.success else StepStatus.FAILED
                error_detail = (
                    None
                    if cap_result.success
                    else (cap_result.error.message if cap_result.error else None)
                )
                step_results.append(
                    StepResult(
                        step_id=f"medium_{i}",
                        capability_name=cap_name,
                        status=status,
                        duration_ms=getattr(cap_result, "duration_ms", 0),
                        result=cap_result,
                        error_detail=error_detail,
                    )
                )
            except AdapterException as exc:
                self._emit_error_routed_async(exc, ctx)
                log.warning(
                    "dispatch_medium.step_adapter_error",
                    extra={
                        "trace_id": ctx.trace_id,
                        "step_index": i,
                        "capability": cap_name,
                        "adapter": exc.adapter_name,
                        "error_code": exc.error_code,
                        "error_message": exc.error_message,
                    },
                )
                step_results.append(
                    StepResult(
                        step_id=f"medium_{i}",
                        capability_name=cap_name,
                        status=StepStatus.FAILED,
                        duration_ms=0,
                        result=None,
                        error_detail=exc.error_message,
                    )
                )

        # 6. Aggregate results (Issue 2.1.5: via aggregate() pure function).
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        aggregated = self.aggregate(
            step_results=step_results,
            plan_id=None,
            compensations=[],
            trace_id=ctx.trace_id,
            duration_ms=elapsed_ms,
        )

        # 7. Emit DAG_COMPLETED + audit (fire-and-forget).
        await self._emit_result(aggregated, ctx)
        trace_phase(
            log,
            "dispatch_medium",
            trace_id=ctx.trace_id,
            request_id=ctx.request_id,
            tier=ctx.tier,
            duration_ms=aggregated.duration_ms,
            success=aggregated.success,
        )

        return self._result_to_process_result(aggregated)

    # ======================================================================
    # HIGH tier dispatch (two-phase: request + receive)
    # ======================================================================

    async def _dispatch_high(
        self,
        envelope: TaskEnvelope,
        ctx: ProcessingContext,
    ) -> ProcessResult:
        """Phase 1 of HIGH tier: send PlanRequest to Planner.

        Fire-and-forget. The CommittedPlan arrives asynchronously via
        event bus (plan.ready.v1) and is processed by _receive_plan().

        Per ADR-1.1.12 / WB Section 10.10:
          - Orchestrator generates request_id (uuid4).
          - Planner echoes request_id in CommittedPlan + response events.
          - Orchestrator correlates via pending_plans[request_id].

        Args:
            envelope: TaskEnvelope with tier=HIGH.
            ctx: Request-scoped processing context.

        Returns:
            DEFERRED (plan request sent, execution happens later).
            FAILED if Planner rejects or pending_plans limit exceeded.
        """
        session_id = envelope.context.get("session_id", "")
        trace_phase(
            log,
            "dispatch_high",
            trace_id=ctx.trace_id,
            request_id=ctx.request_id,
            tier=ctx.tier,
        )

        # 1. Capture state snapshot for planning context.
        try:
            snapshot = await self._state_port.get_snapshot(session_id)
        except AdapterException as exc:
            log.warning(
                "dispatch_high.state_snapshot_failed",
                extra={
                    "trace_id": ctx.trace_id,
                    "adapter": exc.adapter_name,
                    "error": exc.error_message,
                },
            )
            # Proceed with None snapshot -- Planner can work without context.
            snapshot = None  # type: ignore[assignment]

        # 2. Generate a unique request_id for this plan request.
        request_id = str(uuid4())

        # 3. Build PlanRequest.
        plan_request = PlanRequest(
            intent=envelope.intent,
            trace_id=ctx.trace_id,
            context=snapshot,
            request_id=request_id,
            constraints=envelope.constraints,
            timeout_ms=self._config.plan_request_timeout_ms,
        )

        # 4. Send to Planner (fire-and-forget).
        try:
            with self._metrics.time_adapter_wait(adapter="planner", operation="request_plan"):
                ack = await self._planner_port.request_plan(plan_request)
        except AdapterException as exc:
            self._emit_error_routed_async(exc, ctx)
            log.error(
                "dispatch_high.planner_unreachable",
                extra={
                    "trace_id": ctx.trace_id,
                    "error": exc.error_message,
                },
            )
            return ProcessResult.FAILED

        if ack.status != "ACCEPTED":
            log.warning(
                "dispatch_high.plan_rejected",
                extra={
                    "trace_id": ctx.trace_id,
                    "request_id": request_id,
                    "ack_status": ack.status,
                },
            )
            return ProcessResult.FAILED

        # 5. Guard: pending_plans capacity.
        if len(self._pending_plans) >= self._config.max_pending_plans:
            log.error(
                "dispatch_high.pending_plans_limit",
                extra={
                    "trace_id": ctx.trace_id,
                    "current": len(self._pending_plans),
                    "max": self._config.max_pending_plans,
                },
            )
            # Best-effort cancel the request we just sent.
            try:
                with self._metrics.time_adapter_wait(adapter="planner", operation="cancel_plan"):
                    await self._planner_port.cancel_plan(request_id)
            except Exception:
                log.debug("dispatch_high.cancel_after_limit_failed", exc_info=True)
            return ProcessResult.FAILED

        # 6. Park context for receive_plan() correlation.
        self._pending_plans[request_id] = PendingPlanContext(
            request_id=request_id,
            task_envelope=envelope,
            state_snapshot=snapshot,  # type: ignore[arg-type]  # None when snapshot unavailable (V1 accepted)
            created_at=time.time(),
            timeout_ms=self._config.plan_request_timeout_ms,
        )
        self._metrics.set_pending_plans(len(self._pending_plans))

        # 7. Emit PLAN_REQUESTED event (fire-and-forget).
        await self._delta_port.emit(
            event_topic=ORCH_PLAN_REQUESTED,
            payload={
                "request_id": request_id,
                "intent": envelope.intent,
                "trace_id": ctx.trace_id,
                "tier": "HIGH",
            },
            trace_id=ctx.trace_id,
        )

        log.info(
            "dispatch_high.plan_requested",
            extra={
                "trace_id": ctx.trace_id,
                "request_id": request_id,
                "intent": envelope.intent,
            },
        )
        trace_phase(
            log,
            "dispatch_high",
            trace_id=ctx.trace_id,
            request_id=request_id,
            tier=ctx.tier,
            success=True,
        )

        return ProcessResult.DEFERRED

    async def _receive_plan(
        self,
        plan: CommittedPlan,
        ctx: ProcessingContext,
    ) -> ProcessResult:
        """Phase 2 of HIGH tier: execute a CommittedPlan as a DAG.

        Triggered when a CommittedPlan is dequeued from the mailbox
        (routed there by the EventSubscription handler for
        k1.planner.plan.ready.v1).

        Steps:
          1. RACE-3 dedup: check executed_plans for plan_id.
          2. Correlate via request_id -> pending_plans.
          3. RACE-1: re-read state snapshot for freshness.
          4. Validate plan via ConstraintResolver.
          5. Acquire ConcurrencyGuard.
          6. Execute DAG via DAGExecutor.
          7. Release ConcurrencyGuard.
          8. Emit result + audit.

        Args:
            plan: CommittedPlan from Planner (via event bus routing).
            ctx: Request-scoped processing context.

        Returns:
            COMPLETED, DEGRADED, FAILED, or CANCELLED.
        """
        t0 = time.monotonic()

        # 1. RACE-3 dedup: reject duplicate plan delivery.
        if plan.plan_id in self._executed_plans:
            log.warning(
                "receive_plan.duplicate",
                extra={
                    "trace_id": ctx.trace_id,
                    "plan_id": plan.plan_id,
                },
            )
            return ProcessResult.COMPLETED

        # 2. Correlate with pending_plans via request_id (WB 10.10).
        pending = self._pending_plans.pop(plan.request_id, None)
        self._metrics.set_pending_plans(len(self._pending_plans))
        if pending is None:
            # Orphan plan (RACE-2): timeout already expired or unknown.
            log.warning(
                "receive_plan.orphan",
                extra={
                    "trace_id": ctx.trace_id,
                    "plan_id": plan.plan_id,
                    "request_id": plan.request_id,
                },
            )
            # Attempt WAL recovery.
            try:
                wal_entries = await self._bridge_port.read_wal(plan.plan_id)
                if wal_entries:
                    log.info(
                        "receive_plan.wal_recovery_found",
                        extra={
                            "trace_id": ctx.trace_id,
                            "plan_id": plan.plan_id,
                            "wal_entries": len(wal_entries),
                        },
                    )
                    # WAL recovery deferred to crash_recovery() -- not handled here.
            except AdapterException:
                log.debug("receive_plan.wal_read_failed", exc_info=True)

            try:
                await self._delta_port.emit(
                    event_topic=ORCH_DELTA_V1,
                    payload={
                        "type": "processing_error",
                        "reason": "orphan_plan_no_context",
                        "plan_id": plan.plan_id,
                        "request_id": plan.request_id,
                        "trace_id": ctx.trace_id,
                    },
                    trace_id=ctx.trace_id,
                )
            except Exception:
                log.debug("receive_plan.orphan_error_delta_failed", exc_info=True)

            return ProcessResult.FAILED

        # 3. Record in executed_plans LRU (before execution, for dedup).
        self._record_executed_plan(plan.plan_id)

        # Update ctx with dag execution context.
        ctx.dag_id = plan.plan_id
        ctx.tier = "HIGH"

        # 4. RACE-1: re-read state snapshot for freshness (20-60s may have
        #    elapsed since dispatch_high()).
        session_id = pending.task_envelope.context.get("session_id", "")
        try:
            _fresh_snapshot = await self._state_port.get_snapshot(session_id)
            # V1: _fresh_snapshot reserved for ConstraintResolver RACE-1
            # staleness check (3.1.x). Not consumed in current version.
        except AdapterException:
            log.warning(
                "receive_plan.state_re_snapshot_failed",
                extra={"trace_id": ctx.trace_id, "plan_id": plan.plan_id},
            )
            # Proceed with stale snapshot from PendingPlanContext.

        # 5. Validate plan via ConstraintResolver.
        try:
            with self._metrics.time_constraint_validation(step_count=len(plan.steps)):
                validation = await self._constraint_resolver.validate(plan, ctx)
        except AdapterException as exc:
            log.error(
                "receive_plan.validation_failed",
                extra={
                    "trace_id": ctx.trace_id,
                    "plan_id": plan.plan_id,
                    "error": exc.error_message,
                },
            )
            return ProcessResult.FAILED

        if not validation.valid:
            log.warning(
                "receive_plan.plan_invalid",
                extra={
                    "trace_id": ctx.trace_id,
                    "plan_id": plan.plan_id,
                    "issues": validation.issues,
                },
            )
            return ProcessResult.FAILED

        # 6. Acquire ConcurrencyGuard (V1: single DAG at a time).
        if not await self._concurrency_guard.acquire(ctx):
            log.warning(
                "receive_plan.concurrency_rejected",
                extra={
                    "trace_id": ctx.trace_id,
                    "plan_id": plan.plan_id,
                },
            )
            return ProcessResult.DEFERRED
        self._metrics.set_dag_active(True)

        try:
            # 7. Execute DAG.
            aggregated = await self._dag_executor.execute(plan, ctx)
        except AdapterException as exc:
            return self._handle_adapter_error(exc, ctx)
        except Exception:
            log.exception(
                "receive_plan.dag_execution_failed",
                extra={
                    "trace_id": ctx.trace_id,
                    "plan_id": plan.plan_id,
                },
            )
            return ProcessResult.FAILED
        finally:
            # 8. Always release ConcurrencyGuard.
            self._concurrency_guard.release(ctx)
            self._metrics.set_dag_active(False)

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        log.info(
            "receive_plan.completed",
            extra={
                "trace_id": ctx.trace_id,
                "plan_id": plan.plan_id,
                "elapsed_ms": elapsed_ms,
            },
        )

        # 9. Emit result + audit (fire-and-forget).
        await self._emit_result(aggregated, ctx)

        return self._result_to_process_result(aggregated)

    # ======================================================================
    # Plan failure / cancellation handlers
    # ======================================================================

    async def receive_plan_failed(
        self,
        request_id: str,
        reason: str,
        error_detail: Optional[str],
        trace_id: str,
    ) -> ProcessResult:
        """Handle plan.failed.v1 event from Planner.

        Pops the PendingPlanContext and emits a FAILED AggregatedResult.

        Args:
            request_id: Echoed request_id from PlanRequest.
            reason: Failure reason enum string.
            error_detail: Optional additional detail.
            trace_id: Cognitive trace identifier.

        Returns:
            FAILED always.
        """
        pending = self._pending_plans.pop(request_id, None)
        if pending is None:
            log.warning(
                "receive_plan_failed.no_pending_context",
                extra={
                    "trace_id": trace_id,
                    "request_id": request_id,
                },
            )
            return ProcessResult.FAILED

        log.info(
            "receive_plan_failed",
            extra={
                "trace_id": trace_id,
                "request_id": request_id,
                "reason": reason,
                "error_detail": error_detail,
            },
        )

        # Emit an empty FAILED AggregatedResult.
        aggregated = self.aggregate(
            step_results=[],
            plan_id=None,
            compensations=[],
            trace_id=trace_id,
            duration_ms=int((time.time() - pending.created_at) * 1000),
        )

        ctx = ProcessingContext(
            trace_id=trace_id,
            request_id=request_id,
            tier="HIGH",
        )
        await self._emit_result(aggregated, ctx)

        return ProcessResult.FAILED

    async def receive_plan_cancelled(
        self,
        request_id: str,
        trace_id: str,
    ) -> ProcessResult:
        """Handle plan.cancelled.v1 event from Planner.

        Pops the PendingPlanContext and returns CANCELLED.

        Args:
            request_id: Echoed request_id from PlanRequest.
            trace_id: Cognitive trace identifier.

        Returns:
            CANCELLED always.
        """
        pending = self._pending_plans.pop(request_id, None)
        if pending is None:
            log.warning(
                "receive_plan_cancelled.no_pending_context",
                extra={
                    "trace_id": trace_id,
                    "request_id": request_id,
                },
            )
            return ProcessResult.CANCELLED

        log.info(
            "receive_plan_cancelled",
            extra={
                "trace_id": trace_id,
                "request_id": request_id,
            },
        )

        return ProcessResult.CANCELLED

    # ======================================================================
    # Workflow dispatch
    # ======================================================================

    async def _dispatch_workflow(
        self,
        request: WorkflowRunRequest,
        ctx: ProcessingContext,
    ) -> ProcessResult:
        """Dispatch a workflow run request to the WorkflowEngine.

        Args:
            request: WorkflowRunRequest from scheduler or user.
            ctx: Request-scoped processing context.

        Returns:
            ProcessResult from WorkflowEngine.
        """
        ctx.workflow_id = request.workflow_id

        # ConcurrencyGuard: workflows compete for the same DAG slot.
        if not await self._concurrency_guard.acquire(ctx):
            log.info(
                "dispatch_workflow.concurrency_rejected",
                extra={
                    "trace_id": ctx.trace_id,
                    "workflow_id": request.workflow_id,
                },
            )
            return ProcessResult.DEFERRED
        self._metrics.set_dag_active(True)

        try:
            return await self._workflow_engine.execute_workflow(request, ctx)
        except AdapterException as exc:
            return self._handle_adapter_error(exc, ctx)
        except Exception:
            log.exception(
                "dispatch_workflow.failed",
                extra={
                    "trace_id": ctx.trace_id,
                    "workflow_id": request.workflow_id,
                },
            )
            return ProcessResult.FAILED
        finally:
            self._concurrency_guard.release(ctx)
            self._metrics.set_dag_active(False)

    async def _save_workflow(
        self,
        request: WorkflowSaveRequest,
        ctx: ProcessingContext,
    ) -> ProcessResult:
        """Save a committed plan as a reusable workflow (Issue 2.1.6).

        Delegates to WorkflowEngine.save_workflow() which handles:
          - Plan lookup (from DAGExecutor cache or WAL).
          - WorkflowSpec construction.
          - Registry save + trigger registration.

        OrchestratorService's responsibility:
          - Route the WorkflowSaveRequest.
          - Emit ORCH_WORKFLOW_SAVED delta on success.
          - Handle adapter errors.

        Gotcha: save_workflow does not re-validate the plan against
        the current capability registry. The plan was valid when it
        ran; gap detection (4.2.7) handles future drift.

        TODO(M4): WorkflowEngine.save_workflow() full implementation
          in Epic 4.x. Current WorkflowEngineLike protocol stub
          delegates the Plan lookup + WorkflowSpec construction
          to the engine. When M4 ships, this method remains unchanged
          -- only the engine adapter behind the protocol evolves.

        Args:
            request: WorkflowSaveRequest from Concierge.
            ctx: Request-scoped processing context.

        Returns:
            COMPLETED on success, FAILED or DEGRADED on error.
        """
        log.info(
            "save_workflow.start",
            extra={
                "trace_id": ctx.trace_id,
                "committed_plan_id": request.committed_plan_id,
                "workflow_name": request.workflow_name,
            },
        )

        try:
            result = await self._workflow_engine.save_workflow(request, ctx)
        except AdapterException as exc:
            return self._handle_adapter_error(exc, ctx)
        except Exception:
            log.exception(
                "save_workflow.failed",
                extra={
                    "trace_id": ctx.trace_id,
                    "committed_plan_id": request.committed_plan_id,
                },
            )
            return ProcessResult.FAILED

        # Emit workflow_saved delta on success (fire-and-forget).
        if result == ProcessResult.COMPLETED:
            await self._delta_port.emit(
                event_topic=ORCH_WORKFLOW_SAVED,
                payload={
                    "committed_plan_id": request.committed_plan_id,
                    "workflow_name": request.workflow_name,
                    "trigger_type": request.trigger_spec.type.value,
                    "trace_id": ctx.trace_id,
                },
                trace_id=ctx.trace_id,
            )

            log.info(
                "save_workflow.completed",
                extra={
                    "trace_id": ctx.trace_id,
                    "committed_plan_id": request.committed_plan_id,
                    "workflow_name": request.workflow_name,
                },
            )

            try:
                workflows = await self._workflow_engine.registry.list_active()  # type: ignore[union-attr]
                self._metrics.set_workflow_active_count(len(workflows))
            except Exception:
                pass

        return result

    # ======================================================================
    # Interrupt handling
    # ======================================================================

    async def _handle_interrupt(
        self,
        request: InterruptRequest,
        ctx: ProcessingContext,
    ) -> ProcessResult:
        """Handle an interrupt request (cancel DAG, etc.).

        V1: only CANCEL_DAG is supported (PAUSE rejected).

        Args:
            request: InterruptRequest with target_dag_id and type.
            ctx: Request-scoped processing context.

        Returns:
            CANCELLED on success, FAILED if interrupt_type not supported.
        """
        if request.interrupt_type == "PAUSE":
            log.warning(
                "handle_interrupt.pause_not_supported_v1",
                extra={
                    "trace_id": ctx.trace_id,
                    "target_dag_id": request.target_dag_id,
                },
            )
            return ProcessResult.FAILED

        trace_phase(
            log,
            "interrupt",
            trace_id=ctx.trace_id,
            request_id=ctx.request_id,
            tier=ctx.tier,
            success=True,
        )
        log.info(
            "handle_interrupt.cancel_dag",
            extra={
                "trace_id": ctx.trace_id,
                "target_dag_id": request.target_dag_id,
                "reason": request.reason,
            },
        )
        try:
            if hasattr(self._dag_executor, "interrupt_flag"):
                setattr(self._dag_executor, "interrupt_flag", True)
        except Exception:
            log.debug(
                "handle_interrupt.set_interrupt_flag_failed",
                exc_info=True,
                extra={"trace_id": ctx.trace_id},
            )
        # DAG cancellation is cooperative: set interrupt flag on DAGExecutor.
        # The actual cancellation happens at the next step completion.
        # For 2.1.1, we return CANCELLED; actual interrupt flag set is in DAGExecutor (2.2.x).
        return ProcessResult.CANCELLED

    # ======================================================================
    # Timeout reaper for stale pending contexts
    # ======================================================================

    async def reap_stale_contexts(self) -> int:
        """Expire stale PendingPlanContext and PendingHILContext entries.

        Called periodically by the mailbox loop (every config.context_reap_interval_ms).

        For each expired PendingPlanContext:
          - Cancel the plan request with the Planner (best-effort).
          - Emit a FAILED AggregatedResult.
          - Remove from pending_plans.

        For each expired PendingHILContext:
          - Apply timeout_fallback action.
          - Remove from pending_hil.

        Returns:
            Number of contexts reaped.
        """
        now = time.time()
        reaped = 0

        # Reap stale plan contexts.
        stale_plan_ids = [
            rid
            for rid, pctx in self._pending_plans.items()
            if (now - pctx.created_at) > (pctx.timeout_ms / 1000.0)
        ]
        for rid in stale_plan_ids:
            pctx = self._pending_plans.pop(rid, None)
            if pctx is None:
                continue  # Race: already popped by receive_plan.

            log.warning(
                "reap_stale_contexts.plan_timeout",
                extra={
                    "trace_id": pctx.task_envelope.trace_id,
                    "request_id": rid,
                    "age_s": round(now - pctx.created_at, 2),
                },
            )

            # Best-effort cancel.
            try:
                await self._planner_port.cancel_plan(rid)
            except Exception:
                log.debug("reap_stale_contexts.cancel_plan_failed", exc_info=True)

            # Emit FAILED result.
            aggregated = self.aggregate(
                step_results=[],
                plan_id=None,
                compensations=[],
                trace_id=pctx.task_envelope.trace_id,
                duration_ms=int((now - pctx.created_at) * 1000),
            )
            ctx = ProcessingContext(
                trace_id=pctx.task_envelope.trace_id,
                request_id=rid,
                tier="HIGH",
            )
            await self._emit_result(aggregated, ctx)
            reaped += 1
        self._metrics.set_pending_plans(len(self._pending_plans))

        # Reap stale HIL contexts.
        stale_hil_ids = [
            rid
            for rid, hctx in self._pending_hil.items()
            if (now - hctx.created_at) > (hctx.timeout_ms / 1000.0)
        ]
        for rid in stale_hil_ids:
            hctx = self._pending_hil.pop(rid, None)
            if hctx is None:
                continue

            log.warning(
                "reap_stale_contexts.hil_timeout",
                extra={
                    "request_id": rid,
                    "fallback": hctx.timeout_fallback,
                    "age_s": round(now - hctx.created_at, 2),
                },
            )
            self._metrics.increment_hil_request(outcome="timed_out")
            reaped += 1
        self._metrics.set_pending_hil(len(self._pending_hil))

        return reaped

    # ======================================================================
    # Internal helpers
    # ======================================================================

    def _build_context(self, message: MailboxMessage) -> ProcessingContext:
        """Construct a ProcessingContext from an inbound message.

        Extracts trace_id, request_id, and tier from the message
        based on its type.
        """
        trace_id = ""
        request_id = ""
        tier = "MEDIUM"

        if isinstance(message, TaskEnvelope):
            trace_id = message.trace_id
            request_id = message.envelope_id
            tier = message.tier
        elif isinstance(message, CommittedPlan):
            trace_id = message.trace_id
            request_id = message.request_id
            tier = "HIGH"
        elif isinstance(message, WorkflowRunRequest):
            trace_id = message.trace_id
            request_id = message.request_id
            tier = "WORKFLOW"
        elif isinstance(message, WorkflowSaveRequest):
            trace_id = message.trace_id
            request_id = message.request_id
            tier = "WORKFLOW"
        elif isinstance(message, InterruptRequest):
            trace_id = message.trace_id
            request_id = message.request_id
            tier = "REALTIME"

        # Fallback for missing trace_id (should not happen in production).
        if not trace_id:
            trace_id = str(uuid4())
            log.warning(
                "_build_context.missing_trace_id",
                extra={"message_type": type(message).__name__},
            )
        if not request_id:
            request_id = str(uuid4())

        return ProcessingContext(
            trace_id=trace_id,
            request_id=request_id,
            tier=tier,
            created_at=time.time(),
        )

    def _validate_envelope(
        self,
        envelope: TaskEnvelope,
        ctx: ProcessingContext,
    ) -> Optional[ProcessResult]:
        """Validate TaskEnvelope preconditions.

        Returns None if valid, or a ProcessResult on failure.
        """
        if not envelope.trace_id:
            log.error(
                "validate_envelope.missing_trace_id",
                extra={"request_id": ctx.request_id},
            )
            return ProcessResult.FAILED

        if not envelope.intent:
            log.error(
                "validate_envelope.missing_intent",
                extra={"trace_id": ctx.trace_id},
            )
            return ProcessResult.FAILED

        if envelope.tier not in ("MEDIUM", "HIGH"):
            log.error(
                "validate_envelope.invalid_tier",
                extra={
                    "trace_id": ctx.trace_id,
                    "tier": envelope.tier,
                },
            )
            return ProcessResult.FAILED

        return None

    async def _read_safety_band(
        self,
        session_id: str,
        ctx: ProcessingContext,
    ) -> Optional[str]:
        """Read the current safety_band from SessionState.

        Returns the band string or None if unavailable.
        """
        if not session_id:
            return None

        try:
            control = await self._state_port.read_section(session_id, "control")
            if control and isinstance(control, dict):
                return control.get("safety_band")
        except AdapterException as exc:
            log.warning(
                "read_safety_band.failed",
                extra={
                    "trace_id": ctx.trace_id,
                    "adapter": exc.adapter_name,
                },
            )
        return None

    async def _emit_task_accepted(
        self,
        envelope: TaskEnvelope,
        ctx: ProcessingContext,
    ) -> None:
        """Emit TASK_ACCEPTED event (fire-and-forget)."""
        await self._delta_port.emit(
            event_topic=ORCH_TASK_ACCEPTED,
            payload={
                "envelope_id": envelope.envelope_id,
                "intent": envelope.intent,
                "tier": envelope.tier,
                "trace_id": ctx.trace_id,
            },
            trace_id=ctx.trace_id,
        )

    def _requeue_envelope(
        self,
        envelope: TaskEnvelope,
        ctx: ProcessingContext,
    ) -> ProcessResult:
        """Re-enqueue a TaskEnvelope to the mailbox (once guard).

        The "once" constraint prevents infinite retry loops.
        ``_requeued_envelope_ids`` tracks which envelopes have already
        been re-enqueued; a second occurrence returns FAILED.

        The tracking set is bounded (``_EXECUTED_PLANS_MAX`` entries)
        to prevent unbounded growth.

        Args:
            envelope: The TaskEnvelope to re-enqueue.
            ctx: Request-scoped processing context.

        Returns:
            DEFERRED if re-enqueued successfully.
            FAILED if once guard triggered or enqueue rejected.
        """
        # Once guard: prevent infinite re-enqueue loops.
        if envelope.envelope_id in self._requeued_envelope_ids:
            log.warning(
                "requeue_envelope.already_requeued",
                extra={
                    "trace_id": ctx.trace_id,
                    "envelope_id": envelope.envelope_id,
                },
            )
            return ProcessResult.FAILED

        try:
            self._mailbox.enqueue(envelope, priority="INTERACTIVE")
        except Exception:
            log.warning(
                "requeue_envelope.enqueue_failed",
                extra={
                    "trace_id": ctx.trace_id,
                    "envelope_id": envelope.envelope_id,
                },
                exc_info=True,
            )
            return ProcessResult.FAILED

        # Track re-enqueue (bounded LRU, same cap as executed_plans).
        self._requeued_envelope_ids[envelope.envelope_id] = time.time()
        self._requeued_envelope_ids.move_to_end(envelope.envelope_id)
        while len(self._requeued_envelope_ids) > _EXECUTED_PLANS_MAX:
            self._requeued_envelope_ids.popitem(last=False)

        log.info(
            "requeue_envelope.success",
            extra={
                "trace_id": ctx.trace_id,
                "envelope_id": envelope.envelope_id,
            },
        )
        return ProcessResult.DEFERRED

    async def _emit_result(
        self,
        aggregated: AggregatedResult,
        ctx: ProcessingContext,
    ) -> None:
        """Emit DAG_COMPLETED event and submit audit (both fire-and-forget)."""
        if aggregated.success:
            status = "success"
        elif aggregated.cancelled > 0:
            status = "interrupted"
        else:
            status = "failed"
        self._metrics.increment_dag_completed(status=status)

        await self._delta_port.emit(
            event_topic=ORCH_DAG_COMPLETED,
            payload=aggregated.to_dict(),
            trace_id=ctx.trace_id,
        )

        await self._bridge_port.submit_audit(
            run_manifest=aggregated.to_dict(),
            trace_id=ctx.trace_id,
        )

    def _record_executed_plan(self, plan_id: str) -> None:
        """Add plan_id to the bounded LRU dedup set.

        Evicts the oldest entry when the set exceeds _EXECUTED_PLANS_MAX.
        """
        self._executed_plans[plan_id] = time.time()
        # Move to end (most recently used).
        self._executed_plans.move_to_end(plan_id)

        # Evict oldest if over capacity.
        while len(self._executed_plans) > _EXECUTED_PLANS_MAX:
            self._executed_plans.popitem(last=False)

    def _handle_adapter_error(
        self,
        exc: AdapterException,
        ctx: ProcessingContext,
    ) -> ProcessResult:
        """Classify an AdapterException and return the appropriate ProcessResult."""
        self._emit_error_routed_async(exc, ctx)
        severity = self._error_router.classify(exc, ctx)
        self._metrics.increment_error(classification=severity.value)
        trace_phase(
            log,
            "error",
            trace_id=ctx.trace_id,
            request_id=ctx.request_id,
            tier=ctx.tier,
            success=False,
            level=logging.ERROR,
            extra={
                "adapter": exc.adapter_name,
                "operation": exc.operation,
                "classification": severity.value,
                "error_code": exc.error_code,
            },
        )

        log.warning(
            "adapter_error",
            extra={
                "trace_id": ctx.trace_id,
                "adapter": exc.adapter_name,
                "operation": exc.operation,
                "severity": severity.value,
                "error_code": exc.error_code,
                "error_message": exc.error_message,
            },
        )

        if severity == ErrorSeverity.TERMINAL:
            return ProcessResult.FAILED
        elif severity == ErrorSeverity.DEGRADED:
            return ProcessResult.DEGRADED
        else:
            # RECOVERABLE -- caller should re-enqueue if possible.
            return ProcessResult.DEFERRED

    def _emit_error_routed_async(
        self,
        exc: AdapterException,
        ctx: ProcessingContext,
    ) -> None:
        """Best-effort async emission of ORCH_ERROR_ROUTED via ErrorRouter.route_error.

        Keeps existing synchronous severity mapping intact while allowing
        process-path diagnostics to be emitted for Concierge observability.
        """
        route_error = getattr(self._error_router, "route_error", None)
        if not callable(route_error):
            return

        try:
            maybe_coro = route_error(exc.detail, {"trace_id": ctx.trace_id})
            if asyncio.iscoroutine(maybe_coro):
                asyncio.create_task(
                    cast("Any", maybe_coro),
                    name="orchestrator-error-routed",
                )
        except Exception:
            log.debug(
                "emit_error_routed_async.failed",
                exc_info=True,
                extra={"trace_id": ctx.trace_id},
            )

    def aggregate(
        self,
        step_results: List[StepResult],
        plan_id: Optional[str],
        compensations: List[CompensationRecord],
        trace_id: str,
        duration_ms: int = 0,
    ) -> AggregatedResult:
        """Pure aggregation of step results into AggregatedResult (Issue 2.1.5).

        No I/O, no side effects. Delegates to the appropriate
        AggregatedResult factory method based on plan_id presence.

        V1 scope reduction: token/cost aggregation steps removed
        (tokens_consumed, cost_usd, budget_utilization) -- no provider
        populates these fields.

        Delivery is NOT part of this method. Callers (dispatch_medium /
        receive_plan) handle:
          (a) delta_port.emit(ORCH_DAG_COMPLETED, result.to_dict(), trace_id)
          (b) bridge_port.submit_audit(result.to_dict(), trace_id)
        Both fire-and-forget.

        Called for both MEDIUM (1-2 steps, no plan_id) and HIGH
        (N steps, with plan_id) tiers.

        Args:
            step_results: List of StepResults from capability execution.
            plan_id: CommittedPlan.plan_id for HIGH tier, None for MEDIUM.
            compensations: Saga compensation records (HIGH tier only).
            trace_id: Cognitive trace identifier.
            duration_ms: Total elapsed time in milliseconds.

        Returns:
            AggregatedResult with computed success, counts, and classification.
        """
        with self._metrics.time_aggregation(plan_id=plan_id or "medium"):
            trace_phase(
                log,
                "aggregate",
                trace_id=trace_id,
                request_id=None,
                tier="HIGH" if plan_id else "MEDIUM",
                duration_ms=duration_ms,
                level=logging.DEBUG,
            )
            if plan_id is not None:
                return AggregatedResult.from_dag(
                    plan_id=plan_id,
                    step_results=step_results,
                    compensations=compensations,
                    trace_id=trace_id,
                    duration_ms=duration_ms,
                )
            return AggregatedResult.from_medium(
                step_results=step_results,
                trace_id=trace_id,
                duration_ms=duration_ms,
            )

    @staticmethod
    def _result_to_process_result(aggregated: AggregatedResult) -> ProcessResult:
        """Map an AggregatedResult to a ProcessResult enum value."""
        if aggregated.success:
            return ProcessResult.COMPLETED

        if aggregated.cancelled > 0 and aggregated.completed == 0:
            return ProcessResult.CANCELLED

        if aggregated.failed > 0 and aggregated.completed > 0:
            return ProcessResult.DEGRADED

        return ProcessResult.FAILED
