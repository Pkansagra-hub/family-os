"""
R1 Phase — Importance Scoring, audit sampling, and observability.

M4 Issues 4.1.1-4.1.2: Implement R1 Phase for Importance Scoring with Audit Logging.
M5.O Issues 5.O.1.1-5.O.1.6: R1 Observability (OTel span, histograms, gauges).

This phase performs three live operations:
1. Compute CONFIG_B importance scores for each event (Issue 4.1.1)
2. Log sampled scoring factors for audit trail (Issue 4.1.2)
3. Populate R1 observability metrics for downstream reporting (Issue 5.O.1)

Hebbian learning infrastructure exists in the R1 code surface, but this phase
does not execute Hebbian updates. That logic remains gated and downstream.

References:
    - Dossier §2.4: Scientific Formulas - Importance Score
    - Dossier Appendix C.2.1: ImportanceScorer Algorithm
    - M4 Execution: docs/TEMP_EXECUTION_DOCS/M4_EXECUTION.md Issues 4.1.1-4.1.2
    - Phase Interface: k0/pipelines/p03/phase_interface.py

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from k0.modules.consolidation.algorithms.importance_scorer import (
    ImportanceScorer,
    ImportanceWeights,
)
from k0.pipelines.p03.audit_logger import P03AuditLogger
from k0.pipelines.p03.observability import P03Error, R1PhaseMetrics
from k0.pipelines.p03.phase_interface import P03PhaseResult
from k0.pipelines.p03.phase_outputs import ScoredEvent
from k0.pipelines.p03.runner_contract import P03PhaseId
from k0.pipelines.p03.stores import SyscallWeightStore

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.phase_interface import P03RunnerContext

logger = logging.getLogger(__name__)


# =============================================================================
# R1 CONFIGURATION
# =============================================================================


@dataclass
class R1Config:
    """
    R1 phase configuration.

    Attributes:
        audit_sample_rate: Fraction of events to audit [0.0, 1.0].
                          Use 1.0 for debug (100%), 0.1 for production (10%).
        enable_hebbian: Reserved gate for downstream Hebbian integration.
            R1 scoring remains valid with this disabled during phase hardening.
        hebbian_activation_threshold: Cumulative scored events required before
            adaptive Hebbian infrastructure would activate. Mirrors the
            threshold in WeightTrainingConfig. Decision D-R1-001.
        min_samples_for_learned_weights: Minimum samples before trusting pure
            learned weights over blended cold-start priors.
        importance_weights: Optional explicit override passed to
            ImportanceScorer before any learned-weight lookup.
        enable_kg_boost: Whether to enable KG relationship boost (ADR-K026).
            When True, events mentioning entities with strong KG edges
            get a multiplicative importance boost.
        kg_boost_scale: Multiplier for max edge weight in boost formula.
        kg_max_boost_cap: Hard cap on boost above 1.0.
    """

    audit_sample_rate: float = 0.10  # 10% for production (was 1.0 debug)
    enable_hebbian: bool = (
        False  # Auto-activates at hebbian_activation_threshold (Decision D-R1-001)
    )
    hebbian_activation_threshold: int = 500  # Same as weight learner threshold
    min_samples_for_learned_weights: int = 500
    importance_weights: Optional[ImportanceWeights] = None
    # ADR-K026: KG relationship boost
    enable_kg_boost: bool = False  # Disabled until KG has meaningful data
    kg_boost_scale: float = 0.15
    kg_max_boost_cap: float = 0.20


# =============================================================================
# R1 IMPORTANCE SCORER PHASE
# =============================================================================


class R1ImportanceScorer:
    """
    R1 Phase: Importance Scoring.

    Responsibilities:
        1. Load importance weights (config override, cold-start blend, or static)
        2. Compute CONFIG_B importance score for each event
        3. Log scoring factors for audit trail
        4. Update event state with importance fields
        5. Publish R1 metrics for observability

    Scientific Basis:
        McGaugh (2004) - Emotional memories are more strongly encoded
        due to amygdala-hippocampus interaction. Events with high
        emotional salience, novelty, or social significance are
        prioritized for consolidation.

    Scoring Formula:
        base = emotional + surprise + novelty + social + identity + recency
        importance = clamp(base * elaboration * goal * arc * temporal * type
                           * intent * relationship * tier * reliability, 0, 1)

    Audit Logging:
        Each scoring decision can be logged to st_consolidation_audit
        with component breakdowns for explainability and feedback loops.

    Idempotency:
        - Same events always produce same importance scores
        - Audit records use idempotency keys to prevent duplicates
        - No Hebbian side effects are emitted from this phase
    """

    PHASE_ID = P03PhaseId.R1_SCORE

    def __init__(self, config: Optional[R1Config] = None):
        """
        Initialize R1 phase.

        Args:
            config: Optional configuration (defaults used if not provided)
        """
        self.config = config or R1Config()
        self._scorer: Optional[ImportanceScorer] = None

    @property
    def phase_id(self) -> P03PhaseId:
        """Return the phase identifier."""
        return self.PHASE_ID

    def should_skip(self, envelope: "P03BatchEnvelope") -> bool:
        """
        Check if R1 should be skipped.

        Skip Conditions:
            - Empty event list
            - All events already have importance_computed=True

        Args:
            envelope: Current batch envelope

        Returns:
            True if phase should be skipped
        """
        if not envelope.events:
            return True

        # Check if all events already scored
        all_scored = all(getattr(event, "importance_computed", False) for event in envelope.events)
        return all_scored

    def idempotency_key(self, envelope: "P03BatchEnvelope") -> str:
        """
        Compute idempotency key for retry safety.

        Args:
            envelope: Current batch envelope

        Returns:
            Deterministic key for this phase execution
        """
        return f"p03:r1:{envelope.context.cycle_id}"

    async def run(
        self,
        envelope: "P03BatchEnvelope",
        ctx: "P03RunnerContext",
    ) -> P03PhaseResult:
        """
        Execute R1 phase: Importance Scoring.

        Steps:
            1. Initialize scorer with space_id and weight store
            2. Score all events with factor breakdown
            3. Log audit records for sampled events
            4. Update event states with importance fields
            5. Collect scored events into phase outputs
            6. Populate R1PhaseMetrics for observability (5.O.1.1-6)
            7. Emit OTel span attributes and metrics

        Args:
            envelope: Batch envelope with events to score
            ctx: Runner context with syscalls, logger, config

        Returns:
            P03PhaseResult with status, duration, outputs summary
        """
        start_ms = int(time.time() * 1000)
        cycle_id = envelope.context.cycle_id
        space_id = envelope.context.space_id
        tenant_id = envelope.context.tenant_id

        logger.info(
            "R1: Starting importance scoring phase",
            extra={
                "cycle_id": cycle_id,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "event_count": len(envelope.events),
            },
        )

        # Skip check
        if self.should_skip(envelope):
            duration_ms = int(time.time() * 1000) - start_ms
            logger.info(
                "R1: Skipping phase - no unscored events",
                extra={
                    "cycle_id": cycle_id,
                    "duration_ms": duration_ms,
                },
            )
            return P03PhaseResult.skip(
                phase_id=self.PHASE_ID,
                reason="No unscored events in batch",
                duration_ms=duration_ms,
                idempotency_key=self.idempotency_key(envelope),
            )

        # 5.O.1: Initialize R1PhaseMetrics for this cycle
        r1_metrics = R1PhaseMetrics()

        try:
            # ADR-K026: Load KG edge cache if boost enabled
            kg_boost_config = None
            kg_edge_cache = None
            if self.config.enable_kg_boost:
                from k0.modules.consolidation.algorithms.kg_relationship_boost import (
                    KGBoostConfig,
                    KGEdgeCache,
                )

                kg_boost_config = KGBoostConfig(
                    enabled=True,
                    boost_scale=self.config.kg_boost_scale,
                    max_boost_cap=self.config.kg_max_boost_cap,
                )
                kg_edge_cache = KGEdgeCache()
                await kg_edge_cache.load_edges(
                    tenant_id=tenant_id,
                    space_id=space_id,
                    syscalls=ctx.syscalls,
                )
                logger.info(
                    "R1: KG edge cache loaded for relationship boost",
                    extra={
                        "cycle_id": cycle_id,
                        "edge_count": kg_edge_cache.edge_count,
                    },
                )

            # Initialize scorer with weight store backed by syscalls
            weight_store = SyscallWeightStore(syscalls=ctx.syscalls)
            scorer = ImportanceScorer(
                space_id=space_id,
                weight_store=weight_store,
                static_weights=self.config.importance_weights,
                kg_boost_config=kg_boost_config,
                kg_edge_cache=kg_edge_cache,
            )

            # Create audit logger for this cycle
            audit_logger = P03AuditLogger(
                space_id=space_id,
                tenant_id=tenant_id,
                cycle_id=cycle_id,
            )

            # Get sample rate from config or use default
            sample_rate = ctx.get_config(
                "p03.importance.audit_sample_rate",
                self.config.audit_sample_rate,
            )

            # Capture batch timestamp for consistent recency computation
            now_ms = int(time.time() * 1000)

            # Time the scoring operation specifically (5.O.1.1)
            scoring_start_ms = int(time.time() * 1000)

            # Score all events with audit logging
            scored_results = await scorer.score_batch_with_audit(
                events=envelope.events,
                audit_logger=audit_logger,
                sample_rate=sample_rate,
                now_ms=now_ms,
            )

            scoring_duration_ms = int(time.time() * 1000) - scoring_start_ms

            # Collect scored events into phase outputs
            scored_events: List[ScoredEvent] = []
            for result in scored_results:
                scored_events.append(
                    ScoredEvent(
                        event_id=result["event_id"],
                        importance_score=result["importance_score"],
                        recency_factor=result["recency_factor"],
                        affect_factor=result["affect_factor"],
                        social_factor=result["social_factor"],
                        novelty_factor=result["novelty_factor"],
                        surprise_factor=result.get("surprise_factor", 0.0),
                        identity_factor=result.get("identity_factor", 0.0),
                        priority_tier=result.get("priority_tier", "LOW"),
                    )
                )

                # 5.O.1.2: Record score for histogram
                r1_metrics.record_importance_score(result["importance_score"])

                # 5.O.1.6: Record component breakdown for distribution
                breakdown = result.get("breakdown")
                if breakdown is not None:
                    r1_metrics.record_component_breakdown(
                        emotional=breakdown.emotional_component,
                        surprise=breakdown.surprise_component,
                        novelty=breakdown.novelty_component,
                        social=breakdown.social_component,
                        identity=breakdown.identity_component,
                        recency=breakdown.recency_component,
                    )

            # Store scored events in envelope phases
            envelope.phases.r1_scored_events = scored_events

            # Store audit records for R7 batch write
            envelope.phases.r1_audit_records = audit_logger.get_pending_records()

            # Calculate statistics for logging
            scores = [e.importance_score for e in scored_events]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            max_score = max(scores) if scores else 0.0
            min_score = min(scores) if scores else 0.0

            # Count priority tiers (6-tier, POC validated)
            critical_count = sum(1 for s in scores if s >= 0.80)
            high_count = sum(1 for s in scores if 0.60 <= s < 0.80)
            medium_high_count = sum(1 for s in scores if 0.45 <= s < 0.60)
            medium_count = sum(1 for s in scores if 0.30 <= s < 0.45)
            low_medium_count = sum(1 for s in scores if 0.15 <= s < 0.30)
            low_count = sum(1 for s in scores if s < 0.15)

            duration_ms = int(time.time() * 1000) - start_ms

            # ================================================================
            # 5.O.1: Populate R1PhaseMetrics
            # ================================================================

            # 5.O.1.3: Weight source info
            weights = await scorer.get_weights()
            r1_metrics.set_weight_info(
                weights=weights.as_dict(),
                sample_count=scorer._cached_sample_count,
                source=scorer._weights_source,
            )

            # 5.O.1.4: Priority tier gauge
            r1_metrics.set_tier_counts(
                critical=critical_count,
                high=high_count,
                medium_high=medium_high_count,
                medium=medium_count,
                low_medium=low_medium_count,
                low=low_count,
            )

            # 5.O.1.5: Audit sampling metrics
            r1_metrics.set_audit_counts(
                events_scored=len(scored_events),
                audit_records=audit_logger.record_count(),
            )

            # Timing
            r1_metrics.r1_duration_ms = duration_ms
            r1_metrics.importance_scoring_ms = scoring_duration_ms

            # Store R1 metrics on envelope for downstream consumption
            envelope.phases.r1_metrics = r1_metrics

            # ================================================================
            # 5.O.1: Emit metrics via registry if available
            # ================================================================
            metrics_registry = getattr(ctx, "metrics_registry", None)
            if metrics_registry is not None:
                try:
                    metrics_registry.emit_r1_scoring(
                        tenant_id=tenant_id,
                        r1_metrics=r1_metrics,
                    )
                except Exception as metrics_err:
                    logger.warning(
                        "R1: Failed to emit metrics (non-fatal)",
                        extra={"error": str(metrics_err)},
                    )

            logger.info(
                "R1: Importance scoring complete",
                extra={
                    "cycle_id": cycle_id,
                    "events_scored": len(scored_events),
                    "audit_records": len(audit_logger.get_pending_records()),
                    "avg_score": round(avg_score, 3),
                    "max_score": round(max_score, 3),
                    "min_score": round(min_score, 3),
                    "critical_count": critical_count,
                    "high_count": high_count,
                    "medium_high_count": medium_high_count,
                    "medium_count": medium_count,
                    "low_medium_count": low_medium_count,
                    "low_count": low_count,
                    "weights_source": scorer._weights_source,
                    "duration_ms": duration_ms,
                    "scoring_ms": scoring_duration_ms,
                    "performance_status": r1_metrics.check_performance_threshold(),
                },
            )

            return P03PhaseResult.done(
                phase_id=self.PHASE_ID,
                duration_ms=duration_ms,
                outputs_summary={
                    "events_scored": len(scored_events),
                    "audit_records": audit_logger.record_count(),
                    "avg_importance": round(avg_score, 3),
                    "critical_count": critical_count,
                    "high_count": high_count,
                    "medium_high_count": medium_high_count,
                    "weights_source": scorer._weights_source,
                    "scoring_ms": scoring_duration_ms,
                    "r1_metrics": r1_metrics.to_dict(),
                },
                idempotency_key=self.idempotency_key(envelope),
            )

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms
            logger.exception(
                "R1: Importance scoring failed",
                extra={
                    "cycle_id": cycle_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )

            error = P03Error.create(
                phase="R1",
                stage_id="importance_scorer",
                error_type="R1_SCORING_ERROR",
                error_message=str(e),
                recoverable=True,  # R1 failures are retriable
            )

            return P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=error,
                duration_ms=duration_ms,
            )


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_r1_phase(
    config: Optional[R1Config] = None,
) -> R1ImportanceScorer:
    """
    Factory function to create R1 phase.

    Args:
        config: Optional configuration (defaults used if not provided)

    Returns:
        Configured R1ImportanceScorer instance
    """
    return R1ImportanceScorer(config=config)
