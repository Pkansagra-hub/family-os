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

import logging
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Protocol, runtime_checkable
from uuid import uuid4

from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.events import (
    ORCH_DAG_COMPLETED,
    ORCH_PLAN_REQUESTED,
    ORCH_TASK_ACCEPTED,
    ORCH_WORKFLOW_SAVED,
)
from k1.orchestrator.ports.bridge_write_port import IBridgeWritePort
from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
from k1.orchestrator.ports.fabric_gateway_port import IFabricGatewayPort
from k1.orchestrator.ports.mailbox_port import IMailboxPort, MailboxMessage
from k1.orchestrator.ports.planner_port import IPlannerPort
from k1.orchestrator.ports.state_read_port import IStateReadPort
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
    ProcessingContext,
    ProcessResult,
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
    """Placeholder protocol for ConnectorLifecycleManager (5.x)."""

    ...


@runtime_checkable
class ErrorRouterLike(Protocol):
    """Protocol for ErrorRouter (2.1.7).

    classify() -- sync severity-only interface used by OrchestratorService
    route_error() -- async full interface returning ErrorAction with delta emission
    """

    def classify(self, error: "AdapterException", ctx: ProcessingContext) -> ErrorSeverity: ...


@runtime_checkable
class ConcurrencyGuardLike(Protocol):
    """Placeholder protocol for ConcurrencyGuard (3.2.x)."""

    def acquire(self, ctx: ProcessingContext) -> bool: ...

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
        "_mailbox",
        "_config",
        "_pending_plans",
        "_pending_hil",
        "_executed_plans",
        "_requeued_envelope_ids",
        "_started_at",
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
        config: OrchestratorConfig,
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

        # --- Configuration ---
        self._config = config

        # --- Internal mutable state ---
        self._pending_plans: Dict[str, PendingPlanContext] = {}
        self._pending_hil: Dict[str, PendingHILContext] = {}
        self._executed_plans: OrderedDict[str, float] = OrderedDict()
        self._requeued_envelope_ids: OrderedDict[str, float] = OrderedDict()
        self._started_at: float = time.time()

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
            trace_id=envelope.trace_id,
            context=snapshot,
            request_id=request_id,
            constraints=envelope.constraints,
            timeout_ms=self._config.plan_request_timeout_ms,
        )

        # 4. Send to Planner (fire-and-forget).
        try:
            ack: PlanAck = await self._planner_port.request_plan(plan_request)
        except AdapterException as exc:
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
        if not self._concurrency_guard.acquire(ctx):
            log.warning(
                "receive_plan.concurrency_rejected",
                extra={
                    "trace_id": ctx.trace_id,
                    "plan_id": plan.plan_id,
                },
            )
            return ProcessResult.DEFERRED

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
        if not self._concurrency_guard.acquire(ctx):
            log.info(
                "dispatch_workflow.concurrency_rejected",
                extra={
                    "trace_id": ctx.trace_id,
                    "workflow_id": request.workflow_id,
                },
            )
            return ProcessResult.DEFERRED

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

        log.info(
            "handle_interrupt.cancel_dag",
            extra={
                "trace_id": ctx.trace_id,
                "target_dag_id": request.target_dag_id,
                "reason": request.reason,
            },
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
            reaped += 1

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
        severity = self._error_router.classify(exc, ctx)

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
