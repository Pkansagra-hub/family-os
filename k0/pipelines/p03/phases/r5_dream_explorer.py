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
    from k0.modules.consolidation.algorithms.mcts import MCTSScenario
    from k0.modules.consolidation.algorithms.routine_detector import RoutineCandidate
    from k0.modules.consolidation.dream.intent_signals import IntentSignal
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.phase_interface import P03RunnerContext
    from k0.pipelines.p03.phase_outputs import (
        CounterfactualScenario,
        Insight,
        KGEdge,
        KGEntity,
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
        routine_candidates: RoutineDetector detected habits (GAP-003)
        prospective_memories: SPC-UQ prospective memory predictions
        intent_signals: Intent signals for layer routing (GAP-001)
        mcts_scenarios: MCTS forward simulation scenarios
        mcts_decisions_count: Number of MCTS decisions evaluated
        compute_seconds_saved: Compute time saved by skipping (for metrics)
    """

    insights: List["Insight"]
    counterfactuals: List["CounterfactualScenario"]
    routine_optimizations: List["RoutineOptimization"]
    routine_candidates: List["RoutineCandidate"] = field(default_factory=list)
    prospective_memories: List["ProspectiveMemory"] = field(default_factory=list)
    intent_signals: List["IntentSignal"] = field(default_factory=list)
    mcts_scenarios: List["MCTSScenario"] = field(default_factory=list)
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

        GAP-001 M9.2: Loads accumulated KG entities and edges from storage
        and merges with batch-new entities for BGT-SM insight generation.

        Args:
            envelope: P03 batch envelope
            ctx: Runner context

        Returns:
            R5PhaseOutputs container with generated outputs
        """
        from k0.modules.consolidation.dream import (
            DreamConfig,
            DreamExplorer,
            DreamExplorerInput,
        )

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

        # =====================================================================
        # GAP-001 M9.2: Load accumulated KG entities and edges
        # BGT-SM needs the full graph, not just batch-new entities
        # =====================================================================
        accumulated_entities = await self._load_accumulated_entities(
            ctx=ctx,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
        )
        accumulated_edges = await self._load_accumulated_edges(
            ctx=ctx,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
        )

        # Merge accumulated with new (new entities take precedence via dict)
        new_entities = list(envelope.phases.r4_new_entities)
        new_edges = list(envelope.phases.r4_new_edges)

        # Create entity ID set for deduplication
        new_entity_ids = {e.entity_id for e in new_entities}
        merged_entities = new_entities + [
            e for e in accumulated_entities if e.entity_id not in new_entity_ids
        ]

        new_edge_ids = {e.edge_id for e in new_edges}
        merged_edges = new_edges + [e for e in accumulated_edges if e.edge_id not in new_edge_ids]

        self._logger.info(
            "R5 loaded accumulated KG for BGT-SM",
            extra={
                "cycle_id": envelope.context.cycle_id,
                "new_entities": len(new_entities),
                "accumulated_entities": len(accumulated_entities),
                "merged_entities": len(merged_entities),
                "new_edges": len(new_edges),
                "accumulated_edges": len(accumulated_edges),
                "merged_edges": len(merged_edges),
            },
        )

        # =====================================================================
        # R5 Parity Resolution: Load accumulated episodes
        # RoutineDetector, CPN, TDL-HCO need historical episode context
        # =====================================================================
        accumulated_episodes = await self._load_accumulated_episodes(
            ctx=ctx,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
        )

        # Merge accumulated with current cycle (current takes precedence)
        current_episodes = list(envelope.phases.r2_clusters)
        current_episode_ids = {e.cluster_id for e in current_episodes}
        merged_episodes = current_episodes + [
            e for e in accumulated_episodes if e.cluster_id not in current_episode_ids
        ]

        self._logger.info(
            "R5 loaded accumulated episodes for RoutineDetector/CPN",
            extra={
                "cycle_id": envelope.context.cycle_id,
                "current_episodes": len(current_episodes),
                "accumulated_episodes": len(accumulated_episodes),
                "merged_episodes": len(merged_episodes),
            },
        )

        # =====================================================================
        # M4-E2: Load accumulated schemas for SPC-UQ reconstruction
        # SPC-UQ needs semantic patterns to fill gaps in ambiguous episodes
        # =====================================================================
        accumulated_schemas = await self._load_accumulated_schemas(
            ctx=ctx,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
        )

        self._logger.info(
            "R5 loaded accumulated schemas for SPC-UQ",
            extra={
                "cycle_id": envelope.context.cycle_id,
                "schema_count": len(accumulated_schemas),
            },
        )

        # =====================================================================
        # M5-E1: Load accumulated routines for TDL-HCO optimization
        # TDL-HCO needs historical routines from st_procedural for TD learning
        # =====================================================================
        accumulated_routines = await self._load_accumulated_routines(
            ctx=ctx,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
        )

        self._logger.info(
            "R5 loaded accumulated routines for TDL-HCO",
            extra={
                "cycle_id": envelope.context.cycle_id,
                "routine_count": len(accumulated_routines),
            },
        )

        # Build input from envelope with merged KG, episodes, schemas, and routines
        input_data = DreamExplorerInput(
            cycle_id=envelope.context.cycle_id,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            recent_episodes=merged_episodes,
            kg_entities=merged_entities,
            kg_edges=merged_edges,
            event_states=list(envelope.events),
            schemas=accumulated_schemas,
            accumulated_routines=accumulated_routines,
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
            routine_candidates=output.routine_candidates,
            prospective_memories=output.prospective_memories,
            intent_signals=output.intent_signals,
            mcts_scenarios=output.mcts_scenarios,
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
        envelope.phases.r5_routine_candidates = outputs.routine_candidates
        envelope.phases.r5_prospective_memories = outputs.prospective_memories
        envelope.phases.r5_intent_signals = outputs.intent_signals
        envelope.phases.r5_mcts_scenarios = outputs.mcts_scenarios
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

    # =========================================================================
    # GAP-001 M9.2: Accumulated KG Loading
    # =========================================================================

    async def _load_accumulated_entities(
        self,
        ctx: "P03RunnerContext",
        tenant_id: str,
        space_id: str,
    ) -> List["KGEntity"]:
        """
        Load accumulated KG entities from storage for R5.

        GAP-001 M9.2: BGT-SM needs access to the full knowledge graph
        to find meaningful bisociative connections, not just batch-new entities.

        Args:
            ctx: Runner context with syscalls
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            List of KGEntity objects from storage
        """
        from k0.pipelines.p03.phase_outputs import KGEntity

        try:
            result = await ctx.syscalls.kg_entities_query(
                tenant_id=tenant_id,
                space_id=space_id,
                limit=self.config.accumulated_kg_entity_limit,
            )

            entities = []
            for row in result.get("entities", []):
                entity = KGEntity(
                    entity_id=row["entity_id"],
                    canonical_name=row["canonical_name"],
                    entity_type=row["entity_type"],
                    aliases_json=row.get("aliases_json", "[]"),
                    confidence=row.get("confidence", 0.0),
                    embedding_id=row.get("embedding_id"),
                    source_event_ids=[],  # Not loaded for accumulated
                    is_new=False,  # Mark as accumulated, not new
                )
                entities.append(entity)

            # GAP-001 M9.4: Load embeddings for entities that have embedding_id
            # BGT-SM needs semantic vectors to compute distances for bisociative insights
            embedding_ids = [e.embedding_id for e in entities if e.embedding_id is not None]
            if embedding_ids:
                try:
                    emb_result = await ctx.syscalls.embedding_vectors_batch_query(
                        embedding_ids=embedding_ids
                    )
                    vectors = emb_result.get("vectors", {})
                    populated_count = 0
                    for entity in entities:
                        if entity.embedding_id and entity.embedding_id in vectors:
                            entity.embedding = vectors[entity.embedding_id]
                            populated_count += 1

                    self._logger.debug(
                        "Loaded embeddings for accumulated entities",
                        extra={
                            "requested": len(embedding_ids),
                            "populated": populated_count,
                            "missing": len(emb_result.get("missing", [])),
                        },
                    )
                except Exception as emb_err:
                    self._logger.warning(
                        "Failed to load embeddings for accumulated entities",
                        extra={"error": str(emb_err)},
                    )

            self._logger.debug(
                "Loaded accumulated KG entities",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "entity_count": len(entities),
                    "limit": self.config.accumulated_kg_entity_limit,
                },
            )

            return entities

        except Exception as e:
            self._logger.warning(
                "Failed to load accumulated KG entities, proceeding with batch-only",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "error": str(e),
                },
            )
            return []

    async def _load_accumulated_edges(
        self,
        ctx: "P03RunnerContext",
        tenant_id: str,
        space_id: str,
    ) -> List["KGEdge"]:
        """
        Load accumulated KG edges from storage for R5.

        GAP-001 M9.2: BGT-SM random walks need the full graph structure
        to traverse and discover bisociative connections.

        Args:
            ctx: Runner context with syscalls
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            List of KGEdge objects from storage
        """
        from k0.pipelines.p03.phase_outputs import KGEdge

        try:
            result = await ctx.syscalls.kg_edges_query(
                tenant_id=tenant_id,
                space_id=space_id,
                limit=self.config.accumulated_kg_edge_limit,
            )

            edges = []
            for row in result.get("edges", []):
                edge = KGEdge(
                    edge_id=row["edge_id"],
                    source_entity_id=row["source_entity_id"],
                    target_entity_id=row["target_entity_id"],
                    relationship_type=row["relationship_type"],
                    weight=row.get("weight", 0.5),
                    confidence=row.get("confidence", 0.0),
                    is_causal=False,  # Not loaded for accumulated
                    evidence_event_ids=[],  # Not loaded for accumulated
                    is_new=False,  # Mark as accumulated, not new
                )
                edges.append(edge)

            self._logger.debug(
                "Loaded accumulated KG edges",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "edge_count": len(edges),
                    "limit": self.config.accumulated_kg_edge_limit,
                },
            )

            return edges

        except Exception as e:
            self._logger.warning(
                "Failed to load accumulated KG edges, proceeding with batch-only",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "error": str(e),
                },
            )
            return []

    # =========================================================================
    # R5 Parity Resolution: Accumulated Episode/Routine Loading
    # =========================================================================

    async def _load_accumulated_episodes(
        self,
        ctx: "P03RunnerContext",
        tenant_id: str,
        space_id: str,
    ) -> List["EpisodeCluster"]:
        """
        Load accumulated episodes from st_epi for R5.

        R5 Parity Resolution: Algorithms like RoutineDetector, CPN, and TDL-HCO
        need historical episode context to detect patterns, generate counterfactuals,
        and optimize routines. This applies the same merge pattern as GAP-001 M9.2.

        Args:
            ctx: Runner context with syscalls
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            List of EpisodeCluster objects from storage
        """
        import json

        from k0.pipelines.p03.phase_outputs import EpisodeCluster

        try:
            result = await ctx.syscalls.episodes_query(
                tenant_id=tenant_id,
                space_id=space_id,
                limit=self.config.accumulated_episode_limit,
            )

            # Build participant name to entity_id mapping from KG
            kg_result = await ctx.syscalls.kg_entities_query(
                tenant_id=tenant_id,
                space_id=space_id,
                limit=5000,  # Load enough entities for name resolution
            )

            name_to_entity_id = {}
            for kg_entity in kg_result.get("entities", []):
                entity_id = kg_entity["entity_id"]
                canonical_name = kg_entity["canonical_name"].lower()
                name_to_entity_id[canonical_name] = entity_id

                # Also map aliases
                try:
                    aliases = json.loads(kg_entity.get("aliases_json", "[]"))
                    for alias in aliases:
                        if isinstance(alias, str):
                            name_to_entity_id[alias.lower()] = entity_id
                except (json.JSONDecodeError, TypeError):
                    pass

            episodes = []
            for row in result.get("episodes", []):
                # Parse source_events_json to get member_event_ids
                try:
                    member_event_ids = json.loads(row.get("source_events_json", "[]"))
                except (json.JSONDecodeError, TypeError):
                    member_event_ids = []

                # Resolve participant names to entity_ids
                entity_ids = []
                try:
                    participants = json.loads(row.get("participants_json", "[]"))
                    for participant in participants:
                        if isinstance(participant, str):
                            entity_id = name_to_entity_id.get(participant.lower())
                            if entity_id:
                                entity_ids.append(entity_id)
                        elif isinstance(participant, dict):
                            name = participant.get("name", participant.get("id", ""))
                            if name:
                                entity_id = name_to_entity_id.get(name.lower())
                                if entity_id:
                                    entity_ids.append(entity_id)
                except (json.JSONDecodeError, TypeError):
                    pass

                episode = EpisodeCluster(
                    cluster_id=row["episode_id"],
                    member_event_ids=member_event_ids,
                    entity_ids=entity_ids,  # Populate resolved entity IDs
                    dominant_sentiment=row.get("sentiment_score", 0.0),
                    aggregated_sentiment=row.get("sentiment_score"),
                    aggregated_salience=row.get("salience_score"),
                    dominant_location=row.get("primary_location"),
                    location_hint=row.get("primary_location"),
                    temporal_start=row.get("start_time_utc", 0),
                    temporal_end=row.get("end_time_utc", 0),
                    activity_type=row.get("episode_type", ""),
                    summary=row.get("episode_summary", ""),
                )
                episodes.append(episode)

            self._logger.debug(
                "Loaded accumulated episodes",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "episode_count": len(episodes),
                    "limit": self.config.accumulated_episode_limit,
                },
            )

            return episodes

        except Exception as e:
            self._logger.warning(
                "Failed to load accumulated episodes, proceeding with batch-only",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "error": str(e),
                },
            )
            return []

    async def _load_accumulated_routines(
        self,
        ctx: "P03RunnerContext",
        tenant_id: str,
        space_id: str,
    ) -> List[dict]:
        """
        Load accumulated routines from st_procedural for R5.

        R5 Parity Resolution: TDL-HCO needs existing routines to optimize
        using temporal difference learning. This loads historical routines
        that can be passed to TDL-HCO for bottleneck detection.

        Args:
            ctx: Runner context with syscalls
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            List of routine dictionaries from storage
        """
        try:
            result = await ctx.syscalls.procedural_memory_query(
                tenant_id=tenant_id,
                space_id=space_id,
                limit=self.config.accumulated_routine_limit,
            )

            routines = result.get("routines", [])

            self._logger.debug(
                "Loaded accumulated routines",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "routine_count": len(routines),
                    "limit": self.config.accumulated_routine_limit,
                },
            )

            return routines

        except Exception as e:
            self._logger.warning(
                "Failed to load accumulated routines, proceeding without historical routines",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "error": str(e),
                },
            )
            return []

    async def _load_accumulated_schemas(
        self,
        ctx: "P03RunnerContext",
        tenant_id: str,
        space_id: str,
    ) -> List["SemanticPatternData"]:
        """
        Load accumulated schemas from st_sem for SPC-UQ.

        M4-E2: SPC-UQ needs semantic patterns to fill gaps in ambiguous
        episodes. This loads patterns with attribute distributions for
        schema-guided reconstruction.

        Args:
            ctx: Runner context with syscalls
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            List of SemanticPatternData objects from storage
        """
        import json

        from k0.modules.consolidation.algorithms.spc_uq import SemanticPatternData

        try:
            result = await ctx.syscalls.semantic_schema_query(
                tenant_id=tenant_id,
                space_id=space_id,
                pattern_types=["ACTIVITY", "LOCATION", "ROUTINE", "THEME"],
                min_confidence=0.5,
                limit=100,
            )

            schemas = []
            for row in result.get("schemas", []):
                # Parse pattern_attributes_json for attribute distributions
                try:
                    attrs = json.loads(row.get("pattern_attributes_json", "{}") or "{}")
                except (json.JSONDecodeError, TypeError):
                    attrs = {}

                schema = SemanticPatternData(
                    pattern_id=row["pattern_id"],
                    activity_type=row.get("activity_type", "UNKNOWN"),
                    confidence=row.get("confidence", 0.5),
                    attribute_distributions=attrs,
                )
                schemas.append(schema)

            self._logger.debug(
                "Loaded accumulated schemas for SPC-UQ",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "schema_count": len(schemas),
                },
            )

            return schemas

        except Exception as e:
            self._logger.warning(
                "Failed to load accumulated schemas, proceeding with empty schemas",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "error": str(e),
                },
            )
            return []
