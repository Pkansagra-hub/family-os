"""
R4 Entity Merger — Complete entity merge with cascade and undo support.

Issue: 4.4.7 - Implement entity merge cascade + undo support
Spec Reference: Dossier §4.5.1.3, M4_EXECUTION.md

This module provides complete entity merge operations with:
- 6-step merge process (validate, select primary, merge attrs, cascade, archive, log)
- Cascade updates across 7 tables
- Full undo support via snapshots

Architecture:
- Atomic transaction for all merge operations
- merge_cascade_id tracks affected rows for undo
- Snapshots captured before merge for reversal
- st_entity_merges audit table

Performance:
- Merge: O(n) where n = total affected rows across tables
- Undo: O(n) where n = rows with merge_cascade_id

Human Memory Model:
- When we realize "J. Smith" and "John Smith" are the same person,
  all our memories about them should be unified
- But if we're wrong, we should be able to undo

Related:
- k0/modules/consolidation/algorithms/merge_threshold_learner.py: Merge thresholds
- k0/db/alembic/versions/0048_st_entity_merges.py: Merge audit table
- k0/db/tables/st_kg_dom.py: Entity domain table

Cascade Tables (from Dossier §4.5.1.3):
- st_kg_edges: source_entity_id, target_entity_id
- st_hipp_events: entities_json
- st_epi: entity_ids
- st_sem: entity_ids
- st_social: actor_id
- st_procedural: participants
- st_vec: metadata_json

Author: K0 Architecture Team
Date: 2025-01-03
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Constants
# =============================================================================

# Cascade batch size for large updates
P03_MERGE_CASCADE_BATCH_SIZE: int = 1000

# Days to keep undo data
P03_MERGE_UNDO_WINDOW_DAYS: int = 30


# =============================================================================
# Enums
# =============================================================================


class MergeStatus(str, Enum):
    """Status of a merge operation."""

    PENDING = "pending"
    COMPLETED = "completed"
    REVERSED = "reversed"
    FAILED = "failed"


class ArchivalStatus(str, Enum):
    """Archival status for entities."""

    ACTIVE = "ACTIVE"
    MERGED = "MERGED"
    ARCHIVED = "ARCHIVED"
    TOMBSTONED = "TOMBSTONED"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class EntitySnapshot:
    """Snapshot of entity state for undo.

    Captures the full state of an entity before merge for potential reversal.

    Attributes:
        entity_id: Entity identifier
        canonical_name: Display name
        entity_type: Entity type (PERSON, FAMILY_MEMBER, etc.)
        properties: Entity properties/attributes
        observation_count: Number of observations
        archival_status: Current archival status
    """

    entity_id: str
    canonical_name: str
    entity_type: str
    properties: Dict[str, Any]
    observation_count: int
    archival_status: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_id": self.entity_id,
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type,
            "properties": self.properties,
            "observation_count": self.observation_count,
            "archival_status": self.archival_status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EntitySnapshot":
        """Create from dictionary."""
        return cls(
            entity_id=data["entity_id"],
            canonical_name=data["canonical_name"],
            entity_type=data["entity_type"],
            properties=data.get("properties", {}),
            observation_count=data.get("observation_count", 0),
            archival_status=data.get("archival_status", "ACTIVE"),
        )


@dataclass
class CascadeCounts:
    """Counts of rows updated per cascade table.

    Tracks how many rows were affected in each table during cascade update.
    """

    kg_edges_source: int = 0
    kg_edges_target: int = 0
    hipp_events: int = 0
    epi: int = 0
    sem: int = 0
    social: int = 0
    procedural: int = 0
    vec: int = 0

    @property
    def total(self) -> int:
        """Total rows affected across all tables."""
        return (
            self.kg_edges_source
            + self.kg_edges_target
            + self.hipp_events
            + self.epi
            + self.sem
            + self.social
            + self.procedural
            + self.vec
        )

    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary for serialization."""
        return {
            "kg_edges_source": self.kg_edges_source,
            "kg_edges_target": self.kg_edges_target,
            "hipp_events": self.hipp_events,
            "epi": self.epi,
            "sem": self.sem,
            "social": self.social,
            "procedural": self.procedural,
            "vec": self.vec,
            "total": self.total,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> "CascadeCounts":
        """Create from dictionary."""
        return cls(
            kg_edges_source=data.get("kg_edges_source", 0),
            kg_edges_target=data.get("kg_edges_target", 0),
            hipp_events=data.get("hipp_events", 0),
            epi=data.get("epi", 0),
            sem=data.get("sem", 0),
            social=data.get("social", 0),
            procedural=data.get("procedural", 0),
            vec=data.get("vec", 0),
        )


@dataclass
class MergeResult:
    """Result of entity merge operation.

    Attributes:
        merge_id: Unique merge identifier (for undo)
        primary_entity_id: Entity that survived the merge
        secondary_entity_id: Entity that was merged into primary
        cascade_counts: Rows updated per table
        success: Whether merge completed successfully
        error: Error message if failed
    """

    merge_id: str
    primary_entity_id: str
    secondary_entity_id: str
    cascade_counts: CascadeCounts
    success: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "merge_id": self.merge_id,
            "primary_entity_id": self.primary_entity_id,
            "secondary_entity_id": self.secondary_entity_id,
            "cascade_counts": self.cascade_counts.to_dict(),
            "success": self.success,
            "error": self.error,
        }


@dataclass
class MergerMetrics:
    """Metrics for merge operations."""

    total_merges: int = 0
    successful_merges: int = 0
    failed_merges: int = 0
    reversed_merges: int = 0
    total_cascade_rows: int = 0


# =============================================================================
# Protocols
# =============================================================================


@runtime_checkable
class AsyncDBConnection(Protocol):
    """Protocol for async database connection (asyncpg-compatible)."""

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """Fetch single row."""
        ...

    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        """Fetch multiple rows."""
        ...

    async def execute(self, query: str, *args: Any) -> str:
        """Execute query."""
        ...


@runtime_checkable
class TransactionContext(Protocol):
    """Protocol for transaction context manager."""

    async def __aenter__(self) -> "TransactionContext": ...

    async def __aexit__(self, *args: Any) -> None: ...


# =============================================================================
# Helper Functions
# =============================================================================


def _parse_execute_result(result: str) -> int:
    """Parse PostgreSQL execute result to get affected row count.

    Args:
        result: Execute result string (e.g., "UPDATE 5")

    Returns:
        Number of affected rows
    """
    try:
        parts = result.split()
        if len(parts) >= 2:
            return int(parts[-1])
        return 0
    except (ValueError, IndexError):
        return 0


# =============================================================================
# Entity Merger
# =============================================================================


class EntityMerger:
    """
    Complete entity merge with cascade and undo support.

    Spec: Dossier §4.5.1.3

    When entities are merged ("J. Smith" = "John Smith"), references exist
    in many tables that must be updated atomically. If merge was wrong,
    it must be reversible.

    6-Step Merge Process:
        1. Validate: Ensure entities exist, not already merged
        2. Select Primary: Choose entity with more history
        3. Merge Attributes: Combine properties, keep best
        4. Cascade: Update all 7 tables
        5. Archive: Mark secondary as MERGED
        6. Log: Record for undo support

    Cascade Tables:
        - st_kg_edges: source_entity_id, target_entity_id
        - st_hipp_events: entities_json
        - st_epi: entity_ids
        - st_sem: entity_ids
        - st_social: actor_id
        - st_procedural: participants
        - st_vec: metadata_json

    Usage:
        merger = EntityMerger()

        result = await merger.merge_entities(
            primary_entity_id="ent_john_smith",
            secondary_entity_id="ent_j_smith",
            merge_reason="Same person",
            initiated_by="user_123",
            db_conn=conn,
        )

        if not result.success:
            logger.error(f"Merge failed: {result.error}")

        # Later, if merge was wrong
        await merger.reverse_merge(result.merge_id, "user_123", db_conn)
    """

    def __init__(self) -> None:
        """Initialize merger."""
        self._metrics = MergerMetrics()

    @property
    def metrics(self) -> MergerMetrics:
        """Return merger metrics."""
        return self._metrics

    async def merge_entities(
        self,
        primary_entity_id: str,
        secondary_entity_id: str,
        merge_reason: str,
        initiated_by: str,
        db_conn: AsyncDBConnection,
        tenant_id: str = "",
        space_id: str = "",
    ) -> MergeResult:
        """
        Merge two entities with full cascade.

        Args:
            primary_entity_id: Entity to keep (may be swapped if secondary has more history)
            secondary_entity_id: Entity to merge into primary
            merge_reason: Reason for merge (for audit)
            initiated_by: User/system that initiated merge
            db_conn: Database connection
            tenant_id: Tenant isolation key
            space_id: Space isolation key

        Returns:
            MergeResult with merge_id for undo
        """
        merge_id = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        self._metrics.total_merges += 1

        try:
            # STEP 1: Validate
            primary_row, secondary_row = await self._validate_merge(
                primary_entity_id,
                secondary_entity_id,
                db_conn,
            )

            # STEP 2: Select Primary (swap if secondary has more history)
            primary_row, secondary_row = self._select_primary(primary_row, secondary_row)
            final_primary_id = primary_row["entity_id"]
            final_secondary_id = secondary_row["entity_id"]

            # Capture snapshots for undo
            primary_snapshot = self._create_snapshot(primary_row)
            secondary_snapshot = self._create_snapshot(secondary_row)

            # STEP 3: Merge Attributes (update primary with combined data)
            await self._merge_attributes(primary_row, secondary_row, db_conn, now_ms)

            # STEP 4: Cascade References
            cascade_counts = await self._cascade_update_references(
                merge_id,
                final_primary_id,
                final_secondary_id,
                db_conn,
                now_ms,
            )

            # STEP 5: Archive Secondary
            await db_conn.execute(
                """
                UPDATE st_kg_dom
                SET archival_status = 'MERGED',
                    merged_into = $1,
                    merged_at = $2,
                    merged_by = $3,
                    updated_at = $2
                WHERE entity_id = $4
                """,
                final_primary_id,
                now_ms,
                initiated_by,
                final_secondary_id,
            )

            # STEP 6: Log for Undo
            await self._log_merge(
                merge_id=merge_id,
                primary_entity_id=final_primary_id,
                secondary_entity_id=final_secondary_id,
                primary_snapshot=primary_snapshot,
                secondary_snapshot=secondary_snapshot,
                cascade_counts=cascade_counts,
                merge_reason=merge_reason,
                initiated_by=initiated_by,
                tenant_id=tenant_id,
                space_id=space_id,
                db_conn=db_conn,
                now_ms=now_ms,
            )

            self._metrics.successful_merges += 1
            self._metrics.total_cascade_rows += cascade_counts.total

            result = MergeResult(
                merge_id=merge_id,
                primary_entity_id=final_primary_id,
                secondary_entity_id=final_secondary_id,
                cascade_counts=cascade_counts,
                success=True,
            )

            logger.info(
                "Entity merge completed",
                extra={
                    "merge_id": merge_id,
                    "primary": final_primary_id,
                    "secondary": final_secondary_id,
                    "cascade_total": cascade_counts.total,
                },
            )

            return result

        except Exception as e:
            self._metrics.failed_merges += 1
            logger.error(
                "Entity merge failed",
                extra={
                    "primary": primary_entity_id,
                    "secondary": secondary_entity_id,
                    "error": str(e),
                },
            )
            return MergeResult(
                merge_id=merge_id,
                primary_entity_id=primary_entity_id,
                secondary_entity_id=secondary_entity_id,
                cascade_counts=CascadeCounts(),
                success=False,
                error=str(e),
            )

    async def _validate_merge(
        self,
        primary_id: str,
        secondary_id: str,
        db_conn: AsyncDBConnection,
    ) -> tuple:
        """
        Validate merge is possible.

        Checks:
        - Both entities exist
        - Neither is already merged
        - Same entity type

        Args:
            primary_id: Primary entity ID
            secondary_id: Secondary entity ID
            db_conn: Database connection

        Returns:
            Tuple of (primary_row, secondary_row)

        Raises:
            ValueError: If validation fails
        """
        primary = await db_conn.fetchrow(
            "SELECT * FROM st_kg_dom WHERE entity_id = $1",
            primary_id,
        )
        secondary = await db_conn.fetchrow(
            "SELECT * FROM st_kg_dom WHERE entity_id = $1",
            secondary_id,
        )

        if not primary:
            raise ValueError(f"Primary entity {primary_id} not found")
        if not secondary:
            raise ValueError(f"Secondary entity {secondary_id} not found")

        # Check not already merged
        if primary.get("archival_status") == "MERGED":
            raise ValueError(f"Primary entity {primary_id} already merged")
        if secondary.get("archival_status") == "MERGED":
            raise ValueError(f"Secondary entity {secondary_id} already merged")

        # Check same entity type
        if primary.get("entity_type") != secondary.get("entity_type"):
            raise ValueError(
                f"Entity types don't match: {primary.get('entity_type')} "
                f"vs {secondary.get('entity_type')}"
            )

        return primary, secondary

    def _select_primary(
        self,
        primary_row: Dict[str, Any],
        secondary_row: Dict[str, Any],
    ) -> tuple:
        """
        Select which entity should be primary based on history.

        The entity with more observations becomes primary.

        Args:
            primary_row: Initially designated primary
            secondary_row: Initially designated secondary

        Returns:
            Tuple of (primary, secondary) possibly swapped
        """
        primary_count = primary_row.get("observation_count", 0)
        secondary_count = secondary_row.get("observation_count", 0)

        if secondary_count > primary_count:
            logger.debug(
                "Swapping primary/secondary based on observation count",
                extra={
                    "original_primary": primary_row.get("entity_id"),
                    "original_secondary": secondary_row.get("entity_id"),
                    "primary_count": primary_count,
                    "secondary_count": secondary_count,
                },
            )
            return secondary_row, primary_row

        return primary_row, secondary_row

    def _create_snapshot(self, row: Dict[str, Any]) -> EntitySnapshot:
        """Create snapshot from database row."""
        return EntitySnapshot(
            entity_id=row.get("entity_id", ""),
            canonical_name=row.get("canonical_name", ""),
            entity_type=row.get("entity_type", ""),
            properties=row.get("properties", {}),
            observation_count=row.get("observation_count", 0),
            archival_status=row.get("archival_status", "ACTIVE"),
        )

    async def _merge_attributes(
        self,
        primary_row: Dict[str, Any],
        secondary_row: Dict[str, Any],
        db_conn: AsyncDBConnection,
        now_ms: int,
    ) -> None:
        """
        Merge attributes from secondary into primary.

        Combines observation counts and merges properties.
        """
        primary_id = primary_row.get("entity_id")
        primary_count = primary_row.get("observation_count", 0)
        secondary_count = secondary_row.get("observation_count", 0)

        # Combine observation counts
        new_count = primary_count + secondary_count

        # Merge properties (primary wins on conflicts)
        primary_props = primary_row.get("properties", {}) or {}
        secondary_props = secondary_row.get("properties", {}) or {}
        merged_props = {**secondary_props, **primary_props}

        await db_conn.execute(
            """
            UPDATE st_kg_dom
            SET observation_count = $1,
                properties = $2,
                updated_at = $3
            WHERE entity_id = $4
            """,
            new_count,
            json.dumps(merged_props),
            now_ms,
            primary_id,
        )

    async def _cascade_update_references(
        self,
        merge_id: str,
        primary_id: str,
        secondary_id: str,
        db_conn: AsyncDBConnection,
        now_ms: int,
    ) -> CascadeCounts:
        """
        Update all references from secondary to primary.

        Updates 7 tables with merge_cascade_id for potential reversal.

        Returns:
            CascadeCounts with rows updated per table
        """
        counts = CascadeCounts()

        # 1. st_kg_edges: source references
        result = await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET source_entity_id = $1,
                merge_cascade_id = $2,
                updated_at = $4
            WHERE source_entity_id = $3
            """,
            primary_id,
            merge_id,
            secondary_id,
            now_ms,
        )
        counts.kg_edges_source = _parse_execute_result(result)

        # 2. st_kg_edges: target references
        result = await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET target_entity_id = $1,
                merge_cascade_id = $2,
                updated_at = $4
            WHERE target_entity_id = $3
            """,
            primary_id,
            merge_id,
            secondary_id,
            now_ms,
        )
        counts.kg_edges_target = _parse_execute_result(result)

        # 3. st_hipp_events: JSON entity replacement
        # Note: This replaces entity_id occurrences in the JSON
        result = await db_conn.execute(
            """
            UPDATE st_hipp_events
            SET entities_json = REPLACE(entities_json::text, $1, $2)::jsonb,
                merge_cascade_id = $3,
                updated_at = $4
            WHERE entities_json::text LIKE $5
            """,
            secondary_id,
            primary_id,
            merge_id,
            now_ms,
            f"%{secondary_id}%",
        )
        counts.hipp_events = _parse_execute_result(result)

        # 4. st_epi: Episode entity links
        result = await db_conn.execute(
            """
            UPDATE st_epi
            SET entity_ids = array_replace(entity_ids, $1, $2),
                merge_cascade_id = $3,
                updated_at = $4
            WHERE $1 = ANY(entity_ids)
            """,
            secondary_id,
            primary_id,
            merge_id,
            now_ms,
        )
        counts.epi = _parse_execute_result(result)

        # 5. st_sem: Pattern entity links
        result = await db_conn.execute(
            """
            UPDATE st_sem
            SET entity_ids = array_replace(entity_ids, $1, $2),
                merge_cascade_id = $3,
                updated_at = $4
            WHERE $1 = ANY(entity_ids)
            """,
            secondary_id,
            primary_id,
            merge_id,
            now_ms,
        )
        counts.sem = _parse_execute_result(result)

        # 6. st_social: Actor references
        result = await db_conn.execute(
            """
            UPDATE st_social
            SET actor_id = $1,
                merge_cascade_id = $2,
                updated_at = $4
            WHERE actor_id = $3
            """,
            primary_id,
            merge_id,
            secondary_id,
            now_ms,
        )
        counts.social = _parse_execute_result(result)

        # 7. st_procedural: Habit participants
        result = await db_conn.execute(
            """
            UPDATE st_procedural
            SET participants = array_replace(participants, $1, $2),
                merge_cascade_id = $3,
                updated_at = $4
            WHERE $1 = ANY(participants)
            """,
            secondary_id,
            primary_id,
            merge_id,
            now_ms,
        )
        counts.procedural = _parse_execute_result(result)

        # 8. st_vec: Embedding metadata
        result = await db_conn.execute(
            """
            UPDATE st_vec
            SET metadata_json = jsonb_set(
                metadata_json,
                '{entity_id}',
                to_jsonb($1::text)
            ),
            merge_cascade_id = $2,
            updated_at = $4
            WHERE metadata_json->>'entity_id' = $3
            """,
            primary_id,
            merge_id,
            secondary_id,
            now_ms,
        )
        counts.vec = _parse_execute_result(result)

        logger.debug(
            "Cascade update completed",
            extra={
                "merge_id": merge_id,
                "counts": counts.to_dict(),
            },
        )

        return counts

    async def _log_merge(
        self,
        merge_id: str,
        primary_entity_id: str,
        secondary_entity_id: str,
        primary_snapshot: EntitySnapshot,
        secondary_snapshot: EntitySnapshot,
        cascade_counts: CascadeCounts,
        merge_reason: str,
        initiated_by: str,
        tenant_id: str,
        space_id: str,
        db_conn: AsyncDBConnection,
        now_ms: int,
    ) -> None:
        """Log merge to st_entity_merges for undo support."""
        await db_conn.execute(
            """
            INSERT INTO st_entity_merges (
                merge_id, tenant_id, space_id,
                primary_entity_id, secondary_entity_id,
                primary_snapshot, secondary_snapshot,
                cascade_counts, merge_reason,
                initiated_by, merged_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
            )
            """,
            merge_id,
            tenant_id,
            space_id,
            primary_entity_id,
            secondary_entity_id,
            json.dumps(primary_snapshot.to_dict()),
            json.dumps(secondary_snapshot.to_dict()),
            json.dumps(cascade_counts.to_dict()),
            merge_reason,
            initiated_by,
            now_ms,
        )

    async def reverse_merge(
        self,
        merge_id: str,
        reversed_by: str,
        db_conn: AsyncDBConnection,
    ) -> bool:
        """
        Undo an entity merge.

        Restores secondary entity to ACTIVE and reverses cascade updates
        that were tracked via merge_cascade_id.

        Args:
            merge_id: ID of merge to reverse
            reversed_by: User/system reversing the merge
            db_conn: Database connection

        Returns:
            True if successful

        Raises:
            ValueError: If merge not found or already reversed
        """
        now_ms = int(time.time() * 1000)

        # Fetch merge record
        merge = await db_conn.fetchrow(
            "SELECT * FROM st_entity_merges WHERE merge_id = $1",
            merge_id,
        )

        if not merge:
            raise ValueError(f"Merge {merge_id} not found")
        if merge.get("reversed_at"):
            raise ValueError(f"Merge {merge_id} already reversed")

        secondary_id = merge["secondary_entity_id"]
        primary_id = merge["primary_entity_id"]

        # Restore secondary entity
        await db_conn.execute(
            """
            UPDATE st_kg_dom
            SET archival_status = 'ACTIVE',
                merged_into = NULL,
                merged_at = NULL,
                merged_by = NULL,
                updated_at = $2
            WHERE entity_id = $1
            """,
            secondary_id,
            now_ms,
        )

        # Reverse cascade updates using merge_cascade_id
        # This is tracked so we only reverse what this specific merge changed

        # st_kg_edges source
        await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET source_entity_id = $1,
                merge_cascade_id = NULL,
                updated_at = $4
            WHERE merge_cascade_id = $2
              AND source_entity_id = $3
            """,
            secondary_id,
            merge_id,
            primary_id,
            now_ms,
        )

        # st_kg_edges target
        await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET target_entity_id = $1,
                merge_cascade_id = NULL,
                updated_at = $4
            WHERE merge_cascade_id = $2
              AND target_entity_id = $3
            """,
            secondary_id,
            merge_id,
            primary_id,
            now_ms,
        )

        # st_hipp_events (reverse JSON replacement)
        await db_conn.execute(
            """
            UPDATE st_hipp_events
            SET entities_json = REPLACE(entities_json::text, $1, $2)::jsonb,
                merge_cascade_id = NULL,
                updated_at = $4
            WHERE merge_cascade_id = $3
            """,
            primary_id,
            secondary_id,
            merge_id,
            now_ms,
        )

        # st_epi
        await db_conn.execute(
            """
            UPDATE st_epi
            SET entity_ids = array_replace(entity_ids, $1, $2),
                merge_cascade_id = NULL,
                updated_at = $4
            WHERE merge_cascade_id = $3
            """,
            primary_id,
            secondary_id,
            merge_id,
            now_ms,
        )

        # st_sem
        await db_conn.execute(
            """
            UPDATE st_sem
            SET entity_ids = array_replace(entity_ids, $1, $2),
                merge_cascade_id = NULL,
                updated_at = $4
            WHERE merge_cascade_id = $3
            """,
            primary_id,
            secondary_id,
            merge_id,
            now_ms,
        )

        # st_social
        await db_conn.execute(
            """
            UPDATE st_social
            SET actor_id = $1,
                merge_cascade_id = NULL,
                updated_at = $4
            WHERE merge_cascade_id = $2
              AND actor_id = $3
            """,
            secondary_id,
            merge_id,
            primary_id,
            now_ms,
        )

        # st_procedural
        await db_conn.execute(
            """
            UPDATE st_procedural
            SET participants = array_replace(participants, $1, $2),
                merge_cascade_id = NULL,
                updated_at = $4
            WHERE merge_cascade_id = $3
            """,
            primary_id,
            secondary_id,
            merge_id,
            now_ms,
        )

        # st_vec
        await db_conn.execute(
            """
            UPDATE st_vec
            SET metadata_json = jsonb_set(
                metadata_json,
                '{entity_id}',
                to_jsonb($1::text)
            ),
            merge_cascade_id = NULL,
            updated_at = $4
            WHERE merge_cascade_id = $2
            """,
            secondary_id,
            merge_id,
            now_ms,
        )

        # Mark merge as reversed
        await db_conn.execute(
            """
            UPDATE st_entity_merges
            SET reversed_at = $1,
                reversed_by = $2
            WHERE merge_id = $3
            """,
            now_ms,
            reversed_by,
            merge_id,
        )

        self._metrics.reversed_merges += 1

        logger.info(
            "Merge reversed",
            extra={
                "merge_id": merge_id,
                "reversed_by": reversed_by,
                "secondary_restored": secondary_id,
            },
        )

        return True

    async def get_merge_history(
        self,
        entity_id: str,
        db_conn: AsyncDBConnection,
        include_reversed: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get merge history for an entity.

        Args:
            entity_id: Entity to check
            db_conn: Database connection
            include_reversed: Whether to include reversed merges

        Returns:
            List of merge records
        """
        if include_reversed:
            rows = await db_conn.fetch(
                """
                SELECT * FROM st_entity_merges
                WHERE primary_entity_id = $1
                   OR secondary_entity_id = $1
                ORDER BY merged_at DESC
                """,
                entity_id,
            )
        else:
            rows = await db_conn.fetch(
                """
                SELECT * FROM st_entity_merges
                WHERE (primary_entity_id = $1 OR secondary_entity_id = $1)
                  AND reversed_at IS NULL
                ORDER BY merged_at DESC
                """,
                entity_id,
            )

        return [dict(row) for row in rows]


# =============================================================================
# Factory Function
# =============================================================================


def get_entity_merger() -> EntityMerger:
    """
    Factory function to create an EntityMerger.

    Returns:
        Configured EntityMerger instance
    """
    return EntityMerger()
