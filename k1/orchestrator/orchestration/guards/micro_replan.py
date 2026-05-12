"""
k1.orchestrator.orchestration.guards.micro_replan -- ORCH-13.

Post-wave guard that evaluates discoveries from completed steps and
triggers a synchronous micro-replan when new information overlaps
remaining step parameters.

Guard pipeline position: G8 (post-wave).

Design:
  - Stateful: tracks replans_used (max 1 per DAG) and accumulated
    StepResults across waves.
  - Calls planner.micro_replan() synchronously with 10s timeout.
  - On success: returns CONTINUE with new_plan in metadata.
    DAGExecutor reads metadata["new_plan"] and replaces remaining waves.
  - On timeout/None: returns CONTINUE (continue original plan).
  - On no overlap or budget exhausted: returns CONTINUE.

Discovery extraction:
  Discoveries are extracted from CapabilityResult.data["discoveries"]
  (list of dicts with field, value, source_step_id keys).

Overlap heuristic (V1, per ADR-1.1.11 Q8):
  Exact match between discovery.field and any param name in any
  remaining step's params dict. Substring match also supported
  (field is substring of param name or vice versa).

Key contract (from WB S10.6):
  - micro_replan() is SYNCHRONOUS (10s timeout, PROTOCOL-3)
  - Returns Optional[CommittedPlan] directly (no event bus)
  - Max 1 per DAG (ORCH-13)
  - On failure: continue original plan (graceful degradation)

References:
  - orchestrator-implementation-plan.md Issue 3.2.5
  - Schema Whiteboard Section 10.6 (MicroReplan round-trip protocol)
  - M3-constraint-guards-worktickets.md WT-3.2.5

Exports:
  MicroReplanCheckpoint
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from k1.orchestrator.ports.planner_port import IPlannerPort
from k1.orchestrator.types import (
    Discovery,
    GuardAction,
    GuardDecision,
    MicroReplanRequest,
    PlanStep,
    ProcessingContext,
    StepResult,
    WaveResult,
)

from .base import DAGGuard

logger = logging.getLogger(__name__)

# Guard identity constant
_GUARD_NAME = "MicroReplanCheckpoint"

# Timeout for planner.micro_replan() per PROTOCOL-3
_MICRO_REPLAN_TIMEOUT_S = 10.0


# ------------------------------------------------------------------
# Discovery extraction
# ------------------------------------------------------------------


def _extract_discoveries(wave_result: WaveResult) -> List[Discovery]:
    """Extract Discovery objects from wave step results.

    Discoveries are stored in CapabilityResult.data["discoveries"]
    as a list of dicts: [{"field": ..., "value": ..., "source_step_id": ...}].

    Args:
        wave_result: Completed wave results.

    Returns:
        List of Discovery objects found across all step results.
    """
    discoveries: List[Discovery] = []
    for sr in wave_result.step_results:
        if sr.result is None or sr.result.data is None:
            continue
        raw_discoveries = sr.result.data.get("discoveries")
        if not isinstance(raw_discoveries, list):
            continue
        for raw in raw_discoveries:
            if not isinstance(raw, dict):
                continue
            field = raw.get("field")
            if not field:
                continue
            discoveries.append(
                Discovery(
                    field=str(field),
                    value=raw.get("value"),
                    source_step_id=raw.get("source_step_id", sr.step_id),
                )
            )
    return discoveries


# ------------------------------------------------------------------
# Overlap heuristic
# ------------------------------------------------------------------


def _check_param_overlap(
    discoveries: List[Discovery],
    remaining_steps: List[PlanStep],
) -> bool:
    """Check if any discovery field overlaps a remaining step param name.

    V1 heuristic (per ADR-1.1.11 Q8):
      - Exact match: discovery.field == param_name
      - Substring match: discovery.field in param_name or param_name in discovery.field

    Args:
        discoveries: Discoveries from the completed wave.
        remaining_steps: Steps not yet executed in future waves.

    Returns:
        True if any overlap found, False otherwise.
    """
    if not discoveries or not remaining_steps:
        return False

    discovery_fields = {d.field.lower() for d in discoveries}

    for step in remaining_steps:
        for param_name in step.params:
            param_lower = param_name.lower()
            for field in discovery_fields:
                # Exact match or substring match
                if field == param_lower or field in param_lower or param_lower in field:
                    logger.debug(
                        "[%s] Overlap found: discovery field '%s' matches param '%s' in step '%s'",
                        _GUARD_NAME,
                        field,
                        param_name,
                        step.id,
                    )
                    return True
    return False


# ------------------------------------------------------------------
# Guard implementation
# ------------------------------------------------------------------


class MicroReplanCheckpoint(DAGGuard):
    """Post-wave guard for mid-execution micro-replan (ORCH-13).

    Evaluates discoveries from completed steps and triggers a
    synchronous micro-replan when new information overlaps remaining
    step parameters.

    Constructor:
      planner: IPlannerPort for micro_replan() calls.
      max_replans: Maximum replans per DAG (default 1, V1 limit).

    State (reset per DAG via reset()):
      _replans_used: Number of replans already performed.
      _completed_results: Accumulated StepResults from all waves.

    Decision flow:
      1. Collect discoveries from wave results
      2. No discoveries -> CONTINUE (nothing to trigger replan)
      3. Check overlap with remaining step params
      4. No overlap -> CONTINUE
      5. max_replans reached -> CONTINUE (budget exhausted)
      6. Build MicroReplanRequest, call planner with 10s timeout
      7. Success -> CONTINUE with metadata["new_plan"]
      8. Timeout/None -> CONTINUE (continue original plan)
    """

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
        """Reset state for a new DAG execution.

        Called by DAGExecutor at the start of execute() to ensure
        clean state for each DAG run.
        """
        self._replans_used = 0
        self._completed_results = {}

    @property
    def replans_used(self) -> int:
        """Number of replans already performed in this DAG."""
        return self._replans_used

    async def after_wave(
        self,
        wave_result: WaveResult,
        ctx: ProcessingContext,
        remaining_steps: Optional[List[Any]] = None,
        plan_id: Optional[str] = None,
    ) -> GuardDecision:
        """Evaluate discoveries and trigger micro-replan if warranted.

        Args:
            wave_result: Completed wave results containing step discoveries.
            ctx: ProcessingContext for trace correlation.
            remaining_steps: PlanSteps not yet executed (from future waves).
            plan_id: CommittedPlan.plan_id for MicroReplanRequest.

        Returns:
            GuardDecision with action CONTINUE. If replan triggered:
            metadata["new_plan"] contains the replacement CommittedPlan.
        """
        # Accumulate step results from this wave
        for sr in wave_result.step_results:
            self._completed_results[sr.step_id] = sr

        # 1. Collect discoveries from wave results
        discoveries = _extract_discoveries(wave_result)

        if not discoveries:
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason="No discoveries in wave results",
            )

        # 2. Check remaining steps available
        effective_remaining: List[PlanStep] = []
        if remaining_steps:
            for step in remaining_steps:
                if isinstance(step, PlanStep):
                    effective_remaining.append(step)

        if not effective_remaining:
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason="No remaining steps to replan",
            )

        # 3. Check overlap heuristic
        if not _check_param_overlap(discoveries, effective_remaining):
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason=f"No param overlap for {len(discoveries)} discoveries",
            )

        # 4. Check replan budget (M5.4.1: shared ctx flag covers any
        # prior micro/failure replan in the same DAG run).
        if getattr(ctx, "micro_replan_done", False) or self._replans_used >= self._max_replans:
            logger.info(
                "[%s] Replan budget exhausted (%d/%d, ctx.done=%s) -- continuing original plan",
                _GUARD_NAME,
                self._replans_used,
                self._max_replans,
                getattr(ctx, "micro_replan_done", False),
            )
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason=f"Replan budget exhausted ({self._replans_used}/{self._max_replans})",
            )

        # 5. Build MicroReplanRequest
        effective_plan_id = plan_id or ctx.dag_id or "unknown"
        request = MicroReplanRequest(
            original_plan_id=effective_plan_id,
            completed_results=dict(self._completed_results),
            remaining_steps=effective_remaining,
            trace_id=ctx.trace_id,
            discoveries=discoveries,
        )

        # 6. Call planner with timeout
        logger.info(
            "[%s] Triggering micro-replan: %d discoveries, %d remaining steps, plan '%s'",
            _GUARD_NAME,
            len(discoveries),
            len(effective_remaining),
            effective_plan_id,
        )

        try:
            new_plan = await asyncio.wait_for(
                self._planner.micro_replan(request),
                timeout=_MICRO_REPLAN_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[%s] Planner micro_replan timed out after %.1fs -- continuing original plan",
                _GUARD_NAME,
                _MICRO_REPLAN_TIMEOUT_S,
            )
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason=f"Planner micro_replan timed out after {_MICRO_REPLAN_TIMEOUT_S}s",
            )
        except Exception as exc:
            logger.warning(
                "[%s] Planner micro_replan failed: %s -- continuing original plan",
                _GUARD_NAME,
                exc,
            )
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason=f"Planner micro_replan failed: {exc}",
            )

        # 7. Planner returned None -> no replan
        if new_plan is None:
            logger.info(
                "[%s] Planner returned None -- continuing original plan",
                _GUARD_NAME,
            )
            return GuardDecision(
                guard_name=_GUARD_NAME,
                action=GuardAction.CONTINUE,
                reason="Planner returned None for micro-replan",
            )

        # 8. Success! Increment budget and return new plan via metadata
        self._replans_used += 1
        # M5.4.1: mark shared flag so FailureReplanCheckpoint also honors
        # the budget for the rest of this DAG run.
        try:
            ctx.micro_replan_done = True
        except Exception:
            pass
        logger.info(
            "[%s] Micro-replan succeeded: %d new steps (replans: %d/%d)",
            _GUARD_NAME,
            len(new_plan.steps),
            self._replans_used,
            self._max_replans,
        )

        return GuardDecision(
            guard_name=_GUARD_NAME,
            action=GuardAction.CONTINUE,
            reason=f"Micro-replan succeeded with {len(new_plan.steps)} new steps",
            metadata={"new_plan": new_plan},
        )

    def __repr__(self) -> str:
        return (
            f"MicroReplanCheckpoint("
            f"max_replans={self._max_replans}, "
            f"replans_used={self._replans_used})"
        )
