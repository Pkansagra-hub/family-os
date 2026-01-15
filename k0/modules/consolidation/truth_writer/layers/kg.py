"""
KGLayerWriter — Issue 5.2.8

Writer for st_kg_dom (entities) and st_kg_edges (relationships) layers.
Handles knowledge graph persistence from M21 KGConsolidator.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.8 — st_kg_dom / st_kg_edges layer writer)
    - Dossier §4.8.7 (st_kg_dom / st_kg_edges Writes)

Operations for st_kg_dom (entities):
    INSERT: Create new entity
    UPDATE with Actions:
        - EXTEND: Update attributes, boost confidence
        - EVOLVE: Mark old entity invalid (temporal versioning)
    ARCHIVE: Soft-delete low-confidence entity

Operations for st_kg_edges (edges):
    INSERT: Create new edge
    UPDATE: Update confidence/attributes
    ARCHIVE: Soft-delete low-confidence edge

Supports:
    - Entity merge tracking in st_entity_merges
    - Granger causality CAUSES edges with precedence_ratio
    - Temporal validity (valid_from/valid_to)
    - Binary embedding vectors

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from k0.modules.consolidation.truth_writer.result import LayerWriteResult
from k0.pipelines.p03.phases.r7_truth_writer import OptimisticLockError
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    StagedWrite,
    WriteOperation,
)

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


class EntityAction(str, Enum):
    """
    Actions for entity updates.

    EXTEND: Update attributes, boost confidence
    EVOLVE: Mark old entity invalid for temporal versioning
    """

    EXTEND = "EXTEND"
    EVOLVE = "EVOLVE"


@dataclass
class EntityWriteData:
    """
    Data structure for st_kg_dom (entity) writes.

    Represents a knowledge graph entity.

    Attributes:
        entity_id: Unique entity identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        entity_type: Type (PERSON, LOCATION, EVENT, etc.)
        canonical_name: Canonical entity name
        attributes_json: JSON object with entity attributes
        embedding: Binary embedding vector (optional)
        confidence: Confidence score [0.0, 1.0]
        valid_from_ms: Temporal validity start (MILLISECONDS)
        valid_to_ms: Temporal validity end (MILLISECONDS, optional)
        source_events_json: JSON array of contributing event IDs
    """

    entity_id: str
    tenant_id: str
    space_id: str
    entity_type: str = "UNKNOWN"
    canonical_name: str = ""
    attributes_json: str = "{}"
    embedding: Optional[bytes] = None
    confidence: float = 1.0
    valid_from_ms: int = 0
    valid_to_ms: Optional[int] = None
    source_events_json: str = "[]"


@dataclass
class EdgeWriteData:
    """
    Data structure for st_kg_edges (edge) writes.

    Represents a knowledge graph edge (relationship).

    Attributes:
        edge_id: Unique edge identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        source_entity_id: Source entity ID
        target_entity_id: Target entity ID
        relation_type: Type (KNOWS, LOCATED_AT, CAUSES, etc.)
        confidence: Confidence score [0.0, 1.0]
        valid_from_ms: Temporal validity start (MILLISECONDS)
        valid_to_ms: Temporal validity end (MILLISECONDS, optional)
        precedence_ratio: For Granger causality CAUSES edges (optional)
        attributes_json: JSON object with edge attributes
    """

    edge_id: str
    tenant_id: str
    space_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str = "RELATED_TO"
    confidence: float = 1.0
    valid_from_ms: int = 0
    valid_to_ms: Optional[int] = None
    precedence_ratio: Optional[float] = None  # For CAUSES edges
    attributes_json: str = "{}"


class KGLayerWriter:
    """
    Writer for st_kg_dom (entities) and st_kg_edges (relationships) layers.

    This is a dual-layer writer that handles both entity and edge tables.

    Tables:
        st_kg_dom: Entity table (PK: entity_id)
        st_kg_edges: Edge table (PK: edge_id)
        st_entity_merges: Merge tracking table

    Version Column: version (for optimistic locking)

    Action-Based Entity Updates:
        EXTEND: Merge attributes, boost confidence
        EVOLVE: Mark entity as superseded (set valid_to)

    Edge Updates:
        Direct confidence and attribute updates

    Usage:
        writer = KGLayerWriter()
        result = await writer.write(staged_writes, uow)
    """

    # Layers handled by this writer
    LAYERS = (LAYER_ST_KG_DOM, LAYER_ST_KG_EDGES)

    # Confidence boost factor for EXTEND (multiplicative, capped at 1.0)
    EXTEND_BOOST = 1.1

    @property
    def layers(self) -> tuple[str, str]:
        """Target layer names (entities and edges)."""
        return self.LAYERS

    async def write(
        self,
        writes: List[StagedWrite],
        uow: UnitOfWork,
    ) -> LayerWriteResult:
        """
        Execute KG layer writes (both entities and edges).

        Routes writes to entity or edge handlers based on layer.
        Continues processing on failure to maximize partial success.

        Args:
            writes: List of StagedWrite objects for KG layers
            uow: UnitOfWork providing database connection

        Returns:
            LayerWriteResult with combined success/failure counts
        """
        succeeded = 0
        failed_ids: List[str] = []
        error_messages: List[str] = []

        for write in writes:
            try:
                if write.layer == LAYER_ST_KG_DOM:
                    await self._write_entity(uow, write)
                    succeeded += 1
                elif write.layer == LAYER_ST_KG_EDGES:
                    await self._write_edge(uow, write)
                    succeeded += 1
                # Ignore writes for other layers
            except OptimisticLockError:
                failed_ids.append(write.record_id)
                error_messages.append(f"Version conflict for KG record {write.record_id}")
            except Exception as e:
                failed_ids.append(write.record_id)
                error_messages.append(f"Failed to write {write.record_id}: {e}")

        # Count writes for this writer's layers
        kg_writes = [w for w in writes if w.layer in self.LAYERS]

        return LayerWriteResult(
            layer="kg",  # Combined layer name for dual-table writer
            writes_attempted=len(kg_writes),
            writes_succeeded=succeeded,
            writes_failed=len(failed_ids),
            failed_ids=failed_ids,
            error_message="; ".join(error_messages) if error_messages else None,
        )

    # ─────────────────────────────────────────────────────────────────
    # Entity (st_kg_dom) Operations
    # ─────────────────────────────────────────────────────────────────

    async def _write_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """Route entity write to appropriate handler."""
        if write.operation == WriteOperation.INSERT:
            await self._insert_entity(uow, write)
        elif write.operation == WriteOperation.UPDATE:
            await self._update_entity(uow, write)
        elif write.operation == WriteOperation.ARCHIVE:
            await self._archive_entity(uow, write)
        elif write.operation == WriteOperation.TOMBSTONE:
            await self._tombstone_entity(uow, write)

    async def _insert_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        INSERT new entity into st_kg_dom.

        Creates a new entity record with initial values.
        Uses ON CONFLICT DO NOTHING for idempotency.
        """
        data = write.record_data
        now = _now_ms()

        await uow.connection.execute(
            """
            INSERT INTO st_kg_dom (
                entity_id, tenant_id, space_id, entity_type,
                canonical_name, attributes_json, embedding,
                confidence, valid_from, valid_to,
                source_events_json, created_at, version
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 1)
            ON CONFLICT (entity_id) DO NOTHING
            """,
            data["entity_id"],
            data["tenant_id"],
            data["space_id"],
            data.get("entity_type", "UNKNOWN"),
            data.get("canonical_name", ""),
            data.get("attributes_json", "{}"),
            data.get("embedding"),  # bytes or None
            data.get("confidence", 1.0),
            data.get("valid_from_ms", now),
            data.get("valid_to_ms"),
            data.get("source_events_json", "[]"),
            now,
        )

    async def _update_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        UPDATE entity based on action type or special fields.

        Handles:
            - query_count_increment: Increment query_count and update last_queried_at
            - milestone_append: Append milestone to milestones_json
            - _action EXTEND: Update attributes, boost confidence
            - _action EVOLVE: Mark old entity invalid

        Raises OptimisticLockError if version mismatch.
        """
        data = write.record_data

        # Handle special intent signal fields first
        if "query_count_increment" in data:
            await self._update_entity_query_boost(uow, write)
            return
        if "milestone_append" in data:
            await self._update_entity_milestone(uow, write)
            return

        # Standard action-based handling
        action = data.get("_action", "EXTEND")

        if action == EntityAction.EXTEND or action == "EXTEND":
            await self._update_entity_extend(uow, write)
        elif action == EntityAction.EVOLVE or action == "EVOLVE":
            await self._update_entity_evolve(uow, write)
        else:
            # Default to EXTEND for unknown actions
            await self._update_entity_extend(uow, write)

    async def _update_entity_query_boost(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        QUERY_BOOST: Increment query_count and update last_queried_at.

        Used by IntentSignalAssembler for QUERY_BOOST signals.
        Skips version check since this is a low-priority update.
        """
        data = write.record_data
        increment = data.get("query_count_increment", 1)
        last_queried_at = data.get("last_queried_at", _now_ms())

        await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET query_count = COALESCE(query_count, 0) + $1,
                last_queried_at = $2
            WHERE entity_id = $3
            """,
            increment,
            last_queried_at,
            write.record_id,
        )

    async def _update_entity_milestone(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        MILESTONE: Append milestone entry to milestones_json.

        Used by IntentSignalAssembler for MILESTONE signals.
        Uses jsonb_insert to append to existing array.
        """
        data = write.record_data
        milestone_entry = data.get("milestone_append", {})

        import json

        milestone_json = json.dumps(milestone_entry)

        # Append milestone to milestones_json array
        # Initialize array if null
        await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET milestones_json = COALESCE(milestones_json::jsonb, '[]'::jsonb) || $1::jsonb,
                updated_at = $2
            WHERE entity_id = $3
            """,
            f"[{milestone_json}]",  # Wrap in array for concatenation
            data.get("updated_at", _now_ms()),
            write.record_id,
        )

    async def _update_entity_extend(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """EXTEND: Update attributes, merge events, boost confidence."""
        data = write.record_data
        result = await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET attributes_json = attributes_json || COALESCE($1::jsonb, '{}'::jsonb),
                source_events_json = source_events_json || COALESCE($2::jsonb, '[]'::jsonb),
                confidence = LEAST(confidence * $3, 1.0),
                version = version + 1
            WHERE entity_id = $4 AND version = $5
            """,
            data.get("new_attributes_json", "{}"),
            data.get("new_events_json", "[]"),
            self.EXTEND_BOOST,
            write.record_id,
            write.expected_version,
        )

        if result == "UPDATE 0":
            raise OptimisticLockError(f"Version conflict updating entity {write.record_id}")

    async def _update_entity_evolve(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """EVOLVE: Mark old entity as superseded (set valid_to)."""
        now = _now_ms()
        result = await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET valid_to = $1,
                version = version + 1
            WHERE entity_id = $2 AND version = $3
            """,
            now,
            write.record_id,
            write.expected_version,
        )

        if result == "UPDATE 0":
            raise OptimisticLockError(f"Version conflict evolving entity {write.record_id}")

    async def _archive_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """ARCHIVE low-confidence entity."""
        now = _now_ms()
        reason = write.record_data.get("archived_reason", "low_confidence")

        await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET archival_status = 'ARCHIVED',
                archived_at = $1,
                archived_reason = $2
            WHERE entity_id = $3
              AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
            """,
            now,
            reason,
            write.record_id,
        )

    async def _tombstone_entity(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """TOMBSTONE entity for GDPR deletion."""
        now = _now_ms()
        await uow.connection.execute(
            """
            UPDATE st_kg_dom
            SET canonical_name = '',
                attributes_json = '{}',
                embedding = NULL,
                source_events_json = '[]',
                archival_status = 'TOMBSTONE',
                archived_at = $1,
                archived_reason = 'gdpr_deletion'
            WHERE entity_id = $2
            """,
            now,
            write.record_id,
        )

    # ─────────────────────────────────────────────────────────────────
    # Edge (st_kg_edges) Operations
    # ─────────────────────────────────────────────────────────────────

    async def _write_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """Route edge write to appropriate handler."""
        if write.operation == WriteOperation.INSERT:
            await self._insert_edge(uow, write)
        elif write.operation == WriteOperation.UPDATE:
            await self._update_edge(uow, write)
        elif write.operation == WriteOperation.ARCHIVE:
            await self._archive_edge(uow, write)
        elif write.operation == WriteOperation.TOMBSTONE:
            await self._tombstone_edge(uow, write)

    async def _insert_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        INSERT new edge into st_kg_edges.

        Creates a new edge record. Supports Granger causality edges
        with precedence_ratio for CAUSES relation type.
        Uses ON CONFLICT DO NOTHING for idempotency.
        """
        data = write.record_data
        now = _now_ms()

        await uow.connection.execute(
            """
            INSERT INTO st_kg_edges (
                edge_id, tenant_id, space_id,
                source_entity_id, target_entity_id, relation_type,
                confidence, valid_from, valid_to,
                precedence_ratio, attributes_json,
                created_at, version
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 1)
            ON CONFLICT (edge_id) DO NOTHING
            """,
            data["edge_id"],
            data["tenant_id"],
            data["space_id"],
            data["source_entity_id"],
            data["target_entity_id"],
            data.get("relation_type", "RELATED_TO"),
            data.get("confidence", 1.0),
            data.get("valid_from_ms", now),
            data.get("valid_to_ms"),
            data.get("precedence_ratio"),  # For CAUSES edges
            data.get("attributes_json", "{}"),
            now,
        )

    async def _update_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        UPDATE edge confidence/attributes or handle special fields.

        Handles:
            - query_count_increment: Increment query_count and update last_queried_at
            - Standard confidence/attributes update

        Raises OptimisticLockError if version mismatch.
        """
        data = write.record_data

        # Handle special intent signal fields
        if "query_count_increment" in data:
            await self._update_edge_query_boost(uow, write)
            return

        # Standard edge update
        result = await uow.connection.execute(
            """
            UPDATE st_kg_edges
            SET confidence = COALESCE($1, confidence),
                attributes_json = attributes_json || COALESCE($2::jsonb, '{}'::jsonb),
                version = version + 1
            WHERE edge_id = $3 AND version = $4
            """,
            data.get("confidence"),
            data.get("new_attributes_json", "{}"),
            write.record_id,
            write.expected_version,
        )

        if result == "UPDATE 0":
            raise OptimisticLockError(f"Version conflict updating edge {write.record_id}")

    async def _update_edge_query_boost(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        QUERY_BOOST: Increment query_count and update last_queried_at for edge.

        Used by IntentSignalAssembler for QUERY_BOOST signals.
        Skips version check since this is a low-priority update.
        """
        data = write.record_data
        increment = data.get("query_count_increment", 1)
        last_queried_at = data.get("last_queried_at", _now_ms())

        await uow.connection.execute(
            """
            UPDATE st_kg_edges
            SET query_count = COALESCE(query_count, 0) + $1,
                last_queried_at = $2
            WHERE edge_id = $3
            """,
            increment,
            last_queried_at,
            write.record_id,
        )

    async def _archive_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """ARCHIVE low-confidence edge."""
        now = _now_ms()
        reason = write.record_data.get("archived_reason", "low_confidence")

        await uow.connection.execute(
            """
            UPDATE st_kg_edges
            SET archival_status = 'ARCHIVED',
                archived_at = $1,
                archived_reason = $2
            WHERE edge_id = $3
              AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
            """,
            now,
            reason,
            write.record_id,
        )

    async def _tombstone_edge(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """TOMBSTONE edge for GDPR deletion."""
        now = _now_ms()
        await uow.connection.execute(
            """
            UPDATE st_kg_edges
            SET attributes_json = '{}',
                archival_status = 'TOMBSTONE',
                archived_at = $1,
                archived_reason = 'gdpr_deletion'
            WHERE edge_id = $2
            """,
            now,
            write.record_id,
        )

    # ─────────────────────────────────────────────────────────────────
    # Merge Tracking
    # ─────────────────────────────────────────────────────────────────

    async def track_merge(
        self,
        uow: UnitOfWork,
        source_id: str,
        target_id: str,
        merge_reason: str,
    ) -> None:
        """
        Track entity merge in st_entity_merges for undo support.

        Records that source_id was merged into target_id.
        Used by R4 EntityMerger cascade and supports future undo.

        Args:
            uow: UnitOfWork providing database connection
            source_id: Entity ID that was merged (now obsolete)
            target_id: Entity ID that absorbed the merge
            merge_reason: Reason for merge (e.g., "duplicate", "alias")
        """
        now = _now_ms()
        await uow.connection.execute(
            """
            INSERT INTO st_entity_merges (
                source_entity_id, target_entity_id,
                merge_reason, merged_at
            ) VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_entity_id, target_entity_id) DO NOTHING
            """,
            source_id,
            target_id,
            merge_reason,
            now,
        )


def create_kg_writer() -> KGLayerWriter:
    """Factory function to create KGLayerWriter instance."""
    return KGLayerWriter()
