"""
R8 Phase — Event Emission & Completion.

M3 Issue 3.1.2: Build Completion Event + Emit via Outbox.
M5 Issue 5.2.W2: Wire to EventEmitter and GapEmitterModule.

This phase completes the P03 cycle:
1. Build completion payload (p03.consolidation.complete.v1)
2. Stage completion event to outbox
3. Persist detected gaps to st_learning_queue
4. Stage gap events (p03.gap.detected.v1) to outbox
5. Commit offset (exactly-once guarantee)
6. Signal outbox drain

References:
    - Dossier 4.9: R8 Event Emission
    - Schema: k0/contracts/schemas/p03_consolidation_complete.json
    - M3 Execution: docs/TEMP_EXECUTION_DOCS/M3_EXECUTION.md Issue 3.1.2
    - M3 Issue 3.2.3: Gap emitter integration
    - M5 Execution: docs/TEMP_EXECUTION_DOCS/M5_EXECUTION.md Issue 5.2.W2
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List

from k0.modules.consolidation.emission.emitter import CircuitBreakerConfig, EventEmitter
from k0.modules.consolidation.emission.gap_emitter import GapEmitterConfig, GapEmitterModule
from k0.pipelines.p03.gap_emitter import P03GapEmitter
from k0.pipelines.p03.observability import P03Error
from k0.pipelines.p03.phase_interface import P03PhaseResult
from k0.pipelines.p03.runner_contract import P03PhaseId
from k0.storage.outbox import OutboxEntry

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.phase_interface import P03RunnerContext
    from k0.pipelines.p03.phase_outputs import GapCandidate
    from k0.uow.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


# =============================================================================
# R8 EVENT EMITTER PHASE
# =============================================================================


class R8EventEmitter:
    """
    R8 Phase: Event Emission & Completion.

    Responsibilities:
        1. Build completion payload (p03.consolidation.complete.v1)
        2. Stage completion event to outbox
        3. Persist detected gaps to st_learning_queue
        4. Stage gap events (p03.gap.detected.v1) to outbox
        5. Commit offset (exactly-once guarantee)
        6. Signal outbox drain

    M5 Wiring (Issue 5.2.W2):
        - EventEmitter emits all 6 event topics (5.2.11)
        - GapEmitterModule handles gap deduplication, capping, priority (5.2.12)
        - Circuit breaker handles bus unavailability
        - Legacy inline methods kept as deprecated fallback

    Event Topics:
        - p03.consolidation.complete.v1: Emitted after every successful cycle
        - p03.pattern.detected.v1: New semantic pattern detected
        - p03.truth.reinforced.v1: Existing truth reinforced
        - p03.truth.created.v1: New truth record created
        - p03.truth.evolved.v1: Truth evolved (new version)
        - p03.memory.pruned.v1: Memory archived/tombstoned
        - p03.gap.detected.v1: Emitted per gap detected in R4

    Idempotency:
        - Completion fingerprint: complete:{cycle_id}
        - Gap fingerprint: gap:{gap_id}
        - Offset commit is idempotent via upsert

    Note:
        R8 errors are recoverable since R7 has already committed truth writes.
        Retry R8 alone without re-running R0-R7.
    """

    PHASE_ID = P03PhaseId.R8_EMIT
    COMPLETION_TOPIC = "p03.consolidation.complete.v1"
    GAP_TOPIC = "p03.gap.detected.v1"

    # M5: Use new emitters instead of inline methods (toggle for rollback)
    # Default to False during rollout to avoid breaking existing tests
    USE_M5_EMITTERS = False

    def __init__(self) -> None:
        """Initialize R8 phase with M5 emitters."""
        # M5: Initialize emitters
        self._event_emitter = EventEmitter(
            circuit_config=CircuitBreakerConfig(
                failure_threshold=5,
                reset_timeout_ms=60000,
            )
        )
        self._gap_emitter = GapEmitterModule(
            config=GapEmitterConfig(
                max_gaps_per_cycle=50,
                ttl_hours=168,  # 7 days
            )
        )

    async def run(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> P03PhaseResult:
        """
        Execute R8 phase.

        Args:
            envelope: P03BatchEnvelope with completed R0-R7 phases
            ctx: Runner context with syscalls, logger, config

        Returns:
            P03PhaseResult indicating success/failure
        """
        start_ms = int(time.time() * 1000)
        cycle_id = envelope.context.cycle_id

        # M5: Reset gap emitter per-cycle state
        self._gap_emitter.reset_cycle()

        logger.info(
            "R8: Starting event emission phase",
            extra={
                "cycle_id": cycle_id,
                "gaps_count": len(envelope.phases.r4_gap_candidates),
                "use_m5_emitters": self.USE_M5_EMITTERS,
            },
        )

        try:
            if self.USE_M5_EMITTERS:
                # M5: Use EventEmitter + GapEmitterModule
                return await self._run_m5(envelope, ctx, start_ms)
            else:
                # Legacy: Use inline methods
                return await self._run_legacy(envelope, ctx, start_ms)

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms

            logger.exception(
                "R8: Event emission phase failed",
                extra={
                    "cycle_id": cycle_id,
                    "duration_ms": duration_ms,
                    "error": str(e),
                },
            )

            return P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=P03Error(
                    error_id=f"r8-{cycle_id}",
                    phase="R8",
                    stage_id="event_emitter",
                    error_type="R8_EMISSION_ERROR",
                    error_message=str(e),
                    recoverable=True,  # R8 can retry after R7 success
                ),
                duration_ms=duration_ms,
                idempotency_key=f"p03:r8:{cycle_id}",
            )

    async def _run_m5(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
        start_ms: int,
    ) -> P03PhaseResult:
        """
        M5: Execute R8 via EventEmitter + GapEmitterModule.

        Args:
            envelope: P03BatchEnvelope with completed R0-R7 phases
            ctx: Runner context with syscalls
            start_ms: Start time in milliseconds

        Returns:
            P03PhaseResult indicating success/failure
        """
        cycle_id = envelope.context.cycle_id

        # Get R6 summary for EventEmitter
        r6_summary = envelope.phases.r6_summary

        async with ctx.syscalls.unit_of_work() as uow:
            # 1. Emit all events via EventEmitter
            emit_result = await self._event_emitter.emit_all(
                uow=uow,
                envelope=envelope,
                summary=r6_summary,
            )

            # 2. Emit gaps via GapEmitterModule
            gap_stats = await self._gap_emitter.emit(
                uow=uow,
                gaps=envelope.phases.r4_gap_candidates,
                envelope=envelope,
            )

            # 3. Commit offset (exactly-once)
            await self._commit_offset(uow, envelope)

            # Commit happens on UoW __aexit__

        # 4. Signal outbox drain (async, non-blocking)
        await self._trigger_outbox_drain(ctx)

        duration_ms = int(time.time() * 1000) - start_ms

        logger.info(
            "R8: Event emission completed (M5 emitters)",
            extra={
                "cycle_id": cycle_id,
                "duration_ms": duration_ms,
                "events_emitted": emit_result.total_emitted,
                "events_by_topic": emit_result.by_topic,
                "gaps_emitted": gap_stats.emitted,
                "gaps_deduplicated": gap_stats.deduplicated,
                "gaps_capped": gap_stats.capped,
            },
        )

        return P03PhaseResult.done(
            phase_id=self.PHASE_ID,
            duration_ms=duration_ms,
            outputs_summary={
                "events_emitted": emit_result.total_emitted,
                "events_by_topic": emit_result.by_topic,
                "gaps_emitted": gap_stats.emitted,
                "gaps_by_type": gap_stats.by_type,
                "gaps_deduplicated": gap_stats.deduplicated,
                "gaps_capped": gap_stats.capped,
            },
            idempotency_key=f"p03:r8:{cycle_id}",
        )

    async def _run_legacy(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
        start_ms: int,
    ) -> P03PhaseResult:
        """
        DEPRECATED: Legacy R8 execution with inline methods.

        Will be removed in M6. Use M5 emitter path instead.

        Args:
            envelope: P03BatchEnvelope with completed R0-R7 phases
            ctx: Runner context with syscalls
            start_ms: Start time in milliseconds

        Returns:
            P03PhaseResult indicating success/failure
        """
        cycle_id = envelope.context.cycle_id

        # 1. Build completion payload from phase outputs
        completion_payload = self._build_completion_payload(envelope)

        async with ctx.syscalls.unit_of_work() as uow:
            # 2. Stage completion event to outbox
            await self._stage_completion_event(uow, envelope, completion_payload)

            # 3. Persist gaps and stage gap events
            gap_count = await self._process_gaps(uow, envelope)

            # 4. Commit offset (exactly-once)
            await self._commit_offset(uow, envelope)

            # Commit happens on UoW __aexit__

        # 5. Signal outbox drain (async, non-blocking)
        await self._trigger_outbox_drain(ctx)

        duration_ms = int(time.time() * 1000) - start_ms

        logger.info(
            "R8: Event emission phase completed (legacy)",
            extra={
                "cycle_id": cycle_id,
                "duration_ms": duration_ms,
                "completion_status": completion_payload["status"],
                "gaps_persisted": gap_count,
            },
        )

        return P03PhaseResult.done(
            phase_id=self.PHASE_ID,
            duration_ms=duration_ms,
            outputs_summary={
                "completion_status": completion_payload["status"],
                "gaps_persisted": gap_count,
                "events_emitted": 1 + gap_count,  # completion + gaps
            },
            idempotency_key=f"p03:r8:{cycle_id}",
        )

    # =========================================================================
    # COMPLETION PAYLOAD BUILDING
    # =========================================================================

    def _build_completion_payload(
        self,
        envelope: P03BatchEnvelope,
    ) -> Dict[str, Any]:
        """
        Build payload matching p03_consolidation_complete.json schema.

        Schema structure:
        {
          "cycle_id": str,
          "tenant_id": str,
          "space_id": str,
          "status": "SUCCESS" | "PARTIAL" | "FAILED",
          "summary": {...},
          "duration_ms": int,
          "completed_at": str (ISO8601),
          "phase_durations": {phase_id: duration_ms},
          "errors": [{"phase": str, "error_type": str, "message": str}]
        }

        Args:
            envelope: Completed P03BatchEnvelope

        Returns:
            Payload dict conforming to schema
        """
        # Determine overall status
        status = self._determine_status(envelope)

        # Calculate totals from R1-R6 outputs
        summary = self._build_summary(envelope)

        # Collect phase durations
        phase_durations = self._collect_phase_durations(envelope)

        # Collect errors
        errors = self._collect_errors(envelope)

        return {
            "cycle_id": envelope.context.cycle_id,
            "tenant_id": envelope.context.tenant_id,
            "space_id": envelope.context.space_id,
            "status": status,
            "summary": summary,
            "duration_ms": self._calculate_total_duration(envelope),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "phase_durations": phase_durations,
            "errors": errors,
        }

    def _determine_status(self, envelope: P03BatchEnvelope) -> str:
        """
        Determine overall cycle status.

        Returns:
            "SUCCESS" - All phases completed without errors
            "PARTIAL" - Some phases had recoverable errors
            "FAILED" - Fatal error occurred
        """
        from k0.pipelines.p03.runner_contract import P03PhaseStatus

        has_failure = False
        has_success = False

        for phase_id, status in envelope.phase_statuses.items():
            if status == P03PhaseStatus.FAIL:
                has_failure = True
            elif status == P03PhaseStatus.DONE:
                has_success = True

        if has_failure and not has_success:
            return "FAILED"
        elif has_failure:
            return "PARTIAL"
        else:
            return "SUCCESS"

    def _build_summary(self, envelope: P03BatchEnvelope) -> Dict[str, Any]:
        """
        Build summary section of completion payload.

        M5 W4: Includes R7 WriteResult statistics when available.
        """
        outputs = envelope.phases

        # M5 W4: Include R7 write results if available
        r7_stats = {}
        if outputs.r7_result is not None:
            r7_stats = {
                "writes_succeeded": outputs.r7_result.total_succeeded,
                "writes_failed": outputs.r7_result.total_failed,
                "layers_touched": list(outputs.r7_result.by_layer.keys()),
                "failed_decision_ids": outputs.r7_result.failed_decision_ids,
            }

        return {
            "events_processed": len(envelope.events),
            "clusters_created": outputs.r2_cluster_count,
            "duplicates_found": len(outputs.r3_dedup_merges),
            "entities_created": len(outputs.r4_new_entities),
            "edges_created": len(outputs.r4_new_edges),
            "gaps_detected": len(outputs.r4_gap_candidates),
            "patterns_updated": len(outputs.r4_updated_entities),
            "salience_changes": getattr(
                outputs.r6_summary,
                "total_processed",
                getattr(outputs.r6_summary, "consolidated_count", 0),
            ),
            # M5 W4: Add R7 write stats
            "truth_writes": r7_stats,
        }

    def _collect_phase_durations(self, envelope: P03BatchEnvelope) -> Dict[str, int]:
        """Collect duration for each completed phase."""
        return envelope.observability.get_all_phase_durations()

    def _collect_errors(self, envelope: P03BatchEnvelope) -> List[Dict[str, str]]:
        """Collect errors from observability context."""
        errors = []
        for error in envelope.observability.errors:
            errors.append(
                {
                    "phase": error.phase,
                    "error_type": error.error_type,
                    "message": error.error_message,
                }
            )
        return errors

    def _calculate_total_duration(self, envelope: P03BatchEnvelope) -> int:
        """Calculate total cycle duration from phase timings."""
        durations = envelope.observability.get_all_phase_durations()
        return sum(durations.values()) if durations else 0

    # =========================================================================
    # COMPLETION EVENT STAGING
    # =========================================================================

    async def _stage_completion_event(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        payload: Dict[str, Any],
    ) -> None:
        """
        Stage completion event to outbox.

        Args:
            uow: Active UnitOfWork
            envelope: P03BatchEnvelope for context
            payload: Completion payload
        """
        entry = OutboxEntry(
            id=None,
            wal_pos=0,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            driver="p03",
            op_kind=self.COMPLETION_TOPIC,
            payload=json.dumps(payload).encode("utf-8"),
            fingerprint=f"complete:{envelope.context.cycle_id}",
            requeue_seq=0,
            retries=0,
        )
        uow.stage_outbox(entry)

    # =========================================================================
    # GAP PROCESSING (Issue 3.2.3)
    # =========================================================================

    async def _process_gaps(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
    ) -> int:
        """
        Persist gaps to st_learning_queue and stage gap events.

        Uses P03GapEmitter (Issue 3.2.3) for:
        - Deduplication within time window
        - Priority calculation by gap type
        - Idempotency via gap_id fingerprint
        - Metrics tracking

        Per dossier 4.9:
        - Gap persisted to st_learning_queue for P06 consumption
        - Gap event staged to outbox for immediate notification

        Args:
            uow: Active UnitOfWork
            envelope: P03BatchEnvelope with R4 gaps

        Returns:
            Number of gaps emitted (may be less than total due to dedup)
        """
        gaps: List[GapCandidate] = envelope.phases.r4_gap_candidates

        if not gaps:
            return 0

        # Use gap emitter for dedup, priority, and metrics
        emitter = P03GapEmitter()
        result = await emitter.emit_gaps(uow, gaps, envelope)

        logger.info(
            "R8: Gaps processed via emitter",
            extra={
                "cycle_id": envelope.context.cycle_id,
                "total_gaps": result.total,
                "emitted": result.emitted,
                "deduplicated": result.deduplicated,
                "by_type": result.by_type,
            },
        )

        return result.emitted

    # =========================================================================
    # LEGACY GAP METHODS (kept for backward compatibility)
    # =========================================================================

    async def _persist_gap_to_queue(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        gap: GapCandidate,
    ) -> None:
        """
        Insert gap into st_learning_queue.

        Schema: queue_id, tenant_id, space_id, gap_type, gap_id,
                source_event_id, gap_metadata, status, created_at

        Args:
            uow: Active UnitOfWork
            envelope: P03BatchEnvelope for context
            gap: GapCandidate to persist
        """
        now_ms = int(time.time() * 1000)

        # Build metadata from gap fields
        metadata = {
            "related_entity_id": gap.related_entity_id,
            "entropy_score": gap.entropy_score,
            "priority": gap.priority,
            "candidate_values": gap.candidate_values,
            "context": gap.context_json,
        }

        await uow.connection.execute(
            """
            INSERT INTO st_learning_queue (
                queue_id, tenant_id, space_id, gap_type, gap_id,
                source_event_id, gap_metadata, status, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (queue_id) DO NOTHING
            """,
            gap.gap_id,
            envelope.context.tenant_id,
            envelope.context.space_id,
            gap.gap_type,
            gap.gap_id,
            gap.related_entity_id,  # Using related entity as source
            json.dumps(metadata),
            "PENDING",
            now_ms,
        )

    async def _stage_gap_event(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        gap: GapCandidate,
    ) -> None:
        """
        Stage gap event to outbox.

        Args:
            uow: Active UnitOfWork
            envelope: P03BatchEnvelope for context
            gap: GapCandidate to emit
        """
        payload = self._build_gap_payload(envelope, gap)
        entry = OutboxEntry(
            id=None,
            wal_pos=0,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            driver="p03",
            op_kind=self.GAP_TOPIC,
            payload=json.dumps(payload).encode("utf-8"),
            fingerprint=f"gap:{gap.gap_id}",
            requeue_seq=0,
            retries=0,
        )
        uow.stage_outbox(entry)

    def _build_gap_payload(
        self,
        envelope: P03BatchEnvelope,
        gap: GapCandidate,
    ) -> Dict[str, Any]:
        """
        Build gap event payload.

        Args:
            envelope: P03BatchEnvelope for context
            gap: GapCandidate

        Returns:
            Gap event payload dict
        """
        return {
            "cycle_id": envelope.context.cycle_id,
            "tenant_id": envelope.context.tenant_id,
            "space_id": envelope.context.space_id,
            "gap_id": gap.gap_id,
            "gap_type": gap.gap_type,
            "related_entity_id": gap.related_entity_id,
            "entropy_score": gap.entropy_score,
            "priority": gap.priority,
            "candidate_values": gap.candidate_values,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

    # =========================================================================
    # OFFSET COMMIT
    # =========================================================================

    async def _commit_offset(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
    ) -> None:
        """
        Commit offset for exactly-once processing.

        The offset marks the high watermark of processed events.
        On failure and restart, processing resumes from this offset.

        Args:
            uow: Active UnitOfWork
            envelope: P03BatchEnvelope with offset info
        """
        from datetime import datetime
        from datetime import timezone as tz

        from k0.storage.offsets import Offset

        # Get the high watermark from context
        # This is the maximum event_id processed in this batch
        if not envelope.events:
            # No events processed
            return

        # Use the max event_id as the new offset
        # Event IDs are ULIDs, so max() gives the latest
        max_event_id = max(e.event_id for e in envelope.events)

        # Convert to integer offset if possible, otherwise use hash
        # For ULID strings, we use the timestamp prefix as offset
        try:
            # ULID first 10 chars are timestamp (base32)
            offset_value = (
                int(max_event_id[:10], 32) if len(max_event_id) >= 10 else hash(max_event_id)
            )
        except ValueError:
            offset_value = hash(max_event_id)

        # Build offset record
        offset_record = Offset(
            subscriber_id="p03",
            topic="p02.hipp_events",
            space_id=envelope.context.space_id,
            tenant_id=envelope.context.tenant_id,
            offset=offset_value,
            updated_ts=datetime.now(tz.utc).isoformat(),
        )

        # Commit via UoW
        await uow.upsert_offset(offset_record)

    # =========================================================================
    # OUTBOX DRAIN SIGNAL
    # =========================================================================

    async def _trigger_outbox_drain(self, ctx: P03RunnerContext) -> None:
        """
        Signal outbox publisher to drain P03 entries.

        This is non-blocking; actual drain happens asynchronously.
        If no dedicated publisher exists, entries will be drained
        by background cron or next publisher tick.

        Future implementations may:
        - Fire signal to bus: ctx.bus.publish("outbox.drain.request", {"driver": "p03"})
        - Direct invoke: ctx.outbox_publisher.drain_batch(driver="p03")

        For now: rely on background publisher (Issue 3.1.3).

        Args:
            ctx: Runner context
        """
        # For now, this is a no-op.
        # The outbox publisher (Issue 3.1.3) will handle draining.
        # This method serves as a hook for future optimization.
        pass
