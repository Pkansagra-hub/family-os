"""
MCTSLayerWriter — Issue 8.1.7

Writer for st_mcts_decisions (MCTS decision traces) layer.
Handles persistence of MCTS decision records from R5 dream exploration.

Spec Reference:
    - M8_EXECUTION.md (Issue 8.1.7 — st_mcts_decisions layer writer)
    - Dossier Appendix D (st_mcts_decisions schema)

Operations:
    INSERT: Create new MCTS decision trace

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from k0.modules.consolidation.truth_writer.result import LayerWriteResult
from k0.pipelines.p03.staged_writes import LAYER_ST_MCTS, StagedWrite, WriteOperation

if TYPE_CHECKING:
    from k0.modules.consolidation.truth_writer.transaction import UnitOfWork


logger = logging.getLogger(__name__)


class MCTSLayerWriter:
    """
    Writer for st_mcts_decisions (MCTS decision traces) layer.

    Handles INSERT operations for MCTS decision records from R5.

    Table: st_mcts_decisions
    Primary Key: decision_id
    """

    LAYER = LAYER_ST_MCTS

    async def write(
        self,
        writes: List[StagedWrite],
        uow: "UnitOfWork",
    ) -> LayerWriteResult:
        """
        Execute MCTS decision layer writes.

        Processes all writes for this layer, tracking successes and failures.

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
                else:
                    raise ValueError(f"Unsupported operation {write.operation} for {self.LAYER}")
                succeeded += 1
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

    async def _insert(self, uow: "UnitOfWork", write: StagedWrite) -> None:
        """
        INSERT new MCTS decision record.

        Args:
            uow: UnitOfWork with database connection
            write: StagedWrite with decision data
        """
        query = """
        INSERT INTO st_mcts_decisions (
            decision_id,
            cycle_id,
            decision_type,
            context_json,
            rollouts_allocated,
            rollouts_executed,
            early_termination,
            termination_reason,
            chosen_action,
            value_estimate,
            confidence_interval_width,
            compute_ms,
            created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        """

        data = write.record_data
        await uow.connection.execute(
            query,
            data["decision_id"],
            data["cycle_id"],
            data["decision_type"],
            data["context_json"],
            data["rollouts_allocated"],
            data["rollouts_executed"],
            data["early_termination"],
            data["termination_reason"],
            data["chosen_action"],
            data["value_estimate"],
            data["confidence_interval_width"],
            data["compute_ms"],
            data["created_at"],
        )
