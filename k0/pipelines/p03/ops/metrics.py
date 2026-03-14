"""P03 Metrics Registry — Centralized metric definitions for P03 pipeline.

This module defines all P03-specific metrics and provides convenience methods
for emitting them. It integrates with K0's MetricsExporter — it does NOT
create a separate Prometheus registry.

Issue Reference: M6_EXECUTION.md Issues 6.1.1-6.1.5
Dossier Reference: docs/pipelines/P03_consolidation_dossier_v2.md Section 8.2

CRITICAL ARCHITECTURE PRINCIPLE:
    P03 USES K0's MetricsExporter, it does NOT create its own.
    All metrics are registered with the kernel's exporter.

Usage:
    from k0.obs.metrics import MetricsExporter
    from k0.pipelines.p03.ops.metrics import P03MetricsRegistry

    exporter = MetricsExporter()
    registry = P03MetricsRegistry(exporter)

    # Emit cycle completion
    registry.emit_cycle_complete(tenant_id="t1", status="success", duration_s=45.2)

    # Emit phase timing
    registry.emit_phase_duration(tenant_id="t1", phase="R1", duration_s=2.3)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, Optional

if TYPE_CHECKING:
    from k0.obs.metrics import MetricsExporter

__all__ = [
    "P03MetricsRegistry",
    "DecisionType",
    "GapType",
]

LOGGER = logging.getLogger(__name__)


# =============================================================================
# DECISION TYPE ENUM (for Issue 6.1.4)
# =============================================================================


class DecisionType:
    """Decision types for reconciliation metrics.

    Maps to ReconciliationAction from dossier Section 1.3.
    Using class constants instead of Enum for flexibility.
    """

    REINFORCE = "reinforce"  # Strengthen existing memory
    EXTEND = "extend"  # Add new info to existing
    CREATE = "create"  # Create new memory record
    EVOLVE = "evolve"  # Update with new evidence
    PRUNE = "prune"  # Archive/tombstone
    CONTRADICT = "contradict"  # Conflict detected
    SKIP = "skip"  # No action needed

    @classmethod
    def all_types(cls) -> tuple[str, ...]:
        """Return all decision types for metric label validation."""
        return (
            cls.REINFORCE,
            cls.EXTEND,
            cls.CREATE,
            cls.EVOLVE,
            cls.PRUNE,
            cls.CONTRADICT,
            cls.SKIP,
        )


class GapType:
    """Gap types for P06 active learning metrics.

    Mirrors k0/pipelines/p03/gap_emitter.py GapType enum values.
    Using class constants for consistency with DecisionType.
    """

    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"
    LOW_CONFIDENCE_EDGE = "LOW_CONFIDENCE_EDGE"
    MISSING_ATTRIBUTE = "MISSING_ATTRIBUTE"
    CONTRADICTION = "CONTRADICTION"
    CONCEPT_DRIFT = "CONCEPT_DRIFT"
    STRUCTURAL_HOLE = "STRUCTURAL_HOLE"
    STALE_ANCHOR = "STALE_ANCHOR"

    @classmethod
    def all_types(cls) -> tuple[str, ...]:
        """Return all gap types for metric label validation."""
        return (
            cls.AMBIGUOUS_ENTITY,
            cls.LOW_CONFIDENCE_EDGE,
            cls.MISSING_ATTRIBUTE,
            cls.CONTRADICTION,
            cls.CONCEPT_DRIFT,
            cls.STRUCTURAL_HOLE,
            cls.STALE_ANCHOR,
        )


# =============================================================================
# HISTOGRAM BUCKET DEFINITIONS (from Dossier 8.2)
# =============================================================================

# Cycle duration buckets (seconds): 1s to 10min
CYCLE_DURATION_BUCKETS = (1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0)

# Phase duration buckets (seconds): 100ms to 2min
PHASE_DURATION_BUCKETS = (0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0)

# Confidence/similarity score buckets: 0.0 to 1.0
CONFIDENCE_BUCKETS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)

# Gap importance score buckets: 0.0 to 1.0
GAP_IMPORTANCE_BUCKETS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


# =============================================================================
# METRIC DEFINITIONS
# =============================================================================


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """Definition of a single metric."""

    name: str
    description: str
    metric_type: str  # "counter", "gauge", "histogram"
    labelnames: tuple[str, ...]
    buckets: tuple[float, ...] | None = None  # Only for histograms


# Issue 6.1.2: Cycle Metrics
CYCLE_METRICS = (
    MetricDefinition(
        name="p03_cycle_total",
        description="Total P03 consolidation cycles by status",
        metric_type="counter",
        labelnames=("tenant_id", "status"),
    ),
    MetricDefinition(
        name="p03_cycle_duration_seconds",
        description="P03 cycle duration in seconds",
        metric_type="histogram",
        labelnames=("tenant_id", "qos_band"),
        buckets=CYCLE_DURATION_BUCKETS,
    ),
    MetricDefinition(
        name="p03_cycle_batch_size",
        description="P03 batch size (number of items per cycle)",
        metric_type="histogram",
        labelnames=("tenant_id", "qos_band"),
        buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000),
    ),
    MetricDefinition(
        name="p03_cycle_phase_skip_count",
        description="Number of phases skipped per cycle",
        metric_type="histogram",
        labelnames=("tenant_id",),
        buckets=(0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    ),
    MetricDefinition(
        name="p03_events_processed_total",
        description="Total events processed by outcome",
        metric_type="counter",
        labelnames=("tenant_id", "space_id", "outcome"),
    ),
    MetricDefinition(
        name="p03_pending_events",
        description="Current pending events in st_hipp_events",
        metric_type="gauge",
        labelnames=("tenant_id", "space_id"),
    ),
)

# Issue 6.1.3: Phase Timing Metrics
PHASE_METRICS = (
    MetricDefinition(
        name="p03_phase_duration_seconds",
        description="P03 phase duration in seconds",
        metric_type="histogram",
        labelnames=("tenant_id", "phase"),
        buckets=PHASE_DURATION_BUCKETS,
    ),
    MetricDefinition(
        name="p03_phase_total",
        description="Total phase executions by status",
        metric_type="counter",
        labelnames=("tenant_id", "phase", "status"),
    ),
)

# Issue 6.1.4: Decision Metrics
DECISION_METRICS = (
    MetricDefinition(
        name="p03_decisions_total",
        description="Reconciliation decisions by type and target layer",
        metric_type="counter",
        labelnames=("tenant_id", "decision_type", "target_layer"),
    ),
    MetricDefinition(
        name="p03_decision_confidence",
        description="Decision confidence score distribution",
        metric_type="histogram",
        labelnames=("tenant_id", "decision_type"),
        buckets=CONFIDENCE_BUCKETS,
    ),
    MetricDefinition(
        name="p03_similarity_scores",
        description="Similarity scores from truth matching",
        metric_type="histogram",
        labelnames=("tenant_id", "match_result"),
        buckets=CONFIDENCE_BUCKETS,
    ),
)

# Issue 6.1.5: Gap Detection Metrics
GAP_METRICS = (
    MetricDefinition(
        name="p03_gaps_detected_total",
        description="Knowledge gaps detected by type",
        metric_type="counter",
        labelnames=("tenant_id", "space_id", "gap_type"),
    ),
    MetricDefinition(
        name="p03_gap_importance_score",
        description="Gap importance score distribution",
        metric_type="histogram",
        labelnames=("tenant_id", "gap_type"),
        buckets=GAP_IMPORTANCE_BUCKETS,
    ),
    MetricDefinition(
        name="p03_gaps_pending",
        description="Pending gaps in st_learning_queue",
        metric_type="gauge",
        labelnames=("tenant_id", "space_id"),
    ),
    MetricDefinition(
        name="p03_gaps_deduplicated_total",
        description="Gaps skipped due to deduplication",
        metric_type="counter",
        labelnames=("tenant_id", "gap_type"),
    ),
)

# Issue 6.1.6: Memory Layer Metrics
LAYER_METRICS = (
    MetricDefinition(
        name="p03_layer_records_total",
        description="Records created/updated in memory layers",
        metric_type="counter",
        labelnames=("tenant_id", "layer", "operation"),
    ),
    MetricDefinition(
        name="p03_layer_size",
        description="Current size of memory layer (canonical records only)",
        metric_type="gauge",
        labelnames=("tenant_id", "layer", "archival_status"),
    ),
    MetricDefinition(
        name="p03_layer_avg_confidence",
        description="Average confidence score in memory layer",
        metric_type="gauge",
        labelnames=("tenant_id", "layer"),
    ),
    MetricDefinition(
        name="p03_layer_avg_decay",
        description="Average decay factor in memory layer",
        metric_type="gauge",
        labelnames=("tenant_id", "layer"),
    ),
)

# Issue 6.1.7: Module Performance Metrics
MODULE_DURATION_BUCKETS = (0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0)
CLUSTER_SIZE_BUCKETS = (1, 2, 5, 10, 20, 50, 100)

MODULE_METRICS = (
    MetricDefinition(
        name="p03_module_duration_seconds",
        description="Execution time per module",
        metric_type="histogram",
        labelnames=("tenant_id", "module"),
        buckets=MODULE_DURATION_BUCKETS,
    ),
    MetricDefinition(
        name="p03_module_items_processed",
        description="Items processed by each module",
        metric_type="counter",
        labelnames=("tenant_id", "module", "outcome"),
    ),
    MetricDefinition(
        name="p03_clustering_clusters_created",
        description="Episode clusters created by M18 (R2EpisodicIntegrator)",
        metric_type="counter",
        labelnames=("tenant_id",),
    ),
    MetricDefinition(
        name="p03_clustering_cluster_size",
        description="Size of episode clusters",
        metric_type="histogram",
        labelnames=("tenant_id",),
        buckets=CLUSTER_SIZE_BUCKETS,
    ),
)

# Issue 6.1.8: Shadow Mode Learning Metrics
SHADOW_DIVERGENCE_BUCKETS = (0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0)

SHADOW_METRICS = (
    MetricDefinition(
        name="p03_shadow_executions_total",
        description="Total shadow mode dual executions",
        metric_type="counter",
        labelnames=("tenant_id", "learning_type", "outcome"),
    ),
    MetricDefinition(
        name="p03_shadow_agreement_rate",
        description="Percentage where old and new formulas agree",
        metric_type="gauge",
        labelnames=("tenant_id", "learning_type"),
    ),
    MetricDefinition(
        name="p03_shadow_improvement_rate",
        description="Percentage where new formula is objectively better",
        metric_type="gauge",
        labelnames=("tenant_id", "learning_type"),
    ),
    MetricDefinition(
        name="p03_shadow_regression_rate",
        description="Percentage where new formula is worse than baseline",
        metric_type="gauge",
        labelnames=("tenant_id", "learning_type"),
    ),
    MetricDefinition(
        name="p03_shadow_divergence_magnitude",
        description="Magnitude of difference when decisions diverge",
        metric_type="histogram",
        labelnames=("tenant_id", "learning_type"),
        buckets=SHADOW_DIVERGENCE_BUCKETS,
    ),
    MetricDefinition(
        name="p03_shadow_promotion_eligibility",
        description="Whether shadow mode meets promotion criteria (0=no, 1=yes)",
        metric_type="gauge",
        labelnames=("tenant_id", "learning_type"),
    ),
    MetricDefinition(
        name="p03_shadow_sample_size",
        description="Number of shadow mode samples collected (last 7 days)",
        metric_type="gauge",
        labelnames=("tenant_id", "learning_type"),
    ),
)

# Issue 8.1.1: R5 Dream Exploration Metrics
R5_DREAM_ROLLOUTS_BUCKETS = (1, 5, 10, 25, 50, 100, 200, 500)
R5_DREAM_MCTS_DECISIONS_BUCKETS = (1, 5, 10, 25, 50, 100, 250, 500, 1000)

R5_METRICS = (
    # R5 Mode Gauge (Issue 8.1.1)
    # 0=disabled, 1=shadow, 2=enabled_low, 3=enabled
    MetricDefinition(
        name="p03_r5_mode",
        description="R5 Dream Exploration mode (0=disabled, 1=shadow, 2=enabled_low, 3=enabled)",
        metric_type="gauge",
        labelnames=("tenant_id",),
    ),
    # R5 Compute Savings (Issue 8.1.1)
    MetricDefinition(
        name="p03_r5_compute_seconds_saved",
        description="Compute time saved by R5 skip/shadow mode",
        metric_type="counter",
        labelnames=("tenant_id", "skip_reason"),
    ),
    # R5 Skip Counter (Issue 8.1.2)
    MetricDefinition(
        name="p03_r5_skipped_decisions",
        description="R5 decisions skipped due to skip conditions",
        metric_type="counter",
        labelnames=("tenant_id", "skip_reason"),
    ),
    # R5 Algorithm Outputs (Issue 8.1.3)
    MetricDefinition(
        name="p03_r5_insights_generated",
        description="Total insights generated by BGT-SM",
        metric_type="counter",
        labelnames=("tenant_id", "quality_tier"),
    ),
    MetricDefinition(
        name="p03_r5_counterfactuals_generated",
        description="Total counterfactuals generated by CPN",
        metric_type="counter",
        labelnames=("tenant_id", "counterfactual_type"),
    ),
    MetricDefinition(
        name="p03_r5_routine_optimizations_generated",
        description="Total routine optimizations by TDL-HCO",
        metric_type="counter",
        labelnames=("tenant_id",),
    ),
    MetricDefinition(
        name="p03_r5_prospective_memories_generated",
        description="Total prospective memories by SPC-UQ",
        metric_type="counter",
        labelnames=("tenant_id",),
    ),
    # R5 BGT-SM Cold Start (Issue 8.1.20)
    MetricDefinition(
        name="p03_bgt_sm_cold_start_skipped",
        description="BGT-SM discoveries skipped due to cold start (corpus too small)",
        metric_type="counter",
        labelnames=("tenant_id",),
    ),
    # R5 MCTS Metrics (Issue 8.1.5, 8.1.7)
    MetricDefinition(
        name="p03_r5_mcts_decisions",
        description="MCTS decisions evaluated",
        metric_type="histogram",
        labelnames=("tenant_id",),
        buckets=R5_DREAM_MCTS_DECISIONS_BUCKETS,
    ),
    MetricDefinition(
        name="p03_r5_mcts_rollouts_per_decision",
        description="MCTS rollouts per decision",
        metric_type="histogram",
        labelnames=("tenant_id", "mode"),
        buckets=R5_DREAM_ROLLOUTS_BUCKETS,
    ),
    MetricDefinition(
        name="p03_r5_mcts_early_terminations",
        description="MCTS decisions that terminated early due to convergence",
        metric_type="counter",
        labelnames=("tenant_id",),
    ),
    # Issue 8.1.7: MCTS Persistence Metrics
    MetricDefinition(
        name="p03_mcts_early_termination_rate",
        description="Percentage of MCTS decisions that terminated early (7d rolling)",
        metric_type="gauge",
        labelnames=("tenant_id",),
    ),
    MetricDefinition(
        name="p03_mcts_compute_budget_used",
        description="Total MCTS rollouts used per cycle",
        metric_type="counter",
        labelnames=("tenant_id", "cycle_id"),
    ),
    MetricDefinition(
        name="p03_mcts_budget_exhausted",
        description="Cycles that exhausted their MCTS compute budget",
        metric_type="counter",
        labelnames=("tenant_id",),
    ),
    MetricDefinition(
        name="p03_mcts_decisions_persisted",
        description="MCTS decisions persisted to st_mcts_decisions",
        metric_type="counter",
        labelnames=("tenant_id", "decision_type"),
    ),
    # R5 Shadow Validation (Issue 8.1.14)
    MetricDefinition(
        name="p03_r5_shadow_validation_total",
        description="R5 shadow validation comparisons (heuristic vs MCTS)",
        metric_type="counter",
        labelnames=("tenant_id", "outcome"),
    ),
    MetricDefinition(
        name="p03_r5_shadow_mcts_better_rate",
        description="Rate at which MCTS outperforms heuristic (7d rolling)",
        metric_type="gauge",
        labelnames=("tenant_id",),
    ),
    # R5 Duration (Issue 8.1.1)
    MetricDefinition(
        name="p03_r5_duration_seconds",
        description="R5 phase execution duration",
        metric_type="histogram",
        labelnames=("tenant_id", "mode"),
        buckets=PHASE_DURATION_BUCKETS,
    ),
)

# Issue 6.1.9: Decay Engine Metrics
DECAY_METRICS = (
    # Aggregate decay metrics
    MetricDefinition(
        name="p03_decay_total_active",
        description="Total ACTIVE records across all memory layers",
        metric_type="gauge",
        labelnames=("tenant_id", "space_id"),
    ),
    MetricDefinition(
        name="p03_decay_total_archived",
        description="Total ARCHIVED records across all memory layers",
        metric_type="gauge",
        labelnames=("tenant_id", "space_id"),
    ),
    MetricDefinition(
        name="p03_decay_total_tombstoned",
        description="Total TOMBSTONE records across all memory layers",
        metric_type="gauge",
        labelnames=("tenant_id", "space_id"),
    ),
    # Resurrection metrics
    MetricDefinition(
        name="p03_decay_resurrections_total",
        description="Total resurrection events",
        metric_type="counter",
        labelnames=("tenant_id", "space_id", "layer", "trigger"),
    ),
    MetricDefinition(
        name="p03_resurrection_rate",
        description="Resurrections per 1000 accesses (rolling 7d)",
        metric_type="gauge",
        labelnames=("tenant_id", "space_id", "layer"),
    ),
    MetricDefinition(
        name="p03_resurrection_loops",
        description="Entities with resurrection_count >= 3 (instability)",
        metric_type="counter",
        labelnames=("tenant_id", "space_id", "layer"),
    ),
    # Immunity metrics
    MetricDefinition(
        name="p03_decay_immune_entities",
        description="Count of immune entities per layer",
        metric_type="gauge",
        labelnames=("tenant_id", "space_id", "layer", "reason"),
    ),
    MetricDefinition(
        name="p03_decay_immune_skipped",
        description="Decay updates skipped due to immunity",
        metric_type="counter",
        labelnames=("tenant_id", "space_id", "layer"),
    ),
    # Lambda learning metrics
    MetricDefinition(
        name="p03_lambda_learned_spaces",
        description="Number of spaces with learned lambda modifiers",
        metric_type="gauge",
        labelnames=("layer",),
    ),
    MetricDefinition(
        name="p03_lambda_drift_30d",
        description="Maximum lambda change over 30 days per space",
        metric_type="gauge",
        labelnames=("tenant_id", "space_id", "layer"),
    ),
    # Decay feedback metrics
    MetricDefinition(
        name="p03_decay_feedback_events",
        description="Decay feedback events recorded",
        metric_type="counter",
        labelnames=("layer", "event_type"),
    ),
    MetricDefinition(
        name="p03_premature_archival_rate",
        description="Rate of entities accessed within 7 days of archival",
        metric_type="gauge",
        labelnames=("layer", "space_id"),
    ),
)

# Issue 6.1.14: Cross-Space Security Metrics
SECURITY_METRICS = (
    MetricDefinition(
        name="p03_cross_space_query_attempts",
        description="Attempted queries without space_id filter (should always be 0)",
        metric_type="counter",
        labelnames=("table", "query_type"),
    ),
    MetricDefinition(
        name="p03_rls_policy_blocks",
        description="Queries blocked by RLS policy",
        metric_type="counter",
        labelnames=("table", "policy_name"),
    ),
    MetricDefinition(
        name="p03_isolation_health",
        description="Isolation health indicator (1=healthy, 0=violation detected)",
        metric_type="gauge",
        labelnames=(),
    ),
)

# Issue 6.1.15: Formula Debug Tracing Metrics
TRACING_METRICS = (
    MetricDefinition(
        name="p03_debug_traces_captured",
        description="Total debug traces captured",
        metric_type="counter",
        labelnames=("level", "formula"),
    ),
    MetricDefinition(
        name="p03_debug_trace_storage_bytes",
        description="Storage used by debug traces",
        metric_type="gauge",
        labelnames=("level",),
    ),
    MetricDefinition(
        name="p03_debug_trace_sampling_rate",
        description="Current sampling rate for debug traces",
        metric_type="gauge",
        labelnames=(),
    ),
)

# Issue 6.1.16: Formula Comparison Metrics
FORMULA_DURATION_BUCKETS = (1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0)

FORMULA_COMPARISON_METRICS = (
    MetricDefinition(
        name="p03_formula_duration_ms",
        description="Formula execution duration in milliseconds",
        metric_type="histogram",
        labelnames=("formula", "version"),
        buckets=FORMULA_DURATION_BUCKETS,
    ),
    MetricDefinition(
        name="p03_formula_errors_total",
        description="Total formula execution errors",
        metric_type="counter",
        labelnames=("formula", "version", "error_type"),
    ),
    MetricDefinition(
        name="p03_formula_decisions_total",
        description="Total decisions made by formula version",
        metric_type="counter",
        labelnames=("formula", "version", "decision_type"),
    ),
    MetricDefinition(
        name="p03_formula_comparison_divergence",
        description="Times old and new formula disagreed",
        metric_type="counter",
        labelnames=("formula", "old_decision", "new_decision"),
    ),
    MetricDefinition(
        name="p03_prune_regrets_total",
        description="Pruned entities that were later accessed (regret events)",
        metric_type="counter",
        labelnames=("formula_version", "space_id"),
    ),
    MetricDefinition(
        name="p03_entities_pruned_total",
        description="Total entities pruned",
        metric_type="counter",
        labelnames=("formula_version", "space_id"),
    ),
)

# Issue 5.O.1: R1 Importance Scoring Observability Metrics
R1_IMPORTANCE_SCORE_BUCKETS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
R1_COMPONENT_BUCKETS = (0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0)

R1_METRICS = (
    # 5.O.1.1: OTel span is handled in tracing, not as a metric
    # 5.O.1.2: Score distribution histogram
    MetricDefinition(
        name="p03_r1_importance_score_distribution",
        description="Histogram of R1 importance scores per cycle",
        metric_type="histogram",
        labelnames=("tenant_id",),
        buckets=R1_IMPORTANCE_SCORE_BUCKETS,
    ),
    # 5.O.1.3: Weight source counter
    MetricDefinition(
        name="p03_r1_weight_source_total",
        description="Count of R1 cycles by weight source (static/learned/blended)",
        metric_type="counter",
        labelnames=("tenant_id", "weight_source"),
    ),
    # 5.O.1.4: Priority tier gauge
    MetricDefinition(
        name="p03_r1_tier_count",
        description="Count per priority tier per R1 cycle",
        metric_type="gauge",
        labelnames=("tenant_id", "tier"),
    ),
    # 5.O.1.5: Audit sampling metrics
    MetricDefinition(
        name="p03_r1_audit_sampling_ratio",
        description="Ratio of audit records to events scored",
        metric_type="gauge",
        labelnames=("tenant_id",),
    ),
    MetricDefinition(
        name="p03_r1_events_scored_total",
        description="Total events scored by R1",
        metric_type="counter",
        labelnames=("tenant_id",),
    ),
    MetricDefinition(
        name="p03_r1_audit_records_total",
        description="Total audit records generated by R1",
        metric_type="counter",
        labelnames=("tenant_id",),
    ),
    # 5.O.1.6: Component distribution histograms (6 components)
    MetricDefinition(
        name="p03_r1_component_emotional",
        description="Distribution of emotional component values",
        metric_type="histogram",
        labelnames=("tenant_id",),
        buckets=R1_COMPONENT_BUCKETS,
    ),
    MetricDefinition(
        name="p03_r1_component_surprise",
        description="Distribution of surprise component values",
        metric_type="histogram",
        labelnames=("tenant_id",),
        buckets=R1_COMPONENT_BUCKETS,
    ),
    MetricDefinition(
        name="p03_r1_component_novelty",
        description="Distribution of novelty component values",
        metric_type="histogram",
        labelnames=("tenant_id",),
        buckets=R1_COMPONENT_BUCKETS,
    ),
    MetricDefinition(
        name="p03_r1_component_social",
        description="Distribution of social component values",
        metric_type="histogram",
        labelnames=("tenant_id",),
        buckets=R1_COMPONENT_BUCKETS,
    ),
    MetricDefinition(
        name="p03_r1_component_identity",
        description="Distribution of identity component values",
        metric_type="histogram",
        labelnames=("tenant_id",),
        buckets=R1_COMPONENT_BUCKETS,
    ),
    MetricDefinition(
        name="p03_r1_component_recency",
        description="Distribution of recency component values",
        metric_type="histogram",
        labelnames=("tenant_id",),
        buckets=R1_COMPONENT_BUCKETS,
    ),
    # R1 duration (separate from phase_duration for R1-specific buckets)
    MetricDefinition(
        name="p03_r1_scoring_duration_ms",
        description="R1 importance scoring duration in milliseconds",
        metric_type="histogram",
        labelnames=("tenant_id",),
        buckets=(10, 30, 50, 100, 300, 500, 1000, 5000, 10000, 18000),
    ),
)

# All metric definitions combined
ALL_METRICS = (
    CYCLE_METRICS
    + PHASE_METRICS
    + DECISION_METRICS
    + GAP_METRICS
    + LAYER_METRICS
    + MODULE_METRICS
    + SHADOW_METRICS
    + R5_METRICS  # Issue 8.1.1: R5 Dream Exploration
    + DECAY_METRICS
    + SECURITY_METRICS
    + TRACING_METRICS
    + FORMULA_COMPARISON_METRICS
    + TRACING_METRICS
    + R1_METRICS  # Issue 5.O.1: R1 Observability
)


# =============================================================================
# CONSTANTS
# =============================================================================

# Memory layers (8 total) - from dossier Section 6.1
MEMORY_LAYERS = (
    "st_epi",  # Episodic Memory
    "st_sem",  # Semantic Memory
    "st_procedural",  # Procedural Memory (habits)
    "st_social",  # Social Memory (relationships)
    "st_prospective",  # Prospective Memory (intentions)
    "st_kg_dom",  # Knowledge Graph: entities/concepts
    "st_kg_edges",  # Knowledge Graph: relationships
    "st_hipp_events",  # Hippocampal buffer (staging)
)

# Module IDs for M18-M25
MODULE_IDS = (
    "M18",  # R2EpisodicIntegrator
    "M19",  # DuplicateDetector
    "M20",  # RetentionEnforcer
    "M21",  # R4KGConsolidator
    "M22",  # DreamExplorer (optional)
    "M23",  # R1ImportanceScorer
    "M24",  # R7TruthWriter
    "M25",  # P03GapEmitter
)

# Learning types for shadow mode
LEARNING_TYPES = (
    "importance",  # Importance scoring weights
    "hebbian",  # Edge weight adjustments
    "decay",  # Lambda parameter tuning
    "similarity",  # Matching thresholds
    "threshold",  # Decision thresholds
)

# Resurrection triggers
RESURRECTION_TRIGGERS = (
    "EXPLICIT_ACCESS",
    "ASSOCIATION_HIT",
    "SEARCH_RESULT",
    "CONSOLIDATION_RESCUE",
)

# Immunity reasons
IMMUNITY_REASONS = (
    "FAMILY_MEMBER",
    "MANUAL_PIN",
    "HIGH_ACCESS_FREQUENCY",
)


# =============================================================================
# P03 METRICS REGISTRY
# =============================================================================


class P03MetricsRegistry:
    """Centralized registry for all P03 metrics.

    Integrates with K0's MetricsExporter to register and emit P03-specific
    metrics. Does NOT create a separate Prometheus registry.

    Thread Safety:
        Thread-safe. Uses MetricsExporter's internal locking.

    Usage:
        exporter = MetricsExporter()
        registry = P03MetricsRegistry(exporter)

        # Emit on cycle completion
        registry.emit_cycle_complete(tenant_id="t1", status="success", duration_s=45.2)

        # Emit phase timing
        registry.emit_phase_duration(tenant_id="t1", phase="R1", duration_s=2.3)

        # Emit decision
        registry.emit_decision(tenant_id="t1", decision_type="create",
                               target_layer="st_epi", confidence=0.85)

        # Emit gap detection
        registry.emit_gap_detected(tenant_id="t1", space_id="s1",
                                   gap_type="AMBIGUOUS_ENTITY", importance=0.7)
    """

    def __init__(self, exporter: MetricsExporter) -> None:
        """Initialize P03 metrics registry.

        Args:
            exporter: K0's MetricsExporter instance to register metrics with.
        """
        self._exporter = exporter
        self._registered = False

    @property
    def exporter(self) -> MetricsExporter:
        """Return the underlying MetricsExporter."""
        return self._exporter

    def register_all(self) -> None:
        """Register all P03 metrics with the exporter.

        Idempotent: safe to call multiple times.
        Metrics are created lazily by MetricsExporter on first use,
        so this method pre-registers them for discoverability.
        """
        if self._registered:
            return

        for metric_def in ALL_METRICS:
            self._register_metric(metric_def)

        self._registered = True
        LOGGER.info("P03 metrics registry initialized with %d metrics", len(ALL_METRICS))

    def _register_metric(self, metric_def: MetricDefinition) -> None:
        """Register a single metric with the exporter.

        Args:
            metric_def: Metric definition to register.
        """
        if metric_def.metric_type == "counter":
            self._exporter.counter(
                metric_def.name,
                metric_def.description,
                labelnames=metric_def.labelnames,
            )
        elif metric_def.metric_type == "gauge":
            self._exporter.gauge(
                metric_def.name,
                metric_def.description,
                labelnames=metric_def.labelnames,
            )
        elif metric_def.metric_type == "histogram":
            self._exporter.histogram(
                metric_def.name,
                metric_def.description,
                labelnames=metric_def.labelnames,
                buckets=metric_def.buckets,
            )

    # =========================================================================
    # ISSUE 6.1.2: CYCLE METRICS
    # =========================================================================

    def emit_cycle_complete(
        self,
        tenant_id: str,
        status: str,
        duration_s: float,
        events_processed: int = 0,
        space_id: Optional[str] = None,
    ) -> None:
        """Emit metrics for a completed consolidation cycle.

        Args:
            tenant_id: Tenant identifier.
            status: Cycle status ("success", "failure", "partial", "aborted").
            duration_s: Total cycle duration in seconds.
            events_processed: Number of events processed (optional).
            space_id: Space identifier (optional, for events_processed).
        """
        # p03_cycle_total counter
        self._exporter.emit("p03_cycle_total", 1.0, tenant_id=tenant_id, status=status)

        # p03_cycle_duration_seconds histogram
        self._exporter.observe(
            "p03_cycle_duration_seconds",
            duration_s,
            labels={"tenant_id": tenant_id},
            buckets=CYCLE_DURATION_BUCKETS,
        )

        LOGGER.debug(
            "P03 cycle metrics emitted: tenant=%s status=%s duration=%.2fs events=%d",
            tenant_id,
            status,
            duration_s,
            events_processed,
        )

    def emit_events_processed(
        self,
        tenant_id: str,
        space_id: str,
        outcome: str,
        count: int = 1,
    ) -> None:
        """Emit events processed counter.

        Args:
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            outcome: Event outcome ("consolidated", "duplicate", "pruned", "skipped").
            count: Number of events (default 1).
        """
        self._exporter.emit(
            "p03_events_processed_total",
            float(count),
            tenant_id=tenant_id,
            space_id=space_id,
            outcome=outcome,
        )

    def set_pending_events(
        self,
        tenant_id: str,
        space_id: str,
        count: int,
    ) -> None:
        """Set the pending events gauge.

        Args:
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            count: Current pending event count.
        """
        self._exporter.set_gauge(
            "p03_pending_events",
            float(count),
            tenant_id=tenant_id,
            space_id=space_id,
        )

    def emit_cycle_duration(
        self,
        duration_ms: int,
        tenant_id: str,
        space_id: str,
        qos_band: str,
    ) -> None:
        """Emit cycle duration histogram.

        Args:
            duration_ms: Duration in milliseconds.
            tenant_id: Tenant identifier.
            space_id: Space identifier (not used in metric, for context).
            qos_band: QoS band ("GREEN", "AMBER", "RED").
        """
        duration_s = duration_ms / 1000.0
        self._exporter.observe(
            "p03_cycle_duration_seconds",
            duration_s,
            labels={"tenant_id": tenant_id, "qos_band": qos_band},
            buckets=CYCLE_DURATION_BUCKETS,
        )

    def emit_batch_size(
        self,
        batch_size: int,
        tenant_id: str,
        space_id: str,
        qos_band: str,
    ) -> None:
        """Emit batch size histogram.

        Args:
            batch_size: Number of items in the batch.
            tenant_id: Tenant identifier.
            space_id: Space identifier (not used in metric, for context).
            qos_band: QoS band ("GREEN", "AMBER", "RED").
        """
        self._exporter.observe(
            "p03_cycle_batch_size",
            float(batch_size),
            labels={"tenant_id": tenant_id, "qos_band": qos_band},
            buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000),
        )

    def emit_phase_skip_count(
        self,
        skip_count: int,
        tenant_id: str,
        space_id: str,
    ) -> None:
        """Emit phase skip count histogram.

        Args:
            skip_count: Number of phases skipped.
            tenant_id: Tenant identifier.
            space_id: Space identifier (not used in metric, for context).
        """
        self._exporter.observe(
            "p03_cycle_phase_skip_count",
            float(skip_count),
            labels={"tenant_id": tenant_id},
            buckets=(0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        )

    # =========================================================================
    # ISSUE 6.1.3: PHASE TIMING METRICS
    # =========================================================================

    def emit_phase_duration(
        self,
        tenant_id: str,
        phase: str,
        duration_s: float,
    ) -> None:
        """Emit phase duration histogram observation.

        Args:
            tenant_id: Tenant identifier.
            phase: Phase identifier (R0-R8).
            duration_s: Phase duration in seconds.
        """
        self._exporter.observe(
            "p03_phase_duration_seconds",
            duration_s,
            labels={"tenant_id": tenant_id, "phase": phase},
            buckets=PHASE_DURATION_BUCKETS,
        )

    def emit_phase_complete(
        self,
        tenant_id: str,
        phase: str,
        status: str,
    ) -> None:
        """Emit phase completion counter.

        Args:
            tenant_id: Tenant identifier.
            phase: Phase identifier (R0-R8).
            status: Phase status ("success", "skip", "fail").
        """
        self._exporter.emit(
            "p03_phase_total",
            1.0,
            tenant_id=tenant_id,
            phase=phase,
            status=status,
        )

    # =========================================================================
    # ISSUE 5.O.1: R1 IMPORTANCE SCORING METRICS
    # =========================================================================

    def emit_r1_scoring(
        self,
        tenant_id: str,
        r1_metrics: Any,
    ) -> None:
        """Emit all R1 importance scoring observability metrics.

        Covers issues 5.O.1.2 through 5.O.1.6. Called once per R1 cycle.

        Args:
            tenant_id: Tenant identifier.
            r1_metrics: R1PhaseMetrics instance with populated data.
        """
        # 5.O.1.2: Score distribution histogram
        for score in r1_metrics.importance_scores:
            self._exporter.observe(
                "p03_r1_importance_score_distribution",
                score,
                labels={"tenant_id": tenant_id},
                buckets=R1_IMPORTANCE_SCORE_BUCKETS,
            )

        # 5.O.1.3: Weight source counter (one increment per cycle)
        self._exporter.emit(
            "p03_r1_weight_source_total",
            1.0,
            tenant_id=tenant_id,
            weight_source=r1_metrics.importance_weight_source,
        )

        # 5.O.1.4: Priority tier gauge
        for tier, count in r1_metrics.tier_counts.items():
            self._exporter.set_gauge(
                "p03_r1_tier_count",
                float(count),
                tenant_id=tenant_id,
                tier=tier,
            )

        # 5.O.1.5: Audit sampling metrics
        self._exporter.emit(
            "p03_r1_events_scored_total",
            float(r1_metrics.events_scored),
            tenant_id=tenant_id,
        )
        self._exporter.emit(
            "p03_r1_audit_records_total",
            float(r1_metrics.audit_records_generated),
            tenant_id=tenant_id,
        )
        if r1_metrics.events_scored > 0:
            ratio = r1_metrics.audit_records_generated / r1_metrics.events_scored
            self._exporter.set_gauge(
                "p03_r1_audit_sampling_ratio",
                ratio,
                tenant_id=tenant_id,
            )

        # 5.O.1.6: Component distribution histograms
        for component_name, component_values in (
            ("emotional", r1_metrics.emotional_components),
            ("surprise", r1_metrics.surprise_components),
            ("novelty", r1_metrics.novelty_components),
            ("social", r1_metrics.social_components),
            ("identity", r1_metrics.identity_components),
            ("recency", r1_metrics.recency_components),
        ):
            metric_name = f"p03_r1_component_{component_name}"
            for value in component_values:
                self._exporter.observe(
                    metric_name,
                    value,
                    labels={"tenant_id": tenant_id},
                    buckets=R1_COMPONENT_BUCKETS,
                )

        # R1 duration
        self._exporter.observe(
            "p03_r1_scoring_duration_ms",
            r1_metrics.r1_duration_ms,
            labels={"tenant_id": tenant_id},
            buckets=(10, 30, 50, 100, 300, 500, 1000, 5000, 10000, 18000),
        )

        LOGGER.debug(
            "R1 scoring metrics emitted: tenant=%s events=%d source=%s",
            tenant_id,
            r1_metrics.events_scored,
            r1_metrics.importance_weight_source,
        )

    # =========================================================================
    # ISSUE 6.1.4: DECISION METRICS
    # =========================================================================

    def emit_decision(
        self,
        tenant_id: str,
        decision_type: str,
        target_layer: str,
        confidence: Optional[float] = None,
    ) -> None:
        """Emit reconciliation decision metrics.

        Args:
            tenant_id: Tenant identifier.
            decision_type: Decision type (from DecisionType constants).
            target_layer: Target memory layer (st_epi, st_sem, etc.).
            confidence: Optional confidence score [0.0, 1.0].
        """
        # p03_decisions_total counter
        self._exporter.emit(
            "p03_decisions_total",
            1.0,
            tenant_id=tenant_id,
            decision_type=decision_type,
            target_layer=target_layer,
        )

        # p03_decision_confidence histogram (if provided)
        if confidence is not None:
            self._exporter.observe(
                "p03_decision_confidence",
                confidence,
                labels={"tenant_id": tenant_id, "decision_type": decision_type},
                buckets=CONFIDENCE_BUCKETS,
            )

    def emit_similarity_score(
        self,
        tenant_id: str,
        score: float,
        match_result: str,
    ) -> None:
        """Emit similarity score histogram observation.

        Args:
            tenant_id: Tenant identifier.
            score: Similarity score [0.0, 1.0].
            match_result: Match result ("match", "partial", "no_match").
        """
        self._exporter.observe(
            "p03_similarity_scores",
            score,
            labels={"tenant_id": tenant_id, "match_result": match_result},
            buckets=CONFIDENCE_BUCKETS,
        )

    # =========================================================================
    # ISSUE 6.1.5: GAP DETECTION METRICS
    # =========================================================================

    def emit_gap_detected(
        self,
        tenant_id: str,
        space_id: str,
        gap_type: str,
        importance: Optional[float] = None,
    ) -> None:
        """Emit gap detection metrics.

        Args:
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            gap_type: Gap type (from GapType constants).
            importance: Optional importance score [0.0, 1.0].
        """
        # p03_gaps_detected_total counter
        self._exporter.emit(
            "p03_gaps_detected_total",
            1.0,
            tenant_id=tenant_id,
            space_id=space_id,
            gap_type=gap_type,
        )

        # p03_gap_importance_score histogram (if provided)
        if importance is not None:
            self._exporter.observe(
                "p03_gap_importance_score",
                importance,
                labels={"tenant_id": tenant_id, "gap_type": gap_type},
                buckets=GAP_IMPORTANCE_BUCKETS,
            )

    def emit_gap_deduplicated(
        self,
        tenant_id: str,
        gap_type: str,
    ) -> None:
        """Emit gap deduplication counter.

        Args:
            tenant_id: Tenant identifier.
            gap_type: Gap type that was deduplicated.
        """
        self._exporter.emit(
            "p03_gaps_deduplicated_total",
            1.0,
            tenant_id=tenant_id,
            gap_type=gap_type,
        )

    def set_gaps_pending(
        self,
        tenant_id: str,
        space_id: str,
        count: int,
    ) -> None:
        """Set the pending gaps gauge.

        Args:
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            count: Current pending gap count.
        """
        self._exporter.set_gauge(
            "p03_gaps_pending",
            float(count),
            tenant_id=tenant_id,
            space_id=space_id,
        )

    # =========================================================================
    # BATCH EMISSION HELPERS
    # =========================================================================

    def emit_from_observability_context(
        self,
        tenant_id: str,
        space_id: str,
        counters: Mapping[str, int],
        histograms: Mapping[str, list[float]],
        phase_durations: Mapping[str, int],
    ) -> None:
        """Emit metrics from P03ObservabilityContext data.

        Convenience method to flush accumulated metrics from an envelope's
        observability context at end of cycle.

        Args:
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            counters: Counter values from P03ObservabilityContext.counters.
            histograms: Histogram values from P03ObservabilityContext.histograms.
            phase_durations: Phase durations (ms) from get_all_phase_durations().
        """
        # Emit phase durations
        for phase, duration_ms in phase_durations.items():
            self.emit_phase_duration(
                tenant_id=tenant_id,
                phase=phase,
                duration_s=duration_ms / 1000.0,
            )

        LOGGER.debug(
            "P03 metrics flushed from observability context: "
            "phases=%d counters=%d histograms=%d",
            len(phase_durations),
            len(counters),
            len(histograms),
        )

    # =========================================================================
    # ISSUE 6.1.6: MEMORY LAYER METRICS
    # =========================================================================

    def emit_layer_write(
        self,
        tenant_id: str,
        layer: str,
        operation: str,
        count: int = 1,
    ) -> None:
        """Emit layer write counter.

        Args:
            tenant_id: Tenant identifier.
            layer: Memory layer (st_epi, st_sem, etc.).
            operation: Write operation (create, update, archive, tombstone).
            count: Number of records (default 1).
        """
        self._exporter.emit(
            "p03_layer_records_total",
            float(count),
            tenant_id=tenant_id,
            layer=layer,
            operation=operation,
        )

    def set_layer_size(
        self,
        tenant_id: str,
        layer: str,
        archival_status: str,
        count: int,
    ) -> None:
        """Set layer size gauge.

        Args:
            tenant_id: Tenant identifier.
            layer: Memory layer (st_epi, st_sem, etc.).
            archival_status: Status (active, archived, tombstoned).
            count: Current record count.
        """
        self._exporter.set_gauge(
            "p03_layer_size",
            float(count),
            tenant_id=tenant_id,
            layer=layer,
            archival_status=archival_status,
        )

    def set_layer_avg_confidence(
        self,
        tenant_id: str,
        layer: str,
        avg_confidence: float,
    ) -> None:
        """Set layer average confidence gauge.

        Args:
            tenant_id: Tenant identifier.
            layer: Memory layer (st_epi, st_sem, etc.).
            avg_confidence: Average confidence score [0.0, 1.0].
        """
        self._exporter.set_gauge(
            "p03_layer_avg_confidence",
            avg_confidence,
            tenant_id=tenant_id,
            layer=layer,
        )

    def set_layer_avg_decay(
        self,
        tenant_id: str,
        layer: str,
        avg_decay: float,
    ) -> None:
        """Set layer average decay gauge.

        Args:
            tenant_id: Tenant identifier.
            layer: Memory layer (st_epi, st_sem, etc.).
            avg_decay: Average decay factor [0.0, 1.0].
        """
        self._exporter.set_gauge(
            "p03_layer_avg_decay",
            avg_decay,
            tenant_id=tenant_id,
            layer=layer,
        )

    # =========================================================================
    # ISSUE 6.1.7: MODULE PERFORMANCE METRICS
    # =========================================================================

    def emit_module_duration(
        self,
        tenant_id: str,
        module: str,
        duration_s: float,
    ) -> None:
        """Emit module execution duration histogram.

        Args:
            tenant_id: Tenant identifier.
            module: Module ID (M18-M25).
            duration_s: Execution duration in seconds.
        """
        self._exporter.observe(
            "p03_module_duration_seconds",
            duration_s,
            labels={"tenant_id": tenant_id, "module": module},
            buckets=MODULE_DURATION_BUCKETS,
        )

    def emit_module_items_processed(
        self,
        tenant_id: str,
        module: str,
        outcome: str,
        count: int = 1,
    ) -> None:
        """Emit module items processed counter.

        Args:
            tenant_id: Tenant identifier.
            module: Module ID (M18-M25).
            outcome: Processing outcome (success, skip, error).
            count: Number of items (default 1).
        """
        self._exporter.emit(
            "p03_module_items_processed",
            float(count),
            tenant_id=tenant_id,
            module=module,
            outcome=outcome,
        )

    def emit_clustering_stats(
        self,
        tenant_id: str,
        clusters_created: int,
        cluster_sizes: list[int],
    ) -> None:
        """Emit M18 clustering statistics.

        Args:
            tenant_id: Tenant identifier.
            clusters_created: Number of clusters created.
            cluster_sizes: List of cluster sizes for histogram.
        """
        # Emit cluster count
        self._exporter.emit(
            "p03_clustering_clusters_created",
            float(clusters_created),
            tenant_id=tenant_id,
        )

        # Emit cluster size histogram observations
        for size in cluster_sizes:
            self._exporter.observe(
                "p03_clustering_cluster_size",
                float(size),
                labels={"tenant_id": tenant_id},
                buckets=CLUSTER_SIZE_BUCKETS,
            )

    # =========================================================================
    # ISSUE 6.1.8: SHADOW MODE METRICS
    # =========================================================================

    def emit_shadow_execution(
        self,
        tenant_id: str,
        learning_type: str,
        outcome: str,
        divergence_magnitude: Optional[float] = None,
    ) -> None:
        """Emit shadow mode execution metrics.

        Args:
            tenant_id: Tenant identifier.
            learning_type: Learning type (importance, hebbian, decay, etc.).
            outcome: Comparison outcome (agreement, improvement, regression, divergence).
            divergence_magnitude: Optional magnitude of divergence [0.0, inf).
        """
        # p03_shadow_executions_total counter
        self._exporter.emit(
            "p03_shadow_executions_total",
            1.0,
            tenant_id=tenant_id,
            learning_type=learning_type,
            outcome=outcome,
        )

        # p03_shadow_divergence_magnitude histogram (if divergence)
        if divergence_magnitude is not None and outcome == "divergence":
            self._exporter.observe(
                "p03_shadow_divergence_magnitude",
                divergence_magnitude,
                labels={"tenant_id": tenant_id, "learning_type": learning_type},
                buckets=SHADOW_DIVERGENCE_BUCKETS,
            )

    def set_shadow_rates(
        self,
        tenant_id: str,
        learning_type: str,
        agreement_rate: float,
        improvement_rate: float,
        regression_rate: float,
    ) -> None:
        """Set shadow mode rate gauges.

        Args:
            tenant_id: Tenant identifier.
            learning_type: Learning type (importance, hebbian, decay, etc.).
            agreement_rate: Agreement rate [0.0, 1.0].
            improvement_rate: Improvement rate [0.0, 1.0].
            regression_rate: Regression rate [0.0, 1.0].
        """
        self._exporter.set_gauge(
            "p03_shadow_agreement_rate",
            agreement_rate,
            tenant_id=tenant_id,
            learning_type=learning_type,
        )
        self._exporter.set_gauge(
            "p03_shadow_improvement_rate",
            improvement_rate,
            tenant_id=tenant_id,
            learning_type=learning_type,
        )
        self._exporter.set_gauge(
            "p03_shadow_regression_rate",
            regression_rate,
            tenant_id=tenant_id,
            learning_type=learning_type,
        )

    def set_shadow_promotion_status(
        self,
        tenant_id: str,
        learning_type: str,
        eligible: bool,
        sample_size: int,
    ) -> None:
        """Set shadow mode promotion eligibility and sample size.

        Args:
            tenant_id: Tenant identifier.
            learning_type: Learning type (importance, hebbian, decay, etc.).
            eligible: Whether promotion criteria are met.
            sample_size: Number of samples in 7-day window.
        """
        self._exporter.set_gauge(
            "p03_shadow_promotion_eligibility",
            1.0 if eligible else 0.0,
            tenant_id=tenant_id,
            learning_type=learning_type,
        )
        self._exporter.set_gauge(
            "p03_shadow_sample_size",
            float(sample_size),
            tenant_id=tenant_id,
            learning_type=learning_type,
        )

    # =========================================================================
    # ISSUE 6.1.9: DECAY ENGINE METRICS
    # =========================================================================

    def set_decay_aggregates(
        self,
        tenant_id: str,
        space_id: str,
        active_count: int,
        archived_count: int,
        tombstoned_count: int,
    ) -> None:
        """Set decay aggregate gauges.

        Args:
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            active_count: Total ACTIVE records.
            archived_count: Total ARCHIVED records.
            tombstoned_count: Total TOMBSTONE records.
        """
        self._exporter.set_gauge(
            "p03_decay_total_active",
            float(active_count),
            tenant_id=tenant_id,
            space_id=space_id,
        )
        self._exporter.set_gauge(
            "p03_decay_total_archived",
            float(archived_count),
            tenant_id=tenant_id,
            space_id=space_id,
        )
        self._exporter.set_gauge(
            "p03_decay_total_tombstoned",
            float(tombstoned_count),
            tenant_id=tenant_id,
            space_id=space_id,
        )

    def emit_resurrection(
        self,
        tenant_id: str,
        space_id: str,
        layer: str,
        trigger: str,
        resurrection_count: int = 1,
    ) -> None:
        """Emit resurrection event metrics.

        Args:
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            layer: Memory layer (st_epi, st_sem, etc.).
            trigger: Resurrection trigger (EXPLICIT_ACCESS, etc.).
            resurrection_count: Entity's total resurrection count.
        """
        # p03_decay_resurrections_total counter
        self._exporter.emit(
            "p03_decay_resurrections_total",
            1.0,
            tenant_id=tenant_id,
            space_id=space_id,
            layer=layer,
            trigger=trigger,
        )

        # Detect resurrection loop (threshold = 3)
        if resurrection_count >= 3:
            self._exporter.emit(
                "p03_resurrection_loops",
                1.0,
                tenant_id=tenant_id,
                space_id=space_id,
                layer=layer,
            )

    def set_resurrection_rate(
        self,
        tenant_id: str,
        space_id: str,
        layer: str,
        rate_per_1000: float,
    ) -> None:
        """Set resurrection rate gauge.

        Args:
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            layer: Memory layer (st_epi, st_sem, etc.).
            rate_per_1000: Resurrections per 1000 accesses (rolling 7d).
        """
        self._exporter.set_gauge(
            "p03_resurrection_rate",
            rate_per_1000,
            tenant_id=tenant_id,
            space_id=space_id,
            layer=layer,
        )

    def set_immune_entities(
        self,
        tenant_id: str,
        space_id: str,
        layer: str,
        reason: str,
        count: int,
    ) -> None:
        """Set immune entities gauge.

        Args:
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            layer: Memory layer (st_epi, st_sem, etc.).
            reason: Immunity reason (FAMILY_MEMBER, MANUAL_PIN, etc.).
            count: Number of immune entities.
        """
        self._exporter.set_gauge(
            "p03_decay_immune_entities",
            float(count),
            tenant_id=tenant_id,
            space_id=space_id,
            layer=layer,
            reason=reason,
        )

    def emit_immunity_skip(
        self,
        tenant_id: str,
        space_id: str,
        layer: str,
    ) -> None:
        """Emit immunity skip counter.

        Args:
            tenant_id: Tenant identifier.
            space_id: Space identifier.
            layer: Memory layer (st_epi, st_sem, etc.).
        """
        self._exporter.emit(
            "p03_decay_immune_skipped",
            1.0,
            tenant_id=tenant_id,
            space_id=space_id,
            layer=layer,
        )

    def set_lambda_metrics(
        self,
        layer: str,
        learned_spaces_count: int,
        tenant_id: Optional[str] = None,
        space_id: Optional[str] = None,
        drift_30d: Optional[float] = None,
    ) -> None:
        """Set lambda learning metrics.

        Args:
            layer: Memory layer (st_epi, st_sem, etc.).
            learned_spaces_count: Number of spaces with learned lambdas.
            tenant_id: Tenant identifier (for drift metric).
            space_id: Space identifier (for drift metric).
            drift_30d: Maximum lambda change over 30 days (for drift metric).
        """
        self._exporter.set_gauge(
            "p03_lambda_learned_spaces",
            float(learned_spaces_count),
            layer=layer,
        )

        if tenant_id and space_id and drift_30d is not None:
            self._exporter.set_gauge(
                "p03_lambda_drift_30d",
                drift_30d,
                tenant_id=tenant_id,
                space_id=space_id,
                layer=layer,
            )

    def emit_decay_feedback(
        self,
        layer: str,
        event_type: str,
    ) -> None:
        """Emit decay feedback event counter.

        Args:
            layer: Memory layer (st_epi, st_sem, etc.).
            event_type: Event type (ACCESS, RESURRECTION, ARCHIVE, TOMBSTONE).
        """
        self._exporter.emit(
            "p03_decay_feedback_events",
            1.0,
            layer=layer,
            event_type=event_type,
        )

    def set_premature_archival_rate(
        self,
        layer: str,
        space_id: str,
        rate: float,
    ) -> None:
        """Set premature archival rate gauge.

        Args:
            layer: Memory layer (st_epi, st_sem, etc.).
            space_id: Space identifier.
            rate: Rate of entities accessed within 7 days of archival.
        """
        self._exporter.set_gauge(
            "p03_premature_archival_rate",
            rate,
            layer=layer,
            space_id=space_id,
        )

    # =========================================================================
    # ISSUE 8.1.1: R5 DREAM EXPLORATION METRICS
    # =========================================================================

    def set_r5_mode(
        self,
        tenant_id: str,
        mode_value: int,
    ) -> None:
        """Set R5 execution mode gauge.

        Mode values:
        - 0: disabled
        - 1: shadow
        - 2: enabled_low
        - 3: enabled

        Args:
            tenant_id: Tenant identifier.
            mode_value: Numeric mode value (0-3).
        """
        self._exporter.set_gauge(
            "p03_r5_mode",
            float(mode_value),
            tenant_id=tenant_id,
        )

    def emit_r5_skip(
        self,
        tenant_id: str,
        skip_reason: str,
        compute_seconds_saved: float = 0.0,
    ) -> None:
        """Emit R5 skip metrics.

        Args:
            tenant_id: Tenant identifier.
            skip_reason: Reason for skip (disabled, backlog_exceeded, time_window_exceeded).
            compute_seconds_saved: Estimated compute time saved.
        """
        # Increment skip counter
        self._exporter.emit(
            "p03_r5_skipped_decisions",
            1.0,
            tenant_id=tenant_id,
            skip_reason=skip_reason,
        )

        # Increment compute savings if applicable
        if compute_seconds_saved > 0:
            self._exporter.emit(
                "p03_r5_compute_seconds_saved",
                compute_seconds_saved,
                tenant_id=tenant_id,
                skip_reason=skip_reason,
            )

    def emit_r5_insights(
        self,
        tenant_id: str,
        count: int,
        quality_tier: str = "standard",
    ) -> None:
        """Emit R5 insight generation counter.

        Args:
            tenant_id: Tenant identifier.
            count: Number of insights generated.
            quality_tier: Quality tier (low, standard, high).
        """
        self._exporter.emit(
            "p03_r5_insights_generated",
            float(count),
            tenant_id=tenant_id,
            quality_tier=quality_tier,
        )

    def emit_r5_counterfactuals(
        self,
        tenant_id: str,
        count: int,
        counterfactual_type: str,
    ) -> None:
        """Emit R5 counterfactual generation counter.

        Args:
            tenant_id: Tenant identifier.
            count: Number of counterfactuals generated.
            counterfactual_type: Type (UPWARD, DOWNWARD, SEMIFACTUAL).
        """
        self._exporter.emit(
            "p03_r5_counterfactuals_generated",
            float(count),
            tenant_id=tenant_id,
            counterfactual_type=counterfactual_type,
        )

    def emit_r5_routine_optimizations(
        self,
        tenant_id: str,
        count: int,
    ) -> None:
        """Emit R5 routine optimization counter.

        Args:
            tenant_id: Tenant identifier.
            count: Number of routine optimizations generated.
        """
        self._exporter.emit(
            "p03_r5_routine_optimizations_generated",
            float(count),
            tenant_id=tenant_id,
        )

    def emit_r5_prospective_memories(
        self,
        tenant_id: str,
        count: int,
    ) -> None:
        """Emit R5 prospective memory counter.

        Args:
            tenant_id: Tenant identifier.
            count: Number of prospective memories generated.
        """
        self._exporter.emit(
            "p03_r5_prospective_memories_generated",
            float(count),
            tenant_id=tenant_id,
        )

    def emit_bgt_sm_cold_start_skipped(
        self,
        tenant_id: str,
    ) -> None:
        """Emit BGT-SM cold start skip counter.

        Issue 8.1.20: Tracks when BGT-SM is skipped due to insufficient
        corpus size for meaningful PMI calculation.

        Args:
            tenant_id: Tenant identifier.
        """
        self._exporter.emit(
            "p03_bgt_sm_cold_start_skipped",
            1.0,
            tenant_id=tenant_id,
        )

    def emit_r5_mcts_decisions(
        self,
        tenant_id: str,
        decisions_count: int,
    ) -> None:
        """Emit R5 MCTS decisions histogram.

        Args:
            tenant_id: Tenant identifier.
            decisions_count: Number of MCTS decisions evaluated.
        """
        self._exporter.emit(
            "p03_r5_mcts_decisions",
            float(decisions_count),
            tenant_id=tenant_id,
        )

    def emit_r5_mcts_rollouts(
        self,
        tenant_id: str,
        rollouts_per_decision: int,
        mode: str,
    ) -> None:
        """Emit R5 MCTS rollouts per decision histogram.

        Args:
            tenant_id: Tenant identifier.
            rollouts_per_decision: Number of rollouts per decision.
            mode: R5 mode (shadow, enabled_low, enabled).
        """
        self._exporter.emit(
            "p03_r5_mcts_rollouts_per_decision",
            float(rollouts_per_decision),
            tenant_id=tenant_id,
            mode=mode,
        )

    def emit_r5_mcts_early_termination(
        self,
        tenant_id: str,
    ) -> None:
        """Emit R5 MCTS early termination counter.

        Args:
            tenant_id: Tenant identifier.
        """
        self._exporter.emit(
            "p03_r5_mcts_early_terminations",
            1.0,
            tenant_id=tenant_id,
        )

    def emit_r5_shadow_validation(
        self,
        tenant_id: str,
        outcome: str,
    ) -> None:
        """Emit R5 shadow validation counter.

        Args:
            tenant_id: Tenant identifier.
            outcome: Comparison outcome (mcts_better, heuristic_better, equal).
        """
        self._exporter.emit(
            "p03_r5_shadow_validation_total",
            1.0,
            tenant_id=tenant_id,
            outcome=outcome,
        )

    def set_r5_shadow_mcts_better_rate(
        self,
        tenant_id: str,
        rate: float,
    ) -> None:
        """Set R5 shadow MCTS better rate gauge.

        Args:
            tenant_id: Tenant identifier.
            rate: Rate at which MCTS outperforms heuristic (0.0-1.0).
        """
        self._exporter.set_gauge(
            "p03_r5_shadow_mcts_better_rate",
            rate,
            tenant_id=tenant_id,
        )

    def emit_r5_duration(
        self,
        tenant_id: str,
        duration_seconds: float,
        mode: str,
    ) -> None:
        """Emit R5 phase duration histogram.

        Args:
            tenant_id: Tenant identifier.
            duration_seconds: Phase execution duration in seconds.
            mode: R5 mode (disabled, shadow, enabled_low, enabled).
        """
        self._exporter.emit(
            "p03_r5_duration_seconds",
            duration_seconds,
            tenant_id=tenant_id,
            mode=mode,
        )

    # =========================================================================
    # Issue 8.1.7: MCTS Decision Persistence Metrics
    # =========================================================================

    def set_mcts_early_termination_rate(
        self,
        tenant_id: str,
        rate: float,
    ) -> None:
        """Set MCTS early termination rate gauge.

        Args:
            tenant_id: Tenant identifier.
            rate: Percentage of decisions that terminated early (0.0-1.0).
        """
        self._exporter.set_gauge(
            "p03_mcts_early_termination_rate",
            rate,
            tenant_id=tenant_id,
        )

    def emit_mcts_compute_budget_used(
        self,
        tenant_id: str,
        cycle_id: str,
        rollouts_used: int,
    ) -> None:
        """Emit MCTS compute budget usage counter.

        Args:
            tenant_id: Tenant identifier.
            cycle_id: Consolidation cycle ULID.
            rollouts_used: Number of rollouts used in this cycle.
        """
        self._exporter.emit(
            "p03_mcts_compute_budget_used",
            float(rollouts_used),
            tenant_id=tenant_id,
            cycle_id=cycle_id,
        )

    def emit_mcts_budget_exhausted(
        self,
        tenant_id: str,
    ) -> None:
        """Emit MCTS budget exhausted counter (cycle hit 1000 rollout limit).

        Args:
            tenant_id: Tenant identifier.
        """
        self._exporter.emit(
            "p03_mcts_budget_exhausted",
            1.0,
            tenant_id=tenant_id,
        )

    def emit_mcts_decision_persisted(
        self,
        tenant_id: str,
        decision_type: str,
    ) -> None:
        """Emit MCTS decision persisted counter.

        Args:
            tenant_id: Tenant identifier.
            decision_type: Type of decision (merge, causal, cluster, etc.).
        """
        self._exporter.emit(
            "p03_mcts_decisions_persisted",
            1.0,
            tenant_id=tenant_id,
            decision_type=decision_type,
        )
