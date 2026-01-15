"""
GapEmitterModule — Issue 5.2.12

Extended gap emitter for P06 Active Learning integration.
Handles gap deduplication, capping, priority ordering, and queue persistence.

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.12 — R8 gap emission for P06)
    - Dossier §9.3.1 (Gap Emission: p03.gap.detected.v1)
    - Dossier §7.4.8 (M25 — GapDetector)
    - Dossier §6.11 (st_learning_queue Schema)

Gap Types (Dossier §6.11):
    - CONTRADICTION: Conflicting information (priority 100)
    - AMBIGUOUS_ENTITY: Multiple candidates match (priority 80)
    - STRUCTURAL_HOLE: Missing bridge between clusters (priority 70)
    - CONCEPT_DRIFT: Entity meaning shifted (priority 60)
    - LOW_CONFIDENCE_EDGE: KG edge below threshold (priority 50)
    - STALE_ANCHOR: Anchor needs refresh (priority 40)
    - MISSING_ATTRIBUTE: Expected attribute missing (priority 30)

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from k0.pipelines.p03.gap_emitter import (
    GAP_PRIORITY_MAP,
    GapType,
    P03GapEmitter,
    P03GapEmitterConfig,
)
from k0.storage.outbox import OutboxEntry

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.phase_outputs import GapCandidate
    from k0.uow.unit_of_work import UnitOfWork


logger = logging.getLogger(__name__)


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


# Maximum gaps per cycle to avoid P06 overload
MAX_GAPS_PER_CYCLE = 50

# Default TTL for gaps (7 days in hours)
DEFAULT_TTL_HOURS = 168

# Gap event topic
GAP_TOPIC = "p03.gap.detected.v1"


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class GapEmitterConfig:
    """
    Extended configuration for gap emission.

    Attributes:
        topic: Event bus topic for gap events
        max_gaps_per_cycle: Maximum gaps to emit per cycle
        ttl_hours: Time-to-live for gaps in hours
        deduplicate: Whether to deduplicate within cycle
        dedup_window_ms: Deduplication window in milliseconds
        emit_to_outbox: Whether to stage events to outbox
        persist_to_queue: Whether to persist to st_learning_queue
    """

    topic: str = GAP_TOPIC
    max_gaps_per_cycle: int = MAX_GAPS_PER_CYCLE
    ttl_hours: int = DEFAULT_TTL_HOURS
    deduplicate: bool = True
    dedup_window_ms: int = 3600000  # 1 hour
    emit_to_outbox: bool = True
    persist_to_queue: bool = True


# =============================================================================
# EMIT STATISTICS
# =============================================================================


@dataclass
class GapEmitStats:
    """
    Statistics from gap emission.

    Attributes:
        total_received: Total gaps received for emission
        emitted: Gaps successfully emitted
        deduplicated: Gaps skipped due to deduplication
        capped: Gaps skipped due to max cap
        by_type: Count per gap type
        by_priority: Count per priority level
        duration_ms: Time spent emitting (MILLISECONDS)
    """

    total_received: int = 0
    emitted: int = 0
    deduplicated: int = 0
    capped: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    by_priority: Dict[int, int] = field(default_factory=dict)
    duration_ms: int = 0

    @property
    def skipped(self) -> int:
        """Total gaps not emitted."""
        return self.deduplicated + self.capped


# =============================================================================
# QUESTION TEMPLATES
# =============================================================================


# Question templates for P06 prompt generation
QUESTION_TEMPLATES: Dict[str, str] = {
    "AMBIGUOUS_ENTITY": "Which of these best matches '{entity}'?",
    "LOW_CONFIDENCE_EDGE": "Is it true that '{source}' {relation} '{target}'?",
    "MISSING_ATTRIBUTE": "What is the {attribute} of '{entity}'?",
    "CONTRADICTION": "Which statement is correct: A) {claim_a} or B) {claim_b}?",
    "CONCEPT_DRIFT": "Has the meaning of '{entity}' changed recently?",
    "STRUCTURAL_HOLE": "How are '{entity_a}' and '{entity_b}' related?",
    "STALE_ANCHOR": "Is '{entity}' still valid/current?",
}


# =============================================================================
# GAP EMITTER MODULE
# =============================================================================


class GapEmitterModule:
    """
    Extended gap emitter for P06 Active Learning integration.

    Extends P03GapEmitter with:
        1. Gap cap per cycle (prevent P06 overload)
        2. Priority-based ordering (high priority first)
        3. Question template generation hints
        4. TTL configuration per gap type
        5. Metrics for gap distribution

    Workflow:
        1. Sort gaps by priority (highest first)
        2. Deduplicate within cycle (same gap_type + entity)
        3. Cap to max_gaps_per_cycle
        4. Persist to st_learning_queue
        5. Stage to outbox for P06 notification

    Thread Safety:
        Not thread-safe. Use one instance per async context.

    Usage:
        emitter = GapEmitterModule()
        stats = await emitter.emit(uow, gaps, envelope)
        emitter.reset_cycle()  # Call at start of each cycle
    """

    def __init__(self, config: Optional[GapEmitterConfig] = None):
        """
        Initialize gap emitter module.

        Args:
            config: Optional configuration (uses defaults if None)
        """
        self._config = config or GapEmitterConfig()
        self._base_emitter = P03GapEmitter(
            P03GapEmitterConfig(
                topic=self._config.topic,
                deduplicate=self._config.deduplicate,
                dedup_window_ms=self._config.dedup_window_ms,
            )
        )
        self._seen_this_cycle: Set[str] = set()

    @property
    def config(self) -> GapEmitterConfig:
        """Current configuration."""
        return self._config

    async def emit(
        self,
        uow: UnitOfWork,
        gaps: List[GapCandidate],
        envelope: P03BatchEnvelope,
    ) -> GapEmitStats:
        """
        Emit gaps with deduplication, capping, and priority ordering.

        Args:
            uow: Active UnitOfWork
            gaps: List of GapCandidate from R4
            envelope: P03BatchEnvelope for context

        Returns:
            GapEmitStats with emission statistics
        """
        start_ms = _now_ms()
        stats = GapEmitStats(total_received=len(gaps))

        if not gaps:
            return stats

        # 1. Sort by priority (highest first)
        sorted_gaps = self._sort_by_priority(gaps)

        # 2. Deduplicate within cycle
        unique_gaps = self._deduplicate(sorted_gaps, stats)

        # 3. Cap to max per cycle
        capped_gaps = unique_gaps[: self._config.max_gaps_per_cycle]
        stats.capped = len(unique_gaps) - len(capped_gaps)

        # 4. Emit each gap
        for gap in capped_gaps:
            await self._emit_gap(uow, gap, envelope, stats)

        stats.duration_ms = _now_ms() - start_ms

        logger.info(
            "GapEmitterModule: emission complete",
            extra={
                "cycle_id": envelope.context.cycle_id,
                "total_received": stats.total_received,
                "emitted": stats.emitted,
                "deduplicated": stats.deduplicated,
                "capped": stats.capped,
                "duration_ms": stats.duration_ms,
            },
        )

        return stats

    def _sort_by_priority(self, gaps: List[GapCandidate]) -> List[GapCandidate]:
        """Sort gaps by priority (highest first)."""

        def get_priority(gap: GapCandidate) -> int:
            gap_type = GapType.from_string(gap.gap_type)
            return GAP_PRIORITY_MAP.get(gap_type, 50)

        return sorted(gaps, key=get_priority, reverse=True)

    def _deduplicate(
        self,
        gaps: List[GapCandidate],
        stats: GapEmitStats,
    ) -> List[GapCandidate]:
        """Deduplicate gaps within cycle."""
        unique: List[GapCandidate] = []

        for gap in gaps:
            dedup_key = self._make_dedup_key(gap)

            if dedup_key in self._seen_this_cycle:
                stats.deduplicated += 1
                continue

            self._seen_this_cycle.add(dedup_key)
            unique.append(gap)

        return unique

    def _make_dedup_key(self, gap: GapCandidate) -> str:
        """
        Create deduplication key for gap.

        Deduplicates by gap_type + related_entity_id.
        """
        key_str = f"{gap.gap_type}:{gap.related_entity_id or 'none'}"
        return hashlib.md5(key_str.encode()).hexdigest()

    async def _emit_gap(
        self,
        uow: UnitOfWork,
        gap: GapCandidate,
        envelope: P03BatchEnvelope,
        stats: GapEmitStats,
    ) -> None:
        """Emit single gap to queue and outbox."""
        gap_type = GapType.from_string(gap.gap_type)
        priority = GAP_PRIORITY_MAP.get(gap_type, 50)

        # Track stats
        stats.emitted += 1
        stats.by_type[gap.gap_type] = stats.by_type.get(gap.gap_type, 0) + 1
        stats.by_priority[priority] = stats.by_priority.get(priority, 0) + 1

        # 1. Persist to st_learning_queue
        if self._config.persist_to_queue:
            await self._persist_to_queue(uow, gap, envelope, priority)

        # 2. Stage outbox event for immediate notification
        if self._config.emit_to_outbox:
            await self._stage_outbox_event(uow, gap, envelope, priority)

    async def _persist_to_queue(
        self,
        uow: UnitOfWork,
        gap: GapCandidate,
        envelope: P03BatchEnvelope,
        priority: int,
    ) -> None:
        """
        Insert gap into st_learning_queue for P06 consumption.

        Uses ON CONFLICT DO NOTHING for idempotency.
        """
        now_ms = _now_ms()
        expires_ms = now_ms + (self._config.ttl_hours * 3600 * 1000)

        # Parse context from gap
        try:
            context_dict = json.loads(gap.context_json) if gap.context_json else {}
        except json.JSONDecodeError:
            context_dict = {}

        metadata = {
            "related_entity_id": gap.related_entity_id,
            "entropy_score": gap.entropy_score,
            "candidate_values": gap.candidate_values,
            "original_context": context_dict,
            "question_template": self._get_question_template(gap),
        }

        await uow.connection.execute(
            """
            INSERT INTO st_learning_queue (
                id, tenant_id, space_id, gap_type,
                entity_id, confidence_score, entropy_score,
                context_json, status,
                created_at, expires_at,
                attempts, max_attempts,
                consolidation_cycle_id
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6, $7,
                $8, $9,
                $10, $11,
                $12, $13,
                $14
            ) ON CONFLICT (id) DO NOTHING
            """,
            gap.gap_id,
            envelope.context.tenant_id,
            envelope.context.space_id,
            gap.gap_type,
            gap.related_entity_id,
            1.0 - gap.entropy_score,  # confidence = 1 - entropy
            gap.entropy_score,
            json.dumps(metadata),
            "PENDING",
            now_ms,
            expires_ms,
            0,  # attempts
            3,  # max_attempts
            envelope.context.cycle_id,
        )

    async def _stage_outbox_event(
        self,
        uow: UnitOfWork,
        gap: GapCandidate,
        envelope: P03BatchEnvelope,
        priority: int,
    ) -> None:
        """Stage gap event to outbox for P06 notification."""
        # Parse context from gap
        try:
            context_dict = json.loads(gap.context_json) if gap.context_json else {}
        except json.JSONDecodeError:
            context_dict = {}

        payload = {
            "gap_id": gap.gap_id,
            "tenant_id": envelope.context.tenant_id,
            "space_id": envelope.context.space_id,
            "gap_type": gap.gap_type,
            "importance_score": gap.entropy_score,
            "priority": priority,
            "context": {
                "related_entity_id": gap.related_entity_id,
                "candidate_values": gap.candidate_values,
                "conflicting_truths": context_dict.get("conflicting_truths", []),
                "question_template": self._get_question_template(gap),
            },
            "ttl_hours": self._config.ttl_hours,
            "detected_at": _now_ms(),
        }

        entry = OutboxEntry(
            id=None,
            wal_pos=0,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            driver="p06",  # Target P06 pipeline
            op_kind=self._config.topic,
            payload=json.dumps(payload).encode("utf-8"),
            fingerprint=f"gap:{gap.gap_id}",
            requeue_seq=0,
            retries=0,
        )
        uow.stage_outbox(entry)

    def _get_question_template(self, gap: GapCandidate) -> str:
        """
        Get question template based on gap type.

        Returns a template string that P06 can use to generate
        clarification questions.
        """
        return QUESTION_TEMPLATES.get(gap.gap_type, "Can you clarify this?")

    def reset_cycle(self) -> None:
        """
        Reset per-cycle state.

        Call at start of each consolidation cycle to clear
        deduplication tracking.
        """
        self._seen_this_cycle.clear()


# =============================================================================
# FACTORY
# =============================================================================


def create_gap_emitter(
    config: Optional[GapEmitterConfig] = None,
) -> GapEmitterModule:
    """
    Factory function for GapEmitterModule.

    Args:
        config: Optional configuration

    Returns:
        Configured GapEmitterModule instance
    """
    return GapEmitterModule(config=config)
