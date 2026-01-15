"""
R4 Adaptive Merge Thresholds — Per-entity-type similarity thresholds with learning.

Issue: 4.4.6 - Implement adaptive merge thresholds per entity type
Spec Reference: Dossier §4.5.1.1, M4_EXECUTION.md

This module provides per-entity-type similarity thresholds for merge decisions,
with learning from feedback to improve accuracy over time.

Architecture:
- Per-type default thresholds (FAMILY_MEMBER=0.90, CONCEPT=0.65, etc.)
- Learning rates for different feedback signals
- Threshold bounds to prevent extreme values
- Persistence to st_learned_weights

Performance:
- Threshold lookup: O(1)
- Threshold adjustment: O(1)
- Database persistence: O(1)

Human Memory Model:
- FAMILY_MEMBER threshold is highest (0.90) — merging wrong family members is catastrophic
- CONCEPT threshold is lowest (0.65) — abstract concepts can be more liberally merged
- Learning adjusts based on merge corrections from user feedback

Related:
- k0/modules/consolidation/algorithms/entity_disambiguator.py: Uses thresholds
- k0/db/alembic/versions/0040_st_learned_weights.py: Threshold storage
- k0/pipelines/p03/feedback_consumer.py: Feedback signals

Author: K0 Architecture Team
Date: 2025-01-03
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Constants
# =============================================================================

# Learning rates for feedback signals (from Dossier §4.5.1.1)
P03_MERGE_LEARNING_RATE_FP: float = 0.02  # False positive: raise threshold
P03_MERGE_LEARNING_RATE_STRONG_FP: float = 0.05  # Strong FP (split request): raise more
P03_MERGE_LEARNING_RATE_FN: float = -0.02  # False negative: lower threshold
P03_MERGE_LEARNING_RATE_CONFIRM: float = 0.0  # Correct: no change

# Default threshold for unknown entity types
P03_MERGE_THRESHOLD_DEFAULT: float = 0.75


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True)
class ThresholdBounds:
    """Learning bounds for a threshold.

    Attributes:
        min_value: Minimum allowed threshold value
        max_value: Maximum allowed threshold value
        default: Default starting threshold
    """

    min_value: float
    max_value: float
    default: float

    def clamp(self, value: float) -> float:
        """Clamp value within bounds."""
        return max(self.min_value, min(self.max_value, value))


@dataclass
class ThresholdAdjustment:
    """Result of threshold adjustment.

    Attributes:
        entity_type: Entity type that was adjusted
        old_threshold: Previous threshold value
        new_threshold: New threshold value after adjustment
        adjustment: The delta applied
        reason: Feedback signal that triggered adjustment
    """

    entity_type: str
    old_threshold: float
    new_threshold: float
    adjustment: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_type": self.entity_type,
            "old_threshold": round(self.old_threshold, 4),
            "new_threshold": round(self.new_threshold, 4),
            "adjustment": round(self.adjustment, 4),
            "reason": self.reason,
        }


@dataclass
class MergeDecision:
    """Result of should_merge decision.

    Attributes:
        should_merge: Whether entities should be merged
        similarity_score: The similarity score between entities
        threshold: The threshold used for decision
        entity_type: Entity type used for threshold lookup
    """

    should_merge: bool
    similarity_score: float
    threshold: float
    entity_type: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "should_merge": self.should_merge,
            "similarity_score": round(self.similarity_score, 4),
            "threshold": round(self.threshold, 4),
            "entity_type": self.entity_type,
        }


@dataclass
class ThresholdMetrics:
    """Metrics for threshold operations."""

    total_decisions: int = 0
    merge_count: int = 0
    reject_count: int = 0
    adjustments_up: int = 0
    adjustments_down: int = 0
    total_adjustments: int = 0
    no_merge_count: int = 0
    decisions_by_type: Dict[str, int] = field(default_factory=dict)


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


# =============================================================================
# Threshold Configuration
# =============================================================================

# Default thresholds and bounds per entity type (from Dossier §4.5.1.1)
DEFAULT_THRESHOLD_BOUNDS: Dict[str, ThresholdBounds] = {
    # Highest stakes - rarely merge
    "FAMILY_MEMBER": ThresholdBounds(0.85, 0.98, 0.90),
    # Names matter, moderate caution
    "PERSON": ThresholdBounds(0.80, 0.95, 0.85),
    # Locations have synonyms
    "PLACE": ThresholdBounds(0.65, 0.85, 0.75),
    "LOCATION": ThresholdBounds(0.65, 0.85, 0.75),  # Alias for PLACE
    # Company names vary
    "ORGANIZATION": ThresholdBounds(0.70, 0.90, 0.80),
    # Objects have many synonyms (couch/sofa)
    "THING": ThresholdBounds(0.60, 0.80, 0.70),
    "OBJECT": ThresholdBounds(0.60, 0.80, 0.70),  # Alias for THING
    # Abstract concepts, liberal merging OK
    "CONCEPT": ThresholdBounds(0.55, 0.75, 0.65),
    # Activities can overlap
    "EVENT": ThresholdBounds(0.65, 0.85, 0.75),
    # Time references need precision
    "TEMPORAL": ThresholdBounds(0.70, 0.90, 0.80),
}

# Learning rates for different feedback signals
FEEDBACK_LEARNING_RATES: Dict[str, float] = {
    "MERGE_CONFIRMED": P03_MERGE_LEARNING_RATE_CONFIRM,  # Correct, no change
    "MERGE_REJECTED": P03_MERGE_LEARNING_RATE_FP,  # False positive: raise threshold
    "SPLIT_REQUEST": P03_MERGE_LEARNING_RATE_STRONG_FP,  # Strong FP: raise more
    "MISSED_MERGE": P03_MERGE_LEARNING_RATE_FN,  # False negative: lower threshold
}


# =============================================================================
# Adaptive Merge Thresholds
# =============================================================================


class AdaptiveMergeThresholds:
    """
    Per-entity-type merge thresholds with learning.

    Spec: Dossier §4.5.1.1

    Different entity types require different merge thresholds:
    - FAMILY_MEMBER: Very high (0.90) — merging wrong family members is catastrophic
    - CONCEPT: Lower (0.65) — abstract concepts can be more liberally merged
    - THING: Moderate (0.70) — objects have synonyms ("couch"/"sofa")

    Learning adjusts thresholds based on merge corrections:
    - MERGE_REJECTED: Raise threshold (+0.02) — we merged too aggressively
    - SPLIT_REQUEST: Raise more (+0.05) — strong signal we're wrong
    - MISSED_MERGE: Lower threshold (-0.02) — we should have merged

    All thresholds are clamped within bounds to prevent extreme values.

    Usage:
        thresholds = AdaptiveMergeThresholds()

        decision = thresholds.should_merge("PERSON", 0.88)
        if decision.should_merge:
            # Merge entities

        # On feedback
        adjustment = thresholds.adjust_threshold("PERSON", "MERGE_REJECTED")
        await thresholds.persist_threshold("PERSON", db_conn)
    """

    def __init__(
        self,
        learned_thresholds: Optional[Dict[str, float]] = None,
        threshold_bounds: Optional[Dict[str, ThresholdBounds]] = None,
    ) -> None:
        """
        Initialize with optional learned thresholds.

        Args:
            learned_thresholds: Override defaults from st_learned_weights
            threshold_bounds: Custom bounds (uses DEFAULT_THRESHOLD_BOUNDS if None)
        """
        self._bounds = threshold_bounds or DEFAULT_THRESHOLD_BOUNDS
        self._thresholds: Dict[str, float] = {}
        self._metrics = ThresholdMetrics()

        # Initialize with defaults
        for entity_type, bounds in self._bounds.items():
            self._thresholds[entity_type] = bounds.default

        # Apply learned overrides
        if learned_thresholds:
            for entity_type, threshold in learned_thresholds.items():
                if entity_type in self._bounds:
                    # Validate within bounds
                    bounds = self._bounds[entity_type]
                    self._thresholds[entity_type] = bounds.clamp(threshold)
                else:
                    # Unknown type, use default bounds
                    self._thresholds[entity_type] = max(0.50, min(0.95, threshold))

    @property
    def thresholds(self) -> Dict[str, float]:
        """Return copy of current thresholds."""
        return dict(self._thresholds)

    @property
    def metrics(self) -> ThresholdMetrics:
        """Return metrics."""
        return self._metrics

    def get_threshold(self, entity_type: str) -> float:
        """
        Get merge threshold for entity type.

        Args:
            entity_type: Entity type (PERSON, FAMILY_MEMBER, CONCEPT, etc.)

        Returns:
            Threshold value (returns P03_MERGE_THRESHOLD_DEFAULT for unknown types)
        """
        return self._thresholds.get(
            entity_type.upper(),
            P03_MERGE_THRESHOLD_DEFAULT,
        )

    def get_bounds(self, entity_type: str) -> ThresholdBounds:
        """
        Get bounds for entity type.

        Args:
            entity_type: Entity type

        Returns:
            ThresholdBounds for the type
        """
        return self._bounds.get(
            entity_type.upper(),
            ThresholdBounds(0.60, 0.90, P03_MERGE_THRESHOLD_DEFAULT),
        )

    def should_merge(
        self,
        entity_type: str,
        similarity_score: float,
    ) -> MergeDecision:
        """
        Determine if entities should be merged.

        Args:
            entity_type: Entity type for threshold lookup
            similarity_score: Similarity score between entities [0, 1]

        Returns:
            MergeDecision with should_merge, score, and threshold
        """
        entity_type_upper = entity_type.upper()
        threshold = self.get_threshold(entity_type_upper)
        should_merge = similarity_score >= threshold

        # Update metrics
        self._metrics.total_decisions += 1
        if should_merge:
            self._metrics.merge_count += 1
        else:
            self._metrics.reject_count += 1

        type_count = self._metrics.decisions_by_type.get(entity_type_upper, 0)
        self._metrics.decisions_by_type[entity_type_upper] = type_count + 1

        decision = MergeDecision(
            should_merge=should_merge,
            similarity_score=similarity_score,
            threshold=threshold,
            entity_type=entity_type_upper,
        )

        logger.debug(
            "Merge decision",
            extra={
                "entity_type": entity_type_upper,
                "similarity": round(similarity_score, 4),
                "threshold": round(threshold, 4),
                "should_merge": should_merge,
            },
        )

        return decision

    def adjust_threshold(
        self,
        entity_type: str,
        feedback_signal: str,
    ) -> ThresholdAdjustment:
        """
        Adjust threshold based on feedback.

        Feedback signals:
        - MERGE_CONFIRMED: Correct merge, no change
        - MERGE_REJECTED: False positive, raise threshold (+0.02)
        - SPLIT_REQUEST: Strong FP, raise more (+0.05)
        - MISSED_MERGE: False negative, lower threshold (-0.02)

        Args:
            entity_type: Entity type to adjust
            feedback_signal: Type of feedback received

        Returns:
            ThresholdAdjustment with old/new values and reason
        """
        entity_type_upper = entity_type.upper()
        old_threshold = self.get_threshold(entity_type_upper)
        adjustment = FEEDBACK_LEARNING_RATES.get(feedback_signal.upper(), 0.0)

        new_threshold = old_threshold + adjustment

        # Get bounds for this type and clamp
        bounds = self.get_bounds(entity_type_upper)
        new_threshold = bounds.clamp(new_threshold)

        # Update internal state
        self._thresholds[entity_type_upper] = new_threshold

        # Update metrics
        if adjustment > 0:
            self._metrics.adjustments_up += 1
        elif adjustment < 0:
            self._metrics.adjustments_down += 1

        result = ThresholdAdjustment(
            entity_type=entity_type_upper,
            old_threshold=old_threshold,
            new_threshold=new_threshold,
            adjustment=adjustment,
            reason=feedback_signal,
        )

        logger.info(
            "Threshold adjusted",
            extra={
                "entity_type": entity_type_upper,
                "old": round(old_threshold, 4),
                "new": round(new_threshold, 4),
                "adjustment": round(adjustment, 4),
                "signal": feedback_signal,
            },
        )

        return result

    async def persist_threshold(
        self,
        entity_type: str,
        db_conn: AsyncDBConnection,
        space_id: str = "default",
    ) -> bool:
        """
        Persist learned threshold to st_learned_weights.

        Args:
            entity_type: Entity type to persist
            db_conn: Database connection
            space_id: Space isolation key

        Returns:
            True if successful
        """
        entity_type_upper = entity_type.upper()
        threshold = self._thresholds.get(entity_type_upper)
        if threshold is None:
            return False

        now_ms = int(time.time() * 1000)

        await db_conn.execute(
            """
            INSERT INTO st_learned_weights
                (param_id, param_key, param_scope, scope_id, space_id,
                 current_value, prior_value, confidence, sample_count,
                 updated_at, created_at)
            VALUES
                (gen_random_uuid(), 'similarity_threshold', 'entity_type', $1, $2,
                 $3, $4, 0.5, 1, $5, $5)
            ON CONFLICT (space_id, param_key, param_scope, scope_id)
            DO UPDATE SET
                current_value = EXCLUDED.current_value,
                sample_count = st_learned_weights.sample_count + 1,
                updated_at = EXCLUDED.updated_at
            """,
            entity_type_upper,
            space_id,
            threshold,
            self.get_bounds(entity_type_upper).default,
            now_ms,
        )

        logger.debug(
            "Persisted threshold",
            extra={
                "entity_type": entity_type_upper,
                "threshold": round(threshold, 4),
                "space_id": space_id,
            },
        )

        return True

    async def persist_all_thresholds(
        self,
        db_conn: AsyncDBConnection,
        space_id: str = "default",
    ) -> int:
        """
        Persist all learned thresholds to st_learned_weights.

        Args:
            db_conn: Database connection
            space_id: Space isolation key

        Returns:
            Count of thresholds persisted
        """
        count = 0
        for entity_type in self._thresholds:
            if await self.persist_threshold(entity_type, db_conn, space_id):
                count += 1
        return count

    @classmethod
    async def load_from_database(
        cls,
        db_conn: AsyncDBConnection,
        space_id: str = "default",
    ) -> "AdaptiveMergeThresholds":
        """
        Load learned thresholds from st_learned_weights.

        Args:
            db_conn: Database connection
            space_id: Space isolation key

        Returns:
            AdaptiveMergeThresholds instance with learned values
        """
        rows = await db_conn.fetch(
            """
            SELECT scope_id, current_value
            FROM st_learned_weights
            WHERE param_key = 'similarity_threshold'
              AND param_scope = 'entity_type'
              AND space_id = $1
            """,
            space_id,
        )

        learned: Dict[str, float] = {}
        for row in rows:
            entity_type = row["scope_id"]
            threshold = float(row["current_value"])
            learned[entity_type] = threshold

        logger.info(
            "Loaded thresholds from database",
            extra={
                "count": len(learned),
                "space_id": space_id,
            },
        )

        return cls(learned_thresholds=learned)

    def get_all_defaults(self) -> Dict[str, float]:
        """
        Get all default thresholds.

        Returns:
            Dict mapping entity types to default thresholds
        """
        return {entity_type: bounds.default for entity_type, bounds in self._bounds.items()}


# =============================================================================
# Factory Function
# =============================================================================


def get_adaptive_merge_thresholds(
    learned_thresholds: Optional[Dict[str, float]] = None,
) -> AdaptiveMergeThresholds:
    """
    Factory function to create AdaptiveMergeThresholds.

    Args:
        learned_thresholds: Optional learned thresholds override

    Returns:
        Configured AdaptiveMergeThresholds instance
    """
    return AdaptiveMergeThresholds(learned_thresholds=learned_thresholds)
