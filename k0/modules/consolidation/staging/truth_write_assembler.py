"""
TruthWriteAssembler — Issue 5.1.6

Assembles staged writes for all truth layers from phase outputs.
Converts R2-R5 phase outputs into StagedWrite operations for R7 commit.

Spec Reference:
    - Dossier §4.7.2 (R6 Staging — Truth Layer Assembly)
    - Dossier §6 (Truth Layer Schemas)
    - M5_EXECUTION.md Issue 5.1.6

Target Layers:
    - st_epi (R2 EpisodeCluster → episodic memory)
    - st_sem (R3 CREATE/EXTEND decisions → semantic patterns)
    - st_procedural (R4/R5 routines → procedural memory)
    - st_social (R4 social entities → social memory)
    - st_prospective (R5 ProspectiveMemory → future intentions)
    - st_learning_queue (R4 GapCandidate → P06 queue)

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.modules.consolidation.dream.models import (
    CounterfactualScenario,
    Insight,
    RoutineOptimization,
)
from k0.pipelines.p03.phase_outputs import (
    EpisodeCluster,
    GapCandidate,
    ProspectiveMemory,
    SocialRelationship,
)
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_EPI,
    LAYER_ST_LEARNING_QUEUE,
    LAYER_ST_PROCEDURAL,
    LAYER_ST_PROSPECTIVE,
    LAYER_ST_SEM,
    LAYER_ST_SOCIAL,
    StagedWrite,
)

from .idempotency import IdempotencyKeyGenerator

# =============================================================================
# Constants
# =============================================================================

# Actions that create new semantic records
CREATE_ACTIONS = frozenset({ReconciliationAction.CREATE})

# Actions that update existing semantic records
UPDATE_ACTIONS = frozenset(
    {
        ReconciliationAction.REINFORCE,
        ReconciliationAction.EXTEND,
        ReconciliationAction.EVOLVE,
    }
)

# Actions that archive/prune records
ARCHIVE_ACTIONS = frozenset({ReconciliationAction.PRUNE})


def _now_ms() -> int:
    """Return current time in milliseconds since epoch."""
    return int(time.time() * 1000)


# =============================================================================
# AssembledWrite Helper
# =============================================================================


@dataclass
class AssembledWrite:
    """
    Metadata about an assembled write for tracking.

    Attributes:
        write: The StagedWrite object
        layer: Target layer name
        record_id: Primary key
        source: Description of source phase/data
    """

    write: StagedWrite
    layer: str
    record_id: str
    source: str


# =============================================================================
# TruthWriteAssembler Class
# =============================================================================


class TruthWriteAssembler:
    """
    Assembles staged writes for truth layers from phase outputs.

    Converts R2-R5 outputs into StagedWrite operations ready for R7 commit.
    Each layer has specific schema requirements from Dossier §6.

    Attributes:
        idempotency: Key generator for deterministic idempotency keys
        source_phase: Phase name for provenance (default "R6")
        tenant_id: Tenant identifier for multi-tenant isolation
        space_id: Space identifier for family/user isolation
    """

    def __init__(
        self,
        idempotency_gen: IdempotencyKeyGenerator,
        source_phase: str = "R6",
        tenant_id: str = "default",
        space_id: str = "default",
    ) -> None:
        """
        Initialize assembler with idempotency generator.

        Args:
            idempotency_gen: Generator for idempotency keys
            source_phase: Phase name for provenance tracking
            tenant_id: Tenant identifier for multi-tenant isolation
            space_id: Space identifier for family/user isolation
        """
        self.idempotency = idempotency_gen
        self.source_phase = source_phase
        self.tenant_id = tenant_id
        self.space_id = space_id

    # =========================================================================
    # st_epi — Episodic Memory (from R2 EpisodeCluster)
    # =========================================================================

    def assemble_epi_writes(
        self,
        clusters: List[EpisodeCluster],
        event_states: Dict[str, P03EventState],
    ) -> List[StagedWrite]:
        """
        Assemble st_epi writes from R2 episode clusters.

        Each cluster becomes an episodic memory record. Events in the
        cluster contribute to the episode's provenance.

        Args:
            clusters: R2 episode clusters
            event_states: Event states for provenance lookup

        Returns:
            List of StagedWrite for st_epi inserts
        """
        if not clusters:
            return []

        writes: List[StagedWrite] = []

        for cluster in clusters:
            # Extract source event IDs from cluster members
            source_ids = cluster.member_event_ids.copy()

            # Build episode record_data per Dossier §6.1
            record_data = self._build_epi_record_data(cluster, event_states)

            # Generate idempotency key
            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_EPI,
                cluster.cluster_id,
            )

            # Create INSERT write
            write = StagedWrite.insert(
                layer=LAYER_ST_EPI,
                record_id=cluster.cluster_id,
                data=record_data,
                phase=self.source_phase,
                event_ids=source_ids,
            )
            # Override idempotency key with proper format
            write.idempotency_key = idem_key

            writes.append(write)

        return writes

    def _build_epi_record_data(
        self, cluster: EpisodeCluster, event_states: Dict[str, P03EventState]
    ) -> Dict[str, Any]:
        """
        Build st_epi record_data from EpisodeCluster.

        Schema (actual st_epi table columns):
            episode_id, tenant_id, space_id, version, episode_summary,
            episode_type, start_time_utc, end_time_utc, primary_location,
            location_type, participants_json, participant_count,
            embedding_id, cluster_id, cluster_confidence, source_events_json,
            source_event_count, archival_status, created_at, updated_at, valid_from
        """
        now_ms = _now_ms()
        member_ids = list(cluster.member_event_ids)

        # Get embedding_id from cluster centroid or first member event
        embedding_id = cluster.centroid_embedding_id
        if embedding_id is None and member_ids and event_states:
            first_event = event_states.get(member_ids[0])
            if first_event:
                embedding_id = first_event.embedding_id

        return {
            "episode_id": cluster.cluster_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "version": 1,
            "episode_summary": cluster.summary or cluster.title or "Untitled episode",
            "episode_type": cluster.activity_type or "GENERAL",
            "start_time_utc": cluster.temporal_start,
            "end_time_utc": cluster.temporal_end,
            "primary_location": cluster.location_hint,
            "participants_json": cluster.participants_json,
            "participant_count": len(json.loads(cluster.participants_json or "[]")),
            "embedding_id": embedding_id,
            "cluster_id": cluster.cluster_id,
            "cluster_confidence": cluster.cohesion_score or 0.5,
            "source_events_json": json.dumps(member_ids),
            "source_event_count": len(member_ids),
            "archival_status": "ACTIVE",
            "created_at": now_ms,
            "updated_at": now_ms,
            "valid_from": now_ms,
        }

    # =========================================================================
    # st_sem — Semantic Memory (from R3 reconciliation decisions)
    # =========================================================================

    def assemble_sem_writes(
        self,
        event_states: Dict[str, P03EventState],
    ) -> List[StagedWrite]:
        """
        Assemble st_sem writes from R3 CREATE/EXTEND/REINFORCE decisions.

        Events with CREATE action → INSERT new pattern
        Events with EXTEND/EVOLVE/REINFORCE → UPDATE existing pattern

        Args:
            event_states: Event states with reconciliation decisions

        Returns:
            List of StagedWrite for st_sem operations
        """
        if not event_states:
            return []

        writes: List[StagedWrite] = []

        for event_id, state in event_states.items():
            action = state.reconciliation_action
            if action is None:
                continue

            if action in CREATE_ACTIONS:
                write = self._create_sem_insert(event_id, state)
                if write:
                    writes.append(write)

            elif action in UPDATE_ACTIONS:
                write = self._create_sem_update(event_id, state)
                if write:
                    writes.append(write)

            elif action in ARCHIVE_ACTIONS:
                write = self._create_sem_archive(event_id, state)
                if write:
                    writes.append(write)

        return writes

    def _create_sem_insert(
        self,
        event_id: str,
        state: P03EventState,
    ) -> Optional[StagedWrite]:
        """Create st_sem INSERT for CREATE action."""
        import json

        # Pattern ID comes from event being promoted to pattern
        pattern_id = f"sem_{event_id}"
        now = _now_ms()

        # Extract pattern info from event state
        pattern_type = getattr(state, "content_type", "general").upper()
        if pattern_type not in ("ROUTINE", "PREFERENCE", "THEME", "RELATIONSHIP", "GOAL", "VALUE"):
            pattern_type = "THEME"  # Default valid type

        pattern_name = getattr(state, "text", None) or f"Pattern from {event_id}"
        if len(pattern_name) > 200:
            pattern_name = pattern_name[:197] + "..."

        record_data = {
            "pattern_id": pattern_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "pattern_type": pattern_type,
            "pattern_name": pattern_name,
            "embedding_id": state.embedding_id,
            "source_episodes_json": json.dumps([event_id]),
            "source_episode_count": 1,
            "confidence_score": state.confidence or 0.5,
            "observation_count": 1,
            "first_observed_at": now,
            "last_observed_at": now,
            "created_at": now,
            "updated_at": now,
            "valid_from": now,
            "archival_status": "ACTIVE",
        }

        idem_key = self.idempotency.for_truth_write(LAYER_ST_SEM, pattern_id)

        write = StagedWrite.insert(
            layer=LAYER_ST_SEM,
            record_id=pattern_id,
            data=record_data,
            phase=self.source_phase,
            event_ids=[event_id],
        )
        write.idempotency_key = idem_key

        return write

    def _create_sem_update(
        self,
        event_id: str,
        state: P03EventState,
    ) -> Optional[StagedWrite]:
        """Create st_sem UPDATE for REINFORCE/EXTEND/EVOLVE actions."""
        # Target pattern is the best match
        pattern_id = state.best_match_id
        if not pattern_id:
            return None

        now = _now_ms()
        # Partial update: increment observation count, update timestamp
        # st_sem uses observation_count, confidence_score, last_observed_at
        record_data = {
            "observation_count": 1,  # Will be incremented by R7 (or use SQL expression)
            "last_observed_at": now,
            "updated_at": now,
        }

        # Use expected version 0 for first update attempt
        idem_key = self.idempotency.for_truth_write(LAYER_ST_SEM, pattern_id)

        write = StagedWrite.update(
            layer=LAYER_ST_SEM,
            record_id=pattern_id,
            data=record_data,
            phase=self.source_phase,
            expected_version=0,  # Will be resolved at R7
            event_ids=[event_id],
        )
        write.idempotency_key = idem_key

        return write

    def _create_sem_archive(
        self,
        event_id: str,
        state: P03EventState,
    ) -> Optional[StagedWrite]:
        """Create st_sem ARCHIVE for PRUNE action."""
        pattern_id = state.best_match_id
        if not pattern_id:
            return None

        reason = state.reconciliation_reason or "decay"

        write = StagedWrite.archive(
            layer=LAYER_ST_SEM,
            record_id=pattern_id,
            phase=self.source_phase,
            reason=reason,
            event_ids=[event_id],
        )

        return write

    # =========================================================================
    # st_procedural — Procedural Memory (from R5 routines)
    # =========================================================================

    def assemble_procedural_writes(
        self,
        routines: List[Dict[str, Any]],
    ) -> List[StagedWrite]:
        """
        Assemble st_procedural writes from R5 routine optimizations.

        Args:
            routines: List of routine dicts with routine_id and data

        Returns:
            List of StagedWrite for st_procedural
        """
        if not routines:
            return []

        writes: List[StagedWrite] = []

        for routine in routines:
            routine_id = routine.get("routine_id")
            if not routine_id:
                continue

            is_new = routine.get("is_new", True)

            if is_new:
                record_data = {
                    "routine_id": routine_id,
                    "routine_name": routine.get("routine_name", ""),
                    "steps_json": routine.get("steps_json", "[]"),
                    "frequency": routine.get("frequency", 0),
                    "avg_duration_ms": routine.get("avg_duration_ms", 0),
                    "created_at_ms": _now_ms(),
                }

                idem_key = self.idempotency.for_truth_write(
                    LAYER_ST_PROCEDURAL,
                    routine_id,
                )

                write = StagedWrite.insert(
                    layer=LAYER_ST_PROCEDURAL,
                    record_id=routine_id,
                    data=record_data,
                    phase=self.source_phase,
                    event_ids=routine.get("source_event_ids", []),
                )
                write.idempotency_key = idem_key
                writes.append(write)

        return writes

    # =========================================================================
    # st_social — Social Memory (from R4 SocialRelationship)
    # =========================================================================

    def assemble_social_writes(
        self,
        social_relationships: List[SocialRelationship],
    ) -> List[StagedWrite]:
        """
        Assemble st_social writes from R4 SocialRelationship objects.

        Maps SocialRelationship dataclass fields to st_social table columns
        as defined in migration 0030_st_social and enriched by 0054.

        Args:
            social_relationships: List of SocialRelationship from R4

        Returns:
            List of StagedWrite for st_social
        """
        if not social_relationships:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for rel in social_relationships:
            # Use relationship_id as the primary key
            if not rel.relationship_id:
                continue

            if rel.is_new:
                # Map SocialRelationship fields to st_social columns
                record_data = {
                    # Identity (primary key)
                    "relationship_id": rel.relationship_id,
                    "tenant_id": self.tenant_id,
                    "space_id": self.space_id,
                    # Relationship endpoints
                    "actor_a_id": rel.actor_a_id,
                    "actor_b_id": rel.actor_b_id,
                    # Versioning
                    "version": 1,
                    "is_canonical": True,
                    # Relationship type
                    "relationship_type": rel.relationship_type or "ACQUAINTANCE",
                    "relationship_subtype": rel.relationship_subtype or None,
                    "relationship_label": rel.actor_b_name or None,
                    # Relationship strength
                    "interaction_count": rel.interaction_count,
                    "avg_sentiment": rel.emotional_valence_avg,
                    "relationship_strength": rel.confidence,
                    "intimacy_level": rel.intimacy_level or "ACQUAINTANCE",
                    # Temporal
                    "first_interaction_at": now_ms,
                    "last_interaction_at": now_ms,
                    "interaction_frequency": None,
                    # Source episodes
                    "source_episodes_json": json.dumps(rel.source_event_ids),
                    # Truth tracking
                    "observation_count": 1,
                    "confidence_score": rel.confidence,
                    "decay_factor": 1.0,
                    # Lifecycle
                    "archival_status": "ACTIVE",
                    # Timestamps
                    "created_at": now_ms,
                    "updated_at": now_ms,
                    "valid_from": now_ms,
                    # UltraBERT enrichment (migration 0054)
                    "ultrabert_relation_types": json.dumps(rel.ultrabert_relation_types),
                    "emotional_role": rel.emotional_role or None,
                    "emotional_valence_avg": rel.emotional_valence_avg,
                    "emotional_valence_trend": rel.emotional_valence_trend,
                    "relationship_phase": rel.relationship_phase or "FORMING",
                    "interaction_modalities_json": json.dumps(rel.interaction_modalities),
                    "typical_activities_json": json.dumps(rel.typical_activities),
                    "sentiment_trajectory_json": json.dumps(rel.sentiment_trajectory),
                    "emotions_json": json.dumps(rel.emotions),
                    "dominant_emotion": rel.dominant_emotion or None,
                    "canonical_entity_id": rel.canonical_entity_id or None,
                }

                idem_key = self.idempotency.for_truth_write(
                    LAYER_ST_SOCIAL,
                    rel.relationship_id,
                )

                write = StagedWrite.insert(
                    layer=LAYER_ST_SOCIAL,
                    record_id=rel.relationship_id,
                    data=record_data,
                    phase=self.source_phase,
                    event_ids=rel.source_event_ids,
                )
                write.idempotency_key = idem_key
                writes.append(write)

        return writes

    # =========================================================================
    # st_prospective — Prospective Memory (from R5 ProspectiveMemory)
    # =========================================================================

    def assemble_prospective_writes(
        self,
        intentions: List[ProspectiveMemory],
    ) -> List[StagedWrite]:
        """
        Assemble st_prospective writes from R5 prospective memories.

        Args:
            intentions: List of ProspectiveMemory objects

        Returns:
            List of StagedWrite for st_prospective inserts
        """
        if not intentions:
            return []

        writes: List[StagedWrite] = []

        for intention in intentions:
            record_data = {
                "prosp_id": intention.prosp_id,
                "intention_type": intention.intention_type,
                "description": intention.description,
                "trigger_condition": intention.trigger_condition,
                "action_to_take": intention.action_to_take,
                "deadline_ts": intention.deadline_ts,
                "importance": intention.importance,
                "source_episode_id": intention.source_episode_id,
                "created_at_ms": _now_ms(),
            }

            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_PROSPECTIVE,
                intention.prosp_id,
            )

            source_ids = [intention.source_episode_id] if intention.source_episode_id else []

            write = StagedWrite.insert(
                layer=LAYER_ST_PROSPECTIVE,
                record_id=intention.prosp_id,
                data=record_data,
                phase=self.source_phase,
                event_ids=source_ids,
            )
            write.idempotency_key = idem_key
            writes.append(write)

        return writes

    # =========================================================================
    # st_sem — R5 Insight Writes (from BGT-SM)
    # Issue 8.1.16 — TruthWriteAssembler R5 Output Assembly
    # =========================================================================

    def assemble_insight_writes(
        self,
        insights: List[Insight],
    ) -> List[StagedWrite]:
        """
        Assemble st_sem writes from R5 insights.

        Insights from BGT-SM (Bisociative Graph Traversal) are written
        to st_sem with pattern_type='INSIGHT'.

        Args:
            insights: List of Insight objects from R5

        Returns:
            List of StagedWrite for st_sem inserts
        """
        if not insights:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for insight in insights:
            # Pattern ID is derived from insight_id
            pattern_id = f"insight_{insight.insight_id}"

            # Build st_sem record per Issue 8.1.16 spec
            record_data = {
                "pattern_id": pattern_id,
                "tenant_id": self.tenant_id,
                "space_id": self.space_id,
                "pattern_type": "INSIGHT",  # R5 insight type
                "pattern_name": insight.description[:200] if insight.description else "Untitled insight",
                "embedding_id": None,  # Insights don't have embeddings yet
                "source_episodes_json": json.dumps(list(insight.supporting_evidence)),
                "source_episode_count": len(insight.supporting_evidence),
                "confidence_score": insight.confidence,
                "novelty_score": insight.novelty_score,
                "pmi_score": insight.pmi_score,
                "semantic_distance": insight.semantic_distance,
                "concept_a_id": insight.concept_a_id,
                "concept_b_id": insight.concept_b_id,
                "insight_type": insight.insight_type,
                "relevance_score": insight.relevance_score,
                "serendipity_score": insight.serendipity_score,
                "observation_count": 1,
                "first_observed_at": now_ms,
                "last_observed_at": now_ms,
                "created_at": now_ms,
                "updated_at": now_ms,
                "valid_from": now_ms,
                "archival_status": "ACTIVE",
            }

            idem_key = self.idempotency.for_truth_write(LAYER_ST_SEM, pattern_id)

            write = StagedWrite.insert(
                layer=LAYER_ST_SEM,
                record_id=pattern_id,
                data=record_data,
                phase="R5",
                event_ids=list(insight.supporting_evidence),
            )
            write.idempotency_key = idem_key
            writes.append(write)

        return writes

    # =========================================================================
    # st_prospective — R5 Counterfactual Writes (from CPN)
    # Issue 8.1.16 — TruthWriteAssembler R5 Output Assembly
    # =========================================================================

    def assemble_counterfactual_writes(
        self,
        counterfactuals: List[CounterfactualScenario],
    ) -> List[StagedWrite]:
        """
        Assemble st_prospective writes from R5 counterfactual scenarios.

        Counterfactuals from CPN are written to st_prospective with
        type='COUNTERFACTUAL'.

        Args:
            counterfactuals: List of CounterfactualScenario from R5

        Returns:
            List of StagedWrite for st_prospective inserts
        """
        if not counterfactuals:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for scenario in counterfactuals:
            record_data = {
                "prosp_id": scenario.scenario_id,
                "tenant_id": self.tenant_id,
                "space_id": self.space_id,
                "intention_type": "COUNTERFACTUAL",  # Type for counterfactual scenarios
                "description": scenario.counterfactual_outcome[:500] if scenario.counterfactual_outcome else "",
                "trigger_condition": f"If: {scenario.perturbation_target}",
                "action_to_take": scenario.counterfactual_outcome,
                "original_outcome": scenario.original_outcome,
                "scenario_type": scenario.scenario_type,  # UPWARD, DOWNWARD, SEMIFACTUAL
                "base_episode_id": scenario.base_episode_id,
                "perturbation_target": scenario.perturbation_target,
                "plausibility": scenario.plausibility,
                "success_probability": scenario.success_probability,
                "utility_delta": scenario.utility_delta,
                "importance": scenario.plausibility * scenario.success_probability,  # Derived
                "confidence": scenario.plausibility,
                "source_episode_id": scenario.base_episode_id,
                "deadline_ts": None,
                "status": "ACTIVE",
                "created_at_ms": now_ms,
            }

            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_PROSPECTIVE,
                scenario.scenario_id,
            )

            write = StagedWrite.insert(
                layer=LAYER_ST_PROSPECTIVE,
                record_id=scenario.scenario_id,
                data=record_data,
                phase="R5",
                event_ids=[scenario.base_episode_id] if scenario.base_episode_id else [],
            )
            write.idempotency_key = idem_key
            writes.append(write)

        return writes

    # =========================================================================
    # st_procedural — R5 Routine Optimization Writes (from TDL-HCO)
    # Issue 8.1.16 — TruthWriteAssembler R5 Output Assembly
    # =========================================================================

    def assemble_routine_optimization_writes(
        self,
        optimizations: List[RoutineOptimization],
    ) -> List[StagedWrite]:
        """
        Assemble st_procedural writes from R5 routine optimizations.

        Routine optimizations from TDL-HCO identify bottlenecks in
        procedural patterns and suggest improvements.

        Args:
            optimizations: List of RoutineOptimization from R5

        Returns:
            List of StagedWrite for st_procedural updates
        """
        if not optimizations:
            return []

        writes: List[StagedWrite] = []
        now_ms = _now_ms()

        for opt in optimizations:
            # Routine optimizations create update records
            # They target existing routines with improvement suggestions
            record_data = {
                "routine_id": opt.routine_id,
                "tenant_id": self.tenant_id,
                "space_id": self.space_id,
                "routine_name": opt.routine_name,
                "bottleneck_step": opt.bottleneck_step,
                "bottleneck_position": opt.bottleneck_position,
                "value_drop": opt.value_drop,
                "suggested_action": opt.suggested_action,
                "expected_improvement": opt.expected_improvement,
                "optimization_confidence": opt.confidence,
                "optimization_status": "PENDING",  # User hasn't acted yet
                "updated_at": now_ms,
            }

            # Use INSERT for new optimization records
            # (Each optimization is a new suggestion, not an update to existing)
            optimization_id = f"opt_{opt.routine_id}_{opt.bottleneck_position}"

            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_PROCEDURAL,
                optimization_id,
            )

            write = StagedWrite.insert(
                layer=LAYER_ST_PROCEDURAL,
                record_id=optimization_id,
                data=record_data,
                phase="R5",
                event_ids=[],
            )
            write.idempotency_key = idem_key
            writes.append(write)

        return writes

    # =========================================================================
    # st_learning_queue — P06 Gap Queue (from R4 GapCandidate)
    # =========================================================================

    def assemble_learning_queue_writes(
        self,
        gaps: List[GapCandidate],
    ) -> List[StagedWrite]:
        """
        Assemble st_learning_queue writes for P06 active learning.

        Args:
            gaps: List of GapCandidate objects from R4

        Returns:
            List of StagedWrite for st_learning_queue inserts
        """
        if not gaps:
            return []

        writes: List[StagedWrite] = []

        for gap in gaps:
            record_data = {
                "gap_id": gap.gap_id,
                "gap_type": gap.gap_type,
                "related_entity_id": gap.related_entity_id,
                "entropy_score": gap.entropy_score,
                "priority": gap.priority,
                "context_json": gap.context_json,
                "candidate_values_json": json.dumps(gap.candidate_values),
                "status": "PENDING",
                "created_at_ms": _now_ms(),
            }

            idem_key = self.idempotency.for_truth_write(
                LAYER_ST_LEARNING_QUEUE,
                gap.gap_id,
            )

            write = StagedWrite.insert(
                layer=LAYER_ST_LEARNING_QUEUE,
                record_id=gap.gap_id,
                data=record_data,
                phase=self.source_phase,
                event_ids=[gap.related_entity_id] if gap.related_entity_id else [],
            )
            write.idempotency_key = idem_key
            writes.append(write)

        return writes

    # =========================================================================
    # Aggregate Assembly
    # =========================================================================

    def assemble_all(
        self,
        clusters: Optional[List[EpisodeCluster]] = None,
        event_states: Optional[Dict[str, P03EventState]] = None,
        routines: Optional[List[Dict[str, Any]]] = None,
        social_relationships: Optional[List[SocialRelationship]] = None,
        intentions: Optional[List[ProspectiveMemory]] = None,
        gaps: Optional[List[GapCandidate]] = None,
        # R5 outputs (Issue 8.1.16)
        insights: Optional[List[Insight]] = None,
        counterfactuals: Optional[List[CounterfactualScenario]] = None,
        routine_optimizations: Optional[List[RoutineOptimization]] = None,
    ) -> Dict[str, List[StagedWrite]]:
        """
        Assemble all truth layer writes from phase outputs.

        Returns writes grouped by layer for easy routing to P03StagedWrites.

        Args:
            clusters: R2 episode clusters
            event_states: Event states with R3 reconciliation
            routines: R5 routine data (legacy format)
            social_relationships: R4 social relationships (SocialRelationship objects)
            intentions: R5 prospective memories
            gaps: R4 gap candidates
            insights: R5 insights from BGT-SM (Issue 8.1.16)
            counterfactuals: R5 counterfactual scenarios from CPN (Issue 8.1.16)
            routine_optimizations: R5 routine optimizations from TDL-HCO (Issue 8.1.16)

        Returns:
            Dict mapping layer name to list of StagedWrite
        """
        result: Dict[str, List[StagedWrite]] = {}

        # st_epi from R2 clusters
        epi_writes = self.assemble_epi_writes(clusters or [], event_states or {})
        if epi_writes:
            result[LAYER_ST_EPI] = epi_writes

        # st_sem from R3 decisions
        sem_writes = self.assemble_sem_writes(event_states or {})
        if sem_writes:
            result[LAYER_ST_SEM] = sem_writes

        # st_sem from R5 insights (Issue 8.1.16)
        insight_writes = self.assemble_insight_writes(insights or [])
        if insight_writes:
            # Merge with existing st_sem writes
            if LAYER_ST_SEM in result:
                result[LAYER_ST_SEM].extend(insight_writes)
            else:
                result[LAYER_ST_SEM] = insight_writes

        # st_procedural from R5 routines (legacy)
        proc_writes = self.assemble_procedural_writes(routines or [])
        if proc_writes:
            result[LAYER_ST_PROCEDURAL] = proc_writes

        # st_procedural from R5 routine optimizations (Issue 8.1.16)
        opt_writes = self.assemble_routine_optimization_writes(routine_optimizations or [])
        if opt_writes:
            # Merge with existing st_procedural writes
            if LAYER_ST_PROCEDURAL in result:
                result[LAYER_ST_PROCEDURAL].extend(opt_writes)
            else:
                result[LAYER_ST_PROCEDURAL] = opt_writes

        # st_social from R4 relationships
        social_writes = self.assemble_social_writes(social_relationships or [])
        if social_writes:
            result[LAYER_ST_SOCIAL] = social_writes

        # st_prospective from R5 intentions
        prosp_writes = self.assemble_prospective_writes(intentions or [])
        if prosp_writes:
            result[LAYER_ST_PROSPECTIVE] = prosp_writes

        # st_prospective from R5 counterfactuals (Issue 8.1.16)
        cf_writes = self.assemble_counterfactual_writes(counterfactuals or [])
        if cf_writes:
            # Merge with existing st_prospective writes
            if LAYER_ST_PROSPECTIVE in result:
                result[LAYER_ST_PROSPECTIVE].extend(cf_writes)
            else:
                result[LAYER_ST_PROSPECTIVE] = cf_writes

        # st_learning_queue from R4 gaps
        queue_writes = self.assemble_learning_queue_writes(gaps or [])
        if queue_writes:
            result[LAYER_ST_LEARNING_QUEUE] = queue_writes

        return result

    def count_writes(
        self,
        assembled: Dict[str, List[StagedWrite]],
    ) -> Dict[str, int]:
        """
        Count writes per layer.

        Args:
            assembled: Dict from assemble_all()

        Returns:
            Dict mapping layer to write count
        """
        return {layer: len(writes) for layer, writes in assembled.items()}


# =============================================================================
# Utility Functions
# =============================================================================


def flatten_writes(assembled: Dict[str, List[StagedWrite]]) -> List[StagedWrite]:
    """
    Flatten assembled writes dict to single list.

    Note: Does NOT respect dependency order. Use
    P03StagedWrites.get_all_writes_ordered() for commit order.

    Args:
        assembled: Dict from TruthWriteAssembler.assemble_all()

    Returns:
        Flat list of all StagedWrite objects
    """
    result: List[StagedWrite] = []
    for writes in assembled.values():
        result.extend(writes)
    return result


def summarize_assembly(assembled: Dict[str, List[StagedWrite]]) -> str:
    """
    Generate human-readable summary of assembled writes.

    Args:
        assembled: Dict from TruthWriteAssembler.assemble_all()

    Returns:
        Multi-line summary string
    """
    lines = ["Truth Write Assembly Summary:"]
    total = 0
    for layer, writes in sorted(assembled.items()):
        count = len(writes)
        total += count
        lines.append(f"  {layer}: {count} writes")
    lines.append(f"  Total: {total} writes")
    return "\n".join(lines)
