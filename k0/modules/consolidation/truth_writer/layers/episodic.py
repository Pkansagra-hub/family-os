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

import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Optional

from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.modules.consolidation.truth_writer.observation_recorder import (
    ObservationRecorder,
    get_observation_recorder,
)
from k0.modules.consolidation.truth_writer.result import LayerWriteResult
from k0.modules.consolidation.truth_writer.text_vector_coordinator import (
    TextVectorCoordinator,
    get_coordinator,
)
from k0.pipelines.p03.phases.r7_truth_writer import OptimisticLockError
from k0.pipelines.p03.staged_writes import LAYER_ST_EPI, StagedWrite, WriteOperation

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


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

    # GAP-001: Inline vector and text preservation fields
    source_texts_json: Optional[str] = None  # JSON array of source event texts
    embedding_text: Optional[str] = None  # Generated text for UltraBERT embedding
    embedding_vector: Optional[bytes] = None  # 768-dim float32 as BYTEA (3072 bytes)
    embedding_model: Optional[str] = None  # Model version (e.g., "ultrabert-v2.1.0")


class EpisodicLayerWriter:
    """
    Writer for st_epi (episodic memory) layer.

    Handles INSERT, UPDATE, and ARCHIVE operations for episode records.
    Episodes link source events to clusters with temporal bounds.

    Table: st_epi
    Primary Key: episode_id
    Version Column: version (for optimistic locking)

    GAP-001: Now includes source_texts_json, embedding_text, embedding_vector, embedding_model

    Usage:
        writer = EpisodicLayerWriter()
        result = await writer.write(staged_writes, uow)
    """

    LAYER = LAYER_ST_EPI

    def __init__(
        self,
        coordinator: Optional[TextVectorCoordinator] = None,
        observation_recorder: Optional[ObservationRecorder] = None,
    ):
        """
        Initialize with optional dependencies.

        Args:
            coordinator: TextVectorCoordinator instance (uses singleton if None)
            observation_recorder: ObservationRecorder for holistic context (uses singleton if None)
        """
        self._coordinator = coordinator
        self._observation_recorder = observation_recorder

    def _get_coordinator(self) -> TextVectorCoordinator:
        """Get coordinator, using singleton if not injected."""
        if self._coordinator is None:
            self._coordinator = get_coordinator()
        return self._coordinator

    def _get_recorder(self) -> ObservationRecorder:
        """Get observation recorder, using singleton if not injected."""
        if self._observation_recorder is None:
            self._observation_recorder = get_observation_recorder()
        return self._observation_recorder

    def _extract_context(self, write: StagedWrite) -> Optional[ObservationContext]:
        """
        Extract observation context from StagedWrite.

        Returns the attached observation_context if present, otherwise
        builds a minimal context from record_data.

        Args:
            write: StagedWrite with optional observation_context

        Returns:
            ObservationContext if extractable, None otherwise
        """
        # Prefer attached context (from Issue 7.6 pipeline flow)
        if write.observation_context is not None:
            return write.observation_context

        # Fallback: build minimal context from record_data
        data = write.record_data
        observed_at = data.get("created_at") or data.get("start_time_utc") or _now_ms()

        return ObservationContext(
            observed_at=observed_at,
            source_event_id=write.source_event_ids[0] if write.source_event_ids else None,
        )

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

        GAP-001: Now includes text + vector generation before insert.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with record data
        """
        data = write.record_data
        now = _now_ms()

        # GAP-001: Get source event IDs and generate text + vector
        source_events_json_str = data.get("source_events_json", "[]")
        try:
            source_event_ids = json.loads(source_events_json_str)
            if not isinstance(source_event_ids, list):
                source_event_ids = []
        except (json.JSONDecodeError, TypeError):
            source_event_ids = []

        # Generate text and embedding via coordinator
        coordinator = self._get_coordinator()
        tv_result = await coordinator.process(
            layer=self.LAYER,
            record_data=data,
            source_event_ids=source_event_ids,
            conn=uow.connection,
        )

        await uow.connection.execute(
            """
            INSERT INTO st_epi (
                episode_id, tenant_id, space_id, cluster_id,
                source_events_json, source_event_count, start_time_utc, end_time_utc,
                duration_minutes, temporal_bucket, day_of_week, is_recurring, recurrence_pattern,
                confidence_score, observation_count,
                created_at, updated_at, valid_from, version,
                archival_status,
                source_texts_json, embedding_text, embedding_vector, embedding_model,
                episode_summary, episode_type, primary_location, location_type,
                participants_json, participant_count, embedding_id,
                cluster_confidence, consolidation_cycle_id, last_observed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                      $16, $16, $16, 1,
                      'ACTIVE', $17, $18, $19, $20,
                      $21, $22, $23, $24, $25, $26, $27,
                      $28, $29, $30)
            ON CONFLICT (episode_id) DO NOTHING
            """,
            data["episode_id"],
            data["tenant_id"],
            data["space_id"],
            data.get("cluster_id"),
            source_events_json_str,
            len(source_event_ids),
            data.get("start_time_utc") or data.get("started_at", now),
            data.get("end_time_utc") or data.get("ended_at", now),
            data.get("duration_minutes"),
            data.get("temporal_bucket"),
            data.get("day_of_week"),
            data.get("is_recurring"),
            data.get("recurrence_pattern"),
            data.get("confidence_score") or data.get("confidence", 1.0),
            data.get("observation_count", 1),
            data.get("created_at", now),
            # Text + embedding columns:
            tv_result.source_texts_json,
            tv_result.embedding_text,
            tv_result.embedding_vector,
            tv_result.embedding_model,
            # GAP-001 fix: Previously missing episodic metadata columns
            data.get("episode_summary"),
            data.get("episode_type"),
            data.get("primary_location"),
            data.get("location_type"),  # GAP-002: location category
            data.get("participants_json", "[]"),
            data.get("participant_count", 0),
            data.get("embedding_id"),
            data.get("cluster_confidence"),
            data.get("consolidation_cycle_id"),
            data.get("last_observed_at"),
        )

        # Issue 7.5: Record observation with FIRST_SEEN type
        context = self._extract_context(write)
        if context is not None:
            context.observation_type = "FIRST_SEEN"
            try:
                await self._get_recorder().record(
                    uow=uow,
                    layer=self.LAYER,
                    record_id=write.record_id,
                    context=context,
                    tenant_id=data["tenant_id"],
                )
            except Exception as e:
                # Non-fatal: log but don't fail the write
                logger.warning(
                    "Failed to record observation for %s: %s",
                    write.record_id,
                    e,
                )

    async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        UPDATE episode with optimistic locking.

        Updates episode fields using the provided data. Version check
        ensures no concurrent modifications occurred.

        Issue 2 Fix: Special handling for REINFORCE updates that:
        - Append new event IDs to source_events_json
        - Increment source_event_count and observation_count
        - Extend temporal bounds (MIN start, MAX end)

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with record data and expected_version

        Raises:
            OptimisticLockError: If version doesn't match
        """
        data = write.record_data

        # Check if this is a REINFORCE update (Issue 2 fix)
        if "additional_event_ids" in data:
            await self._update_reinforce(uow, write)
            return

        # === Original generic update logic ===
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

    async def _update_reinforce(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        REINFORCE an existing episode by adding new events.

        Issue 2 Fix: When events match an existing episode, we reinforce it:
        - Append new event IDs to source_events_json
        - Increment source_event_count by number of new events
        - Increment observation_count
        - Extend temporal bounds (use MIN for start, MAX for end)
        - Update last_accessed timestamp

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with reinforce data

        Raises:
            OptimisticLockError: If version doesn't match
        """
        data = write.record_data
        now = _now_ms()

        additional_event_ids = data.get("additional_event_ids", [])
        additional_count = data.get("additional_event_count", len(additional_event_ids))
        new_start = data.get("new_start_time_utc", 0)
        new_end = data.get("new_end_time_utc", 0)
        is_recurring = data.get("is_recurring")
        recurrence_pattern = data.get("recurrence_pattern")
        consolidation_cycle_id = data.get("consolidation_cycle_id")

        # Convert event IDs to JSON array for PostgreSQL
        additional_json = json.dumps(additional_event_ids)

        # Use PostgreSQL array concatenation to append event IDs
        # and MIN/MAX for temporal bounds
        sql = """
            UPDATE st_epi
            SET source_events_json = (
                    SELECT jsonb_agg(DISTINCT elem)
                    FROM (
                        SELECT jsonb_array_elements(source_events_json::jsonb) AS elem
                        UNION ALL
                        SELECT jsonb_array_elements($1::jsonb) AS elem
                    ) AS combined
                )::text,
                source_event_count = source_event_count + $2,
                observation_count = observation_count + 1,
                start_time_utc = LEAST(start_time_utc, $3),
                end_time_utc = GREATEST(end_time_utc, $4),
                duration_minutes = CASE
                    WHEN $3 > 0 AND $4 > 0
                        THEN (GREATEST(end_time_utc, $4) - LEAST(start_time_utc, $3)) / 60000
                    ELSE duration_minutes
                END,
                last_observed_at = CASE
                    WHEN $4 > 0
                        THEN GREATEST(COALESCE(last_observed_at, 0), $4)
                    ELSE last_observed_at
                END,
                is_recurring = COALESCE($8, is_recurring),
                recurrence_pattern = COALESCE($9, recurrence_pattern),
                consolidation_cycle_id = COALESCE($10, consolidation_cycle_id),
                updated_at = $5,
                version = version + 1
            WHERE episode_id = $6
              AND version = $7
        """

        result = await uow.connection.execute(
            sql,
            additional_json,
            additional_count,
            new_start,
            new_end,
            now,
            write.record_id,
            write.expected_version or 0,
            is_recurring,
            recurrence_pattern,
            consolidation_cycle_id,
        )

        # Check for version conflict
        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_epi:{write.record_id}")

        # Issue 7.5: Record observation with REINFORCEMENT type
        context = self._extract_context(write)
        if context is not None:
            context.observation_type = "REINFORCEMENT"
            try:
                await self._get_recorder().record(
                    uow=uow,
                    layer=self.LAYER,
                    record_id=write.record_id,
                    context=context,
                    tenant_id=data.get("tenant_id", "unknown"),
                )
            except Exception as e:
                # Non-fatal: log but don't fail the write
                logger.warning(
                    "Failed to record reinforcement observation for %s: %s",
                    write.record_id,
                    e,
                )

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
                                updated_at = $1,
                                valid_to = $1,
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
                updated_at = $1,
                valid_to = $1,
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
