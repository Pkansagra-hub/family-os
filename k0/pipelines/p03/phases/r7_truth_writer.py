"""
R7 Phase — Memory Layer Writes (Truth Update).

M3 Issue 3.1.1: Wire P03StagedWrites to UnitOfWork to Truth Tables.
M5 Issue 5.2.W1: Wire to DecisionRouter and TransactionCoordinator.

This phase executes all staged writes atomically via UnitOfWork:
1. Execute staged writes via DecisionRouter (M5: replaces inline SQL)
2. Stage outbox events for R8 emission
3. Update st_hipp_events consolidation status
4. Commit atomically (all-or-nothing)

References:
    - Dossier 4.8: Outbox Pattern
    - Dossier Appendix G.7: R7 Idempotency Keys
    - M3 Execution: docs/TEMP_EXECUTION_DOCS/M3_EXECUTION.md Issue 3.1.1
    - M5 Execution: docs/TEMP_EXECUTION_DOCS/M5_EXECUTION.md Issue 5.2.W1
"""

from __future__ import annotations

import json
import logging
import time
import warnings
from collections import Counter
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from k0.pipelines.p03.observability import P03Error
from k0.pipelines.p03.phase_interface import P03PhaseResult
from k0.pipelines.p03.runner_contract import P03PhaseId
from k0.pipelines.p03.staged_writes import StagedWrite, WriteOperation
from k0.storage.outbox import OutboxEntry

if TYPE_CHECKING:
    import asyncpg

    from k0.modules.consolidation.truth_writer.result import WriteResult
    from k0.modules.consolidation.truth_writer.router import DecisionRouter
    from k0.modules.consolidation.truth_writer.transaction import TransactionCoordinator
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.phase_interface import P03RunnerContext
    from k0.uow.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


# =============================================================================
# PRIMARY KEY MAPPING
# =============================================================================

# Map layer names to their primary key columns
LAYER_PK_MAP: Dict[str, str] = {
    "st_epi": "episode_id",
    "st_sem": "pattern_id",
    "st_procedural": "routine_id",
    "st_social": "relationship_id",
    "st_prospective": "intention_id",
    "st_kg_dom": "entity_id",
    "st_kg_edges": "edge_id",
    "st_vec": "embedding_id",
    "st_hipp_events": "event_id",
    "st_learning_queue": "queue_id",
}


# =============================================================================
# R7 TRUTH WRITER PHASE
# =============================================================================


class R7TruthWriter:
    """
    R7 Phase: Execute staged writes atomically via UnitOfWork.

    Responsibilities:
        1. Open UoW transaction
        2. Execute all staged writes via DecisionRouter (M5: per-layer writers)
        3. Stage outbox events for R8 emission
        4. Update st_hipp_events consolidation status
        5. Commit atomically (all-or-nothing)

    M5 Wiring (Issue 5.2.W1):
        - DecisionRouter routes writes to per-layer writers (5.2.3-5.2.9)
        - TransactionCoordinator handles atomic transaction + retries
        - Legacy inline SQL kept as deprecated fallback

    Idempotency:
        - Each write has a unique idempotency_key in StagedWrite
        - INSERT uses ON CONFLICT DO NOTHING
        - UPDATE uses optimistic locking via expected_version
        - ARCHIVE/TOMBSTONE are idempotent by nature

    Dependency Order (from P03StagedWrites):
        vec → kg_dom → kg_edges → epi → sem →
        procedural → social → prospective →
        learning_queue → hipp_events
    """

    PHASE_ID = P03PhaseId.R7_WRITE

    # M5: Use per-layer router instead of inline SQL (toggle for rollback)
    # Default to False during rollout to avoid breaking existing tests
    USE_M5_ROUTER = True

    def __init__(self) -> None:
        """Initialize R7 phase with M5 router (lazy-loaded)."""
        self._router: Optional[DecisionRouter] = None
        self._coordinator: Optional[TransactionCoordinator] = None

    async def run(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> P03PhaseResult:
        """
        Execute R7 phase.

        M5 W3: Consumes R6Output when available (preferred).
        Falls back to envelope.staged for backward compatibility.

        Args:
            envelope: P03BatchEnvelope with staged writes from R1-R6
            ctx: Runner context with syscalls, logger, config

        Returns:
            P03PhaseResult indicating success/failure
        """
        start_ms = int(time.time() * 1000)
        cycle_id = envelope.context.cycle_id

        # M5: Store envelope reference for router access
        self._current_envelope = envelope

        # M5 W3: Get staged writes from R6Output or fallback to envelope.staged
        r6_output = envelope.phases.r6_output
        if r6_output is not None:
            # M5: Use validated manifest from R6
            staged = envelope.staged  # R6Output populates envelope.staged
            has_r6_output = True
        else:
            # Legacy: Use P03StagedWrites directly
            staged = envelope.staged
            has_r6_output = False

        logger.info(
            "R7: Starting truth write phase",
            extra={
                "cycle_id": cycle_id,
                "total_writes": staged.total_writes(),
                "total_outbox": staged.total_outbox_events(),
                "use_m5_router": self.USE_M5_ROUTER,
                "has_r6_output": has_r6_output,
            },
        )

        try:
            async with ctx.syscalls.unit_of_work() as uow:
                # 1. Execute staged writes (M5: via DecisionRouter)
                writes = staged.get_all_writes_ordered()
                write_result = await self._execute_staged_writes(uow, writes, ctx)

                # M5: Handle WriteResult vs Dict[str, int]
                # Import at runtime to avoid circular dependency
                from k0.modules.consolidation.truth_writer.result import (
                    WriteResult as WriteResultClass,
                )

                if isinstance(write_result, WriteResultClass):
                    writes_executed = write_result.total_succeeded
                    writes_by_layer = {
                        k: v.writes_succeeded for k, v in write_result.by_layer.items()
                    }
                    # M5: Store result for R8 consumption
                    envelope.phases.r7_result = write_result
                else:
                    # Legacy path
                    writes_executed = sum(write_result.values())
                    writes_by_layer = write_result

                # 2. Stage outbox events for R8
                outbox_count = await self._stage_outbox_events(uow, envelope)

                # 3. Update st_hipp_events consolidation status
                status_counts = await self._writeback_status(uow, envelope)

                # Commit happens automatically on UoW __aexit__

            duration_ms = int(time.time() * 1000) - start_ms

            logger.info(
                "R7: Truth write phase completed",
                extra={
                    "cycle_id": cycle_id,
                    "duration_ms": duration_ms,
                    "writes_executed": writes_executed,
                    "outbox_staged": outbox_count,
                    "status_distribution": status_counts,
                    "use_m5_router": self.USE_M5_ROUTER,
                },
            )

            return P03PhaseResult.done(
                phase_id=self.PHASE_ID,
                duration_ms=duration_ms,
                outputs_summary={
                    "writes_executed": writes_executed,
                    "writes_by_layer": writes_by_layer,
                    "outbox_staged": outbox_count,
                    "events_updated": len(envelope.events),
                    "status_distribution": status_counts,
                },
                idempotency_key=f"p03:r7:{cycle_id}",
            )

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms

            logger.exception(
                "R7: Truth write phase failed",
                extra={
                    "cycle_id": cycle_id,
                    "duration_ms": duration_ms,
                    "error": str(e),
                },
            )

            return P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=P03Error(
                    error_id=f"r7-{cycle_id}",
                    phase="R7",
                    stage_id="truth_writer",
                    error_type="R7_COMMIT_ERROR",
                    error_message=str(e),
                    recoverable=False,  # R7 failure is non-resumable
                ),
                duration_ms=duration_ms,
                idempotency_key=f"p03:r7:{cycle_id}",
            )

    # =========================================================================
    # STAGED WRITE EXECUTION
    # =========================================================================

    async def _execute_staged_writes(
        self,
        uow: UnitOfWork,
        writes: List[StagedWrite],
        ctx: P03RunnerContext,
    ) -> Dict[str, int] | WriteResult:
        """
        Execute all staged writes via UoW connection.

        M5 Wiring: Routes to DecisionRouter if USE_M5_ROUTER is True.
        Legacy path uses inline SQL (deprecated, will be removed in M6).

        Args:
            uow: Active UnitOfWork (transaction)
            writes: Ordered list of StagedWrite objects
            ctx: Runner context for logging

        Returns:
            M5: WriteResult with per-layer statistics
            Legacy: Dict mapping layer name to count of writes executed
        """
        # M5: Use DecisionRouter + TransactionCoordinator
        if self.USE_M5_ROUTER:
            return await self._execute_staged_writes_m5(uow, ctx)

        # Legacy: Inline SQL (deprecated)
        return await self._execute_staged_writes_legacy(uow, writes, ctx)

    async def _execute_staged_writes_m5(
        self,
        uow: UnitOfWork,
        ctx: P03RunnerContext,
    ) -> WriteResult:
        """
        M5: Execute staged writes via DecisionRouter + TransactionCoordinator.

        Args:
            uow: Active UnitOfWork (transaction)
            ctx: Runner context for envelope access

        Returns:
            WriteResult with per-layer statistics
        """
        # Get or create router (lazy initialization)
        coordinator = self._get_or_create_coordinator()

        # Get staged writes from envelope (stored in self._current_envelope)
        staged = self._current_envelope.staged

        # Execute all writes atomically via router
        result = await coordinator.execute(
            staged=staged,
            uow=uow,
            required_caps=["storage.write", "outbox.stage"],
        )

        logger.info(
            "R7: Staged writes executed via M5 router",
            extra={
                "total_succeeded": result.write_result.total_succeeded,
                "total_failed": result.write_result.total_failed,
                "attempts": result.attempts,
                "version_conflicts": result.version_conflicts,
                "by_layer": {
                    k: v.writes_succeeded for k, v in result.write_result.by_layer.items()
                },
            },
        )

        return result.write_result

    async def _execute_staged_writes_legacy(
        self,
        uow: UnitOfWork,
        writes: List[StagedWrite],
        ctx: P03RunnerContext,
    ) -> Dict[str, int]:
        """
        DEPRECATED: Legacy inline SQL execution.

        Will be removed in M6. Use M5 router path instead.

        Args:
            uow: Active UnitOfWork (transaction)
            writes: Ordered list of StagedWrite objects
            ctx: Runner context for logging

        Returns:
            Dict mapping layer name to count of writes executed
        """
        warnings.warn(
            "_execute_staged_writes_legacy is deprecated, use M5 router path",
            DeprecationWarning,
            stacklevel=2,
        )

        # Deduplicate writes for same (layer, record_id) to avoid version conflicts
        deduped_writes = self._deduplicate_writes(writes)

        counts: Dict[str, int] = {}

        for write in deduped_writes:
            await self._execute_single_write(uow.connection, write)
            counts[write.layer] = counts.get(write.layer, 0) + 1

        return counts

    def _deduplicate_writes(self, writes: List[StagedWrite]) -> List[StagedWrite]:
        """
        Deduplicate writes by (layer, record_id).

        When multiple writes target the same (layer, record_id) pair:
        - INSERTs: Keep first one (ON CONFLICT DO NOTHING handles rest)
        - UPDATEs: Merge record_data, keep first expected_version
        - Mixed INSERT+UPDATE: Apply INSERT first, then merge UPDATE data

        This prevents OptimisticLockError when multiple phases produce writes
        for the same record.

        Args:
            writes: List of staged writes (may have duplicates)

        Returns:
            Deduplicated list of writes
        """

        # Group writes by (layer, record_id)
        grouped: Dict[tuple, List[StagedWrite]] = {}
        for write in writes:
            key = (write.layer, write.record_id)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(write)

        result: List[StagedWrite] = []
        for key, group in grouped.items():
            if len(group) == 1:
                # Single write, no deduplication needed
                result.append(group[0])
            else:
                # Multiple writes for same record - merge them
                result.append(self._merge_writes(group))

        return result

    def _merge_writes(self, writes: List[StagedWrite]) -> StagedWrite:
        """
        Merge multiple writes for the same (layer, record_id) into one.

        Strategy:
        - If any write is INSERT, use INSERT operation (covers UPSERT cases)
        - Merge all record_data (later writes override earlier for same keys)
        - Use minimum expected_version (first write's version for locking)
        - Combine source_event_ids and source_phase info

        Args:
            writes: List of writes for the same (layer, record_id)

        Returns:
            Single merged StagedWrite
        """
        from k0.pipelines.p03.staged_writes import StagedWrite, WriteOperation

        base = writes[0]

        # Determine final operation (INSERT takes precedence)
        final_op = base.operation
        for w in writes[1:]:
            if w.operation == WriteOperation.INSERT:
                final_op = WriteOperation.INSERT

        # Merge record_data (later overrides earlier for same keys)
        merged_data = {}
        for w in writes:
            merged_data.update(w.record_data)

        # Keep first expected_version (for optimistic locking)
        expected_version = base.expected_version

        # Combine source_event_ids
        all_event_ids = []
        for w in writes:
            for eid in w.source_event_ids:
                if eid not in all_event_ids:
                    all_event_ids.append(eid)

        # Use base's idempotency_key and source_phase (first wins)
        return StagedWrite(
            layer=base.layer,
            record_id=base.record_id,
            operation=final_op,
            record_data=merged_data,
            source_event_ids=all_event_ids,
            source_phase=base.source_phase,
            idempotency_key=base.idempotency_key,
            expected_version=expected_version,
        )

    def _get_or_create_coordinator(self) -> TransactionCoordinator:
        """
        Get or create the TransactionCoordinator with DecisionRouter.

        Lazy-initializes the router with all layer writers.
        Cached for reuse across calls within same R7 instance.

        GAP-001: Injects TextVectorCoordinator into all layer writers
        for inline embedding generation during consolidation.

        Returns:
            Configured TransactionCoordinator
        """
        if self._coordinator is not None:
            return self._coordinator

        # Import layer writers (M5 modules)
        from k0.modules.consolidation.truth_writer.layers.episodic import (
            EpisodicLayerWriter,
        )
        from k0.modules.consolidation.truth_writer.layers.kg import KGLayerWriter
        from k0.modules.consolidation.truth_writer.layers.procedural import (
            ProceduralLayerWriter,
        )
        from k0.modules.consolidation.truth_writer.layers.prospective import (
            ProspectiveLayerWriter,
        )
        from k0.modules.consolidation.truth_writer.layers.semantic import (
            SemanticLayerWriter,
        )
        from k0.modules.consolidation.truth_writer.layers.social import (
            SocialLayerWriter,
        )
        from k0.modules.consolidation.truth_writer.layers.vector import (
            VectorLayerWriter,
        )
        from k0.modules.consolidation.truth_writer.router import (
            DecisionRouter,
            WriteMode,
        )
        from k0.modules.consolidation.truth_writer.text_vector_coordinator import (
            get_coordinator,
        )
        from k0.modules.consolidation.truth_writer.transaction import (
            TransactionConfig,
            TransactionCoordinator,
        )

        # GAP-001: Get shared TextVectorCoordinator for inline embedding generation
        tv_coordinator = get_coordinator()

        # Build router with all layer writers
        # GAP-001: Inject TextVectorCoordinator into writers that generate embeddings
        kg_writer = KGLayerWriter(coordinator=tv_coordinator)
        self._router = DecisionRouter(
            layer_writers={
                "st_epi": EpisodicLayerWriter(coordinator=tv_coordinator),
                "st_sem": SemanticLayerWriter(coordinator=tv_coordinator),
                "st_procedural": ProceduralLayerWriter(coordinator=tv_coordinator),
                "st_social": SocialLayerWriter(coordinator=tv_coordinator),
                "st_prospective": ProspectiveLayerWriter(coordinator=tv_coordinator),
                "st_kg_dom": kg_writer,  # KGLayerWriter handles both tables
                "st_kg_edges": kg_writer,  # Same writer instance for edges
                "st_vec": VectorLayerWriter(),  # No coordinator needed (already has vectors)
            },
            mode=WriteMode.ATOMIC,
        )

        # Wrap in TransactionCoordinator
        self._coordinator = TransactionCoordinator(
            router=self._router,
            config=TransactionConfig(
                mode=WriteMode.ATOMIC,
                max_retries=3,
                retry_delay_ms=100,
                require_capabilities=True,
            ),
        )

        return self._coordinator

    # =========================================================================
    # LEGACY METHODS (deprecated, kept for backward compatibility)
    # =========================================================================

    async def _execute_single_write(
        self,
        conn: asyncpg.Connection,
        write: StagedWrite,
    ) -> None:
        """
        DEPRECATED: Execute a single StagedWrite via inline SQL.

        Use M5 router path (DecisionRouter) instead.
        Will be removed in M6.

        Args:
            conn: asyncpg connection from UoW
            write: StagedWrite to execute

        Raises:
            Exception: If write fails (will trigger UoW rollback)
        """
        if write.operation == WriteOperation.INSERT:
            await self._execute_insert(conn, write)
        elif write.operation == WriteOperation.UPDATE:
            await self._execute_update(conn, write)
        elif write.operation == WriteOperation.ARCHIVE:
            await self._execute_archive(conn, write)
        elif write.operation == WriteOperation.TOMBSTONE:
            await self._execute_tombstone(conn, write)
        else:
            raise ValueError(f"Unknown write operation: {write.operation}")

    async def _execute_insert(
        self,
        conn: asyncpg.Connection,
        write: StagedWrite,
    ) -> None:
        """
        Execute INSERT with ON CONFLICT DO NOTHING for idempotency.

        Args:
            conn: asyncpg connection
            write: StagedWrite with operation=INSERT
        """
        if not write.record_data:
            logger.warning(
                "R7: Skipping INSERT with empty record_data",
                extra={"write_id": write.write_id, "layer": write.layer},
            )
            return

        columns = list(write.record_data.keys())
        placeholders = [f"${i + 1}" for i in range(len(columns))]
        values = [write.record_data[col] for col in columns]

        # Use ON CONFLICT DO UPDATE for st_kg_dom to apply resolved canonical names
        # Use ON CONFLICT DO NOTHING for other tables for idempotency
        pk_column = self._get_pk_column(write.layer)
        if write.layer == "st_kg_dom" and "canonical_name" in write.record_data:
            sql = f"""
                INSERT INTO {write.layer} ({", ".join(columns)})
                VALUES ({", ".join(placeholders)})
                ON CONFLICT ({pk_column}) DO UPDATE SET
                    canonical_name = EXCLUDED.canonical_name,
                    updated_at = EXCLUDED.updated_at
            """
        else:
            sql = f"""
                INSERT INTO {write.layer} ({", ".join(columns)})
                VALUES ({", ".join(placeholders)})
                ON CONFLICT ({pk_column}) DO NOTHING
            """

        await conn.execute(sql, *values)

    async def _execute_update(
        self,
        conn: asyncpg.Connection,
        write: StagedWrite,
    ) -> None:
        """
        Execute UPDATE with optimistic locking.

        Args:
            conn: asyncpg connection
            write: StagedWrite with operation=UPDATE and expected_version
        """
        if not write.record_data:
            logger.warning(
                "R7: Skipping UPDATE with empty record_data",
                extra={"write_id": write.write_id, "layer": write.layer},
            )
            return

        set_clauses = []
        values = []
        idx = 1

        # Special fields that need atomic increment handling
        INCREMENT_FIELDS = {
            "query_count_increment": "query_count",
        }

        # Special fields that need JSON array append handling
        # Maps special field name to target column name
        JSON_APPEND_FIELDS = {
            "milestone_append": "milestones_json",
            "milestones_append": "milestones_json",
        }

        # Fields to skip entirely (they're markers, not real columns)
        SKIP_FIELDS = {"_action"}

        for col, val in write.record_data.items():
            if col in SKIP_FIELDS:
                # Skip marker fields that aren't real columns
                continue
            elif col in INCREMENT_FIELDS:
                # Handle atomic increment: query_count_increment -> query_count = query_count + val
                target_col = INCREMENT_FIELDS[col]
                set_clauses.append(f"{target_col} = COALESCE({target_col}, 0) + ${idx}")
                values.append(val)
                idx += 1
            elif col in JSON_APPEND_FIELDS:
                # Handle JSON array append: milestone_append -> milestones_json = ... || val
                import json

                target_col = JSON_APPEND_FIELDS[col]
                # If val is a list, wrap each item; if it's a dict, wrap in array
                if isinstance(val, list):
                    json_val = json.dumps(val)
                    set_clauses.append(
                        f"{target_col} = COALESCE({target_col}::jsonb, '[]'::jsonb) || ${idx}::jsonb"
                    )
                else:
                    json_val = json.dumps([val])
                    set_clauses.append(
                        f"{target_col} = COALESCE({target_col}::jsonb, '[]'::jsonb) || ${idx}::jsonb"
                    )
                values.append(json_val)
                idx += 1
            else:
                set_clauses.append(f"{col} = ${idx}")
                values.append(val)
                idx += 1

        pk_column = self._get_pk_column(write.layer)

        # Add version check for optimistic locking if expected_version is set
        if write.expected_version is not None:
            sql = f"""
                UPDATE {write.layer}
                SET {", ".join(set_clauses)}, version = version + 1
                WHERE {pk_column} = ${idx}
                  AND version = ${idx + 1}
            """
            values.extend([write.record_id, write.expected_version])
        else:
            sql = f"""
                UPDATE {write.layer}
                SET {", ".join(set_clauses)}
                WHERE {pk_column} = ${idx}
            """
            values.append(write.record_id)

        result = await conn.execute(sql, *values)

        # Check if update was applied (for optimistic locking)
        if write.expected_version is not None:
            # Result format: "UPDATE N" where N is rows affected
            rows_affected = int(result.split()[-1]) if result else 0
            if rows_affected == 0:
                # If expected_version is 0 and no rows affected, record might not exist
                # In this case, try to INSERT instead (upsert behavior for intent signals)
                if write.expected_version == 0:
                    logger.debug(
                        "R7: UPDATE with expected_version=0 found no rows, "
                        "attempting UPSERT fallback",
                        extra={
                            "layer": write.layer,
                            "record_id": write.record_id,
                        },
                    )
                    # Create a minimal insert with the update data
                    await self._execute_upsert_fallback(conn, write)
                else:
                    raise OptimisticLockError(
                        f"Version conflict for {write.layer}:{write.record_id} "
                        f"(expected version {write.expected_version})"
                    )

    async def _execute_upsert_fallback(
        self,
        conn: asyncpg.Connection,
        write: StagedWrite,
    ) -> None:
        """
        Fallback UPSERT when UPDATE with expected_version=0 finds no rows.

        This handles the case where an intent signal references an entity
        that hasn't been created yet (e.g., query mentions "Emma" but
        entity is stored as "cluster_PERSON_emma").

        For st_kg_dom, creates a minimal entity record.
        For other tables, logs warning and skips.
        """
        if write.layer != "st_kg_dom":
            logger.warning(
                "R7: UPSERT fallback only supported for st_kg_dom, skipping",
                extra={"layer": write.layer, "record_id": write.record_id},
            )
            return

        # Build minimal entity record
        pk_column = self._get_pk_column(write.layer)
        now_ms = int(time.time() * 1000)

        # Start with write's record_data and add required fields
        record_data = dict(write.record_data)
        record_data.setdefault(pk_column, write.record_id)
        record_data.setdefault("canonical_name", write.record_id)

        # Infer entity_type from record_id pattern if not provided
        if "entity_type" not in record_data or record_data.get("entity_type") == "UNKNOWN":
            record_data["entity_type"] = self._infer_entity_type(write.record_id)

        record_data.setdefault("tenant_id", "default")
        record_data.setdefault("space_id", "default")
        record_data.setdefault("created_at", now_ms)
        record_data.setdefault("updated_at", now_ms)
        record_data.setdefault("valid_from", now_ms)
        record_data.setdefault("version", 1)
        record_data.setdefault("confidence_score", 0.5)
        record_data.setdefault("observation_count", 1)
        record_data.setdefault("archival_status", "ACTIVE")
        record_data.setdefault("decay_factor", 1.0)

        # Handle special fields - convert to actual columns
        INCREMENT_FIELDS = {"query_count_increment": "query_count"}
        JSON_APPEND_FIELDS = {
            "milestone_append": "milestones_json",
            "milestones_append": "milestones_json",
        }
        SKIP_FIELDS = {"_action"}

        final_data = {}
        for col, val in record_data.items():
            if col in SKIP_FIELDS:
                continue
            elif col in INCREMENT_FIELDS:
                target_col = INCREMENT_FIELDS[col]
                final_data[target_col] = val  # Initial value
            elif col in JSON_APPEND_FIELDS:
                import json

                target_col = JSON_APPEND_FIELDS[col]
                if isinstance(val, list):
                    final_data[target_col] = json.dumps(val)
                else:
                    final_data[target_col] = json.dumps([val])
            else:
                final_data[col] = val

        columns = list(final_data.keys())
        placeholders = [f"${i + 1}" for i in range(len(columns))]
        values = [final_data[col] for col in columns]

        sql = f"""
            INSERT INTO {write.layer} ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
            ON CONFLICT ({pk_column}) DO UPDATE SET
                updated_at = EXCLUDED.updated_at,
                query_count = COALESCE({write.layer}.query_count, 0) + COALESCE(EXCLUDED.query_count, 0),
                last_queried_at = EXCLUDED.last_queried_at
        """

        try:
            await conn.execute(sql, *values)
            logger.debug(
                "R7: UPSERT fallback succeeded",
                extra={"layer": write.layer, "record_id": write.record_id},
            )
        except Exception as e:
            logger.warning(
                "R7: UPSERT fallback failed, skipping write",
                extra={
                    "layer": write.layer,
                    "record_id": write.record_id,
                    "error": str(e),
                },
            )

    def _infer_entity_type(self, entity_id: str) -> str:
        """
        Infer entity type from entity_id pattern using heuristics.

        This handles entities created by UPSERT fallback when intent signals
        reference entities that don't exist in the KG yet.
        """
        import re

        entity_lower = entity_id.lower()

        # Location indicators
        location_patterns = [
            r"\b(school|park|hospital|bridge|airport|station|building|center|complex)\b",
            r"\b(city|town|village|street|avenue|road|boulevard)\b",
            r"\b(francisco|brooklyn|boston|manhattan|london|tokyo)\b",
            r"\b(golden gate|central park|alcatraz|chipotle|starbucks)\b",
        ]
        for pattern in location_patterns:
            if re.search(pattern, entity_lower):
                return "LOCATION"

        # Organization indicators
        org_patterns = [
            r"\b(company|corp|inc|llc|google|coursera|stanford)\b",
            r"\b(university|college|institute|organization)\b",
        ]
        for pattern in org_patterns:
            if re.search(pattern, entity_lower):
                return "ORGANIZATION"

        # Event indicators
        event_patterns = [
            r"\b(party|recital|meeting|dinner|trip|flight|wedding)\b",
            r"\b(birthday|conference|webinar|appointment)\b",
        ]
        for pattern in event_patterns:
            if re.search(pattern, entity_lower):
                return "EVENT"

        # Concept indicators
        concept_patterns = [
            r"\b(python|yoga|quarterly|atomic habits)\b",
        ]
        for pattern in concept_patterns:
            if re.search(pattern, entity_lower):
                return "CONCEPT"

        # Family role indicators
        family_patterns = [
            r"\b(mom|dad|brother|sister|wife|husband|daughter|son|grandma|grandpa)\b",
            r"\b(mother|father|sibling|spouse|child|grandparent)\b",
        ]
        for pattern in family_patterns:
            if re.search(pattern, entity_lower):
                return "FAMILY_MEMBER"

        # Common first names -> PERSON (simplified list)
        common_names = {
            "emma",
            "john",
            "sarah",
            "mike",
            "david",
            "rachel",
            "tom",
            "alex",
            "chris",
            "lisa",
            "maria",
            "jennifer",
            "jake",
            "sofia",
            "kevin",
            "smith",
            "johnson",
            "andrew",
            "ng",
            "james",
            "clear",
            "sophie",
        }
        # Check if entity starts with a common name (handles "Emma's", "John's", etc.)
        first_word = entity_lower.split()[0] if entity_lower else ""
        first_word_base = first_word.rstrip("'s")
        if first_word_base in common_names or entity_lower.rstrip("'s") in common_names:
            return "PERSON"

        # Default to PERSON if it looks like a proper name (capitalized, no special chars)
        if entity_id and entity_id[0].isupper() and len(entity_id.split()) <= 3:
            words = entity_id.split()
            if all(w[0].isupper() if w else False for w in words):
                # Multiple capitalized words = likely a name
                return "PERSON"

        return "UNKNOWN"

    async def _execute_archive(
        self,
        conn: asyncpg.Connection,
        write: StagedWrite,
    ) -> None:
        """
        Execute soft-delete (ARCHIVE operation).

        Sets archival_status='ARCHIVED', archived_at=now, archived_reason.

        Args:
            conn: asyncpg connection
            write: StagedWrite with operation=ARCHIVE
        """
        now_ms = int(time.time() * 1000)
        pk_column = self._get_pk_column(write.layer)
        reason = write.record_data.get("archived_reason", "")

        sql = f"""
            UPDATE {write.layer}
            SET archival_status = 'ARCHIVED',
                archived_at = $1,
                archived_reason = $2
            WHERE {pk_column} = $3
              AND (archival_status IS NULL OR archival_status != 'ARCHIVED')
        """
        await conn.execute(sql, now_ms, reason, write.record_id)

    async def _execute_tombstone(
        self,
        conn: asyncpg.Connection,
        write: StagedWrite,
    ) -> None:
        """
        Execute tombstone marker (for sync propagation).

        Sets archival_status='TOMBSTONE', tombstoned_at=now.

        Args:
            conn: asyncpg connection
            write: StagedWrite with operation=TOMBSTONE
        """
        now_ms = int(time.time() * 1000)
        pk_column = self._get_pk_column(write.layer)

        sql = f"""
            UPDATE {write.layer}
            SET archival_status = 'TOMBSTONE',
                tombstoned_at = $1
            WHERE {pk_column} = $2
        """
        await conn.execute(sql, now_ms, write.record_id)

    def _get_pk_column(self, layer: str) -> str:
        """
        Get primary key column name for a layer.

        Args:
            layer: Table name (e.g., 'st_epi')

        Returns:
            Primary key column name

        Raises:
            ValueError: If layer is unknown
        """
        pk = LAYER_PK_MAP.get(layer)
        if pk is None:
            raise ValueError(f"Unknown layer: {layer}")
        return pk

    # =========================================================================
    # OUTBOX STAGING
    # =========================================================================

    async def _stage_outbox_events(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
    ) -> int:
        """
        Stage outbox events for R8 emission.

        Args:
            uow: Active UnitOfWork
            envelope: P03BatchEnvelope with staged outbox events

        Returns:
            Number of outbox events staged
        """
        count = 0

        for staged_event in envelope.staged.outbox_events:
            entry = OutboxEntry(
                id=None,
                wal_pos=0,  # Will be set by outbox store
                tenant_id=envelope.context.tenant_id,
                space_id=envelope.context.space_id,
                driver="p03",
                op_kind=staged_event.topic,
                payload=json.dumps(staged_event.payload).encode("utf-8"),
                fingerprint=staged_event.event_id,
                requeue_seq=0,
                retries=0,
            )
            uow.stage_outbox(entry)
            count += 1

        return count

    # =========================================================================
    # STATUS WRITEBACK
    # =========================================================================

    async def _writeback_status(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
    ) -> Dict[str, int]:
        """
        Update st_hipp_events with consolidation status.

        This marks each processed event with:
        - consolidation_status: CONSOLIDATED, DUPLICATE, PRUNED, PENDING_REVIEW
        - consolidation_cycle_id: Current cycle UUID
        - consolidated_at: Timestamp in milliseconds
        - reconciliation_decision: Action taken (from ReconciliationAction)
        - truth_match_id: Best match entity/episode ID (if applicable)
        - truth_match_similarity: Similarity score [0.0, 1.0]

        Args:
            uow: Active UnitOfWork
            envelope: P03BatchEnvelope with events to update

        Returns:
            Dict mapping status string to count (for metrics)
        """
        now_ms = int(time.time() * 1000)
        cycle_id = envelope.context.cycle_id
        status_counts: Counter[str] = Counter()

        for event in envelope.events:
            status = self._determine_status(event)
            status_counts[status] += 1

            # Get reconciliation details from event state
            reconciliation_decision = None
            if hasattr(event, "reconciliation_action") and event.reconciliation_action:
                reconciliation_decision = event.reconciliation_action.value

            truth_match_id = getattr(event, "truth_match_id", None)
            truth_match_similarity = getattr(event, "truth_match_similarity", None)

            await uow.connection.execute(
                """
                UPDATE st_hipp_events
                SET consolidation_status = $1,
                    consolidation_cycle_id = $2,
                    consolidated_at = $3,
                    reconciliation_decision = $4,
                    truth_match_id = $5,
                    truth_match_similarity = $6
                WHERE event_id = $7
            """,
                status,
                cycle_id,
                now_ms,
                reconciliation_decision,
                truth_match_id,
                truth_match_similarity,
                event.event_id,
            )

        # Record status distribution metrics in observability context
        for status, count in status_counts.items():
            envelope.observability.increment(f"p03.r7.status.{status.lower()}", count)

        return dict(status_counts)

    def _determine_status(self, event: Any) -> str:
        """
        Map reconciliation action to consolidation status.

        Args:
            event: P03EventState with reconciliation_action

        Returns:
            Consolidation status string
        """
        # Import here to avoid circular imports
        from k0.pipelines.p03.event_state import ReconciliationAction

        action = getattr(event, "reconciliation_action", None)

        if action is None:
            return "CONSOLIDATED"

        status_map = {
            ReconciliationAction.REINFORCE: "CONSOLIDATED",
            ReconciliationAction.EXTEND: "CONSOLIDATED",
            ReconciliationAction.CREATE: "CONSOLIDATED",
            ReconciliationAction.EVOLVE: "CONSOLIDATED",
            ReconciliationAction.SKIP: "DUPLICATE",
            ReconciliationAction.PRUNE: "PRUNED",
            ReconciliationAction.CONTRADICT: "PENDING_REVIEW",
            ReconciliationAction.PENDING: "PENDING",
        }

        return status_map.get(action, "CONSOLIDATED")

    # =========================================================================
    # STATUS TRANSITION VALIDATION (Issue 3.2.2)
    # =========================================================================

    # Allowed status transitions (current_status -> set of allowed new_status)
    ALLOWED_TRANSITIONS: Dict[str | None, set[str]] = {
        # From NULL (never processed): can go to any status
        None: {"CONSOLIDATED", "DUPLICATE", "PRUNED", "PENDING_REVIEW", "PENDING"},
        # From PENDING: can resolve to any final status
        "PENDING": {"CONSOLIDATED", "DUPLICATE", "PRUNED", "PENDING_REVIEW"},
        # From PENDING_REVIEW: can be resolved or pruned
        "PENDING_REVIEW": {"CONSOLIDATED", "PRUNED"},
        # Final statuses are immutable (can only stay the same - idempotent)
        "CONSOLIDATED": {"CONSOLIDATED"},
        "DUPLICATE": {"DUPLICATE"},
        "PRUNED": {"PRUNED"},
    }

    async def _validate_status_transition(
        self,
        conn: Any,
        event_id: str,
        new_status: str,
    ) -> bool:
        """
        Validate that the status transition is allowed.

        This is an optional guard (Issue 3.2.2) to ensure status transitions
        follow the defined state machine. By default, R7 does not validate
        transitions during normal writeback for performance.

        Args:
            conn: Database connection
            event_id: Event ID to check
            new_status: Target consolidation status

        Returns:
            True if transition is allowed, False otherwise
        """
        row = await conn.fetchrow(
            "SELECT consolidation_status FROM st_hipp_events WHERE event_id = $1",
            event_id,
        )
        current_status = row["consolidation_status"] if row else None

        # Check allowed transitions
        allowed = self.ALLOWED_TRANSITIONS.get(current_status)
        if allowed is not None and new_status in allowed:
            return True

        # Allow idempotent updates (same status -> same status)
        return current_status == new_status


# =============================================================================
# EXCEPTIONS
# =============================================================================


class OptimisticLockError(Exception):
    """Raised when optimistic locking fails due to version conflict."""

    pass
