"""
R5 Dream Explorer Phase — Dream-Like Exploration (REM).

This phase implements the R5 dream-like exploration algorithms that run
during "REM sleep" consolidation cycles. It generates counterfactuals,
forward simulations, insights, and motor rehearsal patterns.

References:
- M8_EXECUTION.md Issue 8.1.1: R5 execution mode control
- M8_EXECUTION.md Issue 8.1.2: R5 skip conditions
- M8_EXECUTION.md Issue 8.1.3: M22 DreamExplorer scaffold
- Dossier §4.6: R5 — Dream-Like Exploration (REM)
- Dossier §4.6.0: MVP Strategy
- Dossier §7.4.5: M22 — DreamExplorer

Algorithms (implemented in later issues):
- CPN: Counterfactual Thinking (Issue 8.1.4)
- TPN-MCTS: Forward Simulation (Issue 8.1.5, 8.1.6)
- SPC-UQ: Episodic Simulation (Issue 8.1.8)
- BGT-SM: Insight Generation (Issue 8.1.9, 8.1.10)
- TDL-HCO: Motor Rehearsal (Issue 8.1.11)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple

from k0.pipelines.p03.observability import P03Error
from k0.pipelines.p03.phase_interface import P03PhaseResult
from k0.pipelines.p03.r5_config import R5Config
from k0.pipelines.p03.runner_contract import P03PhaseId

if TYPE_CHECKING:
    from k0.modules.consolidation.dream.intent_signals import IntentSignal
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.phase_interface import P03RunnerContext
    from k0.pipelines.p03.phase_outputs import (
        CounterfactualScenario,
        Insight,
        ProspectiveMemory,
        RoutineOptimization,
    )

logger = logging.getLogger(__name__)


# =============================================================================
# SKIP REASONS (Issue 8.1.2)
# =============================================================================


class R5SkipReason:
    """Skip reasons for R5 phase."""

    DISABLED = "r5_mode_disabled"
    BACKLOG_EXCEEDED = "r5_backlog_exceeded"
    TIME_WINDOW_EXCEEDED = "r5_time_window_exceeded"
    NO_ELIGIBLE_PATTERNS = "r5_no_eligible_patterns"


# =============================================================================
# R5 PHASE OUTPUT CONTAINER
# =============================================================================


@dataclass
class R5PhaseOutputs:
    """
    Container for R5 phase outputs.

    These outputs are staged in envelope.phases and flow to R6 for
    assembly into staged writes.

    Attributes:
        insights: BGT-SM generated insights
        counterfactuals: CPN generated counterfactual scenarios
        routine_optimizations: TDL-HCO motor rehearsal results
        prospective_memories: SPC-UQ prospective memory predictions
        intent_signals: Intent signals for layer routing (GAP-001)
        mcts_decisions_count: Number of MCTS decisions evaluated
        compute_seconds_saved: Compute time saved by skipping (for metrics)
    """

    insights: List["Insight"]
    counterfactuals: List["CounterfactualScenario"]
    routine_optimizations: List["RoutineOptimization"]
    prospective_memories: List["ProspectiveMemory"]
    intent_signals: List["IntentSignal"] = field(default_factory=list)
    mcts_decisions_count: int = 0
    compute_seconds_saved: float = 0.0


# =============================================================================
# R5 DREAM EXPLORER PHASE
# =============================================================================


class R5DreamExplorer:
    """
    R5 Dream Explorer Phase — Dream-Like Exploration.

    Executes the R5 "REM sleep" algorithms:
    1. CPN — Counterfactual Perturbation Network
    2. TPN-MCTS — Temporal Planning Network with MCTS
    3. SPC-UQ — Sparse Predictive Coding with Uncertainty Quantification
    4. BGT-SM — Bisociative Graph Traversal for Semantic Memory
    5. TDL-HCO — Temporal Difference Learning for Habit/Cognitive Optimization

    This is a stub implementation for Issue 8.1.1 that handles mode control.
    Algorithm implementations are added in Issues 8.1.4-8.1.11.
    """

    PHASE_ID = P03PhaseId.R5_DREAM

    def __init__(self, config: Optional[R5Config] = None):
        """
        Initialize R5 phase with configuration.

        Args:
            config: R5 configuration (uses defaults if None)
        """
        self.config = config or R5Config()
        self._logger = logger

    @property
    def phase_id(self) -> P03PhaseId:
        """Return the phase identifier."""
        return self.PHASE_ID

    async def run(
        self,
        envelope: "P03BatchEnvelope",
        ctx: "P03RunnerContext",
    ) -> P03PhaseResult:
        """
        Execute R5 dream exploration.

        Flow:
        1. Check skip conditions (mode, backlog, time window)
        2. If skipping, record metrics and return SKIPPED
        3. Execute dream algorithms (CPN, MCTS, SPC-UQ, BGT-SM, TDL-HCO)
        4. Stage outputs in envelope.phases
        5. If shadow mode, discard outputs but keep metrics
        6. Return DONE

        Args:
            envelope: P03 batch envelope with context and phase outputs
            ctx: Runner context with syscalls, logger, config

        Returns:
            P03PhaseResult with status, duration, and any errors
        """
        start_ms = int(time.time() * 1000)

        # Check skip conditions first
        should_skip, skip_reason = self.should_skip(envelope, ctx)
        if should_skip:
            duration_ms = int(time.time() * 1000) - start_ms

            # Record skip in envelope
            envelope.phases.r5_skipped = True
            envelope.phases.r5_skip_reason = skip_reason

            # Emit skip metrics
            self._emit_skip_metrics(envelope, ctx, skip_reason)

            self._logger.info(
                "R5 phase skipped",
                extra={
                    "cycle_id": envelope.context.cycle_id,
                    "skip_reason": skip_reason,
                    "duration_ms": duration_ms,
                },
            )

            return P03PhaseResult.skip(
                phase_id=self.PHASE_ID,
                reason=skip_reason,
                duration_ms=duration_ms,
            )

        # Execute dream algorithms
        try:
            outputs = await self._execute_algorithms(envelope, ctx)

            # Stage outputs in envelope (unless shadow mode)
            if self.config.should_persist_outputs:
                self._stage_outputs(envelope, outputs)
            else:
                self._logger.info(
                    "R5 shadow mode: outputs discarded",
                    extra={
                        "cycle_id": envelope.context.cycle_id,
                        "insights_count": len(outputs.insights),
                        "counterfactuals_count": len(outputs.counterfactuals),
                    },
                )

            duration_ms = int(time.time() * 1000) - start_ms

            # Emit success metrics
            self._emit_success_metrics(envelope, ctx, outputs, duration_ms)

            self._logger.info(
                "R5 phase completed",
                extra={
                    "cycle_id": envelope.context.cycle_id,
                    "mode": self.config.mode.value,
                    "insights_count": len(outputs.insights),
                    "counterfactuals_count": len(outputs.counterfactuals),
                    "routine_optimizations_count": len(outputs.routine_optimizations),
                    "prospective_memories_count": len(outputs.prospective_memories),
                    "duration_ms": duration_ms,
                },
            )

            return P03PhaseResult.done(
                phase_id=self.PHASE_ID,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms

            self._logger.exception(
                "R5 phase failed",
                extra={
                    "cycle_id": envelope.context.cycle_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )

            error = P03Error.create(
                phase="R5",
                stage_id="r5_dream_explorer",
                error_type=type(e).__name__,
                error_message=str(e),
                recoverable=True,
                stack_trace=traceback.format_exc(),
            )

            return P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=error,
                duration_ms=duration_ms,
            )

    def should_skip(
        self,
        envelope: "P03BatchEnvelope",
        ctx: "P03RunnerContext",
    ) -> Tuple[bool, str]:
        """
        Check if R5 phase should be skipped.

        Skip conditions (Issue 8.1.2):
        1. Mode is DISABLED
        2. Backlog exceeds threshold (pending > backlog_threshold)
        3. Remaining time window < min_remaining_window_seconds

        Args:
            envelope: P03 batch envelope
            ctx: Runner context

        Returns:
            Tuple of (should_skip, reason). If should_skip is True,
            reason is non-empty.
        """
        # Check 1: Mode disabled
        if not self.config.should_execute:
            return (True, R5SkipReason.DISABLED)

        # Check 2: Backlog pressure
        pending_before = envelope.context.pending_before
        if pending_before > self.config.backlog_threshold:
            self._logger.info(
                "R5 skip: backlog exceeded",
                extra={
                    "pending_before": pending_before,
                    "threshold": self.config.backlog_threshold,
                },
            )
            return (True, R5SkipReason.BACKLOG_EXCEEDED)

        # Check 3: Time window constraint
        remaining_ms = envelope.context.remaining_deadline_ms()
        remaining_seconds = remaining_ms / 1000.0 if remaining_ms > 0 else 0
        if remaining_seconds < self.config.min_remaining_window_seconds:
            self._logger.info(
                "R5 skip: time window exceeded",
                extra={
                    "remaining_seconds": remaining_seconds,
                    "min_required_seconds": self.config.min_remaining_window_seconds,
                },
            )
            return (True, R5SkipReason.TIME_WINDOW_EXCEEDED)

        return (False, "")

    def idempotency_key(self, envelope: "P03BatchEnvelope") -> str:
        """
        Compute deterministic idempotency key for R5 phase.

        Pattern: p03:r5:{cycle_id}:{batch_id}

        Args:
            envelope: P03 batch envelope

        Returns:
            Idempotency key string
        """
        return f"p03:r5:{envelope.context.cycle_id}:{envelope.context.batch_id}"

    async def _execute_algorithms(
        self,
        envelope: "P03BatchEnvelope",
        ctx: "P03RunnerContext",
    ) -> R5PhaseOutputs:
        """
        Execute R5 dream algorithms via M22 DreamExplorer.

        Delegates to the DreamExplorer module which orchestrates:
        - CPN: Counterfactual generation (Issue 8.1.4)
        - TPN-MCTS: Forward simulation (Issue 8.1.5)
        - SPC-UQ: Prospective memory (Issue 8.1.8)
        - BGT-SM: Insight generation (Issue 8.1.9)
        - TDL-HCO: Routine optimization (Issue 8.1.11)

        Args:
            envelope: P03 batch envelope
            ctx: Runner context

        Returns:
            R5PhaseOutputs container with generated outputs
        """
        from k0.modules.consolidation.dream import DreamConfig, DreamExplorer, DreamExplorerInput

        # Create DreamConfig from R5Config
        dream_config = DreamConfig.from_r5_config(self.config)
        dream_config = DreamConfig(
            depth=dream_config.depth,
            creativity=dream_config.creativity,
            seed=envelope.context.cycle_id,  # Use cycle_id for determinism
            max_insights=dream_config.max_insights,
            max_counterfactuals=dream_config.max_counterfactuals,
            max_prospective_memories=dream_config.max_prospective_memories,
            max_routine_optimizations=dream_config.max_routine_optimizations,
            min_novelty_score=dream_config.min_novelty_score,
            min_confidence=dream_config.min_confidence,
            coherence_threshold=dream_config.coherence_threshold,
            semantic_distance_threshold=dream_config.semantic_distance_threshold,
            pmi_threshold=dream_config.pmi_threshold,
            corpus_size_n=dream_config.corpus_size_n,
            cpn_perturbation_std=dream_config.cpn_perturbation_std,
            cpn_counterfactual_types=dream_config.cpn_counterfactual_types,
            spc_simulation_count=dream_config.spc_simulation_count,
            spc_uncertainty_alpha=dream_config.spc_uncertainty_alpha,
            spc_uncertainty_beta=dream_config.spc_uncertainty_beta,
            tdl_learning_rate=dream_config.tdl_learning_rate,
            tdl_discount_factor=dream_config.tdl_discount_factor,
        )

        # Create DreamExplorer instance
        explorer = DreamExplorer(config=dream_config)

        # Build input from envelope
        input_data = DreamExplorerInput(
            cycle_id=envelope.context.cycle_id,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            recent_episodes=list(envelope.phases.r2_clusters),
            kg_entities=list(envelope.phases.r4_new_entities),
            kg_edges=list(envelope.phases.r4_new_edges),
            event_states=list(envelope.events),
        )

        self._logger.debug(
            "R5 delegating to DreamExplorer",
            extra={
                "cycle_id": envelope.context.cycle_id,
                "mode": self.config.mode.value,
                "rollouts": self.config.effective_rollouts,
                "episodes_count": len(input_data.recent_episodes),
                "entities_count": len(input_data.kg_entities),
            },
        )

        # Execute dream exploration
        output = await explorer.explore(input_data)

        # Convert DreamExplorerOutput to R5PhaseOutputs
        return R5PhaseOutputs(
            insights=output.insights,
            counterfactuals=output.counterfactuals,
            routine_optimizations=output.routine_optimizations,
            prospective_memories=output.prospective_memories,
            intent_signals=output.intent_signals,
            mcts_decisions_count=output.mcts_decisions_evaluated,
            compute_seconds_saved=0.0,
        )

    def _stage_outputs(
        self,
        envelope: "P03BatchEnvelope",
        outputs: R5PhaseOutputs,
    ) -> None:
        """
        Stage R5 outputs in envelope.phases for R6 processing.

        Args:
            envelope: P03 batch envelope
            outputs: R5 phase outputs
        """
        envelope.phases.r5_insights = outputs.insights
        envelope.phases.r5_counterfactuals = outputs.counterfactuals
        envelope.phases.r5_routine_optimizations = outputs.routine_optimizations
        envelope.phases.r5_prospective_memories = outputs.prospective_memories
        envelope.phases.r5_intent_signals = outputs.intent_signals
        envelope.phases.r5_skipped = False
        envelope.phases.r5_skip_reason = None

    def _emit_skip_metrics(
        self,
        envelope: "P03BatchEnvelope",
        ctx: "P03RunnerContext",
        skip_reason: str,
    ) -> None:
        """
        Emit metrics for R5 skip event.

        Args:
            envelope: P03 batch envelope (for tenant_id)
            ctx: Runner context
            skip_reason: Reason for skipping
        """
        if ctx.metrics_registry is not None:
            tenant_id = envelope.context.tenant_id

            # Set R5 mode gauge
            ctx.metrics_registry.set_r5_mode(
                tenant_id=tenant_id,
                mode_value=self.config.mode.mode_value,
            )

            # Increment skip counter (Issue 8.1.2)
            ctx.metrics_registry.emit_r5_skip(
                tenant_id=tenant_id,
                skip_reason=skip_reason,
                compute_seconds_saved=0.0,  # No compute happened
            )

    def _emit_success_metrics(
        self,
        envelope: "P03BatchEnvelope",
        ctx: "P03RunnerContext",
        outputs: R5PhaseOutputs,
        duration_ms: int,
    ) -> None:
        """
        Emit metrics for R5 success.

        Args:
            envelope: P03 batch envelope (for tenant_id)
            ctx: Runner context
            outputs: R5 phase outputs
            duration_ms: Phase duration in milliseconds
        """
        if ctx.metrics_registry is not None:
            tenant_id = envelope.context.tenant_id
            mode_str = self.config.mode.value

            # Set R5 mode gauge
            ctx.metrics_registry.set_r5_mode(
                tenant_id=tenant_id,
                mode_value=self.config.mode.mode_value,
            )

            # Emit R5 duration histogram
            ctx.metrics_registry.emit_r5_duration(
                tenant_id=tenant_id,
                duration_seconds=duration_ms / 1000.0,
                mode=mode_str,
            )

            # Emit insight counter
            if outputs.insights:
                ctx.metrics_registry.emit_r5_insights(
                    tenant_id=tenant_id,
                    count=len(outputs.insights),
                    quality_tier="standard",
                )

            # Emit counterfactual counter
            if outputs.counterfactuals:
                # Count by type
                for cf in outputs.counterfactuals:
                    cf_type = getattr(cf, "scenario_type", "UNKNOWN")
                    ctx.metrics_registry.emit_r5_counterfactuals(
                        tenant_id=tenant_id,
                        count=1,
                        counterfactual_type=cf_type,
                    )

            # Emit routine optimization counter
            if outputs.routine_optimizations:
                ctx.metrics_registry.emit_r5_routine_optimizations(
                    tenant_id=tenant_id,
                    count=len(outputs.routine_optimizations),
                )

            # Emit prospective memory counter
            if outputs.prospective_memories:
                ctx.metrics_registry.emit_r5_prospective_memories(
                    tenant_id=tenant_id,
                    count=len(outputs.prospective_memories),
                )

            # Emit MCTS decisions histogram
            if outputs.mcts_decisions_count > 0:
                ctx.metrics_registry.emit_r5_mcts_decisions(
                    tenant_id=tenant_id,
                    decisions_count=outputs.mcts_decisions_count,
                )
