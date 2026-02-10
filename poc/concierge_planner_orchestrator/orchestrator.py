"""
Orchestrator (No LLM -- Blind DAG Executor)
=============================================

Process 3 in the pipeline. Receives a CommittedPlan and:
  1. Converts PlanSteps to CapabilityRequests
  2. Wires _depends_on for DAG execution
  3. Resolves $-references via ParamResolver between waves
  4. Calls Fabric.execute / execute_batch(strategy=DAG)
  5. Aggregates results

The Orchestrator has NO LLM. It is a mechanical execution engine.
It does not think. It follows the plan step by step.

Wave-by-wave execution (when $-refs present):
  Steps are grouped into topological waves based on depends_on.
  After each wave completes, ParamResolver resolves $-references
  in the next wave's params and capability fields using completed
  results. Fabric NEVER sees $-references.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any, Dict, List

from k1.fabric.fabric import BatchStrategy, CapabilityFabric
from k1.fabric.types import CapabilityRequest, CapabilityResult
from k1.orchestrator.orchestration.param_resolver import ParamResolver

from .types import CommittedPlan, OrchestratorResult, PlanStep, StepResult, TaskEnvelope

logger = logging.getLogger(__name__)


def _has_dollar_refs(steps: List[PlanStep]) -> bool:
    """Check if any step has $-references in capability or params."""
    for step in steps:
        if step.capability_name.startswith("$"):
            return True
        for value in step.params.values():
            if isinstance(value, str) and value.startswith("$"):
                return True
    return False


def _build_waves(steps: List[PlanStep]) -> List[List[PlanStep]]:
    """
    Topological sort into execution waves (Kahn's algorithm).

    Wave 0 = steps with no dependencies.
    Wave N = steps whose deps are all in waves 0..N-1.
    """
    step_map: Dict[str, PlanStep] = {s.step_id: s for s in steps}
    in_degree: Dict[str, int] = {s.step_id: 0 for s in steps}
    dependents: Dict[str, List[str]] = defaultdict(list)

    for step in steps:
        for dep in step.depends_on:
            if dep in step_map:
                in_degree[step.step_id] += 1
                dependents[dep].append(step.step_id)

    waves: List[List[PlanStep]] = []
    queue: deque[str] = deque(sid for sid, deg in in_degree.items() if deg == 0)

    while queue:
        wave_ids = list(queue)
        queue.clear()
        wave = [step_map[sid] for sid in wave_ids]
        waves.append(wave)

        for sid in wave_ids:
            for dep_id in dependents[sid]:
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)

    return waves


class Orchestrator:
    """
    Blind DAG executor.

    NO LLM. Receives a CommittedPlan and mechanically executes it
    through Fabric using topological wave execution.

    When steps contain $-references (dynamic params/capabilities),
    execution switches to wave-by-wave mode with ParamResolver
    resolving references between waves.

    For MEDIUM tier: Executes 1-2 Fabric calls directly (no planner).
    For HIGH tier: Delegates to Planner first, then executes the DAG.
    """

    def __init__(self, fabric: CapabilityFabric) -> None:
        self._fabric = fabric
        self._resolver = ParamResolver()  # No registry check in POC mode

    async def execute_plan(
        self,
        plan: CommittedPlan,
    ) -> OrchestratorResult:
        """
        Execute a CommittedPlan via Fabric.

        Two modes:
          1. Batch mode (no $-refs): All requests sent via execute_batch(DAG).
          2. Wave mode ($-refs present): Topological waves with ParamResolver
             resolving $-references between waves.

        Args:
            plan: The committed plan from the Planner.

        Returns:
            OrchestratorResult with all step results.
        """
        if not plan.steps:
            logger.warning("[Orchestrator] Empty plan, nothing to execute")
            return OrchestratorResult(
                plan_id=plan.plan_id,
                success=False,
                step_results=[],
                trace_id=plan.trace_id,
            )

        logger.info(
            "[Orchestrator] Executing plan '%s' with %d steps",
            plan.plan_id[:8],
            len(plan.steps),
        )

        if _has_dollar_refs(plan.steps):
            return await self._execute_wave_by_wave(plan)
        else:
            return await self._execute_batch(plan)

    # ------------------------------------------------------------------
    # Batch mode (original path -- no $-refs)
    # ------------------------------------------------------------------

    async def _execute_batch(
        self,
        plan: CommittedPlan,
    ) -> OrchestratorResult:
        """Execute all steps via single execute_batch(DAG) call."""
        start_time = time.monotonic()

        step_to_request_id: Dict[str, str] = {}
        requests: List[CapabilityRequest] = []

        for step in plan.steps:
            request = CapabilityRequest(
                capability_name=step.capability_name,
                params={
                    **step.params,
                    "_depends_on": [
                        step_to_request_id[dep]
                        for dep in step.depends_on
                        if dep in step_to_request_id
                    ],
                },
                tier="HIGH",
                caller="orchestrator",
                safety_band="AMBER",
                trace_id=plan.trace_id,
                plan_id=plan.plan_id,
                step_id=step.step_id,
            )
            step_to_request_id[step.step_id] = request.request_id
            requests.append(request)

        logger.info(
            "[Orchestrator] Batch mode: sending %d requests (DAG strategy)",
            len(requests),
        )

        results = await self._fabric.execute_batch(
            requests=requests,
            strategy=BatchStrategy.DAG,
        )

        return self._aggregate_results(plan, requests, results, step_to_request_id, start_time)

    # ------------------------------------------------------------------
    # Wave-by-wave mode ($-refs present)
    # ------------------------------------------------------------------

    async def _execute_wave_by_wave(
        self,
        plan: CommittedPlan,
    ) -> OrchestratorResult:
        """Execute steps wave-by-wave, resolving $-refs between waves."""
        start_time = time.monotonic()
        waves = _build_waves(plan.steps)

        logger.info(
            "[Orchestrator] Wave mode: %d waves for %d steps",
            len(waves),
            len(plan.steps),
        )

        # Accumulated results: step_id -> CapabilityResult
        completed_results: Dict[str, CapabilityResult] = {}
        all_step_results: List[StepResult] = []
        step_capabilities = {s.step_id: s.capability_name for s in plan.steps}

        for wave_idx, wave in enumerate(waves):
            logger.info(
                "[Orchestrator] Wave %d: %d steps [%s]",
                wave_idx,
                len(wave),
                ", ".join(s.step_id for s in wave),
            )

            requests: List[CapabilityRequest] = []
            step_to_request_id: Dict[str, str] = {}

            for step in wave:
                # Resolve $-refs using completed results
                step_dict = {
                    "step_id": step.step_id,
                    "capability": step.capability_name,
                    "params": dict(step.params),
                    "depends_on": list(step.depends_on),
                }

                try:
                    resolved = self._resolver.resolve_step(step_dict, completed_results)
                except Exception as e:
                    logger.error(
                        "[Orchestrator] ParamResolver failed for step %s: %s",
                        step.step_id,
                        e,
                    )
                    all_step_results.append(
                        StepResult(
                            step_id=step.step_id,
                            capability_name=step.capability_name,
                            success=False,
                            error=f"ParamResolver: {e}",
                        )
                    )
                    continue

                cap_name = resolved.get("capability", step.capability_name)
                params = resolved.get("params", step.params)

                request = CapabilityRequest(
                    capability_name=cap_name,
                    params=params,
                    tier="HIGH",
                    caller="orchestrator",
                    safety_band="AMBER",
                    trace_id=plan.trace_id,
                    plan_id=plan.plan_id,
                    step_id=step.step_id,
                )
                step_to_request_id[step.step_id] = request.request_id
                requests.append(request)

            if not requests:
                continue

            # Execute this wave
            if len(requests) == 1:
                results = [await self._fabric.execute(requests[0])]
            else:
                results = await self._fabric.execute_batch(
                    requests=requests,
                    strategy=BatchStrategy.DAG,
                )

            # Collect results
            request_id_to_step = {rid: sid for sid, rid in step_to_request_id.items()}

            for req, result in zip(requests, results):
                step_id = request_id_to_step.get(req.request_id, "unknown")
                completed_results[step_id] = result

                sr = StepResult(
                    step_id=step_id,
                    capability_name=step_capabilities.get(step_id, req.capability_name),
                    success=result.success,
                    data=result.data if result.success else None,
                    error=result.error.message if result.error else None,
                    duration_ms=result.duration_ms,
                )
                all_step_results.append(sr)

                status = "OK" if result.success else "FAILED"
                logger.info(
                    "[Orchestrator] Step %s (%s): %s [%dms]",
                    step_id,
                    step_capabilities.get(step_id, "?"),
                    status,
                    result.duration_ms,
                )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        all_success = all(sr.success for sr in all_step_results)

        logger.info(
            "[Orchestrator] Plan execution %s in %dms (%d/%d steps succeeded)",
            "COMPLETE" if all_success else "PARTIAL",
            elapsed_ms,
            len([s for s in all_step_results if s.success]),
            len(all_step_results),
        )

        return OrchestratorResult(
            plan_id=plan.plan_id,
            success=all_success,
            step_results=all_step_results,
            total_duration_ms=elapsed_ms,
            trace_id=plan.trace_id,
        )

    # ------------------------------------------------------------------
    # Shared result aggregation
    # ------------------------------------------------------------------

    def _aggregate_results(
        self,
        plan: CommittedPlan,
        requests: List[CapabilityRequest],
        results: List[CapabilityResult],
        step_to_request_id: Dict[str, str],
        start_time: float,
    ) -> OrchestratorResult:
        """Map Fabric results back to StepResults."""
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        step_results: List[StepResult] = []

        request_id_to_step = {rid: sid for sid, rid in step_to_request_id.items()}
        step_capabilities = {s.step_id: s.capability_name for s in plan.steps}

        for req, result in zip(requests, results):
            step_id = request_id_to_step.get(req.request_id, "unknown")
            sr = StepResult(
                step_id=step_id,
                capability_name=step_capabilities.get(step_id, req.capability_name),
                success=result.success,
                data=result.data if result.success else None,
                error=result.error.message if result.error else None,
                duration_ms=result.duration_ms,
            )
            step_results.append(sr)

            status = "OK" if result.success else "FAILED"
            logger.info(
                "[Orchestrator] Step %s (%s): %s [%dms]",
                step_id,
                step_capabilities.get(step_id, "?"),
                status,
                result.duration_ms,
            )

        all_success = all(sr.success for sr in step_results)

        logger.info(
            "[Orchestrator] Plan execution %s in %dms (%d/%d steps succeeded)",
            "COMPLETE" if all_success else "PARTIAL",
            elapsed_ms,
            len([s for s in step_results if s.success]),
            len(step_results),
        )

        return OrchestratorResult(
            plan_id=plan.plan_id,
            success=all_success,
            step_results=step_results,
            total_duration_ms=elapsed_ms,
            trace_id=plan.trace_id,
        )

    async def execute_direct(
        self,
        envelope: TaskEnvelope,
        capability_name: str,
        params: Dict[str, Any],
    ) -> OrchestratorResult:
        """
        Direct execution for MEDIUM tier (no planner).

        Concierge already knows WHAT to do. Orchestrator just
        coordinates a single Fabric call.

        Args:
            envelope: The task envelope from Concierge.
            capability_name: The capability to execute.
            params: Parameters for the capability.

        Returns:
            OrchestratorResult with single step result.
        """
        logger.info(
            "[Orchestrator] Direct execution: %s",
            capability_name,
        )

        start_time = time.monotonic()

        request = CapabilityRequest(
            capability_name=capability_name,
            params=params,
            tier=envelope.tier.value,
            caller="orchestrator",
            safety_band="AMBER",
            trace_id=envelope.trace_id,
        )

        result = await self._fabric.execute(request)
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        sr = StepResult(
            step_id="direct",
            capability_name=capability_name,
            success=result.success,
            data=result.data if result.success else None,
            error=result.error.message if result.error else None,
            duration_ms=result.duration_ms,
        )

        return OrchestratorResult(
            plan_id="direct",
            success=result.success,
            step_results=[sr],
            total_duration_ms=elapsed_ms,
            trace_id=envelope.trace_id,
        )
