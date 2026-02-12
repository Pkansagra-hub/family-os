"""
k1.orchestrator.workflows.workflow_engine -- WorkflowEngine facade (6.2.1).

Composes workflow sub-components into the two operations required
by OrchestratorService via WorkflowEngineLike Protocol:
  - execute_workflow(request, ctx) -> ProcessResult
  - save_workflow(request, ctx) -> ProcessResult

This facade is the single object injected into OrchestratorService
as ``workflow_engine``.  All workflow-subsystem complexity (registry,
compiler, scheduler, supervisor, cross-resolver, gap-detector) is
hidden behind these two entry points.

Construction order (factory step 14):
  All sub-components must be fully constructed before WorkflowEngine.
  DAGExecutor (step 13) and ConstraintResolver (step 14a) must be
  available because execute_workflow drives the full lifecycle:
    start -> validate -> execute DAG -> complete/fail.

Design constraints:
  - ConcurrencyGuard is NOT held here -- OrchestratorService wraps
    the call in _dispatch_workflow with acquire/release.
  - Error routing for AdapterException is NOT done here --
    OrchestratorService._dispatch_workflow catches and classifies.
  - This class is NOT responsible for event subscriptions (init() step 8).
  - save_workflow V1: saves spec to registry but plan-lookup from WAL
    is deferred to M4 (TODO marker retained for traceability).

References:
  - factory-discovery.md section 12 (WorkflowEngineLike Facade)
  - orchestrator_service.py WorkflowEngineLike Protocol (line 113)
  - orchestrator-implementation-plan.md Issue 6.2.1

Exports:
  WorkflowEngine
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from k1.orchestrator.types import ProcessingContext, ProcessResult

if TYPE_CHECKING:
    from k1.orchestrator.orchestration.constraint_resolver import ConstraintResolver
    from k1.orchestrator.orchestration.dag_executor import DAGExecutor
    from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
    from k1.orchestrator.types import WorkflowRunRequest, WorkflowSaveRequest
    from k1.orchestrator.workflows.cross_workflow_resolver import CrossWorkflowResolver
    from k1.orchestrator.workflows.gap_detector import ProactiveGapDetector
    from k1.orchestrator.workflows.workflow_compiler import WorkflowCompiler
    from k1.orchestrator.workflows.workflow_registry import WorkflowRegistry
    from k1.orchestrator.workflows.workflow_scheduler import WorkflowScheduler
    from k1.orchestrator.workflows.workflow_supervisor import WorkflowRunSupervisor

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Facade composing workflow sub-components into WorkflowEngineLike.

    Holds every workflow-subsystem component so the factory wires them
    once and OrchestratorService consumes a single object.

    Slots are frozen after construction -- no mutable state beyond what
    the sub-components themselves hold.
    """

    __slots__ = (
        "_supervisor",
        "_dag_executor",
        "_constraint_resolver",
        "_registry",
        "_compiler",
        "_scheduler",
        "_cross_resolver",
        "_gap_detector",
        "_delta",
    )

    def __init__(
        self,
        *,
        supervisor: WorkflowRunSupervisor,
        dag_executor: DAGExecutor,
        constraint_resolver: ConstraintResolver,
        registry: WorkflowRegistry,
        compiler: WorkflowCompiler,
        scheduler: WorkflowScheduler,
        cross_resolver: CrossWorkflowResolver,
        gap_detector: ProactiveGapDetector,
        delta: IDeltaEmitPort,
    ) -> None:
        self._supervisor = supervisor
        self._dag_executor = dag_executor
        self._constraint_resolver = constraint_resolver
        self._registry = registry
        self._compiler = compiler
        self._scheduler = scheduler
        self._cross_resolver = cross_resolver
        self._gap_detector = gap_detector
        self._delta = delta

    # ------------------------------------------------------------------
    # WorkflowEngineLike Protocol: execute_workflow
    # ------------------------------------------------------------------

    async def execute_workflow(
        self,
        request: WorkflowRunRequest,
        ctx: ProcessingContext,
    ) -> ProcessResult:
        """Start, validate, execute, and finalize a workflow run.

        Full lifecycle:
          1. supervisor.start_run(request) -- lookup, compile, manifest.
          2. If compilation failed (no compiled_plan) -> FAILED.
          3. constraint_resolver.validate(plan, ctx) -- pre-exec check.
          4. dag_executor.execute(plan, ctx) -- wave-by-wave execution.
          5. supervisor.complete_run/fail_run -- manifest bookkeeping.
          6. Return mapped ProcessResult.

        ConcurrencyGuard is NOT acquired here -- the caller
        (OrchestratorService._dispatch_workflow) holds the guard.

        Args:
            request: WorkflowRunRequest from scheduler or user.
            ctx: Request-scoped ProcessingContext.

        Returns:
            ProcessResult reflecting execution outcome.
        """
        trace = ctx.trace_id

        # 1 -- Start the run (lookup + compile + manifest).
        run_result = await self._supervisor.start_run(request)

        if run_result.compiled_plan is None:
            logger.warning(
                "WorkflowEngine.execute_workflow: compilation failed "
                "(workflow_id=%s, run_id=%s, trace_id=%s)",
                request.workflow_id,
                run_result.manifest.run_id,
                trace,
            )
            return ProcessResult.FAILED

        plan = run_result.compiled_plan
        manifest = run_result.manifest

        # 2 -- Validate plan constraints.
        validation = await self._constraint_resolver.validate(plan)
        if not validation.valid:
            logger.warning(
                "WorkflowEngine.execute_workflow: validation failed "
                "(workflow_id=%s, issues=%s, trace_id=%s)",
                request.workflow_id,
                validation.issues,
                trace,
            )
            await self._supervisor.fail_run(
                manifest,
                error=f"Constraint validation failed: {validation.issues}",
                trace_id=trace,
            )
            return ProcessResult.FAILED

        # 3 -- Execute the compiled plan as a DAG.
        #      DAGExecutor.execute(plan, snapshot) -- Protocol says
        #      (plan, ctx) but implementation uses snapshot parameter
        #      name.  OrchestratorService passes ctx here too.
        aggregated = await self._dag_executor.execute(plan, ctx)  # type: ignore[arg-type]

        # 4 -- Finalize manifest based on execution outcome.
        if aggregated.success:
            await self._supervisor.complete_run(manifest, aggregated)
            return ProcessResult.COMPLETED

        # Partial success (some steps succeeded, independent ones failed).
        has_successes = any(
            sr.status.value == "COMPLETED"
            for sr in aggregated.step_results
            if hasattr(sr, "status") and hasattr(sr.status, "value")
        )
        if has_successes:
            await self._supervisor.complete_run(manifest, aggregated)
            return ProcessResult.DEGRADED

        # Full failure.
        error_msg = (
            aggregated.error_detail if hasattr(aggregated, "error_detail") else "All steps failed"
        )
        await self._supervisor.fail_run(
            manifest,
            error=error_msg,
            trace_id=trace,
        )
        return ProcessResult.FAILED

    # ------------------------------------------------------------------
    # WorkflowEngineLike Protocol: save_workflow
    # ------------------------------------------------------------------

    async def save_workflow(
        self,
        request: WorkflowSaveRequest,
        ctx: ProcessingContext,
    ) -> ProcessResult:
        """Save a committed plan as a reusable workflow.

        TODO(M4): Full implementation requires:
          - Plan step extraction from bridge WAL or DAGExecutor cache
            via committed_plan_id.
          - WorkflowSpec construction with real steps.
          - Version management via registry.save().

        V1 returns FAILED because WorkflowSpec requires non-empty
        steps (validated in __post_init__) and plan-step extraction
        is not yet implemented.  OrchestratorService._save_workflow
        handles the FAILED return correctly (no delta emitted).

        When M4 ships, this method gains the plan-lookup logic.
        The call site in OrchestratorService remains unchanged.

        Args:
            request: WorkflowSaveRequest from Concierge.
            ctx: Request-scoped ProcessingContext.

        Returns:
            FAILED (V1 -- plan-step extraction not yet implemented).
        """
        trace = ctx.trace_id

        logger.warning(
            "WorkflowEngine.save_workflow: not yet implemented "
            "(plan-step extraction deferred to M4) "
            "(name=%s, plan_id=%s, trace_id=%s)",
            request.workflow_name,
            request.committed_plan_id,
            trace,
        )

        # TODO(M4): Look up committed plan by committed_plan_id from
        #   bridge_port WAL or DAGExecutor cache.  Extract steps,
        #   build WorkflowSpec(trigger=request.trigger_spec, steps=...,
        #   version="1.0.0", source_plan_id=request.committed_plan_id),
        #   then call self._registry.save(spec).

        return ProcessResult.FAILED

    # ------------------------------------------------------------------
    # Sub-component accessors (read-only, for lifecycle/init wiring)
    # ------------------------------------------------------------------

    @property
    def supervisor(self) -> WorkflowRunSupervisor:
        """WorkflowRunSupervisor instance."""
        return self._supervisor

    @property
    def scheduler(self) -> WorkflowScheduler:
        """WorkflowScheduler instance (for init() tick-loop startup)."""
        return self._scheduler

    @property
    def gap_detector(self) -> ProactiveGapDetector:
        """ProactiveGapDetector instance (for init() subscription)."""
        return self._gap_detector

    @property
    def cross_resolver(self) -> CrossWorkflowResolver:
        """CrossWorkflowResolver instance."""
        return self._cross_resolver

    @property
    def registry(self) -> WorkflowRegistry:
        """WorkflowRegistry instance."""
        return self._registry

    @property
    def compiler(self) -> WorkflowCompiler:
        """WorkflowCompiler instance."""
        return self._compiler
