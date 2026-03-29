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
import logging
import time
from dataclasses import dataclass
from enum import Enum
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
from k0.pipelines.p03.staged_writes import LAYER_ST_SEM, StagedWrite, WriteOperation

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


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

    # GAP-001: Inline vector and text preservation fields
    source_texts_json: Optional[str] = None  # JSON array of source event texts
    embedding_text: Optional[str] = None  # Generated text for UltraBERT embedding
    embedding_vector: Optional[bytes] = None  # 768-dim float32 as BYTEA (3072 bytes)
    embedding_model: Optional[str] = None  # Model version (e.g., "ultrabert-v2.1.0")


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

    GAP-001: Now includes source_texts_json, embedding_text, embedding_vector, embedding_model

    Usage:
        writer = SemanticLayerWriter()
        result = await writer.write(staged_writes, uow)
    """

    LAYER = LAYER_ST_SEM

    # Confidence boost per reinforcement (additive, capped at 1.0)
    REINFORCE_BOOST = 0.05

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
        """
        if write.observation_context is not None:
            return write.observation_context

        data = write.record_data
        observed_at = data.get("created_at") or data.get("last_observed_at") or _now_ms()

        return ObservationContext(
            observed_at=observed_at,
            source_event_id=write.source_event_ids[0] if write.source_event_ids else None,
        )

    def _looks_like_event_ids(self, ids: List[str]) -> bool:
        """
        Detect if IDs are event UUIDs vs episode IDs.

        Event IDs are UUIDs (e.g., 'c0326faa-4a8c-4050-9f86-4d1bd5677fd9').
        Episode IDs are prefixed (e.g., 'weak-e8e719820b3043fa9427d2892c').

        IntentSignalAssembler stores event_ids in source_episodes_json.
        TruthWriteAssembler stores episode_ids.

        Args:
            ids: List of IDs to check

        Returns:
            True if IDs look like event UUIDs, False otherwise
        """
        if not ids:
            return False

        import re

        # UUID pattern: 8-4-4-4-12 hex digits
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )

        # Check first ID (all should be same type)
        first_id = ids[0]
        return bool(uuid_pattern.match(first_id))

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

        GAP-001: Now includes text + vector generation before insert.
        Uses source_episodes_json to resolve episode → event texts.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with record data
        """
        data = write.record_data
        now = _now_ms()

        # GAP-001: Get source episode IDs and resolve to event texts
        source_episodes_json_str = data.get("source_episodes_json", "[]")
        try:
            source_ids = json.loads(source_episodes_json_str)
            if not isinstance(source_ids, list):
                source_ids = []
        except (json.JSONDecodeError, TypeError):
            source_ids = []

        # Generate text and embedding via coordinator
        # Detect if we have event IDs (UUIDs) or episode IDs (prefixed like weak-xxx)
        # IntentSignalAssembler stores event_ids directly; TruthWriteAssembler uses episode_ids
        coordinator = self._get_coordinator()

        if source_ids and self._looks_like_event_ids(source_ids):
            # Direct event IDs (from IntentSignalAssembler: LESSON, EMOTIONAL_TREND)
            tv_result = await coordinator.process(
                layer=self.LAYER,
                record_data=data,
                source_event_ids=source_ids,
                conn=uow.connection,
            )
        else:
            # Episode IDs (from TruthWriteAssembler: THEME, ROUTINE, etc.)
            tv_result = await coordinator.process_for_episodes(
                layer=self.LAYER,
                record_data=data,
                source_episode_ids=source_ids,
                conn=uow.connection,
            )

        # Calculate source_episode_count
        source_episode_count = len(source_ids) if source_ids else 1

        await uow.connection.execute(
            """
            INSERT INTO st_sem (
                pattern_id, tenant_id, space_id, actor_id, pattern_type, pattern_subtype,
                pattern_name, pattern_description, pattern_attributes_json,
                temporal_regularity, temporal_pattern_json,
                source_episodes_json, source_episode_count,
                embedding_id, confidence_score,
                observation_count, last_observed_at, first_observed_at,
                is_canonical, supersedes_id,
                created_at, updated_at, valid_from, version,
                archival_status,
                source_texts_json, embedding_text, embedding_vector, embedding_model
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26,
                      $27, $28, $29)
            ON CONFLICT (pattern_id) DO NOTHING
            """,
            data["pattern_id"],
            data["tenant_id"],
            data["space_id"],
            data.get("actor_id"),
            data.get("pattern_type", "general"),
            data.get("pattern_subtype"),  # GAP-005: Fine-grained subtype
            data.get("pattern_name") or data.get("canonical_name", ""),
            data.get("pattern_description"),
            data.get("pattern_attributes_json"),
            data.get("temporal_regularity"),
            data.get("temporal_pattern_json"),
            source_episodes_json_str,
            source_episode_count,
            data.get("embedding_id"),
            data.get("confidence_score") or data.get("current_confidence", 1.0),
            data.get("observation_count", 1),
            data.get("last_observed_at", now),
            data.get("first_observed_at", now),
            data.get("is_canonical", True),
            data.get("supersedes_id") or data.get("parent_pattern_id"),
            data.get("created_at", now),
            data.get("updated_at", now),
            data.get("valid_from", now),
            data.get("version", 1),
            data.get("archival_status", "ACTIVE"),
            # GAP-001 new columns:
            tv_result.source_texts_json,
            tv_result.embedding_text,
            tv_result.embedding_vector,
            tv_result.embedding_model,
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
                logger.warning(
                    "Failed to record observation for %s: %s",
                    write.record_id,
                    e,
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
                    tenant_id=write.record_data.get("tenant_id", "unknown"),
                )
            except Exception as e:
                logger.warning(
                    "Failed to record reinforcement observation for %s: %s",
                    write.record_id,
                    e,
                )

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
        now = _now_ms()

        result = await uow.connection.execute(
            """
            UPDATE st_sem
            SET is_canonical = FALSE,
                                last_observed_at = $1,
                                updated_at = $1,
                                valid_to = COALESCE($2, valid_to),
                version = version + 1
            WHERE pattern_id = $3
              AND ($4::int IS NULL OR version = $4)
            """,
            now,
            write.record_data.get("valid_to", now),
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
                                updated_at = $1,
                                valid_to = $1,
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
                updated_at = $1,
                valid_to = $1,
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
