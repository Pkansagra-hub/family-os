"""
DuplicateDetector — M19 SimHash-based deduplication with novelty scoring.

Combines SimHash fingerprinting, two-stage verification, and novelty scoring
to detect duplicates and calculate novelty scores for events.

Scientific Basis:
- SimHash locality-sensitive hashing for O(1) similarity check
- Embedding cosine similarity for semantic verification
- Multiplicative novelty formula with bonuses/penalties

Spec Reference:
- Dossier §7.4.2: M19 DuplicateDetector
- Dossier §4.4.2.1: Adaptive Novelty Bonuses
- M4_EXECUTION.md Issue 4.3.7

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Set, runtime_checkable

from k0.modules.consolidation.algorithms.simhasher import SimHasher
from k0.modules.consolidation.algorithms.two_stage_dedup import (
    DuplicateDecision,
    TwoStageDeduplicator,
)

# =============================================================================
# Constants
# =============================================================================

# Time constants
MS_PER_DAY = 24 * 60 * 60 * 1000

# Default bonus/penalty values (from Dossier §4.4.2.1)
DEFAULT_FIRST_OCCURRENCE_BONUS = 0.15
DEFAULT_MILESTONE_BONUS = 0.20
DEFAULT_RARE_PATTERN_BONUS = 0.10
DEFAULT_TEMPORAL_ANOMALY_BONUS = 0.10
DEFAULT_ROUTINE_PENALTY = 0.30

# Rare pattern threshold (from Dossier §4.4.2.1)
RARE_PATTERN_COUNT_THRESHOLD = 5
RARE_PATTERN_DAYS = 90

# Milestone keywords (from Dossier §7.4.2)
MILESTONE_KEYWORDS = frozenset(
    {
        "birthday",
        "anniversary",
        "graduation",
        "wedding",
        "promotion",
        "retirement",
        "birth",
        "death",
        "engaged",
        "engagement",
        "married",
        "divorce",
        "funeral",
        "memorial",
    }
)

logger = logging.getLogger(__name__)


# =============================================================================
# Protocols
# =============================================================================


@runtime_checkable
class EventStateProtocol(Protocol):
    """
    Protocol for event state objects compatible with duplicate detection.

    This allows the detector to work with any object that has the required
    attributes, not just P03EventState.
    """

    event_id: str
    simhash_hex: str
    content_type: str
    content_text: str
    embedding_768: Optional[List[float]]


@runtime_checkable
class ActivityHistoryProtocol(Protocol):
    """Protocol for activity history lookups."""

    async def get_activity_count(self, activity_type: str, space_id: str, days: int) -> int:
        """Get count of activity occurrences in last N days."""
        ...

    async def get_typical_hours_for_activity(self, activity_type: str, space_id: str) -> Set[int]:
        """Get typical hours (0-23) for this activity type."""
        ...


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class NoveltyBonuses:
    """
    Breakdown of novelty bonuses/penalties applied.

    Used for transparency and debugging of novelty calculations.
    """

    first_occurrence: float = 0.0
    milestone: float = 0.0
    rare_pattern: float = 0.0
    temporal_anomaly: float = 0.0
    routine_penalty: float = 0.0

    @property
    def total_bonus(self) -> float:
        """Net positive bonuses (excluding penalty)."""
        return self.first_occurrence + self.milestone + self.rare_pattern + self.temporal_anomaly


@dataclass
class DuplicationResult:
    """
    Result from duplicate detection and novelty scoring.

    Attributes:
        event_id: ID of the event being checked
        is_duplicate: True if exact duplicate found (hamming=0 or similarity>=0.95)
        near_duplicates: List of event_ids of near-duplicates
        novelty_score: Final novelty score [0, 1]
        duplicate_of: Canonical event ID if this is a duplicate
        match_method: 'SIMHASH', 'EMBEDDING', 'TWO_STAGE', or ''
        max_similarity: Highest similarity to any existing event
        bonuses: Breakdown of applied bonuses/penalties
    """

    event_id: str
    is_duplicate: bool = False
    near_duplicates: List[str] = field(default_factory=list)
    novelty_score: float = 0.5
    duplicate_of: Optional[str] = None
    match_method: str = ""
    max_similarity: float = 0.0
    bonuses: NoveltyBonuses = field(default_factory=NoveltyBonuses)


@dataclass
class DuplicateDetectorConfig:
    """
    Configuration for DuplicateDetector.

    Attributes:
        first_occurrence_bonus: Bonus for first-seen activity category
        milestone_bonus: Bonus for milestone events
        rare_pattern_bonus: Bonus for rare patterns (<5 in 90 days)
        temporal_anomaly_bonus: Bonus for unusual time-of-day
        routine_penalty: Penalty for routine activities
        hamming_threshold: Max Hamming distance for candidates
        exact_duplicate_similarity: Similarity threshold for exact duplicate
        near_duplicate_similarity: Similarity threshold for near-duplicate
    """

    first_occurrence_bonus: float = DEFAULT_FIRST_OCCURRENCE_BONUS
    milestone_bonus: float = DEFAULT_MILESTONE_BONUS
    rare_pattern_bonus: float = DEFAULT_RARE_PATTERN_BONUS
    temporal_anomaly_bonus: float = DEFAULT_TEMPORAL_ANOMALY_BONUS
    routine_penalty: float = DEFAULT_ROUTINE_PENALTY
    hamming_threshold: int = 3
    exact_duplicate_similarity: float = 0.95
    near_duplicate_similarity: float = 0.85

    def validate(self) -> None:
        """Validate configuration."""
        if not (0 <= self.first_occurrence_bonus <= 1):
            raise ValueError("first_occurrence_bonus must be in [0, 1]")
        if not (0 <= self.milestone_bonus <= 1):
            raise ValueError("milestone_bonus must be in [0, 1]")
        if not (0 <= self.rare_pattern_bonus <= 1):
            raise ValueError("rare_pattern_bonus must be in [0, 1]")
        if not (0 <= self.temporal_anomaly_bonus <= 1):
            raise ValueError("temporal_anomaly_bonus must be in [0, 1]")
        if not (0 <= self.routine_penalty <= 1):
            raise ValueError("routine_penalty must be in [0, 1]")
        if self.hamming_threshold < 0:
            raise ValueError("hamming_threshold must be >= 0")

    @classmethod
    def from_learned_bonuses(
        cls, learned: Dict[str, float], **kwargs: Any
    ) -> "DuplicateDetectorConfig":
        """Create config from learned bonus values."""
        return cls(
            first_occurrence_bonus=learned.get("first_occurrence", DEFAULT_FIRST_OCCURRENCE_BONUS),
            milestone_bonus=learned.get("milestone", DEFAULT_MILESTONE_BONUS),
            rare_pattern_bonus=learned.get("rare_pattern", DEFAULT_RARE_PATTERN_BONUS),
            temporal_anomaly_bonus=learned.get("temporal_anomaly", DEFAULT_TEMPORAL_ANOMALY_BONUS),
            **kwargs,
        )


# =============================================================================
# In-Memory Activity History (for testing)
# =============================================================================


class InMemoryActivityHistory:
    """In-memory activity history for testing."""

    def __init__(self) -> None:
        self._counts: Dict[str, Dict[str, int]] = {}  # space_id -> activity -> count
        self._typical_hours: Dict[str, Dict[str, Set[int]]] = {}

    def set_activity_count(self, activity_type: str, space_id: str, count: int) -> None:
        """Set activity count for testing."""
        if space_id not in self._counts:
            self._counts[space_id] = {}
        self._counts[space_id][activity_type] = count

    def set_typical_hours(self, activity_type: str, space_id: str, hours: Set[int]) -> None:
        """Set typical hours for testing."""
        if space_id not in self._typical_hours:
            self._typical_hours[space_id] = {}
        self._typical_hours[space_id][activity_type] = hours

    async def get_activity_count(
        self, activity_type: str, space_id: str, days: int  # noqa: ARG002
    ) -> int:
        """Get activity count."""
        space_counts = self._counts.get(space_id, {})
        return space_counts.get(activity_type, 0)

    async def get_typical_hours_for_activity(self, activity_type: str, space_id: str) -> Set[int]:
        """Get typical hours."""
        space_hours = self._typical_hours.get(space_id, {})
        return space_hours.get(activity_type, set())


# =============================================================================
# DuplicateDetector
# =============================================================================


class DuplicateDetector:
    """
    M19 — SimHash-based deduplication and novelty scoring.

    Combines:
    - SimHash fingerprinting (Issue 4.3.1)
    - Two-stage dedup (Issue 4.3.2)
    - Novelty scoring with bonuses/penalties

    Spec: Dossier §7.4.2
    """

    def __init__(
        self,
        simhasher: SimHasher,
        two_stage_dedup: TwoStageDeduplicator,
        config: Optional[DuplicateDetectorConfig] = None,
    ) -> None:
        self._simhasher = simhasher
        self._two_stage = two_stage_dedup
        self._config = config or DuplicateDetectorConfig()
        self._config.validate()

    @property
    def config(self) -> DuplicateDetectorConfig:
        """Get current configuration."""
        return self._config

    async def detect(
        self,
        event: EventStateProtocol,
        existing_events: List[EventStateProtocol],
        seen_categories: Set[str],
        routine_patterns: Set[str],
        activity_history: Optional[ActivityHistoryProtocol] = None,
        space_id: str = "",
        event_hour: Optional[int] = None,
        activity_type: Optional[str] = None,
    ) -> DuplicationResult:
        """
        Detect duplicates and calculate novelty score.

        Algorithm (from Dossier §7.4.2):
        1. Use two-stage dedup to find duplicates
        2. Identify exact duplicates (hamming=0 or similarity >= 0.95)
        3. Identify near-duplicates (similarity >= 0.85)
        4. Calculate novelty score with bonuses/penalties

        Args:
            event: Event to check
            existing_events: Existing events to check against
            seen_categories: Set of previously seen activity categories
            routine_patterns: Set of routine pattern keys (e.g., "exercise_7")
            activity_history: Optional activity history for rare pattern detection
            space_id: Space ID for history lookups
            event_hour: Hour of day (0-23) for temporal anomaly detection
            activity_type: Activity type for pattern detection

        Returns:
            DuplicationResult with duplicate status and novelty score
        """
        result = DuplicationResult(event_id=event.event_id)

        # Step 1: Find duplicates using two-stage
        matches = self._two_stage.find_duplicates(event, existing_events)

        # Step 2: Identify exact duplicate (best match)
        best_match = self._two_stage.find_best_duplicate(event, existing_events)
        if best_match:
            result.max_similarity = best_match.embedding_similarity
            result.match_method = best_match.check_method

            if (
                best_match.decision_type == DuplicateDecision.DUPLICATE
                or best_match.embedding_similarity >= self._config.exact_duplicate_similarity
            ):
                result.is_duplicate = True
                result.duplicate_of = best_match.event_id
            elif (
                best_match.decision_type == DuplicateDecision.LIKELY_DUPLICATE
                or best_match.embedding_similarity >= self._config.near_duplicate_similarity
            ):
                result.near_duplicates.append(best_match.event_id)

        # Step 3: Collect near-duplicates
        for match in matches:
            if match.event_id != result.duplicate_of:
                if (
                    match.embedding_similarity >= self._config.near_duplicate_similarity
                    and match.event_id not in result.near_duplicates
                ):
                    result.near_duplicates.append(match.event_id)

        # Step 4: Calculate novelty score
        novelty, bonuses = await self._calculate_novelty_score(
            event=event,
            max_similarity=result.max_similarity,
            is_duplicate=result.is_duplicate,
            seen_categories=seen_categories,
            routine_patterns=routine_patterns,
            activity_history=activity_history,
            space_id=space_id,
            event_hour=event_hour,
            activity_type=activity_type,
        )

        result.novelty_score = novelty
        result.bonuses = bonuses

        logger.debug(
            "Duplicate detection complete",
            extra={
                "event_id": event.event_id,
                "is_duplicate": result.is_duplicate,
                "near_duplicates": len(result.near_duplicates),
                "novelty_score": result.novelty_score,
                "max_similarity": result.max_similarity,
            },
        )

        return result

    async def _calculate_novelty_score(
        self,
        event: EventStateProtocol,
        max_similarity: float,
        is_duplicate: bool,
        seen_categories: Set[str],
        routine_patterns: Set[str],
        activity_history: Optional[ActivityHistoryProtocol],
        space_id: str,
        event_hour: Optional[int],
        activity_type: Optional[str],
    ) -> tuple[float, NoveltyBonuses]:
        """
        Calculate novelty score using dossier formula.

        Formula (from Dossier §7.4.2):
        novelty = base_novelty × (1 + first_time_bonus) × (1 + milestone_bonus)
                  × (1 + rare_pattern_bonus) × (1 + temporal_anomaly_bonus)
                  × (1 - routine_penalty)

        Returns:
            Tuple of (novelty_score, bonuses_breakdown)
        """
        bonuses = NoveltyBonuses()

        # Exact duplicates have zero novelty
        if is_duplicate:
            return (0.0, bonuses)

        # Base novelty from similarity (1 - max_similarity)
        base_novelty = 1.0 - max_similarity

        # First occurrence bonus
        if activity_type and activity_type not in seen_categories:
            bonuses.first_occurrence = self._config.first_occurrence_bonus

        # Milestone bonus
        if self._is_milestone_event(event):
            bonuses.milestone = self._config.milestone_bonus

        # Rare pattern bonus (requires history lookup)
        if activity_type and activity_history:
            is_rare = await self._is_rare_pattern(activity_type, activity_history, space_id)
            if is_rare:
                bonuses.rare_pattern = self._config.rare_pattern_bonus

        # Temporal anomaly bonus
        if activity_type and event_hour is not None and activity_history:
            is_anomaly = await self._is_temporal_anomaly(
                activity_type, event_hour, activity_history, space_id
            )
            if is_anomaly:
                bonuses.temporal_anomaly = self._config.temporal_anomaly_bonus

        # Routine penalty
        if activity_type and event_hour is not None:
            routine_key = f"{activity_type}_{event_hour}"
            if routine_key in routine_patterns:
                bonuses.routine_penalty = self._config.routine_penalty

        # Apply multiplicative formula
        novelty = (
            base_novelty
            * (1 + bonuses.first_occurrence)
            * (1 + bonuses.milestone)
            * (1 + bonuses.rare_pattern)
            * (1 + bonuses.temporal_anomaly)
            * (1 - bonuses.routine_penalty)
        )

        # Clamp to [0, 1]
        novelty = max(0.0, min(1.0, novelty))

        return (novelty, bonuses)

    def _is_milestone_event(self, event: EventStateProtocol) -> bool:
        """
        Check if event is a milestone (birthday, anniversary, etc.).

        From Dossier §7.4.2: Check for milestone keywords in content.
        """
        content_lower = event.content_text.lower()
        return any(keyword in content_lower for keyword in MILESTONE_KEYWORDS)

    async def _is_rare_pattern(
        self,
        activity_type: str,
        activity_history: ActivityHistoryProtocol,
        space_id: str,
    ) -> bool:
        """
        Check if activity appears < 5 times in 90 days.

        From Dossier §4.4.2.1: Rare pattern threshold.
        """
        count = await activity_history.get_activity_count(
            activity_type, space_id, RARE_PATTERN_DAYS
        )
        return count < RARE_PATTERN_COUNT_THRESHOLD

    async def _is_temporal_anomaly(
        self,
        activity_type: str,
        event_hour: int,
        activity_history: ActivityHistoryProtocol,
        space_id: str,
    ) -> bool:
        """
        Check if time-of-day is unusual for this activity type.

        From Dossier §4.4.2.1: Temporal anomaly detection.
        """
        typical_hours = await activity_history.get_typical_hours_for_activity(
            activity_type, space_id
        )
        if not typical_hours:
            # No history, not an anomaly
            return False
        return event_hour not in typical_hours


# =============================================================================
# Utility Functions
# =============================================================================


def is_milestone_content(text: str) -> bool:
    """Check if text contains milestone keywords."""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in MILESTONE_KEYWORDS)


def compute_base_novelty(max_similarity: float) -> float:
    """Compute base novelty from similarity."""
    return max(0.0, min(1.0, 1.0 - max_similarity))
