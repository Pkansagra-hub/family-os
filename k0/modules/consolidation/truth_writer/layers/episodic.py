"""
EpisodicLayerWriter — Issue 5.2.3

Writer for st_epi (episodic memory) layer.
Handles episode clustering results with source event linking.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.3 — st_epi layer writer)
    - Dossier §4.8.2 (st_epi Writes)

Operations:
    INSERT: Create new episode with cluster and source events
    UPDATE: Modify episode metadata with optimistic locking
    ARCHIVE: Soft-delete episode with reason

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Optional

from k0.modules.consolidation.truth_writer.result import LayerWriteResult
from k0.pipelines.p03.phases.r7_truth_writer import OptimisticLockError
from k0.pipelines.p03.staged_writes import LAYER_ST_EPI, StagedWrite, WriteOperation

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


@dataclass
class EpisodeWriteData:
    """
    Data structure for episodic layer writes.

    Represents an episode record with temporal bounds and source events.

    Attributes:
        episode_id: Unique episode identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        cluster_id: Optional cluster identifier from R2
        source_events_json: JSON array of source event IDs
        started_at_ms: Episode start time (MILLISECONDS)
        ended_at_ms: Episode end time (MILLISECONDS)
        temporal_spread_ms: Duration in MILLISECONDS
        confidence: Episode confidence score [0.0, 1.0]
        observation_count: Number of observations
    """

    episode_id: str
    tenant_id: str
    space_id: str
    cluster_id: Optional[str] = None
    source_events_json: str = "[]"
    started_at_ms: int = 0
    ended_at_ms: int = 0
    temporal_spread_ms: int = 0
    confidence: float = 1.0
    observation_count: int = 1


class EpisodicLayerWriter:
    """
    Writer for st_epi (episodic memory) layer.

    Handles INSERT, UPDATE, and ARCHIVE operations for episode records.
    Episodes link source events to clusters with temporal bounds.

    Table: st_epi
    Primary Key: episode_id
    Version Column: version (for optimistic locking)

    Usage:
        writer = EpisodicLayerWriter()
        result = await writer.write(staged_writes, uow)
    """

    LAYER = LAYER_ST_EPI

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
        Execute episodic layer writes.

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
        INSERT new episode with ON CONFLICT DO NOTHING.

        Creates a new episode record. If the episode_id already exists,
        the insert is silently ignored (idempotent).

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with record data
        """
        data = write.record_data
        now = _now_ms()

        await uow.connection.execute(
            """
            INSERT INTO st_epi (
                episode_id, tenant_id, space_id, cluster_id,
                source_events_json, started_at, ended_at,
                temporal_spread_ms, confidence, observation_count,
                created_at, version
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 1)
            ON CONFLICT (episode_id) DO NOTHING
            """,
            data["episode_id"],
            data["tenant_id"],
            data["space_id"],
            data.get("cluster_id"),
            data.get("source_events_json", "[]"),
            data.get("started_at", now),
            data.get("ended_at", now),
            data.get("temporal_spread_ms", 0),
            data.get("confidence", 1.0),
            data.get("observation_count", 1),
            data.get("created_at", now),
        )

    async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        UPDATE episode with optimistic locking.

        Updates episode fields using the provided data. Version check
        ensures no concurrent modifications occurred.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with record data and expected_version

        Raises:
            OptimisticLockError: If version doesn't match
        """
        data = write.record_data

        # Build dynamic SET clause from data keys
        set_parts: List[str] = []
        values: List[Any] = []
        idx = 1

        # Exclude internal keys and primary key
        exclude_keys = {"episode_id", "_action", "_version"}

        for key, value in data.items():
            if key not in exclude_keys:
                set_parts.append(f"{key} = ${idx}")
                values.append(value)
                idx += 1

        if not set_parts:
            return  # Nothing to update

        # Add version increment and WHERE clause values
        values.append(write.record_id)  # WHERE episode_id = $N
        values.append(write.expected_version or 0)  # AND version = $N+1

        sql = f"""
            UPDATE st_epi
            SET {", ".join(set_parts)}, version = version + 1
            WHERE episode_id = ${idx}
              AND version = ${idx + 1}
        """

        result = await uow.connection.execute(sql, *values)

        # Check for version conflict
        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_epi:{write.record_id}")

    async def _archive(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        ARCHIVE episode (soft-delete).

        Marks the episode as archived with a timestamp and reason.
        Does not physically delete the record.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with archive reason
        """
        now = _now_ms()

        await uow.connection.execute(
            """
            UPDATE st_epi
            SET archival_status = 'ARCHIVED',
                archived_at = $1,
                archived_reason = $2,
                version = version + 1
            WHERE episode_id = $3
              AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
            """,
            now,
            write.record_data.get("archived_reason", ""),
            write.record_id,
        )

    async def _tombstone(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        TOMBSTONE episode (hard-delete marker).

        Marks the record for sync propagation as deleted.
        Used for replication and eventual consistency.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with tombstone data
        """
        now = _now_ms()

        await uow.connection.execute(
            """
            UPDATE st_epi
            SET archival_status = 'TOMBSTONE',
                archived_at = $1,
                archived_reason = 'tombstone',
                version = version + 1
            WHERE episode_id = $2
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


def create_episodic_writer() -> EpisodicLayerWriter:
    """Factory function to create an EpisodicLayerWriter."""
    return EpisodicLayerWriter()
