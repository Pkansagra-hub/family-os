"""
ProspectiveLayerWriter — Issue 5.2.7

Writer for st_prospective (intentions/goals) layer.
Handles future-oriented patterns and goal inference.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.7 — st_prospective layer writer)
    - Dossier §4.8.6 (st_prospective Writes)

Operations:
    INSERT: Create new intention/goal
    UPDATE with Actions:
        - EXTEND: Update goal inference, add trigger contexts
        - COMPLETE: Mark intention as completed
        - COUNTERFACTUAL: Store counterfactual from R5 CPN
    ARCHIVE: Soft-delete expired/cancelled intention

Status Lifecycle:
    pending → completed/expired/cancelled

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

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
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_PROSPECTIVE,
    StagedWrite,
    WriteOperation,
)

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


class IntentionAction(str, Enum):
    """
    Actions for intention updates.

    EXTEND: Update goal inference, add trigger contexts
    COMPLETE: Mark intention as completed
    COUNTERFACTUAL: Store counterfactual from R5 CPN
    """

    EXTEND = "EXTEND"
    COMPLETE = "COMPLETE"
    COUNTERFACTUAL = "COUNTERFACTUAL"


@dataclass
class IntentionWriteData:
    """
    Data structure for prospective layer writes.

    Represents a future-oriented intention, goal, or reminder.

    Attributes:
        intention_id: Unique intention identifier
        tenant_id: Tenant identifier
        space_id: Space identifier
        intention_type: Type (goal, reminder, plan, intention)
        description: Human-readable description
        trigger_time_ms: When to remind/trigger (MILLISECONDS, optional)
        trigger_context_json: JSON object with context triggers
        goal_inference_json: JSON object with inferred goals
        confidence: Confidence score [0.0, 1.0]
        status: Lifecycle status (pending, completed, expired, cancelled)
        source_episodes_json: JSON array of contributing episode IDs
        counterfactual_json: JSON from R5 CPN (optional)
    """

    intention_id: str
    tenant_id: str
    space_id: str
    intention_type: str = "intention"  # goal, reminder, plan, intention
    description: str = ""
    trigger_time_ms: Optional[int] = None
    trigger_context_json: str = "{}"
    goal_inference_json: str = "{}"
    confidence: float = 0.5
    status: str = "pending"  # pending, completed, expired, cancelled
    source_episodes_json: str = "[]"
    counterfactual_json: Optional[str] = None

    # GAP-001: Inline vector and text preservation fields
    source_texts_json: Optional[str] = None  # JSON array of source event texts
    embedding_text: Optional[str] = None  # Generated text for UltraBERT embedding
    embedding_vector: Optional[bytes] = None  # 768-dim float32 as BYTEA (3072 bytes)
    embedding_model: Optional[str] = None  # Model version (e.g., "ultrabert-v2.1.0")

    # Issue 7.7: Temporal anchor context for prospective memories
    anchor_time_utc: Optional[int] = None  # When user expressed the intention (MILLISECONDS)
    original_temporal_expr: Optional[str] = None  # Original expression ("next week", "tomorrow")


class ProspectiveLayerWriter:
    """
    Writer for st_prospective (intentions/goals) layer.

    Handles INSERT, UPDATE (with actions), and ARCHIVE operations
    for intention records.

    Table: st_prospective
    Primary Key: intention_id
    Version Column: version (for optimistic locking)

    Action-Based Updates:
        EXTEND: Update goal inference, add new trigger contexts
        COMPLETE: Mark intention as completed with timestamp
        COUNTERFACTUAL: Store counterfactual from R5 CPN

    Usage:
        writer = ProspectiveLayerWriter()
        result = await writer.write(staged_writes, uow)
    """

    LAYER = LAYER_ST_PROSPECTIVE

    def __init__(
        self,
        coordinator: Optional[TextVectorCoordinator] = None,
        observation_recorder: Optional[ObservationRecorder] = None,
    ) -> None:
        """
        Initialize ProspectiveLayerWriter.

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
        observed_at = data.get("created_at") or data.get("target_date") or _now_ms()

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
        Execute prospective layer writes.

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
            except OptimisticLockError:
                failed_ids.append(write.record_id)
                error_messages.append(f"Version conflict for intention {write.record_id}")
            except Exception as e:
                failed_ids.append(write.record_id)
                error_messages.append(f"Failed to write {write.record_id}: {e}")

        return LayerWriteResult(
            layer=self.LAYER,
            writes_attempted=len([w for w in writes if w.layer == self.LAYER]),
            writes_succeeded=succeeded,
            writes_failed=len(failed_ids),
            failed_ids=failed_ids,
            error_message="; ".join(error_messages) if error_messages else None,
        )

    async def _insert(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        INSERT new intention/goal.

        Creates a new intention record with initial values.
        Uses ON CONFLICT DO NOTHING for idempotency.

        GAP-001: Uses description field as embedding text (no source events to fetch).
        """
        data = write.record_data
        now = _now_ms()

        # GAP-001: Generate embedding from description
        # Prospective layer uses description field as the embedding text
        source_texts_json: Optional[str] = None
        embedding_text: Optional[str] = None
        embedding_vector: Optional[bytes] = None
        embedding_model: Optional[str] = None

        try:
            description = data.get("intention_description", data.get("description", ""))
            if description:
                coordinator = self._get_coordinator()
                tv_result = await coordinator.process_without_fetch(
                    layer=self.LAYER,
                    record_data=data,
                    source_texts=[description],
                )
                source_texts_json = tv_result.source_texts_json
                embedding_text = tv_result.embedding_text
                embedding_vector = tv_result.embedding_vector
                embedding_model = tv_result.embedding_model
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Prospective embedding failed: {e}")
            # Non-fatal: continue with INSERT

        await uow.connection.execute(
            """
            INSERT INTO st_prospective (
                intention_id, tenant_id, space_id, actor_id, intention_type,
                intention_description, target_date, target_context,
                inferred_from_json, inference_confidence, confidence_score, status,
                created_at, updated_at, valid_from, version,
                -- GAP-001: Inline vector and text preservation columns
                source_texts_json, embedding_text, embedding_vector, embedding_model
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $13, $13, 1,
                      $14, $15, $16, $17)
            ON CONFLICT (intention_id) DO NOTHING
            """,
            data["intention_id"],
            data["tenant_id"],
            data["space_id"],
            data.get("actor_id", data["tenant_id"]),  # Default to tenant if no actor
            data.get("intention_type", "GOAL"),
            data.get("intention_description", data.get("description", "")),
            data.get("target_date", data.get("trigger_time_ms")),
            data.get("target_context", data.get("trigger_context_json")),
            data.get("inferred_from_json", data.get("goal_inference_json")),
            data.get("inference_confidence", data.get("confidence", 0.5)),
            data.get("confidence_score", data.get("confidence", 0.5)),
            data.get("status", "ACTIVE"),
            now,
            # GAP-001 fields
            source_texts_json,
            embedding_text,
            embedding_vector,
            embedding_model,
        )

        # Issue 7.5: Record observation with FIRST_SEEN type
        # Note: Prospective layer has INSERT only (no MERGE/REINFORCE)
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
        UPDATE intention based on action type.

        Raises OptimisticLockError if version mismatch.
        """
        data = write.record_data
        action = data.get("_action", "EXTEND")

        if action == IntentionAction.EXTEND or action == "EXTEND":
            await self._update_extend(uow, write)
        elif action == IntentionAction.COMPLETE or action == "COMPLETE":
            await self._update_complete(uow, write)
        elif action == IntentionAction.COUNTERFACTUAL or action == "COUNTERFACTUAL":
            await self._update_counterfactual(uow, write)
        else:
            # Default to EXTEND for unknown actions
            await self._update_extend(uow, write)

    async def _update_extend(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """EXTEND: Update goal inference, add trigger contexts."""
        data = write.record_data
        result = await uow.connection.execute(
            """
            UPDATE st_prospective
            SET goal_inference_json = COALESCE($1, goal_inference_json),
                trigger_context_json = trigger_context_json || COALESCE($2::jsonb, '{}'::jsonb),
                confidence = COALESCE($3, confidence),
                source_episodes_json = source_episodes_json || COALESCE($4::jsonb, '[]'::jsonb),
                version = version + 1
            WHERE intention_id = $5 AND version = $6
            """,
            data.get("goal_inference_json"),
            data.get("new_triggers_json", "{}"),
            data.get("confidence"),
            data.get("new_episodes_json", "[]"),
            write.record_id,
            write.expected_version,
        )

        if result == "UPDATE 0":
            raise OptimisticLockError(f"Version conflict updating intention {write.record_id}")

    async def _update_complete(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """COMPLETE: Mark intention as completed."""
        now = _now_ms()
        result = await uow.connection.execute(
            """
            UPDATE st_prospective
            SET status = 'completed',
                completed_at = $1,
                version = version + 1
            WHERE intention_id = $2 AND version = $3
            """,
            now,
            write.record_id,
            write.expected_version,
        )

        if result == "UPDATE 0":
            raise OptimisticLockError(f"Version conflict completing intention {write.record_id}")

    async def _update_counterfactual(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """COUNTERFACTUAL: Store counterfactual from R5 CPN."""
        data = write.record_data
        result = await uow.connection.execute(
            """
            UPDATE st_prospective
            SET counterfactual_json = COALESCE($1, counterfactual_json),
                version = version + 1
            WHERE intention_id = $2 AND version = $3
            """,
            data.get("counterfactual_json", "{}"),
            write.record_id,
            write.expected_version,
        )

        if result == "UPDATE 0":
            raise OptimisticLockError(
                f"Version conflict updating counterfactual for intention {write.record_id}"
            )

    async def _archive(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        ARCHIVE expired/cancelled intention.

        Sets archival_status and updates status if reason indicates expired/cancelled.
        """
        data = write.record_data
        reason = data.get("archived_reason", "expired")
        now = _now_ms()

        # Map archive reasons to status values
        status_map = {
            "expired": "expired",
            "cancelled": "cancelled",
            "completed": "completed",
        }
        new_status = status_map.get(reason)

        if new_status:
            await uow.connection.execute(
                """
                UPDATE st_prospective
                SET archival_status = 'ARCHIVED',
                    status = $1,
                    archived_at = $2,
                    archived_reason = $3
                WHERE intention_id = $4
                  AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
                """,
                new_status,
                now,
                reason,
                write.record_id,
            )
        else:
            await uow.connection.execute(
                """
                UPDATE st_prospective
                SET archival_status = 'ARCHIVED',
                    archived_at = $1,
                    archived_reason = $2
                WHERE intention_id = $3
                  AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
                """,
                now,
                reason,
                write.record_id,
            )

    async def _tombstone(self, uow: UnitOfWork, write: StagedWrite) -> None:
        """
        TOMBSTONE intention for GDPR deletion.

        Hard-deletes all data except intention_id and tombstone marker.
        """
        now = _now_ms()
        await uow.connection.execute(
            """
            UPDATE st_prospective
            SET description = '',
                trigger_time = NULL,
                trigger_context_json = '{}',
                goal_inference_json = '{}',
                source_episodes_json = '[]',
                counterfactual_json = NULL,
                archival_status = 'TOMBSTONE',
                archived_at = $1,
                archived_reason = 'gdpr_deletion'
            WHERE intention_id = $2
            """,
            now,
            write.record_id,
        )


def create_prospective_writer() -> ProspectiveLayerWriter:
    """Factory function to create ProspectiveLayerWriter instance."""
    return ProspectiveLayerWriter()
