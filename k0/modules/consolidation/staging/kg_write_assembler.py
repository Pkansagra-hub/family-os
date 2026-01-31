"""
KGWriteAssembler — Issue 5.1.7

Assembles staged writes for Knowledge Graph (KG) layers from R4 phase outputs.
Handles st_kg_dom (entities) and st_kg_edges (relationships).

Spec Reference:
    - Dossier §4.8.7 (st_kg_dom / st_kg_edges KG Writes)
    - Dossier §7.4.4 (M21 KGBuilder module spec)
    - M5_EXECUTION.md Issue 5.1.7

Entity Schema (st_kg_dom):
    entity_id, canonical_name, entity_type, aliases_json,
    confidence, embedding_id, source_event_ids_json

Edge Schema (st_kg_edges):
    edge_id, source_entity_id, target_entity_id, relationship_type,
    weight, confidence, is_causal, evidence_event_ids_json

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from k0.pipelines.p03.phase_outputs import (
    CausalEdge,
    KGEdge,
    KGEdgeUpdate,
    KGEntity,
    KGEntityUpdate,
)
from k0.pipelines.p03.staged_writes import LAYER_ST_KG_DOM, LAYER_ST_KG_EDGES, StagedWrite

from .idempotency import IdempotencyKeyGenerator

# =============================================================================
# Constants
# =============================================================================

# Valid entity types per Dossier §4.8.7
VALID_ENTITY_TYPES = frozenset(
    {
        "PERSON",
        "LOCATION",
        "ORG",
        "THING",
        "CONCEPT",
    }
)

# Valid relationship types per Dossier §4.8.7
VALID_RELATIONSHIP_TYPES = frozenset(
    {
        "KNOWS",
        "LOCATED_AT",
        "PART_OF",
        "CAUSES",
        "RELATED_TO",
        "WORKS_AT",
        "LIVES_IN",
        "OWNS",
        "CREATES",
        "USES",
        # New enricher types (from enhancement plan)
        "EMOTIONALLY_RELATED",  # EmotionSimilarityEnricher
        "INTENT_RELATED",  # IntentSimilarityEnricher
        "CO_MENTIONED",  # NamedEntityEnricher
        "PARENT_OF",
        "FRIEND_OF",  # RelationshipTypeEnricher
        "CONTEXTUALLY_RELATED",  # Enhanced ContextualEdgeEnricher
        "MULTI_MODAL_RELATED",  # MultiModalSimilarityEnricher
        "TEMPORALLY_PATTERNED",  # TemporalPatternEnricher
    }
)


def _now_ms() -> int:
    """Return current time in milliseconds since epoch."""
    return int(time.time() * 1000)


# =============================================================================
# Validation Result
# =============================================================================


@dataclass
class ValidationResult:
    """
    Result of foreign key validation.

    Attributes:
        is_valid: True if all FKs are valid
        errors: List of validation error messages
        orphan_edges: List of edge IDs with invalid FKs
    """

    is_valid: bool
    errors: List[str]
    orphan_edges: List[str]


# =============================================================================
# KGWriteAssembler Class
# =============================================================================


class KGWriteAssembler:
    """
    Assembles staged writes for Knowledge Graph layers.

    Handles st_kg_dom (entities) and st_kg_edges (relationships) from
    R4 phase outputs. Ensures dependency order: entities before edges.

    Attributes:
        idempotency: Key generator for deterministic idempotency keys
        source_phase: Phase name for provenance (default "R6")
        tenant_id: Tenant identifier for multi-tenancy
        space_id: Space identifier for data isolation
    """

    def __init__(
        self,
        idempotency_gen: IdempotencyKeyGenerator,
        source_phase: str = "R6",
        tenant_id: str = "",
        space_id: str = "",
    ) -> None:
        """
        Initialize assembler with idempotency generator.

        Args:
            idempotency_gen: Generator for idempotency keys
            source_phase: Phase name for provenance tracking
            tenant_id: Tenant identifier for multi-tenancy
            space_id: Space identifier for data isolation
        """
        self.idempotency = idempotency_gen
        self.source_phase = source_phase
        self.tenant_id = tenant_id
        self.space_id = space_id

    # =========================================================================
    # st_kg_dom — Entity Writes
    # =========================================================================

    def assemble_entity_writes(
        self,
        entities: List[KGEntity],
        entity_updates: Optional[List[KGEntityUpdate]] = None,
    ) -> List[StagedWrite]:
        """
        Assemble st_kg_dom writes from R4 entities.

        - New entities (is_new=True) → INSERT
        - Existing entities via updates → UPDATE

        Args:
            entities: List of KGEntity objects
            entity_updates: Optional list of KGEntityUpdate for existing entities

        Returns:
            List of StagedWrite for st_kg_dom
        """
        writes: List[StagedWrite] = []

        # Process new entities (INSERT)
        for entity in entities:
            if entity.is_new:
                write = self._create_entity_insert(entity)
                writes.append(write)
            else:
                # Existing entity referenced but not updated via KGEntityUpdate
                # Skip unless there's a corresponding update
                pass

        # Process entity updates (UPDATE)
        if entity_updates:
            for update in entity_updates:
                write = self._create_entity_update(update)
                if write:
                    writes.append(write)

        return writes

    def _create_entity_insert(self, entity: KGEntity) -> StagedWrite:
        """Create st_kg_dom INSERT for new entity."""
        now_ms = _now_ms()
        first_mentioned_event_id = entity.first_mentioned_event_id or (
            entity.source_event_ids[0] if entity.source_event_ids else None
        )
        record_data = {
            "entity_id": entity.entity_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "version": 1,
            "canonical_name": entity.canonical_name,
            "entity_type": entity.entity_type,
            "entity_subtype": entity.entity_subtype,  # GAP-005: Fine-grained classification
            "aliases_json": entity.aliases_json,
            "attributes_json": entity.attributes_json,
            "confidence_score": entity.confidence,
            "embedding_id": entity.embedding_id,
            "source_episodes_json": json.dumps(entity.source_event_ids),
            "first_mentioned_event_id": first_mentioned_event_id,
            "last_observed_at": entity.last_observed_at or now_ms,
            "observation_count": len(entity.source_event_ids) if entity.source_event_ids else 1,
            "decay_factor": 1.0,
            "archival_status": "ACTIVE",
            "valid_from": now_ms,
            "valid_from_ms": now_ms,
            "created_at": now_ms,
            "updated_at": now_ms,
        }

        idem_key = self.idempotency.for_truth_write(
            LAYER_ST_KG_DOM,
            entity.entity_id,
        )

        write = StagedWrite.insert(
            layer=LAYER_ST_KG_DOM,
            record_id=entity.entity_id,
            data=record_data,
            phase=self.source_phase,
            event_ids=entity.source_event_ids,
        )
        write.idempotency_key = idem_key

        return write

    def _create_entity_update(self, update: KGEntityUpdate) -> Optional[StagedWrite]:
        """
        Create st_kg_dom UPDATE for existing entity.

        Issue 3 Fix: Enhanced to handle REINFORCE operations that increment
        observation_count and append new source event IDs.
        """
        if not update.entity_id:
            return None

        # Build partial update data
        record_data: Dict[str, Any] = {
            "updated_at": _now_ms(),
        }

        # Apply field updates
        if update.field_updates:
            record_data.update(update.field_updates)

        # Apply confidence delta
        if update.confidence_delta != 0:
            record_data["confidence_delta"] = update.confidence_delta

        # Apply new aliases (merge with existing)
        if update.new_aliases:
            record_data["new_aliases_json"] = json.dumps(update.new_aliases)

        if update.last_observed_at:
            record_data["last_observed_at"] = update.last_observed_at

        # Issue 3 Fix: Handle REINFORCE operations
        if update.observation_count_increment > 0:
            record_data["observation_count_increment"] = update.observation_count_increment
            record_data["decay_factor"] = 1.0

        if update.new_source_event_ids:
            record_data["additional_source_event_ids"] = json.dumps(update.new_source_event_ids)

        idem_key = self.idempotency.for_truth_write(
            LAYER_ST_KG_DOM,
            update.entity_id,
        )

        write = StagedWrite.update(
            layer=LAYER_ST_KG_DOM,
            record_id=update.entity_id,
            data=record_data,
            phase=self.source_phase,
            expected_version=None,  # No version check for canonical_name updates
            event_ids=update.new_source_event_ids if update.new_source_event_ids else [],
        )
        write.idempotency_key = idem_key

        return write

    # =========================================================================
    # st_kg_edges — Edge Writes
    # =========================================================================

    def assemble_edge_writes(
        self,
        edges: List[KGEdge],
        edge_updates: Optional[List[KGEdgeUpdate]] = None,
        causal_edges: Optional[List[CausalEdge]] = None,
    ) -> List[StagedWrite]:
        """
        Assemble st_kg_edges writes from R4 relationships.

        - New edges (is_new=True) → INSERT
        - CausalEdge objects → INSERT with is_causal=True
        - Edge updates → UPDATE

        Args:
            edges: List of KGEdge objects
            edge_updates: Optional list of KGEdgeUpdate for existing edges
            causal_edges: Optional list of CausalEdge from Granger analysis

        Returns:
            List of StagedWrite for st_kg_edges
        """
        # NOTE:
        # It's common for R4 to emit multiple edges/causal edges with the same
        # edge_id within a single batch (reinforcement). R6 manifest validation
        # requires uniqueness of (layer, record_id) per cycle, so we merge.

        writes_by_id: Dict[str, StagedWrite] = {}

        def upsert(write: Optional[StagedWrite]) -> None:
            if not write:
                return
            existing = writes_by_id.get(write.record_id)
            if not existing:
                writes_by_id[write.record_id] = write
                return
            writes_by_id[write.record_id] = self._merge_edge_writes(existing, write)

        # Process new edges (INSERT)
        for edge in edges:
            if edge.is_new:
                upsert(self._create_edge_insert(edge))

        # Process causal edges (INSERT with is_causal=True)
        if causal_edges:
            for causal in causal_edges:
                upsert(self._create_causal_edge_insert(causal))

        # Process edge updates (UPDATE)
        if edge_updates:
            for update in edge_updates:
                upsert(self._create_edge_update(update))

        # Preserve a stable order for determinism (helps tests/debugging)
        return [writes_by_id[k] for k in sorted(writes_by_id.keys())]

    def _merge_edge_writes(self, a: StagedWrite, b: StagedWrite) -> StagedWrite:
        """Merge two staged writes for the same st_kg_edges record_id.

        The intent is to avoid R6 manifest duplicate-record DLQ while preserving
        reinforcement signals inside a single batch.

        Rules (best-effort, schema-aware):
        - UNION contributing event ids (source_event_ids and evidence JSON)
        - For INSERT+INSERT: sum edge_weight for non-causal; max for CAUSES
        - For INSERT+UPDATE: apply deltas onto the INSERT's record_data
        - For UPDATE+UPDATE: sum deltas and union evidence ids
        - Confidence uses max (INSERT) / sum deltas (UPDATE)
        """
        if a.layer != LAYER_ST_KG_EDGES or b.layer != LAYER_ST_KG_EDGES:
            # Defensive: only merge KG edge writes
            return a
        if a.record_id != b.record_id:
            return a

        # Merge contributing event ids
        merged_event_ids = sorted(set((a.source_event_ids or []) + (b.source_event_ids or [])))

        # Helper: union evidence ids stored in record_data
        def _read_json_list(value: Any) -> List[str]:
            if not value:
                return []
            if isinstance(value, list):
                return [str(x) for x in value]
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(x) for x in parsed]
                except Exception:
                    return []
            return []

        def _read_list(value: Any) -> List[str]:
            if not value:
                return []
            if isinstance(value, list):
                return [str(x) for x in value]
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(x) for x in parsed]
                except Exception:
                    return []
            return []

        def _write_json_list(items: List[str]) -> str:
            return json.dumps(sorted(set(items)))

        # Choose base write deterministically: prefer INSERT over UPDATE
        base = a if a.operation.value == "INSERT" else b
        other = b if base is a else a

        # Ensure we don't lose idempotency key / phase provenance
        base.source_event_ids = merged_event_ids

        # INSERT base: merge in other write
        if base.operation.value == "INSERT":
            # Evidence ids
            base_eids = _read_json_list(base.record_data.get("source_episodes_json"))
            other_eids = _read_json_list(other.record_data.get("source_episodes_json"))
            # UPDATE writes store new evidence under a different key
            other_eids += _read_json_list(other.record_data.get("new_evidence_ids_json"))
            merged_eids = sorted(set(base_eids + other_eids + merged_event_ids))
            base.record_data["source_episodes_json"] = _write_json_list(merged_eids)
            base.record_data["observation_count"] = max(1, len(merged_eids))

            base_ev_ids = _read_list(base.record_data.get("evidence_event_ids"))
            other_ev_ids = _read_list(other.record_data.get("evidence_event_ids"))
            merged_ev_ids = sorted(set(base_ev_ids + other_ev_ids + merged_event_ids))
            if merged_ev_ids:
                base.record_data["evidence_event_ids"] = merged_ev_ids

            base_ep_ids = _read_list(base.record_data.get("evidence_episode_ids"))
            other_ep_ids = _read_list(other.record_data.get("evidence_episode_ids"))
            merged_ep_ids = sorted(set(base_ep_ids + other_ep_ids))
            if merged_ep_ids:
                base.record_data["evidence_episode_ids"] = merged_ep_ids

            # Weight/confidence
            rel = base.record_data.get("relation_type")
            base_weight = float(base.record_data.get("edge_weight") or 0.0)
            other_weight = float(other.record_data.get("edge_weight") or 0.0)
            if other.operation.value == "UPDATE":
                other_weight += float(other.record_data.get("weight_delta") or 0.0)
            if str(rel).upper() == "CAUSES":
                base.record_data["edge_weight"] = max(base_weight, other_weight)
            else:
                base.record_data["edge_weight"] = base_weight + other_weight

            base_conf = float(base.record_data.get("confidence_score") or 0.0)
            other_conf = float(other.record_data.get("confidence_score") or 0.0)
            if other.operation.value == "UPDATE":
                other_conf += float(other.record_data.get("confidence_delta") or 0.0)
            base.record_data["confidence_score"] = max(base_conf, other_conf)

            base.record_data["updated_at"] = _now_ms()
            return base

        # UPDATE base: merge deltas and evidence
        if base.operation.value == "UPDATE" and other.operation.value == "UPDATE":
            base.record_data["weight_delta"] = float(
                base.record_data.get("weight_delta") or 0.0
            ) + float(other.record_data.get("weight_delta") or 0.0)
            base.record_data["confidence_delta"] = float(
                base.record_data.get("confidence_delta") or 0.0
            ) + float(other.record_data.get("confidence_delta") or 0.0)

            e1 = _read_json_list(base.record_data.get("new_evidence_ids_json"))
            e2 = _read_json_list(other.record_data.get("new_evidence_ids_json"))
            merged = sorted(set(e1 + e2 + merged_event_ids))
            if merged:
                base.record_data["new_evidence_ids_json"] = _write_json_list(merged)

            ev1 = _read_list(base.record_data.get("new_evidence_event_ids"))
            ev2 = _read_list(other.record_data.get("new_evidence_event_ids"))
            merged_events = sorted(set(ev1 + ev2 + merged_event_ids))
            if merged_events:
                base.record_data["new_evidence_event_ids"] = merged_events

            ep1 = _read_list(base.record_data.get("new_evidence_episode_ids"))
            ep2 = _read_list(other.record_data.get("new_evidence_episode_ids"))
            merged_eps = sorted(set(ep1 + ep2))
            if merged_eps:
                base.record_data["new_evidence_episode_ids"] = merged_eps

            base.record_data["observation_count_increment"] = int(
                base.record_data.get("observation_count_increment") or 0
            ) + int(other.record_data.get("observation_count_increment") or 0)
            base.record_data["updated_at"] = _now_ms()
            return base

        # Fallback: keep base (prefer INSERT over UPDATE due to above selection)
        base.record_data["updated_at"] = _now_ms()
        return base

    def _create_edge_insert(self, edge: KGEdge) -> StagedWrite:
        """Create st_kg_edges INSERT for new edge."""
        now_ms = _now_ms()
        record_data = {
            "edge_id": edge.edge_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "version": 1,
            "source_entity_id": edge.source_entity_id,
            "target_entity_id": edge.target_entity_id,
            "relation_type": edge.relationship_type,
            "relation_subtype": edge.relation_subtype,
            "edge_weight": edge.weight,
            "confidence_score": edge.confidence,
            "source_episodes_json": json.dumps(edge.evidence_event_ids),
            "co_occurrence_count": len(edge.evidence_event_ids) if edge.evidence_event_ids else 1,
            "observation_count": len(edge.evidence_event_ids) if edge.evidence_event_ids else 1,
            "last_observed_at": edge.last_observed_at or now_ms,
            "decay_factor": 1.0,
            # GAP-007: New enrichment fields
            "source_algorithm": getattr(edge, "source_algorithm", None),
            "evidence_event_ids": edge.evidence_event_ids or [],
            "evidence_episode_ids": edge.evidence_episode_ids or [],
            "properties_json": getattr(edge, "properties_json", None),
            "algorithm_params_json": getattr(edge, "algorithm_params_json", None),
            "inference_chain_json": getattr(edge, "inference_chain_json", None),
            "archival_status": "ACTIVE",
            "valid_from": now_ms,
            "valid_from_ms": now_ms,
            "created_at": now_ms,
            "updated_at": now_ms,
        }

        idem_key = self.idempotency.for_truth_write(
            LAYER_ST_KG_EDGES,
            edge.edge_id,
        )

        write = StagedWrite.insert(
            layer=LAYER_ST_KG_EDGES,
            record_id=edge.edge_id,
            data=record_data,
            phase=self.source_phase,
            event_ids=edge.evidence_event_ids,
        )
        write.idempotency_key = idem_key
        # GAP-007: Attach observation context for st_observations recording
        write.observation_context = getattr(edge, "observation_context", None)

        return write

    def _create_causal_edge_insert(self, causal: CausalEdge) -> StagedWrite:
        """
        Create st_kg_edges INSERT for CausalEdge.

        CausalEdge is converted to KGEdge with relation_type CAUSES and
        Granger test metadata included in properties_json.
        """
        # Generate edge ID from source/target
        edge_id = f"causal_{causal.cause_entity_id}_{causal.effect_entity_id}"

        now_ms = _now_ms()

        # Store Granger metadata in properties_json
        properties = {
            "is_causal": True,
            "granger_p_value": causal.granger_p_value,
            "lag_days": causal.lag_days,
        }

        record_data = {
            "edge_id": edge_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "version": 1,
            "source_entity_id": causal.cause_entity_id,
            "target_entity_id": causal.effect_entity_id,
            "relation_type": "CAUSES",
            "edge_weight": causal.effect_size,
            "confidence_score": causal.confidence,
            "properties_json": json.dumps(properties),
            "source_episodes_json": "[]",
            "co_occurrence_count": 1,
            "observation_count": 1,
            "last_observed_at": now_ms,
            "decay_factor": 1.0,
            "archival_status": "ACTIVE",
            "valid_from": now_ms,
            "valid_from_ms": now_ms,
            "created_at": now_ms,
            "updated_at": now_ms,
        }

        idem_key = self.idempotency.for_truth_write(
            LAYER_ST_KG_EDGES,
            edge_id,
        )

        write = StagedWrite.insert(
            layer=LAYER_ST_KG_EDGES,
            record_id=edge_id,
            data=record_data,
            phase=self.source_phase,
            event_ids=[],
        )
        write.idempotency_key = idem_key

        return write

    def _create_edge_update(self, update: KGEdgeUpdate) -> Optional[StagedWrite]:
        """Create st_kg_edges UPDATE for existing edge."""
        if not update.edge_id:
            return None

        record_data: Dict[str, Any] = {
            "updated_at": _now_ms(),
        }

        # Apply weight delta
        if update.weight_delta != 0:
            record_data["weight_delta"] = update.weight_delta

        # Apply confidence delta
        if update.confidence_delta != 0:
            record_data["confidence_delta"] = update.confidence_delta

        # GAP-007: Apply new_weight (e.g., from weight_normalization)
        if hasattr(update, "new_weight") and update.new_weight is not None:
            record_data["new_weight"] = update.new_weight

        # Add new evidence IDs
        if update.new_evidence_ids:
            record_data["new_evidence_ids_json"] = json.dumps(update.new_evidence_ids)

        # GAP-007: Add new evidence event IDs array
        if hasattr(update, "new_evidence_event_ids") and update.new_evidence_event_ids:
            record_data["new_evidence_event_ids"] = update.new_evidence_event_ids

        # GAP-007: Add new evidence episode IDs array
        if hasattr(update, "new_evidence_episode_ids") and update.new_evidence_episode_ids:
            record_data["new_evidence_episode_ids"] = update.new_evidence_episode_ids

        # GAP-007: Source algorithm attribution
        if hasattr(update, "source_algorithm") and update.source_algorithm:
            record_data["source_algorithm"] = update.source_algorithm

        # GAP-001 M9: Increment observation_count for Granger causality
        if update.observation_count_increment > 0:
            record_data["observation_count_increment"] = update.observation_count_increment
            record_data["decay_factor"] = 1.0

        if update.last_observed_at:
            record_data["last_observed_at"] = update.last_observed_at
        elif (
            update.new_evidence_ids
            or update.new_evidence_event_ids
            or update.observation_count_increment > 0
        ):
            record_data["last_observed_at"] = _now_ms()

        idem_key = self.idempotency.for_truth_write(
            LAYER_ST_KG_EDGES,
            update.edge_id,
        )

        write = StagedWrite.update(
            layer=LAYER_ST_KG_EDGES,
            record_id=update.edge_id,
            data=record_data,
            phase=self.source_phase,
            expected_version=0,  # Resolved at R7
            event_ids=update.new_evidence_event_ids or update.new_evidence_ids,
        )
        write.idempotency_key = idem_key
        # GAP-007: Attach observation context for st_observations recording
        write.observation_context = getattr(update, "observation_context", None)

        return write

    # =========================================================================
    # Foreign Key Validation
    # =========================================================================

    def validate_foreign_keys(
        self,
        entity_ids: Set[str],
        edges: List[KGEdge],
        causal_edges: Optional[List[CausalEdge]] = None,
    ) -> ValidationResult:
        """
        Validate edge source/target reference existing entities.

        Checks that all edges reference entities that either:
        1. Already exist in the database (in entity_ids)
        2. Are being created in this batch

        Args:
            entity_ids: Set of known entity IDs (existing + new)
            edges: List of edges to validate
            causal_edges: Optional causal edges to validate

        Returns:
            ValidationResult with errors and orphan edge IDs
        """
        errors: List[str] = []
        orphan_edges: List[str] = []

        # Validate regular edges
        for edge in edges:
            if edge.source_entity_id not in entity_ids:
                errors.append(
                    f"Edge {edge.edge_id}: source_entity_id " f"'{edge.source_entity_id}' not found"
                )
                orphan_edges.append(edge.edge_id)
            elif edge.target_entity_id not in entity_ids:
                errors.append(
                    f"Edge {edge.edge_id}: target_entity_id " f"'{edge.target_entity_id}' not found"
                )
                orphan_edges.append(edge.edge_id)

        # Validate causal edges
        if causal_edges:
            for causal in causal_edges:
                edge_id = f"causal_{causal.cause_entity_id}_{causal.effect_entity_id}"
                if causal.cause_entity_id not in entity_ids:
                    errors.append(
                        f"CausalEdge {edge_id}: cause_entity_id "
                        f"'{causal.cause_entity_id}' not found"
                    )
                    orphan_edges.append(edge_id)
                elif causal.effect_entity_id not in entity_ids:
                    errors.append(
                        f"CausalEdge {edge_id}: effect_entity_id "
                        f"'{causal.effect_entity_id}' not found"
                    )
                    orphan_edges.append(edge_id)

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            orphan_edges=orphan_edges,
        )

    # =========================================================================
    # Aggregate Assembly
    # =========================================================================

    def assemble_all(
        self,
        entities: Optional[List[KGEntity]] = None,
        entity_updates: Optional[List[KGEntityUpdate]] = None,
        edges: Optional[List[KGEdge]] = None,
        edge_updates: Optional[List[KGEdgeUpdate]] = None,
        causal_edges: Optional[List[CausalEdge]] = None,
    ) -> Tuple[List[StagedWrite], List[StagedWrite]]:
        """
        Assemble all KG writes from R4 outputs.

        Returns entity writes and edge writes separately to maintain
        dependency order (entities must be committed before edges).

        Args:
            entities: List of KGEntity objects
            entity_updates: List of KGEntityUpdate objects
            edges: List of KGEdge objects
            edge_updates: List of KGEdgeUpdate objects
            causal_edges: List of CausalEdge objects

        Returns:
            Tuple of (entity_writes, edge_writes)
        """
        entity_writes = self.assemble_entity_writes(
            entities or [],
            entity_updates,
        )

        edge_writes = self.assemble_edge_writes(
            edges or [],
            edge_updates,
            causal_edges,
        )

        return entity_writes, edge_writes

    def get_new_entity_ids(self, entities: List[KGEntity]) -> Set[str]:
        """
        Extract entity IDs from new entities.

        Useful for FK validation when combined with existing entity IDs.

        Args:
            entities: List of KGEntity objects

        Returns:
            Set of entity IDs for new entities
        """
        return {e.entity_id for e in entities if e.is_new}


# =============================================================================
# Utility Functions
# =============================================================================


def count_kg_writes(
    entity_writes: List[StagedWrite],
    edge_writes: List[StagedWrite],
) -> Dict[str, int]:
    """
    Count KG writes by layer and operation.

    Args:
        entity_writes: List of st_kg_dom writes
        edge_writes: List of st_kg_edges writes

    Returns:
        Dict with counts per layer and operation type
    """
    result: Dict[str, int] = {
        "entity_inserts": 0,
        "entity_updates": 0,
        "edge_inserts": 0,
        "edge_updates": 0,
    }

    for w in entity_writes:
        if w.operation.value == "INSERT":
            result["entity_inserts"] += 1
        else:
            result["entity_updates"] += 1

    for w in edge_writes:
        if w.operation.value == "INSERT":
            result["edge_inserts"] += 1
        else:
            result["edge_updates"] += 1

    return result


def summarize_kg_assembly(
    entity_writes: List[StagedWrite],
    edge_writes: List[StagedWrite],
) -> str:
    """
    Generate human-readable summary of KG assembly.

    Args:
        entity_writes: List of st_kg_dom writes
        edge_writes: List of st_kg_edges writes

    Returns:
        Multi-line summary string
    """
    counts = count_kg_writes(entity_writes, edge_writes)

    return (
        f"KG Write Assembly Summary:\n"
        f"  st_kg_dom: {counts['entity_inserts']} inserts, "
        f"{counts['entity_updates']} updates\n"
        f"  st_kg_edges: {counts['edge_inserts']} inserts, "
        f"{counts['edge_updates']} updates\n"
        f"  Total: {len(entity_writes) + len(edge_writes)} writes"
    )
