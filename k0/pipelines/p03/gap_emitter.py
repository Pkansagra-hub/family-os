"""P03 Gap Emitter — Persists and emits detected gaps. Issue 3.2.3.

This module formalizes gap emission as a separate helper, providing:
- Type-safe GapType enum with all dossier-defined types
- Deduplication within configurable time window
- Idempotency via gap_id fingerprint
- Priority calculation based on gap severity
- Metrics for observability

References:
    - Dossier 5: P06 Active Learning Integration
    - Dossier 6.11: st_learning_queue schema
    - M3 Execution: docs/TEMP_EXECUTION_DOCS/M3_EXECUTION.md Issue 3.2.3
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List

from k0.storage.outbox import OutboxEntry

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.phase_outputs import GapCandidate
    from k0.uow.unit_of_work import UnitOfWork


__all__ = [
    "GapType",
    "P03GapEmitter",
    "P03GapEmitterConfig",
    "GapEmitResult",
]


# =============================================================================
# GAP TYPE ENUM (Dossier 6.11)
# =============================================================================


class GapType(Enum):
    """
    Gap types detected during consolidation.

    From Dossier 6.11 st_learning_queue CHECK constraint.
    Maps to P06 active learning strategies.
    """

    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"
    """Entity resolution unclear - multiple candidates match."""

    LOW_CONFIDENCE_EDGE = "LOW_CONFIDENCE_EDGE"
    """KG edge below confidence threshold."""

    MISSING_ATTRIBUTE = "MISSING_ATTRIBUTE"
    """Expected attribute not found on entity."""

    CONTRADICTION = "CONTRADICTION"
    """Conflicting information between sources."""

    CONCEPT_DRIFT = "CONCEPT_DRIFT"
    """Entity meaning has shifted over time."""

    STRUCTURAL_HOLE = "STRUCTURAL_HOLE"
    """Missing bridge between entity clusters."""

    STALE_ANCHOR = "STALE_ANCHOR"
    """Anchor entity needs refresh/revalidation."""

    @classmethod
    def from_string(cls, value: str) -> "GapType":
        """Convert string to GapType, with fallback."""
        try:
            return cls(value.upper())
        except ValueError:
            # Map legacy gap types to new enum
            legacy_map = {
                "AMBIGUITY": cls.AMBIGUOUS_ENTITY,
                "LOW_CONFIDENCE": cls.LOW_CONFIDENCE_EDGE,
                "MISSING": cls.MISSING_ATTRIBUTE,
                "SEMANTIC_CONFLICT": cls.CONTRADICTION,
            }
            if value.upper() in legacy_map:
                return legacy_map[value.upper()]
            # Default to ambiguous for unknown types
            return cls.AMBIGUOUS_ENTITY


# =============================================================================
# GAP PRIORITY CALCULATION
# =============================================================================

# Priority scores by gap type (higher = more urgent)
GAP_PRIORITY_MAP: Dict[GapType, int] = {
    GapType.CONTRADICTION: 100,  # Highest - conflicts block progress
    GapType.AMBIGUOUS_ENTITY: 80,  # High - entity resolution critical
    GapType.STRUCTURAL_HOLE: 70,  # High - data connectivity
    GapType.CONCEPT_DRIFT: 60,  # Medium - may cause stale results
    GapType.LOW_CONFIDENCE_EDGE: 50,  # Medium - can often infer
    GapType.STALE_ANCHOR: 40,  # Medium - needs refresh
    GapType.MISSING_ATTRIBUTE: 30,  # Low - optional enrichment
}


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass(slots=True, frozen=True)
class P03GapEmitterConfig:
    """Configuration for P03 gap emitter.

    Attributes:
        topic: Event bus topic for gap events.
        deduplicate: Whether to skip duplicate gaps within window.
        dedup_window_ms: Deduplication window in milliseconds (default 1 hour).
        default_expires_ms: Default gap TTL in milliseconds (default 7 days).
        max_attempts: Maximum P06 attempts before gap expires.
    """

    topic: str = "p03.gap.detected.v1"
    deduplicate: bool = True
    dedup_window_ms: int = 3600000  # 1 hour
    default_expires_ms: int = 604800000  # 7 days
    max_attempts: int = 3


# =============================================================================
# EMIT RESULT
# =============================================================================


@dataclass(slots=True)
class GapEmitResult:
    """Result of gap emission operation.

    Attributes:
        total: Total gaps received.
        emitted: Gaps successfully emitted.
        deduplicated: Gaps skipped due to deduplication.
        by_type: Count per gap type.
    """

    total: int = 0
    emitted: int = 0
    deduplicated: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)


# =============================================================================
# GAP EMITTER
# =============================================================================


class P03GapEmitter:
    """
    Persists detected gaps to st_learning_queue and stages them to outbox.

    Responsibilities:
        1. Insert gap to st_learning_queue for P06 consumption
        2. Stage gap event to outbox for immediate notification
        3. Deduplicate gaps within configured window
        4. Ensure idempotency via gap_id fingerprint
        5. Calculate priority based on gap type

    Thread Safety:
        Not thread-safe. Use one instance per async context.

    Usage:
        emitter = P03GapEmitter()
        result = await emitter.emit_gaps(uow, gaps, envelope)
    """

    def __init__(self, config: P03GapEmitterConfig | None = None) -> None:
        """Initialize gap emitter.

        Args:
            config: Emitter configuration (uses defaults if None).
        """
        self._config = config or P03GapEmitterConfig()

    @property
    def config(self) -> P03GapEmitterConfig:
        """Return emitter configuration."""
        return self._config

    async def emit_gaps(
        self,
        uow: UnitOfWork,
        gaps: List[GapCandidate],
        envelope: P03BatchEnvelope,
    ) -> GapEmitResult:
        """
        Emit all gaps within UoW transaction.

        Args:
            uow: Active UnitOfWork (transaction).
            gaps: List of GapCandidate from R4.
            envelope: P03BatchEnvelope for context.

        Returns:
            GapEmitResult with emission counts.
        """
        result = GapEmitResult(total=len(gaps))
        tenant_id = envelope.context.tenant_id
        space_id = envelope.context.space_id
        cycle_id = envelope.context.cycle_id

        # Issue 6.1.5: Get metrics registry from observability context
        metrics_registry = (
            envelope.observability.metrics_registry if envelope.observability else None
        )

        for gap in gaps:
            gap_type = GapType.from_string(gap.gap_type)
            gap_id = self._generate_gap_id(cycle_id, gap)

            # Track by type
            type_key = gap_type.value
            result.by_type[type_key] = result.by_type.get(type_key, 0) + 1

            # Check for deduplication
            if self._config.deduplicate:
                if await self._is_duplicate(uow, gap_id):
                    result.deduplicated += 1
                    # Record metric in observability
                    envelope.observability.increment(f"p03.r8.gaps.deduplicated.{type_key.lower()}")
                    # Issue 6.1.5: Emit gap dedup metric
                    if metrics_registry:
                        metrics_registry.emit_gap_deduplicated(
                            tenant_id=tenant_id,
                            gap_type=gap_type.value,
                        )
                    continue

            # Persist to learning queue
            await self._persist_to_queue(uow, gap, gap_type, tenant_id, space_id, cycle_id, gap_id)

            # Stage to outbox
            await self._stage_to_outbox(uow, gap, gap_type, tenant_id, space_id, cycle_id, gap_id)

            result.emitted += 1

            # Record metric in observability
            envelope.observability.increment(f"p03.r8.gaps.emitted.{type_key.lower()}")

            # Issue 6.1.5: Emit gap detected metric with importance score
            if metrics_registry:
                metrics_registry.emit_gap_detected(
                    tenant_id=tenant_id,
                    gap_type=gap_type.value,
                    importance=gap.importance_score,
                )

        # Record total detected metric
        envelope.observability.increment("p03.r8.gaps.detected", result.total)

        return result

    def _generate_gap_id(self, cycle_id: str, gap: GapCandidate) -> str:
        """
        Generate unique gap ID for idempotency.

        Pattern: p03:gap:{cycle_id}:{related_entity_id}:{gap_type}

        Args:
            cycle_id: Current P03 cycle ID.
            gap: GapCandidate to generate ID for.

        Returns:
            Unique gap identifier string.
        """
        return f"p03:gap:{cycle_id}:{gap.related_entity_id}:{gap.gap_type}"

    async def _is_duplicate(
        self,
        uow: UnitOfWork,
        gap_id: str,
    ) -> bool:
        """
        Check if gap already exists within dedup window.

        Args:
            uow: Active UnitOfWork.
            gap_id: Gap identifier to check.

        Returns:
            True if gap is a duplicate, False otherwise.
        """
        cutoff = int(time.time() * 1000) - self._config.dedup_window_ms

        row = await uow.connection.fetchrow(
            """
            SELECT id FROM st_learning_queue
            WHERE id = $1
              AND created_at > $2
            """,
            gap_id,
            cutoff,
        )

        return row is not None

    async def _persist_to_queue(
        self,
        uow: UnitOfWork,
        gap: GapCandidate,
        gap_type: GapType,
        tenant_id: str,
        space_id: str,
        cycle_id: str,
        gap_id: str,
    ) -> None:
        """
        Insert gap into st_learning_queue.

        Schema from migration 0037:
        - id (PK)
        - tenant_id, space_id
        - gap_type, entity_id, related_event_id, related_truth_id
        - confidence_score, entropy_score, importance_score (computed)
        - context_json, status
        - created_at, expires_at, ready_at
        - attempts, max_attempts, last_attempt_at
        - resolution_type, resolution_data_json
        - consolidation_cycle_id

        Args:
            uow: Active UnitOfWork.
            gap: GapCandidate to persist.
            gap_type: Resolved GapType enum.
            tenant_id: Tenant context.
            space_id: Space context.
            cycle_id: Current cycle ID.
            gap_id: Unique gap identifier.
        """
        now_ms = int(time.time() * 1000)
        expires_ms = now_ms + self._config.default_expires_ms

        # Build context JSON from gap fields
        context = {
            "priority": gap.priority,
            "candidate_values": gap.candidate_values,
            "original_context": gap.context_json,
        }

        await uow.connection.execute(
            """
            INSERT INTO st_learning_queue (
                id, tenant_id, space_id, gap_type,
                entity_id, related_event_id, related_truth_id,
                confidence_score, entropy_score,
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
                $14, $15,
                $16
            )
            ON CONFLICT (id) DO NOTHING
            """,
            gap_id,  # id
            tenant_id,  # tenant_id
            space_id,  # space_id
            gap_type.value,  # gap_type
            gap.related_entity_id,  # entity_id
            None,  # related_event_id (not available in GapCandidate)
            None,  # related_truth_id
            1.0 - gap.entropy_score,  # confidence_score (inverse of entropy)
            gap.entropy_score,  # entropy_score
            json.dumps(context),  # context_json
            "PENDING",  # status
            now_ms,  # created_at
            expires_ms,  # expires_at
            0,  # attempts
            self._config.max_attempts,  # max_attempts
            cycle_id,  # consolidation_cycle_id
        )

    async def _stage_to_outbox(
        self,
        uow: UnitOfWork,
        gap: GapCandidate,
        gap_type: GapType,
        tenant_id: str,
        space_id: str,
        cycle_id: str,
        gap_id: str,
    ) -> None:
        """
        Stage gap event to outbox for bus emission.

        Args:
            uow: Active UnitOfWork.
            gap: GapCandidate to emit.
            gap_type: Resolved GapType enum.
            tenant_id: Tenant context.
            space_id: Space context.
            cycle_id: Current cycle ID.
            gap_id: Unique gap identifier.
        """
        payload = self._build_payload(gap, gap_type, tenant_id, space_id, cycle_id, gap_id)

        entry = OutboxEntry(
            id=None,
            wal_pos=0,
            tenant_id=tenant_id,
            space_id=space_id,
            driver="p03",
            op_kind=self._config.topic,
            payload=json.dumps(payload).encode("utf-8"),
            fingerprint=gap_id,
            requeue_seq=0,
            retries=0,
        )
        uow.stage_outbox(entry)

    def _build_payload(
        self,
        gap: GapCandidate,
        gap_type: GapType,
        tenant_id: str,
        space_id: str,
        cycle_id: str,
        gap_id: str,
    ) -> Dict[str, Any]:
        """
        Build gap event payload for bus emission.

        Args:
            gap: GapCandidate source.
            gap_type: Resolved GapType enum.
            tenant_id: Tenant context.
            space_id: Space context.
            cycle_id: Current cycle ID.
            gap_id: Unique gap identifier.

        Returns:
            Payload dict for JSON serialization.
        """
        return {
            "gap_id": gap_id,
            "cycle_id": cycle_id,
            "tenant_id": tenant_id,
            "space_id": space_id,
            "gap_type": gap_type.value,
            "related_entity_id": gap.related_entity_id,
            "entropy_score": gap.entropy_score,
            "priority": self._calculate_priority(gap_type),
            "priority_label": gap.priority,
            "candidate_values": gap.candidate_values,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

    def _calculate_priority(self, gap_type: GapType) -> int:
        """
        Calculate numeric priority based on gap type.

        Higher priority = processed first by P06.

        Args:
            gap_type: Gap type enum.

        Returns:
            Priority score (0-100).
        """
        return GAP_PRIORITY_MAP.get(gap_type, 50)
