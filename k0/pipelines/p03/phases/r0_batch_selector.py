"""
R0 Phase — Batch Selection (Event Ingestion).

M3 Issue 3.2.1: Implement R0 Phase for Event Ingestion from st_hipp_events.

This phase is the entry point for P03 consolidation:
1. Fetch current offset from st_offsets (via OffsetStore)
2. Query st_hipp_events for eligible events after offset
3. Load embeddings from st_vec for selected events (lazy materialization)
4. Build P03BatchEnvelope with context and events
5. Return envelope for R1-R8 processing

Unlike R1-R8 which receive an envelope, R0 CREATES the envelope.

References:
    - Dossier 4.1: R0 Trigger Detection & Batch Selection
    - P03 Checkpoint: k0/pipelines/p03/checkpoint.py
    - M3 Execution: docs/TEMP_EXECUTION_DOCS/M3_EXECUTION.md Issue 3.2.1
"""

from __future__ import annotations

import json
import logging
import struct
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from k0.modules.consolidation.gap_auto_resolver import GapAutoResolver
from k0.pipelines.p03.checkpoint import P03_SOURCE_TOPIC, P03_SUBSCRIBER_ID
from k0.pipelines.p03.context import P03CycleContext
from k0.pipelines.p03.envelope import P03BatchEnvelope
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.observability import P03Error
from k0.pipelines.p03.phase_interface import P03PhaseResult
from k0.pipelines.p03.runner_contract import P03PhaseId

if TYPE_CHECKING:
    from k0.pipelines.p03.phase_interface import P03RunnerContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class R0FieldSpec:
    """Declarative spec for selecting and mapping a st_hipp_events field."""

    select_sql: str
    row_key: str
    state_field: Optional[str] = None
    default: Any = None
    converter: Optional[Callable[[Any], Any]] = None
    phase_consumers: Tuple[P03PhaseId, ...] = (P03PhaseId.R0_INIT,)


def _column(
    name: str,
    *,
    state_field: Optional[str] = None,
    default: Any = None,
    converter: Optional[Callable[[Any], Any]] = None,
    phase_consumers: Tuple[P03PhaseId, ...] = (P03PhaseId.R0_INIT,),
) -> R0FieldSpec:
    return R0FieldSpec(
        select_sql=name,
        row_key=name,
        state_field=state_field,
        default=default,
        converter=converter,
        phase_consumers=phase_consumers,
    )


def _alias(
    select_sql: str,
    row_key: str,
    *,
    state_field: Optional[str] = None,
    default: Any = None,
    converter: Optional[Callable[[Any], Any]] = None,
    phase_consumers: Tuple[P03PhaseId, ...] = (P03PhaseId.R0_INIT,),
) -> R0FieldSpec:
    return R0FieldSpec(
        select_sql=select_sql,
        row_key=row_key,
        state_field=state_field,
        default=default,
        converter=converter,
        phase_consumers=phase_consumers,
    )


def _to_float(value: Any) -> float:
    return float(value)


def _to_int(value: Any) -> int:
    return int(value)


def _phases(*phase_ids: P03PhaseId) -> Tuple[P03PhaseId, ...]:
    return phase_ids


def _normalize_epoch_ms(value: Any) -> int:
    """Normalize second- or millisecond-based epochs to milliseconds."""
    timestamp = int(value)
    return timestamp * 1000 if timestamp < 1_000_000_000_000 else timestamp


R0_FIELD_SPECS: Tuple[R0FieldSpec, ...] = (
    _column(
        "event_id",
        phase_consumers=_phases(
            P03PhaseId.R0_INIT,
            P03PhaseId.R1_SCORE,
            P03PhaseId.R2_CLUSTER,
            P03PhaseId.R3_PRUNE,
            P03PhaseId.R4_KG,
            P03PhaseId.R6_STAGE,
            P03PhaseId.R7_WRITE,
            P03PhaseId.R8_EMIT,
        ),
    ),
    _column("wal_pos", phase_consumers=_phases(P03PhaseId.R0_INIT)),
    _column(
        "cognitive_trace_id",
        state_field="cognitive_trace_id",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column("tenant_id", phase_consumers=_phases(P03PhaseId.R0_INIT)),
    _column("space_id", phase_consumers=_phases(P03PhaseId.R0_INIT)),
    _column(
        "topic",
        state_field="channel_id",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column(
        "text",
        state_field="content_text",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R4_KG, P03PhaseId.R8_EMIT),
    ),
    _column(
        "simhash_hex",
        state_field="simhash_hex",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R3_PRUNE),
    ),
    _alias(
        "activity_category as content_type",
        "content_type",
        state_field="content_type",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "activity_type",
        state_field="activity_type",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R4_KG),
    ),
    _column(
        "activity_type_ultrabert",
        state_field="activity_type_ultrabert",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R4_KG),
    ),
    _column(
        "activity_type_confidence",
        state_field="activity_type_confidence",
        default=0.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER),
    ),
    _column(
        "intent_ultrabert",
        state_field="intent_ultrabert",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R4_KG),
    ),
    _column(
        "intent_confidence",
        state_field="intent_confidence",
        default=0.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R4_KG),
    ),
    _column(
        "embedding_id",
        state_field="embedding_id",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R3_PRUNE),
    ),
    _column("embedding_status", phase_consumers=_phases(P03PhaseId.R0_INIT)),
    _column(
        "sentiment_score",
        state_field="sentiment_score",
        default=0.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE),
    ),
    _column(
        "sentiment_label",
        state_field="sentiment_label",
        default="neutral",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE),
    ),
    _alias(
        "dominant_emotions_json as emotions_json",
        "emotions_json",
        state_field="emotions_json",
        default="[]",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE),
    ),
    _column("intent_category", phase_consumers=_phases(P03PhaseId.R0_INIT)),
    _column(
        "ner_entities_json",
        state_field="ner_entities_json",
        default="[]",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R4_KG),
    ),
    _column(
        "temporal_json",
        state_field="temporal_expressions_json",
        default="[]",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "salience_score",
        state_field="salience_score",
        default=0.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE),
    ),
    _column(
        "salience_band",
        state_field="salience_band",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE),
    ),
    _column(
        "novelty_score",
        state_field="novelty_score",
        default=0.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE, P03PhaseId.R3_PRUNE),
    ),
    _column(
        "affect_valence",
        state_field="affect_valence",
        default=0.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE),
    ),
    _column(
        "affect_arousal",
        state_field="affect_arousal",
        default=0.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE),
    ),
    _column("event_time_utc", phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER)),
    _column("created_at", phase_consumers=_phases(P03PhaseId.R0_INIT)),
    _column(
        "participants_json",
        state_field="participants_json",
        default="[]",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE, P03PhaseId.R4_KG),
    ),
    _column(
        "num_participants",
        state_field="num_participants",
        default=0,
        converter=_to_int,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE, P03PhaseId.R4_KG),
    ),
    _column(
        "social_context",
        state_field="social_context",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE, P03PhaseId.R4_KG),
    ),
    _column(
        "social_intimacy",
        state_field="social_intimacy",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE, P03PhaseId.R4_KG),
    ),
    _column(
        "is_solo_event",
        state_field="is_solo_event",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE, P03PhaseId.R4_KG),
    ),
    _column(
        "location_name",
        state_field="location_name",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "location_type",
        state_field="location_type",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER),
    ),
    _column(
        "geohash_6",
        state_field="geohash_6",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER),
    ),
    _column(
        "place_id",
        state_field="place_id",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "actor_id",
        state_field="actor_id",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R4_KG),
    ),
    _column(
        "extracted_relations_json",
        state_field="extracted_relations_json",
        default="[]",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R4_KG),
    ),
    _column(
        "time_of_day_bucket",
        state_field="time_of_day_bucket",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column(
        "circadian_slot",
        state_field="circadian_slot",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column(
        "is_weekend",
        state_field="is_weekend",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column(
        "day_of_week",
        state_field="day_of_week",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column(
        "ingress_channel",
        state_field="ingress_channel",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column(
        "ingress_source",
        state_field="ingress_source",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column(
        "device_kind",
        state_field="device_kind",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column(
        "narrative_thread_id",
        state_field="narrative_thread_id",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "narrative_arc_position",
        state_field="narrative_arc_position",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "narrative_is_goal_event",
        state_field="narrative_is_goal_event",
        default=False,
        converter=bool,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "intent_type",
        state_field="intent_type",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R4_KG, P03PhaseId.R8_EMIT),
    ),
    _column(
        "goal_context",
        state_field="goal_context",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "source_type",
        state_field="source_type",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column(
        "novelty",
        state_field="novelty",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE, P03PhaseId.R8_EMIT),
    ),
    _column(
        "elaboration_depth",
        state_field="elaboration_depth",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "identity_domains_json",
        state_field="identity_domains_json",
        default="[]",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE, P03PhaseId.R8_EMIT),
    ),
    _column(
        "entity_salience_json",
        state_field="entity_salience_json",
        default="{}",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R4_KG),
    ),
    _column(
        "k1_signal_version",
        state_field="k1_signal_version",
        default="2.0",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column(
        "affect_dominance",
        state_field="affect_dominance",
        default=0.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE),
    ),
    _column(
        "temporal_mentioned_time",
        state_field="temporal_mentioned_time",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "temporal_resolved_epoch_ms",
        state_field="temporal_resolved_epoch_ms",
        default=0.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "temporal_orientation",
        state_field="temporal_orientation",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "conversation_anchor_ms", phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER)
    ),
    _column(
        "temporal_source",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "temporal_links_json",
        state_field="temporal_links_json",
        default="[]",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "extraction_sequence",
        state_field="extraction_sequence",
        default=0,
        converter=_to_int,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER),
    ),
    _column(
        "location_hierarchy_json",
        state_field="location_hierarchy_json",
        default="[]",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "spatial_context_json",
        state_field="spatial_context_json",
        default="{}",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    _column(
        "participant_relationships_json",
        state_field="participant_relationships_json",
        default="[]",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R4_KG, P03PhaseId.R8_EMIT),
    ),
    _column(
        "surprise_level",
        state_field="surprise_level",
        default=0.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE),
    ),
    _column(
        "identity_relevance",
        state_field="identity_relevance",
        default=0.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE),
    ),
    _column(
        "source_reliability",
        state_field="source_reliability",
        default=1.0,
        converter=_to_float,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R3_PRUNE, P03PhaseId.R8_EMIT),
    ),
    _column(
        "memory_tier",
        state_field="memory_tier",
        default="routine",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R1_SCORE, P03PhaseId.R8_EMIT),
    ),
    _column(
        "temporal_anchor_json",
        state_field="temporal_anchor_json",
        default="{}",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R2_CLUSTER, P03PhaseId.R8_EMIT),
    ),
    # --- K1 Correction Signals (0085) ---
    _column(
        "correction_signal",
        state_field="correction_signal",
        default=False,
        converter=bool,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R3_PRUNE),
    ),
    _column(
        "contradiction_signal",
        state_field="contradiction_signal",
        default=False,
        converter=bool,
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R3_PRUNE),
    ),
    _column(
        "supersedes_concept",
        state_field="supersedes_concept",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R3_PRUNE),
    ),
    _column(
        "correction_source",
        state_field="correction_source",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
    _column(
        "session_context_id",
        state_field="session_context_id",
        default="",
        phase_consumers=_phases(P03PhaseId.R0_INIT, P03PhaseId.R8_EMIT),
    ),
)

R0_SIGNAL_FAMILY_ORDER: Tuple[str, ...] = (
    "routing_identity",
    "content_semantic",
    "embedding_vector",
    "affect_salience",
    "social_context",
    "spatial_context",
    "temporal_context",
    "modality_context",
    "narrative_cognitive",
    "k1_correction_signals",
)

R0_SIGNAL_FAMILY_BY_ROW_KEY: Dict[str, str] = {
    "event_id": "routing_identity",
    "wal_pos": "routing_identity",
    "cognitive_trace_id": "routing_identity",
    "tenant_id": "routing_identity",
    "space_id": "routing_identity",
    "topic": "routing_identity",
    "text": "content_semantic",
    "simhash_hex": "content_semantic",
    "content_type": "content_semantic",
    "activity_type": "content_semantic",
    "activity_type_ultrabert": "content_semantic",
    "activity_type_confidence": "content_semantic",
    "intent_ultrabert": "content_semantic",
    "intent_confidence": "content_semantic",
    "intent_category": "content_semantic",
    "ner_entities_json": "content_semantic",
    "embedding_id": "embedding_vector",
    "embedding_status": "embedding_vector",
    "sentiment_score": "affect_salience",
    "sentiment_label": "affect_salience",
    "emotions_json": "affect_salience",
    "salience_score": "affect_salience",
    "salience_band": "affect_salience",
    "novelty_score": "affect_salience",
    "affect_valence": "affect_salience",
    "affect_arousal": "affect_salience",
    "affect_dominance": "affect_salience",
    "participants_json": "social_context",
    "num_participants": "social_context",
    "social_context": "social_context",
    "social_intimacy": "social_context",
    "is_solo_event": "social_context",
    "actor_id": "social_context",
    "extracted_relations_json": "social_context",
    "participant_relationships_json": "social_context",
    "location_name": "spatial_context",
    "location_type": "spatial_context",
    "geohash_6": "spatial_context",
    "place_id": "spatial_context",
    "location_hierarchy_json": "spatial_context",
    "spatial_context_json": "spatial_context",
    "event_time_utc": "temporal_context",
    "created_at": "temporal_context",
    "temporal_json": "temporal_context",
    "temporal_mentioned_time": "temporal_context",
    "temporal_resolved_epoch_ms": "temporal_context",
    "temporal_orientation": "temporal_context",
    "conversation_anchor_ms": "temporal_context",
    "temporal_source": "temporal_context",
    "temporal_links_json": "temporal_context",
    "extraction_sequence": "temporal_context",
    "temporal_anchor_json": "temporal_context",
    "time_of_day_bucket": "modality_context",
    "circadian_slot": "modality_context",
    "is_weekend": "modality_context",
    "day_of_week": "modality_context",
    "ingress_channel": "modality_context",
    "ingress_source": "modality_context",
    "device_kind": "modality_context",
    "narrative_thread_id": "narrative_cognitive",
    "narrative_arc_position": "narrative_cognitive",
    "narrative_is_goal_event": "narrative_cognitive",
    "intent_type": "narrative_cognitive",
    "goal_context": "narrative_cognitive",
    "source_type": "narrative_cognitive",
    "novelty": "narrative_cognitive",
    "elaboration_depth": "narrative_cognitive",
    "identity_domains_json": "narrative_cognitive",
    "entity_salience_json": "narrative_cognitive",
    "k1_signal_version": "narrative_cognitive",
    "surprise_level": "narrative_cognitive",
    "identity_relevance": "narrative_cognitive",
    "source_reliability": "narrative_cognitive",
    "memory_tier": "narrative_cognitive",
    "correction_signal": "k1_correction_signals",
    "contradiction_signal": "k1_correction_signals",
    "supersedes_concept": "k1_correction_signals",
    "correction_source": "k1_correction_signals",
    "session_context_id": "k1_correction_signals",
}

R0_SELECT_COLUMNS_SQL = ",\n                ".join(spec.select_sql for spec in R0_FIELD_SPECS)


def _signal_family_for_row_key(row_key: str) -> str:
    return R0_SIGNAL_FAMILY_BY_ROW_KEY.get(row_key, "uncategorized")


def get_r0_field_registry_for_discovery() -> List[Dict[str, Any]]:
    """Expose registry metadata for discovery-doc generation."""

    return [
        {
            "select_sql": spec.select_sql,
            "row_key": spec.row_key,
            "state_field": spec.state_field,
            "default": spec.default,
            "has_converter": spec.converter is not None,
            "signal_family": _signal_family_for_row_key(spec.row_key),
            "phase_consumers": [phase.value for phase in spec.phase_consumers],
        }
        for spec in R0_FIELD_SPECS
    ]


def get_r0_field_registry_grouped_for_discovery() -> List[Dict[str, Any]]:
    """Return discovery export grouped by signal family for doc generation."""

    grouped_rows: Dict[str, List[Dict[str, Any]]] = {}
    for row in get_r0_field_registry_for_discovery():
        grouped_rows.setdefault(row["signal_family"], []).append(row)

    ordered_groups: List[Dict[str, Any]] = []
    ordered_families = list(R0_SIGNAL_FAMILY_ORDER) + sorted(
        family for family in grouped_rows if family not in R0_SIGNAL_FAMILY_ORDER
    )

    for family in ordered_families:
        rows = grouped_rows.get(family)
        if not rows:
            continue
        phase_consumers = sorted({phase for row in rows for phase in row["phase_consumers"]})
        ordered_groups.append(
            {
                "signal_family": family,
                "field_count": len(rows),
                "phase_consumers": phase_consumers,
                "fields": rows,
            }
        )

    return ordered_groups


# =============================================================================
# GAP AUTO-RESOLUTION (Uses k0.modules.consolidation.gap_auto_resolver)
# =============================================================================


def _extract_entities_from_events(
    events: List[P03EventState],
) -> tuple[list[dict], list[str]]:
    """
    Extract NER entities and raw texts from P03 events for gap matching.

    Returns (entities_list, event_texts_list).
    """
    all_entities = []
    event_texts = []

    for event in events:
        # Collect raw text for fallback matching
        if event.content_text:
            event_texts.append(event.content_text)

        if not event.ner_entities_json or event.ner_entities_json == "[]":
            continue

        try:
            ner_data = json.loads(event.ner_entities_json)

            if isinstance(ner_data, dict):
                # UltraBERT format: {"ner_family": {"entities": [...]}, ...}
                for key in ["ner_family", "ner_general"]:
                    ner_section = ner_data.get(key, {})
                    if isinstance(ner_section, dict):
                        entities_list = ner_section.get("entities", [])
                    elif isinstance(ner_section, list):
                        entities_list = ner_section
                    else:
                        entities_list = []

                    for entity in entities_list:
                        if isinstance(entity, dict):
                            all_entities.append(
                                {
                                    "text": entity.get("text", entity.get("value", "")),
                                    "label": entity.get("label", entity.get("type", "UNKNOWN")),
                                    "source_event_id": event.event_id,
                                }
                            )
            elif isinstance(ner_data, list):
                # Simple list format
                for entity in ner_data:
                    if isinstance(entity, dict):
                        all_entities.append(
                            {
                                "text": entity.get("text", entity.get("value", "")),
                                "label": entity.get("label", entity.get("type", "UNKNOWN")),
                                "source_event_id": event.event_id,
                            }
                        )
        except (json.JSONDecodeError, TypeError):
            pass

    return all_entities, event_texts


async def _try_auto_resolve_gaps(
    ctx: "P03RunnerContext",
    events: List[P03EventState],
    tenant_id: str,
    space_id: str,
) -> int:
    """
    Check incoming events for entities that resolve pending gaps.

    Delegates to GapAutoResolver for proper similarity-based matching,
    confidence scoring, label matching, and specificity bonuses.

    Returns number of gaps resolved.
    """
    try:
        all_entities, event_texts = _extract_entities_from_events(events)

        if not all_entities and not event_texts:
            logger.debug("R0: No entities or texts to check for gap resolution")
            return 0

        # Get pool from syscalls using capability-gated access
        try:
            pool = ctx.syscalls.get_pool()
        except (PermissionError, RuntimeError) as e:
            logger.debug(f"R0: No pool access for gap auto-resolution: {e}")
            return 0

        # Use GapAutoResolver for sophisticated matching
        resolver = GapAutoResolver(
            pool=pool,
            tenant_id=tenant_id,
            space_id=space_id,
        )

        resolved_count = await resolver.process_entities(
            entities=all_entities,
            source_event_id=events[0].event_id if events else None,
            event_texts=event_texts,
        )

        if resolved_count > 0:
            stats = resolver.stats
            logger.info(
                "R0: Gap auto-resolution stats: checked=%d, matched=%d, resolved=%d, skipped=%d",
                stats.gaps_checked,
                stats.entities_matched,
                stats.gaps_resolved,
                stats.gaps_skipped_low_confidence,
            )

        return resolved_count

    except Exception as e:
        logger.warning(
            "R0: Gap auto-resolution failed (non-fatal): %s",
            str(e),
            extra={"tenant_id": tenant_id, "space_id": space_id},
        )
        return 0


# =============================================================================
# R0 CONFIGURATION
# =============================================================================


@dataclass
class R0Config:
    """
    R0 phase configuration.

    Attributes:
        batch_size: Maximum events per batch (default: 300)
        require_embedding_ready: Only include events with embedding_status='READY'
        exclude_archived: Exclude events with archival_status set
        max_age_hours: Maximum age of events to consider (0 = no limit)
    """

    batch_size: int = 300
    require_embedding_ready: bool = True
    exclude_archived: bool = True
    max_age_hours: int = 0  # 0 = no limit


# =============================================================================
# R0 BATCH SELECTOR PHASE
# =============================================================================


class R0BatchSelector:
    """
    R0 Phase: Batch Selection (Event Ingestion).

    Responsibilities:
        1. Fetch current offset from st_offsets
        2. Query st_hipp_events for eligible events after offset
        3. Build P03BatchEnvelope with context and events
        4. Return (envelope, result) tuple for R1-R8 processing

    Eligibility Criteria:
        - event_id > last_committed_offset
        - consolidation_status IS NULL or 'PENDING'
        - embedding_status = 'READY' (if config.require_embedding_ready)
        - archival_status IS NULL (if config.exclude_archived)

    Unlike R1-R8:
        - R0 CREATES the envelope (others receive it)
        - R0 signature: run(tenant_id, space_id, ctx) -> (envelope, result)
        - R1-R8 signature: run(envelope, ctx) -> result

    Idempotency:
        - Offset read is idempotent (same offset on retry)
        - Same batch selected if no events processed between retries
        - cycle_id is generated fresh on each call
    """

    PHASE_ID = P03PhaseId.R0_INIT

    def __init__(self, config: Optional[R0Config] = None):
        """
        Initialize R0 phase.

        Args:
            config: Optional configuration (defaults used if not provided)
        """
        self.config = config or R0Config()

    @staticmethod
    def _spec_default(spec: R0FieldSpec) -> Any:
        return spec.default

    @classmethod
    def _spec_to_state_value(cls, row: Any, spec: R0FieldSpec) -> Any:
        value = row.get(spec.row_key)
        if value is None:
            return cls._spec_default(spec)
        if spec.converter is None:
            return value
        return spec.converter(value)

    @classmethod
    def _build_state_payload(cls, row: Any, event_time_ms: int) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "event_id": row["event_id"],
            "hipp_event_id": row["event_id"],
            "timestamp": event_time_ms,
        }

        for spec in R0_FIELD_SPECS:
            if spec.state_field is None:
                continue
            payload[spec.state_field] = cls._spec_to_state_value(row, spec)

        payload["intent_label"] = row.get("intent_ultrabert") or row.get("intent_category") or ""
        payload["temporal_source"] = row.get("temporal_source") or (
            "mw_resolved"
            if float(row.get("temporal_resolved_epoch_ms") or 0.0) > 0
            else "event_time"
        )

        return payload

    @property
    def phase_id(self) -> P03PhaseId:
        """Return the phase identifier."""
        return self.PHASE_ID

    async def run(
        self,
        tenant_id: str,
        space_id: str,
        ctx: "P03RunnerContext",
    ) -> Tuple[Optional[P03BatchEnvelope], P03PhaseResult]:
        """
        Execute R0 phase: Batch Selection.

        Unlike R1-R8 which receive an envelope, R0 creates it.

        Args:
            tenant_id: Tenant identifier for multi-tenant isolation
            space_id: Space identifier (family/user)
            ctx: Runner context with syscalls, logger, config

        Returns:
            Tuple of:
                - P03BatchEnvelope if events found (None if skip/fail)
                - P03PhaseResult with status, duration, outputs
        """
        start_ms = int(time.time() * 1000)

        logger.info(
            "R0: Starting batch selection phase",
            extra={
                "tenant_id": tenant_id,
                "space_id": space_id,
                "batch_size": self.config.batch_size,
            },
        )

        try:
            # 1. Fetch current offset
            current_offset = await self._fetch_offset(ctx, tenant_id, space_id)

            logger.info(
                "R0: Fetched current offset",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "offset": current_offset,
                },
            )

            # 2. Query eligible events from st_hipp_events
            events = await self._fetch_eligible_events(
                ctx,
                tenant_id,
                space_id,
                current_offset,
            )

            # 3. Handle empty batch (SKIP)
            if not events:
                duration_ms = int(time.time() * 1000) - start_ms
                logger.info(
                    "R0: No eligible events found, skipping",
                    extra={
                        "tenant_id": tenant_id,
                        "space_id": space_id,
                        "offset": current_offset,
                        "duration_ms": duration_ms,
                    },
                )
                return None, P03PhaseResult.skip(
                    phase_id=self.PHASE_ID,
                    reason="No eligible events found",
                    duration_ms=duration_ms,
                )

            # 4. Load embeddings from st_vec for R2 clustering
            embeddings_loaded = await self._load_embeddings_for_events(
                ctx,
                events,
            )
            logger.info(
                "R0: Loaded embeddings from st_vec",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "events_count": len(events),
                    "embeddings_loaded": embeddings_loaded,
                },
            )

            # 4b. Auto-resolve pending gaps from user context (non-blocking)
            # If user mentions "Lincoln Elementary", resolve "Lincoln School" gap
            gaps_resolved = await _try_auto_resolve_gaps(ctx, events, tenant_id, space_id)
            if gaps_resolved > 0:
                logger.info(
                    "R0: Implicitly resolved %d gaps from user context",
                    gaps_resolved,
                    extra={"tenant_id": tenant_id, "space_id": space_id},
                )

            # 5. Filter to events with embeddings (required for R2 clustering)
            events_with_embeddings = [e for e in events if e.embedding_768 is not None]
            if len(events_with_embeddings) < len(events):
                logger.warning(
                    "R0: Excluding events without embeddings",
                    extra={
                        "tenant_id": tenant_id,
                        "space_id": space_id,
                        "total_events": len(events),
                        "events_with_embeddings": len(events_with_embeddings),
                        "excluded": len(events) - len(events_with_embeddings),
                    },
                )
            events = events_with_embeddings

            if not events:
                duration_ms = int(time.time() * 1000) - start_ms
                return None, P03PhaseResult.skip(
                    phase_id=self.PHASE_ID,
                    reason="No events with embeddings",
                    duration_ms=duration_ms,
                )

            # 6. Build envelope
            envelope = self._build_envelope(
                tenant_id,
                space_id,
                events,
                current_offset,
            )

            duration_ms = int(time.time() * 1000) - start_ms

            logger.info(
                "R0: Batch selection complete",
                extra={
                    "cycle_id": envelope.context.cycle_id,
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "events_selected": len(events),
                    "offset_start": current_offset,
                    "batch_watermark": (
                        envelope.context.event_ids[-1] if envelope.context.event_ids else None
                    ),
                    "duration_ms": duration_ms,
                },
            )

            result = P03PhaseResult.done(
                phase_id=self.PHASE_ID,
                duration_ms=duration_ms,
                outputs_summary={
                    "events_selected": len(events),
                    "offset_start": current_offset,
                    "batch_id": envelope.context.batch_id,
                },
                idempotency_key=f"p03:r0:{envelope.context.cycle_id}",
            )

            return envelope, result

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms
            logger.exception(
                "R0: Batch selection failed",
                extra={
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )

            error = P03Error.create(
                phase="R0",
                stage_id="batch_selector",
                error_type="R0_INGESTION_ERROR",
                error_message=str(e),
                recoverable=True,  # R0 failures are retriable
            )

            return None, P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=error,
                duration_ms=duration_ms,
            )

    async def _fetch_offset(
        self,
        ctx: "P03RunnerContext",
        tenant_id: str,
        space_id: str,
    ) -> int:
        """
        Fetch current offset from st_offsets.

        Args:
            ctx: Runner context with syscalls
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            Current offset (0 if no prior offset exists)
        """
        # Use syscalls to get offset store
        offset_store = ctx.syscalls.offset_store

        offset_record = await offset_store.fetch(
            subscriber_id=P03_SUBSCRIBER_ID,
            topic=P03_SOURCE_TOPIC,
            space_id=space_id,
            tenant_id=tenant_id,
        )

        if offset_record is None:
            return 0

        return offset_record.offset

    async def _fetch_eligible_events(
        self,
        ctx: "P03RunnerContext",
        tenant_id: str,
        space_id: str,
        offset: int,
    ) -> List[P03EventState]:
        """
        Query st_hipp_events for eligible events.

        SQL (conceptual):
            SELECT * FROM st_hipp_events
            WHERE tenant_id = $1
              AND space_id = $2
              AND wal_pos > $3
              AND (consolidation_status IS NULL OR consolidation_status = 'PENDING')
              AND embedding_status = 'READY'
              AND (archival_status IS NULL)
            ORDER BY wal_pos ASC
            LIMIT $4

        Args:
            ctx: Runner context with syscalls
            tenant_id: Tenant identifier
            space_id: Space identifier
            offset: Current offset (events with wal_pos > offset are eligible)

        Returns:
            List of P03EventState populated from st_hipp_events rows
        """
        # Build query with proper filters
        conditions: List[str] = []
        params: List[Any] = []
        param_idx = 1

        # Required filters
        conditions.append(f"tenant_id = ${param_idx}")
        params.append(tenant_id)
        param_idx += 1

        conditions.append(f"space_id = ${param_idx}")
        params.append(space_id)
        param_idx += 1

        # Offset filter (wal_pos > last committed offset)
        conditions.append(f"wal_pos > ${param_idx}")
        params.append(offset)
        param_idx += 1

        # Consolidation status filter
        conditions.append("(consolidation_status IS NULL OR consolidation_status = 'PENDING')")

        # Embedding ready filter
        if self.config.require_embedding_ready:
            conditions.append(f"embedding_status = ${param_idx}")
            params.append("READY")
            param_idx += 1

        # Archived filter
        if self.config.exclude_archived:
            conditions.append("(archival_status IS NULL OR archival_status = '')")

        where_clause = " AND ".join(conditions)

        # Build full query
        # Note: content_type doesn't exist in DB schema - use activity_category instead
        # Note: emotions_json renamed to dominant_emotions_json in DB
        query = f"""
            SELECT
                {R0_SELECT_COLUMNS_SQL}
            FROM st_hipp_events
            WHERE {where_clause}
            ORDER BY wal_pos ASC
            LIMIT ${param_idx}
        """
        params.append(self.config.batch_size)

        # Execute query via syscalls
        async with ctx.syscalls.unit_of_work() as uow:
            conn = uow._connection
            if conn is None:
                raise RuntimeError("UnitOfWork connection not initialized")

            logger.debug(
                "R0: Executing eligible events query",
                extra={
                    "query_params": params,
                    "batch_size": self.config.batch_size,
                },
            )
            rows = await conn.fetch(query, *params)
            logger.info(
                "R0: Query returned rows",
                extra={"row_count": len(rows)},
            )

        # Convert rows to P03EventState
        events: List[P03EventState] = []
        for row in rows:
            event = self._row_to_event_state(row)
            events.append(event)

        return events

    def _row_to_event_state(self, row: Any) -> P03EventState:
        """
        Convert database row to P03EventState.

        Args:
            row: asyncpg Record from st_hipp_events

        Returns:
            P03EventState populated with row data
        """
        # =====================================================================
        # CONVERSATION TIME CHAIN (Epic 1.2 -- Issue 1.2.1 audit / 1.2.2 hardening)
        # =====================================================================
        # R2 episode formation needs CONVERSATION TIME (when user chatted),
        # NOT temporal resolution (what date the event REFERS TO).
        #
        # Chain A (for R2 episodes):
        #   K1 Concierge turn.complete.v1.timestamp_ms (gold standard)
        #   -> MW now_utc() -> body.event_time_utc (close proxy)
        #   -> M08 normalize -> st_hipp_events.event_time_utc (BIGINT, seconds)
        #   -> R0 reads here -> P03EventState.timestamp (ms)
        #   -> R2 EpisodeSplitter, CompositeDistance, episode matching
        #
        # Chain B (for temporal queries, NOT for R2):
        #   K1 LLM -> temporal.resolved_epoch_ms -> st_hipp_events column
        #   -> P03EventState.temporal_resolved_epoch_ms (separate field)
        #
        # v3 (Epic 1.2): Prefer conversation_anchor_ms when available.
        # Fallback order: conversation_anchor_ms -> event_time_utc -> created_at -> now()
        # WARNING: created_at collapses during offline queue drain
        # (all events arrive at same K0 insert time).
        # =====================================================================
        _anchor_ms_raw = row.get("conversation_anchor_ms")
        _event_time_raw = row.get("event_time_utc")
        _created_at_raw = row.get("created_at")

        if _anchor_ms_raw is not None and _anchor_ms_raw > 0:
            # Epic 1.2: Gold standard -- K1 MW turn timestamp.
            # Some historical/backfilled paths may still provide seconds.
            event_time_ms = _normalize_epoch_ms(_anchor_ms_raw)
            event_time_seconds = int(event_time_ms / 1000)
        elif _event_time_raw is not None and _event_time_raw > 0:
            event_time_seconds = _event_time_raw
        elif _created_at_raw is not None and _created_at_raw > 0:
            event_time_seconds = _created_at_raw
            # Issue 1.2.2: This path fires during offline drain or missing event_time_utc
            logger.warning(
                "R0: event_time_utc missing/0, falling back to created_at",
                extra={"event_id": row.get("event_id"), "created_at": _created_at_raw},
            )
        else:
            event_time_seconds = int(time.time())
            logger.error(
                "R0: Both event_time_utc and created_at missing, using now()",
                extra={"event_id": row.get("event_id")},
            )

        # Normalize to ms for P03EventState.timestamp
        if _anchor_ms_raw is not None and _anchor_ms_raw > 0:
            pass  # event_time_ms already set above
        else:
            event_time_ms = (
                event_time_seconds * 1000 if event_time_seconds < 1e12 else event_time_seconds
            )

        return P03EventState(**self._build_state_payload(row, event_time_ms))

    async def _load_embeddings_for_events(
        self,
        ctx: "P03RunnerContext",
        events: List[P03EventState],
    ) -> int:
        """
        Load embeddings from st_vec and materialize into event states.

        Fetches 768-dim vectors from st_vec for events that have embedding_id,
        then calls materialize_embedding() on each P03EventState.

        This enables R2 episodic clustering to use semantic similarity.

        Args:
            ctx: Runner context with syscalls
            events: List of P03EventState to load embeddings for

        Returns:
            Number of embeddings successfully loaded
        """
        if not events:
            return 0

        # Collect event_ids that have embedding_ids
        event_id_to_state: Dict[str, P03EventState] = {}
        for event in events:
            if event.embedding_id:
                event_id_to_state[event.event_id] = event

        if not event_id_to_state:
            logger.debug("R0: No events with embedding_id to load")
            return 0

        # Query st_vec for vectors by event_id
        # Build IN clause for event_ids
        event_ids = list(event_id_to_state.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(event_ids))])

        query = f"""
            SELECT event_id, vector, vector_dim
            FROM st_vec
            WHERE event_id IN ({placeholders})
              AND status IN ('READY', 'INDEXED')
        """

        loaded_count = 0

        try:
            async with ctx.syscalls.unit_of_work() as uow:
                conn = uow._connection
                if conn is None:
                    raise RuntimeError("UnitOfWork connection not initialized")

                rows = await conn.fetch(query, *event_ids)

                for row in rows:
                    event_id = row["event_id"]
                    vector_raw = row["vector"]
                    vector_dim = row["vector_dim"]

                    if event_id not in event_id_to_state:
                        continue

                    event = event_id_to_state[event_id]

                    if not vector_raw:
                        logger.warning(
                            "R0: Empty vector for event",
                            extra={"event_id": event_id},
                        )
                        continue

                    try:
                        # M4 (ADR-K003 v2): st_vec.vector is pgvector VECTOR(768).
                        # asyncpg returns pgvector columns as strings: "[0.1,0.2,...]"
                        # Legacy LargeBinary path kept as fallback for safety.
                        if isinstance(vector_raw, str):
                            # pgvector native format: "[0.1,0.2,...,0.768]"
                            vector = json.loads(vector_raw)
                        elif isinstance(vector_raw, (list, tuple)):
                            # Already a Python sequence (e.g. pgvector extension codec)
                            vector = list(vector_raw)
                        elif isinstance(vector_raw, (bytes, bytearray)):
                            # Legacy LargeBinary format (pre-M4)
                            expected_bytes = vector_dim * 4
                            if len(vector_raw) != expected_bytes:
                                logger.warning(
                                    "R0: Invalid vector byte size",
                                    extra={
                                        "event_id": event_id,
                                        "expected": expected_bytes,
                                        "actual": len(vector_raw),
                                    },
                                )
                                continue
                            vector = list(struct.unpack(f"{vector_dim}f", vector_raw))
                        else:
                            logger.warning(
                                "R0: Unexpected vector type",
                                extra={"event_id": event_id, "type": type(vector_raw).__name__},
                            )
                            continue

                        if len(vector) != vector_dim:
                            logger.warning(
                                "R0: Vector dimension mismatch",
                                extra={
                                    "event_id": event_id,
                                    "expected_dim": vector_dim,
                                    "actual_dim": len(vector),
                                },
                            )
                            continue

                        event.materialize_embedding(vector)
                        loaded_count += 1
                    except (json.JSONDecodeError, struct.error, ValueError, TypeError) as e:
                        logger.warning(
                            "R0: Failed to decode vector",
                            extra={"event_id": event_id, "error": str(e)},
                        )
                        continue

        except Exception as e:
            logger.warning(
                "R0: Failed to load embeddings from st_vec",
                extra={"error": str(e), "event_count": len(event_ids)},
            )
            # Non-fatal - R2 will skip if no embeddings

        return loaded_count

    def _build_envelope(
        self,
        tenant_id: str,
        space_id: str,
        events: List[P03EventState],
        start_offset: int,
    ) -> P03BatchEnvelope:
        """
        Build P03BatchEnvelope from selected events.

        Args:
            tenant_id: Tenant identifier
            space_id: Space identifier
            events: List of selected events
            start_offset: Offset at batch start

        Returns:
            P03BatchEnvelope ready for R1-R8 processing
        """
        # Extract event IDs for context
        event_ids = [e.event_id for e in events]

        # Create immutable cycle context
        context = P03CycleContext.create(
            tenant_id=tenant_id,
            space_id=space_id,
            event_ids=event_ids,
            trigger_type="BATCH",
            trigger_reason=f"R0 selected {len(events)} events after offset {start_offset}",
            pending_before=len(events),  # Simplified - could query actual pending
            qos_band="GREEN" if self.config.batch_size <= 150 else "AMBER",
        )

        # Create envelope with factory
        envelope = P03BatchEnvelope.create(
            context=context,
            events=events,
        )

        return envelope

    def should_skip(
        self,
        tenant_id: str,
        space_id: str,
        ctx: "P03RunnerContext",
    ) -> Tuple[bool, str]:
        """
        Check if R0 should be skipped.

        R0 is never skipped - it's the entry point.
        This method exists for protocol compliance.

        Args:
            tenant_id: Tenant identifier
            space_id: Space identifier
            ctx: Runner context

        Returns:
            Always (False, "")
        """
        return False, ""

    def idempotency_key(
        self,
        tenant_id: str,
        space_id: str,
    ) -> str:
        """
        Generate idempotency key for R0.

        Note: R0 idempotency is based on input parameters,
        not envelope (which doesn't exist yet).

        Args:
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            Idempotency key string
        """
        return f"p03:r0:{tenant_id}:{space_id}"
