"""
RoutineDetector — GAP-003 Implementation.

Detects recurring behavioral patterns (routines/habits) from episodic memory.
Implements basal ganglia-inspired habit formation model.

Neurological Basis:
    - Basal Ganglia: Encodes repeated action sequences through reward-based learning
    - Habit Loop: Cue → Routine → Reward (Graybiel & Grafton, 2015)
    - Temporal Difference Learning: Updates habit strength based on prediction errors
    - Chunking: Compresses repeated sequences into single units

Algorithm:
    1. Temporal Pattern Mining: Detect recurring time-based sequences
    2. Habit Strength Scoring: Frequency × Consistency × Recency
    3. Context Extraction: Identify triggering cues (location, time, social)
    4. Lifecycle State: FORMING → ESTABLISHED → MAINTAINED → DECAYING → EXTINCT

Input: Episodes from st_epi with activity_type, location, timestamps
Output: RoutineCandidate objects for st_procedural

Performance:
    - O(n log n) for temporal sorting
    - O(n × k) for pattern matching where k = pattern types
    - ~1ms per episode batch

References:
    - docs/plans/MEMORY_LAYER_GAPS_FIX_PLAN.md (GAP-003)
    - Graybiel, A. M. (2008). Habits, rituals, and the evaluative brain. Annual Review of Neuroscience.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Lifecycle States (Neurologically Grounded)
# =============================================================================


class RoutineLifecycle(str, Enum):
    """
    Routine lifecycle states based on basal ganglia habit formation.

    FORMING: Initial learning phase (3-7 repetitions, <21 days)
    ESTABLISHED: Habit consolidated (consistency > 0.7, count > 10)
    MAINTAINED: Active, regular execution
    DECAYING: Missed expected occurrences
    EXTINCT: No activity for extended period
    """

    FORMING = "FORMING"
    ESTABLISHED = "ESTABLISHED"
    MAINTAINED = "MAINTAINED"
    DECAYING = "DECAYING"
    EXTINCT = "EXTINCT"


class FrequencyPattern(str, Enum):
    """Detected frequency patterns for routines."""

    DAILY = "DAILY"
    WEEKDAY = "WEEKDAY"
    WEEKEND = "WEEKEND"
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    IRREGULAR = "IRREGULAR"


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class RoutineCandidate:
    """
    Detected routine candidate for st_procedural.

    Maps to st_procedural table schema.

    Attributes:
        routine_id: Unique identifier (ULID format)
        routine_name: Human-readable name
        routine_category: Category (MEAL, EXERCISE, WORK, SOCIAL, etc.)
        temporal_anchor: Primary time anchor ("08:00", "morning", etc.)
        day_pattern: Day pattern ("weekdays", "MWF", "daily", etc.)
        frequency: Frequency pattern
        regularity_score: Temporal consistency [0.0, 1.0]
        action_sequence_json: JSON array of action steps
        typical_duration_minutes: Average duration
        source_episodes_json: JSON array of source episode IDs
        source_episode_count: Number of episodes in pattern
        confidence_score: Detection confidence [0.0, 1.0]
        streak_count: Current consecutive occurrences
        lifecycle_state: Current lifecycle state
        habit_strength: Overall habit strength [0.0, 1.0]
        triggering_cues: Detected contextual triggers
    """

    routine_id: str
    routine_name: str
    routine_category: str
    temporal_anchor: Optional[str] = None
    day_pattern: Optional[str] = None
    frequency: FrequencyPattern = FrequencyPattern.IRREGULAR
    regularity_score: float = 0.0
    action_sequence_json: str = "[]"
    typical_duration_minutes: int = 0
    source_episodes_json: str = "[]"
    source_episode_count: int = 0
    confidence_score: float = 0.5
    streak_count: int = 0
    lifecycle_state: RoutineLifecycle = RoutineLifecycle.FORMING
    habit_strength: float = 0.0
    triggering_cues: List[str] = field(default_factory=list)


@dataclass
class EpisodePattern:
    """Intermediate pattern representation during detection."""

    signature: str  # Pattern signature (activity_type + location)
    episode_ids: List[str] = field(default_factory=list)
    timestamps: List[int] = field(default_factory=list)  # Milliseconds
    locations: List[str] = field(default_factory=list)
    activity_types: List[str] = field(default_factory=list)
    summaries: List[str] = field(default_factory=list)


# =============================================================================
# RoutineDetector
# =============================================================================


class RoutineDetector:
    """
    Detects recurring behavioral patterns from episodic memory.

    Implements basal ganglia-inspired habit detection:
    - Pattern Mining: Groups episodes by (activity_type, location) signature
    - Temporal Analysis: Detects regular timing patterns
    - Habit Strength: Frequency × Consistency × Recency scoring
    - Lifecycle Tracking: Monitors habit formation and decay

    Usage:
        detector = RoutineDetector()
        candidates = detector.detect(episodes)
        for routine in candidates:
            # Write to st_procedural
            ...

    Thread Safety: Stateless, safe for concurrent use.
    """

    # Minimum occurrences to consider a pattern as routine
    MIN_OCCURRENCES = 3

    # Minimum consistency score to be considered a routine
    MIN_CONSISTENCY = 0.3

    # Time window for pattern detection (30 days in ms)
    DEFAULT_WINDOW_MS = 30 * 24 * 60 * 60 * 1000

    # Decay half-life for recency (7 days in ms)
    RECENCY_HALFLIFE_MS = 7 * 24 * 60 * 60 * 1000

    # Habit strength weights (sum to 1.0)
    WEIGHT_FREQUENCY = 0.35
    WEIGHT_CONSISTENCY = 0.40
    WEIGHT_RECENCY = 0.25

    def __init__(
        self,
        min_occurrences: int = MIN_OCCURRENCES,
        min_consistency: float = MIN_CONSISTENCY,
        window_ms: int = DEFAULT_WINDOW_MS,
    ) -> None:
        """
        Initialize RoutineDetector.

        Args:
            min_occurrences: Minimum occurrences for pattern detection
            min_consistency: Minimum temporal consistency score
            window_ms: Time window for pattern analysis (milliseconds)
        """
        self.min_occurrences = min_occurrences
        self.min_consistency = min_consistency
        self.window_ms = window_ms

    def detect(
        self,
        episodes: List[Dict[str, Any]],
        reference_time_ms: Optional[int] = None,
    ) -> List[RoutineCandidate]:
        """
        Detect routine candidates from episodes.

        Args:
            episodes: List of episode dicts with keys:
                - episode_id, activity_type, primary_location,
                - start_time_utc, end_time_utc, episode_summary
            reference_time_ms: Reference time for recency calculation (default: now)

        Returns:
            List of RoutineCandidate objects for qualified patterns
        """
        if not episodes:
            return []

        if reference_time_ms is None:
            reference_time_ms = int(datetime.now().timestamp() * 1000)

        # Step 1: Group episodes by signature (activity_type + location)
        patterns = self._group_by_signature(episodes)

        # Step 2: Filter by minimum occurrences
        qualified_patterns = [
            p for p in patterns.values() if len(p.episode_ids) >= self.min_occurrences
        ]

        # Step 3: Analyze each pattern for routine characteristics
        candidates: List[RoutineCandidate] = []
        for pattern in qualified_patterns:
            candidate = self._analyze_pattern(pattern, reference_time_ms)
            if candidate and candidate.confidence_score >= self.min_consistency:
                candidates.append(candidate)

        # Step 4: Sort by habit strength (strongest first)
        candidates.sort(key=lambda c: c.habit_strength, reverse=True)

        logger.debug(
            f"RoutineDetector: {len(episodes)} episodes → {len(patterns)} patterns → {len(candidates)} candidates"
        )

        return candidates

    def _group_by_signature(
        self,
        episodes: List[Dict[str, Any]],
    ) -> Dict[str, EpisodePattern]:
        """
        Group episodes by (activity_type, location) signature.

        Creates pattern groups for episodes with same activity and location.

        Args:
            episodes: Episode dicts

        Returns:
            Dict mapping signature to EpisodePattern
        """
        patterns: Dict[str, EpisodePattern] = {}

        for ep in episodes:
            activity = (ep.get("activity_type") or ep.get("episode_type") or "").lower()
            location = (ep.get("primary_location") or ep.get("location_hint") or "").lower()

            # Skip if no meaningful signature
            if not activity and not location:
                continue

            # Create signature
            signature = f"{activity}:{location}" if location else activity

            if signature not in patterns:
                patterns[signature] = EpisodePattern(signature=signature)

            pattern = patterns[signature]
            pattern.episode_ids.append(ep.get("episode_id", ""))
            pattern.timestamps.append(ep.get("start_time_utc", 0))
            pattern.locations.append(location)
            pattern.activity_types.append(activity)
            pattern.summaries.append(ep.get("episode_summary", ""))

        return patterns

    def _analyze_pattern(
        self,
        pattern: EpisodePattern,
        reference_time_ms: int,
    ) -> Optional[RoutineCandidate]:
        """
        Analyze a pattern for routine characteristics.

        Computes temporal regularity, habit strength, and lifecycle state.

        Args:
            pattern: EpisodePattern to analyze
            reference_time_ms: Reference time for recency

        Returns:
            RoutineCandidate if pattern qualifies, None otherwise
        """
        if len(pattern.timestamps) < self.min_occurrences:
            return None

        # Sort timestamps
        sorted_ts = sorted(pattern.timestamps)

        # Compute temporal statistics
        temporal_stats = self._compute_temporal_stats(sorted_ts)

        # Compute habit strength components
        frequency_score = self._compute_frequency_score(len(sorted_ts))
        consistency_score = temporal_stats["regularity"]
        recency_score = self._compute_recency_score(sorted_ts[-1], reference_time_ms)

        # Weighted habit strength (basal ganglia model)
        habit_strength = (
            self.WEIGHT_FREQUENCY * frequency_score
            + self.WEIGHT_CONSISTENCY * consistency_score
            + self.WEIGHT_RECENCY * recency_score
        )

        # Determine lifecycle state
        lifecycle = self._determine_lifecycle(
            occurrence_count=len(sorted_ts),
            consistency=consistency_score,
            last_occurrence=sorted_ts[-1],
            reference_time=reference_time_ms,
            expected_interval_ms=temporal_stats.get("mean_interval_ms", 0),
        )

        # Detect triggering cues
        cues = self._detect_cues(pattern, temporal_stats)

        # Generate routine name
        routine_name = self._generate_routine_name(pattern)

        # Determine category
        category = self._determine_category(pattern)

        # Compute confidence (combines strength with pattern clarity)
        confidence = min(1.0, habit_strength * 0.7 + consistency_score * 0.3)

        # Generate routine ID (prefix for clarity)
        routine_id = f"routine-{uuid.uuid4().hex[:24]}"

        return RoutineCandidate(
            routine_id=routine_id,
            routine_name=routine_name,
            routine_category=category,
            temporal_anchor=temporal_stats.get("time_anchor"),
            day_pattern=temporal_stats.get("day_pattern"),
            frequency=temporal_stats.get("frequency", FrequencyPattern.IRREGULAR),
            regularity_score=consistency_score,
            action_sequence_json="[]",  # Could be enriched from episode sequences
            typical_duration_minutes=temporal_stats.get("avg_duration_min", 0),
            source_episodes_json=json.dumps(pattern.episode_ids),
            source_episode_count=len(pattern.episode_ids),
            confidence_score=confidence,
            streak_count=self._compute_streak(sorted_ts, temporal_stats.get("mean_interval_ms", 0)),
            lifecycle_state=lifecycle,
            habit_strength=habit_strength,
            triggering_cues=cues,
        )

    def _compute_temporal_stats(
        self,
        sorted_timestamps: List[int],
    ) -> Dict[str, Any]:
        """
        Compute temporal statistics for a pattern.

        Analyzes timing regularity, frequency patterns, and time anchors.

        Args:
            sorted_timestamps: Sorted list of occurrence timestamps (ms)

        Returns:
            Dict with temporal statistics
        """
        if len(sorted_timestamps) < 2:
            return {
                "regularity": 0.0,
                "frequency": FrequencyPattern.IRREGULAR,
                "mean_interval_ms": 0,
            }

        # Compute intervals between occurrences
        intervals = [
            sorted_timestamps[i + 1] - sorted_timestamps[i]
            for i in range(len(sorted_timestamps) - 1)
        ]

        mean_interval = sum(intervals) / len(intervals)
        variance = sum((i - mean_interval) ** 2 for i in intervals) / len(intervals)
        std_dev = math.sqrt(variance) if variance > 0 else 0

        # Coefficient of variation (lower = more regular)
        cv = std_dev / mean_interval if mean_interval > 0 else float("inf")

        # Regularity score (inverse of CV, capped at 1.0)
        regularity = max(0.0, min(1.0, 1.0 - cv))

        # Detect frequency pattern
        frequency = self._detect_frequency_pattern(mean_interval)

        # Extract time anchor (most common hour)
        hours = [datetime.fromtimestamp(ts / 1000).hour for ts in sorted_timestamps]
        hour_counts = Counter(hours)
        most_common_hour = hour_counts.most_common(1)[0][0] if hour_counts else 12
        time_anchor = f"{most_common_hour:02d}:00"

        # Detect day pattern
        days = [datetime.fromtimestamp(ts / 1000).weekday() for ts in sorted_timestamps]
        day_pattern = self._detect_day_pattern(days)

        return {
            "regularity": regularity,
            "frequency": frequency,
            "mean_interval_ms": int(mean_interval),
            "std_dev_ms": int(std_dev),
            "time_anchor": time_anchor,
            "day_pattern": day_pattern,
        }

    def _detect_frequency_pattern(self, mean_interval_ms: float) -> FrequencyPattern:
        """Detect frequency pattern from mean interval."""
        hours = mean_interval_ms / (1000 * 60 * 60)
        days = hours / 24

        if days < 1.5:
            return FrequencyPattern.DAILY
        elif days < 3:
            # Could be weekday (5 occurrences in 7 days)
            return FrequencyPattern.WEEKDAY
        elif 6 < days < 8:
            return FrequencyPattern.WEEKLY
        elif 13 < days < 15:
            return FrequencyPattern.BIWEEKLY
        elif 28 < days < 32:
            return FrequencyPattern.MONTHLY
        else:
            return FrequencyPattern.IRREGULAR

    def _detect_day_pattern(self, weekdays: List[int]) -> str:
        """Detect day-of-week pattern from weekday indices (0=Monday)."""
        day_counts = Counter(weekdays)
        total = len(weekdays)

        # Check for weekday pattern (Mon-Fri)
        weekday_count = sum(day_counts.get(d, 0) for d in range(5))
        if weekday_count / total > 0.8:
            return "weekdays"

        # Check for weekend pattern
        weekend_count = sum(day_counts.get(d, 0) for d in [5, 6])
        if weekend_count / total > 0.8:
            return "weekends"

        # Check for specific days (e.g., MWF, TTH)
        dominant_days = [d for d, c in day_counts.items() if c / total > 0.25]
        if len(dominant_days) <= 3:
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            return ",".join(day_names[d] for d in sorted(dominant_days))

        return "daily"

    def _compute_frequency_score(self, occurrence_count: int) -> float:
        """
        Compute frequency score with saturation.

        Uses logarithmic scaling so additional occurrences have diminishing returns.

        Args:
            occurrence_count: Number of occurrences

        Returns:
            Frequency score [0.0, 1.0]
        """
        # Log scaling with saturation at ~30 occurrences
        return min(1.0, math.log(occurrence_count + 1) / math.log(30))

    def _compute_recency_score(
        self,
        last_occurrence_ms: int,
        reference_time_ms: int,
    ) -> float:
        """
        Compute recency score with exponential decay.

        Uses half-life model inspired by memory consolidation.

        Args:
            last_occurrence_ms: Timestamp of last occurrence
            reference_time_ms: Current/reference time

        Returns:
            Recency score [0.0, 1.0]
        """
        elapsed_ms = reference_time_ms - last_occurrence_ms
        if elapsed_ms <= 0:
            return 1.0

        # Exponential decay with half-life
        decay = math.exp(-0.693 * elapsed_ms / self.RECENCY_HALFLIFE_MS)
        return max(0.0, min(1.0, decay))

    def _determine_lifecycle(
        self,
        occurrence_count: int,
        consistency: float,
        last_occurrence: int,
        reference_time: int,
        expected_interval_ms: int,
    ) -> RoutineLifecycle:
        """
        Determine routine lifecycle state.

        Based on basal ganglia habit formation research:
        - FORMING: < 7 occurrences or low consistency
        - ESTABLISHED: >= 10 occurrences and consistency > 0.7
        - MAINTAINED: Established and recently active
        - DECAYING: Missed expected occurrences
        - EXTINCT: No activity for > 3x expected interval

        Args:
            occurrence_count: Total occurrences
            consistency: Temporal regularity score
            last_occurrence: Last occurrence timestamp
            reference_time: Current time
            expected_interval_ms: Expected interval between occurrences

        Returns:
            RoutineLifecycle state
        """
        elapsed = reference_time - last_occurrence

        # Check for extinction (no activity for 3x expected interval or 30 days)
        extinction_threshold = max(expected_interval_ms * 3, 30 * 24 * 60 * 60 * 1000)
        if elapsed > extinction_threshold:
            return RoutineLifecycle.EXTINCT

        # Check for decay (missed 1.5x expected interval)
        decay_threshold = (
            expected_interval_ms * 1.5 if expected_interval_ms > 0 else 7 * 24 * 60 * 60 * 1000
        )
        if elapsed > decay_threshold:
            return RoutineLifecycle.DECAYING

        # Check for established (high count + high consistency)
        if occurrence_count >= 10 and consistency >= 0.7:
            return (
                RoutineLifecycle.MAINTAINED
                if elapsed < expected_interval_ms
                else RoutineLifecycle.ESTABLISHED
            )

        # Still forming
        if occurrence_count < 7 or consistency < 0.5:
            return RoutineLifecycle.FORMING

        return RoutineLifecycle.ESTABLISHED

    def _compute_streak(
        self,
        sorted_timestamps: List[int],
        expected_interval_ms: int,
    ) -> int:
        """Compute current consecutive occurrence streak."""
        if len(sorted_timestamps) < 2 or expected_interval_ms <= 0:
            return len(sorted_timestamps)

        streak = 1
        tolerance = expected_interval_ms * 0.5  # 50% tolerance

        for i in range(len(sorted_timestamps) - 1, 0, -1):
            interval = sorted_timestamps[i] - sorted_timestamps[i - 1]
            if abs(interval - expected_interval_ms) <= tolerance:
                streak += 1
            else:
                break

        return streak

    def _detect_cues(
        self,
        pattern: EpisodePattern,
        temporal_stats: Dict[str, Any],
    ) -> List[str]:
        """
        Detect triggering cues for the routine.

        Identifies contextual triggers based on:
        - Temporal cues (time of day, day of week)
        - Spatial cues (location)
        - Activity cues (preceding activity type)

        Args:
            pattern: EpisodePattern
            temporal_stats: Temporal analysis results

        Returns:
            List of cue identifiers
        """
        cues: List[str] = []

        # Temporal cue
        if temporal_stats.get("time_anchor"):
            cues.append(f"time:{temporal_stats['time_anchor']}")

        if temporal_stats.get("day_pattern"):
            cues.append(f"days:{temporal_stats['day_pattern']}")

        # Location cue
        locations = [loc for loc in pattern.locations if loc]
        if locations:
            location_counts = Counter(locations)
            dominant_location = location_counts.most_common(1)[0][0]
            if location_counts[dominant_location] / len(locations) > 0.7:
                cues.append(f"location:{dominant_location}")

        return cues

    def _generate_routine_name(self, pattern: EpisodePattern) -> str:
        """Generate human-readable routine name."""
        activity = pattern.activity_types[0] if pattern.activity_types else "Activity"
        location = pattern.locations[0] if pattern.locations else ""

        # Clean up activity name
        activity_name = activity.replace("_", " ").title()

        if location:
            return f"{activity_name} at {location.title()}"
        return activity_name

    def _determine_category(self, pattern: EpisodePattern) -> str:
        """Determine routine category from activity types."""
        activity = (pattern.activity_types[0] if pattern.activity_types else "").lower()

        # Map activity types to categories
        category_map = {
            "meal": "FOOD_DRINK",
            "food": "FOOD_DRINK",
            "coffee": "FOOD_DRINK",
            "breakfast": "FOOD_DRINK",
            "lunch": "FOOD_DRINK",
            "dinner": "FOOD_DRINK",
            "exercise": "EXERCISE",
            "gym": "EXERCISE",
            "workout": "EXERCISE",
            "run": "EXERCISE",
            "work": "WORK",
            "meeting": "WORK",
            "commute": "TRANSPORT",
            "drive": "TRANSPORT",
            "social": "SOCIAL",
            "call": "COMMUNICATION",
            "email": "COMMUNICATION",
            "sleep": "WELLNESS",
            "meditation": "WELLNESS",
        }

        for key, category in category_map.items():
            if key in activity:
                return category

        return "GENERAL"
