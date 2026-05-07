"""
k1.orchestrator.orchestration.guards.failure_replan -- M16.E2.I2.

Post-wave guard that triggers a synchronous micro-replan when a step
in the just-completed wave failed AND there are remaining steps that
could be amended to recover the failed branch.

Guard pipeline position: post-wave, evaluated AFTER MicroReplanCheckpoint
so a discovery-driven replan still has priority. This keeps existing
ORCH-13 semantics intact while adding the recovery path required by
M16.E2.I2 (FRD: "DAG node failure → planner amend").

Design:
  - Stateful: tracks ``replans_used`` (max 1 per DAG by default,
    matching ``MicroReplanCheckpoint``) and accumulated ``StepResult``
    entries across waves so the planner sees full context.
  - Calls ``planner.micro_replan()`` with a 10s timeout (PROTOCOL-3).
  - On success: returns ``CONTINUE`` with the amended plan in
    ``metadata["new_plan"]``. DAGExecutor consumption of that key is
    a separate (downstream) milestone — see I3 plan-swap follow-up.
  - On timeout / None / exception: returns ``CONTINUE`` so the DAG
    continues with the already-cancelled-dependents view (graceful
    degradation, never escalate to HARD_STOP from this guard).
  - On budget exhausted: returns ``CONTINUE``.

Trigger contract:
  - ``after_wave`` is invoked once per wave by ``DAGExecutor``.
  - Failure is detected via ``StepResult.status == StepStatus.FAILED``.
  - Only the FIRST FAILED step in the wave is treated as the failure
    context for the replan request (V1 keeps it simple — multi-failure
    waves still cancel dependents per ORCH-07 and emit
    ``ORCH_DAG_NODE_FAILED`` per step from the executor).

Why a separate guard (not folding into MicroReplanCheckpoint):
  - Discovery-driven replan and failure-driven replan have different
    triggers and budgets in the long run.
  - Keeping them split lets us evolve the failure budget independently
    (e.g. 1 micro-replan + N failure replans) and lets tests target the
    failure path without the discovery heuristic mocked out.

Exports:
  FailureReplanCheckpoint
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from k1.orchestrator.ports.planner_port import IPlannerPort
from k1.orchestrator.types import (
    FailureContext,
    GuardAction,
    GuardDecision,
    MicroReplanRequest,
    PlanStep,
    ProcessingContext,
    StepResult,
    StepStatus,
    WaveResult,
)

from .base import DAGGuard

logger = logging.getLogger(__name__)

_GUARD_NAME = "FailureReplanCheckpoint"
_REPLAN_TIMEOUT_S = 10.0


class FailureReplanCheckpoint(DAGGuard):
    """Post-wave guard: amend plan when a step fails (M16.E2.I2)."""

    def __init__(
        self,
        planner: IPlannerPort,
        max_replans: int = 1,
    ) -> None:
        self._planner = planner
        self._max_replans = max_replans
        self._replans_used: int = 0
        self._completed_results: Dict[str, StepResult] = {}

    def reset(self) -> None:
        """Reset state for a new DAG execution."""
        self._replans_used = 0
        self._completed_results = {}

    @property
    def replans_used(self) -> int:
        return self._replans_used

    async def after_wave(
        self,
        wave_result: WaveResult,
        ctx: ProcessingContext,
        remaining_steps: Optional[List[Any]] = None,
        plan_id: Optional[str] = None,
    ) -> GuardDecision:
        """Evaluate wave failures and trigger a planner amend if warranted."""
        # Accumulate every step result (success + failure) so the
        # planner can see the full execution history.
        for sr in wave_result.step_results:
            self._completed_results[sr.step_id] = sr

        # 1. Find first failed step (V1 single-failure trigger).
        failed_step: Optional[StepResult] = next(
            (sr for sr in wave_result.step_results if sr.status == StepStatus.FAILED),
            None,
        )
        if failed_step is None:
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason="No failed steps in wave",
            )

        # 2. Need remaining steps to amend.
        effective_remaining: List[PlanStep] = []
        if remaining_steps:
            for step in remaining_steps:
                if isinstance(step, PlanStep):
                    effective_remaining.append(step)

        if not effective_remaining:
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason="No remaining steps to amend",
            )

        # 3. Replan budget gate.
        if self._replans_used >= self._max_replans:
            logger.info(
                "[%s] Replan budget exhausted (%d/%d) -- continuing",
                _GUARD_NAME,
                self._replans_used,
                self._max_replans,
            )
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason=(f"Replan budget exhausted " f"({self._replans_used}/{self._max_replans})"),
            )

        # 4. Build failure-driven MicroReplanRequest.
        effective_plan_id = plan_id or ctx.dag_id or "unknown"
        partial_payload: Optional[Dict[str, Any]] = None
        if failed_step.result is not None and failed_step.result.data is not None:
            try:
                partial_payload = dict(failed_step.result.data)
            except Exception:
                partial_payload = None

        failure_ctx = FailureContext(
            step_id=failed_step.step_id,
            error_code="STEP_FAILED",
            error_message=failed_step.error_detail or "step failed",
            partial_result=partial_payload,
        )

        request = MicroReplanRequest(
            original_plan_id=effective_plan_id,
            completed_results=dict(self._completed_results),
            remaining_steps=effective_remaining,
            trace_id=ctx.trace_id,
            failure_context=failure_ctx,
        )

        logger.info(
            "[%s] Triggering failure-replan: failed_step=%s, " "remaining=%d, plan=%s",
            _GUARD_NAME,
            failed_step.step_id,
            len(effective_remaining),
            effective_plan_id,
        )

        # 5. Call planner with PROTOCOL-3 timeout.
        try:
            new_plan = await asyncio.wait_for(
                self._planner.micro_replan(request),
                timeout=_REPLAN_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[%s] Planner micro_replan timed out after %.1fs",
                _GUARD_NAME,
                _REPLAN_TIMEOUT_S,
            )
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason=(f"Planner micro_replan timed out " f"after {_REPLAN_TIMEOUT_S}s"),
            )
        except Exception as exc:  # noqa: BLE001 -- guard never escalates
            logger.warning(
                "[%s] Planner micro_replan failed: %s",
                _GUARD_NAME,
                exc,
            )
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason=f"Planner micro_replan failed: {exc}",
            )

        if new_plan is None:
            logger.info(
                "[%s] Planner returned None -- no amend",
                _GUARD_NAME,
            )
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason="Planner returned None for failure-replan",
            )

        # 6. Success — surface amended plan to executor via metadata.
        self._replans_used += 1
        logger.info(
            "[%s] Failure-replan succeeded: %d new steps " "(replans=%d/%d)",
            _GUARD_NAME,
            len(new_plan.steps),
            self._replans_used,
            self._max_replans,
        )
        return GuardDecision(
            guard_name=_GUARD_NAME,
            action=GuardAction.CONTINUE,
            reason=(f"Failure-replan succeeded with {len(new_plan.steps)} new steps"),
            metadata={"new_plan": new_plan, "amended_for_step": failed_step.step_id},
        )

    def __repr__(self) -> str:
        return (
            f"FailureReplanCheckpoint("
            f"max_replans={self._max_replans}, "
            f"replans_used={self._replans_used})"
        )
