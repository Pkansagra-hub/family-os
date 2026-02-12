"""
k1.orchestrator.orchestration.guards.base -- DAGGuard abstract base class.

Provides the DAGGuard ABC that all DAG execution guards inherit from.
Defines default no-op implementations for all three lifecycle hooks.

Guard lifecycle hooks:
  before_wave -- evaluated before steps in a wave are dispatched.
  after_step  -- evaluated after each individual step completes.
  after_wave  -- evaluated after all steps in a wave complete.

Default implementations return CONTINUE (no-op pass-through).
Subclasses override only the hooks they need.

Exports:
  DAGGuard
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from k1.orchestrator.types import (
        PlanStep,
        ProcessingContext,
        StepResult,
        Wave,
        WaveResult,
    )

from k1.orchestrator.types import GuardAction, GuardDecision


class DAGGuard(ABC):
    """Abstract base class for DAG execution guards.

    Provides three lifecycle hooks that DAGExecutor calls at the
    appropriate phase. Default implementations return CONTINUE
    (no-op pass-through). Subclasses override only the hooks they need.

    Hook phases:
      before_wave -- evaluated before dispatching steps in a wave.
                     ConditionalEdgeEvaluator uses this to skip steps.
      after_step  -- evaluated after each step completes.
                     OutputSchemaGuard uses this to trigger schema retry.
      after_wave  -- evaluated after all steps in a wave complete.
                     MicroReplanCheckpoint, ExecutionMonitor use this.

    Return type: GuardDecision with GuardAction indicating the decision.
    Pipeline short-circuits on HARD_STOP.
    """

    async def before_wave(
        self,
        wave: Wave,
        ctx: ProcessingContext,
        merged_results: Optional[Dict[str, Any]] = None,
    ) -> List[GuardDecision]:
        """Evaluate guard before wave dispatch.

        Args:
            wave: The wave about to be dispatched.
            ctx: Processing context with trace/request correlation.
            merged_results: step_id -> CapabilityResult from prior waves.
                            Provided by DAGExecutor. None when not available.

        Returns a list of GuardDecisions (one per step to skip/modify).
        Default: empty list (all steps proceed).
        """
        return []

    async def after_step(
        self,
        step: PlanStep,
        result: StepResult,
        ctx: ProcessingContext,
    ) -> GuardDecision:
        """Evaluate guard after a single step completes.

        Returns a GuardDecision controlling next action for the step.
        Default: CONTINUE (proceed normally).
        """
        return GuardDecision(
            guard_name=self.__class__.__name__,
            action=GuardAction.CONTINUE,
            reason="default pass-through",
        )

    async def after_wave(
        self,
        wave_result: WaveResult,
        ctx: ProcessingContext,
        remaining_steps: Optional[List[Any]] = None,
        plan_id: Optional[str] = None,
    ) -> GuardDecision:
        """Evaluate guard after all steps in a wave complete.

        Args:
            wave_result: Aggregated results for the completed wave.
            ctx: Processing context with trace/request correlation.
            remaining_steps: PlanSteps not yet executed (from future waves).
                             Provided by DAGExecutor. None when not available.
            plan_id: The CommittedPlan.plan_id for the current DAG.
                     Provided by DAGExecutor. None when not available.

        Returns a GuardDecision controlling DAG continuation.
        Default: CONTINUE (proceed to next wave).
        """
        return GuardDecision(
            guard_name=self.__class__.__name__,
            action=GuardAction.CONTINUE,
            reason="default pass-through",
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
