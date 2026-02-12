"""
k1.orchestrator.workflows.workflow_supervisor -- WorkflowRunSupervisor (4.2.3).

Manages workflow execution lifecycle: start_run(), concurrent-run
policy (single active per workflow in V1), compilation, manifest
tracking, and result delivery.

Design:
  - start_run() returns (RunManifest, CommittedPlan) for downstream
    DAG execution by OrchestratorService.
  - complete_run() / fail_run() update manifest status and persist.
  - deliver_result() handles session-aware vs deferred result routing
    (PROD-4).
  - _abort_run() is idempotent -- safe even if the DAG already finished.

Constructor dependency chain (OrchestratorFactory step ? in 6.2.1):
  1. registry:  WorkflowRegistry   -- workflow lookup
  2. compiler:  WorkflowCompiler   -- compile spec into CommittedPlan
  3. storage:   IWorkflowStoragePort -- persist manifests, check runs
  4. delta:     IDeltaEmitPort     -- emit events + HIL notification
  5. bridge:    IBridgeWritePort   -- deferred result storage

Anti-hallucination rules:
  - Single active run per workflow (ADR-1.1.11 Q5). If a run is
    already RUNNING when start_run() is called, the old run is aborted.
  - _abort_run() must be idempotent.
  - RunManifest is FROZEN -- status transitions create new instances.
  - AggregatedResult has to_dict(), NOT to_summary_dict().

Exports:
  WorkflowRunSupervisor, WorkflowNotFoundError, StartRunResult
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from k1.orchestrator.ports.bridge_write_port import IBridgeWritePort
from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort
from k1.orchestrator.types import AggregatedResult, CommittedPlan, WorkflowRunRequest
from k1.orchestrator.workflows.workflow_compiler import WorkflowCompiler
from k1.orchestrator.workflows.workflow_registry import WorkflowRegistry
from k1.orchestrator.workflows.workflow_types import RunManifest, RunStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class WorkflowNotFoundError(Exception):
    """Raised when a workflow_id references a non-existent or inactive workflow."""

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"Workflow '{workflow_id}' not found or inactive")


# ---------------------------------------------------------------------------
# StartRunResult -- returned by start_run()
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StartRunResult:
    """Bundle returned by ``WorkflowRunSupervisor.start_run()``.

    Contains the manifest (audit record) and the compiled plan ready
    for DAG execution. If compilation failed, ``compiled_plan`` is None
    and ``manifest.status == FAILED``.
    """

    manifest: RunManifest
    compiled_plan: Optional[CommittedPlan] = None


# ---------------------------------------------------------------------------
# WorkflowRunSupervisor
# ---------------------------------------------------------------------------


class WorkflowRunSupervisor:
    """Manage workflow execution lifecycle (4.2.3).

    Responsibilities:
      - ``start_run(request)`` -- look up spec, enforce single-active-run
        policy, compile, create manifest, return to caller for DAG execution.
      - ``complete_run(manifest, result)`` -- mark COMPLETED, persist, deliver.
      - ``fail_run(manifest, error)`` -- mark FAILED, persist.
      - ``deliver_result(manifest, result)`` -- session-aware result routing.

    Concurrent run policy (ADR-1.1.11 Q5):
      Single active run per workflow. If the latest run is RUNNING when
      ``start_run()`` is called, it is aborted first.
    """

    def __init__(
        self,
        registry: WorkflowRegistry,
        compiler: WorkflowCompiler,
        storage: IWorkflowStoragePort,
        delta: IDeltaEmitPort,
        bridge: IBridgeWritePort,
    ) -> None:
        self._registry = registry
        self._compiler = compiler
        self._storage = storage
        self._delta = delta
        self._bridge = bridge

    # -- Primary entry point -------------------------------------------------

    async def start_run(self, request: WorkflowRunRequest) -> StartRunResult:
        """Start a workflow run from a trigger request.

        Steps:
          1. Look up WorkflowSpec -- raise WorkflowNotFoundError if missing/inactive.
          2. Enforce single-active-run policy -- abort any RUNNING predecessor.
          3. Compile spec -- on failure, save a FAILED manifest and return.
          4. Create RUNNING manifest, persist, and return with compiled plan.

        Args:
            request: Trigger request from WorkflowScheduler or Concierge.

        Returns:
            StartRunResult containing the manifest and optional compiled plan.

        Raises:
            WorkflowNotFoundError: If workflow not found or inactive.
        """
        trace = request.trace_id

        # 1 -- Lookup
        spec = await self._registry.get(request.workflow_id)
        if spec is None or not spec.active:
            raise WorkflowNotFoundError(request.workflow_id)

        # 2 -- Concurrent-run check (single active per workflow, V1)
        await self._enforce_single_active_run(request.workflow_id, trace)

        # 3 -- Compile
        compilation = await self._compiler.compile(spec)

        if not compilation.success:
            # Compilation failed -- store a FAILED manifest
            failed_manifest = RunManifest.create(
                workflow_id=spec.workflow_id,
                version=spec.version,
                compiled_hash=compilation.compiled_hash or "",
                trigger_type=(
                    request.trigger_type.value
                    if hasattr(request.trigger_type, "value")
                    else str(request.trigger_type)
                ),
                total_steps=len(spec.steps),
            ).fail(f"Compilation failed: {len(compilation.gaps)} gap(s) detected")

            await self._storage.save_run(failed_manifest)

            logger.warning(
                "WorkflowRunSupervisor: compilation failed for workflow_id=%s "
                "(gaps=%d, trace_id=%s)",
                spec.workflow_id,
                len(compilation.gaps),
                trace,
            )
            return StartRunResult(manifest=failed_manifest, compiled_plan=None)

        # 4 -- Create RUNNING manifest
        trigger_type_str = (
            request.trigger_type.value
            if hasattr(request.trigger_type, "value")
            else str(request.trigger_type)
        )
        manifest = RunManifest.create(
            workflow_id=spec.workflow_id,
            version=spec.version,
            compiled_hash=compilation.compiled_hash or "",
            trigger_type=trigger_type_str,
            total_steps=len(spec.steps),
        )
        await self._storage.save_run(manifest)

        logger.info(
            "WorkflowRunSupervisor: started run_id=%s for workflow_id=%s "
            "(version=%s, trace_id=%s)",
            manifest.run_id,
            spec.workflow_id,
            spec.version,
            trace,
        )

        await self._delta.emit(
            "k1.orchestration.workflow.run_started",
            {
                "run_id": manifest.run_id,
                "workflow_id": manifest.workflow_id,
                "version": manifest.version,
                "trigger_type": manifest.trigger_type,
            },
            trace,
        )

        return StartRunResult(manifest=manifest, compiled_plan=compilation.compiled_plan)

    # -- Post-execution lifecycle --------------------------------------------

    async def complete_run(
        self,
        manifest: RunManifest,
        result: AggregatedResult,
    ) -> RunManifest:
        """Transition manifest RUNNING -> COMPLETED, persist, deliver result.

        Returns the updated (COMPLETED) manifest.
        """
        updated = manifest.complete(result_summary=result.to_dict())
        await self._storage.save_run(updated)

        logger.info(
            "WorkflowRunSupervisor: completed run_id=%s (success=%s)",
            updated.run_id,
            result.success,
        )

        await self._delta.emit(
            "k1.orchestration.workflow.run_completed",
            {
                "run_id": updated.run_id,
                "workflow_id": updated.workflow_id,
                "success": result.success,
                "duration_ms": result.duration_ms,
            },
            result.trace_id,
        )

        return updated

    async def fail_run(
        self,
        manifest: RunManifest,
        error: str,
        trace_id: str = "",
    ) -> RunManifest:
        """Transition manifest RUNNING -> FAILED, persist.

        Returns the updated (FAILED) manifest.
        """
        updated = manifest.fail(error)
        await self._storage.save_run(updated)

        logger.warning(
            "WorkflowRunSupervisor: failed run_id=%s (error=%s)",
            updated.run_id,
            error,
        )

        await self._delta.emit(
            "k1.orchestration.workflow.run_failed",
            {
                "run_id": updated.run_id,
                "workflow_id": updated.workflow_id,
                "error": error,
            },
            trace_id,
        )

        return updated

    async def deliver_result(
        self,
        manifest: RunManifest,
        result: AggregatedResult,
        session_active: bool,
    ) -> None:
        """Deliver a completed workflow result.

        PROD-4: If session is active, emit via delta. If no session
        (e.g. cron at 3 AM), persist as deferred result via bridge.
        Concierge checks for pending results on next session start.

        Args:
            manifest: The completed RunManifest.
            result: The AggregatedResult from DAG execution.
            session_active: Whether a user session is currently active.
        """
        if session_active:
            await self._delta.emit(
                "k1.orchestration.workflow.result",
                {
                    "run_id": manifest.run_id,
                    "workflow_id": manifest.workflow_id,
                    "result": result.to_dict(),
                },
                result.trace_id,
            )
        else:
            # No session -- persist for later retrieval (PROD-4)
            await self._bridge.submit_deferred_result(
                result=result.to_dict(),
                workflow_id=manifest.workflow_id,
                trace_id=result.trace_id,
            )
            logger.info(
                "WorkflowRunSupervisor: deferred result for run_id=%s " "(no active session)",
                manifest.run_id,
            )

    # -- Internal helpers ----------------------------------------------------

    async def _enforce_single_active_run(
        self,
        workflow_id: str,
        trace_id: str,
    ) -> None:
        """Abort any RUNNING run for this workflow (ADR-1.1.11 Q5).

        Idempotent: if no run is RUNNING or the run already completed
        between the check and abort, this is a no-op.
        """
        runs = await self._storage.get_runs(workflow_id, limit=1)
        if not runs:
            return

        latest = runs[0]
        # If latest is a dict (from storage), check status string
        latest_status = self._extract_status(latest)
        if latest_status == RunStatus.RUNNING:
            await self._abort_run(latest, trace_id)

    async def _abort_run(self, run: Any, trace_id: str) -> None:
        """Abort a run. Idempotent -- safe even if already completed.

        Args:
            run: RunManifest or dict-like run record.
            trace_id: For event correlation.
        """
        if isinstance(run, RunManifest):
            if run.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.ABORTED):
                return  # Already terminal -- no-op
            aborted = run.abort()
            await self._storage.save_run(aborted)
            run_id = run.run_id
            workflow_id = run.workflow_id
        else:
            # Dict-like (from raw storage query)
            run_id = run.get("run_id", "unknown") if isinstance(run, dict) else str(run)
            workflow_id = run.get("workflow_id", "") if isinstance(run, dict) else ""

        logger.info(
            "WorkflowRunSupervisor: aborted run_id=%s for workflow_id=%s",
            run_id,
            workflow_id,
        )

        await self._delta.emit(
            "k1.orchestration.workflow.run_aborted",
            {"run_id": run_id, "workflow_id": workflow_id},
            trace_id,
        )

    @staticmethod
    def _extract_status(run: Any) -> Optional[RunStatus]:
        """Extract RunStatus from a RunManifest or dict-like object."""
        if isinstance(run, RunManifest):
            return run.status
        if isinstance(run, dict):
            raw = run.get("status")
            if isinstance(raw, RunStatus):
                return raw
            if isinstance(raw, str):
                try:
                    return RunStatus(raw)
                except ValueError:
                    return None
        return None
