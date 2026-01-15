"""
R4 Ambiguous Entity Resolver — Context-hierarchy resolution for ambiguous entities.

Issue: 4.4.4 - Implement ambiguous entity resolution with context hierarchy
Spec Reference: Dossier §4.5.1.2, M4_EXECUTION.md

This module provides ambiguous entity resolution using a 5-priority context
hierarchy to select the best candidate when multiple entities match a mention.

Architecture:
- 5-priority context hierarchy (recency, co-occurrence, location, temporal, frequency)
- Confidence band routing (AUTO_RESOLVED, RESOLVED_FLAGGED, GAP_EMITTED)
- P06 gap emission for low-confidence cases
- Full audit trail in st_entity_resolutions

Performance:
- Resolution: O(n) where n = number of candidates
- Memory: O(1) per resolution

Human Memory Model:
- We resolve "John" based on who we talked about recently (recency)
- We resolve "John" based on context ("John and Sarah" → Sarah's husband)
- We resolve "John" based on location ("at work" → colleague John)

Related:
- k0/modules/consolidation/algorithms/entity_disambiguator.py: Base similarity
- k0/pipelines/p03/gap_emitter.py: Gap emission to P06
- k0/db/alembic/versions/0047_st_entity_resolutions.py: Audit table

Author: K0 Architecture Team
Date: 2025-01-03
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Constants
# =============================================================================

# Confidence thresholds (from Dossier §4.5.1.2)
P03_RESOLUTION_THRESHOLD_AUTO: float = 0.85
P03_RESOLUTION_THRESHOLD_FLAG: float = 0.60

# Priority boosts (from Dossier §4.5.1.2)
P03_RESOLUTION_BOOST_RECENCY: float = 0.35
P03_RESOLUTION_BOOST_CO_OCCURRING: float = 0.30
P03_RESOLUTION_BOOST_LOCATION: float = 0.20
P03_RESOLUTION_BOOST_TEMPORAL: float = 0.10
P03_RESOLUTION_BOOST_FREQUENCY: float = 0.05

# Close race penalty
P03_RESOLUTION_CLOSE_RACE_THRESHOLD: float = 0.10
P03_RESOLUTION_CLOSE_RACE_PENALTY: float = 0.10

# Default recency window (1 hour in ms)
P03_RESOLUTION_RECENCY_WINDOW_MS: int = 3600_000

# Max candidates in P06 gap
P03_RESOLUTION_MAX_CANDIDATES_GAP: int = 5


# =============================================================================
# Enums
# =============================================================================


class ResolutionOutcome(str, Enum):
    """Outcome of entity resolution.

    From Dossier §4.5.1.2:
    - AUTO_RESOLVED: ≥0.85 confidence, no human review needed
    - RESOLVED_FLAGGED: 0.60-0.85, accept but flag for review
    - GAP_EMITTED: <0.60, route to P06 for user clarification
    """

    AUTO_RESOLVED = "auto_resolved"
    RESOLVED_FLAGGED = "resolved_flagged"
    GAP_EMITTED = "gap_emitted"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CandidateEntity:
    """A candidate entity for resolution.

    Represents an entity from st_kg_dom that could match the mention.

    Attributes:
        entity_id: Unique entity identifier (ULID)
        entity_type: Entity type (PERSON, FAMILY_MEMBER, ORGANIZATION, etc.)
        canonical_name: Display name for the entity
        embedding: Vector embedding (768-dim for UltraBERT)
        last_seen_ms: Timestamp of last observation (epoch ms)
        frequency: Total observation count
        attributes: Optional additional attributes (e.g., relationship_type)
    """

    entity_id: str
    entity_type: str
    canonical_name: str
    embedding: Optional[List[float]] = None
    last_seen_ms: int = 0
    frequency: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "canonical_name": self.canonical_name,
            "last_seen_ms": self.last_seen_ms,
            "frequency": self.frequency,
            "attributes": self.attributes,
        }


@dataclass
class EventContext:
    """Context from the current event for resolution.

    Provides contextual signals that help disambiguate entities.

    Attributes:
        session_id: Current session identifier
        event_timestamp_ms: Event timestamp (epoch ms)
        co_occurring_entities: Entity IDs appearing in the same event
        location_hint: Location category (work, home, school, gym, etc.)
        temporal_category: Time category (morning, afternoon, evening, weekend)
        tenant_id: Tenant isolation key
        space_id: Space isolation key
    """

    session_id: str
    event_timestamp_ms: int
    co_occurring_entities: List[str] = field(default_factory=list)
    location_hint: Optional[str] = None
    temporal_category: Optional[str] = None
    tenant_id: str = ""
    space_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "event_timestamp_ms": self.event_timestamp_ms,
            "co_occurring_entities": self.co_occurring_entities,
            "location_hint": self.location_hint,
            "temporal_category": self.temporal_category,
        }


@dataclass
class ResolutionBreakdown:
    """Detailed breakdown of resolution score computation.

    Provides transparency into how each priority contributed to the score.
    """

    base_score: float = 0.0
    recent_context: float = 0.0
    co_occurring: float = 0.0
    location: float = 0.0
    temporal: float = 0.0
    frequency: float = 0.0
    close_race_penalty: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for serialization."""
        result = {}
        if self.base_score > 0:
            result["base_score"] = round(self.base_score, 4)
        if self.recent_context > 0:
            result["recent_context"] = round(self.recent_context, 4)
        if self.co_occurring > 0:
            result["co_occurring"] = round(self.co_occurring, 4)
        if self.location > 0:
            result["location"] = round(self.location, 4)
        if self.temporal > 0:
            result["temporal"] = round(self.temporal, 4)
        if self.frequency > 0:
            result["frequency"] = round(self.frequency, 4)
        if self.close_race_penalty > 0:
            result["close_race_penalty"] = round(-self.close_race_penalty, 4)
        return result

    @property
    def total(self) -> float:
        """Calculate total score from components."""
        return (
            self.base_score
            + self.recent_context
            + self.co_occurring
            + self.location
            + self.temporal
            + self.frequency
            - self.close_race_penalty
        )


@dataclass
class ResolutionResult:
    """Result of ambiguous entity resolution.

    Attributes:
        mention: The ambiguous mention text (e.g., "John")
        selected_entity_id: Resolved entity ID (None if GAP_EMITTED)
        confidence: Final confidence score [0, 1]
        outcome: Resolution outcome (AUTO_RESOLVED, RESOLVED_FLAGGED, GAP_EMITTED)
        breakdown: Score breakdown by priority
        candidates_considered: Number of candidates evaluated
        resolution_time_ms: Time taken for resolution (ms)
    """

    mention: str
    selected_entity_id: Optional[str]
    confidence: float
    outcome: ResolutionOutcome
    breakdown: Dict[str, float]
    candidates_considered: int
    resolution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "mention": self.mention,
            "selected_entity_id": self.selected_entity_id,
            "confidence": round(self.confidence, 4),
            "outcome": self.outcome.value,
            "breakdown": self.breakdown,
            "candidates_considered": self.candidates_considered,
            "resolution_time_ms": round(self.resolution_time_ms, 2),
        }


@dataclass
class ResolutionMetrics:
    """Metrics for resolution operations."""

    total_resolutions: int = 0
    auto_resolved: int = 0
    flagged: int = 0
    gaps_emitted: int = 0
    avg_confidence: float = 0.0
    avg_candidates: float = 0.0
    boost_usage: Dict[str, int] = field(default_factory=dict)


# =============================================================================
# Protocols
# =============================================================================


@runtime_checkable
class AsyncDBConnection(Protocol):
    """Protocol for async database connection (asyncpg-compatible)."""

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """Fetch single row."""
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
class AmbiguousResolverConfig:
    """Configuration for ambiguous entity resolver.

    Attributes:
        threshold_auto: Auto-resolve threshold (≥ this = AUTO_RESOLVED)
        threshold_flag: Flag threshold (≥ this = RESOLVED_FLAGGED)
        recency_window_ms: Window for recency boost (ms)
        boost_recency: P1 boost for recent context
        boost_co_occurring: P2 boost for co-occurring entities
        boost_location: P3 boost for location match
        boost_temporal: P4 boost for temporal match
        boost_frequency: P5 boost for frequency
        close_race_threshold: Gap below which to apply penalty
        close_race_penalty: Penalty for close race (multiplier)
        max_candidates_gap: Max candidates to include in P06 gap
    """

    threshold_auto: float = P03_RESOLUTION_THRESHOLD_AUTO
    threshold_flag: float = P03_RESOLUTION_THRESHOLD_FLAG
    recency_window_ms: int = P03_RESOLUTION_RECENCY_WINDOW_MS
    boost_recency: float = P03_RESOLUTION_BOOST_RECENCY
    boost_co_occurring: float = P03_RESOLUTION_BOOST_CO_OCCURRING
    boost_location: float = P03_RESOLUTION_BOOST_LOCATION
    boost_temporal: float = P03_RESOLUTION_BOOST_TEMPORAL
    boost_frequency: float = P03_RESOLUTION_BOOST_FREQUENCY
    close_race_threshold: float = P03_RESOLUTION_CLOSE_RACE_THRESHOLD
    close_race_penalty: float = P03_RESOLUTION_CLOSE_RACE_PENALTY
    max_candidates_gap: int = P03_RESOLUTION_MAX_CANDIDATES_GAP

    def validate(self) -> None:
        """Validate configuration values."""
        if not 0 < self.threshold_flag < self.threshold_auto <= 1.0:
            raise ValueError(
                f"threshold_flag ({self.threshold_flag}) must be < "
                f"threshold_auto ({self.threshold_auto}) and both in (0, 1]"
            )
        if self.recency_window_ms <= 0:
            raise ValueError(f"recency_window_ms must be > 0, got {self.recency_window_ms}")


# =============================================================================
# Location Entity Mapping
# =============================================================================

# Maps location hints to entity types/keywords likely present
LOCATION_ENTITY_MAP: Dict[str, List[str]] = {
    "work": ["ORGANIZATION", "colleague", "coworker", "boss", "manager"],
    "home": ["FAMILY_MEMBER", "family", "spouse", "child", "parent"],
    "school": ["teacher", "student", "professor", "classmate"],
    "gym": ["trainer", "coach", "workout"],
    "church": ["pastor", "priest", "congregation"],
    "hospital": ["doctor", "nurse", "patient"],
    "restaurant": ["waiter", "chef"],
}

# Maps temporal categories to typical entity patterns
TEMPORAL_ENTITY_MAP: Dict[str, List[str]] = {
    "morning": ["commute", "breakfast", "gym"],
    "afternoon": ["lunch", "meeting", "work"],
    "evening": ["dinner", "family", "home"],
    "weekend": ["family", "friend", "hobby"],
}


# =============================================================================
# Ambiguous Entity Resolver
# =============================================================================


class AmbiguousEntityResolver:
    """
    Resolve ambiguous entity mentions using 5-priority context hierarchy.

    Spec: Dossier §4.5.1.2

    When multiple candidate entities match a mention (e.g., "John" could be
    John Smith or John Doe), this resolver selects the best candidate using
    contextual signals ordered by priority:

    Priority Hierarchy:
        P1. Recent context (+0.35): Was entity mentioned recently in session?
        P2. Co-occurring entities (+0.30): Other entities that narrow it down
        P3. Location context (+0.20): "at work" suggests colleague
        P4. Temporal pattern (+0.10): Morning mentions → commute entities
        P5. Frequency (+0.05): Higher frequency = more likely

    Confidence Bands:
        ≥0.85: AUTO_RESOLVED — Accept silently
        0.60-0.85: RESOLVED_FLAGGED — Accept but flag for review
        <0.60: GAP_EMITTED — Route to P06 for user clarification

    Usage:
        resolver = AmbiguousEntityResolver()
        result = resolver.resolve("John", candidates, context)

        if result.outcome == ResolutionOutcome.GAP_EMITTED:
            await resolver.emit_gap_to_p06(...)
    """

    def __init__(self, config: Optional[AmbiguousResolverConfig] = None) -> None:
        """Initialize resolver with optional config.

        Args:
            config: Resolver configuration (uses defaults if None)
        """
        self._config = config or AmbiguousResolverConfig()
        self._metrics = ResolutionMetrics()

    @property
    def config(self) -> AmbiguousResolverConfig:
        """Return resolver configuration."""
        return self._config

    @property
    def metrics(self) -> ResolutionMetrics:
        """Return resolution metrics."""
        return self._metrics

    def resolve(
        self,
        mention: str,
        candidates: List[CandidateEntity],
        event_context: EventContext,
    ) -> ResolutionResult:
        """
        Resolve ambiguous mention to best candidate.

        Algorithm:
        1. Handle edge cases (no candidates, single candidate)
        2. Score each candidate using 5-priority hierarchy
        3. Apply close-race penalty if gap < threshold
        4. Route based on confidence bands

        Args:
            mention: The ambiguous mention text (e.g., "John")
            candidates: List of candidate entities from st_kg_dom
            event_context: Context from the current event

        Returns:
            ResolutionResult with selected entity and confidence
        """
        start_time = time.time()
        self._metrics.total_resolutions += 1

        # Edge case: No candidates
        if not candidates:
            result = ResolutionResult(
                mention=mention,
                selected_entity_id=None,
                confidence=0.0,
                outcome=ResolutionOutcome.GAP_EMITTED,
                breakdown={},
                candidates_considered=0,
            )
            self._metrics.gaps_emitted += 1
            return result

        # Edge case: Single candidate (high confidence)
        if len(candidates) == 1:
            result = ResolutionResult(
                mention=mention,
                selected_entity_id=candidates[0].entity_id,
                confidence=0.95,
                outcome=ResolutionOutcome.AUTO_RESOLVED,
                breakdown={"single_candidate": 0.95},
                candidates_considered=1,
                resolution_time_ms=(time.time() - start_time) * 1000,
            )
            self._metrics.auto_resolved += 1
            return result

        # Score all candidates
        scored: List[Tuple[CandidateEntity, float, ResolutionBreakdown]] = []
        for candidate in candidates:
            score, breakdown = self._score_candidate(candidate, event_context)
            scored.append((candidate, score, breakdown))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        best_candidate, best_score, best_breakdown = scored[0]

        # Check for close race and apply penalty
        if len(scored) > 1:
            second_score = scored[1][1]
            gap = best_score - second_score

            if gap < self._config.close_race_threshold:
                penalty = best_score * self._config.close_race_penalty
                best_score = best_score - penalty
                best_breakdown.close_race_penalty = penalty

        # Clamp to [0, 1]
        best_score = min(1.0, max(0.0, best_score))

        # Determine outcome based on confidence bands
        if best_score >= self._config.threshold_auto:
            outcome = ResolutionOutcome.AUTO_RESOLVED
            selected_id = best_candidate.entity_id
            self._metrics.auto_resolved += 1
        elif best_score >= self._config.threshold_flag:
            outcome = ResolutionOutcome.RESOLVED_FLAGGED
            selected_id = best_candidate.entity_id
            self._metrics.flagged += 1
        else:
            outcome = ResolutionOutcome.GAP_EMITTED
            selected_id = None
            self._metrics.gaps_emitted += 1

        # Update metrics
        self._update_boost_metrics(best_breakdown)

        result = ResolutionResult(
            mention=mention,
            selected_entity_id=selected_id,
            confidence=best_score,
            outcome=outcome,
            breakdown=best_breakdown.to_dict(),
            candidates_considered=len(candidates),
            resolution_time_ms=(time.time() - start_time) * 1000,
        )

        logger.debug(
            "Resolved ambiguous entity",
            extra={
                "mention": mention,
                "outcome": outcome.value,
                "confidence": round(best_score, 4),
                "candidates": len(candidates),
            },
        )

        return result

    def _score_candidate(
        self,
        candidate: CandidateEntity,
        context: EventContext,
    ) -> Tuple[float, ResolutionBreakdown]:
        """
        Score a candidate using 5-priority hierarchy.

        Args:
            candidate: Entity candidate to score
            context: Event context for scoring

        Returns:
            Tuple of (total_score, breakdown)
        """
        breakdown = ResolutionBreakdown(base_score=0.30)  # Baseline for string match

        # P1: Recent context (same session recency)
        recency_age = context.event_timestamp_ms - candidate.last_seen_ms
        if 0 <= recency_age <= self._config.recency_window_ms:
            recency_factor = 1.0 - (recency_age / self._config.recency_window_ms)
            breakdown.recent_context = self._config.boost_recency * recency_factor

        # P2: Co-occurring entities
        if candidate.entity_id in context.co_occurring_entities:
            breakdown.co_occurring = self._config.boost_co_occurring

        # P3: Location context
        if context.location_hint:
            if self._check_location_match(candidate, context.location_hint):
                breakdown.location = self._config.boost_location

        # P4: Temporal pattern
        if context.temporal_category:
            if self._check_temporal_match(candidate, context.temporal_category):
                breakdown.temporal = self._config.boost_temporal

        # P5: Frequency (normalized to max 1.0)
        freq_score = min(1.0, candidate.frequency / 100.0)
        breakdown.frequency = self._config.boost_frequency * freq_score

        return breakdown.total, breakdown

    def _check_location_match(
        self,
        candidate: CandidateEntity,
        location_hint: str,
    ) -> bool:
        """
        Check if candidate matches location hint.

        Args:
            candidate: Entity candidate
            location_hint: Location category (work, home, school, etc.)

        Returns:
            True if candidate matches location context
        """
        hints = LOCATION_ENTITY_MAP.get(location_hint.lower(), [])
        if not hints:
            return False

        # Check entity type
        if candidate.entity_type in hints:
            return True

        # Check canonical name for keywords
        name_lower = candidate.canonical_name.lower()
        return any(h.lower() in name_lower for h in hints)

    def _check_temporal_match(
        self,
        candidate: CandidateEntity,
        temporal_category: str,
    ) -> bool:
        """
        Check if candidate matches temporal pattern.

        Args:
            candidate: Entity candidate
            temporal_category: Time category (morning, afternoon, evening, weekend)

        Returns:
            True if candidate matches temporal pattern
        """
        patterns = TEMPORAL_ENTITY_MAP.get(temporal_category.lower(), [])
        if not patterns:
            return False

        # Check canonical name for temporal keywords
        name_lower = candidate.canonical_name.lower()
        return any(p.lower() in name_lower for p in patterns)

    def _update_boost_metrics(self, breakdown: ResolutionBreakdown) -> None:
        """Update metrics for which boosts were applied."""
        if breakdown.recent_context > 0:
            self._metrics.boost_usage["recent_context"] = (
                self._metrics.boost_usage.get("recent_context", 0) + 1
            )
        if breakdown.co_occurring > 0:
            self._metrics.boost_usage["co_occurring"] = (
                self._metrics.boost_usage.get("co_occurring", 0) + 1
            )
        if breakdown.location > 0:
            self._metrics.boost_usage["location"] = self._metrics.boost_usage.get("location", 0) + 1
        if breakdown.temporal > 0:
            self._metrics.boost_usage["temporal"] = self._metrics.boost_usage.get("temporal", 0) + 1
        if breakdown.frequency > 0:
            self._metrics.boost_usage["frequency"] = (
                self._metrics.boost_usage.get("frequency", 0) + 1
            )

    async def emit_gap_to_p06(
        self,
        mention: str,
        candidates: List[CandidateEntity],
        event_context: EventContext,
        result: ResolutionResult,
        event_bus: EventBusProtocol,
    ) -> None:
        """
        Emit AMBIGUOUS_ENTITY gap to P06 for user resolution.

        Args:
            mention: The ambiguous mention
            candidates: Candidate entities
            event_context: Event context
            result: Resolution result
            event_bus: Event bus for publishing
        """
        gap_payload = {
            "gap_type": "AMBIGUOUS_ENTITY",
            "mention": mention,
            "candidates": [c.to_dict() for c in candidates[: self._config.max_candidates_gap]],
            "context": event_context.to_dict(),
            "confidence": result.confidence,
            "breakdown": result.breakdown,
            "created_at": int(time.time() * 1000),
        }

        await event_bus.publish(
            topic="p03.gap.detected.v1",
            payload=gap_payload,
            key=f"{event_context.tenant_id}:{event_context.space_id}",
        )

        logger.info(
            "Emitted AMBIGUOUS_ENTITY gap to P06",
            extra={
                "mention": mention,
                "candidates": len(candidates),
                "confidence": result.confidence,
            },
        )

    async def record_resolution(
        self,
        result: ResolutionResult,
        event_context: EventContext,
        db_conn: AsyncDBConnection,
    ) -> str:
        """
        Record resolution in st_entity_resolutions for audit.

        Args:
            result: Resolution result
            event_context: Event context
            db_conn: Database connection

        Returns:
            Resolution ID (ULID)
        """
        now_ms = int(time.time() * 1000)

        # Generate ULID-like ID (simplified)
        import uuid

        resolution_id = str(uuid.uuid4())

        await db_conn.execute(
            """
            INSERT INTO st_entity_resolutions (
                resolution_id, tenant_id, space_id,
                mention, selected_entity_id,
                confidence, outcome, breakdown_json,
                candidates_count, session_id,
                created_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
            )
            """,
            resolution_id,
            event_context.tenant_id,
            event_context.space_id,
            result.mention,
            result.selected_entity_id,
            result.confidence,
            result.outcome.value,
            json.dumps(result.breakdown),
            result.candidates_considered,
            event_context.session_id,
            now_ms,
        )

        logger.debug(
            "Recorded entity resolution",
            extra={
                "resolution_id": resolution_id,
                "outcome": result.outcome.value,
            },
        )

        return resolution_id


# =============================================================================
# Factory Function
# =============================================================================


def get_ambiguous_resolver(
    config: Optional[AmbiguousResolverConfig] = None,
) -> AmbiguousEntityResolver:
    """
    Factory function to create an AmbiguousEntityResolver.

    Args:
        config: Optional configuration

    Returns:
        Configured AmbiguousEntityResolver instance
    """
    return AmbiguousEntityResolver(config=config)
