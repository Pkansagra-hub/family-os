"""
EventEmitter — Issue 5.2.11

Emits all consolidation outcome events via outbox pattern.
Handles completion, pattern, truth, memory, and insight events.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.11 — R8 bus event emission)
    - M8_EXECUTION.md (Issue 8.1.13 — R5 insight event emission)
    - Dossier §4.9.1 (Bus Event Emission)
    - Dossier Appendix G.5 (R8 Metrics)

Event Topics:
    - p03.consolidation.complete.v1: Every cycle end
    - p03.pattern.detected.v1: New semantic pattern
    - p03.truth.reinforced.v1: Existing truth reinforced
    - p03.truth.created.v1: New truth record
    - p03.truth.evolved.v1: Truth evolved (new version)
    - p03.memory.pruned.v1: Memory archived/tombstoned
    - p03.insight.generated.v1: R5 insight generated (Issue 8.1.13)

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from k0.storage.outbox import OutboxEntry

if TYPE_CHECKING:
    from k0.modules.consolidation.staging.r6_output import ReconciliationSummary
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.phase_outputs import Insight  # Issue 8.1.13
    from k0.uow.unit_of_work import UnitOfWork


logger = logging.getLogger(__name__)


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


# =============================================================================
# EVENT TOPICS ENUM (Dossier §4.9.1)
# =============================================================================


class EventTopic(Enum):
    """P03 event topics per dossier §4.9.1."""

    CONSOLIDATION_COMPLETE = "p03.consolidation.complete.v1"
    PATTERN_DETECTED = "p03.pattern.detected.v1"
    TRUTH_REINFORCED = "p03.truth.reinforced.v1"
    TRUTH_CREATED = "p03.truth.created.v1"
    TRUTH_EVOLVED = "p03.truth.evolved.v1"
    MEMORY_PRUNED = "p03.memory.pruned.v1"
    # Issue 8.1.13: R5 insight event topic
    INSIGHT_GENERATED = "p03.insight.generated.v1"


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class CircuitBreakerConfig:
    """
    Circuit breaker for bus unavailability.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        reset_timeout_ms: Time (ms) before attempting to close circuit
        queue_on_failure: Whether to queue events on bus outage
    """

    failure_threshold: int = 5
    reset_timeout_ms: int = 60000  # 1 minute
    queue_on_failure: bool = True


# =============================================================================
# EMIT RESULT
# =============================================================================


@dataclass
class EmitResult:
    """
    Result of event emission.

    Attributes:
        total_emitted: Total events successfully staged
        by_topic: Count per event topic
        failed: List of failed fingerprints
        duration_ms: Time spent emitting (MILLISECONDS)
    """

    total_emitted: int = 0
    by_topic: Dict[str, int] = field(default_factory=dict)
    failed: List[str] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def success(self) -> bool:
        """True if no failures occurred."""
        return len(self.failed) == 0


# =============================================================================
# EVENT EMITTER
# =============================================================================


class EventEmitter:
    """
    Emits all consolidation outcome events via outbox pattern.

    Responsibilities:
        1. Build payloads for all event types
        2. Stage events to outbox within UoW
        3. Apply idempotency keys (fingerprints) to prevent duplicates
        4. Circuit breaker for bus unavailability

    Event Types:
        - CONSOLIDATION_COMPLETE: Always emitted at cycle end
        - PATTERN_DETECTED: Emitted per CREATE on st_sem
        - TRUTH_REINFORCED: Emitted per REINFORCE action
        - TRUTH_CREATED: Emitted per CREATE on non-st_sem layers
        - TRUTH_EVOLVED: Emitted per EVOLVE action
        - MEMORY_PRUNED: Emitted per PRUNE action

    Thread Safety:
        Not thread-safe. Use one instance per async context.

    Usage:
        emitter = EventEmitter()
        result = await emitter.emit_all(uow, envelope, summary)
    """

    def __init__(self, circuit_config: Optional[CircuitBreakerConfig] = None):
        """
        Initialize event emitter.

        Args:
            circuit_config: Optional circuit breaker configuration
        """
        self._circuit_config = circuit_config or CircuitBreakerConfig()
        self._failures = 0
        self._last_failure_ms = 0

    async def emit_all(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        summary: ReconciliationSummary,
    ) -> EmitResult:
        """
        Emit all events for a consolidation cycle.

        Emits:
            1. Completion event (always)
            2. Action-based events (from summary.action_breakdown)

        Args:
            uow: Active UnitOfWork
            envelope: Completed P03BatchEnvelope
            summary: ReconciliationSummary from R6

        Returns:
            EmitResult with counts per topic
        """
        start_ms = _now_ms()
        result = EmitResult()

        # 1. Completion event (always emitted)
        await self._emit_completion(uow, envelope, summary, result)

        # 2. Action-based events (aggregate from action_breakdown)
        await self._emit_action_events(uow, envelope, summary, result)

        result.duration_ms = _now_ms() - start_ms

        logger.info(
            "EventEmitter: emission complete",
            extra={
                "cycle_id": envelope.context.cycle_id,
                "total_emitted": result.total_emitted,
                "failed_count": len(result.failed),
                "duration_ms": result.duration_ms,
            },
        )

        return result

    async def emit_completion(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        summary: ReconciliationSummary,
    ) -> EmitResult:
        """
        Emit only the completion event.

        Useful for partial emission or testing.

        Args:
            uow: Active UnitOfWork
            envelope: Completed P03BatchEnvelope
            summary: ReconciliationSummary from R6

        Returns:
            EmitResult with completion event only
        """
        result = EmitResult()
        await self._emit_completion(uow, envelope, summary, result)
        return result

    async def _emit_completion(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        summary: ReconciliationSummary,
        result: EmitResult,
    ) -> None:
        """Emit p03.consolidation.complete.v1."""
        # Build action breakdown dict from tuple
        action_breakdown = dict(summary.action_breakdown) if summary.action_breakdown else {}
        layer_write_counts = dict(summary.layer_write_counts) if summary.layer_write_counts else {}

        payload = {
            "cycle_id": envelope.context.cycle_id,
            "tenant_id": envelope.context.tenant_id,
            "space_id": envelope.context.space_id,
            "status": self._determine_status(envelope),
            "summary": {
                "total_events": summary.total_events,
                "consolidated_count": summary.consolidated_count,
                "duplicate_count": summary.duplicate_count,
                "pruned_count": summary.pruned_count,
                "pending_review_count": summary.pending_review_count,
                "action_breakdown": action_breakdown,
                "layer_write_counts": layer_write_counts,
                "kg_entity_count": summary.kg_entity_count,
                "kg_edge_count": summary.kg_edge_count,
                "gap_count": summary.gap_count,
            },
            "duration_ms": summary.cycle_duration_ms,
            "completed_at": self._iso_now(),
        }

        await self._stage_event(
            uow=uow,
            topic=EventTopic.CONSOLIDATION_COMPLETE,
            payload=payload,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            fingerprint=f"complete:{envelope.context.cycle_id}",
            result=result,
        )

    async def _emit_action_events(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        summary: ReconciliationSummary,
        result: EmitResult,
    ) -> None:
        """
        Emit aggregate events based on action breakdown.

        Since ReconciliationSummary only has counts (not individual decisions),
        we emit aggregate events per action type.
        """
        action_breakdown = dict(summary.action_breakdown) if summary.action_breakdown else {}

        # REINFORCE → truth.reinforced (aggregate)
        reinforce_count = action_breakdown.get("REINFORCE", 0)
        if reinforce_count > 0:
            await self._emit_truth_reinforced_aggregate(uow, envelope, reinforce_count, result)

        # CREATE → truth.created OR pattern.detected (based on layer_write_counts)
        create_count = action_breakdown.get("CREATE", 0)
        if create_count > 0:
            await self._emit_truth_created_aggregate(uow, envelope, summary, create_count, result)

        # EVOLVE → truth.evolved (aggregate)
        evolve_count = action_breakdown.get("EVOLVE", 0)
        if evolve_count > 0:
            await self._emit_truth_evolved_aggregate(uow, envelope, evolve_count, result)

        # PRUNE → memory.pruned (aggregate)
        prune_count = action_breakdown.get("PRUNE", 0)
        if prune_count > 0:
            await self._emit_memory_pruned_aggregate(uow, envelope, prune_count, result)

    async def _emit_truth_reinforced_aggregate(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        count: int,
        result: EmitResult,
    ) -> None:
        """Emit aggregate p03.truth.reinforced.v1."""
        payload = {
            "tenant_id": envelope.context.tenant_id,
            "space_id": envelope.context.space_id,
            "cycle_id": envelope.context.cycle_id,
            "count": count,
            "reinforced_at": self._iso_now(),
        }

        await self._stage_event(
            uow=uow,
            topic=EventTopic.TRUTH_REINFORCED,
            payload=payload,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            fingerprint=f"reinforce_agg:{envelope.context.cycle_id}",
            result=result,
        )

    async def _emit_truth_created_aggregate(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        summary: ReconciliationSummary,
        count: int,
        result: EmitResult,
    ) -> None:
        """Emit aggregate p03.truth.created.v1 and pattern.detected.v1."""
        layer_write_counts = dict(summary.layer_write_counts) if summary.layer_write_counts else {}

        # Check for semantic layer creates (patterns)
        st_sem_creates = layer_write_counts.get("st_sem", 0)
        if st_sem_creates > 0:
            pattern_payload = {
                "tenant_id": envelope.context.tenant_id,
                "space_id": envelope.context.space_id,
                "cycle_id": envelope.context.cycle_id,
                "count": st_sem_creates,
                "detected_at": self._iso_now(),
            }
            await self._stage_event(
                uow=uow,
                topic=EventTopic.PATTERN_DETECTED,
                payload=pattern_payload,
                tenant_id=envelope.context.tenant_id,
                space_id=envelope.context.space_id,
                fingerprint=f"pattern_agg:{envelope.context.cycle_id}",
                result=result,
            )

        # Non-semantic creates (truth)
        non_sem_creates = count - st_sem_creates
        if non_sem_creates > 0:
            truth_payload = {
                "tenant_id": envelope.context.tenant_id,
                "space_id": envelope.context.space_id,
                "cycle_id": envelope.context.cycle_id,
                "count": non_sem_creates,
                "created_at": self._iso_now(),
            }
            await self._stage_event(
                uow=uow,
                topic=EventTopic.TRUTH_CREATED,
                payload=truth_payload,
                tenant_id=envelope.context.tenant_id,
                space_id=envelope.context.space_id,
                fingerprint=f"create_agg:{envelope.context.cycle_id}",
                result=result,
            )

    async def _emit_truth_evolved_aggregate(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        count: int,
        result: EmitResult,
    ) -> None:
        """Emit aggregate p03.truth.evolved.v1."""
        payload = {
            "tenant_id": envelope.context.tenant_id,
            "space_id": envelope.context.space_id,
            "cycle_id": envelope.context.cycle_id,
            "count": count,
            "evolved_at": self._iso_now(),
        }

        await self._stage_event(
            uow=uow,
            topic=EventTopic.TRUTH_EVOLVED,
            payload=payload,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            fingerprint=f"evolve_agg:{envelope.context.cycle_id}",
            result=result,
        )

    async def _emit_memory_pruned_aggregate(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        count: int,
        result: EmitResult,
    ) -> None:
        """Emit aggregate p03.memory.pruned.v1."""
        payload = {
            "tenant_id": envelope.context.tenant_id,
            "space_id": envelope.context.space_id,
            "cycle_id": envelope.context.cycle_id,
            "count": count,
            "pruned_at": self._iso_now(),
        }

        await self._stage_event(
            uow=uow,
            topic=EventTopic.MEMORY_PRUNED,
            payload=payload,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            fingerprint=f"prune_agg:{envelope.context.cycle_id}",
            result=result,
        )

    async def emit_insight_events(
        self,
        uow: UnitOfWork,
        envelope: P03BatchEnvelope,
        insights: List[Insight],
    ) -> EmitResult:
        """
        Emit p03.insight.generated.v1 events for R5 insights.

        Issue 8.1.13: Emits insight events via outbox with deterministic
        idempotency keys per A.0.5 invariant.

        Args:
            uow: Active UnitOfWork
            envelope: P03BatchEnvelope with cycle context
            insights: List of insights from R5 DreamExplorer

        Returns:
            EmitResult with counts and any failures
        """
        result = EmitResult()

        for insight in insights:
            # Build payload matching p03_insight_generated.json schema
            payload = {
                "tenant_id": envelope.context.tenant_id,
                "space_id": envelope.context.space_id,
                "cycle_id": envelope.context.cycle_id,
                "insight_id": insight.insight_id,
                "insight_type": insight.insight_type,
                "concept_a_id": insight.concept_a_id,
                "concept_b_id": insight.concept_b_id,
                "pmi_score": insight.pmi_score,
                "novelty_score": insight.novelty_score,
                "relevance_score": insight.relevance_score,
                "confidence": insight.relevance_score,
                "description": insight.natural_language,
                "supporting_evidence": insight.evidence_ids,
                "generated_at": _now_ms(),
            }

            # Issue 8.1.13: Deterministic idempotency key per A.0.5 invariant
            # Pattern: {cycle_id}:insight:{insight_id}
            fingerprint = f"{envelope.context.cycle_id}:insight:{insight.insight_id}"

            await self._stage_event(
                uow=uow,
                topic=EventTopic.INSIGHT_GENERATED,
                payload=payload,
                tenant_id=envelope.context.tenant_id,
                space_id=envelope.context.space_id,
                fingerprint=fingerprint,
                result=result,
            )

        return result

    async def _stage_event(
        self,
        uow: UnitOfWork,
        topic: EventTopic,
        payload: Dict[str, Any],
        tenant_id: str,
        space_id: str,
        fingerprint: str,
        result: EmitResult,
    ) -> None:
        """Stage event to outbox with circuit breaker."""
        if self._is_circuit_open():
            result.failed.append(fingerprint)
            logger.warning(
                "EventEmitter: circuit open, skipping event",
                extra={"fingerprint": fingerprint, "topic": topic.value},
            )
            return

        try:
            entry = OutboxEntry(
                id=None,
                wal_pos=0,
                tenant_id=tenant_id,
                space_id=space_id,
                driver="p03",
                op_kind=topic.value,
                payload=json.dumps(payload).encode("utf-8"),
                fingerprint=fingerprint,
                requeue_seq=0,
                retries=0,
            )
            uow.stage_outbox(entry)

            result.total_emitted += 1
            result.by_topic[topic.value] = result.by_topic.get(topic.value, 0) + 1
            self._failures = 0  # Reset on success

        except Exception as e:
            self._failures += 1
            self._last_failure_ms = _now_ms()
            result.failed.append(fingerprint)
            logger.error(
                "EventEmitter: failed to stage event",
                extra={"fingerprint": fingerprint, "error": str(e)},
            )

    def _is_circuit_open(self) -> bool:
        """Check circuit breaker state."""
        if self._failures < self._circuit_config.failure_threshold:
            return False

        now_ms = _now_ms()
        if now_ms - self._last_failure_ms > self._circuit_config.reset_timeout_ms:
            self._failures = 0
            return False

        return True

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker."""
        self._failures = 0
        self._last_failure_ms = 0

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

        for status in envelope.phase_statuses.values():
            if status == P03PhaseStatus.FAIL:
                has_failure = True
            elif status == P03PhaseStatus.DONE:
                has_success = True

        if has_failure and not has_success:
            return "FAILED"
        elif has_failure:
            return "PARTIAL"
        return "SUCCESS"

    @staticmethod
    def _iso_now() -> str:
        """Return current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()


# =============================================================================
# FACTORY
# =============================================================================


def create_event_emitter(
    circuit_config: Optional[CircuitBreakerConfig] = None,
) -> EventEmitter:
    """
    Factory function for EventEmitter.

    Args:
        circuit_config: Optional circuit breaker configuration

    Returns:
        Configured EventEmitter instance
    """
    return EventEmitter(circuit_config=circuit_config)
