"""
DAGExecutor -- Adaptive Blind DAG Executor (Issues 2.2.1-2.2.6).

Heart of HIGH-tier execution. Builds execution waves from a
CommittedPlan dependency graph via Kahn's topological sort, then
executes waves in parallel with per-step concurrency control.

Issue 2.2.1: DAGExecutor class + build_waves() pure function.
Issue 2.2.2: execute() + execute_wave() + _execute_step() parallel executor.
Issue 2.2.3: collect_results() result aggregator.
Issue 2.2.4: cancel_dependents() dependent step cancellation (ORCH-07).
Issue 2.2.5: _compensate() saga recovery -- reverse-order compensation.
Issue 2.2.6: recover_from_wal() WAL interaction protocol.

Constructor: 8 deps injected by OrchestratorFactory (6.2.1 step 13).
Guards list is empty in M2, populated by M3.

Anti-hallucination:
  - DAGExecutor does NOT dequeue from mailbox (that is _mailbox_loop).
  - DAGExecutor does NOT call planner_port.request_plan() (that is dispatch_high).
  - DAGExecutor calls planner_port.micro_replan() ONLY via MicroReplanCheckpoint guard.
  - build_waves() is a PURE FUNCTION -- no I/O, no async, no side effects.
  - cancel_dependents() is a PURE FUNCTION -- no I/O, no async, no side effects.
  - recover_from_wal() is a STATIC METHOD -- only reads WAL, returns resume info.
  - No LLM calls. No writes to SessionState.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_DAG_STARTED
from k1.orchestrator.types import (
    AggregatedResult,
    CompensationRecord,
    StepResult,
    StepStatus,
    Wave,
    WaveResult,
)

if TYPE_CHECKING:
    from k1.fabric.ports.state_reader import SessionSnapshot
    from k1.fabric.types import CapabilityResult
    from k1.orchestrator.ports.bridge_write_port import IBridgeWritePort
    from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
    from k1.orchestrator.ports.fabric_gateway_port import IFabricGatewayPort
    from k1.orchestrator.ports.planner_port import IPlannerPort
    from k1.orchestrator.ports.state_read_port import IStateReadPort
    from k1.orchestrator.types import CommittedPlan, PlanStep

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Limits (per orchestrator.mmd and implementation plan)
# ---------------------------------------------------------------------------
MAX_WAVES: int = 20
MAX_STEPS: int = 50

# Max concurrent steps within a single wave (asyncio.Semaphore).
_MAX_CONCURRENT_PER_WAVE: int = 10

# Safety band levels that trigger immediate DAG abort.
_ABORT_SAFETY_LEVELS: frozenset[str] = frozenset({"RED", "BLACK"})


def _now_ms() -> int:
    """Return current monotonic time in milliseconds."""
    return int(time.monotonic() * 1000)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CycleError(Exception):
    """Raised when build_waves detects a cycle in the dependency graph.

    Contains the set of step IDs involved in the cycle for diagnostics.
    """

    def __init__(self, remaining_steps: Set[str]) -> None:
        self.remaining_steps = remaining_steps
        sorted_ids = sorted(remaining_steps)
        super().__init__(f"Cycle detected in dependency graph. " f"Steps involved: {sorted_ids}")


class WaveLimitExceeded(Exception):
    """Raised when topological sort produces more waves than MAX_WAVES."""

    def __init__(self, wave_count: int, max_waves: int = MAX_WAVES) -> None:
        self.wave_count = wave_count
        self.max_waves = max_waves
        super().__init__(f"Wave count {wave_count} exceeds maximum {max_waves}")


class StepLimitExceeded(Exception):
    """Raised when total step count exceeds MAX_STEPS."""

    def __init__(self, step_count: int, max_steps: int = MAX_STEPS) -> None:
        self.step_count = step_count
        self.max_steps = max_steps
        super().__init__(f"Step count {step_count} exceeds maximum {max_steps}")


# ---------------------------------------------------------------------------
# DAGExecutor
# ---------------------------------------------------------------------------


class DAGExecutor:
    """Adaptive Blind DAG Executor -- heart of HIGH-tier execution.

    Constructor: 8 deps + guards list.
    build_waves()        -- pure function, Kahn's topological sort (2.2.1).
    execute()            -- async DAG orchestrator (2.2.2).
    execute_wave()       -- async parallel wave executor (2.2.2).
    _execute_step()      -- async single step delegator (2.2.2).
    collect_results()    -- result aggregator (2.2.3).
    cancel_dependents()  -- BFS dependent cancellation (2.2.4, ORCH-07).
    _compensate()        -- saga recovery, reverse-order compensation (2.2.5).
    recover_from_wal()   -- WAL recovery protocol (2.2.6).

    Internal mutable state (reset per execute() call):
      interrupt_flag   -- cooperative cancellation flag (set by handle_interrupt).
      merged_results   -- step_id -> CapabilityResult from completed steps.
      _cancelled_steps -- step IDs cancelled due to dependency failure.
    """

    __slots__ = (
        "_fabric_port",
        "_planner_port",
        "_delta_port",
        "_state_port",
        "_bridge_port",
        "_step_runner",
        "_error_router",
        "_guards",
        "_param_resolver",
        "interrupt_flag",
        "merged_results",
        "_cancelled_steps",
    )

    def __init__(
        self,
        fabric_port: IFabricGatewayPort,
        planner_port: IPlannerPort,
        delta_port: IDeltaEmitPort,
        state_port: IStateReadPort,
        bridge_port: IBridgeWritePort,
        step_runner: Any,  # StepRunner (2.3.1) -- not yet implemented
        error_router: Any,  # ErrorRouter (2.1.7)
        guards: Optional[List[Any]] = None,  # DAGGuard list, empty in M2
        param_resolver: Optional[Any] = None,  # ParamResolver (2.3.5)
    ) -> None:
        """Construct DAGExecutor with 8 port/service deps + guards.

        Args:
            fabric_port: For execute_batch() parallel step dispatch.
            planner_port: For micro-replan only (via MicroReplanCheckpoint).
            delta_port: For progress deltas after each wave.
            state_port: For safety_band re-read at wave boundary.
            bridge_port: For WAL writes (PLAN_START, WAVE_COMPLETE, etc.).
            step_runner: StepRunner for individual step execution.
            error_router: ErrorRouter for error classification.
            guards: Ordered guard list. Empty in M2, populated by M3.
            param_resolver: ParamResolver for $-reference resolution.
        """
        self._fabric_port = fabric_port
        self._planner_port = planner_port
        self._delta_port = delta_port
        self._state_port = state_port
        self._bridge_port = bridge_port
        self._step_runner = step_runner
        self._error_router = error_router
        self._guards: List[Any] = guards if guards is not None else []
        self._param_resolver = param_resolver

        # Mutable state (reset per execute() call)
        self.interrupt_flag: bool = False
        self.merged_results: Dict[str, CapabilityResult] = {}
        self._cancelled_steps: Set[str] = set()

    # ------------------------------------------------------------------
    # build_waves -- Pure function: Kahn's topological sort (2.2.1)
    # ------------------------------------------------------------------

    @staticmethod
    def build_waves(
        steps: List[PlanStep],
        dependencies: Dict[str, List[str]],
    ) -> List[Wave]:
        """Build parallel execution waves via Kahn's topological sort.

        Pure function -- no I/O, no async, no side effects.
        Uses the dependencies dict from CommittedPlan directly (not
        re-derived from PlanStep.deps).

        Algorithm:
          1. Validate step count <= MAX_STEPS.
          2. Build step lookup and adjacency (dep -> dependents).
          3. Compute in-degree for each step.
          4. Initialize queue with zero-in-degree steps.
          5. While queue non-empty: pop all -> form Wave(wave_index, steps, {}).
          6. Decrement in-degree of dependents; enqueue newly-zero.
          7. If steps remain -> CycleError.
          8. Validate wave count <= MAX_WAVES.

        Args:
            steps: List of PlanStep from CommittedPlan.steps.
            dependencies: Dict of step_id -> [dep_ids] from CommittedPlan.

        Returns:
            List[Wave] ordered by wave_index (0-based).

        Raises:
            StepLimitExceeded: Total steps exceed MAX_STEPS (50).
            WaveLimitExceeded: Wave count exceeds MAX_WAVES (20).
            CycleError: Dependency graph contains a cycle.
            ValueError: Step referenced in dependencies not found in steps.
        """
        # Step 1: Validate total step count
        if len(steps) > MAX_STEPS:
            raise StepLimitExceeded(len(steps))

        # Step 2: Build step lookup by ID
        step_map: Dict[str, PlanStep] = {}
        for step in steps:
            step_map[step.id] = step

        # Validate dependency references
        all_ids = set(step_map.keys())
        for step_id, dep_list in dependencies.items():
            if step_id not in all_ids:
                raise ValueError(
                    f"dependencies key '{step_id}' not found in steps "
                    f"(available: {sorted(all_ids)})"
                )
            for dep_id in dep_list:
                if dep_id not in all_ids:
                    raise ValueError(
                        f"dependency '{dep_id}' of step '{step_id}' not in "
                        f"steps (available: {sorted(all_ids)})"
                    )

        # Step 3: Build adjacency list (dep -> list of dependents)
        # and compute in-degree for each step.
        adjacency: Dict[str, List[str]] = {sid: [] for sid in all_ids}
        in_degree: Dict[str, int] = {sid: 0 for sid in all_ids}

        for step_id, dep_list in dependencies.items():
            for dep_id in dep_list:
                adjacency[dep_id].append(step_id)
                in_degree[step_id] += 1

        # Step 4: Initialize queue with zero-in-degree steps
        queue: deque[str] = deque()
        for sid in all_ids:
            if in_degree[sid] == 0:
                queue.append(sid)

        # Step 5-6: Kahn's algorithm -- form waves
        waves: List[Wave] = []
        visited_count: int = 0

        while queue:
            # All current zero-in-degree steps form one wave
            wave_step_ids: List[str] = list(queue)
            queue.clear()

            # Deterministic ordering within a wave for reproducibility
            wave_step_ids.sort()

            wave_steps: List[PlanStep] = [step_map[sid] for sid in wave_step_ids]
            waves.append(
                Wave(
                    wave_index=len(waves),
                    steps=wave_steps,
                    resolved_params={},
                )
            )
            visited_count += len(wave_step_ids)

            # Decrement in-degree of dependents; enqueue newly-zero
            for sid in wave_step_ids:
                for dependent_id in adjacency[sid]:
                    in_degree[dependent_id] -= 1
                    if in_degree[dependent_id] == 0:
                        queue.append(dependent_id)

        # Step 7: Cycle detection
        if visited_count != len(steps):
            remaining = all_ids - {step.id for wave in waves for step in wave.steps}
            raise CycleError(remaining)

        # Step 8: Validate wave count
        if len(waves) > MAX_WAVES:
            raise WaveLimitExceeded(len(waves))

        log.debug(
            "[DAGExecutor] build_waves: %d steps -> %d waves",
            len(steps),
            len(waves),
        )

        return waves

    # ------------------------------------------------------------------
    # execute -- Full DAG orchestrator (2.2.2)
    # ------------------------------------------------------------------

    async def execute(
        self,
        plan: CommittedPlan,
        snapshot: SessionSnapshot,
    ) -> AggregatedResult:
        """Execute a CommittedPlan as parallel waves.

        Orchestrates full DAG execution lifecycle:
          1. Reset mutable state (interrupt_flag, merged_results, cancelled_steps).
          2. Build waves via Kahn's topological sort.
          3. WAL write PLAN_START.
          4. Execute waves sequentially; steps within each wave run in parallel.
          5. Run post-wave guards (M3, no-op in M2).
          6. Aggregate and return results.

        Args:
            plan: CommittedPlan from Planner (validated, acyclic).
            snapshot: SessionSnapshot for context (passed to step_runner).

        Returns:
            AggregatedResult with per-step results, compensations, success flag.
        """
        dag_start_ms = _now_ms()

        # Step 1: Reset state
        self.interrupt_flag = False
        self.merged_results = {}
        self._cancelled_steps = set()

        # Step 2: Build waves
        waves = self.build_waves(plan.steps, plan.dependencies)

        log.info(
            "[DAGExecutor] execute: plan=%s, steps=%d, waves=%d, trace=%s",
            plan.plan_id,
            len(plan.steps),
            len(waves),
            plan.trace_id,
        )

        # Step 3: WAL write PLAN_START (fire-and-forget)
        try:
            await self._bridge_port.write_wal(
                plan.plan_id,
                "PLAN_START",
                {"plan": plan.to_dict()},
                plan.trace_id,
            )
        except Exception:
            log.warning("[DAGExecutor] WAL write PLAN_START failed", exc_info=True)

        # Emit DAG_STARTED event
        try:
            await self._delta_port.emit(
                ORCH_DAG_STARTED,
                {
                    "plan_id": plan.plan_id,
                    "total_steps": len(plan.steps),
                    "total_waves": len(waves),
                },
                plan.trace_id,
            )
        except Exception:
            log.warning("[DAGExecutor] DAG_STARTED emit failed", exc_info=True)

        # Step 4: Execute waves sequentially
        wave_results: List[WaveResult] = []
        aborted = False

        for wave in waves:
            if self.interrupt_flag:
                log.info(
                    "[DAGExecutor] Interrupt detected before wave %d",
                    wave.wave_index,
                )
                aborted = True
                break

            # Filter out cancelled steps from prior wave failures
            active_steps = [s for s in wave.steps if s.id not in self._cancelled_steps]
            if not active_steps:
                log.debug(
                    "[DAGExecutor] Wave %d: all steps cancelled, skipping",
                    wave.wave_index,
                )
                continue

            # Create a filtered wave with only active steps
            active_wave = Wave(
                wave_index=wave.wave_index,
                steps=active_steps,
                resolved_params={},
            )

            wave_result = await self.execute_wave(active_wave, plan, snapshot)
            wave_results.append(wave_result)

            # Cancel dependents of failed steps (ORCH-07, 2.2.4)
            for sr in wave_result.step_results:
                if sr.status == StepStatus.FAILED:
                    cancelled_ids = self.cancel_dependents(sr.step_id, plan)
                    if cancelled_ids:
                        log.info(
                            "[DAGExecutor] Step %s failed -- cancelled " "dependents: %s",
                            sr.step_id,
                            cancelled_ids,
                        )

            # Check for abort conditions after wave
            has_failures = any(sr.status == StepStatus.FAILED for sr in wave_result.step_results)
            if has_failures and self.interrupt_flag:
                aborted = True
                break

            # Step 5: Post-wave guards (M3 extensions, no-op in M2)
            for guard in self._guards:
                if hasattr(guard, "after_wave"):
                    try:
                        await guard.after_wave(active_wave, wave_result, plan)
                    except Exception:
                        log.warning(
                            "[DAGExecutor] Guard after_wave failed",
                            exc_info=True,
                        )

        # Step 6: Aggregate results
        dag_duration_ms = _now_ms() - dag_start_ms

        # Step 6: Saga compensation (2.2.5)
        # If any side-effect step failed, compensate previously-completed
        # side-effect steps in reverse declaration order.
        compensations = await self._compensate(wave_results, plan)

        result = self.collect_results(
            wave_results=wave_results,
            plan=plan,
            compensations=compensations,
            dag_duration_ms=dag_duration_ms,
        )

        # WAL write DAG_COMPLETE (fire-and-forget)
        dag_status = "COMPLETED" if result.success else "FAILED"
        if aborted:
            dag_status = "ABORTED"

        try:
            await self._bridge_port.write_wal(
                plan.plan_id,
                "DAG_COMPLETE",
                {"status": dag_status},
                plan.trace_id,
            )
        except Exception:
            log.warning("[DAGExecutor] WAL write DAG_COMPLETE failed", exc_info=True)

        # Emit DAG_COMPLETED event
        try:
            await self._delta_port.emit(
                ORCH_DAG_COMPLETED,
                result.to_dict(),
                plan.trace_id,
            )
        except Exception:
            log.warning("[DAGExecutor] DAG_COMPLETED emit failed", exc_info=True)

        # Submit audit record (fire-and-forget)
        try:
            await self._bridge_port.submit_audit(
                result.to_dict(),
                plan.trace_id,
            )
        except Exception:
            log.warning("[DAGExecutor] submit_audit failed", exc_info=True)

        log.info(
            "[DAGExecutor] execute complete: plan=%s, success=%s, "
            "completed=%d, failed=%d, cancelled=%d, skipped=%d, "
            "duration=%dms",
            plan.plan_id,
            result.success,
            result.completed,
            result.failed,
            result.cancelled,
            result.skipped,
            result.duration_ms,
        )

        return result

    # ------------------------------------------------------------------
    # execute_wave -- Parallel wave execution (2.2.2)
    # ------------------------------------------------------------------

    async def execute_wave(
        self,
        wave: Wave,
        plan: CommittedPlan,
        snapshot: SessionSnapshot,
    ) -> WaveResult:
        """Execute all steps in a wave concurrently.

        Logic:
          1. Safety band re-read -- abort if RED/BLACK.
          2. Resolve $-references via ParamResolver.
          3. Dispatch steps with asyncio.Semaphore(10) concurrency.
          4. After each step: check interrupt_flag (SPEC-5).
          5. WAL write WAVE_COMPLETE.
          6. Emit progress delta.

        Args:
            wave: Wave with active steps (cancelled already filtered).
            plan: CommittedPlan for context (plan_id, trace_id).
            snapshot: SessionSnapshot for step_runner context.

        Returns:
            WaveResult with per-step results and wall-clock duration.
        """
        wave_start_ms = _now_ms()

        # Step 1: Safety band check
        abort_result = await self._check_safety_band(plan.trace_id)
        if abort_result is not None:
            # Safety band RED/BLACK -- abort entire DAG
            self.interrupt_flag = True
            log.warning(
                "[DAGExecutor] Safety band abort at wave %d: %s",
                wave.wave_index,
                abort_result,
            )
            return WaveResult(
                wave_index=wave.wave_index,
                step_results=[],
                duration_ms=_now_ms() - wave_start_ms,
            )

        # Step 2: Resolve $-references via ParamResolver
        resolved_steps: List[Tuple[PlanStep, Dict[str, Any]]] = []
        step_results: List[StepResult] = []
        for step in wave.steps:
            resolved_params = dict(step.params) if step.params else {}
            if self._param_resolver is not None:
                try:
                    resolved_params, resolved_cap = self._param_resolver.resolve(
                        step, self.merged_results
                    )
                    # Handle dynamic capability resolution (meta-agent)
                    if resolved_cap and resolved_cap != step.capability:
                        log.info(
                            "[DAGExecutor] Dynamic capability: %s -> %s (step %s)",
                            step.capability,
                            resolved_cap,
                            step.id,
                        )
                except Exception as exc:
                    log.error(
                        "[DAGExecutor] ParamResolver failed for step %s: %s",
                        step.id,
                        exc,
                    )
                    # Treat as step failure -- record error, skip dispatch
                    step_results.append(
                        StepResult(
                            step_id=step.id,
                            capability_name=step.capability,
                            status=StepStatus.FAILED,
                            duration_ms=0,
                            error_detail=f"ParamResolver error: {exc}",
                        )
                    )
                    wave.resolved_params[step.id] = {}
                    continue

            wave.resolved_params[step.id] = resolved_params
            resolved_steps.append((step, resolved_params))

        # Step 3+4: Dispatch steps with semaphore concurrency control
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_PER_WAVE)

        async def _run_guarded(s: PlanStep, params: Dict[str, Any]) -> StepResult:
            async with semaphore:
                return await self._execute_step(s, params, plan.trace_id, snapshot)

        # Create tasks for all resolved steps
        tasks: Dict[asyncio.Task, str] = {}  # task -> step_id
        for step, params in resolved_steps:
            # Skip steps that already failed during param resolution
            if step.id in {sr.step_id for sr in step_results if sr.status == StepStatus.FAILED}:
                continue
            task = asyncio.create_task(
                _run_guarded(step, params),
                name=f"step-{step.id}",
            )
            tasks[task] = step.id

        # Collect results as they complete; check interrupt after each
        for coro in asyncio.as_completed(list(tasks.keys())):
            try:
                result = await coro
            except Exception as exc:
                # Unexpected error in _execute_step wrapper
                task_obj = None
                for t in tasks:
                    if t.done():
                        try:
                            t.result()
                        except Exception:
                            task_obj = t
                            break
                sid = tasks.get(task_obj, "unknown") if task_obj else "unknown"
                log.error(
                    "[DAGExecutor] Unexpected step error for %s: %s",
                    sid,
                    exc,
                )
                result = StepResult(
                    step_id=sid,
                    capability_name="unknown",
                    status=StepStatus.FAILED,
                    error_detail=f"Unexpected: {exc}",
                )

            step_results.append(result)

            # Store in merged_results for param resolution in later waves
            if result.status == StepStatus.COMPLETED and result.result is not None:
                self.merged_results[result.step_id] = result.result

            # Check interrupt flag after EACH step (SPEC-5)
            if self.interrupt_flag:
                log.info(
                    "[DAGExecutor] Interrupt detected during wave %d, "
                    "cancelling remaining steps",
                    wave.wave_index,
                )
                # Cancel remaining tasks
                for t in tasks:
                    if not t.done():
                        t.cancel()
                # Mark remaining as CANCELLED
                completed_ids = {sr.step_id for sr in step_results}
                for t, sid in tasks.items():
                    if sid not in completed_ids:
                        step_results.append(
                            StepResult(
                                step_id=sid,
                                capability_name="unknown",
                                status=StepStatus.CANCELLED,
                                error_detail="Interrupted",
                            )
                        )
                break

        # Add any param-resolution failures that were collected earlier
        # (they are already in the step_results preamble from the resolve loop)

        wave_duration_ms = _now_ms() - wave_start_ms

        # Step 5: WAL write WAVE_COMPLETE (fire-and-forget)
        try:
            await self._bridge_port.write_wal(
                plan.plan_id,
                "WAVE_COMPLETE",
                {
                    "wave_index": wave.wave_index,
                    "completed_steps": [sr.step_id for sr in step_results],
                },
                plan.trace_id,
            )
        except Exception:
            log.warning("[DAGExecutor] WAL write WAVE_COMPLETE failed", exc_info=True)

        # Step 6: Emit progress delta
        total_merged = len(self.merged_results)
        total_steps = len(plan.steps)
        try:
            await self._delta_port.emit_progress(
                step_id=f"wave-{wave.wave_index}",
                summary=(
                    f"Wave {wave.wave_index} complete: " f"{total_merged}/{total_steps} steps done"
                ),
                trace_id=plan.trace_id,
            )
        except Exception:
            log.warning("[DAGExecutor] progress delta failed", exc_info=True)

        return WaveResult(
            wave_index=wave.wave_index,
            step_results=step_results,
            duration_ms=wave_duration_ms,
        )

    # ------------------------------------------------------------------
    # _execute_step -- Single step delegator (2.2.2)
    # ------------------------------------------------------------------

    async def _execute_step(
        self,
        step: PlanStep,
        resolved_params: Dict[str, Any],
        trace_id: str,
        snapshot: SessionSnapshot,
    ) -> StepResult:
        """Execute a single step by delegating to step_runner.

        Pre-step guards and post-step guards (M3) are invoked around
        the step_runner call. In M2, guards list is empty (no-op).

        Args:
            step: PlanStep to execute.
            resolved_params: Params with $-references resolved.
            trace_id: Cognitive trace ID for correlation.
            snapshot: SessionSnapshot for step context.

        Returns:
            StepResult from step_runner (COMPLETED, FAILED, etc.).
        """
        step_start_ms = _now_ms()

        # Pre-step guards (M3 extensions, no-op in M2)
        for guard in self._guards:
            if hasattr(guard, "before_step"):
                try:
                    await guard.before_step(step, resolved_params)
                except Exception:
                    log.warning(
                        "[DAGExecutor] Guard before_step failed for %s",
                        step.id,
                        exc_info=True,
                    )

        # Delegate to step_runner
        try:
            result: StepResult = await self._step_runner.run(
                step, resolved_params, self.merged_results, trace_id
            )
        except Exception as exc:
            log.error(
                "[DAGExecutor] step_runner.run failed for step %s: %s",
                step.id,
                exc,
            )
            result = StepResult(
                step_id=step.id,
                capability_name=step.capability,
                status=StepStatus.FAILED,
                duration_ms=_now_ms() - step_start_ms,
                error_detail=str(exc),
            )

        # Post-step guards (M3 extensions, no-op in M2)
        for guard in self._guards:
            if hasattr(guard, "after_step"):
                try:
                    await guard.after_step(step, result)
                except Exception:
                    log.warning(
                        "[DAGExecutor] Guard after_step failed for %s",
                        step.id,
                        exc_info=True,
                    )

        # WAL write STEP_COMPLETE (fire-and-forget)
        try:
            await self._bridge_port.write_wal(
                step.id,
                "STEP_COMPLETE",
                {
                    "step_id": step.id,
                    "status": result.status.value,
                    "result_summary": (result.result.data if result.result else None),
                },
                trace_id,
            )
        except Exception:
            log.warning(
                "[DAGExecutor] WAL write STEP_COMPLETE failed for %s",
                step.id,
                exc_info=True,
            )

        return result

    # ------------------------------------------------------------------
    # _check_safety_band -- Safety band gate (2.2.2)
    # ------------------------------------------------------------------

    async def _check_safety_band(self, trace_id: str) -> Optional[str]:
        """Check safety band level; return abort reason or None.

        Reads control.safety_band from StateReadPort. If level is
        RED or BLACK, returns abort reason string. Otherwise None.
        On read failure, returns None (proceed anyway -- degraded).

        Args:
            trace_id: Cognitive trace ID for the read call.

        Returns:
            Abort reason string if RED/BLACK, None otherwise.
        """
        try:
            band_data = await self._state_port.read_section(
                session_id="default",
                section="control.safety_band",
            )
            if band_data is not None:
                level = band_data.get("level", "GREEN")
                if level in _ABORT_SAFETY_LEVELS:
                    return f"safety_band={level}"
        except Exception:
            log.warning(
                "[DAGExecutor] Safety band read failed, proceeding",
                exc_info=True,
            )
        return None

    # ------------------------------------------------------------------
    # collect_results -- Result aggregator (2.2.3)
    # ------------------------------------------------------------------

    def collect_results(
        self,
        wave_results: List[WaveResult],
        plan: CommittedPlan,
        compensations: List[CompensationRecord],
        dag_duration_ms: int = 0,
    ) -> AggregatedResult:
        """Aggregate wave results into a single AggregatedResult.

        Pure function (no I/O). Handles partial wave_results from
        aborted DAGs gracefully -- steps not in any WaveResult get
        status=CANCELLED.

        Logic:
          1. Flatten all StepResults from all WaveResults.
          2. For steps not in any wave result (cancelled/skipped),
             create synthetic StepResult(status=CANCELLED).
          3. Compute totals via AggregatedResult.from_dag() factory.

        Args:
            wave_results: List of WaveResult from executed waves.
            plan: CommittedPlan for plan_id, step list, trace_id.
            compensations: CompensationRecords from saga recovery (2.2.5).
            dag_duration_ms: Wall-clock DAG duration in milliseconds.

        Returns:
            AggregatedResult with complete step accounting.
        """
        # Step 1: Flatten all step results from executed waves
        all_step_results: List[StepResult] = []
        seen_step_ids: Set[str] = set()

        for wr in wave_results:
            for sr in wr.step_results:
                all_step_results.append(sr)
                seen_step_ids.add(sr.step_id)

        # Step 2: Create synthetic CANCELLED results for missing steps
        all_plan_step_ids = {s.id for s in plan.steps}
        missing_ids = all_plan_step_ids - seen_step_ids

        for missing_id in sorted(missing_ids):
            # Find the PlanStep to get capability_name
            capability = "unknown"
            for s in plan.steps:
                if s.id == missing_id:
                    capability = s.capability
                    break

            reason = (
                "Cancelled (dependency failure)"
                if missing_id in self._cancelled_steps
                else "Not reached (DAG aborted)"
            )
            all_step_results.append(
                StepResult(
                    step_id=missing_id,
                    capability_name=capability,
                    status=StepStatus.CANCELLED,
                    error_detail=reason,
                )
            )

        # Step 3: Delegate to AggregatedResult.from_dag factory
        return AggregatedResult.from_dag(
            plan_id=plan.plan_id,
            step_results=all_step_results,
            compensations=compensations,
            trace_id=plan.trace_id,
            duration_ms=dag_duration_ms,
        )

    # ------------------------------------------------------------------
    # cancel_dependents -- Dependent step cancellation (2.2.4, ORCH-07)
    # ------------------------------------------------------------------

    def cancel_dependents(
        self,
        failed_step_id: str,
        plan: CommittedPlan,
    ) -> List[str]:
        """Cancel all transitive dependents of a failed step.

        Pure function (no I/O). Uses BFS through the reverse dependency
        graph to find all steps that transitively depend on failed_step_id,
        then adds them to self._cancelled_steps.

        Invariant ORCH-07: "dependent cancel on parent failure".
        Steps with NO dependency path to the failed step are INDEPENDENT
        and continue executing.

        Algorithm:
          1. Build reverse dependency map: for each step, which steps
             directly depend on it (dep -> [dependents]).
          2. BFS from failed_step_id through reverse map.
          3. All reachable step IDs (excluding failed_step_id itself)
             are added to self._cancelled_steps.

        Args:
            failed_step_id: ID of the step that failed.
            plan: CommittedPlan for dependency graph.

        Returns:
            List of step_ids that were newly cancelled (transitive closure).
        """
        # Build reverse dep map: step_id -> list of steps that depend on it
        dependents_of: Dict[str, List[str]] = {}
        for step_id, dep_list in plan.dependencies.items():
            for dep in dep_list:
                dependents_of.setdefault(dep, []).append(step_id)

        # BFS from failed_step_id
        newly_cancelled: List[str] = []
        queue: deque[str] = deque()
        queue.append(failed_step_id)
        visited: Set[str] = {failed_step_id}

        while queue:
            current = queue.popleft()
            for dependent_id in dependents_of.get(current, []):
                if dependent_id not in visited:
                    visited.add(dependent_id)
                    # Only cancel if not already cancelled
                    if dependent_id not in self._cancelled_steps:
                        self._cancelled_steps.add(dependent_id)
                        newly_cancelled.append(dependent_id)
                    queue.append(dependent_id)

        return sorted(newly_cancelled)

    # ------------------------------------------------------------------
    # _compensate -- Saga recovery (2.2.5)
    # ------------------------------------------------------------------

    async def _compensate(
        self,
        wave_results: List[WaveResult],
        plan: CommittedPlan,
    ) -> List[CompensationRecord]:
        """Execute saga compensations for side-effect steps after failure.

        When a side-effect step fails after earlier side-effect steps
        have already completed, this method executes compensations in
        REVERSE DECLARATION ORDER within the CommittedPlan (per INV-2).

        Compensation lookup chain (PROD-3):
          1. PlanStep.compensation field (Planner pre-resolved).
          2. IFabricGatewayPort.query_registry(cap_name).compensation_capability.
          3. If still null: no compensation -- log + dead-letter.

        Compensation is sequential, not concurrent (ADR-1.1.8).
        If a compensation itself fails: dead-letter the record.

        Args:
            wave_results: All wave results from execution so far.
            plan: CommittedPlan for step lookup and dependency graph.

        Returns:
            List of CompensationRecords (may be empty if no saga needed).
        """
        # Collect all step results into a lookup
        result_by_id: Dict[str, StepResult] = {}
        for wr in wave_results:
            for sr in wr.step_results:
                result_by_id[sr.step_id] = sr

        # Check if any side-effect step failed
        has_side_effect_failure = False
        for step in plan.steps:
            if step.has_side_effects:
                sr = result_by_id.get(step.id)
                if sr is not None and sr.status == StepStatus.FAILED:
                    has_side_effect_failure = True
                    break

        if not has_side_effect_failure:
            return []

        # Find completed side-effect steps that need compensation.
        # Order is REVERSE DECLARATION ORDER within the plan (INV-2).
        completed_side_effect_steps: List[PlanStep] = []
        for step in plan.steps:
            if step.has_side_effects:
                sr = result_by_id.get(step.id)
                if sr is not None and sr.status == StepStatus.COMPLETED:
                    completed_side_effect_steps.append(step)

        # Reverse to get LIFO order (last declared first compensated)
        completed_side_effect_steps.reverse()

        if not completed_side_effect_steps:
            return []

        log.info(
            "[DAGExecutor] Saga recovery: compensating %d side-effect steps "
            "in reverse declaration order",
            len(completed_side_effect_steps),
        )

        compensations: List[CompensationRecord] = []
        for step in completed_side_effect_steps:
            comp_cap = await self._resolve_compensation_capability(step)
            if comp_cap is None:
                # No compensation available -- dead-letter
                record = CompensationRecord(
                    dag_id=plan.plan_id,
                    step_id=step.id,
                    compensation_capability="NONE",
                    status="DEAD_LETTERED",
                    error_detail="No compensation capability available",
                    completed_at=time.time(),
                )
                compensations.append(record)
                log.warning(
                    "[DAGExecutor] No compensation for step %s (cap=%s) " "-- dead-lettered",
                    step.id,
                    step.capability,
                )
                continue

            record = CompensationRecord(
                dag_id=plan.plan_id,
                step_id=step.id,
                compensation_capability=comp_cap,
                compensation_params=dict(step.params) if step.params else {},
                status="PENDING",
            )

            try:
                # Execute compensation via fabric_port
                from k1.fabric.types import CapabilityRequest

                comp_request = CapabilityRequest(
                    capability_name=comp_cap,
                    params=record.compensation_params,
                    trace_id=plan.trace_id,
                )
                comp_result = await self._fabric_port.execute(comp_request)

                if comp_result.success:
                    record.status = "EXECUTED"
                    record.completed_at = time.time()
                    log.info(
                        "[DAGExecutor] Compensation executed for step %s: %s",
                        step.id,
                        comp_cap,
                    )
                else:
                    record.status = "DEAD_LETTERED"
                    record.error_detail = (
                        comp_result.error.message
                        if comp_result.error
                        else "Compensation returned failure"
                    )
                    record.completed_at = time.time()
                    log.error(
                        "[DAGExecutor] Compensation failed for step %s: %s",
                        step.id,
                        record.error_detail,
                    )
            except Exception as exc:
                record.status = "DEAD_LETTERED"
                record.error_detail = str(exc)
                record.completed_at = time.time()
                log.error(
                    "[DAGExecutor] Compensation exception for step %s: %s",
                    step.id,
                    exc,
                )

            compensations.append(record)

            # WAL write compensation record (fire-and-forget)
            try:
                await self._bridge_port.write_wal(
                    plan.plan_id,
                    "COMPENSATION",
                    {
                        "record_id": record.record_id,
                        "step_id": step.id,
                        "compensation_capability": comp_cap,
                        "status": record.status,
                    },
                    plan.trace_id,
                )
            except Exception:
                log.warning(
                    "[DAGExecutor] WAL write COMPENSATION failed",
                    exc_info=True,
                )

        return compensations

    async def _resolve_compensation_capability(
        self,
        step: PlanStep,
    ) -> Optional[str]:
        """Resolve compensation capability for a step (PROD-3 lookup chain).

        Chain:
          1. PlanStep.compensation field (Planner pre-resolved).
          2. IFabricGatewayPort.query_registry() runtime lookup.
          3. None if not found.

        Args:
            step: PlanStep that needs compensation.

        Returns:
            Compensation capability name, or None if unavailable.
        """
        # Chain 1: PlanStep.compensation
        if step.compensation:
            return step.compensation

        # Chain 2: Registry lookup
        try:
            entry = await self._fabric_port.query_registry(step.capability)
            if entry is not None and entry.compensation_capability:
                return entry.compensation_capability
        except Exception:
            log.warning(
                "[DAGExecutor] Registry lookup for compensation failed " "for %s",
                step.capability,
                exc_info=True,
            )

        # Chain 3: Not found
        return None

    # ------------------------------------------------------------------
    # recover_from_wal -- WAL recovery protocol (2.2.6)
    # ------------------------------------------------------------------

    @staticmethod
    async def recover_from_wal(
        bridge_port: IBridgeWritePort,
        dag_id: str,
    ) -> Dict[str, Any]:
        """Determine DAG resume point from WAL entries.

        Recovery protocol (6.2.4):
          - Find last WAVE_COMPLETE -> resume from wave_index + 1.
          - If STEP_COMPLETE entries after last WAVE_COMPLETE -> some
            steps completed but wave unfinished -> re-execute entire wave
            (idempotent steps assumed).
          - If no entries -> DAG never started, re-execute from scratch.

        V1 limitation: WAL writes are fire-and-forget. If K0 offline
        during DAG, WAL entries are lost and recovery is impossible.
        Acceptable for Edge-First (local execution continues; audit
        is best-effort).

        Args:
            bridge_port: IBridgeWritePort for reading WAL.
            dag_id: DAG execution identifier.

        Returns:
            Dict with recovery info:
              - status: "NO_WAL" | "RESUME" | "COMPLETED" | "RESTART"
              - resume_wave_index: int (wave to resume from, if RESUME)
              - completed_steps: list of step_ids confirmed complete
              - dag_status: last known DAG status if DAG_COMPLETE found
        """
        try:
            entries = await bridge_port.read_wal(dag_id)
        except Exception:
            log.warning(
                "[DAGExecutor] WAL read failed for dag %s",
                dag_id,
                exc_info=True,
            )
            return {
                "status": "NO_WAL",
                "resume_wave_index": 0,
                "completed_steps": [],
                "dag_status": None,
            }

        if entries is None or len(entries) == 0:
            return {
                "status": "NO_WAL",
                "resume_wave_index": 0,
                "completed_steps": [],
                "dag_status": None,
            }

        # Parse entries
        last_wave_complete_index: int = -1
        completed_steps: List[str] = []
        dag_complete_status: Optional[str] = None
        steps_after_last_wave: List[str] = []

        for entry in entries:
            entry_type = entry.get("entry_type", entry.get("type", ""))

            if entry_type == "DAG_COMPLETE":
                dag_complete_status = entry.get("payload", {}).get("status", "COMPLETED")

            elif entry_type == "WAVE_COMPLETE":
                payload = entry.get("payload", {})
                wave_idx = payload.get("wave_index", -1)
                if wave_idx > last_wave_complete_index:
                    last_wave_complete_index = wave_idx
                wave_steps = payload.get("completed_steps", [])
                completed_steps.extend(wave_steps)
                steps_after_last_wave = []  # reset

            elif entry_type == "STEP_COMPLETE":
                payload = entry.get("payload", {})
                step_id = payload.get("step_id")
                if step_id:
                    steps_after_last_wave.append(step_id)

        # Determine recovery action
        if dag_complete_status is not None:
            return {
                "status": "COMPLETED",
                "resume_wave_index": -1,
                "completed_steps": completed_steps,
                "dag_status": dag_complete_status,
            }

        if last_wave_complete_index >= 0:
            # Resume from the wave AFTER the last completed wave.
            # If there are step completions after that wave, the
            # partial wave must be re-executed (idempotent assumption).
            return {
                "status": "RESUME",
                "resume_wave_index": last_wave_complete_index + 1,
                "completed_steps": completed_steps,
                "dag_status": None,
            }

        # No wave completed, but we have PLAN_START or individual steps
        return {
            "status": "RESTART",
            "resume_wave_index": 0,
            "completed_steps": [],
            "dag_status": None,
        }

    def __repr__(self) -> str:
        return (
            f"DAGExecutor(guards={len(self._guards)}, "
            f"interrupt={self.interrupt_flag}, "
            f"merged={len(self.merged_results)}, "
            f"cancelled={len(self._cancelled_steps)})"
        )
