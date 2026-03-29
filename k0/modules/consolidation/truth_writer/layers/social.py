"""
SocialLayerWriter — Issue 5.2.6

Writer for st_social (relationships) layer.
Handles relationship strength and interaction tracking.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.6 — st_social layer writer)
    - Dossier §4.8.5 (st_social Writes)

Operations:
    INSERT: Create new relationship
    UPDATE with Actions:
        - REINFORCE: Boost strength, update sentiment
        - EXTEND: Add interaction types
        - DECAY: Apply decay factor for inactivity
    ARCHIVE: Soft-delete inactive relationship

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

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
from k0.pipelines.p03.staged_writes import LAYER_ST_SOCIAL, StagedWrite, WriteOperation

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


class RelationshipAction(str, Enum):
    """
    Actions for social relationship updates.

    REINFORCE: Boost strength, update sentiment
    EXTEND: Add new interaction types
    DECAY: Apply decay factor for inactivity
    """

    REINFORCE = "REINFORCE"
    EXTEND = "EXTEND"
    DECAY = "DECAY"


@dataclass
class RelationshipWriteData:
    """
    Data structure for social layer writes.

    Represents a relationship record between two actors.

    Attributes:
        relationship_id: Unique relationship identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        actor_a_id: First actor/person ID
        actor_b_id: Second actor/person ID
        relationship_type: Type of relationship (friend, colleague, family, etc.)
        strength: Relationship strength [0.0, 1.0]
        interaction_count: Number of interactions
        last_interaction_at_ms: Last interaction time (MILLISECONDS)
        sentiment_avg: Rolling average sentiment [-1.0, 1.0]
        interaction_types_json: JSON array of interaction types
    """

    relationship_id: str
    tenant_id: str
    space_id: str
    actor_a_id: str
    actor_b_id: str
    relationship_type: str = "unknown"
    strength: float = 0.5
    interaction_count: int = 1
    last_interaction_at_ms: int = 0
    sentiment_avg: float = 0.0
    interaction_types_json: str = "[]"

    # GAP-001: Inline vector and text preservation fields
    source_texts_json: Optional[str] = None  # JSON array of source event texts
    embedding_text: Optional[str] = None  # Generated text for UltraBERT embedding
    embedding_vector: Optional[bytes] = None  # 768-dim float32 as BYTEA (3072 bytes)
    embedding_model: Optional[str] = None  # Model version (e.g., "ultrabert-v2.1.0")


class SocialLayerWriter:
    """
    Writer for st_social (relationships) layer.

    Handles INSERT, UPDATE (with actions), and ARCHIVE operations
    for relationship records.

    Table: st_social
    Primary Key: relationship_id
    Version Column: version (for optimistic locking)

    Action-Based Updates:
        REINFORCE: Boost strength, update sentiment (rolling average)
        EXTEND: Add interaction types to interaction_types_json
        DECAY: Apply decay factor for inactive relationships

    Usage:
        writer = SocialLayerWriter()
        result = await writer.write(staged_writes, uow)
    """

    LAYER = LAYER_ST_SOCIAL

    # Strength boost factor for reinforcement (multiplicative)
    REINFORCE_FACTOR = 1.1

    # Decay factor for inactive relationships
    DECAY_FACTOR = 0.95

    # Sentiment smoothing factors (new value weight)
    SENTIMENT_NEW_WEIGHT = 0.1
    SENTIMENT_OLD_WEIGHT = 0.9

    def __init__(
        self,
        coordinator: Optional[TextVectorCoordinator] = None,
        observation_recorder: Optional[ObservationRecorder] = None,
    ) -> None:
        """
        Initialize SocialLayerWriter.

        Args:
            coordinator: Optional TextVectorCoordinator for GAP-001 embedding generation.
                        If not provided, uses singleton via get_coordinator().
            observation_recorder: ObservationRecorder for holistic context (uses singleton if None)
        """
        self._coordinator = coordinator
        self._observation_recorder = observation_recorder

    def _get_coordinator(self) -> TextVectorCoordinator:
        """Get coordinator, initializing singleton if needed."""
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
        observed_at = data.get("created_at") or data.get("last_interaction_at") or _now_ms()

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
        Execute social layer writes.

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
        INSERT new relationship with ON CONFLICT DO NOTHING.

        Creates a new relationship record. If the relationship_id already
        exists, the insert is silently ignored (idempotent).

        Includes UltraBERT-derived fields:
        - ultrabert_relation_types: Direct relation labels (parent_of, spouse_of, etc.)
        - emotional_role: Social function (MENTOR, CONFIDANT, etc.)
        - emotional_valence_avg/trend: Sentiment analysis
        - relationship_phase: FORMING, STABLE, DEEPENING, COOLING
        - dominant_emotion: Most frequent emotion
        - interaction_modalities_json, typical_activities_json
        - emotions_json, sentiment_trajectory_json

        GAP-001: Fetches source texts and generates embeddings.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with record data
        """
        import json

        data = write.record_data
        now = _now_ms()

        # Serialize list fields to JSON
        ultrabert_types = data.get("ultrabert_relation_types", [])
        if isinstance(ultrabert_types, list):
            ultrabert_types = json.dumps(ultrabert_types)

        interaction_modalities = data.get("interaction_modalities_json", "[]")
        if isinstance(interaction_modalities, list):
            interaction_modalities = json.dumps(interaction_modalities)

        typical_activities = data.get("typical_activities_json", "[]")
        if isinstance(typical_activities, list):
            typical_activities = json.dumps(typical_activities)

        emotions = data.get("emotions_json", "{}")
        if isinstance(emotions, dict):
            emotions = json.dumps(emotions)

        sentiment_trajectory = data.get("sentiment_trajectory_json", "[]")
        if isinstance(sentiment_trajectory, list):
            sentiment_trajectory = json.dumps(sentiment_trajectory)

        source_episodes = data.get("source_episodes_json", "[]")
        if isinstance(source_episodes, list):
            source_episodes = json.dumps(source_episodes)

        # GAP-001: Fetch source texts and generate embedding
        # Social layer uses source_episodes_json - need to resolve episodes to events
        source_texts_json: Optional[str] = None
        embedding_text: Optional[str] = None
        embedding_vector: Optional[bytes] = None
        embedding_model: Optional[str] = None

        try:
            episode_ids: List[str] = []
            if source_episodes and source_episodes != "[]":
                parsed_episodes = json.loads(source_episodes)
                if isinstance(parsed_episodes, list):
                    episode_ids = [str(eid) for eid in parsed_episodes]

            if episode_ids:
                coordinator = self._get_coordinator()
                tv_result = await coordinator.process_for_episodes(
                    layer=self.LAYER,
                    record_data=data,
                    source_episode_ids=episode_ids,
                    conn=uow.connection,
                )
                source_texts_json = tv_result.source_texts_json
                embedding_text = tv_result.embedding_text
                embedding_vector = tv_result.embedding_vector
                embedding_model = tv_result.embedding_model
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Social embedding failed: {e}")
            # Non-fatal: continue with INSERT

        await uow.connection.execute(
            """
            INSERT INTO st_social (
                relationship_id, tenant_id, space_id,
                actor_a_id, actor_b_id,
                relationship_type, relationship_subtype, relationship_label,
                interaction_count, avg_sentiment, relationship_strength, intimacy_level,
                first_interaction_at, last_interaction_at, interaction_frequency,
                source_episodes_json,
                observation_count, confidence_score, decay_factor,
                archival_status,
                created_at, updated_at, valid_from, valid_to,
                version,
                -- UltraBERT-derived columns (migration 0054)
                ultrabert_relation_types,
                emotional_role,
                emotional_valence_avg,
                emotional_valence_trend,
                relationship_phase,
                interaction_modalities_json,
                typical_activities_json,
                sentiment_trajectory_json,
                emotions_json,
                dominant_emotion,
                canonical_entity_id,
                -- GAP-001: Inline vector and text preservation columns
                source_texts_json,
                embedding_text,
                embedding_vector,
                embedding_model
            ) VALUES (
                $1, $2, $3,
                $4, $5,
                $6, $7, $8,
                $9, $10, $11, $12,
                $13, $14, $15,
                $16,
                $17, $18, $19,
                $20,
                $21, $22, $23, $24,
                1,
                $25, $26, $27, $28, $29, $30, $31, $32, $33, $34, $35,
                $36, $37, $38, $39
            )
            ON CONFLICT (relationship_id) DO NOTHING
            """,
            data["relationship_id"],
            data["tenant_id"],
            data["space_id"],
            data["actor_a_id"],
            data["actor_b_id"],
            data.get("relationship_type", "ACQUAINTANCE"),
            data.get("relationship_subtype"),
            data.get("relationship_label"),
            data.get("interaction_count", 1),
            data.get("avg_sentiment") or data.get("emotional_valence_avg", 0.0),
            data.get("relationship_strength", 0.5),
            data.get("intimacy_level", "CASUAL"),
            data.get("first_interaction_at") or now,
            data.get("last_interaction_at") or now,
            data.get("interaction_frequency"),
            source_episodes,
            data.get("observation_count", 1),
            data.get("confidence_score") or data.get("confidence", 0.5),
            data.get("decay_factor", 1.0),
            "ACTIVE",
            now,  # created_at
            now,  # updated_at
            now,  # valid_from
            None,  # valid_to
            # UltraBERT-derived fields
            ultrabert_types,
            data.get("emotional_role"),
            data.get("emotional_valence_avg", 0.0),
            data.get("emotional_valence_trend", 0.0),
            data.get("relationship_phase", "FORMING"),
            interaction_modalities,
            typical_activities,
            sentiment_trajectory,
            emotions,
            data.get("dominant_emotion"),
            data.get("canonical_entity_id"),
            # GAP-001: Inline vector fields
            source_texts_json,
            embedding_text,
            embedding_vector,
            embedding_model,
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
        UPDATE relationship based on action or generic data.

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

        if action == RelationshipAction.REINFORCE or action == "REINFORCE":
            await self._reinforce(uow, write)
        elif action == RelationshipAction.EXTEND or action == "EXTEND":
            await self._extend(uow, write)
        elif action == RelationshipAction.DECAY or action == "DECAY":
            await self._decay(uow, write)
        else:
            # Generic update
            await self._generic_update(uow, write)

    async def _reinforce(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        REINFORCE action: Boost strength, update sentiment, increment interactions.

        Updates UltraBERT-derived fields:
        - emotional_valence_avg: Exponential moving average with new sentiment
        - emotional_valence_trend: Updated based on recent trajectory
        - emotions_json: Merge new emotions with existing counts
        - dominant_emotion: Recalculate from updated emotions
        - sentiment_trajectory_json: Append new sentiment data point

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with optional new_sentiment, emotions, etc.
        """
        import json

        now = _now_ms()
        data = write.record_data
        new_sentiment = data.get("new_sentiment", 0.0)
        new_valence = data.get("emotional_valence", 0.0)  # From UltraBERT

        # Build sentiment trajectory entry
        trajectory_entry = {
            "timestamp": now,
            "valence": new_valence or new_sentiment,
            "event_id": data.get("source_event_id", ""),
        }
        trajectory_json = json.dumps([trajectory_entry])

        # Merge new emotions with existing
        new_emotions = data.get("emotions", {})
        emotions_json = json.dumps(new_emotions) if new_emotions else "{}"

        result = await uow.connection.execute(
            """
            UPDATE st_social
            SET relationship_strength = LEAST(relationship_strength * $1, 1.0),
                interaction_count = interaction_count + 1,
                observation_count = observation_count + 1,
                last_interaction_at = $2,
                avg_sentiment = (COALESCE(avg_sentiment, 0) * $3 + $4 * $5),
                emotional_valence_avg = (COALESCE(emotional_valence_avg, 0) * $3 + $4 * $5),
                emotional_valence_trend = CASE
                    WHEN emotional_valence_avg IS NULL THEN 0
                    ELSE ($4 - emotional_valence_avg) * 0.3 + COALESCE(emotional_valence_trend, 0) * 0.7
                END,
                sentiment_trajectory_json = CASE
                    WHEN sentiment_trajectory_json IS NULL THEN $6
                    ELSE (
                        SELECT jsonb_agg(value)::text
                        FROM (
                            SELECT value FROM jsonb_array_elements(sentiment_trajectory_json::jsonb)
                            UNION ALL
                            SELECT value FROM jsonb_array_elements($6::jsonb)
                            ORDER BY value->>'timestamp' DESC
                            LIMIT 20
                        ) sub
                    )
                END,
                emotions_json = CASE
                    WHEN emotions_json IS NULL OR emotions_json = '{}' THEN $7
                    ELSE (
                        SELECT jsonb_object_agg(
                            key,
                            COALESCE((emotions_json::jsonb->>key)::int, 0) + COALESCE((($7::jsonb)->>key)::int, 0)
                        )::text
                        FROM (
                            SELECT DISTINCT key FROM (
                                SELECT key FROM jsonb_object_keys(COALESCE(emotions_json::jsonb, '{}'::jsonb)) AS key
                                UNION
                                SELECT key FROM jsonb_object_keys($7::jsonb) AS key
                            ) keys
                        ) all_keys
                    )
                END,
                updated_at = $2,
                version = version + 1
            WHERE relationship_id = $8
              AND ($9::int IS NULL OR version = $9)
            """,
            self.REINFORCE_FACTOR,
            now,
            self.SENTIMENT_OLD_WEIGHT,
            new_valence or new_sentiment,
            self.SENTIMENT_NEW_WEIGHT,
            trajectory_json,
            emotions_json,
            write.record_id,
            write.expected_version,
        )

        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_social:{write.record_id}")

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
                logger.warning(
                    "Failed to record reinforcement observation for %s: %s",
                    write.record_id,
                    e,
                )

    async def _extend(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        EXTEND action: Add interaction types to relationship.

        Appends new_types_json to the existing interaction_types_json array.
        Also increments interaction_count.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with new_types_json
        """
        new_types = write.record_data.get("new_types_json", "[]")
        now = _now_ms()

        result = await uow.connection.execute(
            """
            UPDATE st_social
            SET interaction_types_json = (
                SELECT jsonb_agg(DISTINCT value)::text
                FROM (
                    SELECT value FROM jsonb_array_elements_text(
                        interaction_types_json::jsonb
                    )
                    UNION
                    SELECT value FROM jsonb_array_elements_text($1::jsonb)
                ) sub
            ),
            interaction_count = interaction_count + 1,
            last_interaction_at = $2,
            version = version + 1
            WHERE relationship_id = $3
              AND ($4::int IS NULL OR version = $4)
            """,
            new_types,
            now,
            write.record_id,
            write.expected_version,
        )

        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_social:{write.record_id}")

    async def _decay(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        DECAY action: Apply decay factor for inactive relationships.

        Multiplies strength by DECAY_FACTOR to simulate relationship
        weakening over time without interaction.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with relationship_id
        """
        decay_factor = write.record_data.get("decay_factor", self.DECAY_FACTOR)

        result = await uow.connection.execute(
            """
            UPDATE st_social
            SET strength = strength * $1,
                version = version + 1
            WHERE relationship_id = $2
              AND ($3::int IS NULL OR version = $3)
            """,
            decay_factor,
            write.record_id,
            write.expected_version,
        )

        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_social:{write.record_id}")

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
        exclude_keys = {
            "relationship_id",
            "_action",
            "_version",
            "new_types_json",
            "new_sentiment",
            "decay_factor",
        }

        for key, value in data.items():
            if key not in exclude_keys:
                set_parts.append(f"{key} = ${idx}")
                values.append(value)
                idx += 1

        if not set_parts:
            return  # Nothing to update

        # Add version increment and WHERE clause values
        values.append(write.record_id)  # WHERE relationship_id = $N
        values.append(write.expected_version or 0)  # AND version = $N+1

        sql = f"""
            UPDATE st_social
            SET {", ".join(set_parts)}, version = version + 1
            WHERE relationship_id = ${idx}
              AND version = ${idx + 1}
        """

        result = await uow.connection.execute(sql, *values)

        # Check for version conflict
        rows_affected = _parse_rows_affected(result)
        if rows_affected == 0 and write.expected_version is not None:
            raise OptimisticLockError(f"Version conflict for st_social:{write.record_id}")

    async def _archive(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        ARCHIVE relationship (soft-delete for inactive relationships).

        Marks the relationship as archived with a timestamp and reason.
        Default reason is "inactive".

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with archive reason
        """
        now = _now_ms()

        await uow.connection.execute(
            """
            UPDATE st_social
            SET archival_status = 'ARCHIVED',
                archived_at = $1,
                archived_reason = $2,
                version = version + 1
            WHERE relationship_id = $3
              AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
            """,
            now,
            write.record_data.get("archived_reason", "inactive"),
            write.record_id,
        )

    async def _tombstone(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        TOMBSTONE relationship (hard-delete marker).

        Marks the record for sync propagation as deleted.

        Args:
            uow: UnitOfWork providing database connection
            write: StagedWrite with tombstone data
        """
        now = _now_ms()

        await uow.connection.execute(
            """
            UPDATE st_social
            SET archival_status = 'TOMBSTONE',
                archived_at = $1,
                archived_reason = 'tombstone',
                version = version + 1
            WHERE relationship_id = $2
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


def create_social_writer() -> SocialLayerWriter:
    """Factory function to create a SocialLayerWriter."""
    return SocialLayerWriter()
