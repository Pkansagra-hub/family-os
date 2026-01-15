"""
R4 Confidence Router — Confidence band routing with P06 gap emission.

Issue: 4.4.5 - Implement confidence bands + P06 gap emission
Spec Reference: Dossier §4.5.1.3, M4_EXECUTION.md

This module provides centralized confidence band routing for entity resolution
outcomes, integrating with P06 Active Learning pipeline for gap emission.

Architecture:
- Three confidence bands: AUTO, FLAG, GAP
- P06 integration via st_learning_queue
- Outbox pattern for reliable gap delivery
- Metric tracking for band distribution

Performance:
- Routing: O(1)
- Gap emission: O(1) per gap

Human Memory Model:
- High confidence → We just know (AUTO)
- Medium confidence → We know but we should double-check (FLAG)
- Low confidence → We need to ask someone (GAP)

Related:
- k0/modules/consolidation/algorithms/ambiguous_resolver.py: Resolution logic
- k0/pipelines/p03/gap_emitter.py: Base gap emission
- k0/db/tables/st_learning_queue.py: Gap queue table

Author: K0 Architecture Team
Date: 2025-01-03
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Constants
# =============================================================================

# Confidence thresholds (from Dossier §4.5.1.3)
P03_CONFIDENCE_THRESHOLD_AUTO: float = 0.85
P03_CONFIDENCE_THRESHOLD_FLAG: float = 0.60

# Gap emission settings
P03_GAP_BATCH_SIZE: int = 50
P03_GAP_MAX_CANDIDATES: int = 5
P03_GAP_TTL_MS: int = 86400_000  # 24 hours

# Outbox settings
P03_OUTBOX_TOPIC: str = "p03.gap.detected.v1"
P03_OUTBOX_RETRY_COUNT: int = 3


# =============================================================================
# Enums
# =============================================================================


class ConfidenceBand(str, Enum):
    """Confidence band for routing decisions.

    From Dossier §4.5.1.3:
    - AUTO: ≥0.85, accept without review
    - FLAG: 0.60-0.85, accept but flag
    - GAP: <0.60, emit to P06
    """

    AUTO = "auto"
    FLAG = "flag"
    GAP = "gap"


class GapType(str, Enum):
    """Types of learning gaps emitted to P06.

    From Dossier §4.5.1.3:
    - AMBIGUOUS_ENTITY: Multiple candidate entities for mention
    - LOW_CONFIDENCE_EDGE: Edge with low confidence
    - MISSING_ATTRIBUTE: Entity missing expected attribute
    - CONTRADICTION: Conflicting information detected
    """

    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"
    LOW_CONFIDENCE_EDGE = "LOW_CONFIDENCE_EDGE"
    MISSING_ATTRIBUTE = "MISSING_ATTRIBUTE"
    CONTRADICTION = "CONTRADICTION"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class GapPayload:
    """Payload for a learning gap to be emitted to P06.

    Attributes:
        gap_type: Type of learning gap
        mention: The ambiguous mention or entity
        candidates: Candidate entities/values for resolution
        context: Event context for the gap
        confidence: Current confidence score
        breakdown: Score breakdown components
        created_at_ms: Timestamp when gap was detected
        ttl_ms: Time to live for the gap
    """

    gap_type: GapType
    mention: str
    candidates: List[Dict[str, Any]]
    context: Dict[str, Any]
    confidence: float
    breakdown: Dict[str, float] = field(default_factory=dict)
    created_at_ms: int = 0
    ttl_ms: int = P03_GAP_TTL_MS

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "gap_type": self.gap_type.value,
            "mention": self.mention,
            "candidates": self.candidates,
            "context": self.context,
            "confidence": round(self.confidence, 4),
            "breakdown": self.breakdown,
            "created_at_ms": self.created_at_ms,
            "ttl_ms": self.ttl_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GapPayload":
        """Create from dictionary."""
        return cls(
            gap_type=GapType(data["gap_type"]),
            mention=data["mention"],
            candidates=data["candidates"],
            context=data["context"],
            confidence=data["confidence"],
            breakdown=data.get("breakdown", {}),
            created_at_ms=data.get("created_at_ms", 0),
            ttl_ms=data.get("ttl_ms", P03_GAP_TTL_MS),
        )


@dataclass
class OutboxEntry:
    """Entry for the outbox table for reliable gap delivery.

    Attributes:
        entry_id: Unique identifier (ULID)
        topic: Target topic for publishing
        payload_json: Serialized payload
        partition_key: Key for partitioning
        created_at_ms: Timestamp when entry was created
        retry_count: Number of delivery attempts
        last_error: Last error message if any
    """

    entry_id: str
    topic: str
    payload_json: str
    partition_key: str
    created_at_ms: int
    retry_count: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "entry_id": self.entry_id,
            "topic": self.topic,
            "payload_json": self.payload_json,
            "partition_key": self.partition_key,
            "created_at_ms": self.created_at_ms,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
        }


@dataclass
class RoutingResult:
    """Result of confidence band routing.

    Attributes:
        band: Assigned confidence band
        confidence: Confidence score
        should_emit_gap: Whether to emit gap to P06
        gap_payload: Gap payload if should_emit_gap is True
        action_taken: Description of action taken
    """

    band: ConfidenceBand
    confidence: float
    should_emit_gap: bool
    gap_payload: Optional[GapPayload] = None
    action_taken: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "band": self.band.value,
            "confidence": round(self.confidence, 4),
            "should_emit_gap": self.should_emit_gap,
            "action_taken": self.action_taken,
        }
        if self.gap_payload:
            result["gap_payload"] = self.gap_payload.to_dict()
        return result


@dataclass
class RouterMetrics:
    """Metrics for routing operations."""

    total_routed: int = 0
    auto_count: int = 0
    flag_count: int = 0
    gap_count: int = 0
    gaps_emitted: int = 0
    gaps_failed: int = 0
    avg_confidence: float = 0.0
    band_distribution: Dict[str, float] = field(default_factory=dict)

    def update_avg_confidence(self, confidence: float) -> None:
        """Update rolling average confidence."""
        if self.total_routed == 0:
            self.avg_confidence = confidence
        else:
            # Exponential moving average
            alpha = 0.1
            self.avg_confidence = alpha * confidence + (1 - alpha) * self.avg_confidence

    def update_distribution(self) -> None:
        """Update band distribution percentages."""
        if self.total_routed == 0:
            return
        self.band_distribution = {
            "auto": self.auto_count / self.total_routed,
            "flag": self.flag_count / self.total_routed,
            "gap": self.gap_count / self.total_routed,
        }


# =============================================================================
# Protocols
# =============================================================================


@runtime_checkable
class AsyncDBConnection(Protocol):
    """Protocol for async database connection (asyncpg-compatible)."""

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """Fetch single row."""
        ...

    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        """Fetch multiple rows."""
        ...

    async def execute(self, query: str, *args: Any) -> str:
        """Execute query."""
        ...


@runtime_checkable
class EventBusProtocol(Protocol):
    """Protocol for event bus publishing."""

    async def publish(self, topic: str, payload: Dict[str, Any], **kwargs: Any) -> None:
        """Publish message to topic."""
        ...


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class ConfidenceRouterConfig:
    """Configuration for confidence router.

    Attributes:
        threshold_auto: Auto-accept threshold (≥ this = AUTO band)
        threshold_flag: Flag threshold (≥ this = FLAG band)
        gap_batch_size: Max gaps to emit in one batch
        gap_max_candidates: Max candidates to include in gap
        gap_ttl_ms: TTL for gaps in queue
        outbox_topic: Topic for gap emission
        outbox_retry_count: Max retry attempts for gap delivery
    """

    threshold_auto: float = P03_CONFIDENCE_THRESHOLD_AUTO
    threshold_flag: float = P03_CONFIDENCE_THRESHOLD_FLAG
    gap_batch_size: int = P03_GAP_BATCH_SIZE
    gap_max_candidates: int = P03_GAP_MAX_CANDIDATES
    gap_ttl_ms: int = P03_GAP_TTL_MS
    outbox_topic: str = P03_OUTBOX_TOPIC
    outbox_retry_count: int = P03_OUTBOX_RETRY_COUNT

    def validate(self) -> None:
        """Validate configuration values."""
        if not 0 < self.threshold_flag < self.threshold_auto <= 1.0:
            raise ValueError(
                f"threshold_flag ({self.threshold_flag}) must be < "
                f"threshold_auto ({self.threshold_auto}) and both in (0, 1]"
            )
        if self.gap_batch_size <= 0:
            raise ValueError(f"gap_batch_size must be > 0, got {self.gap_batch_size}")


# =============================================================================
# Confidence Router
# =============================================================================


class ConfidenceRouter:
    """
    Route entity resolutions based on confidence bands with P06 gap emission.

    Spec: Dossier §4.5.1.3

    This class provides centralized routing for entity resolution outcomes,
    determining which band a result falls into and emitting gaps to P06
    for low-confidence cases.

    Confidence Bands:
        AUTO (≥0.85): Accept silently, no human intervention
        FLAG (0.60-0.85): Accept but flag for potential review
        GAP (<0.60): Emit to P06 Active Learning for clarification

    Gap Emission:
        Low-confidence resolutions are persisted to st_learning_queue and
        staged to st_outbox for reliable delivery to P06.

    Usage:
        router = ConfidenceRouter()
        result = router.route(
            confidence=0.55,
            mention="John",
            candidates=[...],
            context={...}
        )

        if result.should_emit_gap:
            await router.emit_gap(result.gap_payload, db_conn)
    """

    def __init__(self, config: Optional[ConfidenceRouterConfig] = None) -> None:
        """Initialize router with optional config.

        Args:
            config: Router configuration (uses defaults if None)
        """
        self._config = config or ConfidenceRouterConfig()
        self._metrics = RouterMetrics()

    @property
    def config(self) -> ConfidenceRouterConfig:
        """Return router configuration."""
        return self._config

    @property
    def metrics(self) -> RouterMetrics:
        """Return routing metrics."""
        return self._metrics

    def route(
        self,
        confidence: float,
        mention: str,
        candidates: List[Dict[str, Any]],
        context: Dict[str, Any],
        breakdown: Optional[Dict[str, float]] = None,
        gap_type: GapType = GapType.AMBIGUOUS_ENTITY,
    ) -> RoutingResult:
        """
        Route based on confidence band.

        Args:
            confidence: Confidence score [0, 1]
            mention: The entity mention being resolved
            candidates: Candidate entities
            context: Event context
            breakdown: Score breakdown (optional)
            gap_type: Type of gap if emitting

        Returns:
            RoutingResult with band assignment and optional gap payload
        """
        self._metrics.total_routed += 1
        self._metrics.update_avg_confidence(confidence)

        now_ms = int(time.time() * 1000)

        # Determine band
        if confidence >= self._config.threshold_auto:
            band = ConfidenceBand.AUTO
            self._metrics.auto_count += 1
            action = "Accepted automatically (high confidence)"
            should_emit = False
            gap_payload = None

        elif confidence >= self._config.threshold_flag:
            band = ConfidenceBand.FLAG
            self._metrics.flag_count += 1
            action = "Accepted with flag (medium confidence)"
            should_emit = False
            gap_payload = None

        else:
            band = ConfidenceBand.GAP
            self._metrics.gap_count += 1
            action = "Routing to P06 for clarification (low confidence)"
            should_emit = True

            # Build gap payload
            gap_payload = GapPayload(
                gap_type=gap_type,
                mention=mention,
                candidates=candidates[: self._config.gap_max_candidates],
                context=context,
                confidence=confidence,
                breakdown=breakdown or {},
                created_at_ms=now_ms,
                ttl_ms=self._config.gap_ttl_ms,
            )

        self._metrics.update_distribution()

        result = RoutingResult(
            band=band,
            confidence=confidence,
            should_emit_gap=should_emit,
            gap_payload=gap_payload,
            action_taken=action,
        )

        logger.debug(
            "Routed confidence band",
            extra={
                "band": band.value,
                "confidence": round(confidence, 4),
                "mention": mention,
                "should_emit_gap": should_emit,
            },
        )

        return result

    def determine_band(self, confidence: float) -> ConfidenceBand:
        """
        Determine confidence band without full routing.

        Args:
            confidence: Confidence score [0, 1]

        Returns:
            Assigned ConfidenceBand
        """
        if confidence >= self._config.threshold_auto:
            return ConfidenceBand.AUTO
        elif confidence >= self._config.threshold_flag:
            return ConfidenceBand.FLAG
        else:
            return ConfidenceBand.GAP

    async def emit_gap(
        self,
        gap_payload: GapPayload,
        db_conn: AsyncDBConnection,
        tenant_id: str = "",
        space_id: str = "",
    ) -> str:
        """
        Emit gap to st_learning_queue and stage to outbox.

        Args:
            gap_payload: Gap payload to emit
            db_conn: Database connection
            tenant_id: Tenant isolation key
            space_id: Space isolation key

        Returns:
            Gap entry ID
        """
        entry_id = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)

        try:
            # 1. Persist to st_learning_queue
            await db_conn.execute(
                """
                INSERT INTO st_learning_queue (
                    entry_id, tenant_id, space_id,
                    gap_type, payload_json,
                    status, created_at, ttl_ms
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8
                )
                """,
                entry_id,
                tenant_id,
                space_id,
                gap_payload.gap_type.value,
                json.dumps(gap_payload.to_dict()),
                "pending",
                now_ms,
                gap_payload.ttl_ms,
            )

            # 2. Stage to st_outbox for reliable delivery
            outbox_id = str(uuid.uuid4())
            partition_key = f"{tenant_id}:{space_id}"

            await db_conn.execute(
                """
                INSERT INTO st_outbox (
                    entry_id, topic, payload_json,
                    partition_key, created_at
                ) VALUES (
                    $1, $2, $3, $4, $5
                )
                """,
                outbox_id,
                self._config.outbox_topic,
                json.dumps(gap_payload.to_dict()),
                partition_key,
                now_ms,
            )

            self._metrics.gaps_emitted += 1

            logger.info(
                "Emitted gap to P06",
                extra={
                    "entry_id": entry_id,
                    "gap_type": gap_payload.gap_type.value,
                    "mention": gap_payload.mention,
                    "confidence": gap_payload.confidence,
                },
            )

            return entry_id

        except Exception as e:
            self._metrics.gaps_failed += 1
            logger.error(
                "Failed to emit gap",
                extra={
                    "gap_type": gap_payload.gap_type.value,
                    "mention": gap_payload.mention,
                    "error": str(e),
                },
            )
            raise

    async def emit_batch(
        self,
        gaps: List[GapPayload],
        db_conn: AsyncDBConnection,
        tenant_id: str = "",
        space_id: str = "",
    ) -> List[str]:
        """
        Emit batch of gaps to st_learning_queue.

        Args:
            gaps: List of gap payloads
            db_conn: Database connection
            tenant_id: Tenant isolation key
            space_id: Space isolation key

        Returns:
            List of gap entry IDs
        """
        entry_ids = []

        for gap in gaps[: self._config.gap_batch_size]:
            try:
                entry_id = await self.emit_gap(gap, db_conn, tenant_id, space_id)
                entry_ids.append(entry_id)
            except Exception as e:
                logger.warning(
                    "Skipping gap in batch due to error",
                    extra={
                        "mention": gap.mention,
                        "error": str(e),
                    },
                )

        return entry_ids

    def get_band_thresholds(self) -> Dict[str, float]:
        """Return band thresholds for external reference.

        Returns:
            Dictionary with threshold values
        """
        return {
            "auto": self._config.threshold_auto,
            "flag": self._config.threshold_flag,
        }


# =============================================================================
# Factory Function
# =============================================================================


def get_confidence_router(
    config: Optional[ConfidenceRouterConfig] = None,
) -> ConfidenceRouter:
    """
    Factory function to create a ConfidenceRouter.

    Args:
        config: Optional configuration

    Returns:
        Configured ConfidenceRouter instance
    """
    return ConfidenceRouter(config=config)


# =============================================================================
# Convenience Functions
# =============================================================================


def quick_band(confidence: float) -> ConfidenceBand:
    """
    Quick band lookup without router instance.

    Args:
        confidence: Confidence score [0, 1]

    Returns:
        Assigned ConfidenceBand
    """
    if confidence >= P03_CONFIDENCE_THRESHOLD_AUTO:
        return ConfidenceBand.AUTO
    elif confidence >= P03_CONFIDENCE_THRESHOLD_FLAG:
        return ConfidenceBand.FLAG
    else:
        return ConfidenceBand.GAP
