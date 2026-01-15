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

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from k0.modules.consolidation.truth_writer.result import LayerWriteResult
from k0.pipelines.p03.phases.r7_truth_writer import OptimisticLockError
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_PROSPECTIVE,
    StagedWrite,
    WriteOperation,
)

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork


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
        """
        data = write.record_data
        now = _now_ms()

        await uow.connection.execute(
            """
            INSERT INTO st_prospective (
                intention_id, tenant_id, space_id, intention_type,
                description, trigger_time, trigger_context_json,
                goal_inference_json, confidence, status,
                source_episodes_json, counterfactual_json,
                created_at, version
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, 1)
            ON CONFLICT (intention_id) DO NOTHING
            """,
            data["intention_id"],
            data["tenant_id"],
            data["space_id"],
            data.get("intention_type", "intention"),
            data.get("description", ""),
            data.get("trigger_time_ms"),
            data.get("trigger_context_json", "{}"),
            data.get("goal_inference_json", "{}"),
            data.get("confidence", 0.5),
            data.get("status", "pending"),
            data.get("source_episodes_json", "[]"),
            data.get("counterfactual_json"),
            now,
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
