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
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    StagedWrite,
)

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
        record_data = {
            "entity_id": entity.entity_id,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "version": 1,
            "canonical_name": entity.canonical_name,
            "entity_type": entity.entity_type,
            "entity_subtype": entity.entity_subtype,  # GAP-005: Fine-grained classification
            "aliases_json": entity.aliases_json,
            "confidence_score": entity.confidence,
            "embedding_id": entity.embedding_id,
            "source_episodes_json": json.dumps(entity.source_event_ids),
            "observation_count": len(entity.source_event_ids) if entity.source_event_ids else 1,
            "archival_status": "ACTIVE",
            "valid_from": now_ms,
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

        # Issue 3 Fix: Handle REINFORCE operations
        if update.observation_count_increment > 0:
            record_data["observation_count_increment"] = update.observation_count_increment

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
        writes: List[StagedWrite] = []

        # Process new edges (INSERT)
        for edge in edges:
            if edge.is_new:
                write = self._create_edge_insert(edge)
                writes.append(write)

        # Process causal edges (INSERT with is_causal=True)
        if causal_edges:
            for causal in causal_edges:
                write = self._create_causal_edge_insert(causal)
                writes.append(write)

        # Process edge updates (UPDATE)
        if edge_updates:
            for update in edge_updates:
                write = self._create_edge_update(update)
                if write:
                    writes.append(write)

        return writes

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
            "edge_weight": edge.weight,
            "confidence_score": edge.confidence,
            "source_episodes_json": json.dumps(edge.evidence_event_ids),
            "observation_count": len(edge.evidence_event_ids) if edge.evidence_event_ids else 1,
            "archival_status": "ACTIVE",
            "valid_from": now_ms,
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
            "observation_count": 1,
            "archival_status": "ACTIVE",
            "valid_from": now_ms,
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

        # Add new evidence IDs
        if update.new_evidence_ids:
            record_data["new_evidence_ids_json"] = json.dumps(update.new_evidence_ids)

        # GAP-001 M9: Increment observation_count for Granger causality
        if update.observation_count_increment > 0:
            record_data["observation_count_increment"] = update.observation_count_increment

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
            event_ids=update.new_evidence_ids,
        )
        write.idempotency_key = idem_key

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
