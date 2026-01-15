"""
SemanticLayerWriter — Issue 5.2.4

Writer for st_sem (semantic memory) layer.
Handles pattern records with action-based updates.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.4 — st_sem layer writer)
    - Dossier §4.8.3 (st_sem Writes)

Operations:
    INSERT: Create new pattern with source episodes
    UPDATE with Actions:
        - REINFORCE: Boost confidence, increment observation_count
        - EXTEND: Append episodes to source_episodes_json
        - EVOLVE: Mark as non-canonical, link to new parent pattern
    ARCHIVE: Soft-delete pattern with reason

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, List, Optional

from k0.modules.consolidation.truth_writer.result import LayerWriteResult
from k0.pipelines.p03.phases.r7_truth_writer import OptimisticLockError
from k0.pipelines.p03.staged_writes import LAYER_ST_SEM, StagedWrite, WriteOperation

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


class PatternAction(str, Enum):
    """
    Actions for semantic pattern updates.

    REINFORCE: Boost confidence, increment observation count
    EXTEND: Append new episodes to source list
    EVOLVE: Mark non-canonical, link to parent pattern
    """

    REINFORCE = "REINFORCE"
    EXTEND = "EXTEND"
    EVOLVE = "EVOLVE"


@dataclass
class PatternWriteData:
    """
    Data structure for semantic layer writes.

    Represents a semantic pattern record.

    Attributes:
        pattern_id: Unique pattern identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        pattern_type: Type of pattern (e.g., "temporal", "causal")
        canonical_name: Human-readable pattern name
        source_episodes_json: JSON array of source episode IDs
        initial_confidence: Confidence at creation [0.0, 1.0]
        current_confidence: Current confidence [0.0, 1.0]
        observation_count: Number of reinforcing observations
        last_observed_at_ms: Last observation time (MILLISECONDS)
        is_canonical: True if this is the canonical version
        parent_pattern_id: Parent pattern if evolved
    """

    pattern_id: str
    tenant_id: str
    space_id: str
    pattern_type: str = "general"
    canonical_name: str = ""
    source_episodes_json: str = "[]"
    initial_confidence: float = 1.0
    current_confidence: float = 1.0
    observation_count: int = 1
    last_observed_at_ms: int = 0
    is_canonical: bool = True
    parent_pattern_id: Optional[str] = None


class SemanticLayerWriter:
    """
    Writer for st_sem (semantic memory) layer.

    Handles INSERT, UPDATE (with actions), and ARCHIVE operations
    for semantic pattern records.

    Table: st_sem
    Primary Key: pattern_id
    Version Column: version (for optimistic locking)

    Action-Based Updates:
        REINFORCE: Increment confidence and observation_count
        EXTEND: Append episodes to source_episodes_json
        EVOLVE: Mark non-canonical and link to parent

    Usage:
        writer = SemanticLayerWriter()
        result = await writer.write(staged_writes, uow)
    """

    LAYER = LAYER_ST_SEM

    # Confidence boost per reinforcement (additive, capped at 1.0)
    REINFORCE_BOOST = 0.05

    @property
    def layer(self) -> str:
        """Target layer name."""
        return self.LAYER

    async def write(
        self,
        writes: List[StagedWrite],
        uow: UnitOfWork,
    ) -> LayerWriteResult:
        """
        Execute semantic layer writes.

        Processes all writes for this layer, tracking successes and failures.
        Continues processing on failure to maximize partial success.

        Args:
            writes: List of StagedWrite objects for this layer
            uow: UnitOfWork providing database connection

        Returns:
            LayerWriteResult with success/failure counts
        """
        succeeded = 0
        failed_ids: List[str] = []
        error_messages: List[str] = []

        for write in writes:
            if write.layer != self.LAYER:
                continue

            try:
                if write.operation == WriteOperation.INSERT:
                    await self._insert(uow, write)
                elif write.operation == WriteOperation.UPDATE:
                    await self._update(uow, write)
                elif write.operation == WriteOperation.ARCHIVE:
                    await self._archive(uow, write)
                elif write.operation == WriteOperation.TOMBSTONE:
                    await self._tombstone(uow, write)
                succeeded += 1
            except OptimisticLockError as e:
                failed_ids.append(write.record_id)
                error_messages.append(str(e))
            except Exception as e:
                failed_ids.append(write.record_id)
                error_messages.append(f"{write.record_id}: {e}")

        error_msg = "; ".join(error_messages) if error_messages else None

        return LayerWriteResult(
            layer=self.LAYER,
            writes_attempted=len([w for w in writes if w.layer == self.LAYER]),
            writes_succeeded=succeeded,
            writes_failed=len(failed_ids),
            failed_ids=failed_ids,
            error_message=error_msg,
        )

    async def _insert(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        INSERT new pattern with ON CONFLICT DO NOTHING.

        Creates a new semantic pattern record. If the pattern_id already
        exists, the insert is silently ignored (idempotent).

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with record data
        """
        data = write.record_data
        now = _now_ms()

        await uow.connection.execute(
            """
            INSERT INTO st_sem (
                pattern_id, tenant_id, space_id, pattern_type,
                canonical_name, source_episodes_json,
                initial_confidence, current_confidence,
                observation_count, last_observed_at,
                is_canonical, parent_pattern_id,
                created_at, version
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, 1)
            ON CONFLICT (pattern_id) DO NOTHING
            """,
            data["pattern_id"],
            data["tenant_id"],
            data["space_id"],
            data.get("pattern_type", "general"),
            data.get("canonical_name", ""),
            data.get("source_episodes_json", "[]"),
            data.get("initial_confidence", 1.0),
            data.get("current_confidence", 1.0),
            data.get("observation_count", 1),
            data.get("last_observed_at", now),
            data.get("is_canonical", True),
            data.get("parent_pattern_id"),
            data.get("created_at", now),
        )

    async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        UPDATE pattern based on action or generic data.

        Dispatches to action-specific handlers if _action is present.
        Otherwise performs a generic field update with optimistic locking.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with record data and optional _action

        Raises:
            OptimisticLockError: If version doesn't match
        """
        data = write.record_data
        action = data.get("_action")

        if action == PatternAction.REINFORCE or action == "REINFORCE":
            await self._reinforce(uow, write)
        elif action == PatternAction.EXTEND or action == "EXTEND":
            await self._extend(uow, write)
        elif action == PatternAction.EVOLVE or action == "EVOLVE":
            await self._evolve(uow, write)
        else:
            # Generic update
            await self._generic_update(uow, write)

    async def _reinforce(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        REINFORCE action: Boost confidence and increment observation count.

        Adds REINFORCE_BOOST to current_confidence (capped at 1.0).
        Increments observation_count by 1.
        Updates last_observed_at to now.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with pattern_id
        """
        now = _now_ms()
        boost = write.record_data.get("confidence_boost", self.REINFORCE_BOOST)

        result = await uow.connection.execute(
            """
            UPDATE st_sem
            SET current_confidence = LEAST(current_confidence + $1, 1.0),
                observation_count = observation_count + 1,
                last_observed_at = $2,
                version = version + 1
            WHERE pattern_id = $3
              AND ($4::int IS NULL OR version = $4)
            """,
            boost,
            now,
            write.record_id,
            write.expected_version,
        )

        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_sem:{write.record_id}")

    async def _extend(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        EXTEND action: Append episodes to source_episodes_json.

        Merges new_episodes into the existing source_episodes_json array.
        Maintains uniqueness by converting to set.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with new_episodes list
        """
        new_episodes = write.record_data.get("new_episodes", [])
        if not new_episodes:
            return

        now = _now_ms()

        # Use PostgreSQL jsonb for atomic merge
        result = await uow.connection.execute(
            """
            UPDATE st_sem
            SET source_episodes_json = (
                SELECT jsonb_agg(DISTINCT value)::text
                FROM (
                    SELECT value FROM jsonb_array_elements_text(
                        source_episodes_json::jsonb
                    )
                    UNION
                    SELECT value FROM jsonb_array_elements_text($1::jsonb)
                ) sub
            ),
            last_observed_at = $2,
            version = version + 1
            WHERE pattern_id = $3
              AND ($4::int IS NULL OR version = $4)
            """,
            json.dumps(new_episodes),
            now,
            write.record_id,
            write.expected_version,
        )

        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_sem:{write.record_id}")

    async def _evolve(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        EVOLVE action: Mark pattern as non-canonical, link to parent.

        Sets is_canonical = false and establishes parent_pattern_id.
        Used when a pattern is superseded by a refined version.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with parent_pattern_id
        """
        parent_id = write.record_data.get("parent_pattern_id")
        now = _now_ms()

        result = await uow.connection.execute(
            """
            UPDATE st_sem
            SET is_canonical = FALSE,
                parent_pattern_id = $1,
                last_observed_at = $2,
                version = version + 1
            WHERE pattern_id = $3
              AND ($4::int IS NULL OR version = $4)
            """,
            parent_id,
            now,
            write.record_id,
            write.expected_version,
        )

        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_sem:{write.record_id}")

    async def _generic_update(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        Generic UPDATE for non-action fields.

        Builds a dynamic SET clause from data keys.
        Uses optimistic locking via version check.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with record data

        Raises:
            OptimisticLockError: If version doesn't match
        """
        data = write.record_data

        # Build dynamic SET clause from data keys
        set_parts: List[str] = []
        values: List[Any] = []
        idx = 1

        # Exclude internal keys and primary key
        exclude_keys = {"pattern_id", "_action", "_version", "new_episodes"}

        for key, value in data.items():
            if key not in exclude_keys:
                set_parts.append(f"{key} = ${idx}")
                values.append(value)
                idx += 1

        if not set_parts:
            return  # Nothing to update

        # Add version increment and WHERE clause values
        values.append(write.record_id)  # WHERE pattern_id = $N
        values.append(write.expected_version or 0)  # AND version = $N+1

        sql = f"""
            UPDATE st_sem
            SET {", ".join(set_parts)}, version = version + 1
            WHERE pattern_id = ${idx}
              AND version = ${idx + 1}
        """

        result = await uow.connection.execute(sql, *values)

        # Check for version conflict
        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_sem:{write.record_id}")

    async def _archive(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        ARCHIVE pattern (soft-delete).

        Marks the pattern as archived with a timestamp and reason.
        Does not physically delete the record.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with archive reason
        """
        now = _now_ms()

        await uow.connection.execute(
            """
            UPDATE st_sem
            SET archival_status = 'ARCHIVED',
                archived_at = $1,
                archived_reason = $2,
                version = version + 1
            WHERE pattern_id = $3
              AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
            """,
            now,
            write.record_data.get("archived_reason", ""),
            write.record_id,
        )

    async def _tombstone(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        TOMBSTONE pattern (hard-delete marker).

        Marks the record for sync propagation as deleted.
        Used for replication and eventual consistency.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with tombstone data
        """
        now = _now_ms()

        await uow.connection.execute(
            """
            UPDATE st_sem
            SET archival_status = 'TOMBSTONE',
                archived_at = $1,
                archived_reason = 'tombstone',
                version = version + 1
            WHERE pattern_id = $2
            """,
            now,
            write.record_id,
        )


def _parse_rows_affected(result: str | None) -> int:
    """
    Parse rows affected from asyncpg execute result.

    Args:
        result: Result string like "UPDATE 1" or "INSERT 0 1"

    Returns:
        Number of rows affected
    """
    if not result:
        return 0
    try:
        parts = result.split()
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0


def create_semantic_writer() -> SemanticLayerWriter:
    """Factory function to create a SemanticLayerWriter."""
    return SemanticLayerWriter()
