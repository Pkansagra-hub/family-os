"""
P03PhaseOutputs - Container for aggregated outputs from each phase R0-R8.

Unlike per-event state (P03EventState), these are batch-level aggregates:
- R2: Episode clusters (not per-event)
- R4: KG entities and edges (extracted from batch)
- R5: Insights and counterfactuals (creative outputs)

Each field is populated by its respective phase and consumed
by downstream phases or R7 writes.

Spec Reference: docs/pipelines/P03_envelope_fields_discovery.md section 17.x

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts`, `*_at`, `*_start`, `*_end` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from k0.modules.consolidation.algorithms.observation_context import (
        ObservationContext,
    )
    from k0.modules.consolidation.algorithms.routine_detector import RoutineCandidate
    from k0.modules.consolidation.dream.intent_signals import IntentSignal
    from k0.modules.consolidation.staging.r6_output import R6Output
    from k0.modules.consolidation.truth_writer.result import WriteResult

# =============================================================================
# R1 Aggregate Types (Importance Scoring)
# =============================================================================


@dataclass
class ScoredEvent:
    """
    Event with computed importance score (R1 output).

    Used for batch-level importance statistics and downstream prioritization.
    """

    event_id: str
    importance_score: float
    recency_factor: float
    affect_factor: float
    social_factor: float
    novelty_factor: float


@dataclass
class HebbianEdgeUpdate:
    """
    Hebbian learning edge weight update (R1 output).

    Represents co-activation strengthening between KG entities.
    """

    source_entity_id: str
    target_entity_id: str
    old_weight: float
    new_weight: float
    delta: float
    update_type: str = "STRENGTHEN"  # STRENGTHEN, WEAKEN, CREATE


# =============================================================================
# R2 Aggregate Types (Episode Clustering)
# =============================================================================


@dataclass
class EpisodeCluster:
    """
    Episode formed by clustering events in R2.

    A cluster represents a coherent episode (e.g., "lunch with mom")
    formed from multiple related events.
    """

    cluster_id: str  # ULID
    member_event_ids: List[str] = field(default_factory=list)
    # Issue 7.6: Observation contexts for member events (for st_observations)
    member_contexts: List["ObservationContext"] = field(default_factory=list)
    centroid_embedding_id: Optional[str] = None
    dominant_sentiment: float = 0.0
    dominant_emotion: str = ""
    temporal_start: int = 0  # MILLISECONDS
    temporal_end: int = 0  # MILLISECONDS
    location_hint: Optional[str] = None
    location_type: Optional[str] = None  # GAP-002: location category (home/work/restaurant/etc)
    participants_json: str = "[]"
    activity_type: str = ""  # Legacy 7-type
    # UltraBERT 12-type INGRESS classification (Issue 0060)
    # DIARY/TASK/HEALTH/FINANCE/RELATIONSHIP/WORK/META/MEMORY/PLANNING/CELEBRATION/CONCERN/GRATITUDE
    activity_type_ultrabert: str = ""
    cohesion_score: float = 0.0  # Intra-cluster similarity
    title: str = ""  # Generated or extracted
    summary: str = ""

    @property
    def event_count(self) -> int:
        """Number of events in this cluster."""
        return len(self.member_event_ids)

    @property
    def duration_ms(self) -> int:
        """Duration of episode in milliseconds."""
        return self.temporal_end - self.temporal_start


# =============================================================================
# R3 Aggregate Types (Reconciliation/Dedup/Decay)
# =============================================================================


@dataclass
class DedupMerge:
    """
    Duplicate detection result from R3.

    When two events are detected as duplicates (via SimHash),
    one is marked canonical and the other is merged/skipped.
    """

    duplicate_id: str
    canonical_id: str
    hamming_distance: int
    merge_confidence: float
    content_type: str


@dataclass
class DecayUpdate:
    """
    Decay score update for existing truth record (R3).

    Tracks how a record's decay score changed due to access patterns.
    """

    record_id: str
    layer: str  # st_epi, st_sem, etc.
    old_decay: float
    new_decay: float
    days_since_access: int
    decision: str  # KEEP, ARCHIVE, TOMBSTONE


# =============================================================================
# R4 Aggregate Types (Knowledge Graph)
# =============================================================================


@dataclass
class KGEntity:
    """
    Knowledge graph entity extracted in R4.

    Can be a new entity or reference to existing one.

    GAP-001 M9.4: Added embedding field for R5 BGT-SM semantic distance.
    GAP-005: Added entity_subtype for fine-grained classification.
    """

    entity_id: str  # ULID (new) or existing ID
    canonical_name: str
    entity_type: str  # PERSON, LOCATION, ORG, THING, CONCEPT
    entity_subtype: Optional[str] = None  # GAP-005: FAMILY_MEMBER, FRIEND, HOME, etc.
    aliases_json: str = "[]"
    confidence: float = 0.0
    embedding_id: Optional[str] = None
    embedding: Optional[List[float]] = None  # GAP-001 M9.4: 768-dim vector for BGT-SM
    source_event_ids: List[str] = field(default_factory=list)
    is_new: bool = True


@dataclass
class KGEntityUpdate:
    """
    Update to existing KG entity in R4.

    Partial update - only specified fields are changed.

    Issue 3 Fix: Added observation_count_increment and new_source_event_ids
    for REINFORCE operations that merge new observations into existing entities.
    """

    entity_id: str
    field_updates: Dict[str, Any] = field(default_factory=dict)
    confidence_delta: float = 0.0
    new_aliases: List[str] = field(default_factory=list)
    # Issue 3 Fix: For REINFORCE operations
    observation_count_increment: int = 0  # How many new observations to add
    new_source_event_ids: List[str] = field(default_factory=list)  # New event IDs to append


@dataclass
class KGEdge:
    """
    Knowledge graph edge created in R4.

    Represents a relationship between two entities.
    """

    edge_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str  # KNOWS, LOCATED_AT, PART_OF, CAUSES, etc.
    weight: float = 0.5
    confidence: float = 0.0
    is_causal: bool = False
    evidence_event_ids: List[str] = field(default_factory=list)
    is_new: bool = True


@dataclass
class KGEdgeUpdate:
    """
    Update to existing KG edge in R4.

    Typically weight/confidence adjustments from new evidence.
    GAP-001 M9: Added observation_count_increment for Granger causality.
    """

    edge_id: str
    weight_delta: float = 0.0
    confidence_delta: float = 0.0
    new_evidence_ids: List[str] = field(default_factory=list)
    # GAP-001 M9: Increment observation_count for Granger causality
    observation_count_increment: int = 0


@dataclass
class CausalEdge:
    """
    Causal relationship inferred via Granger causality in R4.

    Stronger evidence of causation than regular edges.
    """

    cause_entity_id: str
    effect_entity_id: str
    lag_days: int
    granger_p_value: float
    effect_size: float
    confidence: float


@dataclass
class SocialRelationship:
    """
    Social relationship extracted in R4 for st_social.

    Represents a relationship between the SELF actor and another person,
    extracted from UltraBERT outputs and event context.

    UltraBERT provides:
    - extracted_relations_json: Direct relation types (parent_of, spouse_of, etc.)
    - sentiment: Emotional valence of interactions
    - emotions: 44 emotion labels including family-specific ones
    - ner_family: Person/kinship entities for name extraction

    This captures:
    - Contextual identity: "Sarah from work" vs "Sarah (wife)"
    - Emotional significance: Who matters in what contexts
    - Social roles: Mentor, Confidant, Energy-giver
    - Relationship evolution: How connections change over time
    - Interaction patterns: Communication modes, typical activities
    """

    # Identity
    relationship_id: str  # ULID
    actor_a_id: str  # SELF entity ID
    actor_b_id: str  # Other person entity ID
    actor_b_name: str  # Display name for actor_b

    # UltraBERT-derived relationship types (direct signal)
    # Values: parent_of, child_of, spouse_of, sibling_of, friend_of, colleague_of, etc.
    ultrabert_relation_types: List[str] = field(default_factory=list)

    # Inferred relationship type (from UltraBERT + context)
    relationship_type: str = ""  # FAMILY, FRIEND, COLLEAGUE, ACQUAINTANCE
    relationship_subtype: str = ""  # SPOUSE, PARENT, SIBLING, COWORKER, etc.

    # Context
    social_context: str = ""  # nuclear_family, work, friends, etc.
    intimacy_level: str = ""  # ACQUAINTANCE, CASUAL, CLOSE, INTIMATE
    location_pattern: str = ""  # Common location (Home, Office, etc.)

    # Emotional role & significance
    # Values: MENTOR, CONFIDANT, ENERGY_SOURCE, SUPPORT_GIVER, PLAYMATE, etc.
    emotional_role: str = ""
    emotional_valence_avg: float = 0.0  # -1.0 (negative) to +1.0 (positive)
    emotional_valence_trend: float = 0.0  # Warming (+) or cooling (-)
    dominant_emotion: str = ""  # Most frequent emotion in interactions

    # Relationship phase
    # Values: FORMING, STABLE, DEEPENING, COOLING, DORMANT, ESTRANGED
    relationship_phase: str = "FORMING"

    # Interaction patterns
    interaction_modalities: List[str] = field(default_factory=list)  # in_person, phone, text
    typical_activities: List[str] = field(default_factory=list)  # meal, work, recreation

    # Aggregated data
    emotions: Dict[str, int] = field(default_factory=dict)  # emotion -> count
    sentiment_trajectory: List[Dict[str, Any]] = field(default_factory=list)  # Recent sentiments

    # Tracking
    interaction_count: int = 1
    confidence: float = 0.5
    source_event_ids: List[str] = field(default_factory=list)
    canonical_entity_id: str = ""  # Link to KG entity cluster
    is_new: bool = True


@dataclass
class GapCandidate:
    """
    Knowledge gap for P06 active learning.

    Represents uncertainty that could be resolved by asking the user.
    """

    gap_id: str
    gap_type: str  # AMBIGUITY, CONTRADICTION, LOW_CONFIDENCE, MISSING
    related_entity_id: str
    entropy_score: float
    priority: str  # HIGH, MEDIUM, LOW
    context_json: str = "{}"
    candidate_values: List[str] = field(default_factory=list)


# =============================================================================
# R5 Aggregate Types (Dream Exploration)
# =============================================================================


@dataclass
class CounterfactualScenario:
    """
    What-if scenario generated in R5.

    Explores alternative outcomes by perturbing episode parameters.
    """

    scenario_id: str
    base_episode_id: str
    perturbation_type: str  # TIME, PARTICIPANT, LOCATION, ACTION
    perturbation_target: str
    original_outcome: str
    counterfactual_outcome: str
    probability_shift: float
    utility_delta: float


@dataclass
class Insight:
    """
    Creative insight from R5 dream exploration.

    Discovers non-obvious connections between concepts.
    """

    insight_id: str
    insight_type: str  # BRIDGE, PATTERN, ANOMALY, PREDICTION
    concept_a_id: str
    concept_b_id: str
    pmi_score: float  # Pointwise mutual information
    novelty_score: float
    relevance_score: float
    natural_language: str  # Human-readable description
    evidence_ids: List[str] = field(default_factory=list)


@dataclass
class RoutineOptimization:
    """
    Routine improvement suggestion from R5.

    Identifies bottlenecks in repeated behavioral patterns.
    """

    routine_id: str
    routine_name: str
    bottleneck_step: str
    bottleneck_position: int
    value_drop: float
    suggested_action: str
    expected_improvement: float


@dataclass
class ProspectiveMemory:
    """
    Future intention/reminder from R5.

    Represents something the user wants to remember to do.
    """

    prosp_id: str
    intention_type: str  # GOAL, REMINDER, DEADLINE, HABIT
    description: str
    trigger_condition: str
    action_to_take: str
    deadline_ts: Optional[int] = None  # MILLISECONDS (optional)
    importance: float = 0.5
    source_episode_id: Optional[str] = None
    # Issue 7.7: Temporal anchor context for prospective memories
    anchor_time_utc: Optional[int] = None  # When user expressed the intention (MILLISECONDS)
    original_temporal_expr: Optional[str] = None  # Original expression ("next week", "tomorrow")


# =============================================================================
# R6 Aggregate Types (Reconciliation Summary)
# =============================================================================


@dataclass
class EventStatusUpdate:
    """
    Status update for source event in st_hipp_events (R6).

    Tracks the transition from PENDING to PROCESSED/SKIPPED/etc.
    """

    event_id: str
    old_status: str
    new_status: str
    expected_version: int


@dataclass
class TruthWrite:
    """
    Staged write to truth layer (R6).

    Accumulated during R6, committed atomically in R7.
    """

    layer: str  # st_epi, st_sem, st_procedural, etc.
    operation: str  # INSERT, UPDATE, ARCHIVE, TOMBSTONE
    record_id: str
    idempotency_key: str
    source_event_ids: List[str] = field(default_factory=list)


@dataclass
class ReconciliationSummary:
    """
    Summary statistics for R6 reconciliation decisions.

    Provides counts of each action type for metrics/audit.
    """

    reinforce_count: int = 0
    extend_count: int = 0
    create_count: int = 0
    evolve_count: int = 0
    contradict_count: int = 0
    prune_count: int = 0
    skip_count: int = 0

    @property
    def total_processed(self) -> int:
        """Total events with decisions (excluding SKIP)."""
        return (
            self.reinforce_count
            + self.extend_count
            + self.create_count
            + self.evolve_count
            + self.contradict_count
            + self.prune_count
        )

    @property
    def total_all(self) -> int:
        """Total events including skipped."""
        return self.total_processed + self.skip_count


# =============================================================================
# R7 Aggregate Types (Commit Results)
# =============================================================================


@dataclass
class WriteResult:
    """
    Result of a single write operation in R7.

    Tracks success/failure for audit and retry logic.
    """

    table: str
    record_id: str
    operation: str  # INSERT, UPDATE, ARCHIVE, TOMBSTONE
    success: bool
    rows_affected: int = 0
    error_message: Optional[str] = None
    idempotency_key: str = ""


@dataclass
class WriteManifest:
    """
    Complete manifest of all writes committed in R7.

    Used for audit trail and rollback planning.
    """

    cycle_id: str
    total_writes: int = 0
    successful_writes: int = 0
    failed_writes: int = 0
    tables_touched: List[str] = field(default_factory=list)
    write_results: List[WriteResult] = field(default_factory=list)


# =============================================================================
# R8 Aggregate Types (Emission)
# =============================================================================


@dataclass
class EmittedEvent:
    """
    Event emitted to outbox in R8.

    Published to external consumers after cycle completion.
    """

    event_id: str
    topic: str
    payload_summary: str  # Brief description, not full payload
    timestamp: int  # MILLISECONDS


@dataclass
class CycleSummary:
    """
    Complete summary of consolidation cycle (R8 output).

    Final accounting of what happened in this cycle.
    """

    cycle_id: str
    batch_id: str
    events_processed: int
    events_skipped: int
    episodes_created: int
    entities_created: int
    edges_created: int
    insights_generated: int
    gaps_detected: int
    writes_committed: int
    writes_failed: int
    duration_ms: int
    started_at: int  # MILLISECONDS
    completed_at: int  # MILLISECONDS
    final_status: str  # SUCCESS, PARTIAL, FAILED


# =============================================================================
# P03PhaseOutputs - Main Container
# =============================================================================


@dataclass
class P03PhaseOutputs:
    """
    Container for aggregated outputs from each phase R0-R8.

    Unlike per-event state (P03EventState), these are batch-level aggregates.
    Each phase populates its section; downstream phases read as needed.

    Usage:
        outputs = P03PhaseOutputs()
        # R1 populates:
        outputs.r1_scored_events.append(ScoredEvent(...))
        outputs.r1_total_importance = sum(...)
        # R2 reads R1, populates:
        outputs.r2_clusters.append(EpisodeCluster(...))
        # etc.
    """

    # =========================================================================
    # R0 OUTPUTS (Batch Selection)
    # =========================================================================
    r0_selection_strategy: str = "FIFO"  # FIFO, IMPORTANCE, HYBRID
    r0_selection_reason: str = ""

    # =========================================================================
    # R1 OUTPUTS (Importance Scoring)
    # =========================================================================
    r1_scored_events: List[ScoredEvent] = field(default_factory=list)
    r1_hebbian_updates: List[HebbianEdgeUpdate] = field(default_factory=list)
    r1_audit_records: List[Any] = field(default_factory=list)  # AuditRecord for R7 write
    r1_total_importance: float = 0.0
    r1_avg_importance: float = 0.0
    r1_max_importance: float = 0.0
    r1_min_importance: float = 0.0
    r1_importance_histogram: Dict[str, int] = field(default_factory=dict)

    # =========================================================================
    # R2 OUTPUTS (Episode Clustering)
    # =========================================================================
    r2_clusters: List[EpisodeCluster] = field(default_factory=list)
    r2_noise_event_ids: List[str] = field(default_factory=list)
    r2_cluster_count: int = 0
    r2_avg_cluster_size: float = 0.0
    r2_clustering_params: Dict[str, Any] = field(default_factory=dict)

    # =========================================================================
    # R3 OUTPUTS (Reconciliation/Dedup/Decay)
    # =========================================================================
    r3_dedup_merges: List[DedupMerge] = field(default_factory=list)
    r3_decay_updates: List[DecayUpdate] = field(default_factory=list)
    r3_archive_candidates: List[str] = field(default_factory=list)
    r3_prune_candidates: List[str] = field(default_factory=list)
    r3_resurrection_candidates: List[str] = field(default_factory=list)

    # =========================================================================
    # R4 OUTPUTS (Knowledge Graph)
    # =========================================================================
    r4_new_entities: List[KGEntity] = field(default_factory=list)
    r4_updated_entities: List[KGEntityUpdate] = field(default_factory=list)
    r4_new_edges: List[KGEdge] = field(default_factory=list)
    r4_updated_edges: List[KGEdgeUpdate] = field(default_factory=list)
    r4_causal_edges: List[CausalEdge] = field(default_factory=list)
    r4_gap_candidates: List[GapCandidate] = field(default_factory=list)
    # Social relationships for st_social (disambiguates "Sarah from work" vs "Sarah wife")
    r4_social_entities: List[SocialRelationship] = field(default_factory=list)

    # =========================================================================
    # R5 OUTPUTS (Dream Exploration)
    # =========================================================================
    r5_counterfactuals: List[CounterfactualScenario] = field(default_factory=list)
    r5_insights: List[Insight] = field(default_factory=list)
    r5_routine_optimizations: List[RoutineOptimization] = field(default_factory=list)
    r5_routine_candidates: List["RoutineCandidate"] = field(default_factory=list)  # GAP-003
    r5_prospective_memories: List[ProspectiveMemory] = field(default_factory=list)
    r5_intent_signals: List["IntentSignal"] = field(default_factory=list)  # GAP-001
    r5_skipped: bool = False
    r5_skip_reason: Optional[str] = None

    # =========================================================================
    # R6 OUTPUTS (Reconciliation Summary)
    # =========================================================================
    # M5 W3: Structured R6 output with validated manifest (from Issue 5.1.8)
    r6_output: Optional[R6Output] = None
    r6_summary: ReconciliationSummary = field(default_factory=ReconciliationSummary)
    r6_event_updates: List[EventStatusUpdate] = field(default_factory=list)
    r6_truth_writes: List[TruthWrite] = field(default_factory=list)

    # =========================================================================
    # R7 OUTPUTS (Commit Results)
    # =========================================================================
    # M5 W4: WriteResult from DecisionRouter (from Issue 5.2.1)
    r7_result: Optional[WriteResult] = None
    r7_manifest: Optional[WriteManifest] = None
    r7_success: bool = False
    r7_error: Optional[str] = None

    # =========================================================================
    # R8 OUTPUTS (Emission)
    # =========================================================================
    r8_emitted_events: List[EmittedEvent] = field(default_factory=list)
    r8_cycle_summary: Optional[CycleSummary] = None
    r8_success: bool = False

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_r6_counts(self) -> ReconciliationSummary:
        """Get or create R6 reconciliation summary."""
        return self.r6_summary

    def set_r6_counts(
        self,
        reinforce: int = 0,
        extend: int = 0,
        create: int = 0,
        evolve: int = 0,
        contradict: int = 0,
        prune: int = 0,
        skip: int = 0,
    ) -> None:
        """Set R6 reconciliation counts."""
        self.r6_summary = ReconciliationSummary(
            reinforce_count=reinforce,
            extend_count=extend,
            create_count=create,
            evolve_count=evolve,
            contradict_count=contradict,
            prune_count=prune,
            skip_count=skip,
        )

    def total_kg_changes(self) -> int:
        """Total KG entities and edges created/updated."""
        return (
            len(self.r4_new_entities)
            + len(self.r4_updated_entities)
            + len(self.r4_new_edges)
            + len(self.r4_updated_edges)
            + len(self.r4_causal_edges)
        )

    def total_insights(self) -> int:
        """Total creative outputs from R5."""
        return (
            len(self.r5_counterfactuals)
            + len(self.r5_insights)
            + len(self.r5_routine_optimizations)
            + len(self.r5_routine_candidates)
            + len(self.r5_prospective_memories)
            + len(self.r5_intent_signals)
        )

    def to_summary_dict(self) -> Dict[str, Any]:
        """
        Convert to summary dict for logging/metrics.

        Returns counts, not full data, for compact representation.
        """
        return {
            "r1": {
                "total_importance": self.r1_total_importance,
                "avg_importance": self.r1_avg_importance,
                "hebbian_updates": len(self.r1_hebbian_updates),
            },
            "r2": {
                "cluster_count": self.r2_cluster_count,
                "noise_count": len(self.r2_noise_event_ids),
                "avg_cluster_size": self.r2_avg_cluster_size,
            },
            "r3": {
                "dedup_merges": len(self.r3_dedup_merges),
                "archive_candidates": len(self.r3_archive_candidates),
                "prune_candidates": len(self.r3_prune_candidates),
            },
            "r4": {
                "new_entities": len(self.r4_new_entities),
                "new_edges": len(self.r4_new_edges),
                "causal_edges": len(self.r4_causal_edges),
                "gap_candidates": len(self.r4_gap_candidates),
            },
            "r5": {
                "skipped": self.r5_skipped,
                "insights": len(self.r5_insights),
                "counterfactuals": len(self.r5_counterfactuals),
                "prospective_memories": len(self.r5_prospective_memories),
                "intent_signals": len(self.r5_intent_signals),
            },
            "r6": {
                "reinforce": self.r6_summary.reinforce_count,
                "extend": self.r6_summary.extend_count,
                "create": self.r6_summary.create_count,
                "evolve": self.r6_summary.evolve_count,
                "contradict": self.r6_summary.contradict_count,
                "prune": self.r6_summary.prune_count,
                "skip": self.r6_summary.skip_count,
            },
            "r7": {
                "success": self.r7_success,
                "writes": self.r7_manifest.total_writes if self.r7_manifest else 0,
            },
            "r8": {
                "success": self.r8_success,
                "events_emitted": len(self.r8_emitted_events),
            },
        }
