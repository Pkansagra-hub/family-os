"""
ProceduralLayerWriter — Issue 5.2.5

Writer for st_procedural (habits/routines) layer.
Handles routine patterns and temporal regularity.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.5 — st_procedural layer writer)
    - Dossier §4.8.4 (st_procedural Writes)

Operations:
    INSERT: Create new routine pattern
    UPDATE with Actions:
        - REINFORCE: Boost confidence, update regularity
        - EXTEND: Append action sequences
    ARCHIVE: Soft-delete decayed routine

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, List, Optional

from k0.modules.consolidation.truth_writer.result import LayerWriteResult
from k0.modules.consolidation.truth_writer.text_vector_coordinator import (
    TextVectorCoordinator,
    get_coordinator,
)
from k0.pipelines.p03.phases.r7_truth_writer import OptimisticLockError
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_PROCEDURAL,
    StagedWrite,
    WriteOperation,
)

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


class RoutineAction(str, Enum):
    """
    Actions for procedural routine updates.

    REINFORCE: Boost confidence, update regularity score
    EXTEND: Append new action sequences to routine
    """

    REINFORCE = "REINFORCE"
    EXTEND = "EXTEND"


@dataclass
class RoutineWriteData:
    """
    Data structure for procedural layer writes.

    Represents a routine/habit pattern record.

    Attributes:
        routine_id: Unique routine identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        routine_name: Human-readable routine name
        action_sequence_json: JSON array of action steps
        trigger_conditions_json: JSON object with triggers
        expected_outcomes_json: JSON array of expected outcomes
        temporal_regularity: Regularity score [0.0, 1.0]
        daily_pattern: Cron-like daily pattern (optional)
        weekly_pattern: Cron-like weekly pattern (optional)
        confidence: Routine confidence [0.0, 1.0]
        value_function: V(s) for TDL-HCO integration (optional)
    """

    routine_id: str
    tenant_id: str
    space_id: str
    routine_name: str = ""
    action_sequence_json: str = "[]"
    trigger_conditions_json: str = "{}"
    expected_outcomes_json: str = "[]"
    temporal_regularity: float = 0.0
    daily_pattern: Optional[str] = None
    weekly_pattern: Optional[str] = None
    confidence: float = 1.0
    value_function: Optional[float] = None

    # GAP-001: Inline vector and text preservation fields
    source_texts_json: Optional[str] = None  # JSON array of source event texts
    embedding_text: Optional[str] = None  # Generated text for UltraBERT embedding
    embedding_vector: Optional[bytes] = None  # 768-dim float32 as BYTEA (3072 bytes)
    embedding_model: Optional[str] = None  # Model version (e.g., "ultrabert-v2.1.0")


class ProceduralLayerWriter:
    """
    Writer for st_procedural (habits/routines) layer.

    Handles INSERT, UPDATE (with actions), and ARCHIVE operations
    for routine pattern records.

    Table: st_procedural
    Primary Key: routine_id
    Version Column: version (for optimistic locking)

    Action-Based Updates:
        REINFORCE: Boost confidence, update temporal_regularity
        EXTEND: Append action sequences to action_sequence_json

    Usage:
        writer = ProceduralLayerWriter()
        result = await writer.write(staged_writes, uow)
    """

    LAYER = LAYER_ST_PROCEDURAL

    # Confidence boost factor for reinforcement (multiplicative)
    REINFORCE_FACTOR = 1.1

    def __init__(self, coordinator: Optional[TextVectorCoordinator] = None) -> None:
        """
        Initialize ProceduralLayerWriter.

        Args:
            coordinator: Optional TextVectorCoordinator for GAP-001 embedding generation.
                        If not provided, uses singleton via get_coordinator().
        """
        self._coordinator = coordinator

    def _get_coordinator(self) -> TextVectorCoordinator:
        """Get coordinator, initializing singleton if needed."""
        if self._coordinator is None:
            self._coordinator = get_coordinator()
        return self._coordinator

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
        Execute procedural layer writes.

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
        INSERT new routine pattern with ON CONFLICT DO NOTHING.

        Creates a new routine record. If the routine_id already exists,
        the insert is silently ignored (idempotent).

        GAP-001: Generates embedding from routine_name (no source texts to fetch).

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with record data
        """
        data = write.record_data
        now = _now_ms()

        # GAP-001: Generate embedding from routine_name
        # Procedural layer doesn't have source_events - use process_without_fetch
        source_texts_json: Optional[str] = None
        embedding_text: Optional[str] = None
        embedding_vector: Optional[bytes] = None
        embedding_model: Optional[str] = None

        try:
            routine_name = data.get("routine_name", "")
            if routine_name:
                coordinator = self._get_coordinator()
                tv_result = await coordinator.process_without_fetch(
                    layer=self.LAYER,
                    record_data=data,
                    source_texts=[routine_name],
                )
                source_texts_json = tv_result.source_texts_json
                embedding_text = tv_result.embedding_text
                embedding_vector = tv_result.embedding_vector
                embedding_model = tv_result.embedding_model
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Procedural embedding failed: {e}")
            # Non-fatal: continue with INSERT

        await uow.connection.execute(
            """
            INSERT INTO st_procedural (
                routine_id, tenant_id, space_id, actor_id, routine_name,
                action_sequence_json,
                regularity_score,
                day_pattern, frequency, confidence_score,
                source_episodes_json, source_episode_count,
                created_at, updated_at, valid_from, version,
                -- GAP-001: Inline vector and text preservation columns
                source_texts_json, embedding_text, embedding_vector, embedding_model
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $13, $13, 1,
                      $14, $15, $16, $17)
            ON CONFLICT (routine_id) DO NOTHING
            """,
            data["routine_id"],
            data["tenant_id"],
            data["space_id"],
            data.get("actor_id", data["tenant_id"]),  # Default to tenant if no actor
            data.get("routine_name", ""),
            data.get("action_sequence_json", "[]"),
            data.get("regularity_score", data.get("temporal_regularity", 0.0)),
            data.get("day_pattern", data.get("daily_pattern")),
            data.get("frequency", data.get("weekly_pattern")),
            data.get("confidence_score", data.get("confidence", 1.0)),
            data.get("source_episodes_json", "[]"),
            data.get("source_episode_count", 1),
            data.get("created_at", now),
            # GAP-001 fields
            source_texts_json,
            embedding_text,
            embedding_vector,
            embedding_model,
        )

    async def _update(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        UPDATE routine based on action or generic data.

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

        if action == RoutineAction.REINFORCE or action == "REINFORCE":
            await self._reinforce(uow, write)
        elif action == RoutineAction.EXTEND or action == "EXTEND":
            await self._extend(uow, write)
        else:
            # Generic update
            await self._generic_update(uow, write)

    async def _reinforce(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        REINFORCE action: Boost confidence and update regularity.

        Multiplies confidence by REINFORCE_FACTOR (capped at 1.0).
        Updates temporal_regularity via moving average.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with optional new_regularity
        """
        now = _now_ms()
        new_regularity = write.record_data.get("new_regularity", 0.5)

        result = await uow.connection.execute(
            """
            UPDATE st_procedural
            SET confidence = LEAST(confidence * $1, 1.0),
                temporal_regularity = (temporal_regularity + $2) / 2,
                last_observed_at = $3,
                version = version + 1
            WHERE routine_id = $4
              AND ($5::int IS NULL OR version = $5)
            """,
            self.REINFORCE_FACTOR,
            new_regularity,
            now,
            write.record_id,
            write.expected_version,
        )

        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_procedural:{write.record_id}")

    async def _extend(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        EXTEND action: Append action sequences to routine.

        Concatenates new_actions_json to the existing action_sequence_json.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with new_actions_json
        """
        new_actions = write.record_data.get("new_actions_json", "[]")
        now = _now_ms()

        result = await uow.connection.execute(
            """
            UPDATE st_procedural
            SET action_sequence_json = (
                SELECT jsonb_agg(value)::text
                FROM (
                    SELECT value FROM jsonb_array_elements(action_sequence_json::jsonb)
                    UNION ALL
                    SELECT value FROM jsonb_array_elements($1::jsonb)
                ) sub
            ),
            last_observed_at = $2,
            version = version + 1
            WHERE routine_id = $3
              AND ($4::int IS NULL OR version = $4)
            """,
            new_actions,
            now,
            write.record_id,
            write.expected_version,
        )

        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_procedural:{write.record_id}")

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
        exclude_keys = {"routine_id", "_action", "_version", "new_actions_json", "new_regularity"}

        for key, value in data.items():
            if key not in exclude_keys:
                set_parts.append(f"{key} = ${idx}")
                values.append(value)
                idx += 1

        if not set_parts:
            return  # Nothing to update

        # Add version increment and WHERE clause values
        values.append(write.record_id)  # WHERE routine_id = $N
        values.append(write.expected_version or 0)  # AND version = $N+1

        sql = f"""
            UPDATE st_procedural
            SET {", ".join(set_parts)}, version = version + 1
            WHERE routine_id = ${idx}
              AND version = ${idx + 1}
        """

        result = await uow.connection.execute(sql, *values)

        # Check for version conflict
        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_procedural:{write.record_id}")

    async def _archive(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        ARCHIVE routine (soft-delete for decayed routines).

        Marks the routine as archived with a timestamp and reason.
        Default reason is "decay" for unused routines.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with archive reason
        """
        now = _now_ms()

        await uow.connection.execute(
            """
            UPDATE st_procedural
            SET archival_status = 'ARCHIVED',
                archived_at = $1,
                archived_reason = $2,
                version = version + 1
            WHERE routine_id = $3
              AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
            """,
            now,
            write.record_data.get("archived_reason", "decay"),
            write.record_id,
        )

    async def _tombstone(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        TOMBSTONE routine (hard-delete marker).

        Marks the record for sync propagation as deleted.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with tombstone data
        """
        now = _now_ms()

        await uow.connection.execute(
            """
            UPDATE st_procedural
            SET archival_status = 'TOMBSTONE',
                archived_at = $1,
                archived_reason = 'tombstone',
                version = version + 1
            WHERE routine_id = $2
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


def create_procedural_writer() -> ProceduralLayerWriter:
    """Factory function to create a ProceduralLayerWriter."""
    return ProceduralLayerWriter()
